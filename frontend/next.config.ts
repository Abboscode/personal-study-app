import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://backend:8000";
const configuredProxyTimeout = Number(process.env.API_PROXY_TIMEOUT_MS || "330000");
const apiProxyTimeout = Number.isFinite(configuredProxyTimeout) && configuredProxyTimeout > 0
  ? configuredProxyTimeout
  : 330_000;

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    useTypeScriptCli: false,
    // Generation can legitimately take several minutes. Keep this slightly
    // longer than the backend's bounded OpenRouter timeout.
    proxyTimeout: apiProxyTimeout,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
