/**
 * ★렌더 락 — 소스 grep 이 아니라 **화면에 실제로 나온 글자**를 본다.
 *
 * 이 저장소는 소스 검사가 "주석 처리 + 임포트 유지" 변이에 두 번 뚫렸다(CLAUDE.md §A-3).
 * 그래서 필지 라벨의 계약은 DOM 으로 잠근다.
 *
 * 세 모집단이 **서로 다른 DOM** 을 내야 한다 — 같으면 배선을 끊어도 초록이다.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ParcelJibunLabel, PARCEL_JIBUN_UNRESOLVED_TEXT } from "@/components/precheck/ParcelJibunLabel";

const DONG = "경기도 오산시 내삼미동";

describe("ParcelJibunLabel — 세 모집단", () => {
  it("(A) 진짜 PNU 보유 → 지번이 화면에 나온다", () => {
    render(<ParcelJibunLabel address={DONG} pnu="4137011000104670001" />);
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("내삼미동 467-1");
    expect(screen.queryByTestId("parcel-jibun-unresolved")).toBeNull();
  });

  it("(B) 주소에 지번 보유(PNU 없음) → 그대로 나오고 경고 없음", () => {
    render(<ParcelJibunLabel address={`${DONG} 114-1`} pnu={null} />);
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("내삼미동 114-1");
    expect(screen.queryByTestId("parcel-jibun-unresolved")).toBeNull();
  });

  it("★(C) 앵커 없음 → 지번을 지어내지 않고 '지번 미확인' 을 **말한다**", () => {
    render(<ParcelJibunLabel address={DONG} pnu={null} />);
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 내삼미동");
    expect(screen.getByTestId("parcel-jibun-unresolved")).toHaveTextContent(
      PARCEL_JIBUN_UNRESOLVED_TEXT,
    );
    // 지번처럼 보이는 숫자를 만들어내지 않았는지 확인(날조 금지).
    expect(screen.getByTestId("parcel-jibun-text").textContent).not.toMatch(/\d/);
  });

  it("★가짜 PNU(주소가 PNU 칸에 들어앉음)는 (C)와 같은 화면 — 조용히 넘어가지 않는다", () => {
    render(<ParcelJibunLabel address={DONG} pnu={DONG} />);
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 내삼미동");
    expect(screen.getByTestId("parcel-jibun-unresolved")).toBeInTheDocument();
  });

  it("★세 모집단의 DOM 이 **서로 다르다**(같으면 배선을 끊어도 통과한다)", () => {
    const { container: a } = render(<ParcelJibunLabel address={DONG} pnu="4137011000104670001" />);
    const { container: b } = render(<ParcelJibunLabel address={`${DONG} 114-1`} pnu={null} />);
    const { container: c } = render(<ParcelJibunLabel address={DONG} pnu={null} />);
    const texts = [a, b, c].map((el) => el.textContent);
    expect(new Set(texts).size).toBe(3);
  });

  it("★같은 동 77필지가 화면에서 **서로 구분된다**(실제 신고: 77행이 전부 같은 글자)", () => {
    const pnus = Array.from({ length: 77 }, (_, i) => `41370110001${String(1000 + i).padStart(4, "0")}0000`);
    const { container } = render(
      <ul>
        {pnus.map((pnu) => (
          <li key={pnu}>
            <ParcelJibunLabel address={DONG} pnu={pnu} />
          </li>
        ))}
      </ul>,
    );
    const rows = within(container).getAllByTestId("parcel-jibun-text");
    expect(rows).toHaveLength(77); // 공허 진리 가드: 검사 대상이 실제로 렌더됐다
    expect(new Set(rows.map((r) => r.textContent)).size).toBe(77);
  });
});
