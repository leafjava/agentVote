"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  Question,
  FactorBinding,
  fmtFull,
  fmtRelative,
  getMe,
  Me,
} from "@/lib/api";

// ---------------- 子组件 ----------------

// 置信度等级映射（与 V1.3 A/B/C/D 等级对齐）
type ConfidenceGrade = "A" | "B" | "C" | "D";
function getConfidenceGrade(v?: number): {
  grade: ConfidenceGrade | "-";
  bg: string;
  ring: string;
} {
  if (typeof v !== "number") return { grade: "-", bg: "bg-slate-100", ring: "ring-slate-200" };
  if (v >= 0.9) return { grade: "A", bg: "bg-emerald-100", ring: "ring-emerald-300" };
  if (v >= 0.75) return { grade: "B", bg: "bg-blue-100", ring: "ring-blue-300" };
  if (v >= 0.5) return { grade: "C", bg: "bg-amber-100", ring: "ring-amber-300" };
  return { grade: "D", bg: "bg-rose-100", ring: "ring-rose-300" };
}

// 4 档置信度筛选器（与 V1.3 等级映射对齐）
function ConfidenceFilter({
  value,
  onChange,
  passedCount,
  totalCount,
}: {
  value: number;
  onChange: (v: number) => void;
  passedCount: number;
  totalCount: number;
}) {
  const opts: { v: number; label: string; tip: string }[] = [
    { v: 0, label: "全部", tip: "不过滤" },
    { v: 0.5, label: "≥ 0.5", tip: "C 级及以上" },
    { v: 0.75, label: "≥ 0.75", tip: "B 级及以上" },
    { v: 0.9, label: "≥ 0.9", tip: "A 级" },
  ];
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <span className="text-[11px] text-slate-500 font-medium">
        <i className="fa fa-filter mr-1 text-slate-400" />
        置信度筛选
      </span>
      <div className="inline-flex rounded-lg border border-slate-200 bg-white overflow-hidden">
        {opts.map((o, i) => {
          const active = value === o.v;
          return (
            <button
              key={o.v}
              onClick={() => onChange(o.v)}
              title={o.tip}
              className={`px-3 py-1.5 text-xs font-medium transition ${
                active
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-slate-600 hover:bg-slate-50"
              } ${i > 0 ? "border-l border-slate-200" : ""}`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      <span className="text-[11px] text-slate-400 tabular-nums">
        通过 {passedCount} / {totalCount}
      </span>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color =
    value >= 0.75
      ? "from-emerald-500 to-emerald-400"
      : value >= 0.45
        ? "from-amber-500 to-amber-400"
        : "from-rose-500 to-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r ${color} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] text-slate-500 w-9 text-right tabular-nums">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function FactorBindingCard({
  b,
  threshold = 0,
}: {
  b: FactorBinding;
  threshold?: number;
}) {
  const conf = typeof b.confidence === "number" ? b.confidence : undefined;
  const grade = getConfidenceGrade(conf);
  const passes = threshold === 0 || (conf !== undefined && conf >= threshold);
  const isFiltered = !passes && threshold > 0;

  return (
    <div
      className={`border rounded-lg p-3 text-xs space-y-1.5 transition ${
        isFiltered
          ? "border-slate-200 bg-slate-50 opacity-40"
          : "border-indigo-200 bg-indigo-50/40"
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="font-medium text-ink-900 leading-relaxed flex-1">
          {b.text}
        </div>
        {grade.grade !== "-" && (
          <span
            title={`证据等级 ${grade.grade}（confidence ${(conf ?? 0).toFixed(2)}）`}
            className={`shrink-0 w-6 h-6 rounded-md ${grade.bg} ring-1 ${grade.ring} text-[11px] font-bold flex items-center justify-center ${
              grade.grade === "A"
                ? "text-emerald-700"
                : grade.grade === "B"
                  ? "text-blue-700"
                  : grade.grade === "C"
                    ? "text-amber-700"
                    : "text-rose-700"
            }`}
          >
            {grade.grade}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-slate-600">
        {b.source_id && (
          <div className="col-span-2">
            <span className="text-slate-400">source</span>{" "}
            <code className="bg-white rounded px-1 py-0.5 text-[11px] text-indigo-700">
              {b.source_id}
            </code>
          </div>
        )}
        {b.metric && (
          <div className="truncate">
            <span className="text-slate-400">metric</span>{" "}
            <span className="text-ink-900">{b.metric}</span>
          </div>
        )}
        {b.value !== undefined && (
          <div className="truncate">
            <span className="text-slate-400">value</span>{" "}
            <span className="text-ink-900">{b.value}</span>
          </div>
        )}
        {typeof b.confidence === "number" && (
          <div className="col-span-2 pt-1">
            <div className="text-slate-400 mb-1">confidence</div>
            <ConfidenceBar value={b.confidence} />
          </div>
        )}
        {b.url && (
          <div className="col-span-2 truncate">
            <i className="fa fa-link text-slate-400 mr-1" />
            <a
              href={b.url}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 hover:underline"
            >
              {b.url}
            </a>
          </div>
        )}
        {b.tags && b.tags.length > 0 && (
          <div className="col-span-2 flex flex-wrap gap-1 pt-1">
            {b.tags.map((t) => (
              <span
                key={t}
                className="bg-white text-slate-500 rounded px-1.5 py-0.5 text-[10px] border border-slate-200"
              >
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>
      {isFiltered && (
        <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-200">
          <i className="fa fa-eye-slash mr-1" />
          未通过 {threshold} 阈值筛选
        </div>
      )}
    </div>
  );
}

function DecisiveFactorList({ factors }: { factors: string[] }) {
  if (!factors || factors.length === 0)
    return (
      <p className="text-xs text-slate-400 italic">未填决定性数据</p>
    );
  return (
    <ul className="space-y-1 text-sm text-ink-900">
      {factors.map((f, i) => (
        <li key={i} className="flex items-start gap-2">
          <i className="fa fa-quote-left text-[10px] text-indigo-400 mt-1.5 shrink-0" />
          <span>{f}</span>
        </li>
      ))}
    </ul>
  );
}

function ResonanceRow({
  indicator,
  options,
}: {
  indicator: { source_id: string; left_refs: number; right_refs: number; delta: number };
  options: string[];
}) {
  const total = indicator.left_refs + indicator.right_refs;
  const leftPct = total ? (indicator.left_refs / total) * 100 : 0;
  const rightPct = total ? (indicator.right_refs / total) * 100 : 0;
  return (
    <div className="border border-slate-200 rounded-lg p-3 bg-slate-50/40">
      <div className="flex items-center justify-between text-xs mb-2">
        <code className="bg-white rounded px-1.5 py-0.5 text-indigo-700 truncate max-w-[60%]">
          {indicator.source_id}
        </code>
        <span
          className={`tabular-nums font-semibold ${
            indicator.delta > 0
              ? "text-indigo-700"
              : indicator.delta < 0
                ? "text-pink-700"
                : "text-slate-500"
          }`}
        >
          Δ {indicator.delta > 0 ? "+" : ""}
          {indicator.delta}
        </span>
      </div>
      <div className="space-y-1 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-14 shrink-0 text-slate-500 truncate">
            {options[0] ?? "A"}
          </span>
          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-indigo-300 transition-all duration-500"
              style={{ width: `${leftPct}%` }}
            />
          </div>
          <span className="w-8 text-right tabular-nums text-slate-600">
            {indicator.left_refs}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-14 shrink-0 text-slate-500 truncate">
            {options[1] ?? "B"}
          </span>
          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-pink-500 to-pink-300 transition-all duration-500"
              style={{ width: `${rightPct}%` }}
            />
          </div>
          <span className="w-8 text-right tabular-nums text-slate-600">
            {indicator.right_refs}
          </span>
        </div>
      </div>
    </div>
  );
}

function SnapshotTimeline({
  snapshots,
  options,
}: {
  snapshots: NonNullable<Question["snapshots"]>;
  options: string[];
}) {
  if (snapshots.length === 0)
    return <p className="text-sm text-slate-400">暂无快照</p>;
  // 从旧到新
  const ordered = [...snapshots].sort((a, b) => a.bucket_end - b.bucket_end);
  const last = ordered[ordered.length - 1];
  return (
    <div className="space-y-2">
      {ordered.map((s, i) => {
        const isLast = i === ordered.length - 1;
        const top = options
          .map((o) => [o, s.counts[o] ?? 0] as const)
          .sort((a, b) => b[1] - a[1])[0];
        return (
          <div
            key={s.bucket_end}
            className={`flex items-center gap-3 text-xs ${isLast ? "font-semibold" : ""}`}
          >
            <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-[10px] shrink-0">
              {i + 1}
            </span>
            <span className="w-24 shrink-0 text-slate-500">
              {fmtRelative(s.bucket_end)}
            </span>
            <span className="flex-1 text-ink-900 truncate">
              {top[0]}{" "}
              <span className="text-slate-500 font-normal">
                {top[1]} 票 · 共 {s.total_votes}
              </span>
            </span>
          </div>
        );
      })}
      {last && (
        <p className="text-[11px] text-slate-400 pl-9 pt-1">
          最新快照 · {fmtFull(last.bucket_end)} · 快照间隔自动写入
        </p>
      )}
    </div>
  );
}

function FactorSummaryPanel({
  summary,
  options,
  threshold = 0,
}: {
  summary: NonNullable<Question["factor_summary"]>;
  options: string[];
  threshold?: number;
}) {
  const hasAny = options.some((o) => (summary[o] || []).length > 0);
  if (!hasAny)
    return (
      <p className="text-sm text-slate-400">
        暂无决定性数据（投票时填写 decisive_factors / factor_bindings 即可生成）
      </p>
    );
  // 统计筛选通过 / 总数
  let passed = 0;
  let total = 0;
  options.forEach((o) => {
    (summary[o] || []).forEach((it) => {
      total += 1;
      if (threshold === 0 || (it.avg_confidence || 0) >= threshold) {
        passed += 1;
      }
    });
  });

  return (
    <div className="space-y-3">
      {options.map((opt) => {
        const items = summary[opt] || [];
        if (items.length === 0) return null;
        return (
          <div key={opt}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xs font-semibold text-ink-900">
                {opt}
              </span>
              <span className="text-[10px] text-slate-400">
                {items.length} 条因素
              </span>
            </div>
            <ul className="space-y-1.5">
              {items.map((it, i) => {
                const conf = it.avg_confidence || 0;
                const passes =
                  threshold === 0 || conf >= threshold;
                const isFiltered = !passes && threshold > 0;
                const grade = getConfidenceGrade(conf);
                return (
                  <li
                    key={i}
                    className={`flex items-center gap-2 text-xs text-ink-900 transition ${
                      isFiltered ? "opacity-40" : ""
                    }`}
                  >
                    <i className="fa fa-lightbulb-o text-amber-500 shrink-0" />
                    <span className="flex-1 truncate" title={it.text}>
                      {it.text}
                    </span>
                    <span className="text-[10px] text-slate-400 shrink-0 tabular-nums">
                      ×{it.ref_count}
                    </span>
                    <span
                      title={`证据等级 ${grade.grade}（avg_confidence ${conf.toFixed(2)}）`}
                      className={`shrink-0 w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center ${grade.bg} ${
                        grade.grade === "A"
                          ? "text-emerald-700"
                          : grade.grade === "B"
                            ? "text-blue-700"
                            : grade.grade === "C"
                              ? "text-amber-700"
                              : "text-rose-700"
                      }`}
                    >
                      {grade.grade}
                    </span>
                    <span className="w-16 shrink-0">
                      <ConfidenceBar value={conf} />
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      {threshold > 0 && passed < total && (
        <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <i className="fa fa-info-circle mr-1" />
          当前阈值 {threshold} 下隐藏了 {total - passed} 条低置信度因素（共 {total} 条）。
          <span className="text-slate-500 ml-1">
            这正是 V1.3 数据净化的前置呈现 —— 模拟"自动降权"前的可视化。
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------- 投票弹层 ----------------
interface VoteDialogProps {
  open: boolean;
  options: string[];
  kind: Question["kind"];
  initialChoice?: string;
  onClose: () => void;
  onSubmit: (payload: {
    choice: string;
    choice_meta?: { other_text?: string };
    decisive_factors: string[];
    factor_bindings: FactorBinding[];
  }) => Promise<void>;
}

function VoteDialog({
  open,
  options,
  kind,
  initialChoice,
  onClose,
  onSubmit,
}: VoteDialogProps) {
  const [choice, setChoice] = useState(initialChoice || options[0]);
  const [otherText, setOtherText] = useState("");
  const [factors, setFactors] = useState<string[]>([""]);
  const [bindings, setBindings] = useState<FactorBinding[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const showOther = kind === "mixed" && choice === "其他";

  useEffect(() => {
    if (open) {
      setChoice(initialChoice || options[0]);
      setOtherText("");
      setFactors([""]);
      setBindings([]);
      setErr(null);
    }
  }, [open, initialChoice, options]);

  if (!open) return null;

  const submit = async () => {
    setErr(null);
    const cleanFactors = factors
      .map((f) => f.trim())
      .filter((f) => f.length > 0)
      .slice(0, 3);
    if (cleanFactors.some((f) => f.length > 100)) {
      setErr("决定性数据单条不能超过 100 字");
      return;
    }
    if (showOther && otherText.trim().length > 10) {
      setErr("「其他」补充不能超过 10 字");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({
        choice: showOther ? "其他" : choice,
        choice_meta: showOther ? { other_text: otherText.trim() } : undefined,
        decisive_factors: cleanFactors,
        factor_bindings: bindings.filter(
          (b) => b.text && b.text.trim().length > 0,
        ),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-ink-900">
            <i className="fa fa-pencil-square-o text-brand-600 mr-2" />
            投票 + 附带决定性数据
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
          >
            <i className="fa fa-times" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* 选项 */}
          <div>
            <label className="text-xs font-semibold text-ink-600 mb-2 block">
              选项（必选）
            </label>
            <div className="grid grid-cols-2 gap-2">
              {options.map((o) => (
                <button
                  key={o}
                  onClick={() => setChoice(o)}
                  className={`rounded-lg py-2 text-sm font-medium transition border-2 ${
                    choice === o
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white border-slate-200 hover:border-indigo-300 text-ink-900"
                  }`}
                >
                  {o}
                </button>
              ))}
            </div>
            {showOther && (
              <input
                value={otherText}
                onChange={(e) => setOtherText(e.target.value)}
                maxLength={10}
                placeholder="补充 ≤10 字"
                className="w-full mt-2 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600"
              />
            )}
          </div>

          {/* 决定性数据 */}
          <div>
            <label className="text-xs font-semibold text-ink-600 mb-2 block">
              决定性数据（1~3 条，每条 ≤100 字）
            </label>
            <div className="space-y-2">
              {factors.map((f, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <span className="text-[10px] text-slate-400 mt-2.5 w-4 shrink-0">
                    {i + 1}.
                  </span>
                  <input
                    value={f}
                    onChange={(e) => {
                      const next = [...factors];
                      next[i] = e.target.value;
                      setFactors(next);
                    }}
                    maxLength={100}
                    placeholder="例如：现场图显示左脚先触地"
                    className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600"
                  />
                  <span className="text-[10px] text-slate-400 mt-2.5 shrink-0 tabular-nums">
                    {f.length}/100
                  </span>
                  {factors.length > 1 && (
                    <button
                      onClick={() =>
                        setFactors(factors.filter((_, j) => j !== i))
                      }
                      className="text-slate-300 hover:text-rose-500 mt-1.5"
                    >
                      <i className="fa fa-times-circle" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            {factors.length < 3 && (
              <button
                onClick={() => setFactors([...factors, ""])}
                className="mt-2 text-xs text-brand-600 hover:text-brand-700"
              >
                <i className="fa fa-plus-circle mr-1" />
                添加一条
              </button>
            )}
          </div>

          {/* 结构化绑定（高级，可选） */}
          <details className="border border-slate-200 rounded-lg">
            <summary className="px-3 py-2 cursor-pointer text-xs font-semibold text-ink-600 select-none">
              <i className="fa fa-database mr-1 text-indigo-500" />
              结构化绑定（高级，可选）— 让别人看到 source_id / confidence
            </summary>
            <div className="p-3 space-y-3 border-t border-slate-100">
              {bindings.length === 0 && (
                <p className="text-xs text-slate-400">
                  还没添加。添加后可挂数据源、指标、数值、置信度、链接。
                </p>
              )}
              {bindings.map((b, i) => (
                <div
                  key={i}
                  className="border border-indigo-100 bg-indigo-50/30 rounded-lg p-3 space-y-2"
                >
                  <div className="flex gap-2">
                    <input
                      value={b.text}
                      onChange={(e) => {
                        const next = [...bindings];
                        next[i] = { ...b, text: e.target.value };
                        setBindings(next);
                      }}
                      placeholder="绑定到上面哪条决定性数据"
                      className="flex-1 border border-slate-300 rounded px-2 py-1.5 text-xs"
                    />
                    <button
                      onClick={() =>
                        setBindings(bindings.filter((_, j) => j !== i))
                      }
                      className="text-slate-300 hover:text-rose-500"
                    >
                      <i className="fa fa-times-circle" />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      value={b.source_id || ""}
                      onChange={(e) => {
                        const next = [...bindings];
                        next[i] = { ...b, source_id: e.target.value };
                        setBindings(next);
                      }}
                      placeholder="source_id (如 src_reuters)"
                      className="border border-slate-300 rounded px-2 py-1.5 text-xs"
                    />
                    <input
                      value={b.metric || ""}
                      onChange={(e) => {
                        const next = [...bindings];
                        next[i] = { ...b, metric: e.target.value };
                        setBindings(next);
                      }}
                      placeholder="metric (如 first_contact_foot)"
                      className="border border-slate-300 rounded px-2 py-1.5 text-xs"
                    />
                    <input
                      value={b.value || ""}
                      onChange={(e) => {
                        const next = [...bindings];
                        next[i] = { ...b, value: e.target.value };
                        setBindings(next);
                      }}
                      placeholder="value (如 left)"
                      className="border border-slate-300 rounded px-2 py-1.5 text-xs"
                    />
                    <input
                      type="number"
                      step="0.01"
                      min={0}
                      max={1}
                      value={b.confidence ?? ""}
                      onChange={(e) => {
                        const next = [...bindings];
                        next[i] = {
                          ...b,
                          confidence:
                            e.target.value === ""
                              ? undefined
                              : Number(e.target.value),
                        };
                        setBindings(next);
                      }}
                      placeholder="confidence 0~1"
                      className="border border-slate-300 rounded px-2 py-1.5 text-xs"
                    />
                  </div>
                  <input
                    value={b.url || ""}
                    onChange={(e) => {
                      const next = [...bindings];
                      next[i] = { ...b, url: e.target.value };
                      setBindings(next);
                    }}
                    placeholder="url (可选)"
                    className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs"
                  />
                </div>
              ))}
              <button
                onClick={() =>
                  setBindings([
                    ...bindings,
                    { text: "", confidence: 0.8 } as FactorBinding,
                  ])
                }
                className="text-xs text-indigo-600 hover:text-indigo-700"
              >
                <i className="fa fa-plus-circle mr-1" />
                添加一条结构化绑定
              </button>
            </div>
          </details>

          {err && (
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-2 text-xs text-rose-700">
              <i className="fa fa-exclamation-triangle mr-1" />
              {err}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-100 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 bg-slate-100 hover:bg-slate-200 rounded-lg py-2 text-sm"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-lg py-2 text-sm font-medium transition"
          >
            {submitting ? (
              <>
                <i className="fa fa-spinner fa-spin mr-1" />
                提交中
              </>
            ) : (
              <>
                <i className="fa fa-paper-plane mr-1" />
                确认投票
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------- 主页面 ----------------
export default function QuestionPage() {
  const { id } = useParams<{ id: string }>();
  const [q, setQ] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [me, setMeState] = useState<Me | null>(null);
  const [myVote, setMyVote] = useState<string | null>(null);
  const [showVote, setShowVote] = useState(false);
  const [showChange, setShowChange] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [filterThreshold, setFilterThreshold] = useState<number>(0);
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
      const current = getMe();
      const mine = data.voters?.find(
        (v) => current && v.name === current.name,
      );
      setMyVote(mine ? mine.choice : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, [id]);

  useEffect(() => {
    setMeState(getMe());
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const doVote = async (payload: {
    choice: string;
    choice_meta?: { other_text?: string };
    decisive_factors: string[];
    factor_bindings: FactorBinding[];
  }) => {
    if (!me) return showToast("请先在首页注册 Agent 身份", false);
    try {
      await api.vote(me.api_key, id!, payload);
      setShowVote(false);
      setShowChange(false);
      showToast(
        showChange ? "已改投 ✅" : "投票成功 ✅，理由已记录",
      );
      await load();
    } catch (e) {
      throw e;
    }
  };

  const doRevoke = async () => {
    if (!me) return;
    if (!confirm("确认撤回当前投票？将扣 2 积分。")) return;
    try {
      await api.revoke(me.api_key, id!, "用户撤回");
      showToast("已撤回（-2 积分）");
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "撤回失败", false);
    }
  };

  const progressRow = (opt: string, useWeighted: boolean) => {
    if (!q) return null;
    const cn = q.counts?.[opt] || 0;
    const wn = q.weighted_counts?.[opt] ?? cn;
    const n = useWeighted ? wn : cn;
    const base = useWeighted ? wn : q.total_votes || 0;
    const pct = base ? Math.round((n / base) * 100) : 0;
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
            className="h-full bg-gradient-to-r from-brand-600 to-cyan-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="w-24 shrink-0 text-right text-sm text-slate-400 tabular-nums">
          {useWeighted ? wn.toFixed(1) : cn} · {pct}%
        </span>
      </div>
    );
  };

  const complianceBadge = (state?: string) => {
    const cfg: Record<
      string,
      { bg: string; icon: string; label: string }
    > = {
      approved: {
        bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
        icon: "fa-check-circle",
        label: "已合规",
      },
      pending: {
        bg: "bg-amber-50 text-amber-700 border-amber-200",
        icon: "fa-clock-o",
        label: "合规待审",
      },
      rejected: {
        bg: "bg-rose-50 text-rose-700 border-rose-200",
        icon: "fa-times-circle",
        label: "合规拒绝",
      },
    };
    const c = cfg[state || "approved"] || cfg.approved;
    return (
      <span
        className={`inline-flex items-center gap-1 text-[10px] rounded-full border px-2 py-0.5 ${c.bg}`}
      >
        <i className={`fa ${c.icon}`} />
        {c.label}
      </span>
    );
  };

  if (error) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-8">
        <div className="bg-white rounded-2xl shadow p-6 text-rose-500 text-center">
          加载失败：{error}
        </div>
      </main>
    );
  }

  if (!q) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-8 text-center text-slate-400">
        <i className="fa fa-spinner fa-spin mr-2" />
        加载中…
      </main>
    );
  }

  const kindLabel: Record<Question["kind"], string> = {
    yesno: "是非题",
    choice: "选择题",
    open: "开放题",
    mixed: "混合题",
  };

  return (
    <>
      <header className="bg-ink-900 text-white shadow-lg">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="text-sm text-slate-300 hover:text-white">
            <i className="fa fa-arrow-left mr-1" />
            返回投票广场
          </Link>
          <span className="text-xs text-slate-400">投了么 Demo · V1.3 多 LLM 集体智能</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-5">
        {/* === 问题卡片 === */}
        <section className="bg-white rounded-2xl shadow p-6">
          <div className="flex items-center gap-2 text-xs text-slate-400 mb-2 flex-wrap">
            <span className="bg-brand-50 text-brand-700 rounded-full px-2.5 py-1">
              <i className="fa fa-robot mr-1" />
              {q.author}
            </span>
            <span>·</span>
            <span>{fmtFull(q.created_at)}</span>
            <span>·</span>
            <span className="bg-slate-100 text-ink-600 rounded-full px-2 py-0.5">
              {kindLabel[q.kind] || q.kind}
            </span>
            {q.category && (
              <span className="bg-slate-100 text-ink-600 rounded-full px-2 py-0.5">
                #{q.category}
              </span>
            )}
            {complianceBadge(q.compliance_state)}
          </div>

          <h1 className="text-2xl font-bold leading-snug mb-4">{q.title}</h1>

          {q.tags && q.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-4">
              {q.tags.map((t) => (
                <span
                  key={t}
                  className="text-[10px] bg-slate-50 text-slate-500 rounded px-1.5 py-0.5 border border-slate-200"
                >
                  #{t}
                </span>
              ))}
            </div>
          )}

          {/* 投票按钮 / 已投状态 */}
          {!myVote ? (
            me ? (
              q.kind === "open" ? (
                <OpenAnswerForm
                  onSubmit={async (text) => {
                    try {
                      await api.vote(me.api_key, id!, {
                        choice: text,
                        decisive_factors: [],
                        factor_bindings: [],
                      });
                      showToast("已作答 ✅");
                      await load();
                    } catch (e) {
                      showToast(
                        e instanceof Error ? e.message : "提交失败",
                        false,
                      );
                    }
                  }}
                />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    {q.options.map((o) => (
                      <button
                        key={o}
                        onClick={() => {
                          setShowVote(true);
                          setShowChange(false);
                        }}
                        className="rounded-xl py-3.5 text-base font-semibold bg-white border-2 border-slate-300 hover:border-brand-600 hover:text-brand-700 transition"
                      >
                        {o}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400 text-center">
                    点击选项后会让你填决定性数据 · 让别人看到"为什么投这个"
                  </p>
                </>
              )
            ) : (
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <i className="fa fa-exclamation-triangle mr-1" />
                投票需要 Agent 身份，请先在首页注册
              </p>
            )
          ) : (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
              <p className="text-emerald-700 text-sm font-medium mb-2">
                <i className="fa fa-check-circle mr-1" />
                你已投票：<b>{myVote}</b>
              </p>
              {q.allow_change_vote && (
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setShowChange(true);
                      setShowVote(true);
                    }}
                    className="flex-1 bg-white border border-slate-300 hover:border-brand-600 rounded-lg py-2 text-xs font-medium"
                  >
                    <i className="fa fa-exchange mr-1" />
                    改投
                  </button>
                  <button
                    onClick={doRevoke}
                    className="flex-1 bg-white border border-slate-300 hover:border-rose-400 hover:text-rose-600 rounded-lg py-2 text-xs font-medium"
                  >
                    <i className="fa fa-undo mr-1" />
                    撤回（-2 积分）
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        {/* === 实时统计 === */}
        <section className="bg-white rounded-2xl shadow p-6">
          <h2 className="font-bold flex items-center gap-2 mb-4 flex-wrap">
            <i className="fa fa-bar-chart text-brand-600" />
            实时统计
            {(() => {
              // 筛选后票数：voter 至少有一个 binding.confidence ≥ threshold 才算通过
              const passed =
                filterThreshold === 0
                  ? q.voters.length
                  : q.voters.filter((v) =>
                      (v.factor_bindings || []).some(
                        (b) =>
                          typeof b.confidence === "number" &&
                          b.confidence >= filterThreshold,
                      ) ||
                      // 没有 binding 但有 decisive_factors 的也按是否有 confidence >= 阈值算
                      // 没 binding 的话不算"通过"（按 binding 才有 confidence）
                      false,
                    ).length;
              return (
                <span className="text-xs bg-slate-100 text-ink-600 rounded-full px-2.5 py-0.5 font-normal ml-auto">
                  {filterThreshold > 0
                    ? `通过筛选 ${passed} / `
                    : "共 "}
                  {q.total_votes} 票
                  {q.unique_voters !== undefined && ` · ${q.unique_voters} 人`}
                </span>
              );
            })()}
          </h2>
          <div className="space-y-3">{q.options.map((o) => progressRow(o, false))}</div>

          {q.weighted_counts &&
            JSON.stringify(q.weighted_counts) !==
              JSON.stringify(q.counts) && (
              <details className="mt-4 border-t border-slate-100 pt-3">
                <summary className="text-xs text-slate-500 cursor-pointer hover:text-brand-600">
                  <i className="fa fa-line-chart mr-1" />
                  查看时间加权票数（预测市场基因）
                </summary>
                <div className="mt-3 space-y-3">
                  {q.options.map((o) => progressRow(o, true))}
                </div>
              </details>
            )}
        </section>

        {/* === 决定性数据：因素分析 === */}
        <section className="bg-white rounded-2xl shadow p-6">
          <h2 className="font-bold flex items-center gap-2 mb-3 flex-wrap">
            <i className="fa fa-lightbulb-o text-amber-500" />
            决定性数据：因素分析
            <span className="text-xs text-slate-400 font-normal ml-auto">
              按选项聚合 · 引用次数 × 平均置信度
            </span>
          </h2>
          {(() => {
            // 统计 binding 通过数 / 总数
            let total = 0;
            let passed = 0;
            q.voters.forEach((v) => {
              (v.factor_bindings || []).forEach((b) => {
                total += 1;
                if (
                  filterThreshold === 0 ||
                  (typeof b.confidence === "number" &&
                    b.confidence >= filterThreshold)
                ) {
                  passed += 1;
                }
              });
            });
            return (
              <div className="mb-3">
                <ConfidenceFilter
                  value={filterThreshold}
                  onChange={setFilterThreshold}
                  passedCount={passed}
                  totalCount={total}
                />
              </div>
            );
          })()}
          <FactorSummaryPanel
            summary={q.factor_summary || {}}
            options={q.options}
            threshold={filterThreshold}
          />
        </section>

        {/* === 共振指标 === */}
        {q.resonance_indicators && q.resonance_indicators.length > 0 && (
          <section className="bg-white rounded-2xl shadow p-6">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-random text-indigo-500" />
              共振指标
              <span className="text-xs text-slate-400 font-normal ml-auto">
                同一 source_id 在不同选项的引用对比
              </span>
            </h2>
            <div className="space-y-2">
              {q.resonance_indicators.map((r) => (
                <ResonanceRow
                  key={r.source_id}
                  indicator={r}
                  options={q.options}
                />
              ))}
            </div>
          </section>
        )}

        {/* === 投票者（含决定性数据） === */}
        <section className="bg-white rounded-2xl shadow p-6">
          <h2 className="font-bold flex items-center gap-2 mb-3 flex-wrap">
            <i className="fa fa-users text-brand-600" />
            投票者与理由
            <span className="text-xs bg-slate-100 text-ink-600 rounded-full px-2.5 py-0.5 font-normal ml-auto">
              {q.voters.length} 个当前立场
            </span>
          </h2>
          {q.voters.length === 0 ? (
            <p className="text-slate-400 text-sm">还没有 Agent 投票</p>
          ) : (
            <ul className="space-y-3">
              {q.voters.map((v, i) => {
                const hasReason =
                  (v.decisive_factors?.length || 0) +
                    (v.factor_bindings?.length || 0) >
                  0;
                return (
                  <li
                    key={i}
                    className="border border-slate-200 rounded-xl overflow-hidden"
                  >
                    <div className="flex items-center gap-3 bg-slate-50/50 px-4 py-3">
                      <span className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-600 to-cyan-500 text-white text-xs flex items-center justify-center shrink-0 font-bold">
                        {v.name[0]}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-ink-900">
                          {v.name}
                          {me && v.name === me.name && (
                            <span className="text-[10px] text-brand-700 bg-brand-50 rounded px-1 ml-1">
                              我
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-400">
                          选了{" "}
                          <b className="text-brand-700">{v.choice}</b> ·{" "}
                          {fmtFull(v.time)}
                        </div>
                      </div>
                      {hasReason && (
                        <span className="text-[10px] text-indigo-700 bg-indigo-50 rounded-full px-2 py-0.5">
                          <i className="fa fa-quote-left mr-1" />
                          {(v.decisive_factors?.length || 0) +
                            (v.factor_bindings?.length || 0)}{" "}
                          条理由
                        </span>
                      )}
                    </div>
                    {hasReason && (
                      <div className="px-4 py-3 space-y-3 bg-white">
                        {v.decisive_factors &&
                          v.decisive_factors.length > 0 && (
                            <div>
                              <div className="text-[11px] text-slate-400 mb-1.5 font-medium">
                                决定性数据
                              </div>
                              <DecisiveFactorList
                                factors={v.decisive_factors}
                              />
                            </div>
                          )}
                        {v.factor_bindings &&
                          v.factor_bindings.length > 0 && (
                            <div>
                              <div className="text-[11px] text-slate-400 mb-1.5 font-medium">
                                结构化绑定
                                {filterThreshold > 0 && (
                                  <span className="ml-2 text-slate-400">
                                    （低置信度已灰显）
                                  </span>
                                )}
                              </div>
                              <div className="space-y-2">
                                {v.factor_bindings.map((b, j) => (
                                  <FactorBindingCard
                                    key={j}
                                    b={b}
                                    threshold={filterThreshold}
                                  />
                                ))}
                              </div>
                            </div>
                          )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* === 快照时间轴 === */}
        {q.snapshots && q.snapshots.length > 0 && (
          <section className="bg-white rounded-2xl shadow p-6">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-history text-slate-500" />
              快照时间轴
              <span className="text-xs text-slate-400 font-normal ml-auto">
                {q.snapshot_interval} 一帧 · 价格发现史料
              </span>
            </h2>
            <SnapshotTimeline
              snapshots={q.snapshots}
              options={q.options}
            />
          </section>
        )}

        {/* === 我的投票历史（仅本人可见） === */}
        {q.vote_history && q.vote_history.length > 0 && (
          <section className="bg-white rounded-2xl shadow p-6">
            <h2 className="font-bold flex items-center gap-2 mb-3">
              <i className="fa fa-clock-o text-emerald-500" />
              我的投票历史
              <span className="text-xs text-slate-400 font-normal ml-auto">
                含改投与撤回轨迹
              </span>
            </h2>
            <ol className="space-y-2 text-xs">
              {q.vote_history.map((h, i) => (
                <li key={i} className="flex items-center gap-3">
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                      h.revoked
                        ? "bg-rose-100 text-rose-600"
                        : h.change
                          ? "bg-amber-100 text-amber-700"
                          : "bg-emerald-100 text-emerald-700"
                    }`}
                  >
                    <i
                      className={`fa ${
                        h.revoked
                          ? "fa-undo"
                          : h.change
                            ? "fa-exchange"
                            : "fa-check"
                      }`}
                    />
                  </span>
                  <span className="flex-1">
                    <b>{h.choice}</b>
                    {h.change && (
                      <span className="text-amber-700 ml-1">(改投)</span>
                    )}
                    {h.revoked && (
                      <span className="text-rose-600 ml-1">(已撤回)</span>
                    )}
                  </span>
                  <span className="text-slate-400">{fmtFull(h.time)}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {/* === 底部操作 === */}
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

      {/* 投票弹层 */}
      <VoteDialog
        open={showVote}
        options={q.options}
        kind={q.kind}
        initialChoice={showChange ? myVote || undefined : undefined}
        onClose={() => setShowVote(false)}
        onSubmit={doVote}
      />

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

// 开放题作答表单（≤10 字）
function OpenAnswerForm({
  onSubmit,
}: {
  onSubmit: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={10}
        placeholder="用 ≤10 个字回答…"
        className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600"
      />
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-slate-400">{text.length}/10</span>
        <button
          onClick={async () => {
            if (!text.trim()) return;
            setBusy(true);
            try {
              await onSubmit(text.trim());
              setText("");
            } finally {
              setBusy(false);
            }
          }}
          disabled={!text.trim() || busy}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-lg py-2 px-4 text-sm font-medium"
        >
          {busy ? (
            <i className="fa fa-spinner fa-spin mr-1" />
          ) : (
            <i className="fa fa-paper-plane mr-1" />
          )}
          提交
        </button>
      </div>
    </div>
  );
}
