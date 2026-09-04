/**
 * 정밀도 배지 배선 락 (2026-08-23 · #770 후속).
 *
 * ## 무엇이 있었나
 *
 * 프로젝트 허브 화면에 이렇게 나란히 있었다.
 *
 *     설계 분석   → "분석 전"
 *     공사비 분석 → "분석 전"
 *     수지·사업성 → 총사업비 4,157.7억 · 등급 F
 *
 * 백엔드는 `gfa = 대지면적 × 실효용적률` 로 **개략 추정**을 하고 모듈명도
 * `rough_feasibility_orchestrator` 다 — 계산은 정직하다. 문제는 **화면이 개략치를
 * 확정치와 똑같이 보여 준 것**이고, 사용자는 "분석 전인데 왜 숫자가 있나"로 읽었다.
 *
 * `#770` 이 백엔드에 `precision`(E/D/V)을 실었다. 이 락은 **그 값이 화면까지
 * 실제로 오는지**를 본다 — 이 저장소가 반복해 데인 *"정의만 하고 소비처 0"* 방지다.
 *
 * ★소스 검사이지만 **주석·문자열을 배제**하고 실행되는 줄만 본다
 *   (주석 처리 + 임포트 유지 변이에 뚫린 전례가 2회 있다).
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const ROOT = path.resolve(__dirname, "../../..");

function executableSource(rel: string): string {
  const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
  return __stripCommentsForScan(src, rel);
}

describe("정밀도 등급이 화면까지 배선된다", () => {
  it("스토어 타입이 precision 필드를 갖는다", () => {
    const src = executableSource("store/useProjectContextStore.ts");
    expect(src).toMatch(/precision\?:/);
    expect(src).toMatch(/precisionBasis\?:/);
  });

  it("프로젝트 페이지가 백엔드 precision 을 스토어로 승계한다", () => {
    const src = executableSource("app/[locale]/(dashboard)/projects/[id]/page.tsx");
    // ★백엔드 키(snake_case) → 스토어 키(camelCase) 매핑이 실제 코드에 있어야 한다.
    expect(src).toMatch(/precision:\s*feas\.precision/);
    expect(src).toMatch(/precisionBasis:\s*feas\.precision_basis/);
  });

  it("요약 화면이 개략(E)일 때 배지를 렌더한다", () => {
    const src = executableSource("components/projects/ProjectAnalysisSummary.tsx");
    // 문자열 리터럴은 stripped 되므로 **분기 조건**으로 확인한다.
    expect(src).toMatch(/feas\?\.precision\s*===/);
  });

  it("★대조군 — 배지 문구가 실제 파일에 있다(분기만 있고 렌더가 없는 것 방지)", () => {
    // ★`__stripCommentsForScan` 은 **주석만** 제거한다(문자열은 남는다).
    // 그래도 원본을 별도로 확인한다 — 헬퍼 동작이 바뀌어도 이 대조군은 살아남는다.
    const raw = fs.readFileSync(
      path.join(ROOT, "components/projects/ProjectAnalysisSummary.tsx"),
      "utf8",
    );
    expect(raw).toContain("개략(추정)");
  });
});
