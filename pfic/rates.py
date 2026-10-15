"""Pluggable FX policies; Treasury network adapter with immutable response cache."""
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import urllib.request
import urllib.parse
from .numbers import Q, InputError
from .model import day

@dataclass(frozen=True)
class Rate:
    currency: str
    effective_date: date
    foreign_per_usd: Fraction
    source: str
    record_date: date | None = None

    def __post_init__(self):
        object.__setattr__(self,'effective_date',day(self.effective_date))
        object.__setattr__(self,'foreign_per_usd',Q(self.foreign_per_usd))
        if self.record_date is not None:
            object.__setattr__(self,'record_date',day(self.record_date))
        if self.foreign_per_usd <= 0:
            raise InputError('FX rate must be positive')

class LatestEffective:
    name = 'treasury_latest_effective_on_or_before_v1'
    def select(self, records, currency, when):
        available=[r for r in records if r.currency==currency and r.effective_date <= when]
        if not available:
            raise InputError(f'No FX rate for {currency} on/before {when}')
        latest=max(r.effective_date for r in available)
        same=[r for r in available if r.effective_date==latest]
        # Distinct amendments with same effective date cannot be guessed.
        if len({r.foreign_per_usd for r in same}) != 1:
            raise InputError(f'Conflicting FX rates for {currency} at {latest}')
        if (when-latest).days > 120:
            raise InputError(f'Stale FX rate for {currency} at {when}: {latest}')
        return max(same,key=lambda r:r.record_date or r.effective_date)

class TableFX:
    def __init__(self, records=(), policy=None):
        self.records=list(records)
        self.policy=policy or LatestEffective()
        self.audit=[]
        self._seen=set()
    def rate(self,currency,when):
        when=day(when)
        r=Rate('USD',when,Q(1),'USD identity') if currency=='USD' else self.policy.select(self.records,currency,when)
        key=(currency,when,r.effective_date,r.foreign_per_usd)
        if key not in self._seen:
            self._seen.add(key)
            self.audit.append({'currency':currency,'transaction_date':when,'effective_date':r.effective_date,'foreign_per_usd':r.foreign_per_usd,'record_date':r.record_date,'source':r.source,'policy':self.policy.name})
        return r.foreign_per_usd
    def usd(self,amount,currency,when):
        return Q(amount)/self.rate(currency,when)

# Countries disambiguate shared currency names. Any other Treasury currency is
# supported by passing currency_countries={ISO: exact Treasury country label}.
COUNTRIES={'CNY':'China','EUR':'Euro Zone','GBP':'United Kingdom','JPY':'Japan','CAD':'Canada','AUD':'Australia','CHF':'Switzerland','HKD':'Hong Kong','SGD':'Singapore','NZD':'New Zealand','INR':'India','KRW':'Korea','TWD':'Taiwan','BRL':'Brazil','MXN':'Mexico','ZAR':'South Africa','SEK':'Sweden','NOK':'Norway','DKK':'Denmark','ILS':'Israel','THB':'Thailand','MYR':'Malaysia','IDR':'Indonesia','PHP':'Philippines'}

class TreasuryFX(TableFX):
    endpoint='https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange'
    def __init__(self,cache_dir=None,policy=None,currency_countries=None,offline=False):
        super().__init__(policy=policy)
        self.cache_dir=Path(cache_dir or Path.home()/'.cache'/'pfic-calculator'/'treasury')
        self.countries={**COUNTRIES,**(currency_countries or {})}
        self.offline=offline
        self._loaded=set()
    def _fetch_year(self,currency,year):
        country=self.countries.get(currency)
        if not country:
            raise InputError(f'No Treasury country mapping for {currency}; set currency_countries (no rates need to be supplied)')
        key=(currency,year,country)
        if key in self._loaded:return
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        params={'filter':f'country:eq:{country},record_date:gte:{year-1}-09-30,record_date:lte:{year}-12-31','page[size]':'1000','sort':'effective_date,record_date'}
        url=self.endpoint+'?'+urllib.parse.urlencode(params)
        filename=self.cache_dir/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if filename.exists():
            payload=json.loads(filename.read_text(encoding='utf-8'))
            raw=payload['response']
            if payload['url'] != url or hashlib.sha256(raw.encode()).hexdigest()!=payload['sha256']:
                raise InputError('Treasury cache integrity check failed')
        else:
            if self.offline:raise InputError(f'No cached Treasury data for {currency} {year}')
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'PFIC-calculator/0.1 (public Treasury data)'})
                with urllib.request.urlopen(request,timeout=30) as response:raw=response.read().decode('utf-8')
                payload={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'response':raw,'sha256':hashlib.sha256(raw.encode()).hexdigest()}
            except (OSError,ValueError) as e:
                raise InputError(f'Treasury request failed for {currency} {year}: {e}') from e
        try:
            data=json.loads(raw,parse_float=str)
            rows=data['data']
            if not rows or int(data['meta']['total-pages']) != 1:
                raise InputError(f'Unexpected/empty Treasury result for {country}; verify currency mapping')
            names={r['currency'] for r in rows}
            if len(names)!=1:raise InputError(f'Multiple Treasury currencies for {country}: {names}; explicit adapter required')
            records=[Rate(currency,r['effective_date'],r['exchange_rate'],url,r['record_date']) for r in rows]
        except (KeyError,ValueError,TypeError) as e:
            raise InputError(f'Invalid Treasury response: {e}') from e
        if not filename.exists():
            temp=filename.with_suffix('.tmp');temp.write_text(json.dumps(payload,indent=2),encoding='utf-8');temp.replace(filename)
        self.records.extend(records);self._loaded.add(key)
    def rate(self,currency,when):
        when=day(when)
        if currency!='USD':self._fetch_year(currency,when.year)
        return super().rate(currency,when)
