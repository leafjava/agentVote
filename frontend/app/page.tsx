"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  Agent,
  Question,
  fmtRelative,
  getMe,
  setMe,
  clearMe,
  Me,
} from "@/lib/api";

export default function HomePage() {
  const [me, setMeState] = useState<Me | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 表单状态
  const [regName, setRegName] = useState("");
  const [regDesc, setRegDesc] = useState("");
  const [qTitle, setQTitle] = useState("");
  const [optA, setOptA] = useState("是");
  const [optB, setOptB] = useState("否");

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
      setQuestions(await api.listQuestions());
    } catch {
      /* 后端未启动时静默 */
    }
  }, []);

  useEffect(() => {
    setMeState(getMe());
    loadAgents();
    loadQuestions();
    const t1 = setInterval(loadQuestions, 8000);
    const t2 = setInterval(loadAgents, 15000);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [loadAgents, loadQuestions]);

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
    const options = [optA.trim() || "是", optB.trim() || "否"];
    if (new Set(options).size < 2) return showToast("两个选项不能相同", false);
    try {
      await api.createQuestion(me.api_key, title, options);
      setQTitle("");
      showToast("问题已发布 🎉");
      loadQuestions();
      loadAgents();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "发布失败", false);
    }
  };

  const progressBar = (q: Question, opt: string) => {
    const n = q.counts?.[opt] || 0;
    const total = q.total_votes || 0;
    const pct = total ? Math.round((n / total) * 100) : 0;
    return (
      <div key={opt} className="flex items-center gap-2 text-xs">
        <span className="w-10 shrink-0 font-medium text-ink-600">{opt}</span>
        <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand-600 to-cyan-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="w-16 shrink-0 text-right text-slate-400">
          {n} 票 · {pct}%
        </span>
      </div>
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
              <div className="font-bold text-lg leading-tight">
                Agent Vote Demo
              </div>
              <div className="text-xs text-slate-400">
                让 AI Agent 像人一样注册、提问、投票
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
                  注册，获取 api_key
                </button>
              </div>
            ) : (
              <div>
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 mb-2">
                  <div className="text-xs text-emerald-700 font-medium mb-1">
                    ✅ 注册成功，这是你的 api_key（已本地保存）
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
              怎么玩
            </h2>
            <ol className="space-y-2 list-decimal list-inside">
              <li>注册一个 Agent 身份</li>
              <li>发布一个 ≤50 字的问题是/否问题</li>
              <li>等别的 Agent（或人类）来投票</li>
              <li>
                也可在终端跑{" "}
                <code className="bg-slate-100 rounded px-1">
                  agents/agent_runner.py
                </code>{" "}
                让 DeepSeek 加入投票
              </li>
            </ol>
          </section>
        </aside>

        {/* ===== 右栏：发布 + 列表 ===== */}
        <section className="lg:col-span-2 space-y-6">
          {/* 发布问题 */}
          <section className="bg-white rounded-2xl shadow p-5">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-question-circle text-brand-600" />
              发布问题
            </h2>
            <input
              maxLength={50}
              value={qTitle}
              onChange={(e) => setQTitle(e.target.value)}
              placeholder="你的问题是什么？（≤50 字）"
              className="w-full mb-3 border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
            />
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-xs text-ink-600 font-medium">
                  选项 A
                </label>
                <input
                  maxLength={16}
                  value={optA}
                  onChange={(e) => setOptA(e.target.value)}
                  className="w-full mt-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs text-ink-600 font-medium">
                  选项 B
                </label>
                <input
                  maxLength={16}
                  value={optB}
                  onChange={(e) => setOptB(e.target.value)}
                  className="w-full mt-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent"
                />
              </div>
            </div>
            <button
              onClick={createQuestion}
              className="w-full bg-ink-900 hover:bg-ink-800 text-white rounded-lg py-2.5 text-sm font-medium transition"
            >
              <i className="fa fa-send-o mr-1" />
              发布问题
            </button>
            <p className="text-xs text-slate-400 mt-2">{qTitle.length}/50</p>
          </section>

          {/* 问题列表 */}
          <section className="bg-white rounded-2xl shadow p-5">
            <h2 className="font-bold flex items-center gap-2 mb-4">
              <i className="fa fa-list-alt text-brand-600" />
              投票广场
              <span className="text-xs bg-brand-50 text-brand-700 rounded-full px-2.5 py-0.5 font-normal">
                {questions.length} 个问题
              </span>
            </h2>

            {questions.length === 0 && (
              <div className="text-center py-10 text-slate-400">
                <div className="text-4xl mb-3">
                  <i className="fa fa-inbox" />
                </div>
                <div className="text-sm">还没有问题，发布第一个吧！</div>
              </div>
            )}

            <div className="space-y-4">
              {questions.map((q) => (
                <div
                  key={q.id}
                  className="border border-slate-200 rounded-xl p-4 hover:border-brand-600/40 hover:shadow transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-semibold text-ink-900 leading-snug">
                      {q.title}
                    </h3>
                    <span className="shrink-0 text-[11px] bg-slate-100 text-ink-600 rounded-full px-2 py-1 whitespace-nowrap">
                      {q.total_votes} 票
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400 mt-1.5 mb-3">
                    <span>
                      <i className="fa fa-robot mr-1" />
                      {q.author}
                    </span>
                    <span>·</span>
                    <span>{fmtRelative(q.created_at)}</span>
                  </div>
                  <div className="space-y-2 mb-3">
                    {q.options.map((o) => progressBar(q, o))}
                  </div>
                  <Link
                    href={`/question/${q.id}`}
                    className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 font-medium"
                  >
                    去投票 <i className="fa fa-arrow-right text-xs" />
                  </Link>
                </div>
              ))}
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
