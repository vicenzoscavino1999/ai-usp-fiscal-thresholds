"""Build the curated, deterministic public Zenodo reproduction bundle.

The Git repository intentionally ignores runtime data.  A release ZIP therefore
cannot be made safely with a generic archiver: this builder reads tracked files
from the exact HEAD commit, adds only the redistributable frozen inputs required
by the public path, and rejects restricted/raw executable payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL = "ai-usp-fiscal-thresholds"
DEFAULT_VERSION = "1.1.1-rc1"
DEFAULT_OUTPUT = ROOT / "dist" / f"zenodo_bundle_v{DEFAULT_VERSION}.zip"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

LF_NORMALIZED_PATHS = {"02_ESD_AI_USP_v6.md"}
EXCLUDED_TRACKED_PREFIXES = ("paper/clean/",)
FORBIDDEN_SUFFIXES = {".bat", ".cmd", ".com", ".dll", ".dta", ".exe", ".msi", ".ps1", ".sav", ".sh"}
FORBIDDEN_PARTS = {".git", "__pycache__", ".pytest_cache", "cache"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_relative(raw: str | Path) -> str:
    value = str(raw).replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe bundle path: {raw}")
    return path.as_posix()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def tracked_files() -> set[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    files = set()
    for item in output.decode("utf-8").split("\0"):
        if not item:
            continue
        relative = canonical_relative(item)
        if any(relative.startswith(prefix) for prefix in EXCLUDED_TRACKED_PREFIXES):
            continue
        if (ROOT / relative).is_file():
            files.add(relative)
    return files


def require_file(relative: str, files: set[str]) -> None:
    relative = canonical_relative(relative)
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required public bundle input is missing: {relative}")
    if path.is_symlink():
        raise ValueError(f"Symlinks are not permitted in the public bundle: {relative}")
    files.add(relative)


def add_model_inputs(files: set[str]) -> None:
    root = ROOT / "data" / "model_inputs"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing model-input directory: {root}")
    for path in root.rglob("*"):
        if path.is_file():
            require_file(path.relative_to(ROOT).as_posix(), files)


def load_manifest(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def add_manifest_sources(
    files: set[str],
    manifest_relative: str,
    *,
    source_ids: set[str] | None = None,
    parquet_only: bool = False,
    metadata_only: bool = False,
) -> None:
    manifest = load_manifest(manifest_relative)
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id", ""))
        if source_ids is not None and source_id not in source_ids:
            continue
        metadata_path = source.get("metadata_path")
        if metadata_path:
            require_file(str(metadata_path), files)
        if metadata_only:
            continue
        for raw in source.get("raw_files", []):
            if not isinstance(raw, dict) or not raw.get("path"):
                continue
            relative = canonical_relative(str(raw["path"]))
            if parquet_only and Path(relative).suffix.lower() != ".parquet":
                continue
            require_file(relative, files)
            expected = str(raw.get("sha256", "")).lower()
            if expected:
                actual = sha256_file(ROOT / relative)
                if actual != expected:
                    raise ValueError(
                        f"Frozen-input hash mismatch for {relative}: expected={expected} actual={actual}"
                    )


def curated_files(tracked: set[str] | None = None) -> set[str]:
    files = set(tracked if tracked is not None else tracked_files())
    add_model_inputs(files)

    # Complete public baseline: filtered/derived parquets plus every source
    # metadata record promised by DATA_AVAILABILITY.md.
    add_manifest_sources(
        files,
        "reproducibility/snapshot/dataset_manifest_v1.0.1-official-4c.json",
    )

    # H* is the only post-baseline consumer of v1.1.0.  Other v1.1 files are
    # byte-identical baseline duplicates; shipping only the extended WPP source
    # avoids duplicating ~44 MiB while satisfying the registered H* contract.
    add_manifest_sources(
        files,
        "reproducibility/snapshot/dataset_manifest_v1.1.0-official-4c.json",
        source_ids={"UN_WPP"},
    )

    # Public robustness extensions use the reduced parquets and metadata, not
    # the provider ZIP/SAV/codebook payloads.
    add_manifest_sources(
        files,
        "reproducibility/snapshot/dataset_manifest_robustness-lsraw-v1.json",
        parquet_only=True,
    )
    add_manifest_sources(
        files,
        "reproducibility/snapshot/dataset_manifest_robustness-gmimicro-chl-v1.json",
        parquet_only=True,
    )

    # ENAHO row-level data remain excluded.  Its non-sensitive provenance
    # metadata is public and lets a reviewer reconstruct the restricted arm.
    add_manifest_sources(
        files,
        "reproducibility/snapshot/dataset_manifest_robustness-gmimicro-per-v1.json",
        metadata_only=True,
    )
    return files


def validate_policy(files: Iterable[str]) -> None:
    for relative in files:
        path = PurePosixPath(relative)
        lower_parts = {part.lower() for part in path.parts}
        if lower_parts & FORBIDDEN_PARTS:
            raise ValueError(f"Forbidden directory in bundle: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError(f"Forbidden executable or restricted raw suffix in bundle: {relative}")
        if relative.startswith("data/raw_snapshots/robustness-gmimicro-per-v1/") and path.name != "metadata.json":
            raise ValueError(f"ENAHO row-level payload must not be redistributed: {relative}")


def archive_bytes(relative: str, *, tracked: bool) -> bytes:
    if tracked:
        # Read the committed blob instead of the checked-out representation.
        # This prevents Windows checkout line-ending conversion from changing
        # a bundle built from the same commit, while retaining historical blob
        # bytes in checksum-governed snapshot/reference trees.
        payload = subprocess.check_output(["git", "cat-file", "blob", f"HEAD:{relative}"], cwd=ROOT)
    else:
        payload = (ROOT / relative).read_bytes()
    # The primary spec's declared governance hash is explicitly LF-based.
    if relative in LF_NORMALIZED_PATHS:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload


def zip_info(archive_name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def tracked_tree_is_clean() -> bool:
    unstaged = subprocess.run(["git", "diff", "--quiet"], cwd=ROOT, check=False).returncode
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False).returncode
    return unstaged == 0 and staged == 0


def build(output: Path, version: str, *, allow_dirty: bool = False) -> dict[str, object]:
    if not allow_dirty and not tracked_tree_is_clean():
        raise RuntimeError("Refusing to build from modified tracked files; commit the release fixes or pass --allow-dirty")

    tracked = tracked_files()
    files = sorted(curated_files(tracked))
    validate_policy(files)
    payloads = {relative: archive_bytes(relative, tracked=relative in tracked) for relative in files}
    file_manifest = {
        relative: {"sha256": sha256_bytes(payload), "size": len(payload)}
        for relative, payload in payloads.items()
    }
    bundle_manifest = {
        "schema_version": "1.0",
        "bundle_version": version,
        "source_commit": git_output("rev-parse", "HEAD"),
        "top_level_directory": TOP_LEVEL,
        "tracked_file_source": "exact blobs from the declared HEAD commit",
        "line_endings": "committed bytes preserved; primary specification normalized to LF",
        "public_reproduction_scope": "all registered public paths; ENAHO row-level microdata excluded",
        "files": file_manifest,
    }
    manifest_payload = (json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, payload in sorted(payloads.items()):
            archive.writestr(zip_info(f"{TOP_LEVEL}/{relative}"), payload)
        archive.writestr(zip_info(f"{TOP_LEVEL}/BUNDLE_MANIFEST.json"), manifest_payload)

    return {
        "status": "PASS",
        "output": str(output),
        "files": len(files) + 1,
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
        "source_commit": bundle_manifest["source_commit"],
        "version": version,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.check_only:
        files = sorted(curated_files())
        validate_policy(files)
        print(json.dumps({"status": "PASS", "files": len(files)}, indent=2))
        return 0

    result = build(args.output, args.version, allow_dirty=args.allow_dirty)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
