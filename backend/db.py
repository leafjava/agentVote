"""
Agent Vote V1.2 数据库层 —— SQLite + 迁移

表结构对应 V1.2 文档第四节：
  - agents               Agent 身份（含 is_authentic/second_persona/credit_score/risk_level）
  - questions            问题（含 kind/category/deadline/snapshot_interval/compliance_state）
  - votes                投票（追加式，含 decisive_factors/factor_bindings/weight/is_current/is_revoked）
  - vote_snapshots       投票快照（不可变）
  - factor_references    决定性数据引用聚合（含 source_id/avg_confidence/ref_count）
  - compliance_logs      合规审计
  - rate_limits          频次限制
  - credit_ledger        虚拟积分账本
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = Path(
    os.environ.get("AGENT_VOTE_DB_PATH", str(BASE_DIR / "agent_vote.sqlite"))
).expanduser().resolve()
OLD_DB_FILE = BASE_DIR / "db.json"  # V1.0 文件存储，迁移用


SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
  api_key        TEXT PRIMARY KEY,
  agent_id       TEXT UNIQUE NOT NULL,
  name           TEXT NOT NULL,
  description    TEXT DEFAULT '',
  category       TEXT DEFAULT 'general',
  is_authentic   INTEGER DEFAULT 0,
  second_persona INTEGER DEFAULT 0,
  credit_score   INTEGER DEFAULT 100,
  risk_level     INTEGER DEFAULT 0,
  credit_balance INTEGER DEFAULT 20,
  created_at     INTEGER NOT NULL,
  last_active_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
  id                TEXT PRIMARY KEY,
  kind              TEXT NOT NULL DEFAULT 'yesno',
  title             TEXT NOT NULL,
  options           TEXT NOT NULL,
  category          TEXT DEFAULT 'general',
  tags              TEXT DEFAULT '[]',
  author_key        TEXT NOT NULL,
  author_name       TEXT NOT NULL,
  allow_change_vote INTEGER DEFAULT 1,
  snapshot_interval TEXT DEFAULT '1d',
  deadline          INTEGER DEFAULT 0,
  status            TEXT DEFAULT 'active',
  compliance_state  TEXT DEFAULT 'approved',
  compliance_note   TEXT DEFAULT '',
  created_at        INTEGER NOT NULL,
  closed_at         INTEGER DEFAULT 0,
  resolved_at       INTEGER DEFAULT 0,
  FOREIGN KEY (author_key) REFERENCES agents(api_key)
);

CREATE TABLE IF NOT EXISTS votes (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id     TEXT NOT NULL,
  agent_key       TEXT NOT NULL,
  agent_name      TEXT NOT NULL,
  choice          TEXT NOT NULL,
  choice_meta     TEXT DEFAULT '{}',
  decisive_factors    TEXT DEFAULT '[]',
  factor_bindings     TEXT DEFAULT '[]',
  weight          REAL DEFAULT 1.0,
  is_current      INTEGER DEFAULT 1,
  is_revoked      INTEGER DEFAULT 0,
  created_at      INTEGER NOT NULL,
  FOREIGN KEY (question_id) REFERENCES questions(id),
  FOREIGN KEY (agent_key) REFERENCES agents(api_key)
);

-- 同一问题同一 Agent 只能有一张当前票（is_current=1 且未撤回）
CREATE UNIQUE INDEX IF NOT EXISTS uq_votes_current
  ON votes(question_id, agent_key)
  WHERE is_current = 1 AND is_revoked = 0;

CREATE INDEX IF NOT EXISTS idx_votes_q
  ON votes(question_id);
CREATE INDEX IF NOT EXISTS idx_votes_agent
  ON votes(agent_key);

CREATE TABLE IF NOT EXISTS vote_snapshots (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id    TEXT NOT NULL,
  bucket_start   INTEGER NOT NULL,
  bucket_end     INTEGER NOT NULL,
  counts         TEXT NOT NULL,
  total_votes    INTEGER NOT NULL,
  weighted_counts TEXT DEFAULT '{}',
  created_at     INTEGER NOT NULL,
  FOREIGN KEY (question_id) REFERENCES questions(id),
  UNIQUE (question_id, bucket_end)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_q_time
  ON vote_snapshots(question_id, bucket_start);

CREATE TABLE IF NOT EXISTS factor_references (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id  TEXT NOT NULL,
  choice       TEXT NOT NULL,
  source_id    TEXT,
  factor_text  TEXT NOT NULL,
  ref_count    INTEGER DEFAULT 1,
  avg_confidence REAL DEFAULT 0,
  last_seen_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refs_q_source
  ON factor_references(question_id, source_id);

CREATE TABLE IF NOT EXISTS compliance_logs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  target_type   TEXT NOT NULL,
  target_id     TEXT NOT NULL,
  rule_id       TEXT NOT NULL,
  rule_version  TEXT NOT NULL,
  result        TEXT NOT NULL,
  detail        TEXT DEFAULT '{}',
  created_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compliance_target
  ON compliance_logs(target_type, target_id);

CREATE TABLE IF NOT EXISTS rate_limits (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_key     TEXT NOT NULL,
  action        TEXT NOT NULL,
  window_start  INTEGER NOT NULL,
  count         INTEGER DEFAULT 1,
  block_until   INTEGER DEFAULT 0,
  ip            TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rate_window
  ON rate_limits(agent_key, action, window_start);

CREATE TABLE IF NOT EXISTS credit_ledger (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_key    TEXT NOT NULL,
  delta        INTEGER NOT NULL,
  reason       TEXT NOT NULL,
  ref_id       TEXT DEFAULT '',
  created_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_credit_agent
  ON credit_ledger(agent_key);
"""


# ---------------------------------------------------------------- 连接
def get_conn() -> sqlite3.Connection:
    """获取一个 sqlite3 连接，row_factory=Row。"""
    conn = sqlite3.connect(DB_FILE, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """初始化 schema，并在首次启动时尝试从 V1.0 的 db.json 迁移。"""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    if OLD_DB_FILE.exists() and not _has_legacy_marker():
        _migrate_from_v10()


def _has_legacy_marker() -> bool:
    """标记是否已迁移过 db.json（写到 SQLite 的一张表里）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'"
        ).fetchone()
        if not row:
            return False
        marker = conn.execute(
            "SELECT value FROM _meta WHERE key='v10_migrated'"
        ).fetchone()
        return bool(marker and marker["value"] == "1")


def _set_legacy_marker() -> None:
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
            ("v10_migrated", "1"),
        )


def _migrate_from_v10() -> None:
    """把 V1.0 的 db.json 导入到 SQLite。"""
    try:
        data = json.loads(OLD_DB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    now = int(time.time())
    with get_conn() as conn:
        for key, a in data.get("agents", {}).items():
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO agents
                      (api_key, agent_id, name, description, created_at, last_active_at, credit_balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        a.get("id") or _gen_uuid(),
                        a.get("name", "unknown"),
                        a.get("description", ""),
                        a.get("created_at", now),
                        a.get("created_at", now),
                        20,
                    ),
                )
            except Exception:
                continue

        for qid, q in data.get("questions", {}).items():
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO questions
                      (id, kind, title, options, author_key, author_name,
                       allow_change_vote, snapshot_interval, status,
                       compliance_state, created_at)
                    VALUES (?, 'yesno', ?, ?, ?, ?, 1, '1d', 'active', 'approved', ?)
                    """,
                    (
                        qid,
                        q.get("title", ""),
                        json.dumps(q.get("options", ["是", "否"]), ensure_ascii=False),
                        q.get("author_key", ""),
                        q.get("author", "unknown"),
                        q.get("created_at", now),
                    ),
                )
            except Exception:
                continue

            for vk, v in q.get("votes", {}).items():
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO votes
                          (question_id, agent_key, agent_name, choice,
                           is_current, is_revoked, created_at)
                        VALUES (?, ?, ?, ?, 1, 0, ?)
                        """,
                        (
                            qid,
                            vk,
                            v.get("name", "unknown"),
                            v.get("choice", ""),
                            v.get("time", now),
                        ),
                    )
                except Exception:
                    continue

        _set_legacy_marker()

    # 迁移完成后把 db.json 改名归档（避免再次迁移）
    try:
        OLD_DB_FILE.rename(OLD_DB_FILE.with_suffix(".json.migrated"))
    except Exception:
        pass


# ---------------------------------------------------------------- 工具
def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def now_ts() -> int:
    return int(time.time())


def parse_json_field(raw: Optional[str, Any], default: Any = None) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    init_db()
    print(f"[db] initialized at {DB_FILE}")
