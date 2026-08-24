/**
 * 정밀도 등급은 **모든 쓰기 경로**가 옮겨야 한다 (2026-08-24 · 라이브 수용시험에서 적발).
 *
 * ## 무엇이 있었나
 *
 * `#770`(백엔드 산출)과 `#771`(프론트 배지)이 **둘 다 머지·배포**됐는데 화면에 배지가
 * 뜨지 않았다. 사용자 계정으로 라이브에서 '개략수지 생성'을 실제로 눌러 확인했다:
 *
 *     POST /api/v2/feasibility/rough-scenario  → 200 · 화면에 "등급 F" 생성
 *     배지 "개략(추정) — 설계 미반영"          → **0건**
 *     스토어 feasibilityData                    → {grade:"F"} · **precision 키 없음**
 *
 * 원인은 `feasibilityData` 의 **쓰기 경로가 둘**이라는 것이었다:
 *
 *     projects/[id]/page.tsx          하이드레이션(프로젝트 레코드) → `#771` 이 배선
 *     rough-scenario-commit.ts        생성(사용자가 실제로 누르는 것) → **누락**
 *
 * ★"짝이 반만 착지"가 아니다 — **양쪽 다 착지했는데 경로가 갈려** 안 보였다.
 *   그래서 PR 단위 검증(둘 다 머지됐나)으로는 원리적으로 못 잡는다.
 *
 * ## 이 파일이 잠그는 것
 *
 * 백엔드 수지 페이로드를 받아 `updateFeasibilityData` 로 쓰는 **모든 소스 파일**이
 * `precision` 을 함께 옮기는지 본다. 새 쓰기 경로가 생기면 여기서 먼저 걸린다.
 *
 * ★소스 검사인 이유: 두 경로는 각각 다른 층(React 페이지 / 순수 매퍼)이라 하나의
 *   런타임 테스트로 둘을 태울 수 없다. 대신 **주석·문자열에 속지 않도록**
 *   `__stripCommentsForScan` 을 경유해 실행되는 줄만 본다(이 저장소가 반복해 데인 형태).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..", "..");

/** 백엔드 수지 페이로드를 스토어로 옮기는 **쓰기 경로**들(실측으로 확정). */
const FEASIBILITY_WRITERS = [
  "app/[locale]/(dashboard)/projects/[id]/page.tsx",
  "components/feasibility/rough-scenario-commit.ts",
] as const;

function executable(rel: string): string {
  return __stripCommentsForScan(readFileSync(join(WEB_ROOT, rel), "utf8"), rel);
}

describe("정밀도 등급 — 쓰기 경로 계약", () => {
  it("★모든 쓰기 경로가 precision 을 옮긴다 — 하나만 배선되면 화면이 갈린다", () => {
    // ★공허 진리 방지 — 목록이 비면 아래 루프가 통째로 사라진다.
    expect(FEASIBILITY_WRITERS.length).toBeGreaterThanOrEqual(2);
    for (const rel of FEASIBILITY_WRITERS) {
      const code = executable(rel);
      expect(code.length, `${rel} 를 못 읽었다 — 경로가 바뀌었다`).toBeGreaterThan(200);
      expect(code, `${rel} 가 precision 을 안 옮긴다 — 이 경로로 만든 값엔 배지가 안 뜬다`)
        .toContain("precision");
      expect(code, `${rel} 가 precisionLabel 을 안 옮긴다`).toMatch(/precisionLabel/);
      expect(code, `${rel} 가 precisionBasis 를 안 옮긴다`).toMatch(/precisionBasis/);
    }
  });

  it("★대조군 — 검사가 주석에 속지 않는다", () => {
    // 위 락은 *주석에만* precision 이 있어도 초록일 수 있다. 그 가능성을 직접 배제한다.
    const stripped = __stripCommentsForScan(
      "// precision\n/* precisionLabel */\nconst x = 1;\n",
      "probe.ts",
    );
    expect(stripped).not.toContain("precision");
    expect(stripped).toContain("const x = 1");
  });

  it("★대조군 — 쓰기 경로 목록이 실재하는 파일을 가리킨다(죽은 목록 방지)", () => {
    for (const rel of FEASIBILITY_WRITERS) {
      expect(() => readFileSync(join(WEB_ROOT, rel), "utf8"), `${rel} 가 없다`).not.toThrow();
    }
  });
});
