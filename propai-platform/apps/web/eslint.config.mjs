import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".open-next/**",
    ".vercel/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      // React 19/Next 16의 새 정적검사는 기존 전역 레거시를 한 번에 막는다.
      // IA/대시보드 리팩터링 게이트를 복구한 뒤, 대상 모듈부터 단계적으로 해소한다.
      "react-hooks/immutability": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react/no-unescaped-entities": "warn"
    }
  },
  {
    // ★`.mjs` 스크립트에 **no-undef** 를 켠다 — 이 저장소에는 이것을 보는 층이 없었다.
    //
    // 실측(2026-08-27): `e2e/support/hydration-probe.mjs` 의 `run` 모드가 `NOISE_RE`(그 상수를
    // 옮겨 간 `probe-text.mjs` 의 **지역** 상수)를 참조한 채 남아 **실행 즉시 ReferenceError** 로
    // 죽었다. 세 층이 전부 통과시켰다 — ①`tsc` 는 `.mjs` 를 대상으로 삼지 않고 ②`no-undef` 가
    // **미설정**이라 eslint 는 그 파일을 보고도 위반 0 을 냈으며 ③순수부 테스트
    // (`lib/hydration/__tests__/probe-text.test.ts`)는 **스크립트 자체를 태우지 않는다.**
    // 그리고 `control` 모드는 그 줄을 지나지 않아 **통과했다** — 도구가 살아 있는 것처럼 보였다.
    //
    // ★`globals` 를 손으로 나열하지 않는다. 처음엔 18개를 적었는데 **변이(M6: `document` 제거)가
    //   SURVIVED** 해서 재보니 `--print-config` 기준 이미 **1174개**가 상위 config 에서 오고 있었다
    //   — 내 목록은 **전부 중복**이었고, 그 옆에 적어 둔 *"목록형의 한계를 알고 쓴다"* 는 주석은
    //   **거짓 전제**였다. 목록을 두면 그것이 곧 상한이 되고, 여기서는 둘 이유조차 없었다.
    //
    // ★`.js` 까지 넣는다(독립 리뷰가 제안 → **내가 실측해** 채택). tracked `.js` 는 **5건**이고
    //   그중 `public/sw.js` 는 **프로덕션에 실리는 서비스워커**다 — `.mjs` 와 똑같이 `tsc` 사각이다.
    //   실측: 확장 후 `.js`·`.mjs` 전수 **no-undef error 0**(기존 위반 없음 · 래칫 158 불변).
    files: ["**/*.mjs", "**/*.js"],
    rules: { "no-undef": "error" },
  },
  {
    // ★서비스워커 전역 — 상위 config 의 globals 1174개에 `clients` 가 **없다**(실측:
    //   `document`/`localStorage`/`window` 는 있는데 `clients` 만 빠졌다). 목록을 두되
    //   **이 파일에만** 두고, 부족하면 **위양성으로 시끄럽게** 드러나게 한다(조용한 위음성 아님).
    files: ["public/sw.js"],
    languageOptions: {
      globals: { clients: "readonly", self: "readonly", caches: "readonly", skipWaiting: "readonly" },
    },
  },
  {
    // ★자가검증(field_audit) 표면에는 피드백 수집 위젯을 붙이지 못하게 **빌드로** 막는다.
    //
    // 왜: 성장엔진은 사용자 👎(ai_feedback)를 모아 품질저하로 판정하고, 그 판정이 임계를
    // 넘으면 서술기능(llm_narrative)을 자동으로 끈다. 이 경로는 무인으로 주기 실행된다.
    // 자가검증 배지 옆에 👍👎를 놓으면 "값이 이상하다고 알려줄수록 그걸 설명하는 기능이 먼저
    // 꺼지는" 뒤집힌 루프가 생긴다(correctness 판정이 서술 기능을 끄는 카테고리 오류).
    //
    // 지금 이 사고가 안 나는 유일한 이유는 VerificationBadge가 FeedbackWidget에 `service`를
    // 넘기지 않아서인데, 그건 **우연한 차단**이지 설계된 격리가 아니다(집계 쿼리에 출처 필터
    // 자체가 없다). 그래서 물리적으로 임포트를 막아 실수 여지를 없앤다.
    // ★소비 패널까지 포함한다 — 자가검증 카드를 실제로 렌더하는 곳이 여기라서, 카드 파일만
    //   막으면 패널에 위젯을 직접 붙이는 우회가 그대로 통과한다(적대검증에서 실측 확인).
    files: [
      "components/analysis/FieldAuditNotice.tsx",
      "components/analysis/CredibilitySummaryCard.tsx",
      "components/analysis/ComprehensiveAnalysisPanel.tsx",
      "lib/field-audit.ts",
    ],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [{
          // VerificationBadge도 막는다 — 내부에서 FeedbackWidget을 렌더하므로 실질 동일 효과다.
          group: ["**/growth/FeedbackWidget", "**/FeedbackWidget", "**/common/VerificationBadge"],
          message:
            "자가검증 표면에는 피드백 위젯을 붙이지 않습니다 — 사용자 👎가 성장엔진의 서술기능 "
            + "자동 비활성으로 이어지는 경로가 열려 있습니다(F4a). 별도 수집면이 필요하면 출처를 "
            + "구분해 집계에서 제외하는 봉합이 선행돼야 합니다.",
        }],
      }],
    },
  }
]);

export default eslintConfig;
