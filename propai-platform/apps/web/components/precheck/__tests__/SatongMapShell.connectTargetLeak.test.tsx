/**
 * SatongMapShell 연결 대상 전환 시 선택 필지 누수 봉합(레인F P0 — 사용자 버그리포트).
 *
 * 증상: "연결 프로젝트" 드롭다운을 "새 프로젝트로 등록" 또는 "프로젝트 연결 안 함(약식 분석)"
 *   으로 바꿔도 이전 프로젝트의 선택 필지가 그대로 잔존했다. 근본원인 = handleConnectTargetChange
 *   가 가드 전용 함수(detachProjectCarryingSelection)만 호출하고 선택목록은 비우지 않았다.
 *
 * 이 스위트는 수정 후 계약을 고정한다:
 *   ① 드롭다운을 new/none으로 바꾸면 선택 목록이 0건이 된다.
 *   ② sessionStorage(satong_map_selection) 미러도 함께 제거된다.
 *   ③ 지도 staged 폴리곤 청소 신호(clearSignal)도 증가한다(WP-M2 대칭).
 *   ④ 무음 금지 — connectNotice로 사용자에게 고지한다.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { SATONG_MAP_SELECTION_KEY } from "@/components/precheck/satong-map-selection";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// next/dynamic(SatongMultiMap)은 jsdom에서 Leaflet 실로드가 불가 — 스텁으로 대체.
// ★clearSignal(=clearNonce prop)을 캡처해 P0-2(지도 staged 폴리곤 청소 대칭)를 검증한다.
const { capturedMapPropsRef } = vi.hoisted(() => ({
  capturedMapPropsRef: { current: null as null | { clearSignal?: number } },
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: { clearSignal?: number }) => {
      // eslint-disable-next-line react-hooks/immutability -- 테스트 전용 스텁: 지도 props(clearSignal) 캡처
      capturedMapPropsRef.current = props;
      return <div data-testid="dynamic-map-stub" />;
    };
    return DynamicStub;
  },
}));

// 네트워크 차단: /projects 동기화·검색·레이어 조회 전부 영구 pending으로 고정.
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      post: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

function makeProject(partial: Partial<Project>): Project {
  return {
    id: "proj-leak",
    name: "청진동 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 종로구 청진동 1",
    area: "120㎡",
    status: "draft",
    createdAt: "2026-06-01T00:00:00.000Z",
    ...partial,
  };
}

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  } as SiteAnalysisData;
}

describe("SatongMapShell 연결 대상 전환 — 선택 필지 누수 봉합", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [makeProject({})], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({
          address: "서울특별시 종로구 청진동 1",
          parcels: [
            {
              pnu: "1111010100100010000",
              address: "서울특별시 종로구 청진동 1",
              areaSqm: 120,
              landCategory: "대",
              ownerType: "미확인",
              zoneCode: "일반상업지역",
            },
          ],
        } as Partial<SiteAnalysisData>),
      });
    });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("드롭다운을 '새 프로젝트로 등록'으로 바꾸면 선택 필지·세션캐시·지도 staged 폴리곤이 모두 비워지고 고지된다", () => {
    render(<SatongMapShell locale="ko" />);

    // 사전조건: 연결 프로젝트 필지가 선택 목록에 하이드레이션돼 있어야 한다.
    expect(screen.getByText("청진동 1")).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // ① 선택 0건
    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(screen.getByText("아직 선택된 필지가 없습니다.")).toBeInTheDocument();
    // ② sessionStorage 미러 제거
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    // ③ 지도 staged 폴리곤 청소 신호 증가(WP-M2 대칭)
    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
    // ④ 무음 금지 — 고지 문구
    expect(screen.getByText("연결 대상을 바꿔 선택 필지를 비웠습니다.")).toBeInTheDocument();
  });

  it("드롭다운을 '프로젝트 연결 안 함(약식 분석)'으로 바꿔도 동일하게 비워진다", () => {
    render(<SatongMapShell locale="ko" />);

    expect(screen.getByText("청진동 1")).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "none" } });
    });

    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    expect(screen.getByText("연결 대상을 바꿔 선택 필지를 비웠습니다.")).toBeInTheDocument();
  });

  it("비울 선택이 없으면(이미 0건) 무음 유지 — 불필요한 고지 남발 방지", () => {
    // 프로젝트는 연결돼 있으나 필지는 없는 상태(주소도 없음)로 재설정.
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({}),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "none" } });
    });

    expect(
      screen.queryByText("연결 대상을 바꿔 선택 필지를 비웠습니다."),
    ).not.toBeInTheDocument();
  });

  it("R1b: 선택 0건이어도 clearSignal은 증가한다 — 지도 staged 폴리곤 정리가 조건 없이 실행됨을 고정", () => {
    // 확정 목록(selectedParcels)은 0건이지만, 사용자가 지도에서 필지를 찍어 SatongMultiMap
    // 내부 staged(녹색, 아직 [완료] 안 누름)에 쌓아둔 뒤 드롭다운을 바꾸는 순서를 재현한다.
    // staged는 SatongMultiMap 내부 상태라 이 스텁에서 직접 만들 수는 없지만, clearParcels가
    // "비울 selectedParcels가 없다"는 이유로 스킵되지 않고 항상 실행돼야 한다는 계약은
    // selectedParcels가 0인 채로도 clearSignal이 오른다는 사실로 고정할 수 있다(고지만 조건부,
    // 정리는 무조건 — 게이팅 대상이 다르다).
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({}),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
    // 정리는 실행됐지만 비울 확정목록이 없었으므로 고지는 여전히 없다(고지 조건 유지).
    expect(
      screen.queryByText("연결 대상을 바꿔 선택 필지를 비웠습니다."),
    ).not.toBeInTheDocument();
  });
});
