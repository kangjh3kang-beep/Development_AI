/**
 * SatongMapShell 연결 대상 전환 시 선택 필지 누수 봉합(레인F P0 — 사용자 버그리포트) → R2 교정.
 *
 * 증상(R1): "연결 프로젝트" 드롭다운을 "새 프로젝트로 등록" 또는 "프로젝트 연결 안 함(약식 분석)"
 *   으로 바꿔도 이전 프로젝트의 선택 필지가 그대로 잔존했다.
 *
 * R1 수정("무조건 clearParcels()")의 잘못(R2 리뷰어 프로브 실증): 상도동 프로젝트 연결 상태에서
 *   사용자가 지도로 같은 지역(상도동) 필지를 직접 담으면(가드 미발화) 그 방금 고른 선택까지
 *   삭제됐다 — addParcels 가드 경로(선택 항상 보존)와 정반대 계약. 소유권(selectionOwnerProjectIdRef)
 *   으로 "프로젝트에서 상속된 선택"과 "사용자가 직접 담은 선택"을 가른다.
 *
 * 이 스위트가 고정하는 계약:
 *   ① 프로젝트에서 상속된 선택 → 드롭다운 전환 시 비워진다(원 버그리포트 재현 봉합).
 *   ② 사용자가 직접 담은 선택(같은 지역, 가드 미발화) → 드롭다운 전환에도 보존된다(R2 신규 손실 방지).
 *   ③ 지도 staged 폴리곤 청소 신호(clearSignal)는 소유권과 무관하게 항상 증가한다(R1b 결정 유지).
 *   ④ sessionStorage(satong_map_selection) 미러도 확정목록을 비울 때 함께 제거된다(실제 게이트).
 *   ⑤ 무음 금지 — 실제로 비웠을 때만 connectNotice로 고지한다.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  SATONG_MAP_SELECTION_KEY,
  writeSatongMapSelection,
} from "@/components/precheck/satong-map-selection";
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
// ★clearSignal(=clearNonce)과 onPickMany(가드/사용자편집 재현용)을 캡처한다.
const { capturedMapPropsRef } = vi.hoisted(() => ({
  capturedMapPropsRef: {
    current: null as null | {
      clearSignal?: number;
      onPickMany?: (parcels: unknown[]) => void;
    },
  },
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: {
      clearSignal?: number;
      onPickMany?: (parcels: unknown[]) => void;
    }) => {
      // eslint-disable-next-line react-hooks/immutability -- 테스트 전용 스텁: 지도 props 캡처
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

describe("SatongMapShell 연결 대상 전환 — 소유권 판별(R2)", () => {
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

  it("① 프로젝트에서 상속된 선택 → 드롭다운을 '새 프로젝트로 등록'으로 바꾸면 비워지고 고지된다(원 버그리포트 재현)", () => {
    render(<SatongMapShell locale="ko" />);

    // 사전조건: 연결 프로젝트 필지가 선택 목록에 하이드레이션돼 있어야 한다(소유권=proj-leak).
    expect(screen.getByText("청진동 1")).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    // ★LOW 보정: 폴백 하이드레이션은 sessionStorage를 쓰지 않아 이 시점엔 아직 비어 있다.
    //   실사용에서는 다른 커밋 경로(addParcels 등)로 이미 존재했을 세션 미러를 재현해, 아래
    //   "제거됐다" 단언이 공허한 통과가 아니라 실제 게이트가 되게 한다.
    writeSatongMapSelection([
      { id: "mirror-1", address: "서울특별시 종로구 청진동 1", source: "map" },
    ]);
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).not.toBeNull();

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // 선택 0건
    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(screen.getByText("아직 선택된 필지가 없습니다.")).toBeInTheDocument();
    // sessionStorage 미러 제거(실제 게이트)
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    // 지도 staged 폴리곤 청소 신호 증가(WP-M2 대칭)
    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
    // 무음 금지 — 고지 문구
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

  it("비울 확정 선택도 staged도 없으면 무음 유지 — 불필요한 고지 남발 방지", () => {
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

  it("R1b: 확정 선택 0건이어도 clearSignal은 증가한다 — 지도 staged 폴리곤 정리는 소유권과 무관하게 무조건 실행", () => {
    // 확정 목록(selectedParcels)은 0건이지만, 사용자가 지도에서 필지를 찍어 SatongMultiMap
    // 내부 staged(녹색, 아직 [완료] 안 누름)에 쌓아둔 뒤 드롭다운을 바꾸는 순서를 재현한다.
    // staged 배열 자체는 스텁에서 만들 수 없지만, "확정목록이 없다"는 이유로 지도 청소 신호가
    // 스킵되지 않고 항상 오른다는 계약은 selectedParcels=0인 채로도 clearSignal이 증가한다는
    // 사실로 고정할 수 있다(고지만 조건부, 지도 청소는 무조건 — 게이팅 대상이 다르다).
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
    expect(
      screen.queryByText("연결 대상을 바꿔 선택 필지를 비웠습니다."),
    ).not.toBeInTheDocument();
  });

  it("② HIGH(R2): 사용자가 지도로 직접 담은 선택은 드롭다운 전환에도 보존된다(리뷰어 프로브 재현)", () => {
    // 상도동 프로젝트에 연결된 상태 — 최초 하이드레이션이 대표필지 1건을 시드하며 이때
    // 소유권(selectionOwnerProjectIdRef)이 "proj-sangdo"로 잡힌다(SatongMapShell.smoke.test.tsx
    // 의 가드 시나리오와 동일 주소 사용 — 같은 지역이라 addParcels 가드가 발화하지 않는다).
    act(() => {
      useProjectStore.setState({
        projects: [
          {
            id: "proj-sangdo",
            name: "상도동 프로젝트",
            type: "residential",
            pnu: "",
            address: "서울특별시 동작구 상도동 123",
            area: "500㎡",
            status: "draft",
            createdAt: "2026-06-01T00:00:00.000Z",
          },
        ],
        syncing: false,
      });
      useProjectContextStore.setState({
        projectId: "proj-sangdo",
        projectName: "상도동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "서울특별시 동작구 상도동 123" }),
      });
    });

    render(<SatongMapShell locale="ko" />);
    // 상속 시드 1건(대표 필지) 확인.
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    // 사용자가 지도에서 같은 지역(상도동)의 다른 필지를 직접 추가 — 가드 미발화(지역 일치),
    // addParcels가 selectionOwnerProjectIdRef를 null(사용자 소유)로 바꾼다.
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "서울특별시 동작구 상도동 456",
          pnu: "1159010200104560000",
          lat: 37.5,
          lon: 126.94,
        },
      ]);
    });
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 2건/)).toBeInTheDocument();
    // 가드가 발화하지 않았음을 재확인(교차오염 안내 없음 — 같은 지역이라 정상 병합됐다).
    expect(
      screen.queryByText("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다."),
    ).not.toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // ★survived=true — 방금 사용자가 직접 담은 선택은 소유권이 사용자에게 있어 지워지지 않는다.
    //   (R1의 "무조건 clearParcels()"였다면 이 단언이 실패했을 시나리오.)
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 2건/)).toBeInTheDocument();
    // 확정목록을 비우지 않았으므로 "선택 필지를 비웠습니다" 고지는 없다.
    expect(
      screen.queryByText("연결 대상을 바꿔 선택 필지를 비웠습니다."),
    ).not.toBeInTheDocument();
  });
});

describe("SatongMapShell 프로젝트 A→B 전환 — clearNonce 대칭(P0-2 회귀, 종전 미검증)", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-A",
        projectName: "A 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "서울특별시 종로구 청진동 1" }),
      });
    });
  });

  afterEach(() => {
    act(() => {
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("연결 프로젝트가 A에서 B로 바뀌면 clearSignal이 증가한다(A의 staged 폴리곤이 지도에 잔존하지 않게)", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument(); // A 하이드레이션 확인

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    // 실제 전환(예: handleSelectProject가 하는 setProject)을 스토어 갱신으로 직접 재현한다.
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-B",
        projectName: "B 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "경기도 성남시 분당구 판교동 100" }),
      });
    });

    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
  });
});
