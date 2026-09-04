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
import { act, useEffect } from "react";
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

// 네트워크 차단(SatongMapShell.parcelSeed 선례) — 경계·POI 등 모든 조회는 영구 pending.
/** `/zoning/parcel-at-point` 로 나간 좌표들 — 좌표 앵커 치유가 **실제로 요청했는지** 본다. */
const pointCalls: Array<{ lat?: number; lon?: number }> = [];
/** true 면 응답을 보류해 두고 테스트가 원하는 시점에 푼다(비동기 왕복 중 목록 변경 재현). */
const deferred: { hold: boolean; release: Array<() => void> } = { hold: false, release: [] };
/** 지도 스텁이 받은 `onPickMany` — 왕복 중 사용자의 필지 추가를 재현한다. */
const mapHandlers: { pickMany?: (p: Array<Record<string, unknown>>) => void } = {};

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
        // ★좌표마다 **다른 필지**를 준다. 모든 좌표에 같은 답을 주면 "다른 필지를 조회했는데
        //   같은 값이 왔다" 와 "엉뚱한 행에 썼다" 를 구분할 수 없어 검사가 무의미해진다.
        const result =
          opts?.body?.lat === 37.1789
            ? { found: true, pnu: "4137011000101140001", address: "경기도 오산시 내삼미동 114-1" }
            : { found: true, pnu: "4137011000203330000", address: "경기도 오산시 세교동 333" };
        if (!deferred.hold) return Promise.resolve(result);
        return new Promise((resolve) => deferred.release.push(() => resolve(result)));
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

    // ★라벨만 보면 **두 경로 중 하나만** 살아 있어도 초록이다(주소로도, PNU 로도 같은 지번이
    //   나온다). 그래서 둘을 따로 못박는다 — 카드 title 이 주소와 PNU 를 함께 싣는다.
    expect(
      screen.getByTitle(/경기도 오산시 내삼미동 114-1 · PNU 4137011000101140001/),
    ).toBeInTheDocument();
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

/**
 * ★비동기 왕복 **중** 선택이 바뀌면 치유가 **엉뚱한 필지에 쓰지 않는다**.
 *
 * 적대리뷰 지적: 최후 방어인 "라벨이 시드 원본과 같은가" 는 신고 프로젝트에서 **공허하다**
 * (77개 주소가 전부 같아 어느 필지와 짝지어도 통과). 즉 인덱스 정합 가드가 **유일한 잠금**인데
 * 잠겨 있지 않았다. 여기서 참조 동등성 가드(`parcel !== snapshot[index]`)를 직접 태운다.
 */
describe("SatongMapShell 좌표 치유 — 왕복 중 목록이 바뀌면 쓰지 않는다", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    pointCalls.length = 0;
    deferred.hold = false;
    deferred.release.length = 0;
    mapHandlers.pickMany = undefined;
  });

  it("★왕복 중 대상 필지가 **다른 필지로 교체**되면 그 자리에 남의 지번을 쓰지 않는다", async () => {
    deferred.hold = true;
    writeSatongMapSelection(
      [{ id: "target", pnu: null, address: DONG, lat: 37.1789, lon: 127.0611, source: "excel" }],
      null,
    );
    render(<SatongMapShell locale="ko" />);

    // 공허 진리 가드: 요청이 실제로 나갔고 아직 응답 전이다(여기서 0건이면 아래가 무의미).
    await waitFor(() => expect(pointCalls).toHaveLength(1));
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 내삼미동");

    // 왕복 중 사용자가 그 필지를 지우고 **다른 동의 필지**를 담는다 → index 0 의 주인이 바뀐다.
    // ★교체 필지도 **좌표를 가진 미해석 필지**로 둔다 — 그래야 미해석 건수가 1 로 유지돼
    //   이펙트가 재실행(=cancelled 취소 경로)되지 않는다. 취소로 막히면 이 테스트는 정작
    //   검사하려던 **인덱스 정합 가드를 태우지 못한다**(공허한 초록).
    // ★삭제와 추가를 **한 번의 act 로 묶는다**. 두 번으로 나누면 렌더가 두 번 일어나
    //   미해석 건수가 1→0→1 로 흔들려 이펙트가 재실행되고, 그 취소 경로가 먼저 막아버려
    //   정작 검사하려던 **인덱스 정합 가드를 태우지 못한다**(공허한 초록).
    act(() => {
      screen.getByLabelText("필지 제거").click();
      mapHandlers.pickMany!([
        { pnu: null, address: "경기도 오산시 세교동", area_sqm: 50, lat: 37.2, lon: 127.1, found: true },
      ]);
    });
    expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 세교동");

    // 이제 응답이 도착한다 — index 0 은 이미 남의 필지다.
    await act(async () => {
      deferred.release.forEach((fn) => fn());
      await Promise.resolve();
    });

    // ★가드가 없으면 세교동 필지가 **내삼미동 114-1** 로 덮인다(조용한 오답).
    await waitFor(() =>
      expect(screen.getByTestId("parcel-jibun-text")).toHaveTextContent("오산시 세교동"),
    );
    expect(screen.getByTestId("parcel-jibun-text")).not.toHaveTextContent("114-1");
  });
});

/**
 * ★★사용자 신고 프로젝트 **그대로** 재현 — "복구 불가" 오판을 막는 락.
 *
 * 리뷰 1차에서 "좌표 앵커가 없어 복구 불가, 화면은 '지번 미확인' 77개가 된다" 고 판정했고
 * 나도 그대로 보고했다. **사용자가 반증했다**: 스크린샷의 77행은 면적이 **전부 다르고**
 * `지목 답` · `용도지역 자연녹지지역` 을 갖고 있다.
 *
 * 백엔드 코드로 확정한 증거 사슬(2026-08-20):
 *   ① `_detect_columns` 의 역할 집합에 **용도지역이 없다** → 엑셀에서 올 수 없다.
 *   ② 응답 조립 시 `"zone_type": None` 으로 시작한다.
 *   ③ 용도지역을 채우는 **유일한** 곳은 `_enrich_fill` 이고 대상 필터가
 *      `if p.get("pnu") and …` — **PNU 없이는 실행되지 않는다.**
 *   ④ 그 PNU 는 `_pnu_from_bcode(bcode, jibun)` 로 만들어지며 **지번 숫자가 필수**다.
 *   ⑤ `get_land_characteristics(p["pnu"])` 는 **필지별** 조회다 — 면적이 전부 다른 것이 그 증거
 *      (동 대표점 폴백이면 같은 값이 반복된다. C2-2 주석이 그 증상을 적고 있다).
 *
 * → 그 프로젝트의 필지들은 **진짜 PNU 를 갖고 있다**. 주소만 동 단위일 뿐이다.
 *   즉 배포만으로 지번이 복구된다 — 사용자는 아무것도 다시 하지 않아도 된다.
 */
describe("사용자 신고 재현 — PNU 보유 + 동 단위 주소(용도지역이 그 증거)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    pointCalls.length = 0;
  });

  it("★77필지가 서로 다른 지번으로 복구되고, '지번 미확인' 은 **한 건도** 없다", () => {
    // 실제 저장 모습: 주소는 동 단위, PNU 는 진짜, 용도지역·지목·면적은 NED 보강분.
    writeSatongMapSelection(
      Array.from({ length: 77 }, (_, i) => ({
        id: `store-${i}-${DONG}`,
        address: DONG,
        pnu: `41370110001${String(1000 + i).padStart(4, "0")}0000`,
        areaSqm: 53 + i,
        zoneType: "자연녹지지역",
        jimok: "답",
        source: "excel" as const,
      })),
      null,
    );
    render(<SatongMapShell locale="ko" />);

    const labels = screen.getAllByTestId("parcel-jibun-text");
    expect(labels).toHaveLength(77); // 공허 진리 가드
    // ★77개가 서로 다르다 — 신고 증상("전부 오산시 내삼미동")의 정반대.
    expect(new Set(labels.map((el) => el.textContent)).size).toBe(77);
    // ★"복구 불가" 판정이 맞았다면 여기 77개가 떴어야 한다. 0개다.
    expect(screen.queryAllByTestId("parcel-jibun-unresolved")).toHaveLength(0);
    // 좌표가 없어도 좌표 치유를 부를 필요가 없다(PNU 로 이미 해석된다).
    expect(pointCalls).toEqual([]);
  });
});
