import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LandIntelligencePanel } from "@/components/projects/LandIntelligencePanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/**
 * 면적 기준(basis) **렌더 경로** 락 — R1.
 *
 * ■ 무엇을 막는가 (소스 실측)
 *   이 패널은 `/zoning/analyze` 응답의 `land_area_sqm` 을 그대로 표시했다. 그 응답은
 *   **대표 1필지** 분석이라, 다필지 부지에서 이 패널은 대표면적을 보여 주고 통합 경로를 쓰는
 *   다른 패널(사업개요)은 통합면적을 보여 준다 — 같은 이름으로 다른 값이 나온다.
 *   더 나쁜 것은 그 아래 줄이다: `추정 토지가액 = 공시지가 × **대표**면적` 이라
 *   통합 부지의 토지가액을 **통합/대표 면적비만큼 과소표시**했다(돈이 걸린 결함).
 *
 * ■ 출처 라벨 (정직 표기 — 실수 #39 의 처방)
 *   아래 상수 `REP_AREA`/`TOTAL_AREA` 는 **동작을 재기 위한 픽스처**이지 특정 사용자 화면의
 *   관측 기록이 아니다. 이 파일이 잠그는 것은 *"같은 입력에 이 패널이 무엇을 그리는가"* 이며,
 *   그것은 이 테스트가 **직접 태워서** 확인한다. 인계 서술을 실측으로 승격시키지 않는다.
 *
 * ■ 왜 순수함수 테스트만으로는 부족한가
 *   `lib/site-area.test.ts` 가 리졸버를 잠그지만, **패널이 그 리졸버를 실제로 쓰는지**는
 *   잠그지 못한다. 실제로 변이 검증에서 `landAreaSqm: resolvedArea.valueSqm ?? …` 줄을
 *   지워도 순수 테스트는 전부 초록이었다(배선 무잠금). 그래서 **렌더 결과**를 본다.
 *
 * ■ 변이 검증 후 남은 생존 — **의도적 비잠금**이므로 여기 적어 둔다(점수 부풀리기 방지)
 *   · `className="…"` 문자열 변경(4건) — 색상·간격은 잠그지 않는다(디자인 변경마다 빨강이 되면
 *     아무도 게이트를 안 본다). 값·기준·라벨 **문구**는 위 단언들이 잠근다.
 *   · `status: charArea >= 200 ? "safe" : "warning"` — 칩 **색상**만 정한다(값 아님).
 *   · `LandAreaBasis` 유니언 멤버 문자열 — 타입 층이라 `tsc --noEmit` 이 잡는다(CI 게이트).
 *   · `site-analysis/page.tsx` 2줄 — 아래 `it.todo` 로 부채를 명시했다(무잠금 ≠ 미수정).
 *
 * ■ 대조군
 *   단일필지 상태를 함께 태운다. "무엇이든 잡는" 판별기와 "아무것도 안 잡는" 판별기는
 *   둘 다 초록이 되므로, 두 모집단이 **서로 다른 화면**을 내는지 확인해야 락이 성립한다.
 */

// 네트워크/AI 의존 제거 — 이 테스트의 대상은 면적 기준 배선이다.
vi.mock("@/lib/ai-analyze-client", () => ({
  useAIReady: () => ({ isReady: false }),
  useAIAnalyze: () => ({ mutate: vi.fn(), data: null, isPending: false, error: null }),
}));
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: vi.fn().mockRejectedValue(new Error("no network in test")),
    get: vi.fn().mockRejectedValue(new Error("no network in test")),
    postV2: vi.fn().mockRejectedValue(new Error("no network in test")),
  },
}));

const ADDRESS = "충청남도 천안시 동남구 모산동 123-1";
const PRICE_PER_SQM = 1_000_000;
// 대표 1필지 면적 — 백엔드 /zoning/analyze 가 돌려주는 값(통합이 아니다).
const REP_AREA = 3836;
// 7필지 통합면적 — store SSOT(landAreaSqmTotal).
const TOTAL_AREA = 164823;

// zoning 응답은 캐시를 통해 동기적으로 주입한다(비동기 대기 없이 결정적으로 렌더).
vi.mock("@/lib/analysis-fetch-cache", () => ({
  TTL_30D: 1, TTL_7D: 1, TTL_3D: 1,
  setCachedAnalysis: vi.fn(),
  getCachedAnalysis: (key: string) =>
    key.startsWith("zoning:")
      ? {
          address: ADDRESS,
          pnu: "4413110300101230001",
          zone_type: "제1종일반주거지역",
          zone_limits: { max_bcr_pct: 60, max_far_pct: 200, max_height_m: null, zone_key: "1R", legal_basis: "국토계획법 시행령 제85조" },
          land_area_sqm: REP_AREA,
          land_category: "대",
          official_price_per_sqm: PRICE_PER_SQM,
        }
      : null,
}));

/**
 * 공시지가(토지가액) 블록은 **탭이 활성일 때만** 렌더된다. 조건부 렌더 요소는 그 상태를
 * 만들어서 검사해야 한다 — 탭을 안 열고 "위반 0"을 얻으면 공허한 초록이다(이 저장소 4회 재발).
 */
function openPriceTab() {
  fireEvent.click(screen.getByRole("button", { name: "공시지가" }));
}

function seed(parcelCount: number, parcels: number, total: number | null) {
  useProjectContextStore.setState({ siteAnalysis: null } as never);
  const ctx = useProjectContextStore.getState();
  ctx.setProject("p1", "모산동 통합부지", "active");
  ctx.updateSiteAnalysis({
    address: ADDRESS,
    zoneCode: "1R",
    landAreaSqm: REP_AREA,
    ...(total != null ? { landAreaSqmTotal: total } : {}),
    parcelCount,
    parcels: Array.from({ length: parcels }, (_, i) => ({
      pnu: `p${i}`, address: `모산동 123-${i + 1}`,
      areaSqm: Math.round(TOTAL_AREA / 7), landCategory: "대", ownerType: "미확인", zoneCode: "1R",
    })),
  } as never);
}

beforeEach(() => {
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("LandIntelligencePanel — 면적 기준 렌더 배선", () => {
  it("★다필지(7필지 픽스처) — 대표면적이 아니라 통합면적을 보여 주고 기준을 밝힌다", () => {
    seed(7, 7, TOTAL_AREA);
    render(<LandIntelligencePanel projectId="p1" data={{ address: ADDRESS, pnu: "4413110300101230001" }} />);

    // 전제 가드(공허한 초록 방지) — 기준 배지가 실제로 DOM 에 있어야 아래 단언이 의미를 갖는다.
    const badge = document.querySelector('[data-area-basis]');
    expect(badge, "기준 배지가 렌더되지 않았다 — 배선이 끊겼거나 hasData 가 false 다").not.toBeNull();
    expect(badge!.getAttribute("data-area-basis")).toBe("integrated");
    expect(badge!.textContent).toContain("통합 7필지 기준");

    // 표시 면적 = 통합. 대표면적이 그대로 나오면 이 락이 죽는다.
    const body = document.body.textContent ?? "";
    expect(body).toContain(TOTAL_AREA.toLocaleString());
    expect(body).not.toContain(`${REP_AREA.toLocaleString()}m²`);

    // ★이 패널에서 면적을 보여 주는 **셋째** 지점 — 특성표의 '면적' 행.
    //   요약줄·토지가액만 고치고 여기를 놓쳤던 것이 이번 라운드의 실제 누출이다.
    //   음성 단언("3,836 이 없다")만으로는 이 행을 **통째로 지워도** 통과하므로 양성으로 못박는다.
    expect(
      screen.getByText(`${TOTAL_AREA.toLocaleString()}m² (통합 7필지)`),
      "특성표 '면적' 행이 통합면적·기준과 함께 렌더되지 않았다",
    ).toBeTruthy();
  });

  it("★추정 토지가액이 **통합면적**으로 계산되고 개략치임을 고지한다(대표면적 과소표시 회귀 락)", () => {
    seed(7, 7, TOTAL_AREA);
    render(<LandIntelligencePanel projectId="p1" data={{ address: ADDRESS, pnu: "4413110300101230001" }} />);

    openPriceTab();
    const line = document.querySelector("[data-land-value-basis]");
    expect(line, "토지가액 줄이 렌더되지 않았다").not.toBeNull();
    expect(line!.getAttribute("data-land-value-basis")).toBe("integrated");
    // 통합면적으로 곱했는가 — 대표면적으로 곱한 값이 나오면 죽는다.
    expect(line!.textContent).toContain((PRICE_PER_SQM * TOTAL_AREA).toLocaleString());
    expect(line!.textContent).not.toContain((PRICE_PER_SQM * REP_AREA).toLocaleString());
    // 필지별 공시지가 합산이 아님을 밝힌다(정밀도 위장 금지).
    expect(line!.textContent).toContain("개략치");
  });

  it("★대조군(음성) — 단일필지에서는 기준 배지도 개략치 고지도 붙이지 않는다", () => {
    seed(1, 1, null);
    render(<LandIntelligencePanel projectId="p1" data={{ address: ADDRESS, pnu: "4413110300101230001" }} />);

    // 단일필지는 덧붙일 말이 없다 — 여기서도 배지가 뜨면 '무엇이든 잡는' 판별기다.
    expect(document.querySelector("[data-area-basis]")).toBeNull();
    openPriceTab();
    const line = document.querySelector("[data-land-value-basis]");
    expect(line, "토지가액 줄 자체는 단일필지에서도 렌더돼야 한다(대상 존재 확인)").not.toBeNull();
    expect(line!.getAttribute("data-land-value-basis")).toBe("single");
    expect(line!.textContent).not.toContain("개략치");
    // 단일필지 면적은 대표값 그대로가 맞다.
    expect(line!.textContent).toContain(REP_AREA.toLocaleString());
    // 특성표도 군더더기 없이 값만 — 단일필지에 "(통합 N필지)"가 붙으면 거짓 라벨이다.
    expect(screen.getByText(`${REP_AREA.toLocaleString()}m²`)).toBeTruthy();
  });

  it("★다필지인데 통합면적 미확보 — 값은 대표면적이되 '대표필지 1곳'임을 고지한다", () => {
    seed(7, 0, null);
    render(<LandIntelligencePanel projectId="p1" data={{ address: ADDRESS, pnu: "4413110300101230001" }} />);

    const badge = document.querySelector("[data-area-basis]");
    expect(badge).not.toBeNull();
    expect(badge!.getAttribute("data-area-basis")).toBe("representative");
    expect(badge!.textContent).toContain("대표필지 1곳의 면적");
    // 특성표도 강등 상태를 라벨로 말한다(통합인 척하지 않는다).
    expect(screen.getByText(`${REP_AREA.toLocaleString()}m² (대표필지)`)).toBeTruthy();
  });
});

/**
 * ★남은 무잠금(부채) — 커밋 메시지에만 적으면 드러나지 않으므로 초록 안에 남긴다.
 *
 * `projects/[id]/site-analysis/page.tsx` 도 같은 리졸버로 배선했지만(요약줄 기준 고지 ·
 * AVM 카드 `areaSqm`), 그 페이지는 라우트 셸·다수 자식 컴포넌트·네트워크 의존이 얽혀 있어
 * 렌더 경로를 태우는 테스트가 아직 없다. 변이 검증에서 해당 두 줄은 **생존**했다.
 * 공용 헬퍼(`resolveLandArea`·`landAreaBasisNote`)는 순수 테스트로 잠겨 있으므로 값 자체는
 * 안전하나, **페이지가 그 헬퍼를 부른다는 사실**은 아직 잠기지 않았다 — 그 구분을 흐리지 않는다.
 */
describe("site-analysis 페이지 면적 기준 배선 — 렌더 경로 무잠금(부채)", () => {
  it.todo("요약줄이 resolveLandArea 기준 고지를 렌더한다 (page.tsx:1572 변이 생존)");
  it.todo("AVM 카드가 areaResolved.valueSqm 을 받는다 (page.tsx:1680 변이 생존)");
});
