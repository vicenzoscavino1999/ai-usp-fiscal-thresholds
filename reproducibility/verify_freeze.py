"""Standalone audit of the frozen specification and protected tracked files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "reproducibility" / "protected_files_manifest.json"
SPEC_PATH = ROOT / "02_ESD_AI_USP_v6.md"
SPEC_HASH_PATH = ROOT / "PRIMARY_SPEC_HASH.txt"

# Tracked official artifacts used as protected inputs or comparators by the
# post-baseline extension runners. Runtime-only data/, db/, and results/ copies
# are intentionally excluded so this audit works from a reviewer checkout.
DEFAULT_PROTECTED_FILES = (
    "02_ESD_AI_USP_v6.md",
    "PRIMARY_SPEC_HASH.txt",
    "paper/main.tex",
    "paper/supplementary_appendix.tex",
    "reports/calibrated_parameter_registry_baseline-official-v3.csv",
    "reports/country_policy_classification_final_baseline-official-v3.csv",
    "reports/driver_ranking_baseline-official-v3.csv",
    "reports/fiscal_space_result_baseline-official-v2.csv",
    "reports/monte_carlo_result_baseline-official-v3.csv",
    "reports/paper_tables/table2_policy_costs.csv",
    "reports/policy_parameter_official_4c.csv",
    "reports/value_assignment_table_baseline-official-v3.csv",
    "reproducibility/reference/country_policy_classification_final.csv",
    "reproducibility/reference/driver_ranking.csv",
    "reproducibility/reference/fiscal_space_result.csv",
    "reproducibility/reference/monte_carlo_result.csv",
)

DEFAULT_AMENDMENT_REGISTRIES = (
    "reports/h_star_amendment_registry_baseline-official-v3.csv",
    "reports/omega_i_reporting_extension_amendment_registry_baseline-official-v3.csv",
    "reports/lsraw_robustness_amendment_registry_baseline-official-v3.csv",
    "reports/gmimicro_robustness_amendment_registry_baseline-official-v3.csv",
    "reports/gmimicro_chl_robustness_amendment_registry_baseline-official-v3.csv",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


TEXT_SUFFIXES = {".csv", ".json", ".md", ".tex", ".txt", ".yaml", ".yml"}


def sha256_protected_file(path: Path) -> str:
    """Hash text canonically so Git's CRLF checkout policy cannot break CI."""
    raw = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def declared_spec_hash() -> str:
    for line in SPEC_HASH_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("sha256:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"No sha256 entry in {SPEC_HASH_PATH.relative_to(ROOT)}")


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_manifest() -> None:
    missing = [path for path in DEFAULT_PROTECTED_FILES if not (ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError("Cannot create protected manifest; missing: " + ", ".join(missing))
    untracked = [
        path
        for path in DEFAULT_PROTECTED_FILES
        if subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        != 0
    ]
    if untracked:
        raise ValueError("Protected manifest is restricted to tracked files: " + ", ".join(untracked))
    payload = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_from_commit": git_value("rev-parse", "HEAD"),
        "scope_note": (
            "Tracked frozen specification and official comparators consumed by post-baseline extensions; "
            "author-held runtime mirrors under data/, db/, and results/ are outside this standalone manifest."
        ),
        "hash_mode": "sha256 of bytes; CRLF is normalized to LF for declared text suffixes",
        "protected_files": [
            {"path": path, "sha256": sha256_protected_file(ROOT / path)}
            for path in DEFAULT_PROTECTED_FILES
        ],
        "amendment_registries": list(DEFAULT_AMENDMENT_REGISTRIES),
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {MANIFEST_PATH.relative_to(ROOT).as_posix()} with {len(DEFAULT_PROTECTED_FILES)} files")


def load_registry(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "amendment_id" not in rows[0]:
        raise ValueError(f"{path.relative_to(ROOT).as_posix()}: missing amendment_id rows")
    return rows


def verify_amendments(registry_paths: list[str]) -> tuple[bool, list[str]]:
    messages: list[str] = []
    all_rows: list[tuple[str, dict[str, str]]] = []
    ok = True
    for relative in registry_paths:
        path = ROOT / relative
        if not path.is_file():
            messages.append(f"AMENDMENT MISSING {relative}")
            ok = False
            continue
        try:
            rows = load_registry(path)
        except (OSError, ValueError) as exc:
            messages.append(f"AMENDMENT CHANGED {relative}: {exc}")
            ok = False
            continue
        messages.append(f"AMENDMENT COHERENT {relative}: {len(rows)} row(s)")
        all_rows.extend((relative, row) for row in rows)

    ids = {row["amendment_id"].strip() for _, row in all_rows if row["amendment_id"].strip()}
    for relative, row in all_rows:
        amendment_id = row["amendment_id"].strip()
        supersedes = row.get("supersedes", "").strip()
        if supersedes and supersedes not in ids:
            messages.append(
                f"AMENDMENT BROKEN {relative}: {amendment_id} supersedes missing {supersedes}"
            )
            ok = False
        if supersedes and supersedes == amendment_id:
            messages.append(f"AMENDMENT BROKEN {relative}: {amendment_id} supersedes itself")
            ok = False
    return ok, messages


def verify_freeze() -> bool:
    if not MANIFEST_PATH.is_file():
        print(f"FREEZE VERIFY FAIL: missing {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
        return False
    manifest: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # PRIMARY_SPEC_HASH is defined over the canonical LF representation. Use
    # the same cross-platform normalization as the protected-file manifest so
    # a CRLF checkout or ZIP extraction cannot produce a false freeze failure.
    actual_spec = sha256_protected_file(SPEC_PATH)
    declared_spec = declared_spec_hash()
    spec_ok = actual_spec == declared_spec
    print(
        f"SPEC {'INTACT' if spec_ok else 'CHANGED'} {SPEC_PATH.name}: "
        f"actual={actual_spec} declared={declared_spec}"
    )

    files_ok = True
    intact = 0
    protected = manifest.get("protected_files", [])
    for entry in protected:
        relative = entry["path"]
        expected = entry["sha256"]
        path = ROOT / relative
        if not path.is_file():
            print(f"PROTECTED MISSING {relative}")
            files_ok = False
            continue
        actual = sha256_protected_file(path)
        status = "INTACT" if actual == expected else "CHANGED"
        print(f"PROTECTED {status} {relative}")
        if status == "INTACT":
            intact += 1
        else:
            files_ok = False

    amendment_paths = manifest.get("amendment_registries", [])
    amendments_ok, amendment_messages = verify_amendments(amendment_paths)
    for message in amendment_messages:
        print(message)

    passed = spec_ok and files_ok and amendments_ok and intact == len(protected)
    if passed:
        print(
            f"FREEZE VERIFY PASS: {intact} protected files intact, spec hash intact, "
            f"{len(amendment_paths)} amendment registries coherent"
        )
    else:
        print(
            f"FREEZE VERIFY FAIL: {intact}/{len(protected)} protected files intact, "
            f"spec_hash={'intact' if spec_ok else 'changed'}, "
            f"amendment_registries={'coherent' if amendments_ok else 'broken'}"
        )
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="create the manifest from the declared tracked-file inventory, then verify it",
    )
    args = parser.parse_args()
    if args.write_manifest:
        write_manifest()
    return 0 if verify_freeze() else 1


if __name__ == "__main__":
    raise SystemExit(main())
