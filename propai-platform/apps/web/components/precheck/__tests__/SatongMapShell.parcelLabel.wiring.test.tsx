/**
 * ★배선 락 — "라벨 헬퍼가 있다" 가 아니라 **그 화면이 실제로 그걸 쓰는가**를 렌더로 본다.
 *
 * 이 결함(`오산시 내삼미동` 77행)은 다섯 번 고쳐졌고 다섯 번 다 안 나았다. 매번
 * "표시 헬퍼는 고쳤는데 **이 화면은 그 헬퍼를 안 쓴다**" 였다(`#673` 의 형제 스윕이
 * 이 화면을 목록에서 빠뜨렸다). 순수함수 테스트로는 절대 안 잡히는 층이라 셸을 직접 태운다.
 *
 * 세 모집단을 한 목록에 넣고 **서로 다른 3개 라벨** + **미해석 1건 고지**를 못박는다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "@/components/precheck/satong-map-selection";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// next/dynamic(SatongMultiMap)은 jsdom에서 Leaflet 실로드가 불가 — 스텁으로 대체.
//   ★스텁은 **지도만** 대체한다. 검사 대상(선택 필지 목록)은 셸이 직접 렌더하므로
//   이 스텁이 검증 대상 층을 우회하지 않는다(CLAUDE.md 검증 규율 §3).
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

// 네트워크 차단(SatongMapShell.parcelSeed 선례) — 경계·POI 등 모든 조회는 영구 pending.
/** `/zoning/parcel-at-point` 로 나간 좌표들 — 좌표 앵커 치유가 **실제로 요청했는지** 본다. */
const pointCalls: Array<{ lat?: number; lon?: number }> = [];

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending),
      post: vi.fn((path: string, opts?: { body?: { lat?: number; lon?: number } }) => {
        if (path !== "/zoning/parcel-at-point") return pending();
        pointCalls.push(opts?.body ?? {});
        return Promise.resolve({
          found: true,
          pnu: "4137011000101140001",
          address: "경기도 오산시 내삼미동 114-1",
        });
      }),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const DONG = "경기도 오산시 내삼미동";

/** (A) 진짜 PNU / (B) 주소에 지번 / (C) 앵커 없음 — 세 모집단. */
const parcels: SatongSelectionParcel[] = [
  { id: "4137011000104670001", pnu: "4137011000104670001", address: DONG, source: "excel" },
  { id: "b", pnu: null, address: `${DONG} 114-1`, source: "excel" },
  { id: "c", pnu: null, address: DONG, source: "excel" },
];

describe("SatongMapShell 선택 필지 목록 — 라벨 배선", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    writeSatongMapSelection(parcels, null);
  });

  it("★같은 동이라도 세 모집단이 **서로 다른 라벨**로 보이고, 미해석은 그 사실을 말한다", () => {
    render(<SatongMapShell locale="ko" />);

    const labels = screen.getAllByTestId("parcel-jibun-text");
    // 공허 진리 가드: 검사 대상이 실제로 DOM 에 있다(0건이면 '위반 0'이 공허한 참이 된다).
    expect(labels).toHaveLength(3);

    const texts = labels.map((el) => el.textContent);
    expect(texts).toContain("내삼미동 467-1"); // (A) PNU 에서 파생
    expect(texts).toContain("내삼미동 114-1"); // (B) 주소에 이미 있음
    expect(texts).toContain("오산시 내삼미동"); // (C) 지번을 지어내지 않았다
    expect(new Set(texts).size).toBe(3);

    // (C) 한 건만 정직 고지 — (A)(B)에까지 붙으면 위양성(정상 데이터를 의심하게 만든다).
    expect(screen.getAllByTestId("parcel-jibun-unresolved")).toHaveLength(1);
  });
});

/**
 * ★좌표 앵커 자가치유의 **배선** 락(순수 모듈 테스트로는 안 잡히는 층).
 *
 * `lib/parcel-jibun-heal` 이 옳아도 셸이 그걸 부르지 않으면 화면은 그대로다 —
 * 이 결함이 다섯 번 살아남은 방식이 정확히 그것이다.
 */
describe("SatongMapShell 좌표 앵커 지번 자가치유 — 배선", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    pointCalls.length = 0;
  });

  it("★PNU 없고 **좌표만** 있는 필지는 parcel-at-point 로 해석돼 지번이 화면에 나온다", async () => {
    writeSatongMapSelection(
      [{ id: "c", pnu: null, address: DONG, lat: 37.1789, lon: 127.0611, source: "excel" }],
      null,
    );
    render(<SatongMapShell locale="ko" />);

    // 치유 전: 지번이 없어 미해석으로 고지된다(공허 진리 가드 — 출발 상태를 확인).
    expect(screen.getByTestId("parcel-jibun-unresolved")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("내삼미동 114-1"),
    );
    expect(pointCalls).toEqual([{ lat: 37.1789, lon: 127.0611 }]);
    expect(screen.queryByTestId("parcel-jibun-unresolved")).toBeNull();
  });

  it("★앵커가 **동 단위 주소뿐**이면 요청 자체가 나가지 않는다(임의 필지 수렴 금지)", async () => {
    writeSatongMapSelection([{ id: "c", pnu: null, address: DONG, source: "excel" }], null);
    render(<SatongMapShell locale="ko" />);

    // 대조군: 위 테스트가 같은 셸에서 요청을 실제로 만든다 — "0건" 이 배선 부재가 아님을 보증.
    await waitFor(() => expect(screen.getByTestId("parcel-jibun-unresolved")).toBeInTheDocument());
    expect(pointCalls).toEqual([]);
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 내삼미동");
  });
});
