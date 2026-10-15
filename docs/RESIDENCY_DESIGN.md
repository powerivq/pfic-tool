# Pre-U.S.-residency holdings

## Implemented scope

Version 0.2.0 accepts original pre-residency transactions for §1291. It supports
one uninterrupted U.S.-person period for a direct individual calendar-year owner.
The input contract excludes pre-residency U.S.-source/ECI taxation, treaty
overrides, repeated residency changes and holding-period-reset elections.
Residency dates, PFIC status and election validity are supplied facts, not inferred.

`us_person_since` sets the residency boundary. Optional `pfic_start_date` can
specify a later taxpayer-specific PFIC start, but cannot precede residency or
January 1 of `first_pfic_year`. It does not reset general basis or acquisition.

## Section 1291

Original purchase-date USD cost and the full holding period are preserved.
Allocation excludes acquisition day and includes the event day. Prior years
split at the effective PFIC boundary, including within a calendar year.
Pre-PFIC and current-year amounts enter current ordinary income; only prior-PFIC
allocations enter the deferred-tax/interest computation. Pre-residency appreciation
is not erased by an invented general immigration basis step-up.

Pre-residency sales deplete FIFO inventory. Pre-residency reinvestments create
real acquisition lots. Dividends retain eligibility-based block allocation and
payment dates; pre-residency payments have no U.S. income or FTC worksheet under
this input contract. They remain in historical distribution totals. Annual totals
include distributions before the boundary when computing and apportioning excess;
only post-boundary events receive section 1291 treatment. Resident pre-PFIC
payments are ordinary dividends. Historical exclusion removes only the excess
allocated to prior-PFIC days, not all prior calendar years.

The distribution convention follows actual received amounts. The optional use of
known actual pre-acquisition per-share distributions in proposed 1.1291-2(d)(1)
is not implemented. No arbitrary daily annualization multiplier is applied.
The 1992 distribution rules are proposed, not final; this authority distinction
and the wider dividend-review limitation remain material to independent review.

## MTM: supported January 1 transition

For existing shares and a valid election in the first residency year, residency
must begin January 1. Supply `residency_opening_valuation` as per-share FMV in its
currency on that date. It uses the configured FX policy independently of the
purchase date. The general basis stays at original adjusted cost; special MTM
basis is the greater of that basis or opening FMV. The uplift creates no
unreversed inclusion. Subsequent recognized adjustments update both bases.

The final regulation's example is an independent numerical oracle: cost 50,
opening FMV 100, year-end FMV 110, inclusion 10, general basis 60, MTM basis 110.
Sale at 120 produces total gain 60, ordinary gain 10 and capital gain 50.
Tests adapt residency/sale years to 2023/2024 without changing these dollar facts.
Partial FIFO sales divide both bases and inclusions exactly. Capital gains appear
separately in the report, for general capital-gain reporting outside Form 8621.

A valid election in a later residency year uses section 1296(i) first-year
coordination and original basis, without applying an immigration uplift. Missing
required opening valuations are rejected. Election validity remains a factual
confirmation; this tool does not establish eligibility or file the election.

## Explicit remaining limits

- Midyear first-residency-year MTM for pre-existing shares is rejected: the
  regulation refers to the first day of the taxable year, not simply arrival FMV.
- Sales below a special MTM basis that exceeds general basis are rejected pending
  reviewed loss-character treatment. Equal-basis ordinary-loss rules remain supported.
- Multiple residency periods, treaty exceptions, pre-residency ECI, QEF, PFIC
  cessation, deemed-sale holding-period resets and other corporate actions are excluded.
- Taxpayer-wide Schedule D, NIIT and current-year FTC limitations are outside the tool.
- Existing benchmark interest discrepancies and explicit due-date requirements remain.

## Sources and tests

- 26 USC 1291: https://www.law.cornell.edu/uscode/text/26/1291
- Final 1.1291-9(j)(1): https://www.law.cornell.edu/cfr/text/26/1.1291-9
- Final 1.1296-1(d)(5), (i): https://www.law.cornell.edu/cfr/text/26/1.1296-1
- Treasury Decision 9123: https://www.irs.gov/pub/irs-regs/td9123.pdf
- Nonprecedential technical advice: https://www.irs.gov/pub/irs-wd/0733024.pdf
- Proposed 1992 1.1291-1(b)(1), 1.1291-2(c)(2), (d)(1), (d)(6):
  https://archives.federalregister.gov/issue_slice/1992/4/1/11023-11056.pdf

`tests/test_residency.py` contains independently specified expected amounts,
calendar-day iteration, conservation checks, the complete MTM regulatory example,
CLI/HTML/JSON integration, and targeted rejection tests. Passing these tests does
not turn proposed guidance into final regulations or certify filing readiness.
