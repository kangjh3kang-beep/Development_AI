/**
 * 개발방식 카드 — **면적 부분집계·용도지역 추론값**을 화면이 말한다 + 필지 상세를 전송한다.
 *
 * 【무엇이 잘못돼 있었나 — 2026-08-19 라이브 실측】
 * 백엔드가 주소만 받아 면적을 재파생하는데, 주소가 해석되지 않으면
 * `land_area_sqm=None` 이라 그 필지가 **0㎡** 로 합산됐다. 그 결과 총면적이 실제보다 작아지고
 * 면적 게이트가 개발방식을 대량 '불가'로 막는데, **화면은 왜 막혔는지 말하지 못했다**.
 * 같은 실패 경로에서 용도지역은 주소 문자열로부터 **추론**돼(`keyword_inference`) 들어왔다.
 *
 * 【이 파일이 잠그는 것 — 표면층】
 * 백엔드가 정직 신호를 내도 **화면이 읽지 않으면 고친 것이 아니다**("정의만 하고 소비처 0").
 *   1. 부분집계 배지가 **분모와 함께** 뜬다(N필지 중 M필지)
 *   2. 추론 용도지역이 **단정되지 않는다**
 *   3. 대조군: 전부 실측이면 두 배지 모두 **뜨지 않는다**(가드 위양성 방지)
 *   4. 배선: 필지 상세(면적)를 가진 호출자는 **주소가 아니라 상세를 전송**한다
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: async () => ({}),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));

import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";

const ADDR_A = "경기도 오산시 내삼미동 산 66";
const ADDR_B = "경기도 오산시 내삼미동 1";

/** 백엔드 `site` 페이로드(실측 계약) — 2필지 중 1필지만 조회된 상태. */
const PARTIAL_SITE = {
  multi: true,
  parcel_count: 2,
  resolved_parcel_count: 1,
  unresolved_parcels: [{ address: ADDR_B, reason: "용도지역 추론값(주소 미해석 — 조회 실패)" }],
  area_is_partial: true,
  primary_zone: "자연녹지지역",
  primary_zone_is_inferred: false,
  total_area_sqm: 12309,
};

const CLEAN_SITE = {
  multi: true,
  parcel_count: 2,
  resolved_parcel_count: 2,
  unresolved_parcels: [],
  area_is_partial: false,
  primary_zone: "자연녹지지역",
  primary_zone_is_inferred: false,
  total_area_sqm: 86755,
};

function reply(site: Record<string, unknown>) {
  post.mockResolvedValue({
    site,
    scenarios: [],
    recommended: { scheme: "단순 건축", est_far: 100, reason: "테스트" },
  });
}

beforeEach(() => {
  post.mockReset();
  window.localStorage.clear();
});

async function runCard(ui: React.ReactElement) {
  render(ui);
  await userEvent.click(screen.getByRole("button", { name: /분석|시뮬|실행/ }));
  await waitFor(() => expect(post).toHaveBeenCalled());
}

describe("면적 부분집계 정직 표기", () => {
  it("미해석 필지가 있으면 분모와 함께 배지를 띄운다", async () => {
    reply(PARTIAL_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);

    const badge = await screen.findByText(/면적 부분집계/);
    // ★분모가 없으면 "작은 부지"로 오독된다 — 두 수가 모두 보여야 한다.
    expect(badge.textContent).toContain("2필지 중 1필지");
  });

  it("전부 조회되면 배지를 띄우지 않는다(대조군 — 가드 위양성 방지)", async () => {
    reply(CLEAN_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);

    // 공허 진리 가드 — 결과 자체는 렌더됐는가(안 렌더면 "없음"이 당연히 참이 된다).
    expect(await screen.findByText(/86,755㎡/)).toBeTruthy();
    expect(screen.queryByText(/면적 부분집계/)).toBeNull();
  });

  it("용도지역이 추론값이면 단정하지 않는다", async () => {
    reply({ ...PARTIAL_SITE, primary_zone_is_inferred: true });
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);

    expect(await screen.findByText(/용도지역 추론값/)).toBeTruthy();
  });

  it("조회된 용도지역이면 추론 배지를 띄우지 않는다(대조군)", async () => {
    reply(CLEAN_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);

    expect(await screen.findByText("자연녹지지역")).toBeTruthy();
    expect(screen.queryByText(/용도지역 추론값/)).toBeNull();
  });
});

describe("필지 상세 전송 배선", () => {
  it("★면적을 가진 호출자는 주소가 아니라 상세를 보낸다", async () => {
    reply(CLEAN_SITE);
    await runCard(
      <DevelopmentScenarioCard
        address={ADDR_A}
        parcels={[ADDR_A, ADDR_B]}
        parcelRows={[
          { address: ADDR_A, area_sqm: 12309, zone_type: "자연녹지지역" },
          { address: ADDR_B, area_sqm: 74446, zone_type: "자연녹지지역" },
        ]}
      />
    );

    const body = (post.mock.calls[0][1] as { body: { parcels: unknown } }).body;
    const sent = body.parcels as { address: string; area_sqm: number }[];
    // 문자열 배열이면 면적이 사라진다 — 객체로 갔는지, 면적이 실렸는지 둘 다 본다.
    expect(Array.isArray(sent)).toBe(true);
    expect(typeof sent[0]).toBe("object");
    expect(sent.map((r) => r.area_sqm)).toEqual([12309, 74446]);
  });

  it("상세가 없으면 종전대로 주소 배열을 보낸다(무회귀)", async () => {
    reply(CLEAN_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);

    const body = (post.mock.calls[0][1] as { body: { parcels: unknown } }).body;
    expect(body.parcels).toEqual([ADDR_A, ADDR_B]);
  });
});

/**
 * ★2026-08-28 — **붕괴**는 조회 실패와 **다른 사실**이다.
 *
 * 사용자 신고: 77필지·86,755㎡ 프로젝트가 **44㎡(13평)** 로 시뮬레이션돼 개발방식 19건이
 * 거짓 '불가'로 막혔다. 원인은 필지 주소에 지번이 없어 **77개가 한 문자열로 붕괴**한 것이고,
 * 그때 `parcel_count` 는 붕괴 **후** 값(1)이라 종전 문구를 쓰면
 * 「1필지 중 1필지만 조회됨」이라는 **무의미한 말**이 된다.
 */
const COLLAPSED_SITE = {
  multi: false,
  parcel_count: 1,
  resolved_parcel_count: 1,
  unresolved_parcels: [],
  requested_parcel_count: 77,
  collapsed_parcel_count: 76,
  area_is_partial: true,
  primary_zone: "자연녹지지역",
  primary_zone_is_inferred: false,
  total_area_sqm: 44,
};

describe("필지 주소 붕괴 고지", () => {
  it("C1 ★붕괴하면 **요청 수와 사용 수**를 말한다(분모가 붕괴 전이어야 한다)", async () => {
    reply(COLLAPSED_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);
    await waitFor(() => expect(screen.getByText(/필지 주소 중복/)).toBeTruthy());
    // ★77(요청)이 보여야 한다 — 1(사용)만 보이면 "원래 1필지였다"와 구별되지 않는다.
    expect(screen.getByText(/77필지 요청 중 1필지만 구분됨/)).toBeTruthy();
  });

  it("C2 ★붕괴 문구와 조회실패 문구는 **서로 다른 말**이다(한 문구로 뭉개지 않는다)", async () => {
    reply(COLLAPSED_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);
    await waitFor(() => expect(screen.getByText(/필지 주소 중복/)).toBeTruthy());
    // 붕괴일 때 「N필지 중 M필지만 조회됨」이 함께 뜨면 1중1 이라는 무의미한 말이 된다.
    expect(screen.queryByText(/필지만 조회됨/)).toBeNull();
  });

  it("C3 ★조회실패 경로는 **종전 문구 그대로**(무회귀)", async () => {
    reply(PARTIAL_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);
    await waitFor(() => expect(screen.getByText(/필지만 조회됨/)).toBeTruthy());
    expect(screen.queryByText(/필지 주소 중복/)).toBeNull();
  });

  it("C4 ★대조군 — 붕괴도 실패도 없으면 두 배지 **모두** 안 뜬다(위양성 방지)", async () => {
    reply(CLEAN_SITE);
    await runCard(<DevelopmentScenarioCard address={ADDR_A} parcels={[ADDR_A, ADDR_B]} />);
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(screen.queryByText(/필지 주소 중복/)).toBeNull();
    expect(screen.queryByText(/필지만 조회됨/)).toBeNull();
  });
});
