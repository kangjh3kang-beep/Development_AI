/**
 * ★★**렌더 락** — 헬퍼가 아니라 **화면**을 태운다.
 *
 * 【왜 생겼나 · 독립 적대 리뷰 실측 2026-09-03】
 * 형제 락(`billing-fee-keys-parity`)은 **순수 헬퍼만** 태웠다. 그래서 렌더에서
 * **원래 결함으로 되돌리는 변이 두 종이 전부 SURVIVED** 였다:
 *
 *     flatFeeKeys(cfg.service_fees)**.slice(0, 3)**.map(…)              → 5 passed
 *     …**.filter((k) => ["project_create","land_analysis",…].includes(k))** → 5 passed
 *
 * 둘 다 `flatFeeKeys(cfg.service_fees)` 문자열을 남기고 `setSvc(k, v)` 도 그대로라
 * 소스 검사 축을 **모두 비껴간다.** ★내가 커밋에 *"하드코딩 복귀 CAUGHT"* 라고 적은 것은
 * `setSvc("리터럴")` 형태에만 참이었다 — **파생의 축이 헬퍼인데 결함은 렌더에 산다.**
 *
 * 【이 락】서버 응답을 목킹해 페이지를 렌더하고, **그려진 요율 칸 수 == 응답의 평면 숫자 키 수**
 * 를 단언한다. 위 두 변이는 여기서 즉시 빨개진다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const putMock = vi.fn();
// ★페이지는 `apiClient.get("/billing/admin/config")` 하나로 불러오고, 401/403 일 때만
//   `denied` 로 간다(`useIsAdmin` 같은 훅은 **없다** — 첫 시도에서 내가 지어냈다).
//   ★`ApiClientError` 는 **실제 모듈 것을 그대로** 쓴다 — 가짜로 덮으면 페이지의
//     `e instanceof ApiClientError` 분기가 달라져 **다른 코드를 태우게 된다**.
vi.mock("@/lib/api-client", async (orig) => {
  const actual = await (orig as () => Promise<Record<string, unknown>>)();
  return { ...actual, apiClient: { ...(actual.apiClient as object), get: (...a: unknown[]) => getMock(...a), put: (...a: unknown[]) => putMock(...a) } };
});

import Page, { flatFeeKeys } from "@/app/[locale]/(dashboard)/settings/billing/page";

/**
 * ★**라이브 응답에서 파생한 형상**(2026-09-03 `GET /billing/admin/config` 실측).
 *
 * ★첫 시도에서 내가 형상을 **지어냈다** — `free_tier: { land_analysis: {…} }` 로 썼는데
 *   실제는 `free_tier.analysis_quota.{free,guest}` · `analysis_fee.{free,guest}` 였고,
 *   페이지가 `Cannot read properties of undefined (reading 'free')` 로 죽었다.
 *   ★픽스처 형상도 **원문에서 파생**해야 한다 — 기억에서 쓰면 다른 코드를 태운다.
 */
const CFG = {
  budget_ratio: 0.6,
  tiers: {
    power: { fee_krw: 124500, base_quota_krw: 12250, overage_margin_pct: 50, label: "파워" },
  },
  service_fees: {
    project_create: 2000, land_analysis: 2000, sales_provision: 50000,
    photoreal_render: 3000, concept_render: 0,
    registry_issue: 1200, registry_analysis: 2000, bulk_parcel_per_unit: 0,
    stages: { site_analysis: 2000, design: 2000, cost: 2000, feasibility: 2000, tax: 2000, esg: 2000, report: 2000 },
    analysis_modules: {},
  },
  free_tier: {
    analysis_quota: { free: 3, guest: 1 },
    analysis_fee: { free: 5000, guest: 10000 },
  },
};

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue(JSON.parse(JSON.stringify(CFG)));
});

/** 요율 칸 = `Field` 가 그리는 숫자 입력. 라벨이 아니라 **입력 개수**로 센다. */
function feeInputCount(): number {
  return document.querySelectorAll("input.cc-num").length;
}

/** 요율 입력 칸 = `Field` 가 그리는 `input.cc-num`. 라벨이 아니라 **입력 개수**로 센다. */
function numInputs(): number {
  return document.querySelectorAll("input.cc-num").length;
}
/** 화면 전체 텍스트(공백 정규화) — 라벨은 요소 경계로 쪼개져 있어 `findByText` 로는 못 잡는다. */
function bodyText(): string {
  return (document.body.textContent ?? "").replace(/\s+/g, " ");
}
/** 페이지를 그리고 로드가 끝날 때까지 기다린다. */
async function renderPage() {
  render(<Page />);
  await waitFor(() => expect(getMock).toHaveBeenCalled());
  await waitFor(() => expect(bodyText()).toContain("서비스 사용료"));
}

describe("★렌더 락 — 화면이 응답의 요율 키를 전부 그린다", () => {
  it("공허 방지 — 페이지가 실제로 그려졌고 칸이 0이 아니다", async () => {
    await renderPage();
    expect(numInputs(), "★입력 칸이 0 — 아래 단언이 공허해진다").toBeGreaterThan(0);
  });

  it("★서비스 사용료 라벨이 응답의 평면 숫자 키만큼 전부 있다", async () => {
    await renderPage();
    const want = flatFeeKeys(CFG.service_fees as Record<string, unknown>);
    expect(want.length, "★픽스처가 8키가 아니다 — 모집단이 바뀌었다").toBe(8);
    const body = bodyText();
    const missing = want.filter((k) => !body.includes(LABEL[k]));
    expect(missing, `★화면에 없는 요율 칸 — 관리자가 그 금액을 못 바꾼다: ${missing.join(", ")}`).toEqual([]);
  });

  it("★★칸 수가 응답 키 수와 **같다** — 잘라내면(.slice) 빨개진다", async () => {
    await renderPage();
    // 요율 칸 = 전체 숫자 입력 − (플랜 3 + 단계 1 + 무료정책 4). 픽스처를 그렇게 짰다.
    const OTHER = 3 + Object.keys(CFG.service_fees.stages).length + 4;
    const want = flatFeeKeys(CFG.service_fees as Record<string, unknown>).length;
    expect(numInputs(), `★요율 칸 수가 응답 키 수(${want})와 다르다 — 잘라내거나 더 그렸다`)
      .toBe(want + OTHER);
  });

  it("★중첩 묶음은 평면 칸으로 안 그린다(특이도)", async () => {
    await renderPage();
    expect(bodyText()).not.toContain("analysis_modules");
  });

  // ★부채 — 이 PR 이 고치지 않은 같은 클래스 2축(적대 리뷰 F3). 초록 안에서 보이게 남긴다.
  it.todo("★부채: analysis_modules 를 관리자가 화면에서 바꿀 수 있어야 한다(현재 UI 0건)");
  it.todo("★부채: budget_ratio 를 관리자가 화면에서 바꿀 수 있어야 한다(현재 UI 0건)");
});

const LABEL: Record<string, string> = {
  project_create: "프로젝트 생성", land_analysis: "토지분석(구독자)", sales_provision: "분양현장 생성",
  photoreal_render: "실사 렌더링", concept_render: "컨셉 렌더링",
  registry_issue: "등기부 발급", registry_analysis: "등기부 권리분석",
  bulk_parcel_per_unit: "대량 다필지 배치(필지당)",
};
