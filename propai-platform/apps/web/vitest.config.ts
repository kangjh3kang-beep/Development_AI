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
    // ★테스트 1건의 제한시간(벽시계). 10초였는데 **전체 스위트에서만** 터졌다.
    //
    //   왜냐하면 이 저장소에는 `it` 안에서 **저장소 소스 전체(약 940개 파일)를 다시 읽는**
    //   "전수 스캔" 계약 테스트가 여러 개 있다. 혼자 돌리면 3초인데, 전체 스위트에서는
    //   워커들이 CPU 를 나눠 쓰느라 같은 테스트가 10초를 넘긴다.
    //   → **실패가 코드 결함이 아니라 그때의 CPU 경합에 좌우된다**(플레이키).
    //   실측 2026-08-22: `lib/percent-sweep.wiring.test.ts` 가 전체에서 10.8초로 실패,
    //   단독 실행은 3.2초로 통과. main 브랜치가 그대로 EXIT=1 이었다.
    //
    //   ★종전 처방은 **파일마다 `vi.setConfig({ testTimeout })` 를 손으로 넣는 것**이었는데,
    //     전수 스캔 계열 18개 중 **5개에만** 들어가 있었다. 손으로 넣는 처방은 형제를 빠뜨린다
    //     — 이 저장소가 반복해서 데인 형태다(CLAUDE.md "형제·미러 스윕").
    //     그래서 **여기 한 곳**을 올려 새로 생기는 전수 스캔 테스트까지 자동으로 덮는다.
    //
    //   ★이 값은 **정확성 경계가 아니라 벽시계다.** 늘려도 잡아내는 결함은 그대로이고,
    //     느려서 못 끝내는 테스트만 살아난다. 진짜로 멈춘 테스트는 30초 뒤 여전히 실패한다.
    testTimeout: 30000,
    setupFiles: ["./test/setup.ts"],
    css: false,
    globals: true,
    // ★파생형으로 수집한다. 종전엔 디렉토리를 **손으로 나열**해 그 목록이 곧 상한이었다 —
    //   `store/`·`i18n/`·`types/` 등에 테스트를 만들면 `No test files found` 로 조용히
    //   **한 번도 실행되지 않는 락**이 초록 안에 남는다(2026-08-24 실제로 그럴 뻔했다).
    //   빠진 디렉토리를 사람이 알아채는 구조를 없앤다.
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules/**", "e2e/**", ".next/**"],
  },
});
