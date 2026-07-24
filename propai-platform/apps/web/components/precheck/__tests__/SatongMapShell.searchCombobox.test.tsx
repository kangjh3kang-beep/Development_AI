/**
 * SatongMapShell 검색 후보 콤보박스 — 키보드 내비게이션 회귀망(UX 트랙 C6, R1 후속).
 *
 * 왜 필요한가: R1 리뷰어가 방향키/Enter 키보드 핸들러 블록 전체를 무력화한 변이를
 * 주입했더니 기존 스위트 전체가 그대로 통과(생존)했다 — 즉 "키보드로 후보를 고를 수
 * 있다"는 계약을 검증하는 테스트가 실재하지 않았다는 뜻이다. 이 스위트가 그 공백을 닫는다:
 *   ① ArrowDown → aria-activedescendant가 다음 옵션 id로 이동한다.
 *   ② Enter가 "0번 고정"이 아니라 하이라이트된 후보를 확정한다(핵심 회귀 지점).
 *   ③ Home/End가 처음/끝 옵션으로 점프한다.
 *   ④ Escape가 후보 목록(listbox)을 닫는다.
 *
 * 검증됨(수동): keydown 핸들러 본문을 통째로 주석 처리하는 변이를 주입해 이 스위트의
 * ①②③④가 전부 FAIL하는 것을 확인한 뒤 원복했다(아래 커밋 메시지 참조).
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

// 3개 고정 후보 — 검색어 입력→디바운스(350ms)→/zoning/search만 실데이터로 응답하고
// 나머지 엔드포인트(예: /projects 동기화)는 영구 pending(무관 — 이 스위트가 안 건드림).
const CANDIDATES = [
  { address: "서울특별시 종로구 청진동 1", pnu: "1111010100100010000" },
  { address: "서울특별시 종로구 청진동 2", pnu: "1111010100100020000" },
  { address: "서울특별시 종로구 청진동 3", pnu: "1111010100100030000" },
];

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      get: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
      post: vi.fn(async (path: string) => {
        if (path === "/zoning/search") {
          return { candidates: CANDIDATES };
        }
        return pending();
      }),
    },
  };
});

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null,
      projectName: "",
      projectStatus: "",
      siteAnalysis: null,
    });
  });
}

async function typeQueryAndWaitForCandidates(value: string) {
  const input = screen.getByPlaceholderText("예: 의정부동 224, 판교역로 166");
  fireEvent.change(input, { target: { value } });
  // 디바운스(350ms) 경과 → apiClient.post 모킹 응답까지 마이크로태스크 흘려보낸다.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  return input;
}

// ★"연결 프로젝트" 네이티브 <select>의 <option> 자식들도 암묵 role="option"이라, 스코프
//   없이 getAllByRole("option")을 쓰면 그 2개(new/none)까지 섞여 잡힌다(실측 확인) —
//   검색 후보 listbox 안으로만 좁혀 조회한다.
function searchOptions() {
  return within(screen.getByRole("listbox")).getAllByRole("option");
}

describe("SatongMapShell 검색 후보 콤보박스 — 키보드 내비(UX 트랙 C6)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    window.sessionStorage.clear();
    resetStores();
  });

  it("① ArrowDown → aria-activedescendant가 다음 옵션 id로 이동한다", async () => {
    render(<SatongMapShell locale="ko" />);
    const input = await typeQueryAndWaitForCandidates("청진동");

    const options = searchOptions();
    expect(options).toHaveLength(3);
    expect(input).not.toHaveAttribute("aria-activedescendant");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);

    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input).toHaveAttribute("aria-activedescendant", options[1].id);
  });

  it("② Enter가 (0번 고정이 아니라) 하이라이트된 후보를 확정한다 — 핵심 회귀 지점", async () => {
    render(<SatongMapShell locale="ko" />);
    const input = await typeQueryAndWaitForCandidates("청진동");

    // 0→1(청진동 2번째)까지 두 번 내려간 뒤 Enter — 0번(청진동 1)이 아니라
    // 하이라이트된 1번(청진동 2)이 확정돼야 한다.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByText("청진동 2")).toBeInTheDocument();
    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.queryByText("청진동 3")).not.toBeInTheDocument();
  });

  it("③ Home/End가 처음/끝 옵션으로 점프한다", async () => {
    render(<SatongMapShell locale="ko" />);
    const input = await typeQueryAndWaitForCandidates("청진동");
    const options = searchOptions();

    fireEvent.keyDown(input, { key: "End" });
    expect(input).toHaveAttribute("aria-activedescendant", options[2].id);

    fireEvent.keyDown(input, { key: "Home" });
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
  });

  it("④ Escape가 후보 목록(listbox)을 닫는다", async () => {
    render(<SatongMapShell locale="ko" />);
    const input = await typeQueryAndWaitForCandidates("청진동");
    expect(searchOptions()).toHaveLength(3);

    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
