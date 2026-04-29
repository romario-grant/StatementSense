import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Firebase App Hosting — builds a self-contained server for Cloud Run
  output: "standalone",

  async rewrites() {
    return [
      {
        // Proxy API requests directly to the FastAPI Cloud Run backend
        source: "/api/:path*",
        destination: "https://statementsense-backend-430268251728.us-central1.run.app/api/:path*",
      },
    ];
  },
};

export default nextConfig;
