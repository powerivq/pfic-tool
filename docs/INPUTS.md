# Input contract

## One CSV per fund

The CSV contains all transactions for one fund, including history before the
selected reporting year. Use `account` to keep separate account inventories.
Do not mix distinct funds. CSV columns and Python types are defined by
`pfic.model.COLUMNS` and `Transaction`; unrecognized CSV columns are rejected.

| Field | Meaning |
|---|---|
| `id` | Unique stable transaction ID |
| `type` | `BUY`, `SELL`, `DIVIDEND`, or `REINVEST` |
| `date` | ISO confirmation date for trades; payment date for dividends |
| `sequence` | Nonnegative integer for ordering events on the same date |
| `currency` | Uppercase three-letter currency code |
| `amount` | Unsigned gross trade consideration or gross dividend |
| `units` | Positive for trades; zero for dividends |
| `fee` | Trade fee, added to purchase basis/subtracted from proceeds; zero for dividends |
| `eligibility_date` | Required for dividends; no later than payment |
| `eligibility_sequence` | Inclusive cutoff where trades occur on the eligibility date |
| `linked_dividend_id` | Required only for REINVEST; identifies the funding dividend |
| `withholding` | Foreign tax withheld on the dividend; zero on trades |
| `account` | FIFO account identifier; default `default` |
| `source` | Optional local audit reference; avoid secrets |

Amounts use decimal text, never thousands separators. Supply zero rather than a
blank numeric value. `amount` is gross: a dividend of 100 with withholding of 10
is entered as 100 and 10, not 90 and 10. A reinvestment is a DIVIDEND plus a linked
REINVEST purchase; it must not exceed the net available dividend. Two records
represent the income and acquisition, not two income events.

The confirmation-date policy assumes the supplied date is the tax-effective
acquisition/disposition date. The program does not infer dates from request,
settlement, NAV, or cash-posting dates. On a shared eligibility/trade date, supply
an explicit ordering cutoff; the program does not guess entitlement.

## Configuration

Use a `Config` object in Python or a JSON file for the CLI. See
`examples/config.json` and `examples/mtm_config.json` for complete executable
fixtures. JSON decimal values should be strings. The CLI also parses decimal
JSON numbers as strings to avoid binary float conversion.

- Required: `tax_year`, `fund_name`, `first_pfic_year`, `us_person_since`,
  `complete_history`, and `ordinary_dividends_confirmed`.
- `regime`: `1291` or `mtm`.
- MTM: `election_year`, `mtm_eligible`, `election_valid`, and all relevant
  `valuations` keyed by year. Each valuation contains `unit_value`, `currency`,
  and optionally `source`.
- Interest: `due_dates` keyed by tax year, containing reviewed unextended dates.
  See VALIDATION.md for the distinction between filing permission and interest
  endpoints. No built-in taxpayer-specific deadline policy exists.
- FTC: `claim_foreign_tax_credit` and `foreign_taxes_creditable`; both must be
  true to claim distribution credits. No section 1248 FTC input is supported.
- Optional `ending_units`: exact independent reconciliation check.
- CLI-only `currency_countries`: overrides ambiguous Treasury country mappings.

`us_person_since` currently enforces a rejection boundary; it does not implement
residency transition calculations. `first_pfic_year` is a year, not the proposed
future `pfic_start_date` input. Do not use either to bypass pre-residency rejection.

## Money-market funds

A fixed local NAV does not imply zero USD gain. Genuine fund earnings are
DIVIDEND events, with REINVEST events if they buy new shares. Cash deposited from
another investment is a BUY into this fund, not this fund's dividend. A withdrawal
that redeems units is a SELL. Confirm the underlying facts rather than relying
on a platform's transaction label alone.

## Output and replay

The HTML/JSON report includes every block, basis and distribution history,
selected-year worksheets, FX audit, interest segments and a common summary.
Each run of `calculate_csv` includes the source CSV SHA-256. Retain the input,
configuration, report and FX cache together privately for reproducibility.

Use `--cache examples/treasury_cache --offline` for the synthetic examples.
Production input and outputs belong outside version control. The legacy importer
writes an issues file and returns a nonzero status when required facts are absent.
