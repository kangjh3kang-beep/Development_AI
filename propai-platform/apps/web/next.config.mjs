import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@propai/ui"],
  experimental: {
    turbopack: {
      root: path.join(__dirname, "../../"),
    },
  },

  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
      },
      {
        protocol: "https",
        hostname: "propai.kr",
      },
      {
        protocol: "https",
        hostname: "storage.propai.kr",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/proxy/:path*",
        destination: "http://api:8000/api/v1/:path*",
      },
    ];
  },
};

export default nextConfig;
