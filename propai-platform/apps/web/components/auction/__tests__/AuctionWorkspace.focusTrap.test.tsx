/**
 * 경공매 상세 모달 — **렌더 경로 + 포커스 트랩(중첩 포함)**.
 *
 * ## 왜 이 파일이 필요한가
 *
 * `AuctionWorkspace` 는 `aria-modal` 표면을 **2개** 가지면서 포커스 배선이 **0** 이었고,
 * `FOCUS_UNWIRED` 에 이런 사유로 남아 있었다:
 *
 *     "1,839줄 워크스페이스 안의 비-export 상세모달·라이트박스. 단독 렌더에
 *      목록 조회·지도 목이 필요해, 렌더 경로부터 만든 뒤 배선한다"
 *
 * ★**그 사유는 거짓이었다.** `DetailModal` 이 받는 것은 `item`·`locale`·`onClose` 뿐이다.
 *   워크스페이스도, **목록 조회도, 지도도 필요 없다** — 막고 있던 것은 **`export` 하나**였다.
 *
 * ★단, 실측으로 **한 가지는 정정한다**: 라이트박스에 닿으려면 사진이 있어야 하고 사진은
 *   `item` 이 아니라 **`/auction/detail` 응답**에서 온다(`galleryImages` 는 `detail` 을 읽는다).
 *   즉 필요한 목은 *"목록·지도"* 가 아니라 **상세 응답 하나**다. 사유가 완전히 헛되지는
 *   않았지만 **가리킨 대상이 틀렸고**, 그래서 필요보다 훨씬 커 보였다.
 *   부채의 *사유*는 부채의 *사실*보다 빨리 낡는다 — 물려받지 말고 재라.
 *
 * ## 이 표면의 성질 (실측)
 *
 * · 상세 모달은 **마운트 자체가 열림**이다(부모가 `selected` 일 때만 렌더).
 * · 라이트박스는 상세 모달 **안에** 렌더된다 — 두 트랩이 **겹친다**.
 *   그래서 "배선 2개"가 아니라 **여는 경로 2개**를 태워야 잠긴다.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// 이 모달은 권리분석 이동에 라우터를 쓴다 — 옆 파일 관례대로 가볍게 세운다.
vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/auction",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

/** 사진 2장을 주는 최소 상세 응답 — 이게 있어야 라이트박스(둘째 표면)에 닿는다. */
const DETAIL = {
  item: { image_urls: ["https://example.test/a.jpg", "https://example.test/b.jpg"] },
  data_source: "onbid",
};

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(() => Promise.resolve(DETAIL)),
    getRuntimeConfig: () => ({ mode: "live" }),
  },
  ApiClientError: class extends Error {},
  resolveApiOrigin: () => "http://localhost",
}));

import { DetailModal } from "@/components/auction/AuctionWorkspace";

/** 상세조회 키를 갖춘 최소 item — `canFetchDetail=true` 가 되어 위 목이 먹는다. */
const ITEM = {
  cltr_nm: "테스트 물건",
  cltr_mng_no: "C-1",
  pbct_cdtn_no: "P-1",
} as never;

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <DetailModal item={ITEM} locale="ko" onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

/** 훅이 **실제로 가둔 컨테이너**들(`useModalFocus` 가 다는 표식). */
function trapEls(): HTMLElement[] {
  return Array.from(document.body.querySelectorAll<HTMLElement>("[data-modal-focus]"));
}

function focusablesIn(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true");
}

describe("경공매 상세 모달 — 렌더 경로", () => {
  it("★전제: 목록·지도 없이 **단독으로 렌더된다**(이 파일의 존재 이유)", () => {
    renderModal();
    expect(
      screen.getByText("물건 상세"),
      "상세 모달이 단독 렌더되지 않았다 — 사유가 참이었다는 뜻이다",
    ).toBeTruthy();
    expect(document.body.querySelectorAll('[aria-modal="true"]').length).toBe(1);
  });

  it("★두 번째 표면(라이트박스)에 닿는 경로가 있다", async () => {
    renderModal();
    // ★전제 — 열기 전엔 하나뿐이어야 한다(공허한 초록 방지).
    expect(document.body.querySelectorAll('[aria-modal="true"]').length).toBe(1);

    fireEvent.click(await screen.findByRole("button", { name: "사진 확대해서 보기" }));
    await waitFor(() =>
      expect(
        document.body.querySelectorAll('[aria-modal="true"]').length,
        "사진을 눌렀는데 라이트박스가 열리지 않았다 — 여는 경로가 사라졌다",
      ).toBe(2),
    );
  });
});

describe("경공매 상세 모달 — 포커스 생명주기", () => {
  it("열리면 **본체**를 가둔다 — 백드롭이 아니다", () => {
    renderModal();
    const traps = trapEls();
    expect(traps.length, "훅이 아무것도 가두지 않았다 — 배선이 죽었다").toBe(1);
    // ★백드롭에 달았는지 결과로는 구분되지 않는다(#750 이 뚫린 지점) → 표식으로 본다.
    expect(
      traps[0].getAttribute("role"),
      "가둔 대상이 role=dialog(백드롭) 자체다 — 본체가 아니라 배경까지 범위에 든다",
    ).not.toBe("dialog");
    expect(traps[0].contains(screen.getByText("물건 상세"))).toBe(true);
  });

  it("열리면 첫 포커스 가능 요소로 옮긴다", () => {
    renderModal();
    const body = trapEls()[0];
    expect(focusablesIn(body).length, "포커스 가능 요소가 없다 — 공허한 초록").toBeGreaterThan(0);
    expect(body.contains(document.activeElement)).toBe(true);
  });

  it("Tab 이 본체 밖으로 나가지 않는다", () => {
    renderModal();
    const body = trapEls()[0];
    const items = focusablesIn(body);
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      body.contains(document.activeElement),
      "마지막 요소에서 Tab 이 배경으로 빠져나갔다",
    ).toBe(true);
    expect(document.activeElement).toBe(items[0]);
  });

  it("닫히면 **열기 전 요소**로 포커스를 돌려준다", () => {
    const opener = document.createElement("button");
    opener.textContent = "행";
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = renderModal();
    expect(document.activeElement, "모달이 포커스를 가져가지 않았다").not.toBe(opener);
    unmount();
    expect(document.activeElement, "닫았는데 여는 버튼으로 안 돌아왔다").toBe(opener);
    opener.remove();
  });
});

describe("경공매 상세 모달 — ★중첩 트랩(라이트박스가 모달 안에서 열린다)", () => {
  async function openLightbox() {
    renderModal();
    fireEvent.click(await screen.findByRole("button", { name: "사진 확대해서 보기" }));
    await waitFor(() => expect(trapEls().length).toBe(2));
    // 바깥 본체가 안쪽 라이트박스를 **포함**한다는 사실 자체를 먼저 확인한다 —
    // 이게 참이라서 중첩이 위험한 것이고, 거짓이면 이 스펙의 전제가 무너진다.
    const [outer, inner] = trapEls();
    expect(outer.contains(inner), "라이트박스가 모달 밖에 렌더된다 — 전제가 바뀌었다").toBe(true);
    return { outer, inner };
  }

  it("열리면 **안쪽**으로 포커스가 간다", async () => {
    const { inner } = await openLightbox();
    expect(inner.contains(document.activeElement), "라이트박스가 포커스를 못 받았다").toBe(true);
  });

  it("★Tab 이 안쪽에 갇힌다 — 바깥 트랩이 가로채지 않는다", async () => {
    const { inner } = await openLightbox();
    const items = focusablesIn(inner);
    expect(items.length, "라이트박스에 포커스 가능 요소가 없다 — 공허한 초록").toBeGreaterThan(1);

    // 안쪽 **마지막**에서 Tab — 여기가 바깥 트랩이 끼어들 수 있는 자리다.
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      inner.contains(document.activeElement),
      "라이트박스 마지막에서 Tab 이 바깥 모달로 새 나갔다 — 중첩 양보가 죽었다",
    ).toBe(true);
    expect(document.activeElement).toBe(items[0]);
  });

  it("★대조군 — 안쪽이 닫히면 바깥이 다시 가둔다(양보가 영구화되지 않는다)", async () => {
    const { outer, inner } = await openLightbox();
    // ★"닫기" 버튼이 **둘**이다(모달·라이트박스) — 범위를 안쪽으로 좁히지 않으면
    //   바깥 모달을 닫아 놓고 "라이트박스를 닫았다"고 착각한다.
    fireEvent.click(within(inner).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(trapEls().length).toBe(1));
    expect(document.body.contains(inner)).toBe(false);

    const items = focusablesIn(outer);
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "라이트박스를 닫았는데 바깥 트랩이 돌아오지 않았다",
    ).toBe(items[0]);
  });
});
