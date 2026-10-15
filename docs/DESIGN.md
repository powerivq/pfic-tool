# Design and architecture

Status: describes the implemented 0.1.0 engine unless explicitly marked planned.
This is a direct-individual-ownership, calendar-year, single-fund calculator.
A run accepts one fund's complete transaction history and produces one report
containing all disjoint holding-period blocks. Different accounts remain separate
FIFO inventories. A block worksheet is not a complete signed Form 8621.

## Components

| Module | Responsibility |
|---|---|
| `model.py` | Immutable transactions, configuration, valuations, CSV validation |
| `numbers.py` | Exact numeric parsing, rational arithmetic, monetary formatting |
| `engine.py` | FIFO partition, dividend eligibility, historical state, report assembly |
| `tax.py` | Pure §1291 allocation, interest, distribution threshold and MTM primitives |
| `rates.py` | FX providers, selection policy, Treasury fetching and audited cache |
| `report.py` | HTML worksheets and structured exact JSON |
| `legacy.py` | Legacy input conversion with explicit missing-data issues |
| `__main__.py` | CLI adapter; JSON configuration becomes Python objects |

## Calculation flow

1. Validate configuration and transactions. Retain future trades for visible
   wash-sale checks, but do not include them in selected-year inventory.
2. Partition purchases using FIFO within each account. A partial sale creates a
   sold slice and a remainder; each final slice retains its original acquisition.
3. Allocate each distribution over the units eligible on its eligibility date.
   Earlier distributions follow the relevant slices when a lot is later split.
4. Replay each block from acquisition through the selected tax year. Historical
   distributions establish the lookback; prior MTM adjustments establish basis
   and unreversed inclusions. Only selected-year worksheets enter the summary.
5. Render the same result object as exact JSON and readable HTML. The summary
   is derived from the worksheets rather than a second tax calculation.

## Arithmetic and conservation

Input numeric values are strings, integers, Decimal values, or Fractions. Binary
floats, booleans as numbers, and nonfinite values are rejected. Costs, quantities,
allocations and most tax amounts use `Fraction`; repeating divisions remain exact.
Interest uses a local 80-digit Decimal context because repeated daily compounding
produces impractically large rational denominators. It is high precision, not
mathematically infinite precision. Ambient Decimal context must not change results.

Money is rounded half-up to whole dollars only for reporting. Units and rates are
not rounded to whole dollars. Summing individually displayed rounded lines may
not equal the rounded exact aggregate; the JSON preserves the reconciliation.

Required invariants include conservation of purchased units, purchase costs,
sale proceeds, dividends, withholding and allocated excess distributions. The
loss on one block does not offset §1291 gain on another block.

## FX policy

Purchase cost plus purchase fees is translated on the purchase confirmation date.
Sale proceeds less sale fees is translated separately on the sale confirmation
date. USD gain is the difference of those USD amounts. A constant local NAV can
therefore produce USD gain or loss.

`TableFX` permits deterministic injected reference data. `TreasuryFX` fetches
quarterly Treasury records and caches source responses with hashes. Both expose
`usd(amount, currency, date)` and an audit log. `LatestEffective` chooses the last
rate effective on or before the event, with no lookahead and a freshness limit.
A different selection policy/provider can be supplied without changing tax logic.
Currency/country ambiguity requires an explicit mapping. Quarterly rates are an
explicit approximation selected for this project, not a claim of daily spot FX.

## Section 1291

Distribution testing operates in the common distribution currency when possible;
mixed-currency history is normalized to USD. The engine computes the annual
125% lookback threshold, apportions annual excess among distributions, and then
translates each event's excess into USD on its payment date. Historical amounts
excluded as prior-PFIC excess allocations are excluded from the later lookback.
See VALIDATION.md and ROADMAP.md for the incomplete annualization review.

The allocation excludes the acquisition day and includes the event day. Prior
PFIC years receive the historical highest individual tax rate. Current/pre-PFIC
allocations enter current ordinary income. Current code classifies PFIC status by
`first_pfic_year`; residency-based date-level status is not yet implemented.

Distribution FTC is opt-in and requires creditability confirmation. Event
withholding is apportioned to blocks, excess/nonexcess amounts and years. Credits
for prior PFIC years are capped at that year's tax. Current-year candidates are
reported separately for the general FTC calculation. Section 1248 FTC is excluded.

Interest is calculated on net annual tax over explicit due-date intervals with
quarter-specific annual rates, daily compounding, and 365/366-day denominators.
The engine exposes every segment and does not guess missing due dates or rates.

## Mark to market

Each block carries adjusted USD basis and unreversed inclusions. Recognized gains
increase both. A year-end decline is deductible only up to unreversed inclusions;
unrecognized declines do not reduce basis. Sale losses split into ordinary loss
up to unreversed inclusions and a separately reported other-loss amount.

When an election follows prior §1291 years, the engine applies first-year
coordination: distributions/dispositions remain under §1291, and positive year-end
excess is a deemed disposition. This increases basis and unreversed inclusions;
interest is not added to either. Later MTM years use Part IV calculations.

## Conservative boundaries

Inputs must explicitly confirm complete history, ordinary dividend character,
marketability/election validity where applicable, and FTC creditability if claimed.
Missing valuations, ambiguous eligibility-day ordering, unsupported years,
oversales and visible potential wash-sale adjustments are blocked.

Not every unsupported fact is automatically detectable. QEF history, cessation,
indirect ownership, corporate actions and taxpayer-specific exceptions require
screening before supplying data under the supported contract. Do not encode an
unsupported event as an ordinary purchase or sale merely to bypass validation.

See RESIDENCY_DESIGN.md for the planned dual-basis extension. This design does not
claim that passing regression tests establishes complete legal correctness.
