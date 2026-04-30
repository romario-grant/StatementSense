import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Firebase App Hosting — builds a self-contained server for Cloud Run
  output: "standalone",

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: process.env.NODE_ENV === "development"
          ? "http://127.0.0.1:8000/api/:path*"
          : "https://statementsense-backend-430268251728.us-central1.run.app/api/:path*",
      },
    ];
  },
};

export default nextConfig;
