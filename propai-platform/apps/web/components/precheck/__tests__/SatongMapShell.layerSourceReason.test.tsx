/**
 * ★★「주변에 없다」와 「못 봤다」가 **같은 문구**로 나오던 것을 가른다.
 *
 * ## 왜 (라이브 실측 2026-09-12)
 *
 *     GET /api/v1/auction/search?page_size=60
 *     → {"items":[],"total":0,"page":1,"page_size":60,"data_source":"unavailable"}
 *
 * 서버는 **데이터원 조회 불가**라고 답하는데, 화면은
 * `auctionNote || (auctionCount ? "경매 N곳" : "경매 무자료")`(`SatongMultiMap.tsx`) 로
 * **「경매 무자료」**, 즉 *"주변에 없다"* 라고 말했다. 빈 결과 분기가 **사유 없이 반환**했고
 * (`SatongMapShell.tsx` — `if (!items.length) { setAuctionItems([]); return; }`),
 * `data_source` 를 읽는 프론트 코드는 **0건**이었다.
 *
 * ★빠진 것은 「정직 표기」 전부가 아니라 **한 조건뿐**이었다 — 경매 경로는 이미 레이어 꺼짐·
 *   앵커 대기·미로그인 세 조건에 정직한 노트를 낸다. ***옳은 패턴이 바로 옆에 있었다.***
 *
 * ## 이 파일이 잠그는 축
 *
 * **순수 함수가 아니라 배선**이다. `resolveLayerSourceNote` 만 잠그면 «호출부가 안 부른다» 를
 * 못 잡는다 — 이 저장소가 `#1026` 에서 정확히 그렇게 뚫렸다(함수 안은 6/6 CAUGHT 인데
 * 호출부 `opts` 는 8/8 SURVIVED). 그래서 **지도에 실제로 전달되는 prop** 을 본다.
 */
import type { ReactNode } from "react";
import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { useSatongMapPrefs } from "@/store/useSatongMapPrefsStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

const captured: Record<string, unknown>[] = [];
let centerSent = false;
vi.mock("next/dynamic", () => ({
  default: () => (props: Record<string, unknown>) => {
    captured.push(props);
    // ★실제 지도는 moveend 에서 중심을 역전파한다 — 그것이 앵커의 폴백 출처이고,
    //   앵커가 없으면 조회 자체가 «앵커 대기» 노트에서 멈춰 이 테스트가 **공허**해진다.
    const cb = props.onCenterChange as ((c: { lat: number; lon: number }) => void) | undefined;
    if (cb && !centerSent) {
      centerSent = true;
      setTimeout(() => cb({ lat: 37.5, lon: 127.0 }), 0);
    }
    return <div data-testid="map-stub">{props.topRightSlot as ReactNode}</div>;
  },
}));

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    hasAccessToken: () => true,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: (...a: unknown[]) => getMock(...a),
      post: (...a: unknown[]) => postMock(...a),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

/** 경매 조회에만 응답하고 나머지는 영구 pending. */
const 경매응답 = (body: unknown) => {
  getMock.mockImplementation((path: unknown) =>
    typeof path === "string" && path.startsWith("/auction/search")
      ? Promise.resolve(body)
      : new Promise(() => {}),
  );
};
const 분양응답 = (body: unknown) => {
  postMock.mockImplementation((path: unknown) =>
    typeof path === "string" && path.startsWith("/presale/nearby")
      ? Promise.resolve(body)
      : new Promise(() => {}),
  );
};

const 그리기 = async (layer: "auction" | "presale") => {
  act(() => {
    useSatongMapPrefs.getState().ensureLayerEnabled(layer);
  });
  const view = render(<SatongMapShell locale="ko" />);
  await act(async () => {
    await new Promise((r) => setTimeout(r, 300));
  });
  return view;
};

/** 지도에 **마지막으로 전달된** 노트. ★빈 노트는 shell 이 `null` 로 넘긴다
 *  (`SatongMapShell.tsx:4378-4379` — `presaleEnabled ? presaleNote || null : null`).
 *  그래서 `""` 를 기대하면 영원히 틀린다 — **계약을 원문에서 읽고** `""` 로 정규화한다. */
const 마지막노트 = (key: "auctionNote" | "presaleNote"): string => {
  // ★리뷰 지적: `at(-1)` 만 보면 **렌더 순서가 바뀌어도 조용히** 다른 값을 본다.
  //   최소 완화 — 렌더가 실제로 일어났는지부터 단언한다(0이면 아래가 공허하다).
  expect(captured.length, "지도가 한 번도 렌더되지 않았다 — 이 단언은 공허하다").toBeGreaterThan(1);
  const last = captured.at(-1);
  const v = last?.[key];
  return typeof v === "string" ? v : "";
};

beforeEach(() => {
  captured.length = 0;
  centerSent = false;
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockImplementation(() => new Promise(() => {}));
  postMock.mockImplementation(() => new Promise(() => {}));
  window.sessionStorage.clear();
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null, projectName: "", projectStatus: "", siteAnalysis: null,
    });
    useSatongMapPrefs.getState().resetEnabledLayers();
  });
});

describe("★레이어 조회 사유가 화면까지 도달한다 — 「없다」와 「못 봤다」를 가른다", () => {
  it("★★경매: **서버가 준 사유가 그대로** 지도 prop 으로 간다", async () => {
    // ★★2026-09-12 2차 정정: 초판은 `data_source:"unavailable"` 을 「데이터원 조회 불가」로
    //   **매핑**했다. 그 토큰은 `onbid_client.py` 에서 **네 갈래**를 뭉치고 그중 `:308` 은
    //   **조회 성공 + 정말 없음**이다 — 거기서 「불가」는 ***「없다」를 「못 봤다」로 뒤집는 것***.
    //   ⇒ 프론트는 분류하지 않는다. 서버가 자기 말로 준 `reason` 을 그대로 말한다.
    경매응답({ items: [], total: 0, data_source: "unavailable", reason: "온비드 인증키 미설정(공공데이터포털 활용신청 필요)" });
    await 그리기("auction");

    expect(
      getMock.mock.calls.some((c) => String(c[0]).startsWith("/auction/search")),
      "경매 조회가 아예 안 나갔다 — 아래 단언이 공허해진다",
    ).toBe(true);
    const 경매노트 = 마지막노트("auctionNote");
    expect(경매노트, "서버 사유가 화면 prop 에 안 왔다").toContain("인증키 미설정");
    expect(경매노트, "노트에 레이어 이름이 없다 — 형제 노트와 구별되지 않는다").toContain("경매");
    // ★반대 방향 — 내 옛 매핑 문구로 **덮어쓰지 않는다**(그 문구는 네 갈래 중 하나에만 참이다).
    expect(경매노트, "서버 사유를 내 문구로 덮어썼다").not.toContain("데이터원 조회 불가");
  });

  it("★★★서버가 「정직한 0건」이라 하면 **그렇게 말한다**(「불가」로 뒤집지 않는다)", async () => {
    경매응답({ items: [], total: 0, data_source: "unavailable", reason: "온비드 응답 무자료(해당 조건의 공고 없음)" });
    await 그리기("auction");
    const note = 마지막노트("auctionNote");
    expect(note, "서버가 「무자료」라 했는데 화면이 「불가」라 말한다 — 정상 상태를 장애로 오독시킨다").toContain("무자료");
    expect(note, "원인을 단정했다").not.toContain("조회 불가");
  });

  it("★★두 모집단 — 정상 조회에서 0건이면 **사유를 붙이지 않는다**(종전 문구 유지)", async () => {
    // ★한쪽만 재면 «항상 사유를 붙인다» 도 통과한다. 그러면 진짜 무자료가 장애로 오독된다.
    경매응답({ items: [], total: 0, data_source: "onbid_live" });
    await 그리기("auction");

    expect(
      getMock.mock.calls.some((c) => String(c[0]).startsWith("/auction/search")),
      "경매 조회가 안 나갔다 — 공허 진리 가드",
    ).toBe(true);
    expect(
      마지막노트("auctionNote"),
      "정상 조회인데 사유 문구가 붙었다 — 진짜 「무자료」가 장애로 오독된다",
    ).toBe("");
  });

  it("★★세 번째 상태 — **조회했는지조차 모르면** 「무자료」로 떨어뜨리지 않는다", async () => {
    // ★★2026-09-12 독립 리뷰(REVISE): 초판은 미상 `data_source` 에 **빈 문자열**을 냈고
    //   그러면 화면이 **「경매 무자료」**, 즉 *"주변에 없다"* 라고 말한다. 나는 그것을
    //   «날조 금지» 로 정당화했는데 **틀렸다** — 「무자료」는 중립 문구가 아니라 **적극적
    //   주장**이고, 출처를 모르면 그 주장을 뒷받침할 측정이 없다.
    //   ***날조를 피한 것이 아니라 다른 날조를 한 것이다.***
    경매응답({ items: [], total: 0, data_source: "__백엔드가_새로_만든_값__" });
    await 그리기("auction");

    const note = 마지막노트("auctionNote");
    expect(note, "미상 출처인데 노트가 비었다 — 화면이 「무자료」로 부재를 단정한다").not.toBe("");
    expect(note, "사유를 **지어냈다** — 모르는 것은 모른다고만 말해야 한다").not.toContain("조회 불가(");
    expect(note, "「확인 불가」 상태로 가지 않았다").toContain("확인 불가");
  });

  it("★★네 상태가 **서로 다른 화면**을 낸다(둘로도 셋으로도 부족했다)", async () => {
    const 본다 = async (body: unknown) => {
      captured.length = 0;
      centerSent = false;
      경매응답(body);
      const view = await 그리기("auction");
      const v = 마지막노트("auctionNote");
      // ★★언마운트한다. 안 하면 **셸이 여러 개 동시에 마운트된 채** 같은 `captured` 에 push 하고
      //   `at(-1)` 이 **다른 인스턴스의 렌더**를 볼 수 있다 — 실제로 부하 걸린 병렬에서
      //   **12회 중 2회 실패**하는 flaky 를 만들었다(독립 렌즈 M-7).
      view.unmount();
      return v;
    };
    const 무자료 = await 본다({ items: [], total: 0, data_source: "onbid_live" });
    const 서버사유 = await 본다({ items: [], total: 0, data_source: "unavailable", reason: "온비드 호출 실패: timeout" });
    const 사유없는불가 = await 본다({ items: [], total: 0, data_source: "unavailable" });
    const 미상 = await 본다({ items: [], total: 0, data_source: "__미상__" });

    // ★공허 진리 가드 — 겹치면 아래 대조가 무의미하다.
    expect(
      new Set([무자료, 서버사유, 사유없는불가, 미상]).size,
      `상태가 같은 화면으로 접혔다: ${JSON.stringify([무자료, 서버사유, 사유없는불가, 미상])}`,
    ).toBe(3); // ★사유없는불가 와 미상 은 **같아야 옳다**(둘 다 「확인 불가」) — 아래에서 그것을 단언한다
    expect(무자료, "확인된 출처의 0건은 빈 노트여야 한다(화면 「무자료」)").toBe("");
    expect(서버사유, "서버 사유가 그대로 안 왔다").toContain("호출 실패");
    expect(사유없는불가, "사유 없는 unavailable 에 원인을 단정했다").toContain("확인 불가");
    expect(미상, "모름이 「없음」으로 접혔다").toContain("확인 불가");
    expect(사유없는불가, "사유 없는 불가와 미상은 같은 「모름」이다").toBe(미상);
  });

  it("★형제 대칭 — 분양도 `available:false` 면 사유가 도달한다", async () => {
    분양응답({ available: false, items: [] });
    await 그리기("presale");

    expect(
      postMock.mock.calls.some((c) => String(c[0]).startsWith("/presale/nearby")),
      "분양 조회가 안 나갔다 — 공허 진리 가드",
    ).toBe(true);
    const 분양노트 = 마지막노트("presaleNote");
    expect(
      분양노트,
      "분양은 `available` 을 **타입에 선언해 놓고 읽지 않았다** — 경매와 같은 결함 클래스다",
    ).toContain("조회 불가");
    // ★★`label` 인자가 실제로 쓰이는지 — 안 쓰면 두 형제의 노트가 **구별되지 않는다**
    //   (실측: `label` 을 버리는 변이가 **SURVIVED** 했다 · 독립 리뷰 지적 ⑤).
    //   ★한 화면에 경매·분양 노트가 함께 뜨므로, 이름이 없으면 어느 레이어가 막혔는지 모른다.
    expect(분양노트, "노트에 레이어 이름이 없다 — 어느 레이어가 막혔는지 알 수 없다").toContain("분양");
    expect(분양노트, "분양 노트에 경매 이름이 붙었다").not.toContain("경매");
  });

  it("★형제 대칭 두 모집단 — 분양이 결과를 주면 사유를 붙이지 않는다", async () => {
    분양응답({ available: true, items: [{ name: "행복마을", lat: 37.5, lon: 127.0 }] });
    await 그리기("presale");
    expect(마지막노트("presaleNote"), "정상 결과인데 사유가 붙었다").toBe("");
  });
});
