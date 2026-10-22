import type { NextConfig } from "next";

const backendOrigin = (process.env.BACKEND_API_ORIGIN || "https://outreach-marketing-agent.vercel.app").replace(/\/$/, "");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendOrigin}/api/:path*` }];
  },
};

export default nextConfig;
