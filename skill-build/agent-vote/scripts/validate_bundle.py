#!/usr/bin/env python3
"""Static validator for a ClawHive-ready TouLeMa Skill bundle."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {".sqlite", ".pyc", ".pyo", ".log"}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"av_[a-fA-F0-9]{32}"),
    re.compile(r"(?i)(api[_-]?key|admin[_-]?token)\s*[:=]\s*['\"][^${][^'\"]{12,}"),
]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    required = ["SKILL.md", "README.md", "_meta.json"]
    for name in required:
        if not (root / name).is_file():
            errors.append(f"缺少 {name}")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        skill = skill_path.read_text(encoding="utf-8")
        if not skill.startswith("---\n") or "\nname: tou-le-ma\n" not in skill:
            errors.append("SKILL.md frontmatter 缺少 name: tou-le-ma")
        if "description:" not in skill.split("---", 2)[1]:
            errors.append("SKILL.md frontmatter 缺少 description")
        for link in LINK_PATTERN.findall(skill):
            if "://" in link or link.startswith("#"):
                continue
            target = (root / link.split("#", 1)[0]).resolve()
            if not target.exists() or root.resolve() not in target.parents:
                errors.append(f"SKILL.md 引用不存在或越界：{link}")

    sample_paths = sorted((root / "samples").glob("*.json"))
    if len(sample_paths) < 3:
        errors.append(f"企业 Sample 少于 3 个：{len(sample_paths)}")
    for path in sample_paths:
        try:
            sample = json.loads(path.read_text(encoding="utf-8"))
            for key in ("id", "name", "asker", "question", "votes", "expected"):
                if key not in sample:
                    errors.append(f"{path.name} 缺少字段 {key}")
            if len(sample.get("votes", [])) < 3:
                errors.append(f"{path.name} 至少需要 3 张独立票")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name} JSON 无效：{exc}")

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        # Source workspaces may contain ignored interpreter caches; build_bundle.py
        # excludes them from the deliverable, so do not treat them as Skill files.
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"包含运行产物：{relative}")
            continue
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            except SyntaxError as exc:
                errors.append(f"Python 语法错误 {relative}:{exc.lineno}: {exc.msg}")
        if path.suffix.lower() in {".md", ".json", ".py", ".txt"}:
            text = path.read_text(encoding="utf-8")
            unfinished_tokens = ("TO" + "DO", "TB" + "D", "example" + ".invalid")
            if any(token in text for token in unfinished_tokens):
                errors.append(f"包含未完成占位符：{relative}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"疑似密钥：{relative}")
                    break
    return sorted(set(errors))


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = validate(root)
    if errors:
        print("Bundle 校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Bundle 校验通过：{root.name}，3+ Sample、引用、语法、敏感信息和运行产物均合格。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
