#!/usr/bin/env python3
"""Test runner for csv-duplicate-inspector.

Runs inspect.py against every fixture and asserts the expected exit code
and expected output markers. Also runs a 60k-row streaming smoke test.
Exit 0 only if all assertions pass.
"""

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSPECT = ROOT / "inspect.py"
FIX = ROOT / "tests" / "fixtures"

# (args, expected_exit, markers_that_must_appear)
CASES = [
    (["clean.csv"], 0, ["Exact-duplicate rows: none"]),
    (["exact_dupes.csv"], 1, ["Exact-duplicate rows: 5 rows in 2 groups"]),
    (["key_dupes.csv", "--key", "email"], 1,
     ['Key column "email": 2 duplicate value(s) affecting 4 rows',
      "alice@example.com", "bob@example.com"]),
    (["near_dupes.csv", "--key", "company", "--near-dup"], 1,
     ["Near-duplicate clusters", "acme inc", "globex"]),
    (["ragged.csv"], 2, ["ragged row(s)"]),
    (["missing_key.csv", "--key", "nope"], 1, ["NOT FOUND"]),
]


def run(args):
    cmd = [sys.executable, str(INSPECT)] + [str(FIX / a) if a.endswith(".csv")
                                            else a for a in args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def streaming_smoke_test() -> list[str]:
    """Generate 60k rows with known duplicates; verify counts and speed."""
    problems = []
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "email"])
        for i in range(60000):
            # every 100th row repeats row 0's email; every 1000th row is an
            # exact repeat of row 5
            if i % 1000 == 5:
                w.writerow(["5", "user5@example.com"])
            elif i % 100 == 0:
                w.writerow([str(i), "dup@example.com"])
            else:
                w.writerow([str(i), f"user{i}@example.com"])
        path = fh.name
    try:
        cmd = [sys.executable, str(INSPECT), path, "--key", "email", "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        import json
        data = json.loads(proc.stdout)
        # rows 0..59900 step 100 share "dup@example.com": 600 rows, 1 key.
        # (i%1000==5 never coincides with i%100==0, so no overlap.)
        if data["exact_duplicate_groups"] != 1:
            problems.append(
                f"expected 1 exact-dupe group, got {data['exact_duplicate_groups']}")
        if data["exact_duplicate_rows"] != 60:
            problems.append(
                f"expected 60 exact-dupe rows, got {data['exact_duplicate_rows']}")
        kd = data["key_duplicates"].get("dup@example.com", {})
        if kd.get("count") != 600:
            problems.append(
                f"expected 600 dup@example.com rows, got {kd.get('count')}")
        if proc.returncode != 1:
            problems.append(f"expected exit 1, got {proc.returncode}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"smoke test raised: {exc}")
    finally:
        Path(path).unlink(missing_ok=True)
    return problems


def main() -> int:
    failures = 0
    for args, expected_exit, markers in CASES:
        code, output = run(args)
        problems = []
        if code != expected_exit:
            problems.append(f"exit={code}, expected {expected_exit}")
        for want in markers:
            if want not in output:
                problems.append(f"missing marker {want!r}")
        if problems:
            failures += 1
            print(f"FAIL {args}: {'; '.join(problems)}")
            print("---- output ----")
            print(output.strip())
            print("----------------")
        else:
            print(f"ok   {' '.join(args)} (exit {code})")

    smoke_problems = streaming_smoke_test()
    if smoke_problems:
        failures += 1
        print(f"FAIL streaming smoke test: {'; '.join(smoke_problems)}")
    else:
        print("ok   streaming smoke test (60k rows)")

    total = len(CASES) + 1
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
