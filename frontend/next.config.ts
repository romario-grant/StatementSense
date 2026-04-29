import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Firebase App Hosting — builds a self-contained server for Cloud Run
  output: "standalone",

  async rewrites() {
    return [
      {
        // Proxy API requests to the FastAPI backend
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_BACKEND_URL || "https://statementsense-backend-430268251728.us-central1.run.app"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
