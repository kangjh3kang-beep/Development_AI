/**
 * **프로젝트 목록이 20건에서 잘렸다** — 그리고 그 절단이 중복 생성으로 번졌다.
 *
 * ## 실물(라이브 실측 2026-08-25 · admin 테넌트)
 *
 *     GET /api/v1/projects            → total=24 · page_size=20 · has_next=true · items=20
 *     GET /api/v1/projects?page_size=100 → items=24
 *
 * 차집합 4건(`bf93f584`·`f49ae16b`·`44e19843`·`2a8031d8`, 전부 2026-06 생성)은
 * `syncFromBackend` 가 로컬 목록을 응답으로 **교체**하므로 화면에서 사라진다.
 *
 * ## 왜 표시 결함에서 끝나지 않는가
 *
 * 같은 함수가 고아 판정을 그 잘린 목록으로 한다 →
 * **잘려서 안 보이는 프로젝트를 "백엔드에 없다"고 오판해 다시 POST 한다.**
 * `#815` 의 인플라이트 레지스트리는 *생성이 진행 중인* 것만 보호하므로 이 경로를 못 막는다.
 *
 * ★이 파일은 **store 를 직접 태운다** — 순수 헬퍼(`lib/projects-fetch`)만 잠그면
 *   store 가 그것을 안 부르도록 되돌려도 초록이 된다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { __resetProjectCreating, useProjectStore } from "@/store/useProjectStore";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

type Row = { id: string; name: string; address: string };

/** 라이브와 같은 형상의 서버: 24건을 20건씩 페이지로 준다. */
function serve(total: number, serverPageSize: number) {
  const rows: Row[] = Array.from({ length: total }, (_, i) => ({
    id: `0000000${i}-aaaa-bbbb-cccc-dddddddddddd`.slice(-36),
    name: `프로젝트${i + 1}`,
    address: `주소${i + 1}`,
  }));
  vi.mocked(apiClient.get).mockImplementation((async (path: string) => {
    const q = new URL(String(path), "http://x").searchParams;
    const page = Number(q.get("page") ?? "1");
    const size = Math.min(Number(q.get("page_size") ?? String(serverPageSize)), serverPageSize);
    const offset = (page - 1) * size;
    const items = rows.slice(offset, offset + size);
    return { items, total, page, page_size: size, has_next: offset + items.length < total };
  }) as never);
  return rows;
}

const postCalls = () =>
  vi.mocked(apiClient.post).mock.calls.filter((c) => String(c[0]) === "/projects");

describe("★목록 절단 — 오래된 프로젝트가 사라지지 않는다", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    useProjectStore.setState({ projects: [], syncing: false } as never);
    __resetProjectCreating();
  });

  it("서버가 20건씩 24건을 주면 store 에 **24건**이 들어온다(종전엔 20건)", async () => {
    const rows = serve(24, 20);
    await useProjectStore.getState().syncFromBackend();
    const got = useProjectStore.getState().projects;
    expect(got).toHaveLength(24);
    // ★두 모집단을 가른다 — 1페이지만 걸으면 마지막 4건이 없다.
    expect(got.map((p) => p.id)).toContain(rows[23].id);
    expect(got.map((p) => p.id)).toContain(rows[20].id);
  });

  it("[양성 대조군] 20건 이하면 한 번만 부른다 — 과호출 회귀 방지", async () => {
    serve(7, 20);
    await useProjectStore.getState().syncFromBackend();
    expect(vi.mocked(apiClient.get).mock.calls).toHaveLength(1);
    expect(useProjectStore.getState().projects).toHaveLength(7);
  });
});

describe("★절단이 만드는 **중복 생성**을 막는다", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.post).mockResolvedValue({ id: "new-uuid", address: "주소24" } as never);
    useProjectStore.setState({ projects: [], syncing: false } as never);
    __resetProjectCreating();
  });

  it("★2페이지째에만 있는 주소를 가진 로컬 레코드를 **다시 만들지 않는다**", async () => {
    serve(24, 20); // 주소24 는 2페이지에 있다
    useProjectStore.setState({
      projects: [{ id: "local99", name: "프로젝트24", address: "주소24", area: "" }],
    } as never);
    await useProjectStore.getState().syncFromBackend();
    expect(
      postCalls(),
      "2페이지를 안 걸으면 '백엔드에 없다'고 오판해 같은 프로젝트를 다시 만든다",
    ).toHaveLength(0);
  });

  it("[양성 대조군] 어느 페이지에도 없는 주소는 여전히 마이그레이션된다 — 판정이 한쪽으로 굳지 않았다", async () => {
    serve(24, 20);
    useProjectStore.setState({
      projects: [{ id: "local98", name: "진짜 고아", address: "어디에도 없는 주소", area: "" }],
    } as never);
    await useProjectStore.getState().syncFromBackend();
    expect(postCalls()).toHaveLength(1);
  });

  it("★상한에 걸려 전체를 못 받으면 고아 마이그레이션을 **하지 않고**, 로컬도 지우지 않는다", async () => {
    // 서버가 10건씩 1000건 → 상한(20페이지)까지 가도 끝나지 않는다.
    serve(1000, 10);
    useProjectStore.setState({
      projects: [{ id: "local97", name: "모르는 것", address: "확인 불가 주소", area: "" }],
    } as never);
    await useProjectStore.getState().syncFromBackend();
    expect(postCalls(), "불완전한 목록으로 판정하면 중복이 생긴다").toHaveLength(0);
    expect(
      useProjectStore.getState().projects.some((p) => p.id === "local97"),
      "끝까지 못 봤으면서 '삭제됐다'고 단정해 지웠다",
    ).toBe(true);
  });
});
