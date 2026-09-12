/**
 * ★비번이 **설정된** 현장에 자동 시도를 날리면 잠금 카운터를 향해 노크하는 셈이다
 * (2026-09-09 · 리뷰 C1).
 *
 * 【배경】「승인이 곧 인증」으로 모달이 열리자마자 **비번 없이 조용히 먼저 시도**한다.
 * 라이브 14현장 중 11현장이 비번 미설정이라 대부분은 입력이 아예 불필요해진다.
 * 그런데 나머지 3현장에서는 그 시도가 서버까지 간다.
 *
 * 【두 겹의 처방 — 이 락은 바깥 겹을 본다】
 *   · 서버: `resolve_entry` 가 `no_secret_supplied` 를 **실패 카운터 앞에서** 400 으로 막는다
 *     (`apps/api/tests/test_site_enter_membership_auth.py::test_router_maps_each_outcome_to_its_own_status`).
 *   · 프론트(여기): 설정된 것으로 **아는** 현장에는 **애초에 두드리지 않는다**.
 *
 * 【축】«prop 이 선언돼 있는가» 가 아니라 **«POST 가 나갔는가»** 를 센다.
 * 그리고 **두 모집단**을 같은 파일에서 본다 — 모르면(`undefined`) 시도해야 하고,
 * 안다면(`true`) 시도하지 않아야 한다. 한쪽만 보면 «아무것도 안 하는 구현» 도 통과한다.
 */
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: (...a: unknown[]) => post(...a) },
  ApiClientError: class extends Error { status = 0; payload: unknown = null; },
}));
// ★★목이 **안정**해야 한다(2026-09-12 · 리뷰 M5). 종전 `useRouter: () => ({ push: vi.fn() })`
//   는 매 렌더 **새 객체**를 돌려줘, `enter` 의 `useCallback` 의존이 항상 바뀌는 상태를 만든다.
//   그러면 이 파일의 테스트는 «부모 재렌더로 의존이 바뀌는가» 를 **원리적으로 구별하지 못한다**
//   (리뷰어가 자기 프로브에서 같은 함정을 먼저 밟고 정정했다 — 도구 출력도 증거가 아니다).
const STABLE_ROUTER = { push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => STABLE_ROUTER }));
vi.mock("@/lib/salesApi", () => ({ storeSiteToken: vi.fn() }));

import SiteEnterModal from "@/components/sales-app/SiteEnterModal";

const base = { locale: "ko" as const, siteName: "테스트현장", onClose: vi.fn() };

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({
    site_token: "t", token_type: "bearer", expires_in: 3600,
    site_id: "s", role: "MEMBER", features: [],
  });
});

describe("진입 모달 — 자동 시도의 게이팅", () => {
  it("대조군: `password_set` 을 **모르면** 열리자마자 시도한다(그래야 11현장이 열린다)", async () => {
    render(<SiteEnterModal {...base} siteId="s-unknown" open onEntered={vi.fn()} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    // 비번 없이 — 빈 본문으로 나간다.
    expect(post.mock.calls[0][1]).toEqual({ body: {} });
  });

  it("★비번이 **없는 것으로 알려진** 현장도 시도한다(`false`)", async () => {
    render(<SiteEnterModal {...base} siteId="s-nopw" passwordSet={false} open onEntered={vi.fn()} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });

  it("★★비번이 **설정된 것으로 알려진** 현장에는 **노크하지 않는다**(`true`)", async () => {
    render(<SiteEnterModal {...base} siteId="s-haspw" passwordSet open onEntered={vi.fn()} />);
    // 자동 시도가 있었다면 이 사이에 나간다(위 두 모집단은 같은 대기로 1건을 봤다).
    await new Promise((r) => setTimeout(r, 60));
    expect(post).not.toHaveBeenCalled();
  });

  it("★닫힌 모달은 어느 경우에도 시도하지 않는다", async () => {
    render(<SiteEnterModal {...base} siteId="s-closed" open={false} onClose={vi.fn()} onEntered={vi.fn()} />);
    await new Promise((r) => setTimeout(r, 60));
    expect(post).not.toHaveBeenCalled();
  });
});

describe("부모 재렌더 — 입력한 비번이 살아남는가(리뷰 M5 · 이 PR 이 만든 회귀)", () => {
  /**
   * ★두 호출부(`SiteListClient` · `SiteWorkspaceClient`)가 `onEntered` 를 **인라인 화살표**로
   * 넘긴다. 그래서 부모가 재렌더되면 prop 참조가 바뀌고, 종전처럼 초기화 effect 의존에
   * `enter` 가 들어 있으면 **`setPassword("")` 가 다시 돌아 입력이 지워진다.**
   *
   * 도달 경로: `SiteWorkspaceClient` 의 `online`/`offline` 리스너 → `setOffline(...)` →
   * 부모 재렌더. 비번을 아는 사용자가 네트워크가 흔들리는 현장에서 입력 중 겪는다.
   *
   * ★축은 «effect 의존이 무엇인가» 가 아니라 **«입력값이 남는가»** 다.
   */
  function Parent({ tick }: { tick: number }) {
    return (
      <SiteEnterModal
        {...base}
        siteId="s-reRender"
        passwordSet
        open
        // ★인라인 화살표 — 실제 호출부와 같은 형태다(참조가 매번 바뀐다).
        onEntered={() => { void tick; }}
      />
    );
  }

  it("★★부모가 재렌더돼도 **입력한 비번이 남는다**", async () => {
    const { rerender } = render(<Parent tick={0} />);
    const input = document.querySelector('input[type="password"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "mySecret" } });
    expect(input.value).toBe("mySecret");

    rerender(<Parent tick={1} />);
    rerender(<Parent tick={2} />);

    const after = document.querySelector('input[type="password"]') as HTMLInputElement;
    expect(after.value).toBe("mySecret");
  });

  it("★대조군 — 현장을 **바꾸면** 초기화된다(초기화가 죽지 않았다)", () => {
    const { rerender } = render(<SiteEnterModal {...base} siteId="s-a" passwordSet open onEntered={vi.fn()} />);
    const input = document.querySelector('input[type="password"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "typed" } });
    expect(input.value).toBe("typed");

    rerender(<SiteEnterModal {...base} siteId="s-b" passwordSet open onEntered={vi.fn()} />);
    const after = document.querySelector('input[type="password"]') as HTMLInputElement;
    expect(after.value).toBe("");
  });

  it("★자동 시도는 부모 재렌더로 **반복되지 않는다**(멱등 ref)", async () => {
    const { rerender } = render(<SiteEnterModal {...base} siteId="s-once" open onEntered={vi.fn()} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    rerender(<SiteEnterModal {...base} siteId="s-once" open onEntered={vi.fn()} />);
    rerender(<SiteEnterModal {...base} siteId="s-once" open onEntered={vi.fn()} />);
    await new Promise((r) => setTimeout(r, 60));
    expect(post).toHaveBeenCalledTimes(1);
  });
});
