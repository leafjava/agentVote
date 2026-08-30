import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "投了么 · AI Agent 理性投票协议",
  description: "DeepSeek · Grok · Moonshot 三家 LLM 集体决策 —— 让每一次判断都带数据依据",
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
