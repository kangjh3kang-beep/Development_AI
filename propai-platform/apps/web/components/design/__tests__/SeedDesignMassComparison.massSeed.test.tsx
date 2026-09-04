/**
 * SeedDesignMassComparison — 사통맵 인계 **수신 배선**(W4).
 *
 * ★여기가 인계 사슬의 마지막 칸이고, 끊겨도 화면상 아무 표시가 없다: 지도에서 CTA를 눌러
 *   저장까지 됐는데 이 컴포넌트가 요청에 싣지 않으면, 사용자는 "지도에서 고른 대로 시작됐다"고
 *   믿지만 실제 계산은 시드를 전혀 모른다. 그래서 **요청 본문**을 직접 단언한다.
 *
 * 함께 잠그는 정직 계약:
 *   ① 부지가 다르면 싣지 않는다(다른 필지 선택의 조용한 오적용 금지)
 *   ② 만료된 인계는 싣지 않는다
 *   ③ 서버가 map_seeded_mass를 안 주면 카드를 만들지 않는다(무날조)
 *   ④ 카드를 그릴 때 "층수는 상한으로만 작용한다"는 고지가 반드시 함께 뜬다
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SeedDesignMassComparison } from "@/components/design/SeedDesignMassComparison";
import { MASS_SEED_MAX_AGE_MS, writeMassSeedHandoff } from "@/lib/satong-mass-seed";

const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
const response = { current: null as unknown };

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      post: vi.fn((path: string, opts?: { body?: Record<string, unknown> }) => {
        posts.push({ path, body: opts?.body ?? {} });
        return Promise.resolve(response.current);
      }),
    },
  };
});

const ADDR = "경상북도 포항시 남구 호미곶면 대보리 산1-1";

const MASS = {
  num_floors: 12, far_percent: 190.0, bcr_percent: 48.0,
  total_floor_area_sqm: 1900, building_area_sqm: 480, height_m: 36,
};

function baseResponse(over: Record<string, unknown> = {}) {
  return {
    region: "포항시 남구",
    legal_max_mass: MASS,
    regional_typical_mass: null,
    mass_reference: null,
    applied_limit_source: "engine_zone_defaults",
    ...over,
  };
}

function seedHandoff(over: Partial<{ address: string; savedAt: number }> = {}) {
  writeMassSeedHandoff({
    pnu: null,
    address: over.address ?? ADDR,
    areaSqm: 1000,
    targetFloors: 15,
    optionLabel: "판상형 25°",
    savedAt: over.savedAt ?? Date.now(),
  });
}

/** 조회 버튼을 눌러 요청을 발생시킨다. */
async function fetchOnce() {
  const btn = await screen.findByRole("button", { name: /전형|조회|비교|매스/ });
  btn.click();
  await waitFor(() => expect(posts.length).toBeGreaterThan(0));
}

describe("SeedDesignMassComparison — 매스 시드 수신(W4)", () => {
  beforeEach(() => {
    posts.length = 0;
    response.current = baseResponse();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("★① 같은 부지의 인계가 있으면 요청에 map_target_floors를 싣는다", async () => {
    seedHandoff();
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(posts[0].path).toBe("/mass-templates/seed-design");
    expect(posts[0].body.map_target_floors).toBe(15);
    expect(posts[0].body.map_option_label).toBe("판상형 25°");
  });

  it("★② 인계가 없으면 시드 필드를 싣지 않는다(기존 호출 무회귀)", async () => {
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(posts[0].body.map_target_floors).toBeUndefined();
    expect(posts[0].body.map_option_label).toBeUndefined();
  });

  it("★③ 부지가 다르면 싣지 않는다 — 다른 필지의 선택이 조용히 시드가 되면 안 된다", async () => {
    seedHandoff({ address: "완전히 다른 주소 123" });
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(posts[0].body.map_target_floors).toBeUndefined();
  });

  it("★④ 만료된 인계는 싣지 않는다(한참 전 선택의 뒤늦은 반영 금지)", async () => {
    seedHandoff({ savedAt: Date.now() - MASS_SEED_MAX_AGE_MS - 60_000 });
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(posts[0].body.map_target_floors).toBeUndefined();
  });

  it("★⑤ 서버가 map_seeded_mass를 주면 카드와 **상한 고지**가 함께 뜬다", async () => {
    seedHandoff();
    response.current = baseResponse({
      map_seeded_mass: { ...MASS, num_floors: 15 },
      map_seed: { target_floors: 15, option_label: "판상형 25°" },
    });
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(await screen.findByText("지도에서 고른 안")).toBeTruthy();
    // ★고지가 없으면 사용자는 "내가 고른 대로 지어진다"로 읽는다.
    const notice = await screen.findByText(/상한으로 반영/);
    expect(notice.textContent).toContain("부풀리지 않습니다");
    expect(notice.textContent).toContain("동 배치 도형");
  });

  it("★★⑦ 시드가 **미적용**이면 침묵하지 않고 그 사실을 알린다(R1 HIGH-1 회귀락)", async () => {
    // 종전엔 미적용이어도 카드가 뜨고 "반영했다"고 고지해, 5층을 고른 사용자가 38층을
    // '고른 안'으로 읽는 표기 사기가 됐다. 이제 서버가 applied=false로 알리고 화면은 고지한다.
    seedHandoff();
    response.current = baseResponse({
      map_seeded_mass: null,
      map_seed: {
        target_floors: 5,
        option_label: "판상형 25°",
        applied: false,
        not_applied_reason: "이 용도지역·매스 형식(예 포디움-타워)에서는 층수 시드가 반영되지 않습니다.",
      },
    });
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="일반상업지역" buildingUse="공동주택" />);
    await fetchOnce();

    const notice = await screen.findByText(/반영되지 않았습니다/);
    expect(notice.textContent).toContain("판상형 25°");
    // ★반영 안 됐는데 '고른 안' 카드가 뜨면 안 된다.
    expect(screen.queryByText("지도에서 고른 안")).toBeNull();
  });

  it("★⑧ 다필지(합산 면적)면 인계를 싣지 않는다 — 단일필지 층수 오적용 차단(R1 HIGH-3)", async () => {
    seedHandoff(); // 인계 면적 1000㎡
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={2500} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    expect(posts[0].body.map_target_floors).toBeUndefined();
  });

  it("★⑨ 마운트 후 만료된 인계는 **요청 시점**에 걸러진다(R2 MR7 — 생존 변이 봉합)", async () => {
    // 마운트 때 한 번만 판정하면, 탭을 오래 열어둔 뒤 조회할 때 만료분이 그대로 전송된다.
    // 여기서는 마운트 시엔 신선하고 **클릭 직전에** 만료되도록 시계를 옮긴다.
    const t0 = Date.now();
    seedHandoff({ savedAt: t0 });
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);

    const spy = vi.spyOn(Date, "now").mockReturnValue(t0 + MASS_SEED_MAX_AGE_MS + 60_000);
    try {
      await fetchOnce();
      expect(posts[0].body.map_target_floors).toBeUndefined();
    } finally {
      spy.mockRestore();
    }
  });

  it("★⑩ 부지 불일치로 인계를 쓰지 않으면 **조회 전에도** 그 사실을 알린다(R2 MEDIUM-1)", () => {
    // 침묵하면 사용자는 "이 안으로 설계 시작"을 누른 뒤 아무 신호도 못 받는다.
    seedHandoff(); // 인계 면적 1000㎡
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={2500} zoning="제3종일반주거지역" buildingUse="공동주택" />);

    const notice = screen.getByText(/적용하지 않았습니다/);
    expect(notice.textContent).toContain("판상형 25°");
  });

  it("★⑥ 서버가 map_seeded_mass를 주지 않으면 카드를 만들지 않는다(무날조)", async () => {
    seedHandoff();
    response.current = baseResponse(); // map_seeded_mass 없음
    render(<SeedDesignMassComparison address={ADDR} landAreaSqm={1000} zoning="제3종일반주거지역" buildingUse="공동주택" />);
    await fetchOnce();

    await waitFor(() => expect(screen.queryByText("적용 한도 최대")).toBeTruthy());
    expect(screen.queryByText("지도에서 고른 안")).toBeNull();
  });
});
