"""External benchmark comparisons are explicit discrepancies, not false matches.

Default examples retrieved from both user-supplied pages 2026-10-15.
Reference input: 2011-12-05 acquisition, 2025-06-01 event, first PFIC 2015.
"""
import unittest
from datetime import date
from decimal import Decimal,localcontext
from pfic.tax import section1291,distribution_excess,holding_days,interest_factor
from pfic.numbers import Q,money

DUE={year:date(year+1,4,15) for year in range(2011,2026)}

class ReferenceExamples(unittest.TestCase):
    def test_distribution_threshold_exact_match(self):
        r=distribution_excess('100000','60000',3)
        self.assertEqual(r['15c'],20000);self.assertEqual(r['15d'],25000);self.assertEqual(r['excess'],75000);self.assertEqual(r['nonexcess'],25000)
    def test_sale_current_and_pre_pfic_total_matches_reference(self):
        r=section1291(100000,'2011-12-05','2025-06-01',2015,DUE)
        self.assertEqual(money(r['16b'],0),'25858')
    def test_distribution_current_and_pre_pfic_total_matches_reference(self):
        r=section1291(75000,'2011-12-05','2025-06-01',2015,DUE,11250)
        self.assertEqual(money(r['16b'],0),'19393');self.assertEqual(money(r['16c'],0),'21008')
    def test_reference_day_discrepancy_is_preserved(self):
        # Reference shows 27 in 2011 and 151 in 2025. IRS Pub 550 convention:
        # exclude purchase date, include disposition date -> 26 and 152.
        days=holding_days('2011-12-05','2025-06-01')
        self.assertEqual(days[2011],26);self.assertEqual(days[2025],152)
        self.assertNotEqual(days[2011],27)
    def test_reference_sale_tax_rounding_difference_explained(self):
        r=section1291(100000,'2011-12-05','2025-06-01',2015,DUE)
        # Reference equals the sum of individually rounded annual taxes.
        self.assertEqual(sum(int(money(a['gross_tax'],0)) for a in r['annual_allocations']),28013)
        self.assertEqual(money(r['16c'],0),'28011')
    def test_live_same_year_sale_reference_matches(self):
        # Live POST to supplied calculator: purchase 2023-01-01 $10k,
        # sale 2023-06-01 $20k; first PFIC 2023.
        r=section1291(10000,'2023-01-01','2023-06-01',2023,{})
        self.assertEqual(r['16b'],10000);self.assertEqual(r['16c'],0);self.assertEqual(r['16f'],0)
    def test_interest_against_independent_daily_loop(self):
        # Independent day-by-day product, versus production quarter-segment powers.
        from datetime import timedelta
        from pfic.tax import interest_schedule
        import calendar
        with localcontext() as ctx:
            ctx.prec=80
            balance=Decimal(1);d=date(2023,4,18);end=date(2024,4,15)
            while d<end:
                key=f'{d.year}-{((d.month-1)//3)*3+1:02d}-01'
                rate=Decimal(interest_schedule()['annual_percent'][key])/100
                balance*=1+rate/(366 if calendar.isleap(d.year) else 365)
                d+=timedelta(days=1)
            computed,_=interest_factor(date(2023,4,18),end)
            self.assertLess(abs(computed-(balance-1)),Decimal('1e-70'))
    def test_irs_published_compounding_factors(self):
        # Rev. Rul. 2024-25, Appendix A, 0.5% / 365-day year table.
        from pfic.tax import compound_factor
        for days, expected in [(1,'0.000013699'),(63,'0.000863380'),(125,'0.001713784')]:
            result=compound_factor('0.005',days,365)-1
            self.assertEqual(result.quantize(Decimal('0.000000001')),Decimal(expected))

    def test_irs_leap_year_compounding_factors(self):
        from pfic.tax import compound_factor
        for days, expected in [(1,'0.000013661'),(63,'0.000861020'),(125,'0.001709097')]:
            result=compound_factor('0.005',days,366)-1
            self.assertEqual(result.quantize(Decimal('0.000000001')),Decimal(expected))

    def test_regulatory_mtm_separate_lots_example(self):
        # 26 CFR 1.1296-1(c)(7), Example 6. Two lots, $500 and $1,000;
        # each worth $800 at year end. Cannot net second lot's blocked loss.
        from pfic.tax import mtm_year_end
        a=mtm_year_end(500,800,0);b=mtm_year_end(1000,800,0)
        self.assertEqual(a['ordinary_income'],300);self.assertEqual(b['ordinary_income'],0)

if __name__=='__main__':unittest.main()
