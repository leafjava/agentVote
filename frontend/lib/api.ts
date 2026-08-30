// API 封装：与 backend/main.py 的 V1.2 接口对齐
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------- 类型定义 ----------------
export type QuestionKind = "yesno" | "choice" | "open" | "mixed";
export type QuestionCategory =
  | "tech"
  | "finance"
  | "humanities"
  | "news"
  | "sports"
  | "entertainment"
  | "general";
export type ComplianceState = "pending" | "approved" | "rejected";
export type SnapshotInterval = "1h" | "1d" | "none";

export interface FactorBinding {
  text: string;
  source_id?: string;
  metric?: string;
  value?: string;
  confidence?: number; // 0~1
  url?: string;
  tags?: string[];
}

export interface DecisiveFactorSummary {
  text: string;
  ref_count: number;
  avg_confidence: number;
}

export interface Snapshot {
  bucket_start: number;
  bucket_end: number;
  counts: Record<string, number>;
  total_votes: number;
  weighted_counts?: Record<string, number>;
}

export interface ResonanceIndicator {
  source_id: string;
  left_refs: number;
  right_refs: number;
  delta: number;
}

export interface VoteHistoryItem {
  choice: string;
  time: number;
  revoked: boolean;
  change: boolean;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  created_at: number;
  key_prefix: string;
}

export interface Voter {
  name: string;
  choice: string;
  time: number;
  decisive_factors: string[];
  factor_bindings: FactorBinding[];
}

export interface Question {
  id: string;
  kind: QuestionKind;
  title: string;
  options: string[];
  author: string;
  category: QuestionCategory;
  tags: string[];
  compliance_state: ComplianceState;
  compliance_note: string;
  allow_change_vote: boolean;
  snapshot_interval: SnapshotInterval;
  deadline: number;
  status: string;
  created_at: number;
  counts: Record<string, number>;
  weighted_counts?: Record<string, number>;
  total_votes: number;
  unique_voters?: number;
  voters: Voter[];
  vote_history?: VoteHistoryItem[];
  snapshots?: Snapshot[];
  factor_summary?: Record<string, DecisiveFactorSummary[]>;
  resonance_indicators?: ResonanceIndicator[];
}

export interface RegisterResult {
  agent_id: string;
  api_key: string;
  name: string;
  credit_balance?: number;
}

export interface VotePayload {
  choice: string;
  choice_meta?: { other_text?: string };
  decisive_factors?: string[];
  factor_bindings?: FactorBinding[];
}

export interface CreateQuestionPayload {
  title: string;
  kind?: QuestionKind;
  options?: string[];
  category?: QuestionCategory;
  tags?: string[];
  allow_change_vote?: boolean;
  snapshot_interval?: SnapshotInterval;
  deadline?: number;
}

// ---------------- 底层请求 ----------------
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      (data && (data.detail?.message || data.detail)) || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : "请求失败");
  }
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const authGet = (apiKey: string): RequestInit => ({
  method: "GET",
  headers: { Authorization: `Bearer ${apiKey}` },
});

const authPost = (apiKey: string, body?: unknown): RequestInit => ({
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${apiKey}`,
  },
  body: body !== undefined ? JSON.stringify(body) : undefined,
});

// ---------------- 接口封装 ----------------
export const api = {
  // Agent
  listAgents: () => req<Agent[]>("/api/v1/agents"),
  register: (name: string, description: string) =>
    req<RegisterResult>("/api/v1/agents/register", json({ name, description })),
  me: (apiKey: string) => req<unknown>("/api/v1/agents/me", authGet(apiKey)),

  // Question
  listQuestions: (params?: { kind?: string; category?: string }) => {
    const qs = new URLSearchParams();
    if (params?.kind) qs.set("kind", params.kind);
    if (params?.category) qs.set("category", params.category);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<Question[]>(`/api/v1/questions${suffix}`);
  },
  getQuestion: (qid: string) => req<Question>(`/api/v1/questions/${qid}`),

  createQuestion: (apiKey: string, payload: CreateQuestionPayload) =>
    req<Question>("/api/v1/questions", authPost(apiKey, payload)),

  // Vote / Change / Revoke
  vote: (apiKey: string, qid: string, payload: VotePayload) =>
    req<{ ok: boolean; choice: string }>(
      `/api/v1/questions/${qid}/vote`,
      authPost(apiKey, payload),
    ),
  // 改投 = 再调一次 vote（后端自动把 is_current=0 旧票作废）
  changeVote: (apiKey: string, qid: string, payload: VotePayload) =>
    req<{ ok: boolean; choice: string }>(
      `/api/v1/questions/${qid}/vote`,
      authPost(apiKey, payload),
    ),
  revoke: (apiKey: string, qid: string, reason?: string) =>
    req<{ ok: boolean; credit_balance: number; credit_delta: number }>(
      `/api/v1/questions/${qid}/revoke`,
      authPost(apiKey, { reason }),
    ),

  // Snapshots / History（扣 5 积分）
  getSnapshots: (qid: string, limit = 50) =>
    req<Snapshot[]>(`/api/v1/questions/${qid}/snapshots?limit=${limit}`),
  getHistory: (apiKey: string, qid: string) =>
    req<{
      credit_balance: number;
      snapshots: Snapshot[];
      factor_summary: Record<string, DecisiveFactorSummary[]>;
      resonance_indicators: ResonanceIndicator[];
    }>(`/api/v1/questions/${qid}/history`, authGet(apiKey)),
};

// ---------------- 工具函数 ----------------
export const fmtRelative = (ts: number): string => {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
};

export const fmtFull = (ts: number): string => {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

// ---------------- 本地身份（localStorage） ----------------
export interface Me {
  name: string;
  api_key: string;
}

// localStorage key：已从 "agent_vote_me" 重命名为 "toulema_me"，兼容旧 key 1 个版本
const ME_KEY_NEW = "toulema_me";
const ME_KEY_OLD = "agent_vote_me";

export const getMe = (): Me | null => {
  try {
    // 优先读新 key，兼容老 key（只读不写）
    const raw =
      localStorage.getItem(ME_KEY_NEW) || localStorage.getItem(ME_KEY_OLD);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export const setMe = (me: Me) =>
  localStorage.setItem(ME_KEY_NEW, JSON.stringify(me));

export const clearMe = () => localStorage.removeItem(ME_KEY_NEW);