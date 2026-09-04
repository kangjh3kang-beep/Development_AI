/**
 * ★경계 일괄 조회의 **날조 경계** 락.
 *
 * 라이브 실측(2026-08-20, api.4t8t.net):
 *  · `{"pnu":"경기도 오산시 내삼미동"}`(가짜 PNU) → 서버가 echo, `area_sqm:0 · zone_type:null ·
 *    age_status:"lookup_failed"` → **보강 전체가 조용히 죽는다**
 *  · `{"address":"경기도 오산시 내삼미동"}`(동 단위, PNU 없음) → **임의의 한 필지(114-1)로 수렴**
 *    → 같은 동 77필지가 전부 그 한 필지로 보강되는 조용한 오답
 *
 * 그래서 "요청 본문에 무엇이 실리는가" 를 잠근다 — 라벨만 보면 이 결함은 보이지 않는다.
 */
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";

const boundaryBodies: Array<{ parcels?: Array<{ pnu?: string | null; address?: string }> }> = [];

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending),
      post: vi.fn((path: string, opts?: { body?: unknown }) => {
        if (path !== "/zoning/parcel-boundaries") return pending();
        boundaryBodies.push(opts?.body as { parcels?: Array<{ pnu?: string | null; address?: string }> });
        return pending();
      }),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const DONG = "경기도 오산시 내삼미동";
const REAL_PNU = "4137011000104670001";

describe("SatongMultiMap 경계 요청 — 필지를 특정할 수 있는 것만 보낸다", () => {
  beforeEach(() => {
    boundaryBodies.length = 0;
  });

  it("★세 모집단 중 (A)(B)만 실리고 (C)는 실리지 않는다", () => {
    render(
      <SatongMultiMap
        selectedParcels={[
          { id: "a", pnu: REAL_PNU, address: DONG, source: "map" },             // (A) 진짜 PNU
          { id: "b", pnu: null, address: `${DONG} 114-1`, source: "excel" },    // (B) 주소에 지번
          { id: "c", pnu: null, address: DONG, source: "excel" },               // (C) 앵커 없음
          { id: "d", pnu: DONG, address: DONG, source: "excel" },               // (C') 가짜 PNU
        ]}
      />,
    );

    // 공허 진리 가드: 요청이 실제로 나갔다(0건이면 아래 not.toContain 이 공허한 참이 된다).
    expect(boundaryBodies).toHaveLength(1);
    const sent = boundaryBodies[0].parcels ?? [];
    expect(sent).toHaveLength(2);
    expect(sent).toContainEqual({ pnu: REAL_PNU, address: DONG });
    expect(sent).toContainEqual({ pnu: null, address: `${DONG} 114-1` });
    // ★가짜 PNU 는 절대 나가지 않는다(나가면 서버가 echo 하고 보강이 죽는다).
    expect(sent.map((p) => p.pnu)).not.toContain(DONG);
    // ★지번 없는 주소만 가진 필지는 아예 요청하지 않는다(임의 필지 수렴 금지).
    expect(sent.filter((p) => !p.pnu && p.address === DONG)).toHaveLength(0);
  });

  it("★특정 가능한 필지가 하나도 없으면 요청 자체가 나가지 않는다", () => {
    render(
      <SatongMultiMap
        selectedParcels={[
          { id: "c", pnu: null, address: DONG, source: "excel" },
          { id: "d", pnu: DONG, address: DONG, source: "excel" },
        ]}
      />,
    );
    expect(boundaryBodies).toHaveLength(0);
  });
});
