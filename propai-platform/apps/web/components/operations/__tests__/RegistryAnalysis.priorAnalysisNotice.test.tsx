/**
 * ★사용자 신고 회귀 잠금(2026-08-25) — *"권리분석 보고서 기능도 제공하지 못하고 있다"*.
 *
 * ## 실제로 무슨 일이 있었나
 *
 * 기능은 **있었다**. `RegistryRightsReportButton`(PDF/DOCX)도, 백엔드
 * `/registry/rights-report` 도 배포돼 있었다(라이브 `merge-base` 확증).
 * 그런데 그 버튼은 `{batchResults && batchResults.length > 0 && …}` 블록 **안에만**
 * 렌더되고, `batchResults` 는 **저장된 분석 결과**에서 복원된다.
 *
 * 결과 보관(`useRegistryAnalysisStore`)이 최근에 추가돼 **그 이전 분석은 저장된 적이 없다.**
 * 반면 소유자·PDF 링크는 토지조서 행(`useLandScheduleStore`)에 **따로 영속**돼 남아 있다.
 * 그래서 화면은 *"분석은 된 것처럼 보이는데 보고서 버튼은 없는"* 비대칭 상태가 되고,
 * 사용자는 **"기능이 없다"** 고 읽는다.
 *
 * ★이 파일이 잠그는 것: 그 상태에서 **침묵하지 않는다.** 무엇이 없고, 어떻게 하면 되고,
 *   그때 **돈이 드는지**를 말한다. 침묵이 곧 거짓 신호였다.
 */
import { screen, waitFor } from "@testing-library/react";
// ★`RegistryAnalysisWorkspaceClient` 는 이제 `ParcelAuctionWatchBadge`(useQuery)를
//   렌더한다 — 프로바이더가 필요하다. 손으로 감싸지 말고 **공용 헬퍼**를 쓴다(§29).
import { renderWithQueryClient as render } from "@/test/render-with-query-client";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegistryAnalysisWorkspaceClient } from "@/components/operations/RegistryAnalysisWorkspaceClient";
import { FREE_REQUERY_DAYS } from "@/lib/registry-analyze";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";
import { useRegistryAnalysisStore } from "@/store/useRegistryAnalysisStore";

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
      post: vi.fn(async () => ({ found: false })),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const PID = "prj-osan";
const ADDR = "경기도 오산시 내삼미동";

/** 분석 흔적(소유자·PDF)이 남아 있는 행 — 실제 신고 화면의 형상 그대로. */
function analyzedRow(id: string, jibun: string): LandRow {
  return {
    id, jibun, pnu: null, owner: "거창유씨문양공거타군파안녕종회", share: "단독소유",
    area_sqm: 53, owner_type: "", expected_price: null, purchase_price: null,
    contracted: false, land_use_consent: false, district_consent: false,
    operator_consent: false, pdf_url: "https://example.test/a.pdf",
  };
}

/** 흔적이 **없는** 행 — 대조군(고지가 아무 때나 뜨면 안 된다). */
function freshRow(id: string, jibun: string): LandRow {
  return { ...analyzedRow(id, jibun), owner: "", share: "", pdf_url: null };
}

function seed(rows: LandRow[]): void {
  useProjectContextStore.setState({
    projectId: PID,
    projectName: "오산시 내삼미동 외 76필지",
    siteAnalysis: { address: ADDR, pnu: null, parcels: [] } as unknown as SiteAnalysisData,
  });
  useLandScheduleStore.setState({ byProject: { [PID]: rows } });
  useRegistryAnalysisStore.setState({ byProject: {} });
}

describe("등기 분석 — 저장분 없는 이전 분석을 정직하게 고지한다", () => {
  beforeEach(() => {
    seed([analyzedRow("r1", `${ADDR} 467-1`), analyzedRow("r2", `${ADDR} 493-31`)]);
  });

  it("★분석 흔적은 있는데 저장분이 없으면 **말한다**", async () => {
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);
    await waitFor(() =>
      expect(screen.getByTestId("registry-prior-analysis-notice")).toBeTruthy(),
    );
  });

  it("★무엇을 하면 되는지와 **비용**을 함께 말한다 — 조건 없는 '무료'가 아니다", async () => {
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);
    const box = await waitFor(() => screen.getByTestId("registry-prior-analysis-notice"));
    const t = box.textContent ?? "";
    expect(t).toContain("전체 분석");                       // 다음 조치
    expect(t).toContain("권리분석 보고서");                  // 무엇을 얻는지
    expect(t).toContain(`${FREE_REQUERY_DAYS}일`);           // 무과금 기간(상수 결속)
    expect(t).toMatch(/청구/);                              // ★돈이 든다는 사실을 감추지 않는다
  });

  it("★특이도 — 흔적이 **없는** 새 목록에는 뜨지 않는다", async () => {
    // 이 케이스가 없으면 "항상 고지" 구현도 위 두 단언을 만족한다(공짜 초록).
    seed([freshRow("r1", `${ADDR} 467-1`)]);
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);
    // 대조군: 목록 자체는 렌더됐다 — "0건" 이 '고지가 옳게 숨었다' 가 아니라
    //   '화면이 아예 안 그려졌다' 여도 통과하는 것을 막는다.
    await waitFor(() => expect(screen.getAllByTestId("registry-row-jibun").length).toBe(1));
    expect(screen.queryByTestId("registry-prior-analysis-notice")).toBeNull();
  });

  it("★특이도 — 저장분이 **있으면** 뜨지 않는다(그때는 보고서 버튼이 나온다)", async () => {
    seed([analyzedRow("r1", `${ADDR} 467-1`)]);
    useRegistryAnalysisStore.setState({
      byProject: {
        [PID]: [{
          jibun: `${ADDR} 467-1`, rowId: "r1",
          result: { status: "ok", ai: { generated: true } },
          savedAt: "2026-08-25T00:00:00.000Z",
        }],
      },
    });
    render(<RegistryAnalysisWorkspaceClient locale="ko" />);
    // 저장분이 복원되면 보고서 버튼이 실제로 나타난다 — 이것이 이 고지의 반대편이다.
    await waitFor(() => expect(screen.getByTestId("rights-report-pdf")).toBeTruthy());
    expect(screen.queryByTestId("registry-prior-analysis-notice")).toBeNull();
  });
});
