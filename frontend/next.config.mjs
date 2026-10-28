/** @type {import('next').NextConfig} */
const backend = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/healthz", destination: `${backend}/healthz` },
      { source: "/skill.md", destination: `${backend}/skill.md` },
      { source: "/docs", destination: `${backend}/docs` },
      { source: "/docs/:path*", destination: `${backend}/docs/:path*` },
      { source: "/openapi.json", destination: `${backend}/openapi.json` },
    ];
  },
};

export default nextConfig;
