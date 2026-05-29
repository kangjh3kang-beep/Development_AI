import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_USE_MOCKS: process.env.NEXT_PUBLIC_USE_MOCKS || "false",
  },
  reactStrictMode: true,
  transpilePackages: ["@propai/ui"],
  turbopack: {
    root: path.join(__dirname, "../../"),
  },
  outputFileTracingRoot: path.join(__dirname, "../../"),
  experimental: {
    optimizePackageImports: [
      "recharts",
      "framer-motion",
      "three",
      "@react-three/fiber",
      "@react-three/drei",
      "konva",
      "react-konva",
      "graphql",
    ],
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
};

export default nextConfig;
