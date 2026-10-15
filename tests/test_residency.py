"""Residency regression oracles: exact fractions and independent date iteration.

§1291 uses original acquisition through event, with pre-residency days classified
as pre-PFIC. §1296(d)(5)(ii) dollar facts are preserved in the end-to-end fixture;
residency/sale years shift 2005/2006 to 2023/2024 for supported form mappings.
"""
import unittest
from contextlib import redirect_stdout
from io import StringIO
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from pfic import Config, Valuation, TableFX, Rate, calculate, write_report, InputError
from pfic.tax import section1291, allocation_periods, residency_mtm_sale
from pfic.numbers import Q, encode
from test_calculator import tx, cfg


def config(year=2023, **kw):
    return cfg(year,us_person_since='2022-07-17',first_pfic_year=2018,**kw)


def mtm_config(year=2024, **kw):
    values=dict(tax_year=year,fund_name='Synthetic residency test',first_pfic_year=1995,
                us_person_since='2023-01-01',complete_history=True,
                ordinary_dividends_confirmed=True,regime='mtm',election_year=2023,
                mtm_eligible=True,election_valid=True,
                residency_opening_valuation=Valuation(100,'USD'),
                valuations={2023:Valuation(110,'USD'),2024:Valuation(110,'USD')})
    values.update(kw)
    return Config(**values)


class Residency1291Tests(unittest.TestCase):
    def test_july17_exact_annual_split(self):
        # 2021 full year, 2022 197 pre-resident + 168 resident, Jan 1 2023.
        r=section1291(731,'2020-12-31','2023-01-01',2018,
                      {2022:date(2023,4,15),2023:date(2024,4,15)},
                      pfic_start_date='2022-07-17')
        self.assertEqual([(p['year'],p['category'],p['days']) for p in r['annual_allocations']],
                         [(2021,'pre_PFIC',365),(2022,'pre_PFIC',197),
                          (2022,'prior_PFIC',168),(2023,'current',1)])
        self.assertEqual(r['16b'],563)
        self.assertEqual(r['16c'],Q('62.16'))
        self.assertEqual(r['holding_days'],731)
        self.assertEqual(sum(p['allocated_excess_usd'] for p in r['annual_allocations']),731)

    def test_boundary_against_independent_daily_oracle(self):
        for residency in [date(2020,2,29),date(2022,7,17),date(2023,1,1)]:
            acquired=date(2019,12,31);event=date(2023,3,1)
            expected={};cursor=acquired+timedelta(days=1)
            while cursor<=event:
                category='current' if cursor.year==event.year else ('pre_PFIC' if cursor<residency else 'prior_PFIC')
                key=(cursor.year,category);expected[key]=expected.get(key,0)+1
                cursor+=timedelta(days=1)
            rows=allocation_periods(acquired,event,2018,residency)
            self.assertEqual({(p['year'],p['category']):p['days'] for p in rows},expected)

    def test_engine_original_cost_not_residency_value(self):
        r=calculate([tx('b','BUY','2020-12-31','1','100'),tx('s','SELL','2023-01-01','1','831')],config(),TableFX())
        w=r['blocks'][0]['worksheets'][0]
        self.assertEqual(w['15f'],731)
        self.assertEqual(w['tax']['16b'],563)
        self.assertEqual(r['blocks'][0]['holding_start'],date(2021,1,1))

    def test_purchase_and_sale_fx_remain_separate(self):
        f=TableFX([Rate('CNY','2020-12-31',7,'fixture'),Rate('CNY','2023-01-01',6,'fixture')])
        r=calculate([tx('b','BUY','2020-12-31','1','700',currency='CNY'),
                     tx('s','SELL','2023-01-01','1','1200',currency='CNY')],config(),f)
        self.assertEqual(r['blocks'][0]['worksheets'][0]['15f'],100)
        self.assertEqual([a['transaction_date'] for a in f.audit],[date(2020,12,31),date(2023,1,1)])

    def test_pre_residency_sales_deplete_fifo_without_us_tax(self):
        r=calculate([tx('b','BUY','2020-01-01','10','100'),
                     tx('old','SELL','2022-07-16','4','80'),
                     tx('new','SELL','2022-07-17','2','60')],config(2022),TableFX())
        old=next(b for b in r['blocks'] if b['sale_id']=='old')
        new=next(b for b in r['blocks'] if b['sale_id']=='new')
        self.assertEqual(old['worksheets'],[])
        self.assertEqual(new['original_basis_usd'],20)
        self.assertEqual(new['worksheets'][0]['15f'],40)
        self.assertEqual(new['worksheets'][0]['tax']['16b'],40)
        self.assertEqual(r['summary_usd']['1291_additional_tax'],0)
        self.assertEqual(r['ending_units'],4)

    def test_pre_residency_dividend_preserved_in_lookback(self):
        r=calculate([tx('b','BUY','2020-01-01','1','100'),
                     tx('old','DIVIDEND','2021-06-01',amount='80',eligibility_date='2021-05-31'),
                     tx('new','DIVIDEND','2023-06-01',amount='100',eligibility_date='2023-05-31')],config(),TableFX())
        b=r['blocks'][0];w=b['worksheets'][0]
        self.assertEqual(w['15b'],80)
        self.assertEqual(w['15d'],Q(100)/3)
        self.assertEqual(w['event_excess_usd'],Q(200)/3)
        self.assertEqual(b['distribution_history'][0]['included_local'],80)
        self.assertTrue(b['distribution_history'][0]['lookback_only'])

    def test_same_year_pre_residency_dividend_not_taxed_or_credited(self):
        # No prior distributions: whole annual total is excess for testing, but
        # only the $30 post-residency payment is a U.S. §1291 event.
        r=calculate([tx('b','BUY','2020-01-01','1','100'),
                     tx('old','DIVIDEND','2022-07-16',amount='70',withholding='7',eligibility_date='2022-07-15'),
                     tx('new','DIVIDEND','2022-07-17',amount='30',withholding='3',eligibility_date='2022-07-15')],
                    config(2022,claim_foreign_tax_credit=True,foreign_taxes_creditable=True),TableFX())
        w=r['blocks'][0]['worksheets']
        self.assertEqual(len(w),1)
        self.assertEqual(w[0]['transaction_id'],'new')
        self.assertEqual(w[0]['15a'],100)
        self.assertEqual(w[0]['event_excess_usd'],30)
        self.assertEqual(w[0]['tax']['16b'],30)
        self.assertEqual(w[0]['current_year_foreign_tax_credit_candidate_usd'],3)

    def test_pre_residency_reinvestment_is_real_basis_lot(self):
        r=calculate([tx('b','BUY','2020-01-01','10','100'),
                     tx('d','DIVIDEND','2021-06-01',amount='20',eligibility_date='2021-05-31'),
                     tx('r','REINVEST','2021-06-01','2','20',seq=2,linked_dividend_id='d'),
                     tx('s','SELL','2023-06-01','11','220')],config(),TableFX())
        self.assertEqual(r['ending_units'],1)
        sold=[b for b in r['blocks'] if b['sale_id']]
        self.assertEqual([b['original_basis_usd'] for b in sold],[100,10])
        self.assertEqual(sum(b['original_basis_usd'] for b in r['blocks']),120)
        self.assertEqual(r['summary_usd']['ordinary_dividends'],0)

    def test_distribution_credit_split_matches_mixed_year_days(self):
        r=section1291(731,'2020-12-31','2023-01-01',2018,
                      {2022:date(2023,4,15),2023:date(2024,4,15)},Q('73.1'),pfic_start_date='2022-07-17')
        self.assertEqual(r['16d'],Q('16.8'))
        self.assertEqual(r['current_year_credit_candidate'],Q('56.3'))
        self.assertEqual(r['16e'],Q('45.36'))

    def test_optional_pfic_date_can_delay_not_advance(self):
        c=config(pfic_start_date='2022-08-01')
        self.assertEqual(c.effective_pfic_start,date(2022,8,1))
        with self.assertRaises(InputError):config(pfic_start_date='2022-07-16')

    def test_no_pre_residency_due_dates_required(self):
        r=calculate([tx('b','BUY','2010-01-01','1','100'),
                     tx('s','SELL','2022-07-17','1','150')],config(2022,due_dates={}),TableFX())
        self.assertEqual(r['summary_usd']['1291_current_ordinary_income'],50)
        self.assertEqual(r['summary_usd']['1291_interest'],0)

    def test_report_year_before_residency_rejected(self):
        with self.assertRaisesRegex(InputError,'precedes U.S. residency'):config(2021)

    def test_post_residency_purchase_has_no_pre_residency_days(self):
        r=calculate([tx('b','BUY','2022-08-01','1','100'),
                     tx('s','SELL','2023-08-01','1','150')],config(),TableFX())
        rows=r['blocks'][0]['worksheets'][0]['tax']['annual_allocations']
        self.assertFalse(any(p['category']=='pre_PFIC' for p in rows))

    def test_partial_sale_keeps_prior_distribution_history_exact(self):
        r=calculate([tx('b','BUY','2020-01-01','3','100'),
                     tx('d','DIVIDEND','2021-01-01',amount='10',eligibility_date='2020-12-31'),
                     tx('s','SELL','2023-01-01','1','50')],config(),TableFX())
        self.assertEqual(sum(b['original_basis_usd'] for b in r['blocks']),100)
        self.assertEqual(sum(b['distribution_history'][0]['included_local'] for b in r['blocks']),10)

    def test_html_json_show_residency_boundary_and_exact_reconciliation(self):
        r=calculate([tx('b','BUY','2020-12-31','1','100'),tx('s','SELL','2023-01-01','1','831')],config(),TableFX())
        with TemporaryDirectory() as d:
            h,j=write_report(r,d)
            self.assertIn('2022-07-17',h.read_text())
            self.assertIn('start inclusive',h.read_text())
            self.assertEqual(json.loads(j.read_text()),encode(r))


class ResidencyMTMTests(unittest.TestCase):
    def events(self, proceeds=120):
        return [tx('b','BUY','1995-01-01','1','50'),tx('s','SELL','2024-06-01','1',proceeds)]

    def test_d5ii_complete_example(self):
        first=calculate(self.events(),mtm_config(2023),TableFX())
        b=first['blocks'][0]
        self.assertEqual(first['summary_usd']['mtm_ordinary_income'],10)
        self.assertEqual(b['ending_basis_usd'],60)
        self.assertEqual(b['ending_mtm_basis_usd'],110)
        self.assertEqual(b['ending_unreversed_inclusions'],10)
        final=calculate(self.events(),mtm_config(),TableFX())
        w=final['blocks'][0]['worksheets'][0]
        self.assertEqual(w['total_gain_loss_usd'],60)
        self.assertEqual(w['ordinary_income'],10)
        self.assertEqual(w['capital_gain_usd'],50)
        self.assertEqual(final['summary_usd']['capital_gains_before_general_limitations'],50)
        self.assertEqual(w['ordinary_income']+w['capital_gain_usd']-w['other_loss'],w['total_gain_loss_usd'])

    def test_fmv_below_cost_no_downward_step(self):
        r=calculate([tx('b','BUY','1995-01-01','1','150')],
                    mtm_config(2023,valuations={2023:Valuation(110,'USD')}),TableFX())
        b=r['blocks'][0]
        self.assertEqual((b['ending_basis_usd'],b['ending_mtm_basis_usd']),(150,150))
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],0)

    def test_partial_sale_splits_both_bases_and_inclusions(self):
        t=[tx('b','BUY','1995-01-01','3','150'),tx('s','SELL','2024-06-01','1','120')]
        r=calculate(t,mtm_config(),TableFX())
        sold=next(b for b in r['blocks'] if b['sale_id'])
        held=next(b for b in r['blocks'] if not b['sale_id'])
        self.assertEqual(sold['worksheets'][0]['general_adjusted_basis_usd'],60)
        self.assertEqual(sold['worksheets'][0]['mtm_adjusted_basis_usd'],110)
        self.assertEqual(sold['worksheets'][0]['capital_gain_usd'],50)
        self.assertEqual((held['ending_basis_usd'],held['ending_mtm_basis_usd'],held['ending_unreversed_inclusions']),(120,220,20))

    def test_residency_value_uses_its_own_fx_date(self):
        f=TableFX([Rate('CNY','1995-01-01',7,'fixture'),Rate('CNY','2023-01-01',6,'fixture'),Rate('CNY','2023-12-31',5,'fixture')])
        r=calculate([tx('b','BUY','1995-01-01','1','350',currency='CNY')],
                    mtm_config(2023,residency_opening_valuation=Valuation(600,'CNY'),valuations={2023:Valuation(550,'CNY')}),f)
        self.assertEqual((r['blocks'][0]['ending_basis_usd'],r['blocks'][0]['ending_mtm_basis_usd']),(60,110))

    def test_missing_opening_valuation_blocked(self):
        with self.assertRaisesRegex(InputError,'residency_opening_valuation'):
            calculate(self.events(),mtm_config(residency_opening_valuation=None),TableFX())

    def test_midyear_first_year_mtm_explicitly_blocked(self):
        with self.assertRaisesRegex(InputError,'midyear residency'):
            calculate(self.events(),mtm_config(us_person_since='2023-07-17'),TableFX())

    def test_later_election_uses_original_basis_and_resident_only_deferred_days(self):
        r=calculate([tx('b','BUY','2020-12-31','1','100')],config(
            regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True,
            valuations={2023:Valuation(150,'USD')}),TableFX())
        b=r['blocks'][0];w=b['worksheets'][0]
        self.assertEqual(w['kind'],'mtm_transition')
        self.assertEqual(w['15f'],50)
        self.assertEqual((b['ending_basis_usd'],b['ending_mtm_basis_usd'],b['ending_unreversed_inclusions']),(150,150,50))
        self.assertEqual(sum(p['days'] for p in w['tax']['annual_allocations'] if p['category']=='prior_PFIC'),168)

    def test_election_before_residency_blocked(self):
        with self.assertRaisesRegex(InputError,'election cannot precede'):
            mtm_config(election_year=2022)

    def test_dual_basis_loss_not_silently_given_wrong_character(self):
        for proceeds in [100,60,40]:
            with self.subTest(proceeds=proceeds), self.assertRaisesRegex(InputError,'below MTM basis'):
                calculate(self.events(proceeds),mtm_config(),TableFX())

    def test_equal_basis_sale_loss_still_supported(self):
        r=residency_mtm_sale(110,110,90,10)
        self.assertEqual((r['ordinary_income'],r['other_loss'],r['capital_gain_usd']),(-10,10,0))

    def test_year_end_loss_does_not_deduct_residency_uplift(self):
        r=calculate([tx('b','BUY','1995-01-01','1','50')],
                    mtm_config(valuations={2023:Valuation(110,'USD'),2024:Valuation(40,'USD')}),TableFX())
        b=r['blocks'][0]
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],-10)
        self.assertEqual((b['ending_basis_usd'],b['ending_mtm_basis_usd'],b['ending_unreversed_inclusions']),(50,100,0))

    def test_pre_residency_sold_block_needs_no_opening_value(self):
        r=calculate([tx('b','BUY','1995-01-01','1','50'),tx('s','SELL','2022-06-01','1','120'),
                     tx('new','BUY','2023-06-01','1','100')],
                    mtm_config(2023,residency_opening_valuation=None),TableFX())
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],10)
        self.assertEqual(r['blocks'][0]['worksheets'],[])

    def test_cli_accepts_opening_valuation_object(self):
        from pfic.__main__ import main
        with TemporaryDirectory() as d:
            root=Path(d);csv=root/'fund.csv';config_path=root/'config.json';out=root/'out'
            csv.write_text('id,type,date,sequence,currency,amount,units,fee,withholding\nb,BUY,1995-01-01,1,USD,50,1,0,0\ns,SELL,2024-06-01,1,USD,120,1,0,0\n')
            config_path.write_text(json.dumps(dict(tax_year=2024,fund_name='Synthetic CLI',first_pfic_year=1995,
                us_person_since='2023-01-01',complete_history=True,ordinary_dividends_confirmed=True,
                regime='mtm',election_year=2023,mtm_eligible=True,election_valid=True,
                residency_opening_valuation={'unit_value':'100','currency':'USD'},
                valuations={'2023':{'unit_value':'110','currency':'USD'}})))
            with redirect_stdout(StringIO()), patch('sys.argv',['pfic','calculate',str(csv),'--config',str(config_path),'--out',str(out),'--offline']):
                self.assertEqual(main(),0)
            data=json.loads((out/'form8621.json').read_text())
            self.assertEqual(data['summary_usd']['capital_gains_before_general_limitations']['exact'],'50/1')



class ResidencyValidationTests(unittest.TestCase):
    def test_election_before_effective_pfic_status_rejected(self):
        with self.assertRaisesRegex(InputError, 'effective PFIC status'):
            mtm_config(pfic_start_date='2024-01-01')

    def test_negative_general_basis_rejected(self):
        with self.assertRaisesRegex(InputError, 'Negative general basis'):
            residency_mtm_sale(-1,100,120,0)


if __name__=='__main__':unittest.main()
