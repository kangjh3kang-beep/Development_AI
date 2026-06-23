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
      "lucide-react",
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
      // ★서비스워커는 절대 캐시 금지(no-cache). 이게 없으면 CDN(Cloudflare) 기본 Browser Cache TTL
      //   4시간(max-age=14400)이 적용돼, 새 sw.js를 배포해도 브라우저가 최대 4시간 동안 재확인조차
      //   하지 않는다 → skipWaiting 새 sw가 설치 안 됨 → 구버전 프론트가 계속 서빙(배포가 사용자에게
      //   안 닿는 근본원인). no-cache로 매 방문 재검증시켜 새 sw를 즉시 감지·활성화한다.
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
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
