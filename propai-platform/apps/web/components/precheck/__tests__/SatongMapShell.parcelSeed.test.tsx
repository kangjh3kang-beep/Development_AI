/**
 * SatongMapShell 초기 하이드레이션(T1) — 미연결 신규 진입 잔존 차단 + 계약 보존.
 *
 * 증상 A: 프로젝트를 연결하지 않고 검색도 안 한 '신규 진입'인데, 이전 세션의 선택 필지가
 *   선택 목록에 되살아났다. 근본원인 = 초기 하이드레이션이 sessionStorage(탭 수명)·persist
 *   store(localStorage, 브라우저 수명)에서 선택을 무조건 복원했기 때문.
 *
 * 이 스위트는 수정 후 세 가지 계약을 고정한다:
 *   ① 미연결 신규 진입(하드 리로드/새 탭 잔존) → 빈 목록으로 시작.
 *   ② 프로젝트 연결 → 스냅샷(스토어 필지) 하이드레이션 유지(PR#221 계약 불변).
 *   ③ 같은 SPA 세션 내 라우트 이동 후 복귀 → 선택 유지(작업 연속성).
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  writeSatongMapSelection,
  SATONG_MAP_SELECTION_KEY,
} from "@/components/precheck/satong-map-selection";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

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
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
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

const STALE_ADDRESS = "경기도 용인시 수지구 신봉동 56-16";

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null,
      projectName: "",
      projectStatus: "",
      siteAnalysis: null,
    });
  });
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

describe("SatongMapShell 초기 하이드레이션(T1)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("① 미연결 신규 진입 — 이전 세션(다른 SPA 토큰) 잔존은 복원하지 않고 빈 목록으로 시작", () => {
    // 하드 리로드/새 탭 잔존을 재현: sessionStorage에 '다른 세션 토큰'으로 저장된 선택.
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({
        savedAt: new Date().toISOString(),
        spaSession: "이전-세션-토큰",
        parcels: [{ id: "P-stale", address: STALE_ADDRESS, source: "map" }],
      }),
    );

    render(<SatongMapShell locale="ko" />);

    // 잔존 필지는 목록에 없어야 하고, 빈 상태 안내가 보여야 한다.
    expect(screen.queryByText(STALE_ADDRESS)).not.toBeInTheDocument();
    expect(screen.getByText("아직 선택된 필지가 없습니다.")).toBeInTheDocument();
    // 헤더 카운트도 0건.
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    // 잔존 캐시는 정리돼 다른 소비처도 읽지 않는다.
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
  });

  it("② 프로젝트 연결 — 스토어 스냅샷 필지로 하이드레이션 유지(PR#221 계약)", () => {
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-x",
        projectName: "연결 프로젝트",
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

    render(<SatongMapShell locale="ko" />);

    // U4 카드 압축: 목록엔 짧은 지번, 전체 주소는 카드 title 속성에 보존.
    expect(screen.getByText("청진동 1")).toBeInTheDocument();
    expect(screen.getByTitle(/서울특별시 종로구 청진동 1/)).toBeInTheDocument();
  });

  it("③ 같은 SPA 세션 내 복귀 — 미연결이라도 이번 세션 선택은 유지", () => {
    // 이번 세션에서 write(현재 SPA 토큰 스탬프) → sameSpaSession=true 로 복원돼야 한다.
    writeSatongMapSelection([
      { id: "P-live", address: "경기도 성남시 분당구 판교동 100", source: "map" },
    ]);

    render(<SatongMapShell locale="ko" />);

    expect(screen.getByText("판교동 100")).toBeInTheDocument();
    expect(screen.getByTitle(/경기도 성남시 분당구 판교동 100/)).toBeInTheDocument();
  });
});
