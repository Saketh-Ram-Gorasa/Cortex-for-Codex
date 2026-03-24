from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


FIXED_ZIP_DT = (2026, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "chroma_db",
    "extracted_logs",
    "dist",
}
EXCLUDED_FILE_NAMES = {
    ".env",
    "auth.db",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite3",
    ".zip",
    ".log",
}

CORE_FILES = [
    "main.py",
    "mcp_server.py",
    "config.py",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "Dockerfile",
    ".env.example",
    "verify_backend.py",
]
CORE_DIRS = [
    "agents",
    "auth",
    "models",
    "projects",
    "services",
    "teams",
    "runtime",
]


def _is_excluded(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def _iter_dir_files(base_dir: Path, relative_dir: Path) -> Iterable[Path]:
    source_dir = base_dir / relative_dir
    if not source_dir.exists() or not source_dir.is_dir():
        return []

    files: list[Path] = []
    for candidate in source_dir.rglob("*"):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(base_dir)
        if _is_excluded(rel):
            continue
        files.append(rel)

    return sorted(files, key=lambda p: p.as_posix())


def _sha256_for(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(64 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_version(base_dir: Path) -> str:
    pyproject = base_dir / "pyproject.toml"
    with pyproject.open("rb") as file_obj:
        data = tomllib.load(file_obj)
    return str(((data.get("project") or {}).get("version")) or "0.0.0")


def _zipinfo_for(arcname: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_DT)
    if arcname.endswith(".sh"):
        info.external_attr = 0o755 << 16
    else:
        info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _build_offline_wheelhouse(base_dir: Path, target_dir: Path) -> list[tuple[Path, str]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    requirements = base_dir / "requirements.txt"
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "-r",
        str(requirements),
        "-d",
        str(target_dir),
    ]
    result = subprocess.run(cmd, cwd=base_dir, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to build wheelhouse for offline runtime ZIP.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    entries: list[tuple[Path, str]] = []
    for wheel_file in sorted(target_dir.glob("*"), key=lambda p: p.name.lower()):
        if wheel_file.is_file():
            entries.append((wheel_file, f"wheelhouse/{wheel_file.name}"))
    return entries


def create_local_runtime_zip(
    base_dir: Path,
    output_file: Path,
    include_wheelhouse: bool,
) -> Path:
    source_entries: list[tuple[Path, str]] = []
    files_to_package: list[Path] = []

    for file_name in CORE_FILES:
        path = Path(file_name)
        full = base_dir / path
        if full.exists() and full.is_file() and not _is_excluded(path):
            files_to_package.append(path)

    for dir_name in CORE_DIRS:
        files_to_package.extend(_iter_dir_files(base_dir, Path(dir_name)))

    deduped = sorted({path.as_posix(): path for path in files_to_package}.values(), key=lambda p: p.as_posix())
    for rel_path in deduped:
        source_entries.append((base_dir / rel_path, rel_path.as_posix()))

    if include_wheelhouse:
        with tempfile.TemporaryDirectory(prefix="secondcortex-wheelhouse-") as temp_dir:
            wheelhouse_entries = _build_offline_wheelhouse(base_dir, Path(temp_dir) / "wheelhouse")
            source_entries.extend(wheelhouse_entries)

            _write_zip(output_file, source_entries)
            return output_file

    _write_zip(output_file, source_entries)
    return output_file


def _write_zip(output_file: Path, source_entries: list[tuple[Path, str]]) -> None:
    deduped_entries: dict[str, Path] = {}
    for source_path, arcname in source_entries:
        deduped_entries[arcname] = source_path

    ordered_entries = sorted(deduped_entries.items(), key=lambda item: item[0])

    manifest_entries: list[dict[str, str | int]] = []
    for arcname, full_path in ordered_entries:
        manifest_entries.append(
            {
                "path": arcname,
                "size": full_path.stat().st_size,
                "sha256": _sha256_for(full_path),
            }
        )

    manifest = {
        "name": "secondcortex-local-runtime",
        "format": "full",
        "file_count": len(manifest_entries),
        "files": manifest_entries,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_file, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for arcname, full_path in ordered_entries:
            data = full_path.read_bytes()
            zip_file.writestr(_zipinfo_for(arcname), data)

        manifest_data = json.dumps(manifest, indent=2).encode("utf-8")
        zip_file.writestr(_zipinfo_for("RUNTIME_MANIFEST.json"), manifest_data)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    version = _read_version(script_dir)

    parser = argparse.ArgumentParser(description="Create stable SecondCortex Local Runtime full ZIP")
    parser.add_argument(
        "--output",
        default=str(script_dir / "dist" / f"secondcortex-local-runtime-v{version}-full.zip"),
        help="Output ZIP path",
    )
    parser.add_argument(
        "--include-wheelhouse",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Bundle dependency wheels for offline install (default: enabled)",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    archive = create_local_runtime_zip(
        script_dir,
        output_path,
        include_wheelhouse=args.include_wheelhouse,
    )

    size_mb = archive.stat().st_size / (1024 * 1024)
    print(f"Created stable runtime ZIP: {archive}")
    print(f"Size: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
