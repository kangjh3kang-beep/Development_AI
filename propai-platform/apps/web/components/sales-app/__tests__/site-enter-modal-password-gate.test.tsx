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
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: (...a: unknown[]) => post(...a) },
  ApiClientError: class extends Error { status = 0; payload: unknown = null; },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
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
