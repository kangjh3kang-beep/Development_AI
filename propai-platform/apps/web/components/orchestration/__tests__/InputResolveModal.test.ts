/**
 * (P1 B-3 LOW-1) slotLabel 순수함수 단위 테스트.
 *
 * 결함: PR#230의 feasibility 노드 항상-ready 슬롯(readyCheck 무조건 true)이 manualPrompt
 * 없이 등록돼 있어, InputResolveModal의 "확보된 입력" 목록에 raw 키(feasibilityData)가
 * 그대로 노출됐다. 수정은 (1) node-registry에 manualPrompt를 부여해 slotLabel이 사람말을
 * 쓰게 하고, (2) 모달 렌더에서 실값이 없으면 ✓ 대신 중립 표기로 분기한다(렌더 검증은
 * 기존 orchestration-components.test.tsx 스모크로 충분 — 여기서는 slotLabel 자체만 검증).
 */
import { describe, it, expect } from "vitest";

import { slotLabel } from "@/components/orchestration/InputResolveModal";
import type { SsotInputSpec } from "@/lib/orchestration/types";

function spec(over: Partial<SsotInputSpec>): SsotInputSpec {
  return {
    slot: "siteAnalysis",
    readyCheck: () => true,
    resolution: ["ssot"],
    provenanceGuarded: false,
    ...over,
  };
}

describe("slotLabel — 입력 슬롯 → 사람이 읽는 라벨(순수함수)", () => {
  it("manualPrompt가 있으면 그 문구를 그대로 사용한다(raw 키 노출 금지)", () => {
    expect(
      slotLabel(spec({ slot: "feasibilityData", manualPrompt: "수지 파생환류(선택·자동 반영)" })),
    ).toBe("수지 파생환류(선택·자동 반영)");
  });

  it("manualPrompt가 없고 field가 있으면 slot.field 형태의 raw 키를 반환한다", () => {
    expect(slotLabel(spec({ slot: "siteAnalysis", field: "address" }))).toBe(
      "siteAnalysis.address",
    );
  });

  it("manualPrompt·field 모두 없으면 slot명만 반환한다", () => {
    expect(slotLabel(spec({ slot: "feasibilityData" }))).toBe("feasibilityData");
  });
});
