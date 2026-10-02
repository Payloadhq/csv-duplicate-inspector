# csv-duplicate-inspector

**Small software that earns its keep.** — a Payload free utility

A zero-dependency Python CLI that inspects a CSV for duplicate risks before
you migrate, import, or deduplicate it: exact-duplicate rows, duplicate
values in a key column, and near-duplicate values via normalized comparison.

## Install

Nothing. Python 3.10+ and this repo. Standard library only.

```bash
python3 inspect.py contacts.csv
```

## Usage

```bash
# exact-duplicate row scan (streams the file; no full load)
python3 inspect.py contacts.csv

# also check a key column for duplicate values
python3 inspect.py contacts.csv --key email

# plus near-duplicate detection on the key column
# (case / whitespace / punctuation insensitive)
python3 inspect.py contacts.csv --key company --near-dup

# machine-readable output
python3 inspect.py contacts.csv --key email --json
```

Exit codes: `0` = no duplicates found, `1` = duplicates found (or unusable
input), `2` = no duplicates, data-quality warnings only.

Real output:

```
$ python3 inspect.py prospects.csv --key company --near-dup
CSV duplicate inspection: prospects.csv
Rows: 5 (header excluded)
Exact-duplicate rows: none
Key column "company": 0 duplicate value(s) affecting 0 rows
Near-duplicate clusters in "company" (normalized): 2
  - 'acme inc' <- 'Acme Inc' x1, 'ACME INC.' x1, 'acme  inc.' x1
  - 'globex' <- 'Globex' x1, 'globex!' x1
```

## What it reports

- **Exact-duplicate rows** — byte-identical rows (as parsed), with group
  counts, share of total rows, and first-seen line numbers. The file is
  streamed; only one hash entry per unique row is kept in memory.
- **Key-column duplicates** (`--key`) — values occurring more than once,
  with counts and up to 10 line numbers each.
- **Near-duplicate clusters** (`--key` + `--near-dup`) — values that match
  after lowercasing and stripping whitespace/punctuation differences, e.g.
  `Acme Inc`, `ACME INC.`, `acme  inc.`
- **Warnings** — blank lines skipped, ragged rows (field count differs from
  the header), with line numbers.

Notes on scope, stated plainly:

- The first row is treated as the header. Files without a header row are not
  specially handled.
- Near-duplicate detection is normalization-based, not fuzzy matching: it
  catches `Acme Inc` vs `ACME INC.` but not `Acme` vs `Acme Corporation`.
- Memory use for the exact-duplicate pass is proportional to the number of
  *unique* rows, not file size. The near-duplicate pass additionally holds
  the key column's values.
- This tool reports duplicates; it does not merge, normalize, or rewrite
  your data.

## Tests

```bash
python3 tests/run_tests.py
```

6 fixtures (clean, exact dupes, key dupes, near dupes, ragged rows, missing
key column) plus a 60,000-row streaming smoke test with known duplicate
counts. All must pass.

## What this doesn't do

This tells you *where* the duplicates are. It doesn't decide which record
survives a merge, normalize fields across systems, validate against
HubSpot/Salesforce formats, or produce a migration-ready dataset with an
audit trail.

For the full merge/normalize/migration workflow — duplicate detection,
survivor rules, field standardization, and migration-ready output — see the
**[CRM Dedup & Migration Cleanup Kit](https://payloadtools.gumroad.com/l/crm-dedup-migration-kit)**
($149) by Payload.

## License

MIT — see [LICENSE](LICENSE). Copyright 2026 Payload.
