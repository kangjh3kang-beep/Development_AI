/**
 * ★R1 후속(레인G R2 항목1·MEDIUM 필수) — 전월세 모드 지원유형 필터 회귀.
 *
 * 배경: 백엔드 `_RENT_TYPES`는 4종(apt/villa/house/officetel)뿐인데, SatongMapShell의
 * marketLayer.types가 kind로 필터링되지 않아 기본값(kind-trade + type-apt/land/commercial)
 * 상태에서 "전월세"를 누르는 즉시 `land_rent`·`commercial_rent`(백엔드 미존재 카테고리)를
 * 요청 → SatongMultiMap 범례에 "토지 0건·상업업무용 0건"으로 표기됐다. 이는 "미수집"을
 * "거래 없음"으로 오인시키는 결함(무음/오도 클래스) — 정답 기준선은 형제
 * NearbyTransactionsMap(RENT_TYPES=MARKET_RENT_TYPES 필터)과 동일 SSOT를 shell 경로에
 * 대칭 적용하는 것.
 *
 * 이 테스트는 next/dynamic을 캡처 목업으로 대체해(★basemapSwitcher.test.tsx와 동일 기법 —
 * window.L 목업 없이 SatongMultiMap에 실제로 전달되는 props만 단언) kind 전환 시
 * marketLayer.types가 지원 4종으로만 좁혀지는지 검증한다.
 */
import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { MARKET_RENT_TYPES, MARKET_TRADE_TYPES } from "@/lib/satong-map-layers";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

const capturedMapProps: Record<string, unknown>[] = [];
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub" />;
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
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending),
      putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
  });
}

describe("SatongMapShell 실거래 레이어 — 전월세 지원유형 필터(R1 후속)", () => {
  beforeEach(() => {
    capturedMapProps.length = 0;
    window.sessionStorage.clear();
    resetStores();
  });
  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("기본값(매매)에서는 토지·상업업무용이 types에 포함된다(개발 실무 기본값)", () => {
    render(<SatongMapShell locale="ko" />);
    const last = capturedMapProps.at(-1) as { marketLayer?: { kind?: string; types?: string[] } };
    expect(last.marketLayer?.kind).toBe("trade");
    expect(last.marketLayer?.types).toEqual(expect.arrayContaining(["land", "commercial"]));
  });

  it("★핵심 회귀: '전월세' 클릭 시 types가 지원 4종으로만 좁혀지고 land/commercial이 사라진다", () => {
    render(<SatongMapShell locale="ko" />);

    // 실거래·시세 레이어 패널을 연다.
    fireEvent.click(screen.getByRole("button", { name: "실거래·시세" }));
    // 매매/전월세 배타 컨트롤 — 전월세로 전환.
    fireEvent.click(screen.getByRole("button", { name: "전월세" }));

    const last = capturedMapProps.at(-1) as { marketLayer?: { kind?: string; types?: string[] } };
    expect(last.marketLayer?.kind).toBe("rent");
    const supportedKeys = MARKET_RENT_TYPES.map((t) => t.key);
    const unsupportedKeys = MARKET_TRADE_TYPES.map((t) => t.key).filter((k) => !supportedKeys.includes(k));
    for (const key of last.marketLayer?.types ?? []) {
      expect(supportedKeys).toContain(key);
    }
    for (const key of unsupportedKeys) {
      expect(last.marketLayer?.types ?? []).not.toContain(key);
    }
    // ★백엔드 미존재 카테고리(land_rent/commercial_rent)를 조회하지 않는다는 확증.
    expect(last.marketLayer?.types ?? []).not.toContain("land");
    expect(last.marketLayer?.types ?? []).not.toContain("commercial");
  });

  it("전월세 모드에서 '토지' 유형 토글 버튼이 비활성화된다(눌러도 무의미한 오도 UX 차단)", () => {
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByRole("button", { name: "실거래·시세" }));
    fireEvent.click(screen.getByRole("button", { name: "전월세" }));

    const landButton = screen.getByRole("button", { name: "토지" });
    expect(landButton).toBeDisabled();
  });
});
