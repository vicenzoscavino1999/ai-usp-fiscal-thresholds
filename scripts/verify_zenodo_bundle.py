"""Verify integrity and public-policy constraints of a Zenodo bundle ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN_SUFFIXES = {".bat", ".cmd", ".com", ".dll", ".exe", ".msi", ".ps1", ".sh"}
DECLARED_HASH_RE = re.compile(r"^sha256:\s*([0-9a-f]{64})\s*$", re.MULTILINE)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_unsafe(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or any(":" in part for part in path.parts)
        or "\\" in name
    )


def is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def verify(path: Path) -> dict[str, object]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("ZIP contains duplicate entry names")
        unsafe = [name for name in names if is_unsafe(name)]
        if unsafe:
            raise ValueError(f"ZIP contains unsafe paths: {unsafe[:5]}")
        symlinks = [info.filename for info in infos if is_symlink(info)]
        if symlinks:
            raise ValueError(f"ZIP contains symlinks: {symlinks[:5]}")
        executables = [name for name in names if PurePosixPath(name).suffix.lower() in FORBIDDEN_SUFFIXES]
        if executables:
            raise ValueError(f"ZIP contains executable payloads: {executables[:5]}")

        top_levels = {PurePosixPath(name).parts[0] for name in names}
        if top_levels != {"ai-usp-fiscal-thresholds"}:
            raise ValueError(f"Unexpected top-level entries: {sorted(top_levels)}")
        prefix = "ai-usp-fiscal-thresholds/"
        manifest_name = prefix + "BUNDLE_MANIFEST.json"
        if manifest_name not in names:
            raise ValueError("BUNDLE_MANIFEST.json is missing")
        manifest = json.loads(archive.read(manifest_name))
        expected = manifest.get("files", {})
        actual_names = {name.removeprefix(prefix) for name in names if name != manifest_name}
        if actual_names != set(expected):
            missing = sorted(set(expected) - actual_names)
            extra = sorted(actual_names - set(expected))
            raise ValueError(f"Bundle manifest inventory mismatch: missing={missing[:5]} extra={extra[:5]}")
        for relative, contract in expected.items():
            payload = archive.read(prefix + relative)
            if len(payload) != int(contract["size"]):
                raise ValueError(f"Size mismatch: {relative}")
            actual_hash = sha256_bytes(payload)
            if actual_hash != contract["sha256"]:
                raise ValueError(f"SHA-256 mismatch: {relative}")

        spec = archive.read(prefix + "02_ESD_AI_USP_v6.md").replace(b"\r\n", b"\n")
        declaration = archive.read(prefix + "PRIMARY_SPEC_HASH.txt").decode("utf-8")
        match = DECLARED_HASH_RE.search(declaration)
        if match is None:
            raise ValueError("PRIMARY_SPEC_HASH.txt has no SHA-256 declaration")
        spec_hash = sha256_bytes(spec)
        if spec_hash != match.group(1):
            raise ValueError(f"Primary specification hash mismatch: actual={spec_hash} declared={match.group(1)}")

    return {
        "status": "PASS",
        "zip": str(path),
        "zip_sha256": sha256_file(path),
        "entries": len(names),
        "unsafe_paths": 0,
        "symlinks": 0,
        "executable_payloads": 0,
        "primary_spec_sha256": spec_hash,
        "bundle_version": manifest.get("bundle_version"),
        "source_commit": manifest.get("source_commit"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.zip_path), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
