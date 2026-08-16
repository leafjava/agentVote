import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: { 900: "#0f172a", 800: "#1e293b", 600: "#475569" },
        brand: { 600: "#4f46e5", 700: "#4338ca", 50: "#eef2ff" },
      },
    },
  },
  plugins: [],
};

export default config;
