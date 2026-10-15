import unittest
from datetime import date,timedelta
from decimal import Decimal,localcontext
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import csv,json,random
from pfic import *
from pfic.numbers import Q,dec,money
from pfic.tax import holding_days,section1291,mtm_year_end,mtm_sale,interest_factor,interest_schedule
from pfic.engine import allocate_dividends
from pfic.model import COLUMNS


def tx(id,type,d,units='0',amount='0',seq=1,**kw):
    return Transaction(id,type,d,seq,kw.pop('currency','USD'),amount,units,**kw)

def cfg(year=2023,**kw):
    args=dict(tax_year=year,fund_name='Synthetic test fund',first_pfic_year=2018,us_person_since='2000-01-01',complete_history=True,ordinary_dividends_confirmed=True,due_dates={y:date(y+1,4,15) for y in range(2000,2026)})
    args.update(kw);return Config(**args)

def calc(t,**kw):return calculate(t,cfg(**kw),TableFX())

class ExactTests(unittest.TestCase):
    def test_float_rejected(self):
        for x in [0.1,float('nan'),float('inf'),True]:
            with self.subTest(x=x),self.assertRaises(InputError):Q(x)
    def test_nonfinite_rejected(self):
        for x in ['NaN','Infinity','-Infinity','']:
            with self.subTest(x=x),self.assertRaises(InputError):Q(x)
    def test_decimal_exact(self):self.assertEqual(Q('0.1')+Q('0.2'),Q('0.3'))
    def test_round_half_up(self):
        self.assertEqual(money(Q('1.50'),0),'2');self.assertEqual(money(Q('-1.50'),0),'-2')
    def test_context_independence(self):
        with localcontext() as ctx:
            ctx.prec=3
            self.assertEqual(Q('123456.789')+Q('0.001'),Q('123456.790'))
    def test_rational_conservation(self):
        pieces=[Q('10.01')/3]*3;self.assertEqual(sum(pieces),Q('10.01'))

class LotTests(unittest.TestCase):
    def test_half_sale(self):
        b=partition([tx('a','BUY','2020-01-01','10','101'),tx('s','SELL','2023-01-01','5','70')])
        self.assertEqual([x.units for x in b],[Q(5),Q(5)])
        self.assertEqual(sum(x.purchase_cost for x in b),Q(101))
    def test_fifo_cross_lots(self):
        b=partition([tx('a','BUY','2020-01-01','3','30'),tx('b','BUY','2021-01-01','7','140'),tx('s','SELL','2023-01-01','5','150')])
        sold=[x for x in b if x.sale]
        self.assertEqual([(x.buy.id,x.units) for x in sold],[('a',Q(3)),('b',Q(2))]);self.assertEqual(sum(x.proceeds for x in sold),150)
    def test_accounts_separate(self):
        with self.assertRaises(InputError):partition([tx('a','BUY','2020-01-01','10','100',account='A'),tx('s','SELL','2023-01-01','1','20',account='B')])
    def test_oversell(self):
        with self.assertRaises(InputError):partition([tx('s','SELL','2023-01-01','1','20')])
    def test_duplicate_ids(self):
        with self.assertRaises(InputError):partition([tx('a','BUY','2020-01-01','1','1'),tx('a','BUY','2020-01-02','1','1')])
    def test_duplicate_order(self):
        with self.assertRaises(InputError):partition([tx('a','BUY','2020-01-01','1','1'),tx('b','BUY','2020-01-01','1','1')])
    def test_same_day_fifo(self):
        b=partition([tx('b','BUY','2020-01-01','1','20',seq=2),tx('a','BUY','2020-01-01','1','10',seq=1),tx('s','SELL','2023-01-01','1','30')]);self.assertEqual([x.buy.id for x in b if x.sale],['a'])
    def test_fee_basis_and_net_proceeds(self):
        r=calc([tx('a','BUY','2020-01-01','10','99',fee='1'),tx('s','SELL','2023-01-01','10','151',fee='1')]);w=r['blocks'][0]['worksheets'][0];self.assertEqual(w['15f'],50)
    def test_random_partition_invariants(self):
        rng=random.Random(234)
        for run in range(80):
            buys=[tx(f'b{i}','BUY',f'2020-01-{i+1:02}','0.03',str(rng.randint(1,1000))) for i in range(10)]
            total=sum((b.amount for b in buys),Q(0));sold_units=Q(rng.randint(1,29))/100
            b=partition(buys+[tx('s','SELL','2023-01-01',sold_units,'100')]);self.assertEqual(sum(x.units for x in b),Q('.30'));self.assertEqual(sum(x.purchase_cost for x in b),total);self.assertEqual(sum(x.proceeds for x in b if x.sale),100)

class DividendTests(unittest.TestCase):
    def test_proportional_allocation(self):
        t=[tx('a','BUY','2020-01-01','100','100'),tx('b','BUY','2021-01-01','300','300'),tx('d','DIVIDEND','2023-06-01',amount='40',eligibility_date='2023-05-01')]
        r=calc(t);self.assertEqual([b['worksheets'][0]['allocated_dividend_local'] for b in r['blocks']],[10,30])
    def test_eligibility_date_required(self):
        with self.assertRaises(InputError):tx('d','DIVIDEND','2023-01-01',amount='40')
    def test_eligibility_order_required(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2023-01-01','1','1'),tx('d','DIVIDEND','2023-06-01',amount='1',eligibility_date='2023-01-01')])
    def test_excludes_later_purchase(self):
        t=[tx('a','BUY','2020-01-01','1','1'),tx('b','BUY','2023-05-15','3','3'),tx('d','DIVIDEND','2023-06-01',amount='4',eligibility_date='2023-05-01')]
        r=calc(t);self.assertEqual(r['blocks'][0]['worksheets'][0]['allocated_dividend_local'],4);self.assertEqual(r['blocks'][1]['worksheets'],[])
    def test_payment_after_sale(self):
        r=calc([tx('a','BUY','2020-01-01','1','1'),tx('s','SELL','2023-05-15','1','2'),tx('d','DIVIDEND','2023-06-01',amount='4',eligibility_date='2023-05-01')]);self.assertEqual(r['blocks'][0]['worksheets'][0]['allocated_dividend_local'],4)
    def test_partial_sale_keeps_prior_dividend_history(self):
        t=[tx('a','BUY','2020-01-01','10','100'),tx('d1','DIVIDEND','2021-06-01',amount='10',eligibility_date='2021-05-01'),tx('s','SELL','2022-06-01','5','70'),tx('d2','DIVIDEND','2023-06-01',amount='10',eligibility_date='2023-05-01')]
        r=calc(t);hist=[b['distribution_history'][0]['gross_local'] for b in r['blocks']];self.assertEqual(hist,[5,5]);self.assertEqual(sum(hist),10)
    def test_first_holding_year_no_excess(self):
        r=calc([tx('a','BUY','2023-01-01','1','1'),tx('d','DIVIDEND','2023-06-01',amount='100',eligibility_date='2023-05-01')]);self.assertEqual(r['summary_usd']['ordinary_dividends'],100);self.assertEqual(r['summary_usd']['1291_additional_tax'],0)
    def test_dec31_purchase_first_holding_year(self):
        r=calc([tx('a','BUY','2022-12-31','1','1'),tx('d','DIVIDEND','2023-06-01',amount='100',eligibility_date='2023-05-01')]);self.assertEqual(r['summary_usd']['ordinary_dividends'],100)
    def test_prior_excluded_amount_not_in_average(self):
        r=calc([tx('a','BUY','2021-01-01','1','1'),tx('d1','DIVIDEND','2022-07-01',amount='100',eligibility_date='2022-06-01'),tx('d2','DIVIDEND','2023-07-01',amount='100',eligibility_date='2023-06-01')]);b=r['blocks'][0];self.assertLess(b['worksheets'][0]['15b'],100);self.assertEqual(b['worksheets'][0]['15b'],b['distribution_history'][0]['included_local'])
    def test_multiple_dividends_apportion_annual_excess(self):
        r=calc([tx('a','BUY','2021-01-01','1','1'),tx('d1','DIVIDEND','2021-06-01',amount='80',eligibility_date='2021-05-01'),tx('d2','DIVIDEND','2023-06-01',amount='100',eligibility_date='2023-05-01'),tx('d3','DIVIDEND','2023-12-01',amount='300',eligibility_date='2023-11-01')]);w=r['blocks'][0]['worksheets'];self.assertEqual(w[0]['15d'],50);self.assertEqual(w[0]['event_excess_usd'],Q('87.5'));self.assertEqual(w[1]['event_excess_usd'],Q('262.5'))
    def test_reinvestment_new_lot(self):
        r=calc([tx('a','BUY','2023-01-01','100','100'),tx('d','DIVIDEND','2023-06-01',amount='2',eligibility_date='2023-05-31'),tx('r','REINVEST','2023-06-01','2','2',seq=2,linked_dividend_id='d')]);self.assertEqual(r['ending_units'],102);self.assertEqual(len(r['blocks']),2);self.assertEqual(r['summary_usd']['ordinary_dividends'],2)
    def test_reinvestment_over_net_blocked(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2023-01-01','100','100'),tx('d','DIVIDEND','2023-06-01',amount='2',withholding='1',eligibility_date='2023-05-31'),tx('r','REINVEST','2023-06-01','2','2',seq=2,linked_dividend_id='d')])
    def test_constant_nav_can_have_usd_gain(self):
        fx=TableFX([Rate('CNY','2020-01-01','7','fixture'),Rate('CNY','2023-01-01','6','fixture')])
        r=calculate([tx('a','BUY','2020-01-01','100','100',currency='CNY'),tx('s','SELL','2023-01-01','100','100',currency='CNY')],cfg(),fx);self.assertEqual(r['blocks'][0]['worksheets'][0]['15f'],Q(100)/6-Q(100)/7)
    def test_local_currency_threshold_before_usd(self):
        fx=TableFX([Rate('CNY','2022-01-01','7','fixture'),Rate('CNY','2022-06-01','8','fixture'),Rate('CNY','2023-06-01','6','fixture')])
        r=calculate([tx('a','BUY','2022-01-01','1','7',currency='CNY'),tx('d1','DIVIDEND','2022-06-01',amount='80',eligibility_date='2022-05-31',currency='CNY'),tx('d2','DIVIDEND','2023-06-01',amount='120',eligibility_date='2023-05-31',currency='CNY')],cfg(),fx)
        w=r['blocks'][0]['worksheets'][0];self.assertEqual(w['annual_excess'],20);self.assertEqual(w['event_excess_usd'],Q(20)/6)
    def test_foreign_credit_capped_per_year(self):
        r=section1291(100,'2020-01-01','2023-01-01',2020,cfg().due_dates,1000);self.assertEqual(r['16e'],0);self.assertEqual(r['16f'],0)

class TaxTests(unittest.TestCase):
    def test_leap_days(self):self.assertEqual(holding_days('2019-12-31','2020-12-31'),{2020:366})
    def test_cross_year_endpoints(self):self.assertEqual(holding_days('2022-12-30','2023-01-01'),{2022:1,2023:1})
    def test_same_day_rejected(self):
        with self.assertRaises(InputError):holding_days('2023-01-01','2023-01-01')
    def test_annual_allocation_conservation(self):
        r=section1291('10.01','2020-01-01','2023-03-04',2020,cfg().due_dates);self.assertEqual(sum(a['allocated_excess_usd'] for a in r['annual_allocations']),Q('10.01'))
    def test_no_loss_netting_against_gain(self):
        r=calc([tx('a','BUY','2020-01-01','1','10'),tx('b','BUY','2021-01-01','1','30'),tx('s','SELL','2023-06-01','2','40')]);w=[b['worksheets'][0] for b in r['blocks']];self.assertEqual(w[0]['15f'],10);self.assertEqual(w[1]['15f'],-10);self.assertGreater(r['summary_usd']['1291_additional_tax'],0)
    def test_due_dates_required(self):
        with self.assertRaises(InputError):section1291(1,'2020-01-01','2023-01-01',2020,{})
    def test_current_year_only_no_interest(self):
        r=section1291(100,'2023-01-01','2023-06-01',2020,{});self.assertEqual(r['16b'],100);self.assertEqual(r['16f'],0)
    def test_pre_pfic_ordinary(self):
        r=section1291(100,'2020-01-01','2023-06-01',2023,{});self.assertEqual(r['16b'],100)
    def test_interest_one_day(self):
        f,t=interest_factor(date(2023,1,1),date(2023,1,2));self.assertLess(abs(f-Decimal(7)/100/365),Decimal('1e-28'))
    def test_interest_leap(self):
        f,t=interest_factor(date(2024,1,1),date(2024,1,2));self.assertEqual(t[0]['year_days'],366)
    def test_interest_quarter_boundary(self):
        f,t=interest_factor(date(2022,3,31),date(2022,4,2));self.assertEqual(len(t),2);self.assertEqual([s['annual_rate'] for s in t],[Q('.03'),Q('.04')])
    def test_interest_no_extrapolation(self):
        with self.assertRaises(InputError):interest_factor(date(2030,1,1),date(2030,2,1))
    def test_whole_dollars_not_intermediate_rounding(self):
        r=section1291('1.49','2020-01-01','2023-01-01',2020,cfg().due_dates);self.assertEqual(r['amount_usd'],Q('1.49'))

class MTMTests(unittest.TestCase):
    def test_gain_increases_basis_and_unreversed(self):
        r=mtm_year_end(100,140,0);self.assertEqual(r['ending_basis'],140);self.assertEqual(r['ending_unreversed'],40)
    def test_decline_limited(self):
        r=mtm_year_end(140,80,40);self.assertEqual(r['12'],40);self.assertEqual(r['ending_basis'],100);self.assertEqual(r['unrecognized_decline'],20)
    def test_no_inclusion_no_deduction(self):self.assertEqual(mtm_year_end(100,80,0)['ending_basis'],100)
    def test_sale_ordinary_and_other_loss(self):
        r=mtm_sale(140,80,40);self.assertEqual(r['14b'],40);self.assertEqual(r['14c'],20)
    def test_multiple_years(self):
        r=calc([tx('a','BUY','2021-01-01','10','100')],regime='mtm',election_year=2021,mtm_eligible=True,election_valid=True,valuations={2021:Valuation('14','USD'),2022:Valuation('8','USD'),2023:Valuation('12','USD')});self.assertEqual(r['blocks'][0]['ending_basis_usd'],120);self.assertEqual(r['blocks'][0]['ending_unreversed_inclusions'],20)
    def test_transition_gain_1291(self):
        r=calc([tx('a','BUY','2020-01-01','1','100')],regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True,valuations={2023:Valuation('150','USD')});w=r['blocks'][0]['worksheets'][0];self.assertEqual(w['kind'],'mtm_transition');self.assertEqual(w['15f'],50);self.assertEqual(w['ending_unreversed'],50)
    def test_transition_decline_no_deduction(self):
        r=calc([tx('a','BUY','2020-01-01','1','100')],regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True,valuations={2023:Valuation('80','USD')});self.assertEqual(r['blocks'][0]['ending_basis_usd'],100)
    def test_transition_sale_1291(self):
        r=calc([tx('a','BUY','2020-01-01','2','200'),tx('s','SELL','2023-05-01','1','150')],regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True,valuations={2023:Valuation('160','USD')});self.assertEqual([w for b in r['blocks'] for w in b['worksheets'] if w['kind']=='sale'][0]['form_part'],'V')
    def test_transition_inclusion_carries_forward(self):
        r=calc([tx('a','BUY','2020-01-01','1','100')],regime='mtm',election_year=2022,mtm_eligible=True,election_valid=True,valuations={2022:Valuation('150','USD'),2023:Valuation('120','USD')});self.assertEqual(r['blocks'][0]['ending_unreversed_inclusions'],20);self.assertEqual(r['summary_usd']['mtm_ordinary_income'],-30)
    def test_partial_sale_splits_unreversed(self):
        r=calc([tx('a','BUY','2021-01-01','10','100'),tx('s','SELL','2023-05-01','5','60')],regime='mtm',election_year=2021,mtm_eligible=True,election_valid=True,valuations={2021:Valuation('14','USD'),2022:Valuation('14','USD'),2023:Valuation('14','USD')});sold=next(b for b in r['blocks'] if b['sale_id']);self.assertEqual(sold['worksheets'][0]['14a'],20);self.assertEqual(sold['worksheets'][0]['14b'],10)
    def test_missing_valuation_blocked(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2021-01-01','1','100')],regime='mtm',election_year=2021,mtm_eligible=True,election_valid=True)
    def test_eligibility_not_assumed(self):
        with self.assertRaises(InputError):cfg(regime='mtm',election_year=2023)

class FXTests(unittest.TestCase):
    def test_effective_rate_no_lookahead(self):
        f=TableFX([Rate('CNY','2023-03-31','7','x'),Rate('CNY','2023-06-30','6','x')]);self.assertEqual(f.usd(70,'CNY',date(2023,5,1)),10)
    def test_rate_boundary(self):
        f=TableFX([Rate('CNY','2023-03-31','7','x'),Rate('CNY','2023-06-30','6','x')]);self.assertEqual(f.usd(60,'CNY',date(2023,6,30)),10)
    def test_missing_rate(self):
        with self.assertRaises(InputError):TableFX().usd(1,'CNY',date(2023,1,1))
    def test_stale_rate(self):
        with self.assertRaises(InputError):TableFX([Rate('CNY','2022-01-01','7','x')]).usd(1,'CNY',date(2023,1,1))
    def test_conflicting_rate(self):
        with self.assertRaises(InputError):TableFX([Rate('CNY','2023-01-01','7','x'),Rate('CNY','2023-01-01','6','x')]).usd(1,'CNY',date(2023,1,1))
    def test_policy_replaceable(self):
        class Custom:
            name='custom'
            def select(self,records,currency,when):return records[0]
        f=TableFX([Rate('CNY','2023-01-01','7','x')],Custom());self.assertEqual(f.usd(70,'CNY',date(2023,5,1)),10);self.assertEqual(f.audit[0]['policy'],'custom')
    def test_usd_no_network(self):self.assertEqual(TreasuryFX(offline=True).usd('1.23','USD','2023-01-01'),Q('1.23'))
    def test_network_cache_and_offline(self):
        data={'data':[{'effective_date':'2023-03-31','record_date':'2023-03-31','currency':'Renminbi','exchange_rate':'6.867'}],'meta':{'total-pages':1}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):return json.dumps(data).encode()
        with TemporaryDirectory() as d,patch('urllib.request.urlopen',return_value=Response()) as call:
            f=TreasuryFX(d);a=f.usd('100','CNY','2023-04-01');call.assert_called_once()
            g=TreasuryFX(d,offline=True);self.assertEqual(a,g.usd('100','CNY','2023-04-01'))
    def test_cache_tamper_detected(self):
        with TemporaryDirectory() as d:
            f=TreasuryFX(d,offline=True)
            with self.assertRaises(InputError):f.usd(1,'CNY','2023-01-01')

class ValidationTests(unittest.TestCase):
    def test_missing_confirmation_date(self):
        with self.assertRaises(InputError):tx('a','BUY','','1','1')
    def test_string_boolean_rejected(self):
        with self.assertRaises(InputError):cfg(complete_history='false')
    def test_mtm_no_year_end_ownership(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2020-01-01','1','1'),tx('s','SELL','2023-06-01','1','2')],regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True)
    def test_future_tax_year_rejected(self):
        with self.assertRaises(InputError):cfg(2030)
    def test_history_confirmation_required(self):
        with self.assertRaises(InputError):cfg(complete_history=False)
    def test_pre_residency_purchase_preserved(self):
        r=calc([tx('a','BUY','1999-01-01','1','1')])
        self.assertEqual(r['blocks'][0]['original_basis_usd'],1)
        self.assertEqual(r['blocks'][0]['acquisition_date'],date(1999,1,1))
    def test_ending_balance(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2020-01-01','1','1')],ending_units='2')
    def test_wash_sale_risk_blocked(self):
        with self.assertRaises(InputError):calc([tx('a','BUY','2020-01-01','1','10'),tx('s','SELL','2023-06-01','1','5'),tx('r','BUY','2023-06-02','1','5')])
    def test_future_sales_not_applied(self):
        r=calc([tx('a','BUY','2020-01-01','1','1'),tx('s','SELL','2024-06-01','1','5')]);self.assertEqual(r['ending_units'],1)
    def test_2023_mapping(self):
        r=calc([tx('a','BUY','2020-01-01','1','1'),tx('d','DIVIDEND','2023-06-01',amount='10',eligibility_date='2023-05-31')]);self.assertIn('15e',r['blocks'][0]['worksheets'][0]);self.assertNotIn('15e(2)',r['blocks'][0]['worksheets'][0])
    def test_2025_mapping(self):
        r=calc([tx('a','BUY','2020-01-01','1','1'),tx('d','DIVIDEND','2025-06-01',amount='10',eligibility_date='2025-05-31')],year=2025);self.assertIn('15e(2)',r['blocks'][0]['worksheets'][0])
    def test_report_rounding_and_exact_values(self):
        r=calc([tx('a','BUY','2020-01-01','1.2345','1.49')])
        with TemporaryDirectory() as d:
            html,data=write_report(r,d);text=html.read_text();self.assertIn('whole dollars',text);self.assertIn('1.2345',text);self.assertIn('149/100',data.read_text())
    def test_csv_required_zero(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'x.csv';p.write_text('id,type,date,sequence,currency,amount,units,fee,withholding\na,BUY,2023-01-01,1,USD,1,1,,0\n')
            with self.assertRaises(InputError):read_csv(p)

if __name__=='__main__':unittest.main()
