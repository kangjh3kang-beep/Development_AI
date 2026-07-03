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
    // ★CI heap OOM 방지: vitest 기본 forks 병렬(=CPU 코어수)이 동시 jsdom 인스턴스 heap 을
    //   곱해 "JS heap out of memory"를 유발했다(main·전 프론트 PR 의 frontend check 를 막던
    //   근본원인). fork 수를 제한해 동시 jsdom 메모리를 CI 러너 범위로 억제한다.
    //   isolate 기본값 유지 → 테스트 격리·정확성은 불변(속도만 소폭 트레이드오프).
    pool: "forks",
    poolOptions: { forks: { maxForks: 2, minForks: 1 } },
    // 파일별 힙 사용량을 로그로 남겨 OOM 을 유발하는 원흉 테스트 파일을 특정한다(근본 진단용).
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
