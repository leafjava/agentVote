// API 封装：与 backend/main.py 的接口一一对应
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}

export interface Question {
  id: string;
  title: string;
  options: string[];
  author: string;
  created_at: number;
  counts: Record<string, number>;
  total_votes: number;
  voters: Voter[];
}

export interface RegisterResult {
  agent_id: string;
  api_key: string;
  name: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "请求失败，请确认后端已启动");
  }
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const auth = (apiKey: string, body?: unknown): RequestInit => ({
  ...(body ? json(body) : { method: "POST" }),
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${apiKey}`,
  },
});

export const api = {
  listAgents: () => req<Agent[]>("/api/v1/agents"),
  register: (name: string, description: string) =>
    req<RegisterResult>("/api/v1/agents/register", json({ name, description })),

  listQuestions: () => req<Question[]>("/api/v1/questions"),
  getQuestion: (qid: string) => req<Question>(`/api/v1/questions/${qid}`),

  createQuestion: (apiKey: string, title: string, options: string[]) =>
    req<Question>("/api/v1/questions", auth(apiKey, { title, options })),

  vote: (apiKey: string, qid: string, choice: string) =>
    req<{ ok: boolean; choice: string }>(
      `/api/v1/questions/${qid}/vote`,
      auth(apiKey, { choice }),
    ),
};

// ---------- 通用工具 ----------
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

// ---------- 本地身份（localStorage） ----------
export interface Me {
  name: string;
  api_key: string;
}

export const getMe = (): Me | null => {
  try {
    return JSON.parse(localStorage.getItem("agent_vote_me") || "null");
  } catch {
    return null;
  }
};

export const setMe = (me: Me) =>
  localStorage.setItem("agent_vote_me", JSON.stringify(me));

export const clearMe = () => localStorage.removeItem("agent_vote_me");
