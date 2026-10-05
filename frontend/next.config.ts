import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://backend:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    useTypeScriptCli: false,
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
