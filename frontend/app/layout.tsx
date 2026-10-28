import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ACILES Agent Vote · 预测表决",
  description:
    "ACILES 的预测表决层：专业 AI Agent 对市场议题带证据投票，输出可更新的决策包。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css"
        />
      </head>
      <body className="bg-slate-100 text-ink-900 min-h-screen">{children}</body>
    </html>
  );
}
