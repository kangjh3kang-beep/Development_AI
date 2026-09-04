/**
 * ChangeCauseCard 표시 계약 잠금 — 실제 렌더 결과를 단언한다(픽스처 동어반복 금지).
 *
 * ★골든의 출처: 2026-08-01 프로덕션 화면에서 "이전 분석과 모순 감지 / 최고 심각도 HIGH"로
 * 잘못 표시된 실제 케이스(사용자가 필지를 3개→2개로 재선택). 만들어낸 예시가 아니다.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChangeCauseCard } from "@/components/analysis/ComprehensiveAnalysisPanel";

vi.mock("@/lib/api-client", () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }));

/** 라이브 오표기 케이스 — 필지 3→2 재선택(백엔드가 INPUT_CHANGED로 분류). */
const INPUT_CHANGED = {
  contradictions: [],
  groups: [
    { key_pattern: "effective_far.parcel_count", prev: 3, now: 2, severity: "high" },
    { key_pattern: "land_area_sqm", prev: 176458, now: 152826, severity: "medium" },
    { key_pattern: "location.education.school_count", prev: 5, now: 1, severity: "high" },
  ],
  max_severity: "high",
  needs_review: false,
  change_cause: {
    cause: "INPUT_CHANGED",
    headline: "분석 조건이 바뀌었습니다 (선택 필지 수)",
    reason: "이전 분석과 입력이 다릅니다 — 선택 필지 수: 3 → 2.",
    comparable: false,
    trust_hint: "두 결과는 각각의 조건에서 모두 유효합니다.",
    changed_inputs: [{ index: 2, label: "선택 필지 수", prev: "3", now: "2" }],
    needs_review: false,
  },
};

const UNEXPLAINED = {
  contradictions: [],
  groups: [{ key_pattern: "land_area_sqm", prev: 152826, now: 180000, severity: "high" }],
  max_severity: "high",
  needs_review: true,
  change_cause: {
    cause: "UNEXPLAINED",
    headline: "확인이 필요한 차이가 있습니다",
    reason: "입력과 분석 기준이 모두 같은데 수치가 달라졌습니다.",
    comparable: true,
    trust_hint: "근거·출처를 직접 확인하세요.",
    changed_inputs: [],
    needs_review: true,
  },
};

describe("ChangeCauseCard", () => {
  it("★입력 변경은 경고가 아니다 — '모순'·심각도 배지를 렌더하지 않는다", () => {
    const { container } = render(<ChangeCauseCard contradictions={INPUT_CHANGED} />);

    expect(screen.queryByText(/모순/)).toBeNull();
    expect(screen.queryByText(/최고 심각도/)).toBeNull();
    expect(screen.queryByText(/HIGH/i)).toBeNull();
    expect(screen.getByText(/비교 불가/)).toBeTruthy();
    // 경고색 클래스(status-warning)가 카드에 칠해지지 않아야 한다.
    expect(container.querySelector('[class*="status-warning"]')).toBeNull();
  });

  it("★원시 키를 화면에 노출하지 않고 한국어 라벨로 보여준다", () => {
    render(<ChangeCauseCard contradictions={INPUT_CHANGED} />);

    expect(screen.queryByText(/effective_far/)).toBeNull();
    expect(screen.queryByText(/zone_mix/)).toBeNull();
    expect(screen.queryByText(/school_count/)).toBeNull();
    expect(screen.getByText("선택 필지 수")).toBeTruthy();
    expect(screen.getByText("대지면적")).toBeTruthy();
    expect(screen.getByText("반경 내 학교")).toBeTruthy();
  });

  it("★'변화율 %' 대신 실제 단위 증감을 보여준다", () => {
    const { container } = render(<ChangeCauseCard contradictions={INPUT_CHANGED} />);
    const text = container.textContent ?? "";

    expect(text).not.toContain("변화율");
    expect(text).toContain("152,826㎡");
    expect(text).toContain("−23,632㎡");
    expect(text).toContain("−1개");
  });

  it("입력 변경 시 '어느 쪽을 믿나' 안내를 제공하되 우열을 단정하지 않는다", () => {
    const { container } = render(<ChangeCauseCard contradictions={INPUT_CHANGED} />);
    const text = container.textContent ?? "";

    expect(text).toContain("어느 쪽을 믿어야 하나요?");
    for (const forbidden of ["틀렸", "오류", "잘못"]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("★UNEXPLAINED만 경고색과 '확인 필요' 배지를 받는다", () => {
    const { container } = render(<ChangeCauseCard contradictions={UNEXPLAINED} />);

    expect(screen.getByText(/확인 필요/)).toBeTruthy();
    expect(container.querySelector('[class*="status-warning"]')).not.toBeNull();
  });

  it("미등재 키는 이름을 지어내지 않고 접힌 '기타 항목'에 원본 그대로 둔다", async () => {
    const withUnknown = {
      ...INPUT_CHANGED,
      groups: [
        ...INPUT_CHANGED.groups,
        { key_pattern: "sd_gate.ratio", prev: 0.4, now: 0.7, severity: "low" },
      ],
    };
    render(<ChangeCauseCard contradictions={withUnknown} />);

    // 접힌 상태에서는 원본 키가 보이지 않는다.
    expect(screen.queryByText(/sd_gate\.ratio/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /기타 변경 항목 1건 보기/ }));
    // 펼치면 지어낸 이름이 아니라 원본 키가 그대로 나온다.
    expect(screen.getByText(/sd_gate\.ratio/)).toBeTruthy();
  });

  it("변화가 없으면 카드 대신 한 줄 배지만 남긴다", () => {
    const none = {
      contradictions: [],
      groups: [],
      needs_review: false,
      change_cause: { cause: "NONE", headline: "이전 분석과 동일합니다", reason: "", trust_hint: "", changed_inputs: [], needs_review: false },
    };
    const { container } = render(<ChangeCauseCard contradictions={none} />);

    expect(container.textContent).toContain("이전 분석과 동일합니다");
    expect(container.querySelector(".rounded-2xl")).toBeNull();
  });

  it("★구버전 응답(change_cause 없음)을 '원인 없음'으로 낙관하지 않는다", () => {
    const legacy = {
      contradictions: [{ key: "land_area_sqm", prev: 1, now: 2, severity: "high" }],
      groups: [{ key_pattern: "land_area_sqm", prev: 1, now: 2, severity: "high" }],
      max_severity: "high",
    };
    render(<ChangeCauseCard contradictions={legacy} />);

    expect(screen.getByText(/확인 필요/)).toBeTruthy();
  });

  it("데이터가 없으면 아무것도 렌더하지 않는다", () => {
    const { container } = render(<ChangeCauseCard contradictions={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});
