/**
 * ★배선을 **행위로** 잠근다 — 「이름이 있다」가 아니라 **「불렀더니 줄었다」**.
 *
 * 초판은 소스 위치(`indexOf`)로 잠갔는데, 호출 콜백을 무력화하는 변이가 **생존**했다
 * (문자열은 그대로 남으므로). 이 저장소가 반복해 데인 그 형태다:
 * **정의만 하고 소비처 0** / **이름만 보는 락**.
 *
 * ★그리고 **절단 분기**를 같은 파일에서 태운다 — `#822`(목록 20건 절단) 전례가 있어,
 *   절단된 목록으로 정리하면 **살아 있는 스냅샷을 고아로 오판**한다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const snap = (tag: string) => ({ siteAnalysis: { address: tag } }) as never;

/** 백엔드가 프로젝트 하나(`live`)만 돌려주는 완전한 목록. */
function mockBackend(items: Array<{ id: string }>, hasNext = false) {
  vi.mocked(apiClient.get).mockResolvedValue({
    items: items.map((p) => ({ ...p, name: p.id, address: `주소-${p.id}` })),
    has_next: hasNext,
    total: items.length,
  } as never);
}

describe("배선 — 동기화가 실제로 정리를 일으킨다", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    useProjectStore.setState({ projects: [], syncing: false } as never);
    useProjectContextStore.setState({
      projectId: null,
      snapshots: { live: snap("L"), gone: snap("G") },
    } as never);
  });

  it("★syncFromBackend 뒤 고아가 실제로 사라진다(두 모집단)", async () => {
    mockBackend([{ id: "live" }]);
    await useProjectStore.getState().syncFromBackend();
    // 동적 임포트가 마이크로태스크로 도니 한 틱 넘긴다.
    await new Promise((r) => setTimeout(r, 0));

    const s = useProjectContextStore.getState().snapshots;
    expect(s.live).toBeDefined();      // 살아 있는 것은 남고
    expect(s.gone).toBeUndefined();    // 고아는 사라진다
  });

  it("★★목록이 절단되면 정리하지 않는다 — 「모르는 것을 지우지 않는다」", async () => {
    // `has_next: true` 이고 다음 페이지가 없으면 `fetchAllProjects` 가 truncated 로 신고한다.
    vi.mocked(apiClient.get).mockResolvedValue({
      items: [{ id: "live", name: "live", address: "주소-live" }],
      has_next: true,
      total: 99,
    } as never);
    await useProjectStore.getState().syncFromBackend();
    await new Promise((r) => setTimeout(r, 0));

    const s = useProjectContextStore.getState().snapshots;
    expect(s.gone).toBeDefined();      // ★절단이면 고아처럼 보여도 남긴다
  });
});
