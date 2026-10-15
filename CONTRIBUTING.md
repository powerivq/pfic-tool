# Contributing

Python 3.10 or later; the runtime and tests use the standard library. Run from
repository root:

```bash
python -m unittest discover -s tests -v
PYTHONPATH=. python tests/benchmark_comparison.py
python -m pfic calculate examples/fund.csv --config examples/config.json \
  --out /tmp/pfic-1291 --cache examples/treasury_cache --offline
python -m pfic calculate examples/fund.csv --config examples/mtm_config.json \
  --out /tmp/pfic-mtm --cache examples/treasury_cache --offline
```

For tax logic changes, cite primary authority and identify its status (statute,
final regulation, proposed regulation, instruction, or nonprecedential advice).
Keep test expectations independently derived. If using a historical example,
label adapted dates and distinguish primitive tests from end-to-end coverage.

Preserve exact arithmetic. Do not introduce binary floats or intermediate
monetary rounding. Add conservation checks for allocation or lot changes and
update coverage/scope documentation when capabilities change.

Use synthetic fixtures only. Do not commit personal transaction histories,
account statements, taxpayer names/identifiers, generated personal returns,
credentials, or private source audits. Public IRS/Treasury reference data is
permitted with provenance. Do not submit private inputs to benchmark websites.

The repository currently has no selected open-source license; publication alone
does not grant a license. The repository owner should choose licensing terms.
