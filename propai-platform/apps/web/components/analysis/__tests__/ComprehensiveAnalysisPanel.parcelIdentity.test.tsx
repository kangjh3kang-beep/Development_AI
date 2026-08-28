/**
 * 종합분석 패널 — 다필지가 **주소 문자열 붕괴**로 단필지가 되지 않는다.
 *
 * 【사용자 신고 · 2026-08-28】
 * 프로젝트가 **77필지 · 86,755㎡** 인데 「최적 개발방식 시뮬레이션」이 **44㎡(약 13평)** 로
 * 계산했다. 같은 화면의 실효용적률·적정공급면적은 86,755㎡ 를 썼다 —
 * **한 화면이 1,972배 다른 두 면적으로 말했다.** 그 44㎡ 가
 * 「도시개발사업: 총면적 44m² < 1만m² 요건 미달」 등 **19개 개발방식을 거짓 '불가'** 로 막았다.
 *
 * 【근본 원인】
 * 이 패널이 스토어 필지의 `address` 를 **그대로** 넘겼다. 그 주소엔 지번이 없을 수 있어
 * (예: "경기도 오산시 내삼미동") **77필지가 모두 같은 문자열**이 되고, 백엔드
 * `scenario_simulator._merge` 가 주소로 중복제거하면서 **1필지로 붕괴**했다.
 *
 * ★처방은 이미 저장소에 있었다 — `lib/parcel-rows.ts` 가 `parcelDisplayAddress` 로
 *   **PNU 에서 지번을 파생**한다. 그 파일 주석이 이 결함을 그대로 적어 뒀다:
 *   *"여기서 지번이 빠지면 백엔드가 같은 동의 필지를 구분하지 못한다."*
 *   형제 3화면은 그 헬퍼를 쓰는데 **이 패널만 손수 복제**했다(타입만 임포트하고 빌더는 베낌).
 *
 * 【이 파일이 잠그는 것】
 * 스토어에 **같은 주소·다른 PNU** 필지가 있을 때, 시뮬레이션 카드로 내려가는 값이
 * **서로 구분되는가**. 구분되지 않으면 백엔드에서 붕괴한다.
 */

import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ★타입은 **제네릭**으로 주고 구현은 무인자로 둔다(형제 `…stageSplit.test.tsx` 관례).
//   · `vi.fn(async () => ({}))` 만 쓰면 **0-인자**로 추론돼 `post(path, opts)` 가 tsc TS2554.
//   · 반대로 `async (_path, _opts) =>` 로 받으면 eslint `no-unused-vars` 경고가 늘어
//     **lint 래칫**(경고가 늘지 않았는가)이 CI 를 막는다. 둘 다 **차단 게이트**다.
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(async () => ({}));
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(
  async () => ({ providers: [] }),
);

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));
vi.mock("@/components/precheck/SatongMapShell", () => ({ SatongMapShell: () => null }));

/** 시뮬레이션 카드를 가로채 **패널이 무엇을 넘기는지** 그대로 본다(렌더 부작용 없이). */
const captured: { address?: string; parcels?: string[]; parcelRows?: { address: string }[] }[] = [];
vi.mock("@/components/common/DevelopmentScenarioCard", () => ({
  DevelopmentScenarioCard: (props: {
    address?: string; parcels?: string[]; parcelRows?: { address: string }[];
  }) => {
    captured.push({ address: props.address, parcels: props.parcels, parcelRows: props.parcelRows });
    return null;
  },
}));

import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const DONG = "경기도 오산시 내삼미동";

/** ★사용자 사례 그대로 — 주소는 **동까지만** 같고 PNU 는 서로 다르다. */
const PARCELS = [
  { address: DONG, areaSqm: 30000, zoneCode: "자연녹지지역", pnu: "4137011000104670001" },
  { address: DONG, areaSqm: 30000, zoneCode: "자연녹지지역", pnu: "4137011000101140001" },
  { address: DONG, areaSqm: 26755, zoneCode: "자연녹지지역", pnu: "4137011000104680001" },
];

beforeEach(() => {
  captured.length = 0;
  post.mockClear();
  useProjectContextStore.setState({
    siteAnalysis: {
      address: DONG,
      zoneCode: "자연녹지지역",
      parcels: PARCELS,
    } as never,
  } as never);
});

async function mount() {
  render(<ComprehensiveAnalysisPanel />);
  await waitFor(() => expect(captured.length).toBeGreaterThan(0));
  return captured[captured.length - 1];
}

describe("다필지 정체성 — 주소 붕괴 방지", () => {
  it("P1 ★같은 동 주소라도 **서로 구분되는** 주소로 내려간다(PNU 로 지번 파생)", async () => {
    const p = await mount();
    const addrs = p.parcels ?? [];
    expect(addrs.length).toBe(3);
    // ★핵심 — 고유값이 3이어야 한다. 1이면 백엔드에서 1필지로 붕괴한다(44㎡ 사고).
    expect(new Set(addrs).size).toBe(3);
  });

  it("P2 ★전송용 행도 구분된다 — 붕괴하면 면적이 합산되지 않는다", async () => {
    const p = await mount();
    const rows = p.parcelRows ?? [];
    expect(rows.length).toBe(3);
    expect(new Set(rows.map((r) => r.address)).size).toBe(3);
  });

  it("P3 ★음성 대조군 — 스토어에 PNU 가 없으면 **구분을 지어내지 않는다**", async () => {
    // 지어내면 존재하지 않는 필지가 만들어진다(무날조). 붕괴는 백엔드가 고지한다.
    useProjectContextStore.setState({
      siteAnalysis: {
        address: DONG, zoneCode: "자연녹지지역",
        parcels: PARCELS.map((x) => ({ ...x, pnu: null })),
      } as never,
    } as never);
    captured.length = 0;
    const p = await mount();
    expect(new Set(p.parcels ?? []).size).toBe(1);
  });

  it("P4 ★표시 모집단과 전송 모집단을 섞지 않는다 — 면적 없는 필지도 **선택 수**엔 남는다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: {
        address: DONG, zoneCode: "자연녹지지역",
        parcels: [...PARCELS, { address: DONG, areaSqm: 0, zoneCode: "자연녹지지역", pnu: "4137011000104690001" }],
      } as never,
    } as never);
    captured.length = 0;
    const p = await mount();
    // 사용자가 고른 것 = 4 (표시·게이트)
    expect((p.parcels ?? []).length).toBe(4);
    // 보낼 수 있는 것 = 3 (면적>0)
    expect((p.parcelRows ?? []).length).toBe(3);
  });
});

describe("대표주소 정체성 — 유령 필지 방지", () => {
  it("P5 ★대표주소도 **parcels 와 같은 형태**로 넘어간다(유령 주입 방지)", async () => {
    const p = await mount();
    // ★원본(지번 없는 동 주소)을 그대로 넘기면 백엔드 `_merge` 가 **별개 필지로 승격**해
    //   77 → 78 이 되고, `primary_zone` 이 그 유령(enriched[0])에서 나온다(독립 리뷰 실측).
    expect(p.address).not.toBe(DONG);
    expect(p.parcels).toContain(p.address);
  });

  it("P6 ★음성 대조군 — PNU 가 없으면 대표주소도 **원본 그대로**(지어내지 않는다)", async () => {
    useProjectContextStore.setState({
      siteAnalysis: {
        address: DONG, zoneCode: "자연녹지지역",
        parcels: PARCELS.map((x) => ({ ...x, pnu: null })),
      } as never,
    } as never);
    captured.length = 0;
    const p = await mount();
    expect(p.address).toBe(DONG);
  });
});
