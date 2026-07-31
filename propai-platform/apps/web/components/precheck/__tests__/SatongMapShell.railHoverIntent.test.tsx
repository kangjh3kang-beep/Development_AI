/**
 * SatongMapShell 레일 hover '전환' 의도 지연 — 사용자 지적 회귀 봉합(A안).
 *
 * ★무슨 버그였나: 레일이 2열(`railPinned` 펼침 = `grid-cols-2`)이고 팝오버는 레일 **바깥
 *   왼쪽**(`right-36`)에 뜬다. 그래서 **오른쪽 열 아이콘에서 팝오버로 가려면 왼쪽 열 위를
 *   반드시 지나야** 하는데, 지나가는 순간 그 아이콘의 mouseenter가 즉시 팝오버를 갈아치워
 *   정작 열려던 팝오버가 사라졌다. 1열이던 시절엔 없던 **2열 전환이 만든 회귀**다.
 *
 * 고정하는 계약:
 *   ① 스쳐 지나가는 hover(임계 미만 체류)는 **전환하지 않는다** — 원래 팝오버가 유지된다
 *   ② 머물면(임계 경과) 전환한다 — 의도적 전환은 막지 않는다
 *   ③ 팝오버에 도달하면 대기 중이던 전환이 **취소**된다(목적지 도달 = 사용자의 의도)
 *   ④ 첫 열기는 **지연 없이 즉시**(반응성 보존 — 지연은 '전환'에만)
 *   ⑤ 클릭은 즉시 확정하고 예약 전환이 뒤늦게 덮어쓰지 않는다
 */
import type { ReactNode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = ({ topRightSlot }: { topRightSlot?: ReactNode }) => (
      <div data-testid="dynamic-map-stub">{topRightSlot}</div>
    );
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
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

/** 레일 아이콘 — 접근성 이름(title)이 `${label} — 미리보기 열기 …` 형태다. */
function railIcon(label: string) {
  return screen.getByTitle(new RegExp(`^${label} — 미리보기 열기`));
}

/**
 * 지금 보이는 레일 팝오버의 이름.
 * 팝오버는 `role="dialog" aria-label={레이어 라벨}`을 이미 갖고 있어 시맨틱 선택자로 충분하다
 * (테스트 전용 testid를 새로 심지 않는다 — 접근성 계약을 그대로 검증하는 편이 낫다).
 */
function shownPanelName(): string | null {
  const dialogs = Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"][aria-label]'),
  );
  return dialogs.at(-1)?.getAttribute("aria-label") ?? null;
}

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null, projectName: "", projectStatus: "", siteAnalysis: null,
    });
  });
}

describe("SatongMapShell 레일 hover 전환 의도 지연(A안)", () => {
  beforeEach(() => {
    // ★`shouldAdvanceTime`은 쓰지 않는다 — 페이크 타이머가 실경과만큼 자동 전진하면
    //   느린 CI에서 mouseEnter~단언 사이 실경과가 임계(150ms)를 넘어 위양성 실패한다.
    vi.useFakeTimers();
    window.sessionStorage.clear();
    resetStores();
  });

  afterEach(() => {
    vi.useRealTimers();
    window.sessionStorage.clear();
    resetStores();
  });

  it("★④ 첫 열기는 지연 없이 즉시 뜬다(반응성 보존)", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("공시지가"));
    // 타이머를 전혀 진행시키지 않았는데도 이미 열려 있어야 한다.
    expect(shownPanelName()).toBe("공시지가");
  });

  it("★① 스쳐 지나가는 hover는 전환하지 않는다 — 원래 팝오버가 유지된다", () => {
    render(<SatongMapShell locale="ko" />);

    // 오른쪽 열 아이콘으로 팝오버를 연다.
    fireEvent.mouseEnter(railIcon("개발계획"));
    expect(shownPanelName()).toBe("개발계획");

    // 팝오버로 가는 길에 왼쪽 열 아이콘을 스친다(임계 미만 체류).
    const passing = railIcon("교통·편의 POI");
    fireEvent.mouseEnter(passing);
    act(() => { vi.advanceTimersByTime(80); });

    // ★핵심 단언: 임계 미만 체류에서는 아직 전환되지 않았다(가드를 지우면 여기서 이미 POI가 된다).
    expect(shownPanelName()).toBe("개발계획");

    // 스치고 벗어난 뒤에도 예약 전환이 뒤늦게 발화하지 않는다.
    //   ★단언은 **양성**으로 — `not.toBe(...)`는 그 시점 값이 null이면(닫힘 유예가 먼저 걸림)
    //   무조건 참이 되어 공허 통과한다(R1 MEDIUM-3). 닫힘 유예(200ms) 이전 시점에서 관측한다.
    fireEvent.mouseLeave(passing);
    act(() => { vi.advanceTimersByTime(180); });
    expect(shownPanelName()).toBe("개발계획");
  });

  it("★③ 팝오버에 도달하면 대기 중이던 전환이 취소된다", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    const panel = screen.getByRole("dialog", { name: "개발계획" });

    // 지나가는 아이콘 위에서 임계 직전까지 머문 뒤 팝오버에 진입한다.
    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(120); });
    fireEvent.mouseEnter(panel);
    act(() => { vi.advanceTimersByTime(500); });

    // ★목적지에 도달했으므로 예약 전환은 발화하지 않는다.
    expect(shownPanelName()).toBe("개발계획");
  });

  it("★② 머물면 전환한다 — 의도적 전환은 막지 않는다", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    expect(shownPanelName()).toBe("개발계획");

    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(300); }); // 임계(250ms) 경과

    expect(shownPanelName()).toBe("교통·편의 POI");
  });

  it("★⑤ 클릭은 즉시 확정되고 예약 전환이 뒤늦게 덮어쓰지 않는다", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    // 다른 아이콘 위에서 전환이 예약된 상태를 만든다.
    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(100); });

    // 그 상태에서 또 다른 아이콘을 클릭(의도 확정).
    fireEvent.click(railIcon("지형도·항공뷰"));
    act(() => { vi.advanceTimersByTime(500); });

    // ★클릭한 것이 남아야 한다(예약된 POI 전환이 덮어쓰면 안 된다).
    expect(shownPanelName()).toBe("지형도·항공뷰");
  });

  it("★⑥ 예약 중에 원래 열린 아이콘으로 되돌아오면 예약 전환이 취소된다", () => {
    // ★변이가 적발한 실갭: `requestHoverOpen` 첫 줄의 `cancelHoverSwitch()`를 지워도 5개
    //   테스트가 전부 통과했다. 그런데 이건 이 PR이 고치려는 버그 **그 자체**다 —
    //   스쳐 지나갔다가 되돌아왔는데도 예약이 뒤늦게 발화해 팝오버를 뺏어간다.
    //   (되돌아온 아이콘은 `alreadyShown`이라 조기 return 하므로, 취소가 그 앞에 있어야 한다.)
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(100); }); // 임계 직전
    fireEvent.mouseEnter(railIcon("개발계획")); // 되돌아옴
    act(() => { vi.advanceTimersByTime(500); });

    expect(shownPanelName()).toBe("개발계획");
  });

  it("★⑦ 아이콘에서 벗어나면(레일 안이라도) 예약 전환이 취소된다", () => {
    // ★변이가 적발한 실갭: 아이콘의 `onMouseLeave={cancelHoverSwitch}`를 양쪽 다 지워도
    //   전부 통과했다. 아이콘 사이 여백으로 빠지는 경로는 형제 mouseenter도, 레일 이탈도
    //   발화하지 않아 **이 핸들러만이** 예약을 거둔다.
    //   ★`relatedTarget`을 레일로 준다: 인자 없는 `fireEvent.mouseLeave`는 relatedTarget이
    //   null이라 React가 **레일 이탈**로도 해석해 닫힘 유예가 먼저 걸리고, 그러면 패널이
    //   null이 되어 `not.toBe(...)`가 **공허하게 통과**한다(그래서 ①은 이 갭을 못 잡았다).
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    const passing = railIcon("교통·편의 POI");
    fireEvent.mouseEnter(passing);
    act(() => { vi.advanceTimersByTime(100); });

    // 레일 안 여백으로 이탈 — 형제 mouseenter도, 레일 이탈도 발화하지 않는 경로.
    fireEvent.mouseLeave(passing, { relatedTarget: screen.getByTestId("map-layer-rail") });
    act(() => { vi.advanceTimersByTime(500); });

    // 원래 팝오버가 그대로 살아 있어야 한다(예약이 발화하면 POI로 갈아치워진다).
    expect(shownPanelName()).toBe("개발계획");
  });

  it("★⑪ Esc로 닫은 뒤 예약 전환이 되살리지 않는다(닫힘 근원 전파)", () => {
    // ★R1 MEDIUM-1: 취소를 핸들러마다 흩어 배선했더니 Esc·X·외부클릭 3경로가 샜다 —
    //   아이콘 위에서 Esc를 누르면 닫힌 뒤 150ms 후 예약이 발화해 **되살아났다**.
    //   봉합은 공용 닫힘 헬퍼(closeLayerPanel/closeBasemapPanel)에서 취소하는 것이고,
    //   이 테스트가 그 수렴점을 잠근다(한 곳을 고치면 6경로가 따라온다).
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(100); });

    fireEvent.keyDown(document, { key: "Escape" });
    expect(shownPanelName()).toBeNull();

    act(() => { vi.advanceTimersByTime(500); });
    expect(shownPanelName()).toBeNull(); // 되살아나면 안 된다
  });

  // ── 베이스맵 형제 대칭(R1 MEDIUM-2) ───────────────────────────────────────────
  //   레이어 쪽 배선(①③⑤)은 잠겼는데 **베이스맵 쌍둥이 3곳은 전부 무커버리지**였다
  //   (onMouseEnter 지연 경유·onClick 즉시확정·팝오버 도달 취소를 각각 지워도 33/33 통과).
  //   주석이 주장하는 "레일 형제와 동일 계약"이 강제되지 않던 것 — 이 저장소가 반복 지적하는
  //   '배선 미변이로 뚫림' 패턴이라 대칭 케이스를 심는다.
  it("★⑧ 베이스맵도 스쳐 지나가면 전환하지 않는다(형제 대칭)", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    expect(shownPanelName()).toBe("개발계획");

    fireEvent.mouseEnter(screen.getByRole("button", { name: "베이스맵 선택" }));
    act(() => { vi.advanceTimersByTime(80); }); // 임계 미만
    expect(shownPanelName()).toBe("개발계획");

    act(() => { vi.advanceTimersByTime(220); }); // 임계 경과 = 의도적 전환
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("★⑨ 베이스맵 클릭은 즉시 확정되고 예약 전환이 덮어쓰지 않는다(형제 대칭)", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(100); });

    fireEvent.click(screen.getByRole("button", { name: "베이스맵 선택" })); // 의도 확정
    act(() => { vi.advanceTimersByTime(500); });

    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("★⑩ 베이스맵 팝오버에 도달하면 대기 중이던 전환이 취소된다(형제 대칭)", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(screen.getByRole("button", { name: "베이스맵 선택" }));
    const panel = screen.getByRole("dialog", { name: "베이스맵" });

    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(120); });
    fireEvent.mouseEnter(panel); // 목적지 도달
    act(() => { vi.advanceTimersByTime(500); });

    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("★⑫ 고정(클릭)분으로의 복귀는 지연하지 않는다 — 대가까지 의도로 박제", () => {
    // ★이 테스트는 '좋은 동작'이 아니라 **선택한 트레이드오프**를 박제한다(R2 MEDIUM).
    //   고정분 복귀를 지연시키면 레일 이탈이 그 예약을 죽여 **클릭으로 고정한 팝오버가 닫힌다**.
    //   그래서 예외를 뒀고, 그 대가로 **고정된 아이콘 1개는 스침만으로도 즉시 열린다**.
    //   다음 세션이 이 대가를 '버그'로 보고 예외를 걷어내면 더 심한 회귀가 부활하므로,
    //   대가 쪽 동작 자체를 테스트로 고정해 '알고 고른 것'임을 남긴다.
    render(<SatongMapShell locale="ko" />);

    fireEvent.click(railIcon("개발계획")); // 클릭 확정(pin=개발계획)
    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(300); }); // 의도적 전환 — 지금 보이는 건 POI
    expect(shownPanelName()).toBe("교통·편의 POI");

    // 고정분을 '스치기만' 해도 즉시 열린다 = 알고 수용한 대가.
    fireEvent.mouseEnter(railIcon("개발계획"));
    expect(shownPanelName()).toBe("개발계획"); // 타이머 진행 없이 이미
  });

  it("★⑬ 베이스맵도 Esc로 닫은 뒤 예약 전환이 되살리지 않는다(형제 대칭)", () => {
    // R2 LOW: `closeBasemapPanel`의 취소만 무커버리지였다(코드는 정상, 테스트 공백).
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(screen.getByRole("button", { name: "베이스맵 선택" }));
    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(100); });

    fireEvent.keyDown(document, { key: "Escape" });
    expect(shownPanelName()).toBeNull();

    act(() => { vi.advanceTimersByTime(500); });
    expect(shownPanelName()).toBeNull();
  });

  it("★⑮ 임계 하한을 잠근다 — 모델 최악치(~172ms) 체류로는 전환되지 않는다", () => {
    // ★이 테스트가 없으면 임계를 150으로 되돌려도 **전 스위트가 침묵한다**(R3 LOW-1 실측:
    //   delay=0·90은 CAUGHT인데 150·299는 SURVIVED). 즉 임계 상향 커밋의 **존재 이유**가
    //   회귀 방어되지 않는다. 임계값 자체에 결합시키지 않으면서 하한만 잠그기 위해,
    //   근거 모델의 최악치(보수 계수·최하단 행 대각 통과 체류 ~172ms)보다 넉넉한 200ms를
    //   써서 "이 정도 스침으로는 전환되지 않는다"를 단언한다.
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    expect(shownPanelName()).toBe("개발계획");

    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(200); });

    expect(shownPanelName()).toBe("개발계획");
  });

  it("★⑯ 앵커 토글은 닫힘 유예도 거두고, 재이탈 시 닫힘이 재무장된다", () => {
    // R3 LOW-2: 앵커 onClick의 `cancelHoverClose()`가 무커버리지였다(동작은 정상, 테스트 공백).
    //   앵커는 레일 **안**의 버튼이라 클릭 시점에 포인터가 레일 안에 있다 → 유예를 거두는 것이
    //   "레일을 벗어날 때 닫는다" 계약과 정합해야 하고, 벗어나면 다시 닫혀야 한다.
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    const rail = screen.getByTestId("map-layer-rail");
    fireEvent.mouseLeave(rail); // 닫힘 유예 가동
    act(() => { vi.advanceTimersByTime(100); });

    fireEvent.click(screen.getByTitle(/레이어 목록 고정 해제|지도 레이어 관리/));
    act(() => { vi.advanceTimersByTime(600); });
    expect(shownPanelName()).toBe("개발계획"); // 유예가 거둬져 살아 있다

    fireEvent.mouseLeave(rail); // 재이탈
    act(() => { vi.advanceTimersByTime(600); });
    expect(shownPanelName()).toBeNull(); // 닫힘 계약 재무장
  });

  it("★⑭ 레일 1↔2열 토글이 예약된 전환을 발화시키지 않는다", () => {
    // ★토글은 12개 버튼을 리플로우시켜 **마우스를 1px도 안 움직여도** 커서 밑 아이콘이 바뀐다.
    //   예약을 안 거두면 '접기' 버튼이 조용히 무관한 레이어로 팝오버를 갈아치운다.
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    fireEvent.mouseEnter(railIcon("교통·편의 POI")); // 전환 예약
    act(() => { vi.advanceTimersByTime(100); });

    fireEvent.click(screen.getByTitle(/레이어 목록 고정 해제|지도 레이어 관리/));
    act(() => { vi.advanceTimersByTime(500); });

    expect(shownPanelName()).toBe("개발계획");
  });

  it("레일을 벗어나면 예약된 전환이 발화하지 않는다", () => {
    render(<SatongMapShell locale="ko" />);

    fireEvent.mouseEnter(railIcon("개발계획"));
    fireEvent.mouseEnter(railIcon("교통·편의 POI"));
    act(() => { vi.advanceTimersByTime(100); });

    // ★닫힘 유예(200ms) 이전 시점에서 **양성** 단언 — 500ms 뒤엔 전부 닫혀 null이라
    //   `not.toBe(...)`가 공허 통과했다(R1 MEDIUM-3: 레일 이탈 취소를 지운 변이가 이 테스트를
    //   통과했고 다른 파일이 우연히 잡았다). 임계(150ms)는 이미 지났으므로 미발화가 증명된다.
    fireEvent.mouseLeave(screen.getByTestId("map-layer-rail"));
    act(() => { vi.advanceTimersByTime(180); });

    expect(shownPanelName()).toBe("개발계획");
  });
});
