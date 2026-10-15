# Validation and benchmark discrepancies

The program was executed, including automatic Treasury fetching, both CLI regimes,
and offline replay. Unit/integration tests exercise exact arithmetic, FIFO,
partial sales, dividend eligibility, reinvestment, currency normalization,
§1291 history, interest, MTM basis, first-year coordination, validation and output.

## Supplied calculator comparisons

Reference pages:
- https://www.andrewmitchel.com/resources/pfic/1291_fund_sale
- https://www.andrewmitchel.com/resources/pfic/1291_fund_distribution

Their default inputs were inspected on 2026-10-15: acquired 2011-12-05, event
2025-06-01, first PFIC year 2015. Sale cost/proceeds are $10,000/$110,000.
Distribution is $100,000, prior included distributions $60,000, withholding $15,000.
The distribution threshold ($25,000) and excess ($75,000) match exactly.

For comparison ONLY, the program receives an explicit April 15 date for each
unextended return deadline. This is not an inferred filing-deadline policy for
real taxpayers. Reference pages do not expose all interest assumptions.

| Example / line | Reference | Program | Status |
|---|---:|---:|---|
| Sale 16b | 25,858 | 25,858 | Rounded match |
| Sale 16c | 28,013 | 28,011 | Rounding difference |
| Sale 16e | 28,013 | 28,011 | Rounding difference |
| Sale 16f | 10,958 | 11,183 | Interest discrepancy unresolved |
| Distribution 16b | 19,393 | 19,393 | Rounded match |
| Distribution 16c | 21,008 | 21,008 | Rounded match |
| Distribution 16d | 8,339 | 8,341 | Allocation/rounding difference |
| Distribution 16e | 12,669 | 12,667 | Allocation/rounding difference |
| Distribution 16f | 4,995 | 5,098 | Interest discrepancy unresolved |

### Holding-period endpoints

The reference default table has 27 days in 2011 and 151 in 2025. The program uses
26 and 152: acquisition day excluded, event day included, consistent with IRS
Publication 550's holding-period rule and the Form 8621 event-end instruction.
The total days are 4,927 in either convention. Moving a day between current and
pre-PFIC years happens to preserve total line 16b in the default examples.
It does not generally preserve line 16b when the first year is a PFIC year.

A live POST check was also run with acquisition 2022-01-01, disposition 2023-06-01,
$10,000 cost, $20,000 proceeds, first PFIC 2022. The reference uses 365/151 days;
the program uses 364/152. Reference 16b/16c/16f are $2,926/$2,617/$197. With
explicit 2023-04-18 and 2024-04-15 return deadlines, the program produces
$2,946/$2,610/$203. These are not asserted to match.

A same-year live POST (acquired 2023-01-01; disposed 2023-06-01; same amounts)
matched $10,000 ordinary income, zero deferred tax, and zero interest.

### Rounding

For the default sale, summing each annual tax after whole-dollar rounding gives
$28,013, exactly the reference. Adding exact annual taxes and rounding once gives
$28,011. This program deliberately retains precision until output, as agreed.
The reference's displayed distribution credit also equals the sum of its rounded
annual credits. With the program's exact allocation and unrounded aggregation,
the displayed total is $8,341.

### Interest

Production interest uses published IRS noncorporate underpayment rates, daily
compounding and 365/366-day denominators. A separate day-by-day multiplication
implementation agrees with the quarter-segment implementation to better than
1e-70 on the tested cross-year interval. An IRS published compound-factor table
is also checked in the tests.

The reference calculators' interest results have NOT been reconciled in full.
Possible date/rate/rounding conventions are not silently guessed. The JSON audit
exposes each interval, days, rate, denominator, principal and resulting interest
so an independent reviewer can reproduce it. This is a concrete remaining
validation limitation, not a passing benchmark.

## Scope limits

The software emits reviewable calculation worksheets, not an official completed
Form 8621 PDF. Part I identity/annual summary, actual election paperwork, QEF,
pre-residency transition basis, corporate actions, automatic wash-sale adjustments,
and the taxpayer's full income tax/NIIT/FTC calculations are outside this version.
Supported form mappings are 2018–2025. No missing date, valuation or rate is
silently manufactured.

## Treasury regulation regression coverage (2026-10-15)

Added 17 tests in `tests/test_treasury_regulations.py`; all 104 suite tests pass.
The independent source is Treasury Decision 9123, final regulations:
https://www.irs.gov/pub/irs-regs/td9123.pdf .
`treasury_regulation_coverage.json` inventories all 13 examples within its
section 1.1296-1, including unsupported scenarios. Six examples have computational
coverage (some with stated scope limits), one has a rejection test, and six
remain unsupported. Additional tests cover related dividend coordination rules.

Tests preserve the regulation's dollar amounts. Where full engine tests require
2018–2025 form support, dates are explicitly adapted and are not represented as
checks of the original historical tax or interest totals. The original 1992–2005
transition allocation is also exercised directly. The regulation gives no
numerical interest answer for that example.

Example (c)(7)-6 specifically identifies the second lot. The corresponding
primitive test matches its $100 loss; an explicitly different FIFO integration
test correctly sells the first lot for $100 ordinary gain. This does not change
the user's FIFO policy. Capital-loss amounts are tested, but classification and
general capital-loss reporting remain outside this calculator.

Unsupported examples are not disguised as passing numerical tests. PFIC
cessation, partnership allocation, QEF/election interruption, and RIC taxpayer
rules need additional inputs and implementation. Pre-residency holdings are
explicitly rejected. No production calculation change was necessary for the
supported examples. Existing benchmark and deadline-review limitations remain.

Distribution FTC scope update: five additional regression tests verify eligible
block/year allocation, claim-disabled behavior, creditability confirmation,
nonexcess credits, and rejection of withholding on sale rows. All 109 tests pass.
Section 1248 FTC is intentionally excluded. No tax arithmetic changed.

## Publication review

The synthetic example configurations now explicitly use April 15 for their
2021–2023 tax-year interest endpoints; this corrects the earlier examples'
unreviewed April 18 filing dates. These are illustrative inputs, not an automatic
taxpayer-specific deadline resolver. General filing permission under section 7503
and interest due dates must not be assumed identical. Disaster relief, COVID
postponements, and taxpayer-specific deadlines still require separate review.
The engine continues to require explicit dates.

A calendar-year interest-window hypothesis explains much of the external
benchmark gap, but has not established the external calculators' implementation.
It is not a replacement for the statutory due-date rule. No benchmark discrepancy
is concealed by updating expected values to production output.
