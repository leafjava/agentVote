#!/usr/bin/env python3
"""Build a deterministic ClawHive Skill ZIP and verify byte-for-byte contents."""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "agent-vote"
OUTPUT = ROOT / "agent-vote.zip"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".log"}


def source_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE.rglob("*")
        if path.is_file()
        and not EXCLUDED_PARTS.intersection(path.parts)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    files = source_files()
    if not files or files[0].name == "":
        print("Skill 源目录为空", file=sys.stderr)
        return 1
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(SOURCE).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())

    with zipfile.ZipFile(OUTPUT) as archive:
        names = archive.namelist()
        expected = [path.relative_to(SOURCE).as_posix() for path in files]
        if names != expected:
            raise RuntimeError("ZIP 文件顺序或文件列表与源目录不一致")
        for path, name in zip(files, names):
            if digest(path.read_bytes()) != digest(archive.read(name)):
                raise RuntimeError(f"ZIP 内容不一致：{name}")
    print(f"已生成 {OUTPUT.name}：{len(files)} 个文件，{OUTPUT.stat().st_size} bytes，内容校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
