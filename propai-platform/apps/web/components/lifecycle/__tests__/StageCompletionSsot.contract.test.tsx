import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LifecycleProgressRail } from "@/components/lifecycle/LifecycleProgressRail";
import { ProjectHealthBoard } from "@/components/projects/ProjectHealthBoard";
import { ProjectAddressBar } from "@/components/projects/ProjectAddressBar";
import { ProjectLifecyclePipeline } from "@/components/projects/ProjectLifecyclePipeline";
import { useProjectContextStore, LIFECYCLE_STAGES } from "@/store/useProjectContextStore";

// 라우터 훅 — 이 테스트의 대상은 판정 배선이라 경로는 고정값으로 충분하다.
vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko", id: "p1" }),
  usePathname: () => "/ko/projects/p1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

/**
 * 단계 완료 판정 SSOT 계약 — **같은 화면이 같은 단계를 두고 반대로 말하지 않는다**.
 *
 * ■ 무엇을 막는가 (실측된 결함)
 *   판정이 두 벌이었다. 같은 데이터·같은 화면인데 답이 반대였다:
 *     라이프사이클 레일  `stageHasData("site-analysis")` = 주소 **또는** zoneCode 만 있어도 true
 *                        → "부지분석 **완료**"
 *     헬스보드          `projectCompleteness().site.done` = 면적이 있어야 true
 *                        → "부지 **부분 완료**"
 *   그래서 한 화면에 진행률이 **두 개** 나온다 — 분모가 11(여정)과 7(수치 필요 분석)로 다른데
 *   둘 다 "진행/완성도"라고만 적혀 있고, 게다가 **같은 단계에 다른 등급**을 준다.
 *   ※ 출처 라벨(실수 #39 의 처방): 분모 11·7 과 두 판정의 상반은 **이 저장소 코드에서 잰 것**이다.
 *   인계서가 보고한 특정 화면의 수치(18% vs 14%)는 내가 라이브에서 재확인하지 않았으므로
 *   여기서 관측 사실로 인용하지 않는다 — 픽스처는 아래에서 직접 만든다.
 *
 * ■ 왜 '완료'가 더 나쁜 쪽인가
 *   주소만 있는 부지를 "분석 완료"라 말하면, **설계·공사비·수지는 돌지 않는데 여정은 끝나
 *   가는 것처럼 보인다.** 이 캠페인이 고치는 '정밀도 위장'과 같은 병이다 —
 *   값이 없는데 있는 것처럼 보이게 하는 것.
 *
 * ■ 계약
 *   판정은 `store.stageCompletion` **하나**에서만 나온다(done/partial/none).
 *   두 화면은 분모가 다를 뿐(11 vs 7) **같은 단계에 같은 등급**을 준다.
 *
 * ■ 변이 검증 후 남은 생존 — **의도적 비잠금**이므로 여기 적어 둔다(점수 부풀리기 방지)
 *   · `className="…"` 문자열 3건(레일 partial 스타일·주소배지) — 색상·간격은 잠그지 않는다.
 *     상태·문구·분모는 위 단언들이 잠근다.
 *   · `stageCompletion: (stageId: string) => …` 인터페이스 선언 — 타입 층이라
 *     `tsc --noEmit` 이 잡는다(CI 게이트).
 *   · 주석 문자열 1건 — 동작에 영향이 없다.
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

/**
 * ★키 매핑표(완성도 7키 → 라이프사이클 단계) 락.
 *
 * 변이 검증에서 `["cost", "construction", "공사비"]` 의 문자열을 바꿔도 **아무도 죽지 않았다**.
 * 나는 `site` 만 단언하고 나머지 여섯을 방치했다 — 표가 장식이 되어 있었다.
 * 각 단계의 데이터를 **그 단계만** 채우고, 대응하는 키 **하나만** done 이 되는지 본다
 * (매핑이 어긋나면 엉뚱한 키가 켜지거나 아무 키도 안 켜져 죽는다).
 */
describe("완성도 7키 ↔ 라이프사이클 단계 매핑표", () => {
  function reset() {
    useProjectContextStore.setState({
      siteAnalysis: null, designData: null, costData: null, complianceData: null,
      esgData: null, completedStages: [], updatedAt: {},
    } as never);
    useProjectContextStore.getState().setProject("p1", "모산동", "active");
  }

  const CASES: Array<[string, () => void]> = [
    ["site", () => useProjectContextStore.getState().updateSiteAnalysis({ address: "주소", landAreaSqm: 100 } as never)],
    ["design", () => useProjectContextStore.setState({ designData: { totalGfaSqm: 1000 } } as never)],
    ["cost", () => useProjectContextStore.setState({ costData: { totalConstructionCostWon: 1 } } as never)],
    ["compliance", () => useProjectContextStore.setState({ complianceData: { farCompliant: true } } as never)],
    ["finance", () => useProjectContextStore.getState().markFinanceUpdated()],
    ["esg", () => useProjectContextStore.setState({ esgData: { totalCarbonPerSqm: 1 } } as never)],
    ["permit", () => useProjectContextStore.setState({ completedStages: ["permit"] } as never)],
  ];

  it.each(CASES)("%s 키는 그 단계의 데이터로만 켜진다(오매핑 시 죽는다)", (key, seed) => {
    reset();
    seed();
    const done = useProjectContextStore
      .getState()
      .projectCompleteness()
      .stages.filter((st) => st.done)
      .map((st) => st.key);
    expect(done).toEqual([key]);
  });
});

describe("남은 두 표면의 렌더 배선", () => {
  function seedAddressOnlyLocal() {
    useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
    const ctx = useProjectContextStore.getState();
    ctx.setProject("p1", "모산동", "active");
    ctx.updateSiteAnalysis({ address: "충청남도 천안시 동남구 모산동 123-1" } as never);
  }

  it("★주소 배지가 분모를 함께 말한다 — 벌거벗은 %는 레일과 모순처럼 읽힌다", () => {
    seedAddressOnlyLocal();
    render(<ProjectAddressBar />);
    const chip = screen.getByText(/분석 완성도/);
    expect(chip.textContent).toContain("0/7");
    // 툴팁(분모 설명)이 지워지면 사용자는 다시 두 숫자를 모순으로 읽는다.
    expect(chip.getAttribute("title") ?? "").toContain("라이프사이클 진행률과 분모가 다릅니다");
  });

  it("★파이프라인은 진행중(partial) 단계를 **완료가 아니라 현재**로 표시한다", () => {
    seedAddressOnlyLocal();
    const { container } = render(<ProjectLifecyclePipeline locale="ko" projectId="p1" />);
    // 전제 가드 — 부지분석 노드가 실제로 렌더돼야 아래 단언이 의미를 갖는다.
    const node = container.querySelector('[data-stage-id="site-analysis"]');
    expect(node, "부지분석 노드가 렌더되지 않았다").not.toBeNull();
    // ★주소만 있는 부지는 **완료가 아니다**(종전엔 completed 였다) — 현재 단계로 안내한다.
    expect(node!.getAttribute("data-stage-status")).toBe("current");
    expect(node!.getAttribute("data-stage-status")).not.toBe("completed");
  });

  it("★대조군 — 면적이 확보되면 같은 노드가 completed 로 바뀐다(두 상태가 달라야 락이 성립)", () => {
    useProjectContextStore.setState({ siteAnalysis: null, completedStages: [] } as never);
    const ctx = useProjectContextStore.getState();
    ctx.setProject("p1", "모산동", "active");
    ctx.updateSiteAnalysis({ address: "충청남도 천안시 동남구 모산동 123-1", landAreaSqm: 3836 } as never);
    const { container } = render(<ProjectLifecyclePipeline locale="ko" projectId="p1" />);
    const node = container.querySelector('[data-stage-id="site-analysis"]');
    expect(node!.getAttribute("data-stage-status")).toBe("completed");
  });
});
