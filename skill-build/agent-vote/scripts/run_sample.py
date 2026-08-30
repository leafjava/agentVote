#!/usr/bin/env python3
"""Run one or all deterministic enterprise samples against TouLeMa."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from agent_vote import AgentVoteClient, ApiError

ROOT = Path(__file__).resolve().parent.parent
GRADE = {"D": 0, "C": 1, "B": 2, "A": 3}


def run_sample(client: AgentVoteClient, path: Path, output_dir: Path | None) -> dict:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    suffix = uuid.uuid4().hex[:6]
    asker = client.register(
        f"{scenario['asker']}-{suffix}",
        description=f"Sample {scenario['id']} 提问者",
    )
    question = client.create_question(asker["api_key"], scenario["question"])
    if question.get("compliance_state") != "approved":
        raise RuntimeError(
            f"{path.name}: compliance_state={question.get('compliance_state')}，Sample 必须稳定通过"
        )

    for index, vote in enumerate(scenario["votes"], start=1):
        voter = client.register(
            f"{vote['agent']}-{suffix}",
            authentic=True,
            description=f"Sample {scenario['id']} Voter {index}",
        )
        client.vote(
            voter["api_key"],
            question["id"],
            {
                "choice": vote["choice"],
                "decisive_factors": vote["decisive_factors"],
                "factor_bindings": vote["factor_bindings"],
            },
        )

    pack = client.decision_pack(question["id"])
    expected = scenario["expected"]
    actual_choice = pack["decision"]["leading_choice"]
    if actual_choice != expected["leading_choice"]:
        raise AssertionError(
            f"{path.name}: leading_choice expected={expected['leading_choice']!r} actual={actual_choice!r}"
        )
    if GRADE[pack["evidence"]["grade"]] < GRADE[expected["min_grade"]]:
        raise AssertionError(
            f"{path.name}: evidence grade {pack['evidence']['grade']} < {expected['min_grade']}"
        )

    summary = {
        "sample": scenario["name"],
        "question_id": question["id"],
        "leading_choice": actual_choice,
        "consensus_ratio": pack["decision"]["consensus_ratio"],
        "disagreement_index": pack["decision"]["disagreement_index"],
        "evidence_grade": pack["evidence"]["grade"],
        "binding_coverage": pack["evidence"]["binding_coverage"],
        "unique_sources": pack["evidence"]["unique_sources"],
        "audit_digest": pack["audit"]["digest"],
    }
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{scenario['id']}.decision-pack.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 TouLeMa 三个企业级 Sample")
    parser.add_argument("samples", nargs="*", help="Sample JSON；省略则运行 samples/*.json")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    sample_paths = [Path(item) for item in args.samples]
    if not sample_paths:
        sample_paths = sorted((ROOT / "samples").glob("*.json"))
    client = AgentVoteClient(args.base_url)
    try:
        health = client.health()
        if health.get("status") != "ok":
            raise RuntimeError(f"健康检查失败：{health}")
        summaries = [run_sample(client, path, args.output_dir) for path in sample_paths]
    except (ApiError, AssertionError, KeyError, RuntimeError, ValueError) as exc:
        print(f"Sample 失败：{exc}", file=sys.stderr)
        return 1

    for index, summary in enumerate(summaries, start=1):
        print(
            f"[{index}/{len(summaries)}] {summary['sample']} | "
            f"领先={summary['leading_choice']} | 共识={summary['consensus_ratio']:.0%} | "
            f"证据={summary['evidence_grade']} | 来源={summary['unique_sources']} | "
            f"sha256={summary['audit_digest'][:12]}…"
        )
    print(f"\n通过：{len(summaries)} 个企业 Sample 全部可复现。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
