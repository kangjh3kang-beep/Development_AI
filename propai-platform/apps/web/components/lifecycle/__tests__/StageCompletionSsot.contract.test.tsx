import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { LifecycleProgressRail } from "@/components/lifecycle/LifecycleProgressRail";
import { ProjectHealthBoard } from "@/components/projects/ProjectHealthBoard";
import { useProjectContextStore, LIFECYCLE_STAGES } from "@/store/useProjectContextStore";

/**
 * 단계 완료 판정 SSOT 계약 — **같은 화면이 같은 단계를 두고 반대로 말하지 않는다**.
 *
 * ■ 무엇을 막는가 (실측된 결함)
 *   판정이 두 벌이었다. 같은 데이터·같은 화면인데 답이 반대였다:
 *     라이프사이클 레일  `stageHasData("site-analysis")` = 주소 **또는** zoneCode 만 있어도 true
 *                        → "부지분석 **완료**"
 *     헬스보드          `projectCompleteness().site.done` = 면적이 있어야 true
 *                        → "부지 **부분 완료**"
 *   그래서 사용자는 한 화면에서 진행률 **18%(2/11)** 와 완성도 **14%(1/7)** 를 동시에 봤다.
 *
 * ■ 왜 '완료'가 더 나쁜 쪽인가
 *   주소만 있는 부지를 "분석 완료"라 말하면, **설계·공사비·수지는 돌지 않는데 여정은 끝나
 *   가는 것처럼 보인다.** 이 캠페인이 고치는 '정밀도 위장'과 같은 병이다 —
 *   값이 없는데 있는 것처럼 보이게 하는 것.
 *
 * ■ 계약
 *   판정은 `store.stageCompletion` **하나**에서만 나온다(done/partial/none).
 *   두 화면은 분모가 다를 뿐(11 vs 7) **같은 단계에 같은 등급**을 준다.
 */

const ADDRESS = "충청남도 천안시 동남구 모산동 123-1";

function seedAddressOnly() {
  useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
  const ctx = useProjectContextStore.getState();
  ctx.setProject("p1", "모산동", "active");
  // 주소만 — 면적 없음. 프로젝트를 막 만든 직후의 실제 상태다.
  ctx.updateSiteAnalysis({ address: ADDRESS } as never);
}

function seedWithArea() {
  useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
  const ctx = useProjectContextStore.getState();
  ctx.setProject("p1", "모산동", "active");
  ctx.updateSiteAnalysis({ address: ADDRESS, landAreaSqm: 3836 } as never);
}

beforeEach(() => {
  useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
});

describe("단계 완료 판정 SSOT — 두 화면이 갈리지 않는다", () => {
  it("★주소만 있는 부지 — 두 판정이 **같이** '진행중'이라 답한다(종전엔 완료 vs 부분완료로 갈렸다)", () => {
    seedAddressOnly();
    const s = useProjectContextStore.getState();

    // 단일 판정자
    expect(s.stageCompletion("site-analysis")).toBe("partial");
    // 헬스보드가 쓰는 파생
    const site = s.projectCompleteness().stages.find((x) => x.key === "site")!;
    expect(site.done).toBe(false);
    expect(site.partial).toBe(true);
    // ★레일이 쓰는 판정 — 종전엔 여기가 true 라 "완료"였다. 이 줄이 회귀 락이다.
    expect(s.stageCompletion("site-analysis") === "done").toBe(false);
    // `stageHasData` 는 이름 그대로 "데이터가 있는가" — 여전히 true 여야 한다(무회귀).
    expect(s.stageHasData("site-analysis")).toBe(true);
  });

  it("면적이 확보되면 두 판정이 **같이** '완료'라 답한다(대조군 — 양성)", () => {
    seedWithArea();
    const s = useProjectContextStore.getState();
    expect(s.stageCompletion("site-analysis")).toBe("done");
    expect(s.projectCompleteness().stages.find((x) => x.key === "site")!.done).toBe(true);
  });

  it("★두 상태가 서로 다른 답을 낸다 — 어느 상태든 같은 답이면 락이 공허하다", () => {
    seedAddressOnly();
    const partial = useProjectContextStore.getState().stageCompletion("site-analysis");
    seedWithArea();
    const done = useProjectContextStore.getState().stageCompletion("site-analysis");
    expect(partial).not.toBe(done);
  });

  it("다필지 통합면적만으로도 완료다 — 면적은 effectiveLandAreaSqm(SSOT)로 읽는다", () => {
    useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
    const ctx = useProjectContextStore.getState();
    ctx.setProject("p1", "모산동", "active");
    // raw landAreaSqm 은 없고 통합면적만 있는 상태. raw 로 읽으면 "면적 없음"이 되어
    // 이미 확보된 부지가 미완료로 셈해진다.
    ctx.updateSiteAnalysis({
      address: ADDRESS, landAreaSqm: null, landAreaSqmTotal: 164823, parcelCount: 7,
    } as never);
    expect(useProjectContextStore.getState().stageCompletion("site-analysis")).toBe("done");
  });

  it("★레일이 주소만 있는 부지를 '완료 0/11' 로 표시하고 '진행중 1' 을 따로 밝힌다(렌더 경로)", () => {
    seedAddressOnly();
    render(<LifecycleProgressRail locale="ko" projectId="p1" />);

    // 전제 가드 — 배지가 실제로 렌더돼야 아래 단언이 의미를 갖는다(대상 0개 통과 방지).
    const badge = screen.getByText(/완료 \d+\//);
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain(`완료 0/${LIFECYCLE_STAGES.length}`);
    expect(badge.textContent).toContain("0%");
    // 한 일은 사라지지 않는다 — 진행중으로 인정한다.
    expect(badge.textContent).toContain("진행중 1");
  });

  it("★헬스보드는 분모가 무엇인지 밝힌다 — 벌거벗은 %는 레일과 모순처럼 읽힌다", () => {
    seedAddressOnly();
    render(<ProjectHealthBoard locale="ko" />);
    const section = screen.getByLabelText("프로젝트 완성도 헬스보드");
    expect(section.textContent).toContain("수치가 필요한 7단계");
    expect(section.textContent).toContain("여정 진행률과 분모가 다릅니다");
  });
});
