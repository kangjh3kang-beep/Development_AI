/**
 * 베이스맵 스위처 — terrain 컨트롤 상호배타 계약 + 우상단 레일 통합(2026-07-23).
 *   ① 레일 '베이스맵' 버튼으로 열기 전에는 스와치가 없다(도크 잔재 회귀 방지).
 *   ② 기본은 '일반' 활성. ③ '위성' 클릭 → 위성만 활성(상호배타). ④ '일반' 복귀 가능.
 *   ⑤ 레이어 팝오버와 상호배타(같은 좌표를 쓰므로 동시 표시 금지). ⑥ Esc 닫힘.
 */
import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

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
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub" />;
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

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
  });
}

function openBasemapPopover() {
  fireEvent.click(screen.getByRole("button", { name: "베이스맵 선택" }));
}

describe("SatongMapShell 베이스맵 스위처(레일 통합)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });
  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("★하단 도크로 스위처를 전달하지 않는다(도크 잔재 회귀 방지 — props 계약 단언)", () => {
    capturedMapProps.length = 0;
    render(<SatongMapShell locale="ko" />);
    expect(capturedMapProps.length).toBeGreaterThan(0);
    expect(capturedMapProps.at(-1)).not.toHaveProperty("bottomDockSlot");
  });

  it("★레일 버튼으로 열기 전에는 스와치가 없다", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("기본 '일반' 활성 → '위성' 클릭 시 상호배타 전환, '일반' 복귀 가능", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();

    const base = screen.getByRole("button", { name: "베이스맵: 일반" });
    const satellite = screen.getByRole("button", { name: "베이스맵: 위성" });

    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(satellite);
    expect(satellite).toHaveAttribute("aria-pressed", "true");
    expect(base).toHaveAttribute("aria-pressed", "false");
    // 상호배타 — 하이브리드/회색도 비활성 유지
    expect(screen.getByRole("button", { name: "베이스맵: 하이브리드" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(base);
    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");
  });

  it("★레이어 팝오버와 상호배타 — 같은 좌표(right-20 top-20)에 둘이 겹치지 않는다", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();

    // 레일의 레이어 버튼(지적도)을 누르면 베이스맵 팝오버는 닫힌다.
    fireEvent.click(screen.getByRole("button", { name: "지적도" }));
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();

    // 다시 베이스맵을 열면 정상 표시(토글 무결성).
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("★좌상단 활성레이어 칩 경로에서도 닫힌다(근원 봉합=handleLayerClick)", () => {
    render(<SatongMapShell locale="ko" />);
    // 레일에서 지적도를 켜면 좌상단에 활성 레이어 칩이 생긴다.
    fireEvent.click(screen.getByRole("button", { name: "지적도" }));
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();

    // ★조건부 단언 금지 — 칩을 못 찾으면 조용히 통과하는 약한 테스트가 된다(명시 실패).
    const railButton = screen.getByRole("button", { name: "지적도" });
    const chip = screen
      .getAllByRole("button", { name: /지적/ })
      .find((el) => el !== railButton);
    expect(chip, "좌상단 활성 레이어 칩을 찾지 못함").toBeTruthy();
    fireEvent.click(chip!);
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
  });

  it("Esc로 닫힌다(레이어 팝오버와 동일 닫힘 계약)", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
  });
});
