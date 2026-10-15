# Single-fund PFIC calculator (Python)

One fund transaction CSV → FIFO blocks → §1291 / §1296 calculations →
whole-dollar Form 8621 line worksheets for every block.

Python 3.10+, standard library only. No installation or supplied FX-rate file
is required. Run commands from this directory.

## Project status and documentation

Research implementation, version 0.2.0. **Pre-U.S.-residency holdings are supported
under §1291, with bounded MTM support described below.** Benchmark interest discrepancies
remain unresolved. Supported reporting years are 2018–2025.

- [Design and architecture](docs/DESIGN.md)
- [Input contract and examples](docs/INPUTS.md)
- [Validation results and known discrepancies](docs/VALIDATION.md)
- [Residency support and limitations](docs/RESIDENCY_DESIGN.md)
- [Roadmap and open decisions](docs/ROADMAP.md)
- [Source register](docs/SOURCES.md)
- [Treasury regulation coverage](docs/treasury_regulation_coverage.json)
- [Contributing](CONTRIBUTING.md)

## Run

```bash
python -m pfic calculate examples/fund.csv \
  --config examples/config.json --year 2023 --out output
```

Produces:

- `output/form8621.html`: readable, printable block worksheets, annual §1291
  allocations, interest segments, basis history and FX audit.
- `output/form8621.json`: the same results, with exact rational amounts and
  80-digit decimal interest. No binary floating-point values.

These are calculation worksheets with Form 8621 line references, **not a filled
official IRS PDF or a complete tax return**. Taxpayer/PFIC identity, Part I annual
information and election statements are not fabricated. The included examples
are synthetic, not calculated results for any individual taxpayer.

**Validation status:** 139 automated tests pass; see `docs/test_results.txt`. Checks against the two supplied Andrew Mitchel
calculators exposed holding-day, rounding and interest differences. They are
recorded in `docs/VALIDATION.md` and `docs/benchmark_comparison.json`, not called
successful matches. Treat this implementation as reviewable calculation software,
not independently certified filing software.

## Python API

```python
from datetime import date
from pfic import Config, Valuation, calculate_csv, write_report

config = Config(
    tax_year=2023,
    fund_name="My fund",
    first_pfic_year=2021,
    us_person_since="2010-01-01",  # supply the actual date
    complete_history=True,        # explicit factual confirmation
    ordinary_dividends_confirmed=True,
    regime="1291",
    due_dates={                  # explicit illustrative interest dates; see docs/VALIDATION.md
        2021: date(2022, 4, 15),
        2022: date(2023, 4, 15),
        2023: date(2024, 4, 15),
    },
)
report = calculate_csv("my_fund.csv", config)  # Treasury FX fetched automatically
write_report(report, "output")
```

Use `calculate(list_of_Transaction_objects, config, fx=None)` when input comes
from another format. CSV parsing, tax calculations, FX selection and rendering
are separate modules. Configuration is a Python dataclass; JSON is merely the
CLI adapter. Nothing requires elections or valuations to be CSVs.

For MTM set `regime="mtm"`, `election_year=...`, `mtm_eligible=True`,
`election_valid=True`, and provide a dictionary:

```python
valuations = {
    2022: Valuation("15.1250", "CNY", "year-end statement"),
    2023: Valuation("16.2500", "CNY", "year-end statement"),
}
```

Values are **per-share NAVs at December 31**, not total position values. Supply
every year-end valuation needed since the effective election, not only the target
year. The engine reconstructs adjusted basis and unreversed inclusions per block.
Selecting a past year does not create or backdate an election. Marketability and
a valid election must be established independently. First-year coordination with
§1291 is implemented for previously held PFIC lots, including no deduction for a
transition-year unrealized decline and carryforward of taxed transition gains.

## One transaction CSV per fund

See `examples/fund.csv`. Include all historical rows, not only the reporting year.
An optional `account` column keeps FIFO within each account when one fund is held
in several accounts. The caller must ensure this CSV represents one fund/share
class; there is no multi-PFIC orchestration.

| Column | Meaning |
|---|---|
| `id` | Unique, stable transaction ID |
| `type` | `BUY`, `SELL`, `DIVIDEND`, `REINVEST` |
| `date` | Confirmation date for a trade; payment/distribution date for a dividend |
| `sequence` | Nonnegative integer ordering events on the same date and account |
| `currency` | Three-letter ISO currency code |
| `amount` | Trade gross amount **excluding fees**, or gross dividend before withholding |
| `units` | Positive on trades; explicit `0` on dividends |
| `fee` | Nonnegative fee in the row currency; explicit `0` when none |
| `eligibility_date` | Required for every dividend; date shares earned entitlement |
| `eligibility_sequence` | Inclusive event cutoff on eligibility date; required when trades occur that day |
| `linked_dividend_id` | Required only for `REINVEST`; references the preceding dividend |
| `withholding` | Dividend withholding, or explicit `0`; unknown must not be replaced by zero |
| `account` | Optional account identifier; omitted/blank means one `default` account |
| `source` | Optional statement/screenshot/reference description |

All numeric input values must be decimal strings, integers, `Decimal` or
`Fraction`. Python floats, NaN and infinity are rejected. JSON decimal numbers are
parsed as strings, but decimal strings are recommended for portability.

**Purchase cost = gross amount + acquisition fee. Net sale proceeds = gross
amount − selling fee.** Each is translated separately at its own transaction-date
FX selection. Never convert a local-currency gain as a shortcut.

A reinvestment is two rows: a `DIVIDEND`, then a linked `REINVEST` acquisition.
Partial reinvestment is supported. Daily money-market income works the same way:
its income distribution creates taxable dividend history, and its reinvestment
creates new shares with new basis. Constant local NAV does not imply zero USD gain.
Deposits funded by dividends from a different fund are `BUY` rows here, not this
fund's dividends. Withdrawals are `SELL` rows.

Eligibility is determined from shares held after the specified inclusive cutoff.
For example, `eligibility_sequence=0` means before a same-day purchase at sequence
1. A later payment can still belong to shares already sold after eligibility.
Daily distributions need actual eligibility dates/order; the engine never guesses
that a newly reinvested share earned that same dividend.

All distributions in a rolling calculation that are denominated in one currency
are tested for excess in that currency, then event portions are translated on
payment dates. Mixed-currency distribution histories are normalized to USD.
Prior-year excess portions not included in gross income are excluded from future
averages. Annual excess is allocated proportionally across the year's payments.

## Precision and rounding

- Share, basis, proceeds and dividend allocations use exact rational arithmetic.
- Compound interest uses a local 80-digit decimal context and actual 365/366-day
  calendar years. Interest rates are quarterly IRS underpayment rates, not AFRs.
- Whole dollars, half up, are used only in the presentation of monetary amounts.
- Share quantities, rates and exact audit values retain their precision.
- Independently rounded displayed rows can differ from a rounded total. Exact
  totals reconcile; no penny/dollar adjustments are hidden in a selected block.
- `16b` is current/pre-PFIC ordinary income, **not the tax on that income**. The
  calculator cannot determine regular income tax without the rest of the return.

## Exchange rates

The default adapter fetches public Treasury Reporting Rates of Exchange, caches
the original responses with hashes and fetch timestamps, and records every rate
used. It selects the latest **effective date on or before** the event, as requested.
This is the selected quarterly approximation, not an assertion that it equals a
daily spot rate. Missing rates, conflicting observations and observations more
than 120 days old are rejected rather than silently reused.

The cache defaults to `~/.cache/pfic-calculator/treasury`. Use `--cache PATH` to
choose a location, and `--offline` to require cached data. Cached responses are
not silently refreshed; use a new cache directory to deliberately fetch revised
data and compare results.

`TreasuryFX(currency_countries={"XXX": "Exact Treasury country label"})` adds a
Treasury currency mapping. CNY and common currencies are included. Ambiguous or
unknown mappings block calculation. The numeric engine is currency-independent.
Alternative rate selection is injected through an object with `name` and
`select(records, currency, date)` methods; a wholly different data source can
implement `usd(amount, currency, date)` plus an `audit` list.

## Dates, history and deliberately blocked cases

The input policy uses confirmation dates as requested. They must represent the
tax-effective acquisition/disposition date; a settlement receipt date must not
silently replace it. Holding periods exclude acquisition day and include the
sale/distribution day. Same-day §1291 excess allocation is blocked for review.

Provide actual **unextended return due dates** in `due_dates` whenever a §1291
interest computation needs them. They are not election/valuation CSVs. The engine
does not guess taxpayer-specific holiday, location or disaster-postponement rules.
Its interest intervals are `[prior return due date, event-year return due date)`.
The comparison fixture's April-15 dates are explicitly test assumptions.

Supported tax-year form mappings: **2018–2025**, including 2023; historical tax
rates and interest data cover 1987 onward. Unknown later form revisions and
interest quarters are blocked, not extrapolated. See `docs/SOURCES.md`.

Scope is direct individual calendar-year ownership, ordinary acquisitions,
ordinary dividends, FIFO, continuous PFIC status from the specified first PFIC
year, and either §1291 or one continuing valid MTM election. Explicit configuration
confirms complete history. No automatic PFIC legal classification is performed.

Not implemented: QEF, gifts/inheritances/transfers, mergers/splits, return of
capital, PFIC cessation, election revocation, repeated residency changes,
opening-state imports, indirect/corporate ownership, or completed Forms 1116/8960.
These require additional reviewed logic. Potential wash-sale replacements visible
in the supplied history block calculations involving losses; outside-account
activity and future replacement transactions cannot be inferred. Other losses
are exported separately and are not netted against §1291 gains.

Foreign withholding is retained. To compute allowable prior-PFIC-year credits,
set both `claim_foreign_tax_credit=True` and `foreign_taxes_creditable=True`.
Otherwise no credit is presumed. Current-year credit candidates are identified
but are not a completed foreign tax credit calculation.

## Legacy-format CSV

```bash
python -m pfic import-legacy old_one_fund.csv --out my_fund.csv
```

Also writes `my_fund.issues.json`. Missing confirmation dates, dividend payment or
eligibility dates, withholding details, and inconsistent amounts are flagged.
The importer preserves source references and does not replace missing facts with
NAV/request/cash-receipt dates. Exit code 2 means unresolved fields remain.

## Tests and examples

```bash
python -m unittest discover -s tests -v
PYTHONPATH=. python tests/benchmark_comparison.py
python -m pfic calculate examples/fund.csv --config examples/config.json \
  --out output_1291 --cache examples/treasury_cache --offline
python -m pfic calculate examples/fund.csv --config examples/mtm_config.json \
  --out output_mtm --cache examples/treasury_cache --offline
```

The bundled Treasury cache contains the public data used to generate the examples.
Reproducible HTML and JSON examples are included. Only synthetic transactions and public reference data are included. No personal
transaction records or credentials are included.

Treasury regulation example coverage and explicit exclusions are inventoried in
`docs/treasury_regulation_coverage.json`; run `tests/test_treasury_regulations.py`
through unittest discovery with the rest of the suite.

## Foreign tax credit scope

Only distribution FTC is supported. Enter gross dividends in `amount` and actual
foreign withholding in `withholding` on each DIVIDEND row, in that row's currency.
Enable `claim_foreign_tax_credit` and confirm `foreign_taxes_creditable` to apply
credits. Withholding is allocated to eligible blocks and to excess/nonexcess
amounts; prior-PFIC credits reduce the corresponding annual tax subject to its
cap. Current-year credit candidates remain subject to the general FTC calculation
outside this program. Withholding is retained when no credit is claimed.

Section 1248 FTC is excluded by user instruction. Sale rows cannot contain
withholding, and the program does not apply distribution credits to sale gains.
The supported FTC scope is independent of PFIC start-date and residency inputs.


## Shares purchased before U.S. residency

Keep the original purchases, sales, dividends and reinvestments in the fund CSV.
Set `us_person_since` to the actual first U.S.-person date; do not move purchase
dates to residency or replace their historical USD cost. For §1291, allocations
retain the full original holding period and split prior years at that date.
Pre-residency days are pre-PFIC allocations, not prior-PFIC deferred-tax days.
Pre-residency payments remain distribution history but produce no U.S. income
or FTC in the selected-year worksheets under this input contract.

Optional `pfic_start_date` can specify a later taxpayer-specific PFIC boundary;
it cannot precede residency or January 1 of `first_pfic_year`.

For a valid first-residency-year MTM election with January 1 residency, supply
`residency_opening_valuation=Valuation("100", "USD", "opening NAV source")`.
This is a per-share January 1 value, separate from December 31 valuations.
General cost basis is preserved; the special MTM basis is tracked separately.
A later valid election uses first-year §1291 coordination, without silently
applying an immigration uplift. Midyear first-residency-year MTM on existing
shares and sales below an uplifted MTM basis remain explicitly blocked.
See [residency details](docs/RESIDENCY_DESIGN.md) for assumptions and sources.

Run the synthetic §1291 residency example:

```bash
python -m pfic calculate examples/residency_fund.csv --config examples/residency_config.json --out output-residency --offline
```
