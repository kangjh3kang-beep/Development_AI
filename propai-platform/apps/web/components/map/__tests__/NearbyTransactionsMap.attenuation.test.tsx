/**
 * 감쇠 사슬이 **실제로 렌더된다** — 타입만 늘리고 화면은 안 바뀌는 것을 막는다.
 *
 * ★종전 라벨은 `radius_filtered_out_count` **한 갈래만** 말했다. 라이브 실측
 * (2026-08-25 · 역삼동 736 · 1000m)에서 그건 **306곳**이었고, 정작 가장 크게 깎인
 * **사전컷 1,761곳**은 화면 어디에도 없었다 — 원본 2,350 → 표시 209(91% 제외).
 *
 * ★이 파일의 첫 판(payload 를 prop 으로 넘김)은 **공허했다** — `payload` 는 컴포넌트
 *   **내부 상태**라 prop 이 무시됐고, 음성 케이스 2건이 "요소가 없다"는 이유로
 *   **트리비얼하게 통과**했다. 그래서 형제 테스트처럼 `apiClient.post` 를 스텁해
 *   실제 조회 경로를 태운다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@/lib/api-client", () => ({ apiClient: { post: postMock } }));
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: () => <div data-testid="satong-multi-map" />,
}));

const ATTENUATION = {
  source_group_count: 2350,
  shown_group_count: 209,
  dropped_total: 2141,
  dropped_pct: 91.1,
  reconciles: true,
  headline:
    "원본 2,350곳 중 209곳을 지도에 표시했습니다(91.1% 제외 — 지오코딩 사전컷 1,761 · 좌표 미확보 35 · 반경 밖 306 · 표시 상한 절단 39).",
  stages: [
    { key: "precut", label: "지오코딩 사전컷", dropped: 1761, reason: "예산 상한" },
    { key: "unlocated", label: "좌표 미확보", dropped: 35, reason: "지오코딩 실패" },
    { key: "radius", label: "반경 밖", dropped: 306, reason: "반경 1000m 밖" },
    { key: "display_cap", label: "표시 상한 절단", dropped: 39, reason: "표시 상한" },
  ],
};

function basePayload(atten: unknown) {
  return {
    center: { lat: 37.5, lon: 127.03, address: "서울특별시 강남구 역삼동 736" },
    radius_m: 1000, radius_applied: true, lawd_cd: "11680",
    months: ["202608", "202607", "202606"], categories: {},
    sample_attenuation: atten,
  };
}

async function renderWith(atten: unknown) {
  postMock.mockResolvedValue(basePayload(atten));
  const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
  return render(<NearbyTransactionsMap address="서울특별시 강남구 역삼동 736" />);
}

describe("감쇠 사슬 렌더", () => {
  beforeEach(() => postMock.mockReset());
  afterEach(() => vi.resetModules());

  it("원본 수와 **가장 큰 감쇠 갈래**를 화면에 낸다", async () => {
    await renderWith(ATTENUATION);
    const el = await screen.findByTestId("sample-attenuation-headline");
    expect(el.textContent).toContain("2,350");
    expect(el.textContent).toContain("209");
    expect(el.textContent).toContain("1,761");   // ★종전에 화면에 없던 그 숫자
  });

  it("사유가 title 로 붙는다 — 숫자만 있으면 무엇을 고칠지 모른다", async () => {
    await renderWith(ATTENUATION);
    const el = await screen.findByTestId("sample-attenuation-headline");
    expect(el.getAttribute("title")).toContain("지오코딩 사전컷");
    expect(el.getAttribute("title")).toContain("예산 상한");
  });

  it("계기가 어긋나면 **그 사실을 화면에 적는다**", async () => {
    await renderWith({ ...ATTENUATION, reconciles: false });
    const el = await screen.findByTestId("sample-attenuation-headline");
    expect(el.textContent).toContain("계기 불일치");
  });

  it("감쇠가 없으면 줄을 만들지 않는다(특이도)", async () => {
    await renderWith({ ...ATTENUATION, dropped_total: 0 });
    // ★공허 방지 — 컴포넌트가 실제로 조회를 마쳤는지 먼저 확인한다.
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByTestId("satong-multi-map");
    expect(screen.queryByTestId("sample-attenuation-headline")).toBeNull();
  });

  it("백엔드가 사슬을 안 주면 조용히 넘어간다(옵셔널 계약)", async () => {
    await renderWith(undefined);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByTestId("satong-multi-map");
    expect(screen.queryByTestId("sample-attenuation-headline")).toBeNull();
  });
});

describe("좌표 미확보 참고줄", () => {
  beforeEach(() => postMock.mockReset());
  afterEach(() => vi.resetModules());

  it("미확보를 **제외가 아니라 참고**로 그린다", async () => {
    await renderWith({
      ...ATTENUATION,
      unlocated_group_count: 56,
      unlocated_note:
        "이 중 56곳은 좌표를 확보하지 못해 **반경 판정을 하지 못했습니다**. 제외된 것이 아니라 거리로 거르지 못한 채 표시됩니다.",
    });
    const el = await screen.findByTestId("sample-attenuation-headline");
    expect(el.textContent).toContain("제외된 것이 아니라");
    expect(el.textContent).not.toContain("**");   // 마크다운 별표가 화면에 새지 않는다
  });

  it("참고줄이 없으면 만들지 않는다(특이도)", async () => {
    await renderWith(ATTENUATION);
    const el = await screen.findByTestId("sample-attenuation-headline");
    expect(el.textContent).not.toContain("제외된 것이 아니라");
  });
});
