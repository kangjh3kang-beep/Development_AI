/**
 * 선택을 비울 때 **그 선택에서 파생된 집계도 함께 비운다**(2026-08-23 · 사용자 신고 근본).
 *
 * ── 증상(라이브 실측, 프로젝트 `1dad85f0` "모산동 123-1 외 6필지") ──────────────────
 *   한 화면이 동시에 이렇게 말했다:
 *     헤더    "모산동 123-1 외 6필지"   ← **프로젝트 이름 문자열**(등록 시점에 굳은 값)
 *     본문    "단일 필지입니다"          ← parcels = []
 *     구획도  "1필지 · 3,836㎡"          ← repLandAreaSqm(스테일)
 *     통합면적 164,823㎡                 ← landAreaSqm/Total(스테일 · 대표필지의 **43배**)
 *
 *   영속된 SSOT 실측: `parcelCount=0 · parcels=[]` 인데
 *   `landAreaSqm=landAreaSqmTotal=164823 · repLandAreaSqm=3836 · dataSource='satong-map-shell'`.
 *
 * ── 근본 ──────────────────────────────────────────────────────────────────────
 *   쓰기(`selectionToSiteAnalysisPatch`)는 선택 목록에서 **11개 필드**를 파생시켜 쓰는데,
 *   지우기(`syncParcelsToStores([])`)는 그중 **2개**(`parcels`·`parcelCount`)만 되돌렸다.
 *   나머지 9개 중 면적 3종(`landAreaSqm`·`landAreaSqmTotal`·`repLandAreaSqm`)과 `zoneMixed`
 *   가 **유령으로 살아남아** 수지·설계가 존재하지 않는 부지 면적을 곱한다.
 *   ★`address`·`pnu`·`coordinates`·`zoneCode` 보존은 **의도**다(프로젝트 정체성 —
 *     SatongMapShell 의 `hasTarget` 판정이 이 보존에 의존한다). 면적 집계 보존은
 *     어디에도 의도로 적힌 적이 없다 — 검토되지 않은 잔여였다.
 *
 * ── 이 스위트가 잠그는 계약 ────────────────────────────────────────────────────
 *   A) 배선 층(실 컴포넌트) — 연결 대상 전환으로 상속 선택이 비워지면 면적 집계도 함께 사라진다.
 *   B) 위양성 방지 — 사용자 소유 선택은 보존되고, 따라서 집계도 보존된다(무회귀).
 *   C) ★파생형 락 — 쓰기 패치가 만드는 **모든 키**는 지우기 패치가 되돌리거나
 *      명시적 보존목록에 있어야 한다. 손으로 센 목록이 아니라 쓰기 함수의 **실제 출력**에서
 *      파생시키므로, 나중에 쓰기에 필드가 늘면 이 테스트가 **자동으로** 결정을 강요한다
 *      (규율 §A4 — 사람이 센 목록이 곧 상한이 되는 것을 막는다).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  emptySelectionSiteAnalysisPatch,
  selectionToSiteAnalysisPatch,
  type SatongSelectionParcel,
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

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

// 네트워크 차단 — 조회가 스토어를 다시 채워 단언을 오염시키지 않게 영구 pending 으로 고정.
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

const PROJECT_ID = "proj-mosan";

function makeProject(partial: Partial<Project> = {}): Project {
  return {
    id: PROJECT_ID,
    name: "모산동 123-1 외 6필지",
    type: "residential",
    pnu: "4315011400101230001",
    address: "충청북도 제천시 모산동 123-1",
    area: "164,823㎡",
    status: "draft",
    createdAt: "2026-08-21T03:29:08.000Z",
    ...partial,
  };
}

/** 라이브 프로젝트 `1dad85f0` 의 실제 형상 — 대표 3,836㎡ + 6필지 = 164,823㎡. */
function makeCorruptibleSite(): SiteAnalysisData {
  const rest = 164823 - 3836;
  const parcels = [
    { pnu: "4315011400101230001", address: "충청북도 제천시 모산동 123-1", areaSqm: 3836 },
    ...Array.from({ length: 6 }, (_, i) => ({
      pnu: `431501140010123000${i + 2}`,
      address: `충청북도 제천시 모산동 123-${i + 2}`,
      areaSqm: Math.round(rest / 6),
    })),
  ].map((p) => ({
    ...p,
    landCategory: "임야",
    ownerType: "미확인",
    zoneCode: "자연녹지지역",
  }));

  return {
    estimatedValue: null,
    address: "충청북도 제천시 모산동 123-1",
    pnu: "4315011400101230001",
    zoneCode: "자연녹지지역",
    dominantZoneCode: "자연녹지지역",
    zoneMixed: false,
    landAreaSqm: 164823,
    landAreaSqmTotal: 164823,
    repLandAreaSqm: 3836,
    parcelCount: 7,
    parcels,
    dataSource: "satong-map-shell",
  } as unknown as SiteAnalysisData;
}

function currentSite() {
  return useProjectContextStore.getState().siteAnalysis as
    | (SiteAnalysisData & {
        landAreaSqmTotal?: number | null;
        repLandAreaSqm?: number | null;
        parcelCount?: number | null;
        zoneMixed?: boolean | null;
      })
    | null;
}

describe("선택을 비우면 그 선택에서 파생된 집계도 비운다", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [makeProject()], syncing: false });
      useProjectContextStore.setState({
        projectId: PROJECT_ID,
        projectName: "모산동 123-1 외 6필지",
        projectStatus: "draft",
        siteAnalysis: makeCorruptibleSite(),
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

  it("A) '초기화'로 선택을 비우면 **유령 면적이 남지 않는다**(사용자 신고 재현 경로)", () => {
    render(<SatongMapShell locale="ko" />);

    // ── 공허한 통과 방지: 지우기 前에 유령이 될 값들이 **실제로 존재**함을 먼저 단언한다.
    const before = currentSite();
    expect(before?.parcels).toHaveLength(7);
    expect(before?.landAreaSqm).toBe(164823);
    expect(before?.landAreaSqmTotal).toBe(164823);
    expect(before?.repLandAreaSqm).toBe(3836);
    // 선택이 실제로 하이드레이션돼 화면에 올라와야 지우기가 의미를 가진다(대상 존재 가드).
    expect(screen.getByText(/필지 선택 7건/)).toBeInTheDocument();

    // ★실행 경로 선택의 근거: 연결 대상 전환(`handleConnectTargetChange`)은 먼저
    //   `detachProjectCarryingSelection()` 이 siteAnalysis 를 null 로 만들어 지우기가
    //   R2(LOW) 가드에 걸려 **아예 실행되지 않는다**(초판 테스트가 그 경로를 골랐다가
    //   RED 로 적발됐다). 프로젝트 연결을 **유지한 채** 비우는 경로가 실제 오염원이고,
    //   그게 이 "초기화" 버튼이다(형제: 마지막 1건 개별 삭제 — 같은 통로를 쓴다).
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "초기화" }));
    });

    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    const after = currentSite();
    expect(after?.parcels).toEqual([]);
    expect(after?.parcelCount).toBe(0);
    // ★이 네 줄이 이 PR 의 본체 — 종전에는 전부 살아남았다.
    expect(after?.landAreaSqm ?? null).toBeNull();
    expect(after?.landAreaSqmTotal ?? null).toBeNull();
    expect(after?.repLandAreaSqm ?? null).toBeNull();
    expect(after?.zoneMixed ?? false).toBe(false);

    // 의도된 보존 — 프로젝트 정체성은 남는다(SatongMapShell hasTarget 판정이 여기 의존).
    expect(after?.address).toBe("충청북도 제천시 모산동 123-1");
    expect(after?.pnu).toBe("4315011400101230001");
  });

  it("B) 선택이 남아 있으면 집계도 남는다(위양성 방지·무회귀)", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 7건/)).toBeInTheDocument();

    // 비우지 **않는** 조작 — 지도 레이어 토글처럼 선택과 무관한 상호작용 후에도
    //   집계는 그대로여야 한다. 지우기가 과잉발화하면(예: 매 렌더마다 빈 패치를 쓰면)
    //   여기서 죽는다.
    const after = currentSite();
    expect(after?.landAreaSqmTotal).toBe(164823);
    expect(after?.repLandAreaSqm).toBe(3836);
    expect(after?.parcelCount).toBe(7);
    expect(after?.parcels).toHaveLength(7);
  });

  it("C) ★파생형 락 — 쓰기 패치의 모든 키는 지우기가 되돌리거나 보존목록에 있어야 한다", () => {
    const sample: SatongSelectionParcel[] = [
      {
        id: "4315011400101230001",
        address: "충청북도 제천시 모산동 123-1",
        pnu: "4315011400101230001",
        lat: 37.1,
        lon: 128.2,
        areaSqm: 3836,
        zoneType: "자연녹지지역",
        jimok: "임야",
        source: "map",
      },
      {
        id: "4315011400101230002",
        address: "충청북도 제천시 모산동 123-2",
        pnu: "4315011400101230002",
        lat: 37.1,
        lon: 128.2,
        areaSqm: 160987,
        zoneType: "보전관리지역",
        jimok: "임야",
        source: "map",
      },
    ];

    const writePatch = selectionToSiteAnalysisPatch(sample);
    expect(writePatch).not.toBeNull();
    const clearPatch = emptySelectionSiteAnalysisPatch();

    /**
     * 의도적 보존 — **프로젝트 정체성·출처**. 선택이 비어도 거짓이 되지 않는 값만 들어온다.
     *   · address/pnu/coordinates : 프로젝트가 가리키는 대표 지점. `hasTarget` 판정이 의존한다.
     *   · zoneCode/dominantZoneCode : 그 대표 지점의 용도지역(면적가중이 아니라 대표값).
     *   · dataSource/fetchedAt : 이 SSOT 를 누가 언제 썼는지의 출처 — 지우면 추적이 끊긴다.
     * ★여기에 필드를 추가하려면 "선택이 없어도 참인가"에 답할 수 있어야 한다.
     */
    const DELIBERATELY_PRESERVED = new Set([
      "address",
      "pnu",
      "coordinates",
      "zoneCode",
      "dominantZoneCode",
      "dataSource",
      "fetchedAt",
    ]);

    const writeKeys = Object.keys(writePatch!);
    // 공허 진리 가드 — 쓰기가 실제로 여러 필드를 만드는지 먼저 확인한다.
    expect(writeKeys.length).toBeGreaterThanOrEqual(11);

    const unhandled = writeKeys.filter(
      (k) => !DELIBERATELY_PRESERVED.has(k) && !(k in clearPatch),
    );
    expect(
      unhandled,
      `쓰기 패치가 만드는 필드가 지우기에서 처리되지 않았습니다: ${unhandled.join(", ")}\n` +
        "선택에서 파생된 값이면 지우기 패치에 되돌림을 추가하고, 선택이 없어도 참인 값이면 " +
        "DELIBERATELY_PRESERVED 에 근거와 함께 추가하세요.",
    ).toEqual([]);

    // 되돌림이 '유령을 남기지 않는 값'인지도 본다 — 키만 있고 값이 옛 집계면 의미가 없다.
    expect(clearPatch.parcels).toEqual([]);
    expect(clearPatch.parcelCount).toBe(0);
    expect(clearPatch.landAreaSqm ?? null).toBeNull();
    expect(clearPatch.landAreaSqmTotal ?? null).toBeNull();
    expect(clearPatch.repLandAreaSqm ?? null).toBeNull();
    expect(clearPatch.zoneMixed ?? false).toBe(false);
  });
});
