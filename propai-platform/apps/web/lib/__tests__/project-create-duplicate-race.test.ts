/**
 * **같은 프로젝트가 두 번 만들어졌다** — 생성 중 동기화 경합.
 *
 * ## 실물
 *
 * 프로덕션에 이름·주소·필지수(77)가 **완전히 같은 중복 프로젝트 2건**이 있다.
 *
 * ## 기전(코드로 확정)
 *
 * 두 생성 경로 모두 이 순서다:
 *
 *     addProject(...)            → **비UUID** 로컬 레코드(주소 포함)
 *     await POST /projects       → ★이 창 동안 레코드는 "고아"로 보인다
 *     updateProject(id → UUID)
 *
 * 그런데 `syncFromBackend` 는 *"비UUID + 주소가 백엔드 목록에 없음 = 고아"* 로 보고
 * **POST 로 다시 만든다.** 그 동기화는 여러 화면의 마운트마다 발화한다.
 *
 * ★주소 문자열 중복제거로는 못 막는다 — **그 창에서는 백엔드에 아직 없기 때문**이다.
 *   (그래서 종전 dedup 은 이 경합에 무력했다.)
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import {
  __resetProjectCreating,
  _creatingCount,
  markProjectCreating,
  unmarkProjectCreating,
  useProjectStore,
} from "@/store/useProjectStore";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const ADDR = "경기도 오산시 내삼미동";

/** 로컬에 비UUID 레코드만 있고 백엔드 목록은 비어 있는 상태 = 생성 await 창. */
function seedCreatingWindow(localId: string) {
  useProjectStore.setState({
    projects: [{ id: localId, name: "오산시 내삼미동 외 76필지", address: ADDR, area: "86755" }],
  } as never);
  vi.mocked(apiClient.get).mockResolvedValue({ items: [] } as never);
}

const postCalls = () =>
  vi.mocked(apiClient.post).mock.calls.filter((c) => String(c[0]) === "/projects");

describe("생성 중 동기화 경합 — 같은 프로젝트를 두 번 만들지 않는다", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.post).mockResolvedValue({ id: "uuid-1", address: ADDR } as never);
    useProjectStore.setState({ projects: [], syncing: false } as never);
    __resetProjectCreating();
  });

  it("★서버 생성 진행 중이면 동기화가 그 레코드를 다시 만들지 않는다", async () => {
    const localId = "abc1234";
    seedCreatingWindow(localId);
    markProjectCreating(localId); // 생성기가 POST 직전에 알린다

    await useProjectStore.getState().syncFromBackend();

    expect(
      postCalls(),
      "생성 await 창에서 동기화가 같은 프로젝트를 다시 POST 했다 — 중복 프로젝트의 기전",
    ).toHaveLength(0);
    unmarkProjectCreating(localId);
  });

  it("[양성 대조군] 진행 중이 아니면 **종전대로** 고아를 마이그레이션한다", async () => {
    // 가드가 정상 경로(오프라인에서 만들어진 진짜 고아)까지 막으면 로컬 전용 프로젝트가
    // 영영 서버에 안 올라간다 — 그 회귀를 여기서 잡는다.
    seedCreatingWindow("orphan1");

    await useProjectStore.getState().syncFromBackend();

    expect(postCalls(), "진짜 고아를 마이그레이션하지 않았다 — 과차단").toHaveLength(1);
  });

  it("★생성 실패 후에는 다시 고아가 된다 — 실패 건이 영영 안 올라가면 안 된다", async () => {
    const localId = "abc9999";
    seedCreatingWindow(localId);
    markProjectCreating(localId);
    unmarkProjectCreating(localId); // 생성기가 finally 에서 해제(성공·실패 양쪽)

    await useProjectStore.getState().syncFromBackend();

    expect(postCalls(), "해제 후에도 막혀 있으면 실패 건이 영영 서버에 못 간다").toHaveLength(1);
  });

  it("★이미 UUID 인 레코드는 애초에 대상이 아니다(회귀 없음)", async () => {
    useProjectStore.setState({
      projects: [{ id: "11111111-2222-4333-8444-555555555555", name: "x", address: ADDR, area: "1" }],
    } as never);
    vi.mocked(apiClient.get).mockResolvedValue({ items: [] } as never);

    await useProjectStore.getState().syncFromBackend();

    expect(postCalls()).toHaveLength(0);
  });
});

describe("인플라이트 레지스트리", () => {
  it("★빈 id 는 등록하지 않는다 — 빈 문자열이 모든 판정을 막지 않게", () => {
    const before = _creatingCount();
    markProjectCreating("");
    expect(_creatingCount()).toBe(before);
  });
});
