/**
 * 건축계획 블록 정직 고지 락 — **라이브 실측(2026-08-24)에서 시작**.
 *
 * ## 무엇이 있었나 (프로덕션 `4t8t.net` · 역삼동 736 · 3필지·일반상업)
 *
 * 같은 페이지 안에 두 기준이 동시에 있었다:
 *
 *     건축계획       용적률 1,300% · 건폐율 80%   · 65층  · 연면적 1,911,962㎡
 *     건축 가능 범위  실효  158.2% · 건폐 25.7%  · 7~8층 · 연면적   256,336㎡
 *
 * **연면적 7.5배 차이**인데 건축계획 블록에는 **아무 고지도 없었다.**
 *
 * ★그런데 데이터는 이미 알고 있었다 — 저장된 스냅샷의
 * `designData.farIsEffective === false` 가 *"이 용적률은 실효가 아니라 법정상한 폴백"* 이라고
 * 말한다. `DesignStudio` 와 `MetricBar` 는 그 신호를 **이미 정직하게 표시**하는데
 * **이 형제 표면만 빠져 있었다.** 새 신호를 만들지 않고 같은 신호를 여기서도 읽는다.
 *
 * ## 왜 값 옆이어야 하는가
 *
 * 이 페이지의 공사비·수지 카드는 스스로 *"입력 근거: **설계 연면적** 활용"* 이라고 적어 둔다.
 * 즉 이 연면적이 곧 총사업비의 입력이다. 다른 블록에 있는 "한도 초과 검토"는 읽히지 않는다 —
 * **고지는 결함 옆에 있어야 한다.**
 *
 * ## 잠그는 것
 * 1. 한도를 넘으면 **연면적 값 옆에서** 초과 배수를 말한다
 * 2. `farIsEffective === false` 면 **법정상한 기준**임을 말한다
 * 3. **비교 근거가 없으면 초과라고 말하지 않는다**(없는 판정을 만들지 않는다)
 * 4. 대조군 — 한도 내/실효 기준이면 **아무 말도 붙지 않는다**
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { ProjectAnalysisSummary } from "@/components/projects/ProjectAnalysisSummary";
import { useProjectContextStore } from "@/store/useProjectContextStore";

// 네트워크 의존 자식·API 는 대체 — 이 테스트의 대상은 건축계획 블록의 고지다.
vi.mock("@/components/projects/BuildableEnvelopeCard", () => ({ BuildableEnvelopeCard: () => null }));
vi.mock("@/components/projects/SolarPlacementCard", () => ({ SolarPlacementCard: () => null }));
vi.mock("@/components/common/DevelopmentScenarioCard", () => ({ DevelopmentScenarioCard: () => null }));
vi.mock("@/components/common/AnalysisVerificationPanel", () => ({ AnalysisVerificationPanel: () => null }));
vi.mock("@/components/projects/ParcelExportButton", () => ({ ParcelExportButton: () => null }));
// 분석 캐시는 테스트 간 오염원이다 — 항상 미스로 두고 저장은 무시한다.
vi.mock("@/lib/analysis-fetch-cache", () => ({
  TTL_30D: 1, TTL_7D: 1, TTL_3D: 1,
  getCachedAnalysis: () => null,
  setCachedAnalysis: () => {},
}));

const { postMock, getMock } = vi.hoisted(() => ({ postMock: vi.fn(), getMock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, post: postMock, get: getMock } };
});

// 라이브 실측값 — 픽스처가 아니라 **프로덕션에서 읽은 수치**다.
const LIVE = {
  gfaDesign: 1_911_962,   // designData.totalGfaSqm
  gfaIntegrated: 257_326, // 통합분석 integrated_gfa_sqm
  far: 1300,
  bcr: 80,
  effFar: 158.2,
  effBcr: 25.7,
  area: 162_033,
};

/** 통합분석 응답을 제어한다(라이브 실측 형상 재현용). */
function mockIntegrated(payload: Record<string, unknown>) {
  postMock.mockImplementation((path: string) =>
    String(path).includes("/zoning/integrated-analysis")
      ? Promise.resolve(payload)
      : Promise.reject(new Error("no network in test")),
  );
}

function seed(design: Record<string, unknown>, opts: { effFar?: number | null; effBcr?: number | null; zoneMixed?: boolean } = {}) {
  act(() => {
    useProjectContextStore.setState({
      projectId: "p1",
      siteAnalysis: {
        address: "서울특별시 강남구 역삼동 736",
        landAreaSqm: LIVE.area,
        landAreaSqmTotal: LIVE.area,
        parcelCount: 3,
        // 통합분석 호출은 `parcelCount > 1 && parcels.length > 1` 에 게이트돼 있다.
        parcels: [
          { pnu: "1168010100107360000", address: "역삼동 736", areaSqm: 100_000, landCategory: "대", ownerType: "미확인", zoneCode: "일반상업지역" },
          { pnu: "1168010100107360001", address: "역삼동 736-1", areaSqm: 40_000, landCategory: "대", ownerType: "미확인", zoneCode: "일반상업지역" },
          { pnu: "1168010100107360002", address: "역삼동 736-2", areaSqm: 22_033, landCategory: "대", ownerType: "미확인", zoneCode: "제3종일반주거지역" },
        ],
        zoneCode: "일반상업지역",
        effectiveFarPct: opts.effFar === undefined ? LIVE.effFar : opts.effFar,
        effectiveBcrPct: opts.effBcr === undefined ? LIVE.effBcr : opts.effBcr,
        zoneMixed: opts.zoneMixed ?? true,
      },
      designData: design,
      costData: null, feasibilityData: null, esgData: null, complianceData: null,
    } as never);
  });
}

beforeEach(() => {
  postMock.mockReset();
  getMock.mockReset();
  // 통합분석은 이 테스트가 제어한다(기본은 미응답 — 비교 근거 없음).
  postMock.mockRejectedValue(new Error("no network in test"));
  getMock.mockRejectedValue(new Error("no network in test"));
});

/** 라벨로 DataField 행의 값 텍스트를 얻는다(없으면 null — 행 자체가 안 그려진 것). */
function fieldValue(label: string): string | null {
  const dts = Array.from(document.querySelectorAll("dt"));
  const hit = dts.find((el) => (el.textContent ?? "").trim().startsWith(label));
  const dd = hit?.parentElement?.querySelector("dd");
  return dd ? (dd.textContent ?? "").trim() : null;
}

describe("건축계획 블록 — 한도 초과와 기준을 값 옆에서 말한다", () => {
  it("★라이브 재현 — 실효 용적률로 계산한 한도를 넘으면 연면적 옆에 초과 배수를 적는다", async () => {
    seed({ buildingType: "공동주택", totalGfaSqm: LIVE.gfaDesign, floorCount: 65, bcr: LIVE.bcr, far: LIVE.far, farIsEffective: false });
    render(<ProjectAnalysisSummary locale="ko" />);

    // 전제 가드 — 건축계획 행이 실제로 렌더돼야 아래 단언이 의미를 갖는다.
    await waitFor(() => expect(fieldValue("연면적")).not.toBeNull());
    const gfa = fieldValue("연면적")!;
    expect(gfa).toContain("1,911,962");
    // 건축가능 = 162,033㎡ × 158.2% = 256,336㎡ → 약 7.5배
    expect(gfa).toContain("초과");
    expect(gfa).toMatch(/7\.\d배/);
  });

  it("★farIsEffective=false 면 '법정상한 기준(실효 아님)'을 값 옆에 적는다", async () => {
    seed({ totalGfaSqm: LIVE.gfaDesign, far: LIVE.far, farIsEffective: false });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("용적률")).not.toBeNull());
    const far = fieldValue("용적률")!;
    expect(far).toContain("1300%");
    expect(far).toContain("법정상한 기준");
  });

  it("★대조군 — farIsEffective=true 면 아무 말도 붙지 않는다", async () => {
    seed({ totalGfaSqm: 200_000, far: LIVE.effFar, farIsEffective: true });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("용적률")).not.toBeNull());
    expect(fieldValue("용적률")).not.toContain("법정상한");
  });

  it("★대조군 — 한도 안이면 연면적에 초과 문구가 없다", async () => {
    // 162,033 × 158.2% = 256,336 → 그 아래 값
    seed({ totalGfaSqm: 200_000, far: LIVE.effFar, farIsEffective: true });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("연면적")).not.toBeNull());
    expect(fieldValue("연면적")).not.toContain("초과");
  });

  it("★비교 근거가 없으면 초과라고 말하지 않는다(없는 판정을 만들지 않는다)", async () => {
    // 실효 용적률 미확보 + 통합분석 없음 → 건축가능 연면적을 산출할 수 없다.
    seed({ totalGfaSqm: LIVE.gfaDesign, far: LIVE.far, farIsEffective: false }, { effFar: null });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("연면적")).not.toBeNull());
    const gfa = fieldValue("연면적")!;
    expect(gfa).toContain("1,911,962");
    expect(gfa).not.toContain("초과");
  });

  it("건폐율도 실효를 넘으면 그 사실을 적는다(저장 플래그가 없어 값 비교로만 말한다)", async () => {
    seed({ totalGfaSqm: 200_000, bcr: LIVE.bcr, far: LIVE.effFar, farIsEffective: true });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("건폐율")).not.toBeNull());
    expect(fieldValue("건폐율")).toContain("실효 25.7% 초과");
  });
});


/**
 * 센티널 유출 락 — **내부 코드가 용도지역 이름 자리에 나왔다**(라이브 실측 2026-08-24).
 *
 *     화면:   용도지역   `mixed_review_required` 외 (혼재·분리검토)
 *     API:    dominant_zone="mixed_review_required" · dominant_basis="area_weighted"
 *
 * 프론트는 **`dominant_basis`** 만 센티널인지 봤는데 백엔드는 **`dominant_zone` 값**에 넣는다
 * (#787 이 확립한 "임의 단일화 거부" 신호). 검사한 필드가 달랐다.
 * 마침 `zoneMixed` 가 true 라 뒷말만 붙어 **우연히** 혼재 표기가 됐을 뿐,
 * `zoneMixed` 가 false 였다면 센티널이 **맨몸으로** 나온다.
 *
 * ★센티널일 때 대표 필지 용도지역으로 대체하지 않는다 — 그것이 #787 이 방금 고친
 *   "대표를 우세라 부르는" 결함이다. **이름을 짓지 않고 판정하지 않았다고 말한다.**
 */
describe("용도지역 — 내부 센티널이 화면에 새지 않는다", () => {
  async function renderWithZone(payload: Record<string, unknown>, zoneMixed: boolean) {
    mockIntegrated(payload);
    seed({ totalGfaSqm: 200_000, far: LIVE.effFar, farIsEffective: true }, { zoneMixed });
    render(<ProjectAnalysisSummary locale="ko" />);
    await waitFor(() => expect(fieldValue("용도지역")).not.toBeNull());
    return fieldValue("용도지역")!;
  }

  it("★라이브 재현 — dominant_zone 이 센티널이면 그 문자열을 화면에 쓰지 않는다", async () => {
    const v = await renderWithZone(
      { parcel_count: 3, dominant_zone: "mixed_review_required", dominant_basis: "area_weighted" },
      true,
    );
    expect(v).not.toContain("mixed_review_required");
    expect(v).toContain("혼재");
    expect(v).toContain("판정하지 않았습니다");
  });

  it("★zoneMixed=false 여도 센티널이 맨몸으로 나오지 않는다(우연에 기대지 않는다)", async () => {
    const v = await renderWithZone(
      { parcel_count: 3, dominant_zone: "mixed_review_required", dominant_basis: "area_weighted" },
      false,
    );
    expect(v).not.toContain("mixed_review_required");
    expect(v).toContain("혼재");
  });

  it("★대조군 — 진짜 용도지역이 오면 그대로 보여 준다(무엇이든 가리는 처리가 아니다)", async () => {
    const v = await renderWithZone(
      { parcel_count: 3, dominant_zone: "자연녹지지역", dominant_basis: "area_weighted" },
      false,
    );
    expect(v).toBe("자연녹지지역");
  });

  it("★센티널일 때 대표 용도지역으로 **대체하지 않는다**(#787 이 고친 결함 재발 방지)", async () => {
    const v = await renderWithZone(
      { parcel_count: 3, dominant_zone: "mixed_review_required", dominant_basis: "area_weighted" },
      true,
    );
    // store 의 대표 zoneCode 는 "일반상업지역" 이다 — 그 이름을 빌려 쓰면 안 된다.
    expect(v).not.toContain("일반상업지역");
  });
});
