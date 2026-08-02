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
    files: [
      "components/analysis/FieldAuditNotice.tsx",
      "components/analysis/CredibilitySummaryCard.tsx",
      "lib/field-audit.ts",
    ],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [{
          group: ["**/growth/FeedbackWidget", "**/FeedbackWidget"],
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
