import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_USE_MOCKS: process.env.NEXT_PUBLIC_USE_MOCKS || "false",
  },
  reactStrictMode: true,
  output: "standalone",
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
      // konva·react-konva는 제외: CADEditor가 런타임 require()로 로드하는데
      // optimizePackageImports의 배럴 재작성이 require() 반환 객체의 named export를
      // undefined로 만들어 Konva 캔버스가 무에러로 비렌더됨(빈 캔버스 버그 근본원인).
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
