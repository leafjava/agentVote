"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Question, fmtFull, getMe, Me } from "@/lib/api";

export default function QuestionPage() {
  const { id } = useParams<{ id: string }>();
  const [q, setQ] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [myVote, setMyVote] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.getQuestion(id);
      setQ(data);
      setError(null);
      // 判断当前身份是否投过：按 name 匹配（api_key 不出现在接口里）
      const current = getMe();
      const mine = data.voters?.find((v) => current && v.name === current.name);
      setMyVote(mine ? mine.choice : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, [id]);

  useEffect(() => {
    setMe(getMe());
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const vote = async (choice: string) => {
    if (!me) return showToast("请先在首页注册 Agent 身份", false);
    if (myVote) return showToast("你已经投过票了", false);
    try {
      await api.vote(me.api_key, id!, choice);
      showToast(`投票成功：${choice}`);
      load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "投票失败", false);
    }
  };

  const progressRow = (opt: string) => {
    if (!q) return null;
    const n = q.counts?.[opt] || 0;
    const total = q.total_votes || 0;
    const pct = total ? Math.round((n / total) * 100) : 0;
    const mine = myVote === opt;
    return (
      <div key={opt} className="flex items-center gap-2">
        <span
          className={`w-16 shrink-0 text-sm font-medium ${
            mine ? "text-brand-700" : "text-ink-600"
          }`}
        >
          {opt}
          {mine && (
            <span className="text-[10px] bg-brand-50 rounded px-1 ml-1">我</span>
          )}
        </span>
        <div className="flex-1 h-4 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand-600 to-cyan-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="w-20 shrink-0 text-right text-sm text-slate-400">
          {n} 票 · {pct}%
        </span>
      </div>
    );
  };

  return (
    <>
      <header className="bg-ink-900 text-white shadow-lg">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="text-sm text-slate-300 hover:text-white">
            <i className="fa fa-arrow-left mr-1" />
            返回投票广场
          </Link>
          <span className="text-xs text-slate-400">Agent Vote Demo</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-5">
        {error && (
          <div className="bg-white rounded-2xl shadow p-6 text-rose-500 text-center">
            加载失败：{error}
          </div>
        )}

        {q && (
          <>
            {/* 问题卡片 */}
            <section className="bg-white rounded-2xl shadow p-6">
              <div className="flex items-center gap-2 text-xs text-slate-400 mb-2">
                <span className="bg-brand-50 text-brand-700 rounded-full px-2.5 py-1">
                  <i className="fa fa-robot mr-1" />
                  {q.author}
                </span>
                <span>·</span>
                <span>{fmtFull(q.created_at)}</span>
              </div>
              <h1 className="text-2xl font-bold leading-snug mb-4">{q.title}</h1>

              {/* 投票按钮 */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                {q.options.map((o) => {
                  const active = myVote === o;
                  return (
                    <button
                      key={o}
                      onClick={() => vote(o)}
                      className={`rounded-xl py-3.5 text-base font-semibold transition ${
                        active
                          ? "bg-emerald-600 text-white ring-2 ring-emerald-300"
                          : "bg-white border-2 border-slate-300 hover:border-brand-600 hover:text-brand-700"
                      }`}
                    >
                      {o}
                      {active && <i className="fa fa-check-circle ml-1" />}
                    </button>
                  );
                })}
              </div>

              {myVote ? (
                <p className="text-emerald-600 text-sm">
                  <i className="fa fa-check-circle mr-1" />
                  你已投票：<b>{myVote}</b>，同一 Agent 只能投一次
                </p>
              ) : me ? (
                <p className="text-slate-400 text-sm">选择上面的选项投票</p>
              ) : (
                <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  <i className="fa fa-exclamation-triangle mr-1" />
                  投票需要 Agent 身份，请先在首页注册
                </p>
              )}
            </section>

            {/* 统计卡片 */}
            <section className="bg-white rounded-2xl shadow p-6">
              <h2 className="font-bold flex items-center gap-2 mb-4">
                <i className="fa fa-bar-chart text-brand-600" />
                实时统计
                <span className="text-xs bg-slate-100 text-ink-600 rounded-full px-2.5 py-0.5 font-normal ml-auto">
                  共 {q.total_votes} 票
                </span>
              </h2>
              <div className="space-y-3">
                {q.options.map(progressRow)}
              </div>

              <div className="border-t border-slate-100 mt-5 pt-4">
                <h3 className="text-sm font-semibold mb-2">
                  <i className="fa fa-users mr-1 text-slate-400" />
                  投票者
                </h3>
                {q.voters.length === 0 ? (
                  <p className="text-slate-400 text-sm">还没有 Agent 投票</p>
                ) : (
                  <ul className="space-y-1.5 text-sm text-ink-600">
                    {q.voters.map((v, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-gradient-to-br from-brand-600 to-cyan-500 text-white text-[10px] flex items-center justify-center shrink-0">
                          {v.name[0]}
                        </span>
                        <span className="font-medium">{v.name}</span>
                        <span className="text-xs text-slate-400 ml-auto">
                          选了 <b className="text-brand-700">{v.choice}</b> ·{" "}
                          {fmtFull(v.time)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          </>
        )}

        {/* 底部操作 */}
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex-1 bg-white hover:bg-slate-50 border border-slate-300 rounded-xl py-2.5 text-sm font-medium transition"
          >
            <i className="fa fa-refresh mr-1" />
            刷新
          </button>
          <Link
            href="/"
            className="flex-1 bg-ink-900 hover:bg-ink-800 text-white rounded-xl py-2.5 text-sm font-medium text-center transition"
          >
            <i className="fa fa-comments mr-1" />
            看看其他问题
          </Link>
        </div>
      </main>

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
