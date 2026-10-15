# Changelog

## 0.2.0

- Accept pre-residency transaction history with date-level §1291 allocations.
- Preserve original USD cost, historical dividends, FIFO sales and reinvestments.
- Add optional PFIC boundary and January 1 residency MTM dual-basis valuation.
- Export separate MTM ordinary/capital gains and exact basis reconciliation.
- Add 30 residency regressions; 139 tests pass. JSON schema is now 1.1.
- Keep midyear first-residency-year MTM and dual-basis loss sales explicitly blocked.


## 0.1.0 — initial repository publication

- Python single-fund FIFO calculator with §1291 and MTM supporting worksheets.
- Decimal-input rational arithmetic and 80-digit compounded interest.
- Dividend eligibility, reinvestment and distribution-only FTC handling.
- Treasury fetching, source-response cache and replaceable rate-selection policy.
- 109 passing tests, with a Treasury-regulation example coverage inventory.
- README, architecture, input contract, validation, residency proposal and roadmap.
- Synthetic configurations use explicit illustrative April 15 interest endpoints;
  bundled HTML/JSON outputs regenerated from those inputs.
- Personal import audits and transaction histories excluded from publication.

Known limitations remain: residency-transition implementation, partial-year
annualization review, complete interest benchmark reconciliation, and additional
scope exclusions documented in the README and roadmap. Not filing-certified.
