/**
 * ★필지 상세 팝오버 정직화 — 사용자 신고 ①② 를 직접 답한다(2026-08-23).
 *
 * ① **"실효 용적률 60% 가 이상하다"** → 값은 정확했다(제천시 조례값). 없던 것은 **근거**다.
 *    이제 실효값 아래에 `법정 80% · 조례 적용값(…)` 을 병기한다.
 *    ★법정==실효면 병기하지 않는다 — 같은 수를 두 번 보여 주지 않는다.
 *
 * ② **"현황 용적률 미확보"인데 건물 노후도는 "나대지·건물 없음"(단정)** → 한 화면이 같은 사실
 *    (`lookup_state=="no_data"`)을 두고 **확신과 모름을 동시에** 말했다. 백엔드는 이 상태를
 *    "나대지 **추정**"으로 분류하고 연면적은 보수적으로 `None` 으로 둔다 — 틀린 것은 **라벨**이다.
 *
 * 배선을 실 컴포넌트로 태운다: 판정·필드가 맞아도 팝오버에 안 붙으면 사용자에겐 아무 일도 없다.
 */
import type { ReactNode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { writeSatongMapSelection } from "@/components/precheck/satong-map-selection";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

const { boundaryCbRef } = vi.hoisted(() => ({
  boundaryCbRef: { current: null as null | ((f: Array<Record<string, unknown>>) => void) },
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// ★H2 봉합 이후 필수: 상세 패널은 SatongMultiMap 의 `topRightSlot` 으로 전달돼 **지도 래퍼
//   안**에서 렌더된다. 스텁이 그 슬롯을 버리면 패널이 DOM 에 아예 없어 검사가 공허해진다
//   (실제로 슬롯을 버린 스텁으로 짰다가 `parcel-detail-panel` 을 못 찾아 RED 로 적발됐다 —
//   CLAUDE.md 가 경고한 "테스트 스텁이 실제 층을 우회" 그 형태다).
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = ({ topRightSlot, onBoundaryEnriched }: {
      topRightSlot?: ReactNode;
      onBoundaryEnriched?: (f: Array<Record<string, unknown>>) => void;
    }) => {
      // ★경계 응답 역전파 콜백을 캡처한다 — 실서버는 이 경로로 값을 준다.
      //   캡처하지 않으면 병합(`SatongMapShell` 의 onBoundaryEnriched)이 **무잠금**으로 남는다
      //   (변이로 확인: 그 줄들을 지워도 전부 초록이었다).
      boundaryCbRef.current = onBoundaryEnriched ?? null;
      return <div data-testid="dynamic-map-stub">{topRightSlot}</div>;
    };
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

/**
 * 세션 미러로 시드한다 — ★스토어(`siteAnalysis.parcels`)로는 안 된다:
 * `legalFarPct`·`farBasis` 는 `effectiveFarPct` 선례와 같이 **런타임 전용**이라
 * 스토어 왕복(`selectionToSiteAnalysisPatch`)에 싣지 않는다. 스토어로 시드하면 그 필드가
 * 사라져 검사가 공허해진다(실제로 그렇게 짰다가 RED 로 적발됐다).
 */
function seed(parcel: Record<string, unknown>) {
  writeSatongMapSelection([
    {
      id: "P-honesty",
      address: "충청북도 제천시 금성면 성내리 산 7-2",
      source: "map",
      zoneType: "보전관리지역",
      jimok: "임야",
      areaSqm: 423,
      pnu: "4315031022200070002",
      ...parcel,
    } as never,
  ]);
}

/** 상세 패널을 연다 — ★조건부 렌더라 이 상태를 만들지 않으면 검사가 공허해진다.
 *  카드 라벨은 `parcelShortLabel`(동+지번) 파생이라 하드코딩하지 않고 정규식으로 찾는다. */
function openDetail(): HTMLElement {
  // 같은 짧은 라벨이 카드·지도 라벨 등 여러 곳에 나오므로 첫 번째(선택 목록 카드)를 쓴다.
  act(() => { fireEvent.click(screen.getAllByText(/산\s*7-2$/)[0]); });
  return screen.getByTestId("parcel-detail-panel");
}

describe("★팝오버 정직화 — 근거 병기 · 추정 표기", () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null } as never);
    });
  });

  it("① 실효(60)와 법정(80)이 다르면 **법정과 근거를 병기**한다", () => {
    seed({ effectiveFarPct: 60, legalFarPct: 80, farBasis: "조례 적용값(지자체 도시계획조례 적용값(법제처API))" });
    render(<SatongMapShell locale="ko" />);
    const panel = openDetail();

    const note = within(panel).getByTestId("far-basis-note");
    // 공허 진리 가드 — 실효값이 실제로 렌더됐는지 먼저 본다.
    expect(within(panel).getByText("60.0%")).toBeInTheDocument();
    expect(note.textContent).toContain("법정 80.0%");
    expect(note.textContent).toContain("조례 적용값");
  });

  it("★② 위양성 방지 — 법정==실효면 병기하지 않는다(같은 수를 두 번 보여 주지 않는다)", () => {
    seed({ zoneCode: "제2종일반주거지역", effectiveFarPct: 250, legalFarPct: 250, farBasis: "법정 상한" });
    render(<SatongMapShell locale="ko" />);
    const panel = openDetail();

    expect(within(panel).getByText("250.0%")).toBeInTheDocument(); // 대상 존재 가드
    expect(within(panel).queryByTestId("far-basis-note")).not.toBeInTheDocument();
  });

  it("★③ 무회귀 — 법정값이 아예 없으면(구 서버) 병기하지 않는다", () => {
    seed({ effectiveFarPct: 60 });
    render(<SatongMapShell locale="ko" />);
    const panel = openDetail();

    expect(within(panel).getByText("60.0%")).toBeInTheDocument();
    expect(within(panel).queryByTestId("far-basis-note")).not.toBeInTheDocument();
  });

  it("④ 건물 노후도는 **단정하지 않는다** — '나대지 추정(건축물대장 무자료)'", () => {
    seed({ ageStatus: "no_building" });
    render(<SatongMapShell locale="ko" />);
    const panel = openDetail();

    // ★같은 화면이 현황 용적률을 "모른다"고 하면서 건물 유무를 단정하면 안 된다.
    expect(within(panel).getByText("나대지 추정(건축물대장 무자료)")).toBeInTheDocument();
    expect(within(panel).queryByText("나대지·건물 없음")).not.toBeInTheDocument();
  });

  it("★⑥ 실서버 경로 — 경계 응답이 값을 주면 병합돼 팝오버까지 온다", () => {
    // ★앞의 케이스들은 필드가 **이미 있는** 상태를 검사한다. 실사용에서 그 값은 경계 API 가
    //   준다 — 그 역전파(`onBoundaryEnriched` 병합)가 끊기면 백엔드는 정상인데 화면만 빈다.
    seed({ effectiveFarPct: 60 }); // 법정·근거는 **아직 없다**
    render(<SatongMapShell locale="ko" />);
    expect(within(openDetail()).queryByTestId("far-basis-note")).not.toBeInTheDocument();

    // 경계 응답 도착 — 서버가 법정·근거를 준다.
    act(() => {
      boundaryCbRef.current?.([{
        pnu: "4315031022200070002",
        address: "충청북도 제천시 금성면 성내리 산 7-2",
        inputAddress: "충청북도 제천시 금성면 성내리 산 7-2",
        legalFarPct: 80,
        farBasis: "조례 적용값(지자체 도시계획조례 적용값(법제처API))",
      }]);
    });

    const note = within(screen.getByTestId("parcel-detail-panel")).getByTestId("far-basis-note");
    expect(note.textContent).toContain("법정 80.0%");
    expect(note.textContent).toContain("조례 적용값");
  });

  it("★⑤ 위양성 방지 — 다른 무자료 사유는 문구가 갈린다(나대지로 뭉뚱그리지 않는다)", () => {
    seed({ ageStatus: "no_approval_date" });
    render(<SatongMapShell locale="ko" />);
    const panel = openDetail();

    expect(within(panel).getByText("사용승인일 미기재(연식 미상)")).toBeInTheDocument();
    expect(within(panel).queryByText(/나대지/)).not.toBeInTheDocument();
  });
});
