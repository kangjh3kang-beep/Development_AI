/**
 * ★★CRITICAL 회귀 잠금 — "가짜 PNU 를 정화했더니 **77필지가 1필지로 지워진다**".
 *
 * 신고 프로젝트는 77필지의 **주소가 전부 같다**(`경기도 오산시 내삼미동`). 종전엔 PNU 칸에
 * 들어앉은 서로 다른 **가짜값**이 우연히 `parcelKey` 의 유일성을 제공하고 있었다. 그 가짜를
 * `null` 로 정화하는 순간 `new Map(prev.map(p => [parcelKey(p), p]))` 가 전부를 한 키로 접고,
 * `syncParcelsToStores` 가 그 1건을 **영속**한다 — 지도에서 필지 하나를 클릭하는 것만으로
 * 사용자의 76필지가 조용히 사라진다.
 *
 * ★픽스처는 두 모집단을 가른다:
 *   (A) 주소 동일 · PNU 없음 **2건**  → **2건으로 남아야** 한다(같은 주소라도 다른 필지다)
 *   (B) 주소 동일 · 같은 필지 재삽입   → 1건으로 접혀야 한다(기존 중복제거 계약 무회귀)
 * 두 모집단이 **다른 결과**를 내지 않으면 배선을 끊어도 통과한다.
 */
import { render, screen } from "@testing-library/react";
import { act, useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  readSatongMapSelection,
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "@/components/precheck/satong-map-selection";
import { useProjectContextStore } from "@/store/useProjectContextStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

/** 지도 스텁 — `onPickMany`(사용자의 지도 클릭 확정)를 테스트가 직접 발화할 수 있게 잡아 둔다. */
const mapHandlers: { pickMany?: (parcels: Array<Record<string, unknown>>) => void } = {};

vi.mock("next/dynamic", () => ({
  default: () => {
    // 렌더 중 외부 변수 쓰기는 린트가 막는다(react-compiler) — 기존 선례
    // (SatongMapShell.parcelLayout.test)처럼 effect 에서 잡는다.
    const DynamicStub = (props: { onPickMany?: (p: Array<Record<string, unknown>>) => void }) => {
      useEffect(() => {
        mapHandlers.pickMany = props.onPickMany;
      });
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
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const DONG = "경기도 오산시 내삼미동";

/** 스토어에서 복원된 모습 그대로 — 주소 동일 · PNU 없음 · id 는 필지별 유일. */
function restoredParcels(n: number): SatongSelectionParcel[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `store-${i}-${DONG}`,
    address: DONG,
    pnu: null,
    areaSqm: 100 + i,
    source: "map" as const,
  }));
}

function persistedCount(): number {
  return readSatongMapSelection()?.parcels.length ?? 0;
}

describe("★CRITICAL: 같은 동 필지가 지도 클릭 한 번에 지워지지 않는다", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    mapHandlers.pickMany = undefined;
    act(() => {
      useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
    });
  });

  it("(A) 주소 동일·PNU 없음 77건 + 지도 클릭 1건 → **78건이 남는다**(1건으로 접히지 않는다)", () => {
    writeSatongMapSelection(restoredParcels(77), null);
    render(<SatongMapShell locale="ko" />);

    // 공허 진리 가드: 복원이 실제로 77건을 올렸다(0/1이면 아래 단언이 무의미해진다).
    expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(77);
    expect(mapHandlers.pickMany).toBeTypeOf("function");

    act(() => {
      mapHandlers.pickMany!([
        { pnu: "4137011000104670001", address: `${DONG} 467-1`, area_sqm: 53, found: true },
      ]);
    });

    expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(78);
    // ★영속까지 확인한다 — 화면만 맞고 세션에 1건이 저장되면 재진입에서 사라진다.
    expect(persistedCount()).toBe(78);
  });

  it("(B) 같은 필지 재삽입은 여전히 1건으로 접힌다(중복제거 계약 무회귀)", () => {
    writeSatongMapSelection([], null);
    render(<SatongMapShell locale="ko" />);
    expect(mapHandlers.pickMany).toBeTypeOf("function");

    const pick = { pnu: null, address: DONG, area_sqm: 100, found: true };
    act(() => { mapHandlers.pickMany!([pick]); });
    act(() => { mapHandlers.pickMany!([pick]); });

    expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(1);
    expect(persistedCount()).toBe(1);
  });

  it("★(A)와 (B)는 **다른 결과**여야 한다 — 같으면 키를 어떻게 바꿔도 통과한다", () => {
    writeSatongMapSelection(restoredParcels(2), null);
    const { unmount } = render(<SatongMapShell locale="ko" />);
    act(() => { mapHandlers.pickMany!([{ pnu: null, address: DONG, area_sqm: 1, found: true }]); });
    const differentParcels = persistedCount(); // (A) 서로 다른 필지 2 + 신규 1
    unmount();

    window.sessionStorage.clear();
    writeSatongMapSelection([], null);
    render(<SatongMapShell locale="ko" />);
    const same = { pnu: null, address: DONG, area_sqm: 1, found: true };
    act(() => { mapHandlers.pickMany!([same]); });
    act(() => { mapHandlers.pickMany!([same]); });
    const sameParcel = persistedCount(); // (B) 같은 필지 2회

    expect(differentParcels).toBe(3);
    expect(sameParcel).toBe(1);
    expect(differentParcels).not.toBe(sameParcel);
  });
});
