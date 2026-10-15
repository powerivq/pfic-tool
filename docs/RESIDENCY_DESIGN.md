# Pre-U.S.-residency holdings: proposed design

**Status: required feature, not implemented.** The current engine rejects these
holdings. This document records implementation requirements and unresolved tax
questions; it is not an instruction to remove that guard.

## Separate concepts

Keep actual acquisition date and general USD cost basis. Track U.S.-person periods
separately from fund PFIC status, PFIC holding-period resets and MTM election dates.
A simplified user-facing PFIC start date can describe taxpayer-specific status,
but cannot also identify whether the taxpayer immigrated or the fund changed status.

Proposed configuration: confirmed residency effective date, taxpayer-specific PFIC
start date/reason, relevant opening-year valuation with date/currency/source, and
valid election year. A single uninterrupted residency period is the initial target;
repeated changes, treaty overrides and elections require explicit treatment.
No factual residency date or election validity will be inferred from transactions.

## Section 1291 requirements

Retain the actual holding period and original purchase-date USD basis. Split
allocation periods at residency boundaries, including within a calendar year.
Distinguish pre-PFIC ordinary-income allocation from prior-PFIC deferred-tax and
interest allocation. Preserve all historical purchases, sales and distributions;
pre-residency reinvestments remain real lots, not zero-basis opening balances.

Primary sources for review:
- https://www.law.cornell.edu/uscode/text/26/1291
- https://www.law.cornell.edu/cfr/text/26/1.1291-9 (j)(1)
- https://www.irs.gov/pub/irs-wd/0733024.pdf (nonprecedential technical advice)
- https://archives.federalregister.gov/issue_slice/1992/4/1/11023-11056.pdf
  (1992 proposed rules, not represented as final regulations)

## MTM dual basis

Treas. Reg. 1.1296-1(d)(5) states a special basis solely for section 1296:
greater of FMV or adjusted basis on the first day of the taxable year of becoming
a U.S. person, for stock owned on that first day. Do not silently replace that
date with a midyear arrival date or extend the rule to a later election.

Each block needs general adjusted basis, section 1296 adjusted basis, unreversed
inclusions, and the relevant holding-period dates. Partial FIFO sales must split
all these balances exactly. Year-end adjustments affect both bases according to
the applicable rules; a sale must reconcile total gain/loss and character.

Required source example, 1.1296-1(d)(5)(ii): original cost 50; January 1 residency
value 100; year-end value 110; recognize 10 MTM income; carry general basis 60
and MTM basis 110; subsequent sale 120 produces total gain 60, ordinary 10 and
long-term capital gain 50. No general immigration step-up erases the original 50.

Source: https://www.irs.gov/pub/irs-regs/td9123.pdf

## Questions to resolve before enabling

1. Midyear residency, including purchases after January 1 but before residency.
2. Election in a later residency year and interaction with first-year §1291 rules.
3. Pre-residency dividends in the lookback, partial-year annualization and
   eligibility/payment dates that straddle the residency boundary.
4. Dual-basis sales when proceeds fall between or below the two bases.
5. Reporting ordinary and capital components without implying a completed
   Schedule D or general FTC/NIIT calculation.

## Acceptance tests

Reproduce the complete regulatory example above. Add FMV below cost, fractional
partial sales, multiple original lots, pre-residency reinvestments, separate FX
dates, midyear boundaries, delayed elections, and same-day residency/trade facts.
Check basis/units/withholding conservation and component-to-total reconciliation.
Replace the current rejection test only when the supported branch is implemented;
keep explicit guards for unresolved scenarios. Document all date adaptations
when testing historical regulatory examples with modern form mappings.
