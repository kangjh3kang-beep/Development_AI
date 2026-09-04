/**
 * 본문 ↔ 지도 오버레이 층위 계약 (2026-08-06 — 사용자 실측 지적의 회귀망).
 *
 * ★무엇이 결함이었나: 지도 래퍼가 스태킹 컨텍스트를 만들지 않아 지도 오버레이(z 380~500)가
 *   **루트에서** 본문과 경쟁했고, sticky ContextHeader(당시 z-30)가 스크롤 중 지도 영역에
 *   들어오면 레이어 레일·팝오버에 **가려졌다**. 사용자가 스크린샷으로 지목한 그 장면이다.
 *
 * ★이 파일이 잠그는 것: 숫자가 아니라 **관계**다 —
 *     max(지도 오버레이 z) < ContextHeader z < 앱 헤더 z
 *   오버레이 값을 렌더 결과에서 **전수로 뽑아** 최댓값과 비교하므로, 새 오버레이가 더 높은 z로
 *   추가되면 이 테스트가 **자동으로 발화**한다(목록형이 아니라 전수형).
 *
 * ★한계(정직): jsdom 은 레이아웃·페인트를 하지 않으므로 이 테스트는 **z 서열만** 증명한다.
 *   "실제로 가려지는가"는 라이브 뷰포트 확인 대상이다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { SATONG_CONTENT_Z, SATONG_UI_Z } from "@/lib/satong-map-z";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const Stub = (props: { topRightSlot?: React.ReactNode }) => (
      <div data-testid="dynamic-map-stub">{props.topRightSlot}</div>
    );
    return Stub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: { ...actual.apiClient, request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending) },
  };
});

/**
 * 렌더된 요소들의 z 를 **전수** 뽑는다 — class 의 `z-[N]`(변형자 접두 허용) **와 인라인 style**.
 *
 * ★2026-08-17 — 인라인 style 을 추가했다. 종전에는 class 리터럴만 봐서, **SSOT 가 규정한
 *   사용법을 따르는 오버레이에 오히려 눈이 멀었다.** `satong-map-z.ts` 는
 *   *"Tailwind v4 는 `z-[${동적값}]` 을 생성하지 못하므로 상수를 인라인 스타일로 흘려보낸다"*
 *   고 규정한다 — 즉 **계약을 지킬수록 이 수집기에서 사라졌다.**
 *   실제로 레일·배지행을 `SATONG_UI_Z` 상수로 결속하자 수집이 **0건**이 되어 아래 공허 진리
 *   가드가 발동했다. 그 가드가 없었으면 "위반 0"으로 **조용히 통과**했을 것이다.
 */
function renderedZValues(root: ParentNode): number[] {
  const out: number[] = [];
  root.querySelectorAll<HTMLElement>("[class], [style]").forEach((el) => {
    for (const m of (el.className ?? "").toString().matchAll(/(?:^|\s)(?:[a-z0-9-]+:)*z-\[(\d+)\]/g)) {
      out.push(Number(m[1]));
    }
    const raw = el.style?.zIndex ?? "";
    const inline = Number(raw);
    if (raw !== "" && Number.isFinite(inline)) out.push(inline);
  });
  return out;
}

describe("본문 ↔ 지도 오버레이 층위 계약", () => {
  it("★sticky ContextHeader 는 지도 오버레이 **전부**보다 위에 온다(전수 비교)", () => {
    render(<SatongMapShell locale="ko" showContextHeader />);

    const mapStub = screen.getByTestId("dynamic-map-stub");
    const overlayZ = renderedZValues(mapStub);
    // 공허 진리 방지 — 오버레이가 하나도 렌더되지 않았으면 "최댓값보다 크다"가 무의미하다.
    expect(overlayZ.length, "지도 오버레이가 렌더되지 않아 비교 대상이 없다").toBeGreaterThan(0);

    const header = document.querySelector<HTMLElement>('[class*="sticky"][class*="z-["]');
    expect(header, "sticky ContextHeader 를 찾지 못했다").not.toBeNull();
    const headerZ = Number((header!.className.match(/(?:^|\s)z-\[(\d+)\]/) ?? [])[1]);
    expect(Number.isFinite(headerZ), `ContextHeader 에서 z-[N] 을 읽지 못했다: ${header!.className}`).toBe(true);

    const maxOverlay = Math.max(...overlayZ);
    expect(
      headerZ,
      `ContextHeader(z ${headerZ}) 가 지도 오버레이 최댓값(z ${maxOverlay}) 아래다 — 스크롤 시 가려진다`,
    ).toBeGreaterThan(maxOverlay);
  });

  it("★계약 상수가 실제 서열과 일치한다 — 오버레이 최댓값 < 본문 < 앱 헤더(1000)", () => {
    const maxUiZ = Math.max(...Object.values(SATONG_UI_Z));
    expect(SATONG_CONTENT_Z.stickyContextHeader).toBeGreaterThan(maxUiZ);
    // 앱 셸 크롬(DashboardChromeGate 헤더 z-[1000])보다는 아래여야 전역 내비가 항상 위에 온다.
    expect(SATONG_CONTENT_Z.stickyContextHeader).toBeLessThan(1000);
  });

  it("★소스와 계약값이 갈리지 않는다 — 렌더된 헤더 z 가 상수와 같다", () => {
    render(<SatongMapShell locale="ko" showContextHeader />);
    const header = document.querySelector<HTMLElement>('[class*="sticky"][class*="z-["]');
    const headerZ = Number((header!.className.match(/(?:^|\s)z-\[(\d+)\]/) ?? [])[1]);
    expect(headerZ).toBe(SATONG_CONTENT_Z.stickyContextHeader);
  });
});
