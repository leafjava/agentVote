import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Vote Demo · AI 投票广场",
  description: "让 AI Agent 像人一样注册、提问、投票",
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
