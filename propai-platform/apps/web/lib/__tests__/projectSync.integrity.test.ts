/**
 * WP-D 무결성 가드가 **서버 쓰기 경로 둘 다**에 닿는지 고정한다.
 *
 * 증상(실측): 가드는 pushSnapshot(/projects/{id}.analysis_snapshot)에만 걸려 있었다.
 *   ProjectSyncProvider 의 한 구독 콜백이 scheduleSnapshotSync 와 scheduleSyncUp 을 함께
 *   부르므로, 스냅샷을 막아도 같은 오염 siteAnalysis 가 syncUp 으로 /store/projects 에
 *   실려 나갔고(CTX_KEYS 에 siteAnalysis 포함) syncDown 이 그대로 되돌렸다.
 *   그 가드를 태우는 테스트는 전수 0건이었다(무잠금).
 *
 * ★픽스처는 두 모집단을 가른다 — "다른 지역"(교차오염·막아야 함)과
 *   "같은 지역·다른 번지"(지도에서 인접 필지 추가 = 정상 워크플로우·막으면 안 됨).
 *   판별자를 addressRegionMismatch → addressTokenMismatch 로 되돌리면 후자가 죽는다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { pushSnapshot, syncUp } from "@/lib/projectSync";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), put: vi.fn(), post: vi.fn() },
}));

const PROJECT_ID = "11111111-2222-4333-8444-555555555555";

/** 프로젝트 레코드 주소와 분석 주소를 각각 세워 실제 스토어를 오염/정상 상태로 만든다. */
function seed(recordAddress: string, analysisAddress: string) {
  useProjectStore.setState({
    projects: [{ id: PROJECT_ID, name: "테스트", address: recordAddress }],
  } as never);
  useProjectContextStore.setState({
    projectId: PROJECT_ID,
    siteAnalysis: { address: analysisAddress },
  } as never);
}

const putCalls = (path: string) =>
  vi.mocked(apiClient.put).mock.calls.filter((c) => String(c[0]).includes(path));

/** 보류 경고 문구 전체(앞뒤 잔재까지) — 개발자가 로그만 보고 "어느 경로가·무엇 때문에"
    막혔는지 알 수 있어야 가드가 진단 가능하다. */
const warnText = (warn: ReturnType<typeof vi.spyOn>) =>
  warn.mock.calls.map((c) => String(c[0])).join("\n");

describe("WP-D 무결성 가드 — 서버 쓰기 경로 전수", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("propai_access_token", "test-token");
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
  });

  it("[양성 대조군] 주소가 일치하면 스토어 blob 을 실제로 푸시한다(가드가 정상 동기화를 막지 않는다)", async () => {
    seed("서울특별시 동작구 상도동 123", "서울특별시 동작구 상도동 123");

    await syncUp();

    // ★이 단언이 먼저다 — 아래 "푸시 0건"이 "원래 아무것도 안 나간다"로 공허하게 참이 되는 것을 막는다.
    expect(putCalls("/store/projects")).toHaveLength(1);
  });

  it("★교차오염(다른 지역)이면 /store/projects 푸시를 보류한다", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    seed("서울특별시 동작구 상도동 123", "경기도 용인시 처인구 고기동 45");

    await syncUp();

    expect(putCalls("/store/projects")).toHaveLength(0);
    // 진단 가능성 락 — 두 주소를 모두 말하고, 어느 경로가 막혔는지 사유로 구분된다.
    const text = warnText(warn);
    expect(text).toContain("서울특별시 동작구 상도동 123");
    expect(text).toContain("경기도 용인시 처인구 고기동 45");
    expect(text).toContain("지역 불일치");
    warn.mockRestore();
  });

  it("★같은 지역·다른 번지(인접 필지 추가)는 보류하지 않는다 — 스토어 blob 은 차단 범위가 계정 전체다", async () => {
    seed("서울특별시 동작구 상도동 123", "서울특별시 동작구 상도동 456");

    await syncUp();

    expect(putCalls("/store/projects")).toHaveLength(1);
  });

  it("스냅샷 경로도 여전히 교차오염을 보류한다(기존 가드 회귀 없음)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    seed("서울특별시 동작구 상도동 123", "경기도 용인시 처인구 고기동 45");

    await pushSnapshot();

    expect(putCalls(`/projects/${PROJECT_ID}`)).toHaveLength(0);
    // ★두 경로의 사유가 서로 구분돼야 한다 — 같은 문구면 로그로 경로를 못 가른다.
    expect(warnText(warn)).toContain("핵심 토큰 불일치");
    warn.mockRestore();
  });

  it("[양성 대조군] 스냅샷 경로는 주소가 일치하면 실제로 푸시한다", async () => {
    seed("서울특별시 동작구 상도동 123", "서울특별시 동작구 상도동 123");

    await pushSnapshot();

    expect(putCalls(`/projects/${PROJECT_ID}`)).toHaveLength(1);
  });

  it("★정화된 상태(siteAnalysis 없음)에서는 가드가 열린다 — 자가치유 뒤 동기화가 영구 정지하면 안 된다", async () => {
    // #779 계열 자가치유가 오염 스냅샷을 비우면 비교 대상이 사라진다. 그때 계속 막으면
    //   계정 전체 동기화가 영영 멈춘다 — 비교 불능은 위반이 아니다(fail-open)를 못박는다.
    useProjectStore.setState({
      projects: [{ id: PROJECT_ID, name: "테스트", address: "서울특별시 동작구 상도동 123" }],
    } as never);
    useProjectContextStore.setState({ projectId: PROJECT_ID, siteAnalysis: null } as never);

    await syncUp();

    expect(putCalls("/store/projects")).toHaveLength(1);
  });

  it("프로젝트 레코드에 주소가 없으면 가드가 열린다 — 한쪽만으로는 오염을 판정할 수 없다", async () => {
    useProjectStore.setState({
      projects: [{ id: PROJECT_ID, name: "테스트", address: "" }],
    } as never);
    useProjectContextStore.setState({
      projectId: PROJECT_ID,
      siteAnalysis: { address: "경기도 용인시 처인구 고기동 45" },
    } as never);

    await syncUp();

    expect(putCalls("/store/projects")).toHaveLength(1);
  });

  it("★주소가 아닌 값(엑셀 소유자 컬럼 오인식)은 두 경로 모두 보류한다 — 지역 비교는 이걸 못 잡는다", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    // 실측 손상 데이터의 형태: 프로젝트는 상도동인데 분석 주소가 소유자 이름이다.
    seed("서울특별시 동작구 상도동 210-453", "◀ 전성결");

    await syncUp();
    await pushSnapshot();

    expect(putCalls("/store/projects")).toHaveLength(0);
    expect(putCalls(`/projects/${PROJECT_ID}`)).toHaveLength(0);
    expect(warnText(warn)).toContain("주소 형태가 아니다");
    warn.mockRestore();
  });

  it("[양성 대조군] 시도 접두 없는 정상 주소는 보류하지 않는다 — 형태 검사가 정상 표기를 막으면 안 된다", async () => {
    // 실측 프로덕션 표기: "용인시 수지구 신봉동 56-16"(광역시도 접두 없음)·"경기도 오산시 내삼미동"(번지 없음)
    seed("용인시 수지구 신봉동 56-16", "용인시 수지구 신봉동 56-16");

    await syncUp();

    expect(putCalls("/store/projects")).toHaveLength(1);
  });

  // 부채 — 스냅샷 경로는 번지까지 엄격한 판별자를 쓴다(기존 동작 유지). 인접 필지를 추가해
  //   대표 주소의 번지가 바뀌면 그 프로젝트의 analysis_snapshot 영속이 멈출 수 있다.
  //   차단 범위가 프로젝트 하나라 스토어 blob 만큼 위험하지는 않으나, 엄격도가 옳은지는
  //   재현으로 확인하지 않았다 — 확인 전에는 바꾸지 않는다.
  it.todo("스냅샷 경로의 번지 엄격도가 정상 워크플로우를 막지 않는지 재현으로 확인");
});
