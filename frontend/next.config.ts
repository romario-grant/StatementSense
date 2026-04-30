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
          : `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
