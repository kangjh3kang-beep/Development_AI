// SeniorVerdictCard — 시니어 자문 verdict 공용 카드 렌더 테스트.
// graceful(미가용/없음 미렌더) + verdict 배지 + 도메인별 정량판정 노출 검증.

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";

const SAMPLE: SeniorConsultation = {
  verdict: "BLOCK",
  citations: ["건축법 제61조"],
  needs_expert_review: true,
  honest_notes: "정비사업 입력 미비로 일부 판정 생략",
  consultations: [
    {
      agent_key: "senior_deliberation_member",
      name_ko: "심의위원",
      verdict: "BLOCK",
      confidence_label: "높은 신뢰",
      citations: ["건축법 제61조"],
      evaluations: [
        {
          rule_id: "delib.far_csp",
          label: "용적률 적합성",
          value: 400,
          unit: "%",
          verdict: "BLOCK",
          threshold: "≤250%",
          detail: "제안 400% > 법정 250%",
        },
      ],
    },
    {
      agent_key: "senior_urban_planner",
      name_ko: "도시계획",
      verdict: null,
      evaluations: [],
    },
  ],
};

describe("SeniorVerdictCard", () => {
  it("consultation이 없으면 렌더하지 않는다", () => {
    const { container } = render(<SeniorVerdictCard consultation={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("verdict='unavailable'이면 렌더하지 않는다(정직·노이즈 방지)", () => {
    const { container } = render(
      <SeniorVerdictCard
        consultation={{ verdict: "unavailable", consultations: [] }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("consultations가 비면 렌더하지 않는다", () => {
    const { container } = render(
      <SeniorVerdictCard consultation={{ verdict: "PASS", consultations: [] }} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("종합 verdict 배지와 전문가 검토 권장을 헤더에 표시한다", () => {
    render(<SeniorVerdictCard consultation={SAMPLE} title="시니어 자문" />);
    expect(screen.getByText("시니어 자문")).toBeTruthy();
    // 종합 BLOCK → '차단' 라벨.
    expect(screen.getByText(/종합 차단/)).toBeTruthy();
    expect(screen.getByText("전문가 검토 권장")).toBeTruthy();
  });

  it("펼치면 도메인별 정량 판정(evaluations)과 근거를 노출한다", () => {
    render(<SeniorVerdictCard consultation={SAMPLE} defaultOpen />);
    expect(screen.getByText("심의위원")).toBeTruthy();
    expect(screen.getByText("도시계획")).toBeTruthy();
    expect(screen.getByText("용적률 적합성")).toBeTruthy();
    expect(screen.getByText(/제안 400% > 법정 250%/)).toBeTruthy();
    // citation chip.
    expect(screen.getAllByText("건축법 제61조").length).toBeGreaterThan(0);
    // honest note.
    expect(screen.getByText(/정비사업 입력 미비/)).toBeTruthy();
  });

  it("정량 verdict 없는 정성 자문(finance 프레임워크 전용)도 카드를 렌더한다", () => {
    // 시장보고서 경로: finance 단일도메인·verdict null·evaluations 빈 배열(총사업비만 전달).
    const frameworkOnly: SeniorConsultation = {
      verdict: null,
      consultations: [
        { agent_key: "senior_financial_advisor", name_ko: "금융전문가", verdict: null, evaluations: [] },
      ],
    };
    render(<SeniorVerdictCard consultation={frameworkOnly} title="시니어 금융 자문" />);
    // 정량 verdict 없으므로 '정성 자문' 안내 + 도메인명 노출, crash 없음.
    expect(screen.getByText(/정성 자문/)).toBeTruthy();
    expect(screen.getByText("시니어 금융 자문")).toBeTruthy();
  });

  it("접힘/펼침 토글이 동작한다", () => {
    render(<SeniorVerdictCard consultation={SAMPLE} />);
    // 기본 접힘 — evaluations 미표시.
    expect(screen.queryByText("용적률 적합성")).toBeNull();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("용적률 적합성")).toBeTruthy();
  });
});
