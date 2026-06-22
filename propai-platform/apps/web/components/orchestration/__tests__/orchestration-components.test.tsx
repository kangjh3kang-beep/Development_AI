// 오케스트레이션 컴포넌트 렌더 스모크 — Phase B B3
// 정직고지(미가용·신선·검증 배지)·모드스위처 활성/비활성·플랜 미리보기·입력해소 모달의 핵심 렌더 단언.
// store/엔진은 mock하지 않고, props로 결과를 직접 주입해 표시 로직만 검증한다(순수 렌더).

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// @propai/ui는 사전 컴파일된 jsxDEV 번들이라 vitest(jsx-dev-runtime 미해소)에서 import 실패한다
// (기존 32개 컴포넌트 테스트가 동일 사유로 사전 실패 중인 환경 이슈). Card/CardContent는 단순 래퍼라
// 렌더 스모크 목적상 div로 대체 mock한다(컴포넌트 로직 미변경, 표시 단언만 검증).
vi.mock("@propai/ui", () => ({
  Card: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
  CardContent: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
}));

import { NodeRunCard } from "@/components/orchestration/NodeRunCard";
import { RunModeSwitcher } from "@/components/orchestration/RunModeSwitcher";
import { PlanPreview } from "@/components/orchestration/PlanPreview";
import { RunProgressTimeline } from "@/components/orchestration/RunProgressTimeline";
import { InputResolveModal } from "@/components/orchestration/InputResolveModal";
import type { NodeResult, RunStep } from "@/store/useOrchestrationStore";

function mkResult(over: Partial<NodeResult>): NodeResult {
  return {
    state: "done",
    verifyStatus: null,
    grounding: {},
    chargedKrw: 0,
    inputSignature: null,
    at: Date.now(),
    ...over,
  };
}

describe("NodeRunCard — 상태·검증·그라운딩 정직고지", () => {
  it("done + verify pass + grounding ok 표기", () => {
    render(
      <NodeRunCard
        nodeId="land"
        result={mkResult({
          state: "done",
          verifyStatus: "pass",
          grounding: { VWorld: "ok", "NED 토지특성": "unavailable" },
        })}
      />,
    );
    expect(screen.getByText("토지·부지분석")).toBeInTheDocument();
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("검증 통과")).toBeInTheDocument();
    // 그라운딩: ok/unavailable 모두 정직 표기(0 강제 금지). VWorld는 근거 부제+배지 2곳 등장 → 다중 허용.
    expect(screen.getAllByText(/VWorld/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NED 토지특성/).length).toBeGreaterThan(0);
    // 미확보 슬롯 배지(— 표기) 존재.
    expect(screen.getByTitle("미확보(정직 표기)")).toBeInTheDocument();
  });

  it("available:true(audit, 심의엔진 BFF 통합)는 라벨 표기 + 미가용 라벨 비표기", () => {
    render(<NodeRunCard nodeId="audit" />);
    expect(screen.getByText("AI 설계심의")).toBeInTheDocument();
    // 심의분석엔진 BFF 풀통합으로 audit 노드 unlock(node-registry available:true) →
    // !node.available 분기의 미가용 라벨("심의엔진 연결 대기")은 렌더되지 않는다.
    expect(screen.queryByText("심의엔진 연결 대기")).not.toBeInTheDocument();
  });

  it("error 상태는 오류 메시지 표기 + 다시 실행 CTA", () => {
    const onRun = vi.fn();
    render(
      <NodeRunCard
        nodeId="legal"
        result={mkResult({ state: "error", error: "500" })}
        onRun={onRun}
      />,
    );
    expect(screen.getByText(/오류: 500/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "다시 실행" }));
    expect(onRun).toHaveBeenCalledWith("legal");
  });
});

describe("RunModeSwitcher — 활성/비활성", () => {
  it("별도·선택·프로필(B5)은 활성, 가이드(B4)만 비활성 정직 표기", () => {
    const onChange = vi.fn();
    render(<RunModeSwitcher value="selective" onChange={onChange} />);
    // 가이드만 준비중 배지(프로필은 B5 활성이라 배지 없음).
    expect(screen.getByText("준비중(B4)")).toBeInTheDocument();
    expect(screen.queryByText("준비중(B5)")).not.toBeInTheDocument();
  });

  it("활성 탭 클릭은 onChange 호출, 비활성 탭은 호출 안 함", () => {
    const onChange = vi.fn();
    render(<RunModeSwitcher value="selective" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: /별도/ }));
    expect(onChange).toHaveBeenCalledWith("standalone");
    onChange.mockClear();
    // 프로필(B5 활성) — 클릭 시 onChange 호출.
    fireEvent.click(screen.getByRole("tab", { name: /프로필/ }));
    expect(onChange).toHaveBeenCalledWith("profile");
    onChange.mockClear();
    // 가이드(비활성) — disabled라 클릭해도 onChange 미발생.
    fireEvent.click(screen.getByRole("tab", { name: /가이드/ }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("PlanPreview — 폐포·신선스킵·과금합계 선표시", () => {
  const steps: RunStep[] = [
    { node: "land", reason: "closure", skipped: true, skipReason: "fresh", chargeable: false, estimatedKrw: 0 },
    { node: "design", reason: "closure", skipped: false, chargeable: true, estimatedKrw: 0 },
    { node: "sales", reason: "selected", skipped: false, chargeable: true, estimatedKrw: 3000 },
    { node: "audit", reason: "closure", skipped: true, skipReason: "unavailable", chargeable: false, estimatedKrw: 0 },
  ];

  it("실행/스킵 개수·최신스킵·미가용제외 표기", () => {
    render(<PlanPreview steps={steps} />);
    expect(screen.getByText(/실행 2개/)).toBeInTheDocument();
    expect(screen.getByText(/최신 1개는 재실행/)).toBeInTheDocument();
    expect(screen.getByText(/미가용 1개 제외/)).toBeInTheDocument();
  });

  it("과금 합계 표기(estimatedKrw 합 = 3,000원)", () => {
    render(<PlanPreview steps={steps} />);
    // sales 행(per-step) + 총합 두 곳에 3,000원 등장 → 다중 허용(합계 b 태그 별도 단언).
    expect(screen.getAllByText(/3,000원/).length).toBeGreaterThanOrEqual(2);
  });

  it("unlimited 등급은 '무제한' 표기", () => {
    render(<PlanPreview steps={steps} unlimited />);
    expect(screen.getByText(/무제한\(관리자\)/)).toBeInTheDocument();
  });

  it("빈 계획은 안내 placeholder(가짜 진행 금지)", () => {
    render(<PlanPreview steps={[]} />);
    expect(screen.getByText(/분석 항목을 선택하면/)).toBeInTheDocument();
  });
});

describe("RunProgressTimeline — 진행 집계", () => {
  it("plan 비면 안내만(가짜 진행률 금지)", () => {
    render(<RunProgressTimeline plan={[]} nodeResult={{}} />);
    expect(screen.getByText(/분석을 실행하면/)).toBeInTheDocument();
  });

  it("완료 카운트 집계 + 노드 카드 렌더", () => {
    render(
      <RunProgressTimeline
        plan={["land", "design"]}
        nodeResult={{ land: mkResult({ state: "done" }) }}
      />,
    );
    expect(screen.getByText(/완료 1\/2/)).toBeInTheDocument();
    expect(screen.getByText("토지·부지분석")).toBeInTheDocument();
    expect(screen.getByText("건축개요·설계 AI")).toBeInTheDocument();
  });
});

describe("InputResolveModal — 입력 자동해소(자동실행 금지·동의식)", () => {
  it("미확보 입력 + 업스트림 자동실행 동의 버튼(클릭 시 콜백)", () => {
    const onAuto = vi.fn();
    render(
      <InputResolveModal
        nodeId="design"
        resolution={{
          ready: [],
          missing: [
            {
              slot: "siteAnalysis",
              readyCheck: () => false,
              resolution: ["ssot", "upstream-suggest"],
              provenanceGuarded: true,
            },
          ],
          autoCandidates: ["land", "recommend"],
        }}
        onClose={vi.fn()}
        onRun={vi.fn()}
        onAutoRunUpstream={onAuto}
        onManualSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText(/미확보 입력 1개/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /업스트림 2개 자동 실행/ });
    fireEvent.click(btn);
    expect(onAuto).toHaveBeenCalledWith("design", ["land", "recommend"]);
  });

  it("모든 입력 확보 시 '바로 실행' 버튼", () => {
    const onRun = vi.fn();
    render(
      <InputResolveModal
        nodeId="land"
        resolution={{
          ready: [
            {
              slot: "siteAnalysis",
              field: "address",
              readyCheck: () => true,
              resolution: ["ssot", "manual"],
              manualPrompt: "주소를 입력하세요",
              provenanceGuarded: true,
            },
          ],
          missing: [],
          autoCandidates: [],
        }}
        onClose={vi.fn()}
        onRun={onRun}
        onAutoRunUpstream={vi.fn()}
        onManualSubmit={vi.fn()}
      />,
    );
    const btn = screen.getByRole("button", { name: /바로 실행/ });
    fireEvent.click(btn);
    expect(onRun).toHaveBeenCalledWith("land");
  });
});
