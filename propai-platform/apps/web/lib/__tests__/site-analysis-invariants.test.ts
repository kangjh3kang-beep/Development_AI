/**
 * 유령 면적 집계 자가치유 — **순수 판정 + 두 진입점 배선**.
 *
 * 배경: 필지 목록(`parcels`)이 비었는데 그 목록에서 파생된 면적 집계
 * (`landAreaSqm`/`landAreaSqmTotal`/`repLandAreaSqm`)만 살아남은 저장본이 실재했다.
 * 라이브 실측(2026-08-23) — 프로젝트 스냅샷 54건 중 2건. 그중 `1dad85f0`
 * "모산동 123-1 외 6필지" 는 대표필지(3,836㎡)의 **43배**인 164,823㎡ 를 유령으로 들고 있었고,
 * 그 값이 "단일 필지입니다" 문구와 **같은 화면에** 떠 사용자 신고로 이어졌다.
 *
 * ★근본(쓰기/지우기 비대칭)은 `satong-map-selection` 에서 따로 고쳤다. 이 스위트는
 *   **두 번째 방어선**을 잠근다 — 이미 저장된 오염본이 다시 흘러들어도 화면에 닿지 않게.
 *
 * ★진입점이 **둘**이라 배선 테스트도 둘이다(하나만 잠그면 나머지로 그대로 관통한다):
 *     ① `useProjectContextStore.updateSiteAnalysis` (store 액션)
 *     ② `projectSync.applyRemoteSnapshot`          (setState 직접 — 액션을 **우회**)
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  hasPhantomAreaAggregates,
  healPhantomAreaAggregates,
} from "@/lib/site-analysis-invariants";
import { applyRemoteSnapshot } from "@/lib/projectSync";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: { ...actual.apiClient, request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending) },
  };
});

/**
 * 라이브 오염본 **두 형상** — 목록 0건인데 집계 생존.
 * ★둘을 다 두는 이유: 실측한 두 행이 `zoneMixed` 에서 **갈린다**(1dad85f0=false · 49b59c62=true).
 *   false 픽스처 하나만 쓰면 `zoneMixed: false` 되돌림을 지워도 결과가 같아 **변이가 생존한다**
 *   (실제로 초판에서 생존했다 — 픽스처가 두 모집단을 가르지 못하면 잠금이 아니다).
 */
const PHANTOM = {
  address: "충청북도 제천시 모산동 123-1",
  pnu: "4315011400101230001",
  zoneCode: "자연녹지지역",
  parcels: [],
  parcelCount: 0,
  landAreaSqm: 164823,
  landAreaSqmTotal: 164823,
  repLandAreaSqm: 3836,
  zoneMixed: false,
} as unknown as SiteAnalysisData;

/** 라이브 오염본 `49b59c62` "산 1-1 외 1필지" — 이쪽은 `zoneMixed` 가 **true** 로 굳어 있었다. */
const PHANTOM_MIXED = {
  address: "경상북도 포항시 남구 장기면 산 1-1",
  parcels: [],
  parcelCount: 0,
  landAreaSqm: 147074,
  landAreaSqmTotal: 147074,
  repLandAreaSqm: 147074,
  zoneMixed: true,
} as unknown as SiteAnalysisData;

describe("유령 면적 집계 — 순수 판정", () => {
  it("목록 0건인데 집계가 살아 있으면 유령으로 판정하고 걷어낸다", () => {
    expect(hasPhantomAreaAggregates(PHANTOM)).toBe(true);
    const healed = healPhantomAreaAggregates(PHANTOM)!;
    expect(healed.landAreaSqm).toBeNull();
    expect(healed.landAreaSqmTotal).toBeNull();
    expect(healed.repLandAreaSqm).toBeNull();
    expect(healed.zoneMixed).toBe(false);
    // 정체성은 남긴다 — 지우는 것은 '목록에서 파생된 값'뿐이다.
    expect(healed.address).toBe("충청북도 제천시 모산동 123-1");
    expect(healed.pnu).toBe("4315011400101230001");
  });

  it("★`zoneMixed` 도 되돌린다 — 목록이 없으면 '용도지역이 섞였다'는 말은 성립할 수 없다", () => {
    // ★이 케이스가 없으면 `zoneMixed: false` 되돌림 삭제 변이가 생존한다(픽스처가 갈라야 죽는다).
    expect(PHANTOM_MIXED.zoneMixed).toBe(true); // 전제 확인 — 갈림이 실재하는지 먼저 본다
    const healed = healPhantomAreaAggregates(PHANTOM_MIXED)!;
    expect(healed.zoneMixed).toBe(false);
    expect(healed.landAreaSqmTotal).toBeNull();
  });

  it("★위양성 방지 — 정상 단일필지는 건드리지 않는다(landAreaSqm 만 쓰는 모집단)", () => {
    // 단일필지 분석은 Total/rep 을 쓰지 않는다 → 함의가 깨지지 않았다.
    const single = { address: "서울 종로구 청진동 1", parcels: [], landAreaSqm: 3836 } as unknown as SiteAnalysisData;
    expect(hasPhantomAreaAggregates(single)).toBe(false);
    expect(healPhantomAreaAggregates(single)).toBe(single); // ★같은 참조(리렌더 연쇄 방지)
  });

  it("★위양성 방지 — 정상 다필지(목록 있음)는 건드리지 않는다", () => {
    const multi = {
      parcels: [{ address: "a", areaSqm: 1 }, { address: "b", areaSqm: 2 }],
      parcelCount: 2,
      landAreaSqmTotal: 3,
      repLandAreaSqm: 1,
    } as unknown as SiteAnalysisData;
    expect(hasPhantomAreaAggregates(multi)).toBe(false);
    expect(healPhantomAreaAggregates(multi)).toBe(multi);
  });

  it("이미 치유된 형상(집계 null)은 재차 손대지 않는다 — 멱등", () => {
    const cleared = { parcels: [], parcelCount: 0, landAreaSqm: null, landAreaSqmTotal: null, repLandAreaSqm: null } as unknown as SiteAnalysisData;
    expect(hasPhantomAreaAggregates(cleared)).toBe(false);
    expect(healPhantomAreaAggregates(cleared)).toBe(cleared);
  });

  it("null/undefined 안전", () => {
    expect(hasPhantomAreaAggregates(null)).toBe(false);
    expect(healPhantomAreaAggregates(null)).toBeNull();
    expect(healPhantomAreaAggregates(undefined)).toBeUndefined();
  });
});

describe("★배선 — 진입점 두 곳 모두에서 치유된다", () => {
  beforeEach(() => {
    useProjectContextStore.setState({
      projectId: null,
      siteAnalysis: null,
      decisionBrief: null,
    } as never);
  });

  it("① store 액션(updateSiteAnalysis)으로 오염본이 들어와도 집계가 남지 않는다", () => {
    useProjectContextStore.getState().updateSiteAnalysis(PHANTOM, { source: "auto" });

    const sa = useProjectContextStore.getState().siteAnalysis as SiteAnalysisData & {
      landAreaSqmTotal?: number | null;
      repLandAreaSqm?: number | null;
    };
    // 공허 진리 가드 — 실제로 뭔가 쓰였는지 먼저 본다.
    expect(sa).not.toBeNull();
    expect(sa.address).toBe("충청북도 제천시 모산동 123-1");
    expect(sa.landAreaSqm ?? null).toBeNull();
    expect(sa.landAreaSqmTotal ?? null).toBeNull();
    expect(sa.repLandAreaSqm ?? null).toBeNull();
  });

  it("② 스냅샷 하이드레이션(applyRemoteSnapshot)으로 들어와도 집계가 남지 않는다 — 액션 우회 경로", () => {
    const projectId = "1dad85f0-7f4e-407b-9a33-a393b6c41a4d";
    useProjectContextStore.setState({ projectId, siteAnalysis: null } as never);

    applyRemoteSnapshot(projectId, {
      siteAnalysis: PHANTOM,
      updatedAt: { siteAnalysis: Date.now() + 60_000 },
    } as unknown as Record<string, unknown>);

    const sa = useProjectContextStore.getState().siteAnalysis as
      | (SiteAnalysisData & { landAreaSqmTotal?: number | null; repLandAreaSqm?: number | null })
      | null;
    // ★공허 진리 가드 — 하이드레이션이 실제로 적용됐는지 먼저 확인한다.
    //   (적용 자체가 안 되면 "집계 없음"은 공허하게 참이 된다.)
    expect(sa).not.toBeNull();
    expect(sa!.address).toBe("충청북도 제천시 모산동 123-1");
    expect(sa!.landAreaSqm ?? null).toBeNull();
    expect(sa!.landAreaSqmTotal ?? null).toBeNull();
    expect(sa!.repLandAreaSqm ?? null).toBeNull();
  });
});
