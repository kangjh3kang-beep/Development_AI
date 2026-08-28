/**
 * API 키 관리 — **「값이 있다」를 「정상」으로 그리지 않는다**(2026-08-28).
 *
 * 【이 락이 잡으려는 결함】
 * `list_status` 의 `is_set` 은 `bool(cur) or in_db`(secret_store.py) — **값의 존재**일 뿐인데
 * 화면이 그것을 `--status-success`(초록 점 포함) 배지로 그려 관리자가 **「정상 연결됨」으로
 * 읽었다**. 이 화면에서 실제로 연결을 확인하는 키는 **4개뿐**이고(테스트 버튼이 그 넷에만
 * 렌더된다) 나머지에 대해 관리자가 보는 초록은 **바로 이 배지**였다.
 *
 * 【★왜 소스 grep 이 아니라 렌더인가】
 * 같은 주제의 앞선 시도에서 소스 문자열 락을 썼다가, 독립 리뷰가 만든 변이
 * (상태에 항상 `false` 를 싣기 · 메시지를 아예 안 그리기)가 **전부 통과**했다 —
 * 문자열이 파일에 있는지만 봤기 때문이다. 여기서는 **실제로 렌더해 클래스를 읽는다.**
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const delMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    delete: (...a: unknown[]) => delMock(...a),
  },
  ApiClientError: class extends Error {},
}));

import { ApiKeyManagementPanel } from "../ApiKeyManagementPanel";

/** 두 모집단 — 값이 있는 키 / 없는 키. */
const ITEMS = [
  {
    name: "VWORLD_API_KEY", label: "V-World 인증키", group: "공공데이터·지도",
    secret: true, kind: "text", options: null, desc: null, guide_url: null,
    custom: false, is_set: true, source: "db", masked: "abc••••xyz",
  },
  {
    name: "IROS_PIN", label: "IROS PIN", group: "등기(부동산등기부)",
    secret: true, kind: "text", options: null, desc: null, guide_url: null,
    custom: false, is_set: false, source: null, masked: null,
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

/** 그 키 카드 **안의** 「설정됨」 배지를 집는다(헤더 집계 문구와 섞이지 않게). */
function badgeOf(name: string): HTMLElement | null {
  const nameEl = screen.getByText(name);
  const card = nameEl.closest("div.rounded-2xl, div[class*=\"rounded\"]") || nameEl.parentElement;
  const spans = Array.from(card?.querySelectorAll("span") || []);
  return (spans.find((s) => /^설정됨/.test(s.textContent || "")) as HTMLElement) || null;
}

async function renderPanel() {
  // ★`groups` 가 없으면 카드가 **한 장도 렌더되지 않는다**(패널이 groups 를 순회한다).
  //   첫 판이 그래서 헤더의 "1/2 설정됨" 을 배지로 착각할 뻔했다 — 공허한 초록의 문턱.
  getMock.mockResolvedValue({ items: ITEMS, groups: ["공공데이터·지도", "등기(부동산등기부)"] });
  render(<ApiKeyManagementPanel />);
  // ★공허 진리 방지 — **카드 배지**가 그려진 뒤에 단언한다(헤더의 "N/M 설정됨" 이 아니라).
  await waitFor(() => expect(screen.getByText("미설정")).toBeTruthy());
  expect(badgeOf("VWORLD_API_KEY"), "존재 배지를 못 찾았다 — 카드가 안 그려졌다").toBeTruthy();
}

describe("★존재 배지 — 초록(성공)으로 그리지 않는다", () => {
  it("값이 있는 키의 배지가 **status-success 를 쓰지 않는다**", async () => {
    await renderPanel();
    const badge = badgeOf("VWORLD_API_KEY");
    expect(badge, "「설정됨」 배지를 못 찾았다 — 이 테스트가 공허해진다").toBeTruthy();
    // ★**배지 전체(자식 포함)** 를 본다. 바깥 span 의 class 만 보면 **안쪽 점만 초록**으로
    //   바꾸는 변이가 통과한다(실측: SURVIVED). 관리자가 「정상」으로 읽는 것은 바로 그 점이다.
    const html = badge!.outerHTML;
    expect(html, `존재를 성공색으로 그린다(자식 포함): ${html}`).not.toContain("status-success");
  });

  it("★중립 토큰을 쓴다(색만 지우고 끝내지 않았다)", async () => {
    await renderPanel();
    const cls = badgeOf("VWORLD_API_KEY")!.getAttribute("class") || "";
    expect(cls, `중립 토큰이 없다: ${cls}`).toContain("text-secondary");
  });

  it("★대조 모집단 — 미설정 키는 **여전히 구별되게** 그린다(전부 회색으로 뭉개지 않았다)", async () => {
    await renderPanel();
    const unset = screen.getByText("미설정");
    const cls = unset.getAttribute("class") || "";
    expect(cls, `미설정이 존재 배지와 구별되지 않는다: ${cls}`).toContain("status-error");
  });

  it("★화면이 「설정됨」의 뜻을 스스로 말한다(색만 내리면 다음 사람이 되돌린다)", async () => {
    await renderPanel();
    expect(
      screen.getByText(/값이 저장돼 있다는 뜻이며, 연결·인증을 확인한 것이 아닙니다/),
      "설정됨의 의미를 밝히는 문장이 화면에 없다",
    ).toBeTruthy();
  });
});
