/**
 * 연결결산 **보류 가시화** 렌더 락 — #838 이 API 까지만 하고 남긴 소비처를 잠근다.
 *
 * ★왜 소스 문자열 검사가 아니라 렌더 테스트인가:
 *   앞 세션에서 문자열 락이 **세 번 뚫렸다**(증가문을 `pass` 로 바꿔도 문자열은 남는다 ·
 *   파일이 SyntaxError 인데 문자열 검사는 참이다). 렌더 테스트는 **문법·배선·표면**을
 *   한 번에 태운다 — 컴포넌트가 안 그리면 문자열이 아무리 있어도 빨개진다.
 *
 * ★라이브 실측(2026-08-26 · admin 테넌트 /api/v1/sales/projection/accounting-rollup):
 *   현장 **13곳 = balanced null 11 · true 2 · false 0**. 응답엔 reconcile_failed_count=0 만
 *   있어 화면이 **"정합 실패 0"으로 깨끗해 보였다.** '불일치 0'과 '확인 못 함 11'은 다른 사실이다.
 *
 * 락 구성 — 탐지 3 · 특이도 3 · 배선 1:
 *   D1 보류 배너가 **수까지** 그린다            D2 보류 0이면 배너 없음(공허진리 가드 동반)
 *   D3 보류만 있을 때 **불일치 배너는 안 뜬다**(축 비혼입)   D4 불일치 축은 그대로 산다(형제 회귀)
 *   D5 ★드릴다운이 **백엔드 사유 문구**를 그린다(관리 ▾ 클릭 = 실경로)
 *   D6 사유 미탑재(구버전 응답)면 폴백 문구      D7 balanced=true 는 보류로 안 읽는다
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

type Recon = {
  balanced: boolean | null; balanced_basis?: string; balanced_absent?: string;
  discrepancies?: { key: string; detail?: string }[];
};
// 테스트가 응답을 갈아 끼운다(고정 픽스처가 두 모집단을 못 가르는 것을 피한다).
const fx: { withheld: number; failed: number; recon: Recon } = {
  withheld: 0, failed: 0, recon: { balanced: null },
};

const SITE = { site_id: "S-1", site_name: "테스트현장", status: "OPEN", visitors: 1, contracts_cnt: 1, contract_amt: 1000, sold_ratio: 0.5, commission_paid: 0, commission_due: 0 };

vi.mock("@/lib/salesApi", () => ({
  won: (n: number) => `${(n ?? 0).toLocaleString()}원`,
  // 전역(테넌트) 조회 — 요약/롤업 두 경로를 경로문자열로 가른다.
  salesGlobal: {
    get: (path: string) => {
      if (path.includes("summary")) return Promise.resolve([SITE]);
      return Promise.resolve({
        consolidated: {
          revenue: 100, cost_total: 10, commission: 5, profit_estimate: 85, by_type: [],
          complete: true, failed_count: 0, partial: false,
          reconcile_failed_count: fx.failed,
          reconcile_withheld_count: fx.withheld,
        },
        sites: [], errors: [], note: "테스트 노트",
      });
    },
  },
  // 현장 드릴다운 — 관리 ▾ 클릭 시 마운트되는 SiteManagePanel 이 부른다.
  salesApi: () => ({
    // ★드릴다운이 부르는 **세 경로 전부**에 계약을 지키는 응답을 준다(파생형으로 수집:
    //   site-detail · payroll?ym= · ad/roi). 종전엔 나머지를 `{}` 로 뭉갰는데,
    //   `Payroll.staff` 는 타입상 **필수**라 PayrollAdSection 이 `pay.staff.length` 에서
    //   던졌다 — 단언은 통과하는데 **vitest 가 unhandled error 로 exit 1**(=CI 빨강).
    //   ★스텁이 실제 계약보다 좁으면 그 필드를 쓰는 코드가 **테스트에서만** 터진다(§33).
    get: (path: string) => {
      if (path.includes("site-detail")) {
        return Promise.resolve({
          staff_assigned: 0, contracts: 0, revenue: 0, commission: 0, visitors: 0,
          attendance_today: 0, ad_budget: 0, accounting: { by_type: [], cost_total: 0 },
          profit_estimate: 0, reconciliation: fx.recon,
        });
      }
      if (path.includes("payroll")) {
        return Promise.resolve({
          year_month: "2026-08", staff: [], headcount: 0, total_payroll: 0,
          total_gross: 0, total_deduction: 0, total_net: 0, note: "",
        });
      }
      if (path.includes("ad/roi")) {
        return Promise.resolve({
          budget: 0, spend: 0, leads: 0, visitors: 0, contracts: 0,
          cost_per_lead: 0, cost_per_visitor: 0, cost_per_contract: 0, note: "",
        });
      }
      return Promise.resolve({});
    },
    post: vi.fn().mockResolvedValue({}),
  }),
}));

import DeveloperProjection from "@/components/sales/DeveloperProjection";

/** 롤업 절이 실제로 렌더됐는지 — 공허진리 가드(대상 0개면 "위반 0"은 무의미하다). */
async function rollupRendered() {
  await screen.findByText("테스트 노트");
}

beforeEach(() => { fx.withheld = 0; fx.failed = 0; fx.recon = { balanced: null }; });

describe("연결결산 보류 가시화(#838 소비처)", () => {
  it("D1 탐지 — 보류 현장 수를 배너에 **수까지** 그린다", async () => {
    fx.withheld = 11;
    render(<DeveloperProjection />);
    const b = await screen.findByText(/독립 대사 확인 불가 · 현장/);
    // ★수를 못 박는다. "배너가 떴다"만 보면 상수 배너로 바꿔도 초록이다.
    expect(b.textContent).toContain("11곳");
  });

  it("D2 특이도 — 보류 0이면 배너를 그리지 않는다(정상 운영을 결함으로 신고 금지)", async () => {
    fx.withheld = 0;
    render(<DeveloperProjection />);
    await rollupRendered();               // ← 공허진리 가드
    expect(screen.queryByText(/독립 대사 확인 불가 · 현장/)).toBeNull();
  });

  it("D3 축 비혼입 — 보류만 있을 때 **불일치** 배너는 뜨지 않는다", async () => {
    fx.withheld = 11; fx.failed = 0;
    render(<DeveloperProjection />);
    await screen.findByText(/독립 대사 확인 불가 · 현장/);
    expect(screen.queryByText(/독립 대사 불일치 · 현장/)).toBeNull();
  });

  it("D4 형제 회귀 — 불일치 축은 그대로 산다(보류를 넣다 실패축을 죽이지 않았다)", async () => {
    fx.failed = 2; fx.withheld = 0;
    render(<DeveloperProjection />);
    const b = await screen.findByText(/독립 대사 불일치 · 현장/);
    expect(b.textContent).toContain("2곳");
    expect(screen.queryByText(/독립 대사 확인 불가 · 현장/)).toBeNull();
  });

  it("D5 ★배선 — 드릴다운이 **백엔드가 말한 사유**를 그린다(화면이 지어내지 않는다)", async () => {
    // 고유 문구 — 화면 상수와 절대 겹치지 않게 만든다(부분일치 위양성 차단).
    const BASIS = "ZZ고유사유토큰: 분납 약정표와 SIGNED 계약총액이 모두 비어 있습니다";
    fx.recon = { balanced: null, balanced_basis: BASIS, balanced_absent: "insufficient_coverage" };
    render(<DeveloperProjection />);
    fireEvent.click(await screen.findByText("관리 ▾"));   // ← 실경로: 패널 마운트 → site-detail 조회
    await waitFor(() => expect(screen.getByText(BASIS)).toBeTruthy());
  });

  it("D6 특이도 — 사유 미탑재(구버전 응답)면 폴백 문구를 쓴다", async () => {
    fx.recon = { balanced: null };
    render(<DeveloperProjection />);
    fireEvent.click(await screen.findByText("관리 ▾"));
    await waitFor(() => expect(screen.getByText(/대조할 근거가 없습니다/)).toBeTruthy());
  });

  it("D8 경계 — balanced 키가 **없으면**(undefined) 거짓 불일치 경보를 내지 않는다", async () => {
    // ★백엔드가 키를 빠뜨리면 JSON 에서 undefined 가 된다. 타입은 필수라 선언하지만
    //   **런타임은 그 타입을 지키지 않는다**(tsc 통과 실측). 종전엔 최종 else 로 떨어져
    //   항목 0개짜리 빨간 "불일치" 배너가 떴다 — 정상 현장을 결함으로 신고한 것이다.
    fx.recon = {} as Recon;
    render(<DeveloperProjection />);
    fireEvent.click(await screen.findByText("관리 ▾"));
    await waitFor(() => expect(screen.getByText(/대조할 근거가 없습니다/)).toBeTruthy());
    expect(screen.queryByText(/독립 대사 불일치/)).toBeNull();
  });

  it("D7 축 — balanced=true 는 보류로 읽지 않는다", async () => {
    fx.recon = { balanced: true };
    render(<DeveloperProjection />);
    fireEvent.click(await screen.findByText("관리 ▾"));
    await waitFor(() => expect(screen.getByText(/독립 대사 통과/)).toBeTruthy());
    expect(screen.queryByText(/독립 대사 확인 불가/)).toBeNull();   // 드릴다운 표면
  });
});
