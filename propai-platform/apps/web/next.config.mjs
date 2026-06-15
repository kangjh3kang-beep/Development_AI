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

  // P2-9 보안: 비파괴 보안 헤더(클릭재킹·MIME 스니핑·레퍼러 유출·HSTS).
  // CSP는 Next 인라인 스크립트·외부(카카오맵/three) 출처로 인해 nonce 기반 검증 롤아웃이 필요 → 별도(앱 실검증 후).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
        ],
      },
    ];
  },
};

export default nextConfig;
