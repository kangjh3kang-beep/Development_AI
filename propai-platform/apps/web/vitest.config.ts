import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
      "@propai/ui": path.resolve(__dirname, "../../packages/ui/src/index.ts"),
    },
  },
  test: {
    environment: "jsdom",
    testTimeout: 10000,
    setupFiles: ["./test/setup.ts"],
    css: false,
    globals: true,
    // 파일별 힙 사용량을 로그로 남겨 향후 메모리 이상 테스트를 조기 진단(#174에서 흡수).
    // 로그 출력만 하므로 테스트 동작·정확성에는 영향이 없다.
    logHeapUsage: true,
    include: [
      "app/**/*.test.ts",
      "app/**/*.test.tsx",
      "components/**/*.test.ts",
      "components/**/*.test.tsx",
      "hooks/**/*.test.ts",
      "hooks/**/*.test.tsx",
      "lib/**/*.test.ts",
      "lib/**/*.test.tsx",
    ],
    exclude: ["node_modules/**", "e2e/**", ".next/**"],
  },
});
