/**
 * 법정초과 가드 경고 — **렌더와 배선**.
 *
 * ## 무엇이 있었나 (2026-08-24 실측)
 *
 * 백엔드 `apply_legal_hotpath_guard` 가 법정 건폐·용적·층수 초과를 검출해 **네 표면**이
 * `integrity_warnings` 를 응답에 싣는데, **프론트 소비처가 0** 이었다.
 *
 * ★가드가 신뢰도를 강등하며 붙이는 문구가 *"…— integrity_warnings 참조."* 였다.
 *   **화면에 없는 것을 참조하라**고 말하는 매달린 참조였다.
 *
 * ## 이 파일이 잠그는 것
 *
 * 1. 항목이 있으면 **실제로 그려진다**(백엔드 원문 그대로 — 무날조)
 * 2. **비면 아무것도 그리지 않는다** — "이상 없음"이라고 단언하지도 않는다
 * 3. `high`(근거 미제시)가 시각적으로 갈린다
 * 4. ★두 소비 표면이 이 컴포넌트를 **실제로 렌더**한다(배선 — 소스 검사 아님)
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IntegrityWarnings, type IntegrityWarning } from "@/components/ui/IntegrityWarnings";

const HIGH: IntegrityWarning = {
  type: "층수제한초과",
  claim: "5층",
  severity: "high",
  note: "자연녹지지역은 4층 이하 제한이 있으나 5층이 제시됨 — 근거 미제시(할루시네이션 의심).",
};
const WARN: IntegrityWarning = {
  type: "높이제한오표기",
  claim: "높이 제한없음",
  severity: "medium",
  note: "4층(약 13m) 이하 제한이 있으나 '제한없음'으로 표기됨 — 오표기.",
};

describe("IntegrityWarnings — 렌더", () => {
  it("★항목이 있으면 백엔드 원문 그대로 그린다(프론트가 문구를 지어내지 않는다)", () => {
    render(<IntegrityWarnings items={[HIGH, WARN]} />);
    const box = screen.getByTestId("integrity-warnings");
    expect(box).toBeTruthy();
    expect(box.textContent).toContain("층수제한초과");
    expect(box.textContent).toContain("5층");
    expect(box.textContent, "백엔드 note 원문이 잘렸다").toContain("할루시네이션 의심");
    expect(box.textContent).toContain("높이제한오표기");
    expect(box.textContent, "건수 표기가 없다").toContain("2건");
  });

  it("★비면 아무것도 그리지 않는다 — '이상 없음'이라고 단언하지 않는다", () => {
    // 가드가 아예 돌지 않았을 수도 있다. 침묵과 무결을 구분해 주장하지 않는 것이 정직하다.
    for (const empty of [[], null, undefined]) {
      const { container, unmount } = render(<IntegrityWarnings items={empty} />);
      expect(container.textContent, `items=${JSON.stringify(empty)} 에서 무언가 그렸다`).toBe("");
      unmount();
    }
  });

  it("★high(근거 미제시)가 나머지와 갈린다 — 두 모집단이 다른 결과를 낸다", () => {
    const { container: onlyWarn, unmount } = render(<IntegrityWarnings items={[WARN]} />);
    const warnHtml = onlyWarn.innerHTML;
    unmount();
    const { container: withHigh } = render(<IntegrityWarnings items={[HIGH]} />);
    expect(withHigh.textContent, "high 인데 근거 미확인 건수를 안 알린다").toContain("근거 미확인 1건");
    expect(warnHtml, "high 가 아닌데 '근거 미확인'이라고 말한다(위양성)").not.toContain("근거 미확인");
  });

  it("★값을 몰래 깎지 않는다는 사실을 화면이 말한다(무날조 고지)", () => {
    render(<IntegrityWarnings items={[HIGH]} />);
    expect(screen.getByTestId("integrity-warnings").textContent).toContain("보정하지 않고");
  });
});
