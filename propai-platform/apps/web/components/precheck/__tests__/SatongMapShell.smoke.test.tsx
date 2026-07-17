/**
 * SatongMapShell 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 내부 지도(SatongMultiMap)는 next/dynamic 로드라 스텁으로 대체하고,
 * 마운트 시 프로젝트 동기화(syncFromBackend → /projects)는 pending으로 고정한다.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
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
// ★F6: 스텁이 받은 props(특히 onPickMany)를 캡처해두면, 지도에서 필지를 고른 것처럼
//   테스트에서 직접 호출할 수 있다(가드 발화 통합테스트용). vi.mock은 파일 상단으로 호이스트
//   되므로 캡처 변수는 vi.hoisted로 선언한다(ParcelMapWrapper.test.tsx와 동일 패턴).
const { capturedMapPropsRef } = vi.hoisted(() => ({
  capturedMapPropsRef: { current: null as null | { onPickMany?: (parcels: unknown[]) => void } },
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: { onPickMany?: (parcels: unknown[]) => void }) => {
      // eslint-disable-next-line react-hooks/immutability -- 테스트 전용 스텁: 지도 props(onPickMany)를 캡처해 가드 통합테스트에서 직접 호출하기 위한 의도적 렌더 부작용
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

describe("SatongMapShell 스모크", () => {
  it("크래시 없이 마운트되고 헤더·필지 입력 패널·지도 스텁이 보인다", () => {
    render(<SatongMapShell locale="ko" />);

    expect(
      screen.getByRole("heading", { name: /지도 위에서 입력부터 산출물 생성까지/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "통합 필지 입력" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("dynamic-map-stub")).toBeInTheDocument();
  });
});

// ── F6: 교차오염 가드 발화 시 선택 유지 통합테스트 ──
//   기존 프로젝트(상도동)에 연결된 상태에서 지역이 다른 필지(용인 고기동)를 지도에서 고르면
//   addParcels 가드가 detachProjectCarryingSelection으로 프로젝트를 해제하는데, 이 해제가
//   PR#221 전환 이펙트에 '프로젝트 전환'으로 오인돼 방금 고른 선택을 지워버리면 안 된다(F1 회귀).
function makeGuardTestProject(partial: Partial<Project>): Project {
  return {
    id: "proj-sangdo",
    name: "상도동 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 동작구 상도동 123",
    area: "500㎡",
    status: "draft",
    createdAt: "2026-06-01T00:00:00.000Z",
    ...partial,
  };
}

function makeGuardTestSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

describe("SatongMapShell 연결 프로젝트 가드", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    act(() => {
      useProjectStore.setState({ projects: [makeGuardTestProject({})], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-sangdo",
        projectName: "상도동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeGuardTestSite({ address: "서울특별시 동작구 상도동 123" }),
      });
    });
  });

  afterEach(() => {
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

  it("가드가 프로젝트를 해제해도 방금 고른 지역불일치 필지 선택은 유지된다", () => {
    render(<SatongMapShell locale="ko" />);

    // 지도에서 상도동 프로젝트와 지역이 다른 용인 고기동 필지를 고른 상황을 재현.
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 용인시 수지구 고기동 689",
          pnu: "4146025629108900000",
          lat: 37.32,
          lon: 127.11,
        },
      ]);
    });

    // 선택 필지 카드에 방금 고른 주소가 남아있어야 한다(F1 회귀 없음 — 전환 이펙트가 와이프 안 함).
    // U4 카드 압축: 목록엔 짧은 지번, 전체 주소는 카드 title 속성에 보존.
    expect(screen.getByText("고기동 689")).toBeInTheDocument();
    expect(screen.getByTitle(/경기도 용인시 수지구 고기동 689/)).toBeInTheDocument();
    // 가드가 발화해 '새 프로젝트로 등록' 모드로 전환했다는 안내도 함께 보여야 한다.
    expect(
      screen.getByText("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다."),
    ).toBeInTheDocument();
  });
});
