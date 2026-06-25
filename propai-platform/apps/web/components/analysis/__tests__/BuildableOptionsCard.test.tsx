// BuildableOptionsCard — 건축가능항목 랭킹 카드 렌더 테스트.
// graceful(없음 미렌더) + 랭킹/인허가배지/현행·종상향 + similar_designs 노출 검증.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { BuildableOptionsCard, type BuildableOptions } from "@/components/analysis/BuildableOptionsCard";

const SAMPLE: BuildableOptions = {
  summary: "현행 제2종일반주거 기준 건축가능 사업유형 3건을 랭킹했습니다.",
  disclaimer: "현행은 실효(조례) 사실값, 종상향은 예상치입니다.",
  current_zone: "제2종일반주거지역",
  top_recommendation: { product: "주상복합", achievable_far_pct: 400, permit_feasibility: "중", is_current: false },
  options: [
    {
      product: "주상복합",
      achievable_far_pct: 400,
      permit_feasibility: "중",
      permit_difficulty: "보통~어려움 — 종상향 조건부",
      via: "지구단위계획 수립",
      zone: "준주거지역",
      is_current: false,
      is_upzoning: true,
      similar_designs: { count: 2, results: [{ title: "APT_FP.jpg", drawing_type: "floor_plan" }] },
    },
    {
      product: "공동주택(아파트)",
      achievable_far_pct: 200,
      permit_feasibility: "현행",
      via: "현행 용도지역",
      zone: "제2종일반주거지역",
      is_current: true,
    },
  ],
};

describe("BuildableOptionsCard", () => {
  it("data가 없으면 렌더하지 않는다", () => {
    const { container } = render(<BuildableOptionsCard data={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("options가 비면 렌더하지 않는다", () => {
    const { container } = render(<BuildableOptionsCard data={{ options: [] }} />);
    expect(container.firstChild).toBeNull();
  });

  it("최우선 사업유형·랭킹·가용용적률·인허가가능성을 노출한다", () => {
    render(<BuildableOptionsCard data={SAMPLE} />);
    expect(screen.getByText("건축가능항목 랭킹")).toBeTruthy();
    expect(screen.getByText("최우선 주상복합")).toBeTruthy();
    expect(screen.getByText(/가용 용적률 400%/)).toBeTruthy();
    expect(screen.getByText("공동주택(아파트)")).toBeTruthy();
    // 현행/종상향 구분 배지.
    expect(screen.getByText("현행 가능")).toBeTruthy();
    expect(screen.getByText("종상향 전제(예상)")).toBeTruthy();
  });

  it("Stage3 유사 설계 도면을 노출한다", () => {
    render(<BuildableOptionsCard data={SAMPLE} />);
    expect(screen.getByText(/APT_FP.jpg/)).toBeTruthy();
  });

  it("유사 설계 미확보(count 0·skipped_reason)·permit_feasibility 누락도 안전 렌더", () => {
    // 프로덕션 흔한 상태: 임베딩 미가용 → count 0 + skipped_reason. permit_feasibility 누락.
    const data: BuildableOptions = {
      options: [
        {
          product: "오피스텔",
          achievable_far_pct: 400,
          via: "현행 용도지역",
          is_current: true,
          similar_designs: { count: 0, results: [], skipped_reason: "embed_dim_mismatch" },
        },
      ],
    };
    render(<BuildableOptionsCard data={data} />);
    expect(screen.getByText("오피스텔")).toBeTruthy();
    // 유사 설계 라벨 미노출(count 0).
    expect(screen.queryByText(/유사 설계:/)).toBeNull();
    // permit_feasibility 누락 시 '확인필요' 폴백(literal 'undefined' 미노출).
    expect(screen.getByText(/인허가 확인필요/)).toBeTruthy();
    expect(screen.queryByText(/인허가 undefined/)).toBeNull();
  });
});
