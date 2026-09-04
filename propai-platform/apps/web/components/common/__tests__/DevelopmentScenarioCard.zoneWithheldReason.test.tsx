/**
 * 개발방식 카드 — **보류 사유가 화면에 도달하는가**(★배선층 락).
 *
 * 【무엇이 잘못돼 있었나 — 2026-09-04 실측】
 * 백엔드는 우세 용도지역을 단일화하지 못하면 보류값 계약대로 `primary_zone: null` +
 * `primary_zone_absent: "ambiguous"` 를 **응답에 싣는다**. 그런데 화면 소비처가 **0건**이라
 * 카드는 `{site.primary_zone || "용도미상"}` 폴백만 탔다 — **사유가 버려졌다.**
 * 사용자도 조사자도 「왜 용도미상인지」를 알 수 없었다(**진단 불가는 그 자체로 장애다**).
 *
 * 【★왜 함수 락으로 부족한가】
 * `lib/zoning/dominant-zone.ts` 를 아무리 잠가도 **카드가 그 함수를 부르지 않으면** 무잠금이다.
 * 이 저장소는 *"변이를 함수 안에만 넣으면 5/5 CAUGHT 인데 배선은 무잠금"* 을 실측한 전례가 있다.
 * 그래서 이 파일은 **`simulate` 응답 → 화면**이라는 **같은 경로**를 태운다.
 *
 * 【잠그는 것 — 두 모집단을 **같은 실행**에서】
 *   1. 보류 응답 → 사유 문구가 화면에 뜬다 (raw 코드는 절대 안 나온다)
 *   2. ★정상 응답 → 용도지역 이름이 **글자까지 종전 그대로**이고 사유 칩은 **뜨지 않는다**
 *      (위양성 방지 — 가드가 정상 화면에 경고를 붙이면 그것도 결함이다)
 *   3. 어휘 밖 코드 → 아무것도 지어내지 않는다
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
// ★기대 문구를 **테스트에 적지 않고 계약에서 파생**시킨다. 여기에 한글을 다시 적으면
//   그 사본이 계약과 갈릴 때 **테스트가 옛 문구를 정답으로 못 박는다**.
import { ABSENT_CODES, ABSENT_REASONS, ABSENT_SHORT } from "@/lib/withheld/absent-reasons";

const ADDR = "서울특별시 동작구 상도동 211-376";
const ZONE = "제2종일반주거지역";

/** 보류 3종 세트를 백엔드 계약 그대로. `site` 외 나머지는 두 모집단이 **동일**하다. */
function reply(site: Record<string, unknown>) {
  post.mockResolvedValue({
    site: {
      multi: true, parcel_count: 2, resolved_parcel_count: 2,
      unresolved_parcels: [], area_is_partial: false, total_area_sqm: 12000,
      primary_zone_is_inferred: false,
      ...site,
    },
    scenarios: [{
      scheme: "지구단위계획 연계", applicable: "조건부", est_far: 300,
      contribution_pct: 15, requirements: [], pros: [], cons: [],
      notes: "테스트", buildable_types: ["아파트"],
    }],
    recommended: { scheme: "지구단위계획 연계", est_far: 300, reason: "테스트" },
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
  // ★공허 진리 가드 — 결과가 실제로 렌더됐는가. 안 됐으면 아래 «없다» 단언이 전부 무의미하다.
  expect((await screen.findAllByText(/지구단위계획 연계/)).length).toBeGreaterThan(0);
}

describe("보류 사유 도달 — `primary_zone_absent`", () => {
  // ★**양성 방향도 어휘 전수**다. 첫 판은 `ambiguous` 하나만 태웠고, 그래서 툴팁에 박힌
  //   `ambiguous` 전용 산문이 **7종 전부에 붙는** 결함을 못 봤다(적대 리뷰 MEDIUM-1).
  //   *"이 단언이 초록일 때 **반대로 틀린 구현**도 초록인가"* — 한 코드만 보면 초록이었다.
  it.each(ABSENT_CODES)("★보류(%s)면 **왜** 보류인지가 화면에 뜬다 — 칩·툴팁이 서로 모순되지 않는다", async (code) => {
    reply({ primary_zone: null, primary_zone_basis: code, primary_zone_absent: code });
    await runCard();

    // 칩은 짧은 라벨 — 계약에서 파생한다(테스트가 문구를 지어내지 않는다).
    const chip = await screen.findByText(ABSENT_SHORT[code]);
    // ★툴팁은 **같은 코드의** 긴 문구여야 한다. 여기가 종전에 `ambiguous` 산문으로 고정돼
    //   `source_unavailable` 일 때 «조회 못 함» 옆에서 «판정 안 함» 이라 단정했다.
    expect(chip.getAttribute("title")).toBe(ABSENT_REASONS[code]);
    // ★다른 코드의 문구가 새어 들어오지 않는다(한 사유를 다른 사유의 이름으로 부르지 않는다).
    for (const other of ABSENT_CODES) {
      if (other === code) continue;
      expect(chip.getAttribute("title"), `${code} 칩이 ${other} 문구를 달았다`)
        .not.toBe(ABSENT_REASONS[other]);
    }
    // ★raw 코드가 사용자에게 맨몸으로 나가지 않는다(이 모듈군의 존재 이유).
    expect(document.body.textContent ?? "").not.toContain(code);
    // 값 자리는 종전 폴백 그대로다 — 사유는 **별도 칩**이지 이름 대체가 아니다.
    expect(screen.getAllByText("용도미상").length).toBeGreaterThan(0);
  });

  it("★정상 응답은 **글자까지 종전 그대로**이고 사유 칩이 뜨지 않는다(위양성 방지)", async () => {
    reply({ primary_zone: ZONE, primary_zone_basis: "area_weighted" });
    await runCard();

    expect(screen.getAllByText(ZONE).length).toBeGreaterThan(0);
    expect(screen.queryByText("용도미상")).toBeNull();
    // ★어휘 **전체**를 훑는다 — 「ambiguous 만 안 뜬다」는 목록형이라 상한이 된다.
    //   긴 문구·짧은 라벨 **양쪽** 축을 본다(한 축만 보면 다른 축으로 샌다).
    for (const code of ABSENT_CODES) {
      expect(screen.queryByText(ABSENT_REASONS[code]), `정상 화면에 사유가 떴다: ${code}`).toBeNull();
      expect(screen.queryByText(ABSENT_SHORT[code]), `정상 화면에 짧은 라벨이 떴다: ${code}`).toBeNull();
    }
  });

  it("★어휘 밖 코드면 아무것도 지어내지 않는다", async () => {
    reply({ primary_zone: null, primary_zone_absent: "zzz_not_in_vocabulary" });
    await runCard();

    expect(screen.getAllByText("용도미상").length).toBeGreaterThan(0);
    expect(document.body.textContent ?? "").not.toContain("zzz_not_in_vocabulary");
    for (const code of ABSENT_CODES) {
      expect(screen.queryByText(ABSENT_REASONS[code])).toBeNull();
      expect(screen.queryByText(ABSENT_SHORT[code])).toBeNull();
    }
  });
});
