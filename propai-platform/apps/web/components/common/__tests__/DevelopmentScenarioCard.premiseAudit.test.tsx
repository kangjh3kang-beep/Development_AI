/**
 * 개발방식 카드 — **전제 감사가 화면에 도달하는가**(★배선층 락).
 *
 * 【무엇이 잘못돼 있었나 — 2026-09-04 실측】
 * `#963` 이 감사기를 이 경로에 배선해 응답에 `premise_audit` 를 싣는데, **프론트 소비처가 0건**
 * 이었다(대조군: 카드가 최상위에서 읽는 키 12종 실재 → 조회기 생존).
 * ★`#963` 커밋 본문이 *"`#940` 에서 «백엔드 계약만 서고 화면 소비처 0» 으로 데였으므로 여기
 *   싣는 것만으로 끝내지 않는다 — **소비처는 별도 좌표로 남긴다**"* 라 적었고, 여기가 그 좌표다.
 *
 * 【★왜 함수 락으로 부족한가】
 * `PremiseAuditNotice` 를 아무리 잠가도 **카드가 그것을 부르지 않으면** 무잠금이다.
 * 이 저장소는 *"변이를 함수 안에만 넣으면 CAUGHT 인데 배선은 무잠금"* 을 실측한 전례가 있다.
 * 그래서 이 파일은 **`simulate` 응답 → 화면**이라는 **같은 경로**를 태운다.
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
const DETAIL = "통합 우세 용도지역(자연녹지지역)과 시나리오 계산 기준(제2종일반주거지역)이 다릅니다.";

/** `premise_audit` 외 나머지는 두 모집단이 **완전히 동일**하다 — 그 축만이 답을 가른다. */
function reply(premise_audit: unknown) {
  post.mockResolvedValue({
    site: {
      multi: true, parcel_count: 2, resolved_parcel_count: 2,
      unresolved_parcels: [], area_is_partial: false, total_area_sqm: 12000,
      primary_zone: "제2종일반주거지역", primary_zone_is_inferred: false,
    },
    scenarios: [{
      scheme: "지구단위계획 연계", applicable: "조건부", est_far: 300,
      contribution_pct: 15, requirements: [], pros: [], cons: [],
      notes: "테스트", buildable_types: ["아파트"],
    }],
    recommended: { scheme: "지구단위계획 연계", est_far: 300, reason: "테스트" },
    premise_audit,
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

describe("전제 감사 도달 — `premise_audit`", () => {
  it("★위반이 오면 **백엔드 원문**이 화면에 뜬다(종전에는 소비처 0이라 버려졌다)", async () => {
    reply({
      violations: [{ relation: "path_invariance_zone", title: "경로 무관성", detail: DETAIL }],
      checked: 6, registered: 6,
    });
    await runCard();

    const box = await screen.findByTestId("premise-audit-notice");
    expect(box.dataset.state).toBe("violations");
    // ★평문 대조 — 문구의 괄호가 정규식 그룹으로 읽히는 함정을 피한다.
    expect(box.textContent ?? "").toContain(DETAIL);
  });

  it("★공허(한 건도 실행 안 됨)도 도달한다 — 「위반 없음」과 **다른 말**이어야 한다", async () => {
    // ★`checked` 는 **시도한 수**다(백엔드 락: *"빈 입력도 판정은 시도해야 한다"*).
    //   그러므로 0 은 «감사기를 한 건도 실행하지 못했다» 이지 «입력이 부족했다» 가 아니다.
    reply({ violations: [], checked: 0, registered: 6 });
    await runCard();

    const box = await screen.findByTestId("premise-audit-notice");
    expect(box.dataset.state).toBe("vacuous");
    expect(box.textContent ?? "").toContain("확인하지 못함");
  });

  it("★감사기 사망도 도달한다 — **왜** 못 했는지가 화면에 있다(무언 실패 금지)", async () => {
    reply({ violations: [], checked: 0, registered: null, reason: "audit_failed", detail: "감사 실패 사유 문구" });
    await runCard();

    const box = await screen.findByTestId("premise-audit-notice");
    expect(box.dataset.state).toBe("failed");
    expect(box.textContent ?? "").toContain("감사 실패 사유 문구");
  });

  it("★★음성 대조군 — **배선된 백엔드가 정상 부지에서 실제로 내는 페이로드**면 무렌더", async () => {
    // ★★이 픽스처가 이 파일에서 가장 중요하다. 첫 판은 `structurally_vacuous` 키가 **없는**
    //   모양을 「정상」이라 불렀는데, 성공 경로는 **항상** 그 키를 덧씌운다
    //   (`scenario_simulator.py` 실측). 그래서 «정상 화면이 깨끗하다» 가 초록인데
    //   **실제 정상 화면은 경고 상자를 달고 있었다** — 픽스처가 그 축을 원리적으로 못 태웠다.
    //   ★*"정상 화면에 배지를 늘리지 않는다"* 를 설계 중심에 놓고 **정상 화면에만** 띄우고 있었다.
    reply({ violations: [], checked: 6, registered: 6, structurally_vacuous: ["path_invariance_zone"] });
    await runCard();
    expect(screen.queryByTestId("premise-audit-notice")).toBeNull();
  });

  it("★부분 실행(관계가 죽음)은 도달하되 사유를 **날조하지 않는다**", async () => {
    reply({ violations: [], checked: 4, registered: 6, structurally_vacuous: ["path_invariance_zone"] });
    await runCard();

    const box = await screen.findByTestId("premise-audit-notice");
    expect(box.dataset.state).toBe("partial");
    expect(box.querySelector("p")?.textContent).toBe("전제 감사 부분 실행 · 4/6");
    // 백엔드는 「입력 부족」이라는 사유를 준 적이 없다.
    expect(box.textContent ?? "").not.toContain("입력이 부족");
  });

  it("★필드가 없어도 화면이 깨지지 않고 아무 주장도 하지 않는다", async () => {
    reply(undefined);
    await runCard();
    expect(screen.queryByTestId("premise-audit-notice")).toBeNull();
  });

  it("★고지가 시나리오 표 **위**에 온다 — 판정을 읽기 전에 교차검증 여부를 알아야 한다", async () => {
    reply({ violations: [{ relation: "r", title: "t", detail: DETAIL }], checked: 6, registered: 6 });
    await runCard();

    const box = await screen.findByTestId("premise-audit-notice");
    const scheme = (await screen.findAllByText(/지구단위계획 연계/))[0];
    // ★좌표가 아니라 **문서 순서**로 판정한다(DOCUMENT_POSITION_FOLLOWING = 4).
    expect(box.compareDocumentPosition(scheme) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
