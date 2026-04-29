import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Firebase App Hosting — builds a self-contained server for Cloud Run
  output: "standalone",

  async rewrites() {
    return [
      {
        // Proxy API requests to the FastAPI backend
        // Local dev: http://localhost:8000
        // Production: Set BACKEND_URL to your Cloud Run URL
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
