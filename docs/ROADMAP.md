# Roadmap and open decisions

This is an implementation backlog, not a claim of supported features.

## Before treating results as filing-validated

1. Reconcile the remaining external benchmark interest differences and document
   independent authoritative expected results. Similarity is not a passing oracle.
2. Complete interest due-date review, including weekend/holiday filing permission,
   COVID postponements and disaster relief. Current dates are explicit inputs.
3. Review dividend annualization under section 1291(b)(3)(C). The existing engine
   uses prior included totals divided by the preceding-year count and does not
   implement a general partial-year annualization adjustment. Identify applicable
   cases and add independent tests before claiming full dividend coverage.
4. Complete historical-form line mapping and treatment review for each supported
   year. Current outputs are supporting worksheets, not complete IRS forms.

## Required next feature

Pre-U.S.-residency ownership under §1291 and MTM, including the dual-basis
regulatory example. See RESIDENCY_DESIGN.md. Proposed PFIC-start-date input is not
implemented and cannot replace all residency/election/valuation facts.

## Deliberate scope decisions

- One fund per CSV; multiple accounts remain separate FIFO inventories.
- Distribution FTC only. Section 1248 FTC is excluded by project requirements.
- Treasury quarterly FX is the selected replaceable policy.
- Whole-dollar reporting with full precision retained internally.
- Direct individual calendar-year taxpayer; no RIC taxpayer or partnership engine.

## Other unsupported areas

QEF, PFIC cessation, election interruptions, mergers, share splits, gifts,
inheritance, return-of-capital events, automatic wash-sale basis adjustments,
full capital-loss/FTC/NIIT return calculations, and automatic election filing.
Many such facts cannot be detected from a plain transaction CSV; document the
input contract rather than claiming every unsupported scenario is auto-rejected.

## Release discipline

Every tax change needs a source, explicit assumptions, independent expected
values, targeted tests and readable reconciliation. Keep unresolved findings
visible. Do not change expected tests merely to match production calculations.
