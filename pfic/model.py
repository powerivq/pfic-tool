from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from typing import Mapping
import csv
import re
from .numbers import Q, InputError

ZERO = Fraction(0)

def day(value):
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise InputError(f'Expected ISO date YYYY-MM-DD, got {value!r}')
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise InputError(str(e)) from e

@dataclass(frozen=True)
class Transaction:
    id: str
    type: str
    date: date
    sequence: int
    currency: str
    amount: Fraction
    units: Fraction = ZERO
    fee: Fraction = ZERO
    eligibility_date: date | None = None
    eligibility_sequence: int | None = None
    linked_dividend_id: str = ''
    withholding: Fraction = ZERO
    account: str = 'default'
    source: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'date', day(self.date))
        if self.eligibility_date is not None:
            object.__setattr__(self, 'eligibility_date', day(self.eligibility_date))
        for key in ('amount', 'units', 'fee', 'withholding'):
            object.__setattr__(self, key, Q(getattr(self, key)))
        if not self.id or not self.account:
            raise InputError('Transaction ID and account must be nonempty')
        if self.type not in ('BUY', 'SELL', 'DIVIDEND', 'REINVEST'):
            raise InputError(f'{self.id}: unsupported event {self.type}')
        if not re.fullmatch(r'[A-Z]{3}', self.currency):
            raise InputError(f'{self.id}: three-letter currency required')
        if type(self.sequence) is not int or self.sequence < 0:
            raise InputError(f'{self.id}: nonnegative integer sequence required')
        if self.eligibility_sequence is not None and (type(self.eligibility_sequence) is not int or self.eligibility_sequence < 0):
            raise InputError('Invalid eligibility sequence')
        if min(self.amount, self.units, self.fee, self.withholding) < 0:
            raise InputError(f'{self.id}: unsigned amounts/units required')
        if self.type == 'DIVIDEND':
            if not self.eligibility_date or self.eligibility_date > self.date:
                raise InputError(f'{self.id}: eligibility date required, no later than payment date')
            if self.units or self.fee or self.withholding > self.amount or self.amount <= 0:
                raise InputError(f'{self.id}: invalid dividend fields')
        else:
            if self.units <= 0 or self.withholding or self.eligibility_date or self.eligibility_sequence is not None:
                raise InputError(f'{self.id}: invalid trade fields')
            if self.type in ('BUY', 'REINVEST') and self.amount + self.fee <= 0:
                raise InputError(f'{self.id}: purchase cost must be positive')
            if self.type == 'SELL' and self.fee > self.amount:
                raise InputError(f'{self.id}: fee exceeds gross proceeds')
        if (self.type == 'REINVEST') != bool(self.linked_dividend_id):
            raise InputError(f'{self.id}: only REINVEST requires linked_dividend_id')

    @property
    def key(self):
        return (self.date, self.sequence)

@dataclass(frozen=True)
class Valuation:
    unit_value: Fraction
    currency: str
    source: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'unit_value', Q(self.unit_value))
        if self.unit_value < 0 or not re.fullmatch(r'[A-Z]{3}', self.currency):
            raise InputError('Invalid year-end valuation')

@dataclass(frozen=True)
class Config:
    tax_year: int
    fund_name: str
    first_pfic_year: int
    us_person_since: date
    complete_history: bool
    ordinary_dividends_confirmed: bool
    regime: str = '1291'
    election_year: int | None = None
    mtm_eligible: bool = False
    election_valid: bool = False
    valuations: Mapping[int, Valuation] = field(default_factory=dict)
    # Explicit unextended due dates prevent silently guessing holiday/disaster rules.
    due_dates: Mapping[int, date] = field(default_factory=dict)
    claim_foreign_tax_credit: bool = False
    foreign_taxes_creditable: bool = False
    ending_units: Fraction | None = None
    # Optional taxpayer-specific PFIC boundary; cannot precede either factual boundary.
    pfic_start_date: date | None = None
    residency_opening_valuation: Valuation | None = None

    def __post_init__(self):
        object.__setattr__(self, 'us_person_since', day(self.us_person_since))
        for flag in ('complete_history','ordinary_dividends_confirmed','mtm_eligible','election_valid','claim_foreign_tax_credit','foreign_taxes_creditable'):
            if type(getattr(self,flag)) is not bool:
                raise InputError(f'{flag} must be a boolean')
        if type(self.tax_year) is not int or not 2018 <= self.tax_year <= 2025:
            raise InputError('Verified Form 8621 mappings currently support tax years 2018–2025')
        if type(self.first_pfic_year) is not int or not 1987 <= self.first_pfic_year <= self.tax_year:
            raise InputError('first_pfic_year must be 1987 through reporting year')
        if self.us_person_since > date(self.tax_year,12,31):
            raise InputError('Reporting year precedes U.S. residency')
        if self.pfic_start_date is not None:
            object.__setattr__(self,'pfic_start_date',day(self.pfic_start_date))
            if self.pfic_start_date < max(self.us_person_since,date(self.first_pfic_year,1,1)):
                raise InputError('pfic_start_date cannot precede residency or first_pfic_year')
        if self.residency_opening_valuation is not None and not isinstance(self.residency_opening_valuation,Valuation):
            raise InputError('residency_opening_valuation must be a Valuation')
        if not self.complete_history:
            raise InputError('Complete acquisition/distribution history required; opening-state import not yet supported')
        if self.regime not in ('1291', 'mtm'):
            raise InputError('Regime must be 1291 or mtm')
        if self.regime == 'mtm':
            if type(self.election_year) is not int or self.election_year < self.first_pfic_year or not self.mtm_eligible or not self.election_valid:
                raise InputError('MTM needs eligible marketable stock, a confirmed valid election, and election_year')
            if self.election_year < self.us_person_since.year:
                raise InputError('MTM election cannot precede U.S. residency')
            if self.election_year < self.effective_pfic_start.year:
                raise InputError('MTM election cannot precede effective PFIC status')
        elif self.election_year is not None:
            raise InputError('Use regime=mtm for an election, including a future election')
        if self.claim_foreign_tax_credit and not self.foreign_taxes_creditable:
            raise InputError('Confirm creditability before claiming foreign tax credits')
        for year,v in self.valuations.items():
            if type(year) is not int or not isinstance(v, Valuation):
                raise InputError('valuations must map integer year to Valuation')
        for year,d in self.due_dates.items():
            if type(year) is not int or day(d).year < year + 1:
                raise InputError('Invalid return due date')
        if self.ending_units is not None:
            object.__setattr__(self, 'ending_units', Q(self.ending_units))

    @property
    def effective_pfic_start(self):
        return max(self.us_person_since,date(self.first_pfic_year,1,1),
                   self.pfic_start_date or date(self.first_pfic_year,1,1))

COLUMNS = ['id','type','date','sequence','currency','amount','units','fee','eligibility_date','eligibility_sequence','linked_dividend_id','withholding','account','source']

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise InputError('Missing or duplicate CSV headers')
        required = {'id','type','date','sequence','currency','amount','units','fee','withholding'}
        if required - set(reader.fieldnames):
            raise InputError(f'Missing CSV columns: {sorted(required - set(reader.fieldnames))}')
        unknown = set(reader.fieldnames) - set(COLUMNS)
        if unknown:
            raise InputError(f'Unknown columns: {sorted(unknown)}; use import-legacy for the old format')
        rows=[]
        for number,r in enumerate(reader,2):
            try:
                if None in r or any(v is None for v in r.values()):
                    raise InputError('CSV row length differs from header')
                r={k:v.strip() for k,v in r.items()}
                for key in ('units','fee','withholding'):
                    if r[key]=='':
                        raise InputError(f'{key} is required; use explicit 0')
                rows.append(Transaction(id=r['id'],type=r['type'],date=r['date'],sequence=int(r['sequence']),currency=r['currency'],amount=r['amount'],units=r['units'],fee=r['fee'],withholding=r['withholding'],eligibility_date=r.get('eligibility_date') or None,eligibility_sequence=int(r['eligibility_sequence']) if r.get('eligibility_sequence') else None,linked_dividend_id=r.get('linked_dividend_id',''),account=r.get('account') or 'default',source=r.get('source','')))
            except (ValueError, TypeError) as e:
                raise InputError(f'{path}: row {number}: {e}') from e
        return rows
