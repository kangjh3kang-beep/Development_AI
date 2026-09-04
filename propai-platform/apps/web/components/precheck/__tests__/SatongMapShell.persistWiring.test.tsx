/**
 * 컴포넌트 → 저장 **배선**(2026-09-04 · #965 적대 리뷰 Finding 5).
 *
 * ★리뷰 실측: 셸의 `setLayerControls` 를 **no-op 으로 바꿔도** 이 PR 이 더한 락 37건이
 *   전부 통과했다. 즉 «토글이 스토어에 닿는가» 를 아무것도 안 봤다. 형제 테스트가
 *   구해 주긴 했지만 그건 **메모리 토글**만 증명하고 **저장**은 건드리지 않는다.
 *   → 화면에서 클릭 → 프로덕션 플러시 경로(`pagehide`) → **계정별 키의 내용**까지 태운다.
 */
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// ★R1(M): 스텁이 슬롯을 '안 그리는' 것만으로는 도크 잔재를 감시할 수 없다(누가
//   bottomDockSlot을 되돌려도 스텁이 삼켜 테스트가 통과한다). props를 캡처해 전달
//   계약 자체를 단언한다.
const capturedMapProps: Record<string, unknown>[] = [];
vi.mock("next/dynamic", () => ({
  default: () => {
    // ★H2 봉합 이후 필수: 레일·팝오버·배지행은 topRightSlot으로 지도 래퍼 '안'에 렌더된다
    //   (풀스크린에서 살아남게 하는 봉합). 스텁도 실컴포넌트와 동일하게 슬롯을 렌더한다.
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub">{props.topRightSlot as ReactNode}</div>;
    };
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending),
      putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});


// ★R1 MEDIUM-A: jsdom의 fireEvent.click은 선행 mouseenter를 합성하지 않는다. 실브라우저는
//   반드시 mouseenter→click 순서라, click만 쏘는 테스트는 '현실에 없는 순서'를 고정한다
//   (그래서 첫 클릭이 팝오버를 닫는 HIGH-A가 초록으로 통과했다). 레일 상호작용은 전부 이 헬퍼로.



import { accountScopedKey } from "@/lib/account-scope";
import {
  SATONG_MAP_PREFS_STORE_KEY,
  defaultEnabledLayerIds,
  defaultSatongMapControls,
  useSatongMapPrefs,
} from "@/store/useSatongMapPrefsStore";

const KEY = accountScopedKey(SATONG_MAP_PREFS_STORE_KEY);

function openLayerPopover(): void {
  fireEvent.click(screen.getByRole("button", { name: /레이어/ }));
}

describe("컴포넌트 → 저장 배선", () => {
  beforeEach(() => {
    // ★순서가 중요하다 — `setState` 자체가 persist 쓰기를 예약하므로 **뒤에** 지운다.
    //   (처음에 반대로 썼다가 음성 대조군이 «렌더만 해도 저장됐다» 로 깨졌다.)
    useSatongMapPrefs.setState({
      controlsByLayer: defaultSatongMapControls(),
      enabledLayerIds: defaultEnabledLayerIds(),
      enabledLayersCustomized: false,
    });
    window.dispatchEvent(new Event("pagehide"));
    window.localStorage.clear();
  });

  it("★★화면에서 「선택 필지」를 끄면 **계정별 키에 그 상태가 저장된다**", () => {
    render(<SatongMapShell locale="ko" />);
    openLayerPopover();
    fireEvent.click(screen.getByRole("button", { name: "지적도" }));

    const btn = screen.getByRole("button", { name: /선택 필지/ });
    // ★대조군은 **스토어**로 본다 — 이 버튼은 `aria-pressed` 를 쓰지 않고 활성 표시가
    //   CSS 클래스뿐이다(실측). 시각 표기에 결속하면 스타일 변경에 깨진다.
    expect(useSatongMapPrefs.getState().controlsByLayer.cadastre).toContain("selected");

    fireEvent.click(btn);
    // ①배선: 클릭이 스토어에 닿았다(리뷰가 no-op 으로 바꿔도 통과하던 자리)
    expect(useSatongMapPrefs.getState().controlsByLayer.cadastre).not.toContain("selected");

    // 프로덕션 플러시 경로를 태운다(500ms 디바운스를 흉내 내지 않는다).
    window.dispatchEvent(new Event("pagehide"));
    const raw = window.localStorage.getItem(KEY);
    expect(raw, "화면 클릭이 저장까지 닿지 않았다").toBeTruthy();
    expect(JSON.parse(raw!).state.controlsByLayer.cadastre).not.toContain("selected");
  });

  it("★★화면에서 **레이어를 켜면** 계정별 키에 그 상태가 저장된다(적대 리뷰 MAJOR-1)", () => {
    // ★리뷰 실측: 셸의 파생 Set·`mapLayerState`·memo deps 를 끊는 변이 3종이
    //   이 PR 의 락 **4파일 63건을 전부 통과**했다. 스토어는 완벽히 영속하는데 셸이
    //   그것을 무시해도 초록이었다 — «부른다» 를 잠그면 아무것도 안 잠긴다.
    //   → 형제 케이스(컨트롤)와 **같은 모양**으로 레이어 활성 축을 태운다.
    render(<SatongMapShell locale="ko" />);
    openLayerPopover();
    fireEvent.click(screen.getByRole("button", { name: "용도지역" }));

    // 꺼짐="지도에 표시" · 켜짐="지도 표시 중" — 둘 다 잡는다.
    const enableBtn = screen.getByRole("button", { name: /지도.*표시/ });
    // ★이 버튼은 `aria-pressed` 를 노출한다(컨트롤 버튼과 달리) — 화면 상태로 대조군을 잡는다.
    expect(enableBtn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(enableBtn);
    expect(enableBtn).toHaveAttribute("aria-pressed", "true");

    // ①배선: 클릭이 스토어에 닿았다
    expect(useSatongMapPrefs.getState().enabledLayerIds).toContain("zoning");
    // ②영속: 프로덕션 플러시 경로를 태운다
    window.dispatchEvent(new Event("pagehide"));
    const raw = window.localStorage.getItem(KEY);
    expect(raw, "화면 클릭이 저장까지 닿지 않았다").toBeTruthy();
    const st = JSON.parse(raw!).state;
    expect(st.enabledLayerIds).toContain("zoning");
    // ③«골랐다» 표시 — 이게 없으면 재수화가 저장분을 무시한다(MAJOR-3 봉합)
    expect(st.enabledLayersCustomized).toBe(true);

    // ★★④**그 값이 지도까지 내려간다**(리뷰 변이 B: `mapLayerState` 를 끊어도 통과했다).
    //   스토어·저장소만 보면 «스토어를 잠갔다» 일 뿐 «화면에 닿는다» 가 아니다.
    const lastMapProps = capturedMapProps.at(-1) as { layerState?: { enabledLayerIds?: string[] } };
    expect(lastMapProps?.layerState?.enabledLayerIds, "지도에 layerState 가 안 내려간다").toContain(
      "zoning",
    );
  });

  it("★음성 대조군 — 아무것도 안 누르면 저장하지 않는다", () => {
    render(<SatongMapShell locale="ko" />);
    window.dispatchEvent(new Event("pagehide"));
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });
});
