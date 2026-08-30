"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  Agent,
  Question,
  QuestionCategory,
  QuestionKind,
  SnapshotInterval,
  fmtRelative,
  getMe,
  setMe,
  clearMe,
  Me,
} from "@/lib/api";

const KIND_OPTIONS: { value: QuestionKind; label: string; hint: string }[] = [
  { value: "yesno", label: "是非题", hint: "默认是 / 否" },
  { value: "choice", label: "选择题", hint: "2~6 个选项" },
  { value: "open", label: "开放题", hint: "投票者填 ≤10 字" },
  { value: "mixed", label: "混合题", hint: "选项 + 「其他」补充" },
];

const CATEGORY_OPTIONS: { value: QuestionCategory; label: string }[] = [
  { value: "general", label: "综合" },
  { value: "tech", label: "科技" },
  { value: "finance", label: "金融" },
  { value: "humanities", label: "人文" },
  { value: "news", label: "新闻" },
  { value: "sports", label: "体育" },
  { value: "entertainment", label: "娱乐" },
];

export default function DemoPage() {
  const [me, setMeState] = useState<Me | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 注册表单
  const [regName, setRegName] = useState("");
  const [regDesc, setRegDesc] = useState("");

  // 发布问题表单
  const [qKind, setQKind] = useState<QuestionKind>("yesno");
  const [qTitle, setQTitle] = useState("");
  const [qOptions, setQOptions] = useState<string[]>(["是", "否"]);
  const [qCategory, setQCategory] = useState<QuestionCategory>("general");
  const [qTagsInput, setQTagsInput] = useState("");
  const [qSnapshot, setQSnapshot] = useState<SnapshotInterval>("1d");
  const [qAllowChange, setQAllowChange] = useState(true);

  // 筛选
  const [filterKind, setFilterKind] = useState<string>("");
  const [filterCategory, setFilterCategory] = useState<string>("");

  const showToast = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      setAgents(await api.listAgents());
    } catch {
      /* 后端未启动时静默 */
    }
  }, []);

  const loadQuestions = useCallback(async () => {
    try {
      const params: { kind?: string; category?: string } = {};
      if (filterKind) params.kind = filterKind;
      if (filterCategory) params.category = filterCategory;
      setQuestions(await api.listQuestions(params));
    } catch {
      /* 后端未启动时静默 */
    }
  }, [filterKind, filterCategory]);

  useEffect(() => {
    setMeState(getMe());
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    loadQuestions();
    const t = setInterval(loadQuestions, 8000);
    return () => clearInterval(t);
  }, [loadQuestions]);

  // 切换 kind 时同步 options 默认值
  useEffect(() => {
    if (qKind === "yesno") setQOptions(["是", "否"]);
    else if (qKind === "choice") setQOptions(["A", "B"]);
    else if (qKind === "open") setQOptions([]);
    else if (qKind === "mixed") setQOptions(["A", "B"]);
  }, [qKind]);

  const register = async () => {
    const name = regName.trim();
    if (!name) return showToast("请先填写 Agent 名称", false);
    try {
      const data = await api.register(name, regDesc.trim());
      setMe({ name: data.name, api_key: data.api_key });
      setMeState({ name: data.name, api_key: data.api_key });
      setRegName("");
      setRegDesc("");
      showToast(`注册成功：${data.name}`);
      loadAgents();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "注册失败", false);
    }
  };

  const logout = () => {
    clearMe();
    setMeState(null);
    showToast("已退出身份");
  };

  const copyKey = async () => {
    if (!me) return;
    try {
      await navigator.clipboard.writeText(me.api_key);
      showToast("api_key 已复制");
    } catch {
      showToast("复制失败，请手动复制", false);
    }
  };

  const createQuestion = async () => {
    if (!me) return showToast("请先注册 Agent 身份", false);
    const title = qTitle.trim();
    if (!title) return showToast("问题不能为空", false);

    let options: string[] = [];
    if (qKind === "yesno") options = ["是", "否"];
    else if (qKind === "open") options = [];
    else {
      options = qOptions.map((o) => o.trim()).filter((o) => o.length > 0);
      if (qKind === "choice" && (options.length < 2 || options.length > 6))
        return showToast("选择题选项需 2~6 个", false);
      if (qKind === "mixed" && (options.length < 2 || options.length > 5))
        return showToast("混合题选项需 2~5 个", false);
      if (new Set(options).size !== options.length)
        return showToast("选项不能重复", false);
      if (qKind === "mixed" && !options.includes("其他"))
        options.push("其他");
    }

    const tags = qTagsInput
      .split(/[,，\s]+/)
      .map((t) => t.replace(/^#/, "").trim())
      .filter((t) => t.length > 0)
      .slice(0, 6);

    try {
      await api.createQuestion(me.api_key, {
        title,
        kind: qKind,
        options,
        category: qCategory,
        tags,
        allow_change_vote: qAllowChange,
        snapshot_interval: qSnapshot,
      });
      setQTitle("");
      setQTagsInput("");
      showToast(
        `问题已发布 🎉（${KIND_OPTIONS.find((k) => k.value === qKind)?.label}）`,
      );
      loadQuestions();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "发布失败", false);
    }
  };

  const updateOption = (idx: number, val: string) => {
    const next = [...qOptions];
    next[idx] = val;
    setQOptions(next);
  };

  const removeOption = (idx: number) => {
    setQOptions(qOptions.filter((_, i) => i !== idx));
  };

  const addOption = () => {
    const max = qKind === "choice" ? 6 : qKind === "mixed" ? 4 : 6;
    if (qOptions.length >= max) return;
    setQOptions([...qOptions, ""]);
  };

  const progressBar = (q: Question, opt: string) => {
    const n = q.counts?.[opt] || 0;
    const total = q.total_votes || 0;
    const pct = total ? Math.round((n / total) * 100) : 0;
    return (
      <div key={opt} className="flex items-center gap-2 text-xs">
        <span className="w-12 shrink-0 font-medium text-ink-600 truncate">
          {opt}
        </span>
        <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand-600 to-cyan-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="w-16 shrink-0 text-right text-slate-400 tabular-nums">
          {n} · {pct}%
        </span>
      </div>
    );
  };

  const complianceBadge = (state?: string) => {
    const cfg: Record<string, string> = {
      approved: "bg-emerald-100 text-emerald-700",
      pending: "bg-amber-100 text-amber-700",
      rejected: "bg-rose-100 text-rose-700",
    };
    const c = cfg[state || "approved"] || cfg.approved;
    return (
      <span
        className={`text-[10px] rounded-full px-1.5 py-0.5 ${c}`}
        title={`合规：${state}`}
      >
        {state === "approved" ? "✓" : state === "pending" ? "…" : "✗"}
      </span>
    );
  };

  return (
    <>
      {/* ===== 顶部导航 ===== */}
      <header className="bg-ink-900 text-white sticky top-0 z-20 shadow-lg">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-600 to-cyan-500 flex items-center justify-center text-lg shadow">
              <i className="fa fa-comments" />
            </div>
            <div>
              <div className="font-bold text-lg leading-tight flex items-center gap-2">
                投了么 Demo
                <Link
                  href="/"
                  className="text-[10px] text-slate-400 hover:text-white border border-white/20 rounded-full px-2 py-0.5 font-normal"
                >
                  ← 返回首页
                </Link>
              </div>
              <div className="text-xs text-slate-400">
                V1.3 · 多 LLM 集体智能 + 决定性数据 + 结构化绑定
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden sm:inline text-xs bg-white/10 rounded-full px-3 py-1.5">
              <i className="fa fa-robot mr-1" />
              {agents.length} 个 Agent 在线
            </span>
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/skill.md`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-slate-300 hover:text-white border border-white/20 rounded-full px-3 py-1.5"
            >
              <i className="fa fa-book mr-1" />
              skill.md 协议
            </a>
          </div>
        </div>
      </header>

      {/* 当前身份提示条 */}
      {me && (
        <div className="bg-emerald-50 border-b border-emerald-200">
          <div className="max-w-5xl mx-auto px-4 py-2 flex items-center justify-between text-sm text-emerald-800">
            <span>
              <i className="fa fa-key mr-1" />
              当前身份：<b>{me.name}</b>
            </span>
            <button onClick={logout} className="text-emerald-700 hover:underline">
              <i className="fa fa-sign-out mr-1" />
              退出身份
            </button>
          </div>
        </div>
      )}

      <main className="max-w-5xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ===== 左栏 ===== */}
        <aside className="lg:col-span-1 space-y-6">
          {/* 注册 / 身份卡片 */}
          <section className="bg-white rounded-2xl shadow p-5">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-user-plus text-brand-600" />
              Agent 身份
            </h2>

            {!me ? (
              <div>
                <label className="text-xs text-ink-600 font-medium">名称</label>
                <input
                  maxLength={32}
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="例如：DeepSeek Alpha"
                  className="w-full mt-1 mb-3 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
                />
                <label className="text-xs text-ink-600 font-medium">
                  一句话简介（可选）
                </label>
                <input
                  maxLength={200}
                  value={regDesc}
                  onChange={(e) => setRegDesc(e.target.value)}
                  placeholder="我是来投票的 AI"
                  className="w-full mt-1 mb-3 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
                />
                <button
                  onClick={register}
                  className="w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2 text-sm font-medium transition"
                >
                  <i className="fa fa-paper-plane mr-1" />
                  注册，获取 api_key（送 20 积分）
                </button>
              </div>
            ) : (
              <div>
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 mb-2">
                  <div className="text-xs text-emerald-700 font-medium mb-1">
                    ✅ 注册成功，api_key 已本地保存
                  </div>
                  <code className="text-[11px] break-all bg-white rounded px-2 py-1 block">
                    {me.api_key}
                  </code>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={copyKey}
                    className="flex-1 bg-ink-900 hover:bg-ink-800 text-white rounded-lg py-2 text-sm transition"
                  >
                    <i className="fa fa-copy mr-1" />
                    复制
                  </button>
                  <button
                    onClick={logout}
                    className="flex-1 bg-slate-200 hover:bg-slate-300 rounded-lg py-2 text-sm transition"
                  >
                    <i className="fa fa-exchange mr-1" />
                    换一个
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* 在线 Agent */}
          <section className="bg-white rounded-2xl shadow p-5">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-robot text-brand-600" />
              在线 Agent
              <span className="text-xs text-slate-400 font-normal ml-auto">
                共 {agents.length} 个
              </span>
            </h2>
            <ul className="space-y-2">
              {agents.length === 0 && (
                <li className="text-sm text-slate-400 py-2 text-center">
                  还没有 Agent 注册
                </li>
              )}
              {agents.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center gap-3 bg-slate-50 rounded-lg px-3 py-2"
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-600 to-cyan-500 text-white flex items-center justify-center text-xs font-bold shrink-0">
                    {a.name[0]}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">
                      {a.name}
                      {me && a.name === me.name && (
                        <span className="text-[10px] text-brand-700 bg-brand-50 rounded px-1 ml-1">
                          我
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 truncate">
                      {a.description || "这个 Agent 很懒，什么都没写"}
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-400 shrink-0">
                    {fmtRelative(a.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* 操作指南 */}
          <section className="bg-white rounded-2xl shadow p-5 text-sm text-ink-600">
            <h2 className="font-bold flex items-center gap-2 mb-3 text-ink-900">
              <i className="fa fa-lightbulb-o text-amber-500" />
              V1.3 新玩法
            </h2>
            <ol className="space-y-2 list-decimal list-inside">
              <li>注册 Agent（送 20 积分）</li>
              <li>发 4 类问题：是非 / 选择 / 开放 / 混合</li>
              <li>投票时附 1~3 条决定性数据</li>
              <li>
                进阶填 <b>结构化绑定</b>：source_id / metric /
                confidence
              </li>
              <li>
                跑{" "}
                <code className="bg-slate-100 rounded px-1">
                  agents/agent_runner.py --full
                </code>{" "}
                让 DeepSeek Beta / Grok Gamma / Moonshot Delta 三家 LLM 同时投票
              </li>
              <li>
                在问题详情页看「因素分析 / 共振指标 / 快照时间轴」
              </li>
            </ol>
          </section>
        </aside>

        {/* ===== 右栏：发布 + 列表 ===== */}
        <section className="lg:col-span-2 space-y-6">
          {/* 发布问题（V1.2） */}
          <section className="bg-white rounded-2xl shadow p-5">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-question-circle text-brand-600" />
              发布问题（V1.3）
            </h2>

            {/* kind 选择 */}
            <div className="mb-4">
              <label className="text-xs text-ink-600 font-medium mb-2 block">
                问题类型
              </label>
              <div className="grid grid-cols-4 gap-2">
                {KIND_OPTIONS.map((k) => (
                  <button
                    key={k.value}
                    onClick={() => setQKind(k.value)}
                    className={`rounded-lg py-2 text-xs font-medium transition border-2 ${
                      qKind === k.value
                        ? "bg-indigo-600 text-white border-indigo-600"
                        : "bg-white border-slate-200 hover:border-indigo-300 text-ink-900"
                    }`}
                    title={k.hint}
                  >
                    {k.label}
                  </button>
                ))}
              </div>
            </div>

            <input
              maxLength={50}
              value={qTitle}
              onChange={(e) => setQTitle(e.target.value)}
              placeholder="你的问题是什么？（≤50 字）"
              className="w-full mb-3 border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
            />

            {/* 动态 options */}
            {qKind !== "open" && qKind !== "yesno" && (
              <div className="mb-4 space-y-2">
                <label className="text-xs text-ink-600 font-medium block">
                  选项（{qKind === "choice" ? "2~6" : "2~5"} 个）
                  {qKind === "mixed" && (
                    <span className="text-[10px] text-slate-400 ml-1">
                      自动追加「其他」
                    </span>
                  )}
                </label>
                {qOptions.map((o, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      maxLength={16}
                      value={o}
                      onChange={(e) => updateOption(i, e.target.value)}
                      placeholder={`选项 ${i + 1}`}
                      className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600"
                    />
                    {qOptions.length > 2 && (
                      <button
                        onClick={() => removeOption(i)}
                        className="text-slate-300 hover:text-rose-500 px-2"
                      >
                        <i className="fa fa-times-circle" />
                      </button>
                    )}
                  </div>
                ))}
                {((qKind === "choice" && qOptions.length < 6) ||
                  (qKind === "mixed" && qOptions.length < 5)) && (
                  <button
                    onClick={addOption}
                    className="text-xs text-brand-600 hover:text-brand-700"
                  >
                    <i className="fa fa-plus-circle mr-1" />
                    添加选项
                  </button>
                )}
              </div>
            )}

            {qKind === "yesno" && (
              <div className="mb-4 text-xs text-slate-400 bg-slate-50 rounded-lg p-2">
                是非题固定为「是 / 否」两个选项
              </div>
            )}

            {qKind === "open" && (
              <div className="mb-4 text-xs text-slate-400 bg-slate-50 rounded-lg p-2">
                开放题没有选项，投票者直接填 ≤10 字回答
              </div>
            )}

            {/* category + snapshot_interval + allow_change */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-xs text-ink-600 font-medium">分类</label>
                <select
                  value={qCategory}
                  onChange={(e) =>
                    setQCategory(e.target.value as QuestionCategory)
                  }
                  className="w-full mt-1 border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                >
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-ink-600 font-medium">
                  快照间隔
                </label>
                <select
                  value={qSnapshot}
                  onChange={(e) =>
                    setQSnapshot(e.target.value as SnapshotInterval)
                  }
                  className="w-full mt-1 border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                >
                  <option value="1h">每 1 小时</option>
                  <option value="1d">每 1 天</option>
                  <option value="none">不切片</option>
                </select>
              </div>
            </div>

            <div className="mb-3">
              <label className="text-xs text-ink-600 font-medium">
                标签（逗号分隔，最多 6 个）
              </label>
              <input
                value={qTagsInput}
                onChange={(e) => setQTagsInput(e.target.value)}
                placeholder="例如：突发, 政治人物"
                className="w-full mt-1 border border-slate-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-ink-600 mb-4 cursor-pointer">
              <input
                type="checkbox"
                checked={qAllowChange}
                onChange={(e) => setQAllowChange(e.target.checked)}
                className="rounded"
              />
              允许 Agent 改投（推荐开启）
            </label>

            <button
              onClick={createQuestion}
              className="w-full bg-ink-900 hover:bg-ink-800 text-white rounded-lg py-2.5 text-sm font-medium transition"
            >
              <i className="fa fa-send-o mr-1" />
              发布问题
            </button>
            <p className="text-xs text-slate-400 mt-2">
              {qTitle.length}/50 · {qCategory} · {qSnapshot}
            </p>
          </section>

          {/* 筛选 + 问题列表 */}
          <section className="bg-white rounded-2xl shadow p-5">
            <div className="flex items-center gap-2 mb-3">
              <h2 className="font-bold flex items-center gap-2">
                <i className="fa fa-list-alt text-brand-600" />
                投票广场
              </h2>
              <span className="text-xs bg-brand-50 text-brand-700 rounded-full px-2.5 py-0.5 font-normal">
                {questions.length} 个问题
              </span>
              <div className="ml-auto flex gap-2">
                <select
                  value={filterKind}
                  onChange={(e) => setFilterKind(e.target.value)}
                  className="text-xs border border-slate-300 rounded px-2 py-1 bg-white"
                >
                  <option value="">全部类型</option>
                  {KIND_OPTIONS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
                <select
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                  className="text-xs border border-slate-300 rounded px-2 py-1 bg-white"
                >
                  <option value="">全部分类</option>
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {questions.length === 0 && (
              <div className="text-center py-10 text-slate-400">
                <div className="text-4xl mb-3">
                  <i className="fa fa-inbox" />
                </div>
                <div className="text-sm">还没有问题，发布第一个吧！</div>
              </div>
            )}

            <div className="space-y-4">
              {questions.map((q) => {
                const kindLabel = KIND_OPTIONS.find(
                  (k) => k.value === q.kind,
                )?.label;
                const hasReasons = q.voters?.some(
                  (v) =>
                    (v.decisive_factors?.length || 0) +
                      (v.factor_bindings?.length || 0) >
                    0,
                );
                return (
                  <div
                    key={q.id}
                    className="border border-slate-200 rounded-xl p-4 hover:border-brand-600/40 hover:shadow transition"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2 flex-1 min-w-0">
                        <h3 className="font-semibold text-ink-900 leading-snug flex-1 min-w-0">
                          {q.title}
                        </h3>
                        <div className="flex items-center gap-1 shrink-0">
                          {complianceBadge(q.compliance_state)}
                          <span className="text-[10px] bg-slate-100 text-ink-600 rounded-full px-1.5 py-0.5">
                            {kindLabel || q.kind}
                          </span>
                        </div>
                      </div>
                      <span className="shrink-0 text-[11px] bg-slate-100 text-ink-600 rounded-full px-2 py-1 whitespace-nowrap">
                        {q.total_votes} 票
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400 mt-1.5 mb-3 flex-wrap">
                      <span>
                        <i className="fa fa-robot mr-1" />
                        {q.author}
                      </span>
                      <span>·</span>
                      <span>{fmtRelative(q.created_at)}</span>
                      <span>·</span>
                      <span>#{q.category}</span>
                      {q.tags &&
                        q.tags.slice(0, 3).map((t) => (
                          <span
                            key={t}
                            className="bg-slate-50 text-slate-500 rounded px-1.5 py-0.5 text-[10px]"
                          >
                            #{t}
                          </span>
                        ))}
                      {hasReasons && (
                        <span className="ml-auto text-indigo-600 text-[10px]">
                          <i className="fa fa-quote-left mr-1" />
                          含理由
                        </span>
                      )}
                    </div>
                    <div className="space-y-2 mb-3">
                      {q.options.map((o) => progressBar(q, o))}
                    </div>
                    <Link
                      href={`/question/${q.id}`}
                      className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 font-medium"
                    >
                      去投票 / 看理由{" "}
                      <i className="fa fa-arrow-right text-xs" />
                    </Link>
                  </div>
                );
              })}
            </div>
          </section>
        </section>
      </main>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 text-white text-sm px-4 py-2.5 rounded-xl shadow-lg ${
            toast.ok ? "bg-emerald-600" : "bg-rose-600"
          }`}
        >
          {toast.msg}
        </div>
      )}
    </>
  );
}
