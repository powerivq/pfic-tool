"""Distribution-only FTC scope and event/lot allocation regressions."""
import unittest
from test_calculator import tx, cfg
from pfic import calculate, TableFX, InputError
from pfic.numbers import Q

class DistributionFTCTests(unittest.TestCase):
    def events(self):
        return [tx('a','BUY','2021-01-01','1','100'),
                tx('b','BUY','2021-06-01','3','300'),
                tx('d','DIVIDEND','2023-06-01',amount='100',withholding='10',eligibility_date='2023-05-31')]

    def test_withholding_allocated_to_blocks_and_years(self):
        r=calculate(self.events(),cfg(claim_foreign_tax_credit=True,foreign_taxes_creditable=True),TableFX())
        worksheets=[b['worksheets'][0] for b in r['blocks']]
        self.assertEqual([w['withholding_usd'] for w in worksheets],[Q('2.5'),Q('7.5')])
        for w in worksheets:
            tax=w['tax']
            self.assertEqual(sum(a['allocated_credit'] for a in tax['annual_allocations']),w['withholding_usd'])
            self.assertEqual(tax['16d']+w['current_year_foreign_tax_credit_candidate_usd'],w['withholding_usd'])
            self.assertEqual(tax['16e'],tax['16c']-tax['16d'])

    def test_claim_disabled_keeps_withholding_without_credit(self):
        r=calculate(self.events(),cfg(),TableFX())
        self.assertEqual(r['summary_usd']['1291_credit'],0)
        self.assertEqual(sum(b['worksheets'][0]['withholding_usd'] for b in r['blocks']),10)

    def test_creditability_confirmation_required(self):
        with self.assertRaises(InputError):cfg(claim_foreign_tax_credit=True)

    def test_nonexcess_distribution_credit_stays_current_year(self):
        r=calculate([tx('a','BUY','2023-01-01','1','100'),
                     tx('d','DIVIDEND','2023-06-01',amount='100',withholding='10',eligibility_date='2023-05-31')],
                    cfg(claim_foreign_tax_credit=True,foreign_taxes_creditable=True),TableFX())
        w=r['blocks'][0]['worksheets'][0]
        self.assertIsNone(w['tax'])
        self.assertEqual(w['current_year_foreign_tax_credit_candidate_usd'],10)
        self.assertEqual(r['summary_usd']['1291_credit'],0)

    def test_sale_withholding_not_accepted(self):
        with self.assertRaises(InputError):tx('s','SELL','2023-06-01','1','200',withholding='10')

if __name__=='__main__':unittest.main()
