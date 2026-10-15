# Source register

Reviewed 2026-10-15. Policy and reference data are visible in the program.

- IRS Form 8621 instructions (12/2025), Part IV and Part V:
  https://www.irs.gov/instructions/i8621
  Block calculations, distribution currency, 125% threshold, first-holding-year
  exception, multiple distributions, rates, credits, interest and MTM line mapping.
- Form 8621 (12/2018), historical Part IV/V line layout:
  https://www.irs.gov/pub/irs-prior/f8621--2018.pdf
  Older line 15e versus the 2025 line 15e(1)/15e(2) layout.
- 26 CFR 1.1296-1:
  https://www.ecfr.gov/current/title-26/section-1.1296-1
  Separate-lot MTM calculations, deductions limited by unreversed inclusions,
  basis adjustments, and first-election-year coordination with §1291.
- IRS Publication 550, Holding Period:
  https://www.irs.gov/publications/p550
  Acquisition-day exclusion and sale-day inclusion; trade versus settlement date.
- IRS quarterly interest-rate tables:
  https://www.irs.gov/payments/quarterly-interest-rates
- Revenue Ruling 2024-25 and historical interest tables:
  https://www.irs.gov/irb/2024-49_IRB
  Bundled quarterly underpayment rates are extracted from these public IRS tables.
  Each quarter is separately present; there is no carry-forward into unknown years.
- Treasury Reporting Rates of Exchange:
  https://fiscaldata.treasury.gov/datasets/treasury-reporting-rates-exchange/
- Treasury API:
  https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange
- User-supplied comparison calculators:
  https://www.andrewmitchel.com/resources/pfic/1291_fund_sale
  https://www.andrewmitchel.com/resources/pfic/1291_fund_distribution
  See VALIDATION.md for matches and discrepancies; these are independent checks,
  not substituted authority when their displayed conventions differ.

User-selected policies: FIFO within account; confirmation-date input;
latest Treasury effective rate not later than transaction; explicit dividend
eligibility; selectable tax year; whole-dollar monetary reporting only.

Additional design-review sources:
- Treasury Decision 9123, final §1.1296-1 examples:
  https://www.irs.gov/pub/irs-regs/td9123.pdf
- IRC §1291, including dividend annualization under (b)(3)(C):
  https://www.law.cornell.edu/uscode/text/26/1291
- IRS interest guidance, IRM 20.2.5 (statutory dates versus §7503 permission):
  https://www.irs.gov/irm/part20/irm_20-002-005
- Residency design sources and their authority/status are separately listed in
  RESIDENCY_DESIGN.md. Proposed and nonprecedential material is labeled as such.
