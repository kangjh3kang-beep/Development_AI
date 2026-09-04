/**
 * ★형제 스윕에서 잡힌 **더 나쁜 결함**의 회귀 잠금(2026-08-20).
 *
 * `#694` 가 넣은 지오코딩 폴백은 "추측 PNU 는 조용한 오답이라 실패가 낫다"고 **주석에 썼지만**
 * 코드에는 그 가드가 없었다. `/zoning/geocode` 는 **동 단위 주소에도** `found:true` 와 PNU 를
 * 준다(라이브 실측 2026-08-20: `경기도 오산시 내삼미동` → `4137011000101140001` = 114-1).
 * 실제 신고 프로젝트는 77행이 전부 그 동 주소였다 — 즉 77행 전부에 **같은 남의 필지 PNU** 를
 * 박고 그 PNU 로 등기까지 조회했다.
 *
 * 그래서 **요청이 나가는지 아닌지**를 잠근다(라벨만 보면 이 결함은 안 보인다).
 */
import { screen, waitFor } from "@testing-library/react";
// ★`RegistryAnalysisWorkspaceClient` 는 이제 `ParcelAuctionWatchBadge`(useQuery)를
//   렌더한다 — 프로바이더가 필요하다. 손으로 감싸지 말고 **공용 헬퍼**를 쓴다(§29).
import { renderWithQueryClient as render } from "@/test/render-with-query-client";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegistryAnalysisWorkspaceClient } from "@/components/operations/RegistryAnalysisWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/registry-analysis",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending),
      post: vi.fn(async () => ({ found: true, pnu: "4137011000101140001" })),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const PID = "prj-osan";
const DONG = "경기도 오산시 내삼미동";

function row(id: string, jibun: string): LandRow {
  return {
    id, jibun, pnu: null, owner: "", share: "", area_sqm: 100, owner_type: "",
    expected_price: null, purchase_price: null, contracted: false,
    land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
  };
}

describe("등기정보분석 — 지오코딩 폴백의 날조 경계", () => {
  beforeEach(() => {
    useProjectContextStore.setState({
      projectId: PID,
      projectName: "오산시 내삼미동 외 1필지",
      // parcels 를 이미 채워 두어 시드 이펙트가 rows 를 갈아치우지 않게 한다.
      siteAnalysis: {
        address: DONG,
        pnu: null,
        parcels: [
          { pnu: "", address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
          { pnu: "", address: `${DONG} 467-1`, areaSqm: 100, landCategory: "임야", ownerType: "" },
        ],
      } as SiteAnalysisData,
    });
    useLandScheduleStore.setState({
      byProject: { [PID]: [row("r1", DONG), row("r2", `${DONG} 467-1`)] },
    });
  });

  it("★동 단위 주소는 **지오코딩하지 않는다**(같은 동 전 행이 남의 필지로 수렴한다)", async () => {
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);

    // 공허 진리 가드: 대조군(번지 있는 행)에는 요청이 실제로 나갔다 —
    //   "0건" 이 '가드가 동작했다' 가 아니라 '이펙트가 아예 안 돌았다' 여도 통과하는 것을 막는다.
    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    const queries = (apiClient.post as unknown as { mock: { calls: unknown[][] } }).mock.calls
      .filter((c) => c[0] === "/zoning/geocode")
      .map((c) => (c[1] as { body?: { query?: string } })?.body?.query);

    expect(queries).toContain(`${DONG} 467-1`); // 대조군: 번지 있는 행은 해석한다
    expect(queries).not.toContain(DONG);        // ★가드: 동 단위는 절대 보내지 않는다
  });

  it("★해석하지 않은 행은 '지번 미확인' 을 말한다(조용히 넘어가지 않는다)", async () => {
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);
    await waitFor(() =>
      expect(screen.getAllByTestId("registry-row-jibun-unresolved")).toHaveLength(1),
    );
  });
});
