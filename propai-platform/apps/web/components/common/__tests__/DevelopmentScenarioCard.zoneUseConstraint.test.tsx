/**
 * 개발방식 카드 — **용도지역 법정 제약 고지가 화면에 도달하는가**(표면층 락).
 *
 * 【무엇이 잘못돼 있었나 — 적대 리뷰 3차 실측 2026-09-02】
 * 백엔드가 제1종일반주거 부지에서 아파트 제안에 `zone_use_constraint` 를 붙이도록 고쳤는데,
 * **화면 소비처가 0건**이었다(같은 카드의 형제 필드 `pros`·`requirements`·`notes`·
 * `buildable_types` 는 전부 렌더되는데 `cons`·`zone_use_constraint` 만 0회).
 * 그래서 제1종 부지에서 *"주상복합 아파트"* 가 **아무 경고 없이** 떴다.
 * ★백엔드 주석은 *"소비되기 전까지는 `cons` 에도 싣는다"* 고 적었는데 **`cons` 도 0회**였다 —
 *   정직 신호를 만들어 놓고 **도달을 확인하지 않은** 것이다("정의만 하고 소비처 0").
 *
 * 【이 파일이 잠그는 것】
 *   1. 제약이 오면 **경고로** 렌더된다(근거 조문 포함)
 *   2. ★**「건축 가능」 칩 목록에는 부정 문구가 섞이지 않는다** — 경고를 상품명 자리에 넣으면
 *      *"아파트"* 와 *"아파트 불가"* 가 나란히 선다. 그건 고친 것이 아니라 **문구로 덮은 것**이다.
 *   3. 대조군: 제약이 없으면 경고가 **뜨지 않는다**(위양성 방지)
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

const ADDR = "서울특별시 동작구 상도동 211-376";

const SITE = {
  multi: true,
  parcel_count: 2,
  resolved_parcel_count: 2,
  unresolved_parcels: [],
  area_is_partial: false,
  primary_zone: "제2종일반주거지역",
  primary_zone_is_inferred: false,
  total_area_sqm: 12000,
};

/** 백엔드가 보내는 「건축 가능」 목록 — 락이 **이 값과 결속**한다(존재 단언은 공허해진다). */
const BUILDABLE = ["주상복합 아파트", "오피스텔", "상가"];

const CONSTRAINT = {
  zones: ["제1종일반주거지역"],
  prohibited: ["아파트"],
  message: "제1종일반주거지역: 현 용도지역은 아파트 불허 — 용도지역 변경(종상향) 등 별도 절차 전제",
  legal_ref: "국토계획법 시행령 §71①3호 [별표 4] 1호 나목 — 공동주택(아파트를 제외한다)",
};

/** 백엔드 계약 그대로 — 아파트를 제안하는 방식 + 제약. */
function reply(withConstraint: boolean) {
  post.mockResolvedValue({
    site: SITE,
    scenarios: [
      {
        scheme: "역세권 활성화사업",
        applicable: "조건부",
        est_far: 400,
        contribution_pct: 20,
        requirements: ["역세권 350m"],
        pros: ["용적 상향"],
        cons: [],
        notes: "역세권 활성화",
        buildable_types: [...BUILDABLE],
        ...(withConstraint ? { zone_use_constraint: CONSTRAINT } : {}),
      },
    ],
    recommended: { scheme: "역세권 활성화사업", est_far: 400, reason: "테스트" },
  });
}

beforeEach(() => {
  post.mockReset();
  window.localStorage.clear();
});

async function runCard() {
  render(<DevelopmentScenarioCard address={ADDR} parcels={[ADDR]} />);
  await userEvent.click(screen.getByRole("button", { name: /분석|시뮬|실행/ }));
  await waitFor(() => expect(post).toHaveBeenCalled());
}

describe("용도지역 법정 제약 고지", () => {
  it("제약이 오면 경고로 렌더된다(근거 조문 포함)", async () => {
    reply(true);
    await runCard();

    // ★공허 진리 가드 — 시나리오 자체가 렌더됐는가(안 됐으면 아래가 무의미하다).
    //   추천안과 목록 양쪽에 뜨므로 findAll 로 받는다(단수 조회는 "여럿"으로 실패한다).
    expect((await screen.findAllByText(/역세권 활성화사업/)).length).toBeGreaterThan(0);

    const warn = await screen.findByText(/현 용도지역은 아파트 불허/);
    expect(warn).toBeTruthy();
    // 근거 조문이 함께 나와야 한다 — 사유 없는 경고는 사용자가 다음 행동을 정할 수 없다.
    expect(warn.textContent ?? "").toContain("별표 4");
  });

  it("★「건축 가능」 칩 목록에는 부정 문구가 섞이지 않는다", async () => {
    reply(true);
    await runCard();

    const label = await screen.findByText("건축 가능");
    const chips = Array.from(label.parentElement?.querySelectorAll("span") ?? [])
      // ★`.trim()` 이 없으면 라벨 자신이 필터를 통과한다 — 아이콘 때문에 `textContent` 가
      //   `" 건축 가능"`(앞 공백)이라 `!== "건축 가능"` 이 참이 되기 때문이다.
      //   그러면 `chips` 가 **영원히 최소 1개**라 아래 존재 단언이 **그 자체로 공허**해진다
      //   (실측: 칩을 0개 렌더해도 초록 / 라벨 공백을 지우면 CAUGHT).
      //   ★공허진리를 막으려고 쓴 가드가 공허했다 — 이 PR 이 고친다고 선언한 결함 클래스다.
      .map((el) => (el.textContent ?? "").trim())
      .filter((t) => t && t !== "건축 가능");

    // ★존재 단언이 아니라 **픽스처와 결속**시킨다 — 0개·누락·주입을 한 번에 잡는다.
    expect(chips).toEqual(BUILDABLE);
    for (const t of chips) {
      // 닫힌 토큰 집합 — 상수 하나의 부재가 아니라 **속성**을 잠근다.
      for (const bad of ["불가", "불허", "제외", "금지"]) {
        expect(t).not.toContain(bad);
      }
    }
  });

  it("제약이 없으면 경고가 뜨지 않는다(대조군 — 위양성 방지)", async () => {
    reply(false);
    await runCard();

    expect((await screen.findAllByText(/역세권 활성화사업/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/현 용도지역은 아파트 불허/)).toBeNull();
  });
});
