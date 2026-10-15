"""Treasury Decision 9123, final §1.1296-1 examples.

Dollar expectations transcribed independently from the regulation, not generated
by production functions. Pure tests retain original dollar facts. Integration
adaptations move reporting years to 2023/24 (supported forms); they are explicitly
not reproductions of historical 2005/07 tax or interest amounts. See coverage JSON.
"""
import unittest
from datetime import date
from pfic import Config, Transaction, Valuation, TableFX, calculate, InputError
from pfic.tax import mtm_year_end, mtm_sale, section1291
from pfic.numbers import Q


def transaction(id, kind, when, amount, units=1, **kw):
    return Transaction(id, kind, when, 1, 'USD', amount, units, **kw)


def run(transactions, year=2023, election=2023, first=2023, values=None):
    return calculate(transactions, Config(
        tax_year=year, fund_name='Treasury regulation fixture',
        first_pfic_year=first, us_person_since='1980-01-01',
        complete_history=True, ordinary_dividends_confirmed=True,
        regime='mtm', election_year=election, mtm_eligible=True,
        election_valid=True, valuations={y:Valuation(v,'USD') for y,v in (values or {}).items()},
        due_dates={y:date(y+1,4,15) for y in range(1987,2026)}), TableFX())


class TreasuryRegulationExamples(unittest.TestCase):
    def test_c7_example1_gain_and_basis(self):
        r=mtm_year_end(1000,1200,0)
        self.assertEqual(r['ordinary_income'],200)
        self.assertEqual(r['ending_basis'],1200)
        self.assertEqual(r['ending_unreversed'],200)

    def test_c7_example1_engine_no_step_up_when_becoming_pfic(self):
        # Original 1990 acquisition retained; PFIC/election year shifted 2005->2023.
        # The $1,100 value on becoming a PFIC is NOT an acquisition basis reset.
        r=run([transaction('buy','BUY','1990-01-01',1000)],values={2023:1200})
        b=r['blocks'][0]
        self.assertEqual(b['worksheets'][0]['form_part'],'IV')
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],200)
        self.assertEqual(b['ending_basis_usd'],1200)

    def test_c7_example3_sale_loss_within_inclusions(self):
        r=mtm_sale(1200,1100,200)
        self.assertEqual(r['ordinary_income'],-100)
        self.assertEqual(r['other_loss'],0)

    def test_c7_example3_engine_basis_carryforward(self):
        r=run([transaction('buy','BUY','1990-01-01',1000),
               transaction('sale','SELL','2024-12-01',1100)],year=2024,values={2023:1200})
        w=r['blocks'][0]['worksheets'][0]
        self.assertEqual((w['13b'],w['14a'],w['14b'],w['14c']),(1200,200,100,0))
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],-100)

    def test_c7_example5_sale_loss_exceeding_inclusions(self):
        r=mtm_sale(1200,900,200)
        self.assertEqual(r['ordinary_income'],-200)
        self.assertEqual(r['other_loss'],100)

    def test_c7_example5_engine_loss_split(self):
        r=run([transaction('buy','BUY','1990-01-01',1000),
               transaction('sale','SELL','2024-12-01',900)],year=2024,values={2023:1200})
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],-200)
        self.assertEqual(r['summary_usd']['other_losses_before_general_limitations'],100)
        # General capital-loss reporting/holding-period character remains external.

    def test_c7_example6_separate_basis_and_inclusions(self):
        a=mtm_year_end(500,800,0);b=mtm_year_end(1000,800,0)
        self.assertEqual((a['ordinary_income'],a['ending_basis'],a['ending_unreversed']),(300,800,300))
        self.assertEqual((b['ordinary_income'],b['ending_basis'],b['ending_unreversed']),(0,1000,0))
        self.assertEqual(b['unrecognized_decline'],200)

    def test_c7_example6_identified_second_lot_sale_primitive_only(self):
        # Regulation specifically identifies lot 2. FIFO engine must NOT be used
        # to assert the regulation's $100 loss on this selected lot.
        r=mtm_sale(1000,900,0)
        self.assertEqual((r['ordinary_income'],r['other_loss']),(0,100))

    def test_c7_example6_engine_year_end_lots_not_netted(self):
        r=run([transaction('lot1','BUY','2023-01-01',500,100),
               transaction('lot2','BUY','2023-06-01',1000,100)],values={2023:8})
        self.assertEqual([b['ending_basis_usd'] for b in r['blocks']],[800,1000])
        self.assertEqual([b['ending_unreversed_inclusions'] for b in r['blocks']],[300,0])
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],300)

    def test_c7_example6_fifo_variant_is_explicitly_different(self):
        r=run([transaction('lot1','BUY','2023-01-01',500,100),
               transaction('lot2','BUY','2023-06-01',1000,100),
               transaction('sale','SELL','2024-07-01',900,100)],year=2024,
              values={2023:8,2024:8})
        sold=next(b for b in r['blocks'] if b['sale_id'])
        self.assertEqual(sold['purchase_id'],'lot1')
        self.assertEqual(sold['worksheets'][0]['ordinary_income'],100)
        self.assertEqual(r['summary_usd']['other_losses_before_general_limitations'],0)

    def test_a3iii_transition_90_not_40_or_interest(self):
        # Shift 2005/06/07 to 2021/22/23; all stated dollar facts retained.
        r=run([transaction('buy','BUY','2021-01-01',150)],first=2021,
              values={2022:200,2023:240})
        b=r['blocks'][0];w=b['worksheets'][0]
        self.assertEqual(w['kind'],'mtm_transition')
        self.assertEqual(w['15f'],90)
        self.assertEqual(b['ending_basis_usd'],240)
        self.assertEqual(b['ending_unreversed_inclusions'],90)
        self.assertGreater(w['tax']['16f'],0)
        self.assertEqual(sum(a['allocated_excess_usd'] for a in w['tax']['annual_allocations']),90)

    def test_a3iii_transition_following_loss_uses_full_90(self):
        # Derived boundary case, not an additional numbered regulatory example.
        r=run([transaction('buy','BUY','2021-01-01',150)],year=2024,first=2021,
              values={2023:240,2024:100})
        b=r['blocks'][0]
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],-90)
        self.assertEqual((b['ending_basis_usd'],b['ending_unreversed_inclusions']),(150,0))

    def test_i4_example1_original_historical_allocation(self):
        # Original dates. Regulation states the $10 subject to §1291, not a
        # numerical tax/interest answer. Verify routing/conservation separately.
        r=section1291(10,'1992-01-01','2005-12-31',1992,
                      {y:date(y+1,4,15) for y in range(1992,2006)})
        self.assertEqual(r['amount_usd'],10)
        self.assertEqual(sum(a['allocated_excess_usd'] for a in r['annual_allocations']),10)
        self.assertEqual(r['holding_end'],date(2005,12,31))
        self.assertTrue(all(a['category']=='prior_PFIC' for a in r['annual_allocations'][:-1]))

    def test_i4_example1_engine_deemed_sale_and_basis(self):
        # $100/$110 basis/value chosen because example supplies only $10 excess.
        r=run([transaction('buy','BUY','1992-01-01',100)],first=1992,values={2023:110})
        b=r['blocks'][0];w=b['worksheets'][0]
        self.assertEqual((w['kind'],w['form_part'],w['15f']),('mtm_transition','V',10))
        self.assertEqual(w['tax']['holding_end'],date(2023,12,31))
        self.assertEqual((b['ending_basis_usd'],b['ending_unreversed_inclusions']),(110,10))
        self.assertEqual(r['summary_usd']['mtm_ordinary_income'],0)

    def test_d5ii_requires_opening_valuation(self):
        # Missing the opening value must block the dual-basis calculation.
        config=Config(tax_year=2023,fund_name='Residency fixture',first_pfic_year=1995,
                      us_person_since='2005-01-01',complete_history=True,
                      ordinary_dividends_confirmed=True,regime='mtm',election_year=2005,
                      mtm_eligible=True,election_valid=True)
        with self.assertRaisesRegex(InputError,'residency_opening_valuation'):
            calculate([transaction('buy','BUY','1995-01-01',50)],config,TableFX())

    def test_i2i_transition_dividend_remains_1291(self):
        # Rule-derived fixture (not a numbered example): zero prior distributions
        # means entire $20 election-year dividend is excess, plus $10 deemed gain.
        r=run([transaction('buy','BUY','2021-01-01',100),
               transaction('div','DIVIDEND','2023-06-01',20,0,eligibility_date='2023-05-31')],
              first=2021,values={2023:110})
        w=r['blocks'][0]['worksheets']
        self.assertEqual(w[0]['event_excess_usd'],20)
        self.assertEqual(w[0]['form_part'],'V')
        self.assertEqual(w[1]['15f'],10)
        self.assertEqual(r['blocks'][0]['ending_basis_usd'],110)

    def test_1291_1c3_ongoing_mtm_dividend_not_excess(self):
        r=run([transaction('buy','BUY','2023-01-01',100),
               transaction('div','DIVIDEND','2024-06-01',20,0,eligibility_date='2024-05-31')],
              year=2024,values={2023:110,2024:110})
        self.assertEqual(r['summary_usd']['ordinary_dividends'],20)
        self.assertEqual(r['summary_usd']['1291_additional_tax'],0)
        self.assertIsNone(r['blocks'][0]['worksheets'][0]['tax'])

if __name__=='__main__':unittest.main()
