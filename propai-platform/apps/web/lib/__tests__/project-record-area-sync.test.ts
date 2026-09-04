/**
 * 프로젝트 레코드의 대지면적이 **생성 시점에 얼어붙어** 있었다.
 *
 * ## 실측(프로덕션 20건)
 *
 * `projects.total_area_sqm` 은 생성 시 1회 기록되고 **그 뒤 갱신 경로가 없다** —
 * 프론트 전체에서 `/projects/{id}` 로 가는 PUT 은 `pushSnapshot` 하나뿐이고, 그 body 에는
 * `analysis_snapshot` 만 있었다. 그래서 필지를 고쳐도 레코드는 그대로다.
 *
 *     레코드 5,781㎡  vs  스냅샷 필지합 5,881㎡     ← 같은 부지를 화면이 두 값으로 말한다
 *     20건 중 **7건**이 레코드 ≠ 필지합 (최대 차 23,632㎡)
 *
 * ## 의미는 **대지면적**이다(추측 아님)
 *
 * 생성 경로 둘(`projects/new`·`satong-project-create`)이 대지면적을 쓰고,
 * `building_compliance_service._get_site_area()` 독스트링도 *"프로젝트 DB에서 대지면적을
 * 조회한다"* 라고 적는다. 소비처로 확인했다.
 *
 * ## 산식은 복제하지 않는다
 *
 * 유효면적 판정(다필지 통합 우선·강등 처리)은 `effectiveLandAreaSqm` **한 곳**에만 산다.
 * 서버에 같은 산식을 다시 쓰지 않고, **그 값을 이미 가진 쪽**이 같은 PUT 에 실어 보낸다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api-client";
import { pushSnapshot } from "@/lib/projectSync";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), put: vi.fn(), post: vi.fn() },
}));

const PID = "33333333-4444-4555-8666-777777777777";
const ADDR = "서울특별시 동작구 상도동 210-453";

function seed(site: Record<string, unknown>) {
  useProjectStore.setState({ projects: [{ id: PID, name: "테스트", address: ADDR }] } as never);
  useProjectContextStore.setState({ projectId: PID, siteAnalysis: site } as never);
}

const lastBody = () => {
  const calls = vi.mocked(apiClient.put).mock.calls.filter((c) => String(c[0]).includes(PID));
  return (calls.at(-1)?.[1] as { body?: Record<string, unknown> } | undefined)?.body ?? {};
};

describe("프로젝트 레코드 대지면적 동기화", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("propai_access_token", "t");
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
  });

  it("★다필지 통합면적이 스냅샷과 **같은 PUT** 으로 레코드에 간다 — 갱신 경로가 없던 자리", async () => {
    seed({
      address: ADDR,
      landAreaSqm: 543,
      landAreaSqmTotal: 10686,
      parcelCount: 33,
      parcels: Array.from({ length: 33 }, () => ({ address: ADDR, areaSqm: 300 })),
    });

    await pushSnapshot();

    const body = lastBody();
    expect(body.analysis_snapshot, "스냅샷이 빠졌다 — 기존 계약 회귀").toBeTruthy();
    expect(body.total_area_sqm, "레코드 면적이 안 갔다 — 생성 시점에 얼어붙은 채로 남는다").toBe(10686);
  });

  it("★단일필지도 간다", async () => {
    seed({ address: ADDR, landAreaSqm: 236, parcelCount: 1 });
    await pushSnapshot();
    expect(lastBody().total_area_sqm).toBe(236);
  });

  it("★면적 미확보면 **키를 만들지 않는다** — 0/null 로 레코드를 지우지 않는다", async () => {
    seed({ address: ADDR });
    await pushSnapshot();
    const body = lastBody();
    expect(body.analysis_snapshot, "스냅샷은 그대로 가야 한다").toBeTruthy();
    expect("total_area_sqm" in body, "미확보인데 키를 만들어 레코드를 덮었다").toBe(false);
  });

  it("★0 이하는 보내지 않는다 — 서버 스키마가 gt=0 이라 통째로 422 가 된다", async () => {
    seed({ address: ADDR, landAreaSqm: 0, parcelCount: 1 });
    await pushSnapshot();
    expect("total_area_sqm" in lastBody()).toBe(false);
  });

  it("[양성 대조군] 무결성 가드가 막으면 아무것도 안 간다 — 면적만 새어 나가지 않는다", async () => {
    useProjectStore.setState({
      projects: [{ id: PID, name: "테스트", address: "충청북도 제천시 모산동 123-1" }],
    } as never);
    useProjectContextStore.setState({
      projectId: PID,
      siteAnalysis: { address: ADDR, landAreaSqm: 236, parcelCount: 1 },
    } as never);

    await pushSnapshot();

    expect(
      vi.mocked(apiClient.put).mock.calls.filter((c) => String(c[0]).includes(PID)),
      "오염 상태인데 면적 갱신이 서버로 갔다",
    ).toHaveLength(0);
  });
});
