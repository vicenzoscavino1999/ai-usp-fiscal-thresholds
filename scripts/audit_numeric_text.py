"""Editorial numeric-token audit for the body-compression phase.

This tool compares protected textual tokens between two TeX versions. Inputs
may be filesystem paths or Git object specs such as
``c2064ab:paper/main_jpm.tex``. It reports multiset differences for the body,
appendix, and complete document. A difference passes only when an exact signed
delta is present in a JSON whitelist with a non-empty justification. The tool is
editorial infrastructure and does not read from or write to the data pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
INTRODUCTION = r"\section{Introduction}"
APPENDIX = r"\appendix"
BIBLIOGRAPHY = r"\begin{thebibliography}"

COMMAND_PATTERN = re.compile(r"\\(?:eqref|ref|label)\{[^{}]+\}")
HORIZON_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:H|horizon)\s*(?:=|\\in|in)\s*"
    r"(?:\{[^{}]+\}|\[[^\]]+\]|[-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
RANGE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?\s*(?:--|\\textendash|–|—)\s*"
    r"[-+]?\d+(?:\.\d+)?\s*(?:\\%|%|percent(?:age points?)?)?",
    re.IGNORECASE,
)
PERCENT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?\s*(?:\\%|%|percent(?:age points?)?)",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9])")
SIGN_PATTERN = re.compile(r"\\leq|\\geq|≤|≥|(?<![A-Za-z])<|>(?![A-Za-z])")

SCENARIO_TERMS = (
    "low",
    "mid",
    "high",
    "stress",
    "conservative",
    "moderate",
    "disruptive",
)

CLASSIFICATION_TERMS = (
    "baseline feasible",
    "frontier feasible",
    "stress feasible",
    "floor-driven",
    "FloorDriven",
    "feasible_cell",
    "not_feasible",
    "impossible_or_noncomputable",
    "accounting_feasible_debt_failed",
    "extreme_conditional_crossing",
    "fiscally_ordinary",
    "fiscally_moderate",
    "fiscally_demanding",
    "extreme_or_outside_historical_support",
    "robustly_feasible",
    "conditionally_feasible",
    "fragile_feasible",
    "stress_benchmark_only",
)


@dataclass(frozen=True)
class WhitelistEntry:
    scope: str
    token: str
    delta: int
    justification: str


def read_source(spec: str) -> str:
    path = Path(spec)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return path.read_text(encoding="utf-8")
    try:
        return subprocess.check_output(
            ["git", "show", spec], cwd=ROOT, text=True, encoding="utf-8"
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"cannot read path or Git object spec: {spec}") from exc


def split_scopes(text: str) -> dict[str, str]:
    body_start = text.find(INTRODUCTION)
    appendix_start = text.find(APPENDIX)
    if body_start < 0:
        raise ValueError("could not locate Introduction/body boundary")
    if appendix_start < 0:
        bibliography_start = text.find(BIBLIOGRAPHY, body_start)
        if bibliography_start < 0:
            raise ValueError("could not locate appendix or bibliography body boundary")
        return {
            "body": text[body_start:bibliography_start],
            "appendix": "",
            "document": text,
        }
    if appendix_start <= body_start:
        raise ValueError("could not locate Introduction/body and appendix boundaries")
    return {
        "body": text[body_start:appendix_start],
        "appendix": text[appendix_start:],
        "document": text,
    }


def normalized_token(kind: str, value: str) -> str:
    compact = re.sub(r"\s+", " ", value.strip())
    if kind in {"scenario", "classification"}:
        compact = compact.lower()
    return f"{kind}:{compact}"


def extract_tokens(text: str) -> Counter[str]:
    tokens: Counter[str] = Counter()
    patterns = (
        ("command", COMMAND_PATTERN),
        ("horizon", HORIZON_PATTERN),
        ("range", RANGE_PATTERN),
        ("percent", PERCENT_PATTERN),
        ("number", NUMBER_PATTERN),
        ("sign", SIGN_PATTERN),
    )
    for kind, pattern in patterns:
        tokens.update(normalized_token(kind, match.group(0)) for match in pattern.finditer(text))
    for term in SCENARIO_TERMS:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
        tokens.update(normalized_token("scenario", term) for _ in pattern.finditer(text))
    for term in CLASSIFICATION_TERMS:
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", re.IGNORECASE)
        tokens.update(normalized_token("classification", term) for _ in pattern.finditer(text))
    return tokens


def counter_diff(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    return {
        token: after[token] - before[token]
        for token in sorted(set(before) | set(after))
        if after[token] != before[token]
    }


def load_whitelist(path: str | None, inline: Iterable[str]) -> list[WhitelistEntry]:
    entries: list[WhitelistEntry] = []
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in payload.get("entries", []):
            entries.append(
                WhitelistEntry(
                    scope=str(row["scope"]),
                    token=str(row["token"]),
                    delta=int(row["delta"]),
                    justification=str(row["justification"]).strip(),
                )
            )
    for value in inline:
        parts = value.split("|", 3)
        if len(parts) != 4:
            raise ValueError("--allow must be scope|token|delta|justification")
        entries.append(WhitelistEntry(parts[0], parts[1], int(parts[2]), parts[3].strip()))
    invalid = [entry for entry in entries if not entry.justification]
    if invalid:
        raise ValueError("every whitelist entry requires a non-empty justification")
    return entries


def audit(before_text: str, after_text: str, whitelist: list[WhitelistEntry]) -> bool:
    before_scopes = split_scopes(before_text)
    after_scopes = split_scopes(after_text)
    allowed = {(entry.scope, entry.token, entry.delta): entry for entry in whitelist}
    used: set[tuple[str, str, int]] = set()
    passed = True

    for scope in ("body", "appendix", "document"):
        before = extract_tokens(before_scopes[scope])
        after = extract_tokens(after_scopes[scope])
        differences = counter_diff(before, after)
        print(
            f"SCOPE {scope}: before_tokens={sum(before.values())} "
            f"after_tokens={sum(after.values())} differences={len(differences)}"
        )
        for token, delta in differences.items():
            key = (scope, token, delta)
            entry = allowed.get(key)
            if entry:
                used.add(key)
                print(f"  WHITELISTED delta={delta:+d} {token} :: {entry.justification}")
            else:
                passed = False
                print(f"  UNWHITELISTED delta={delta:+d} {token}")

    unused = sorted(set(allowed) - used)
    for key in unused:
        passed = False
        entry = allowed[key]
        print(
            f"UNUSED WHITELIST scope={entry.scope} delta={entry.delta:+d} "
            f"{entry.token} :: {entry.justification}"
        )
    print(
        f"NUMERIC TEXT AUDIT {'PASS' if passed else 'FAIL'}: "
        f"whitelist_entries={len(whitelist)} used={len(used)}"
    )
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", help="baseline path or Git object spec")
    parser.add_argument("after", help="candidate path or Git object spec")
    parser.add_argument("--whitelist", help="JSON file with exact scope/token/delta/justification entries")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="inline scope|token|delta|justification entry; may be repeated",
    )
    args = parser.parse_args()
    try:
        before = read_source(args.before)
        after = read_source(args.after)
        whitelist = load_whitelist(args.whitelist, args.allow)
        return 0 if audit(before, after, whitelist) else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"NUMERIC TEXT AUDIT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
