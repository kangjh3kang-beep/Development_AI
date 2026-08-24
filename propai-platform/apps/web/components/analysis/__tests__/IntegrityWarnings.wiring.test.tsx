/**
 * 법정초과 가드 경고 — **종합분석 화면 배선**(2026-08-24).
 *
 * 백엔드 `apply_legal_hotpath_guard` 가 실효 건폐·용적·층수의 법정초과를 검출해
 * 응답에 `integrity_warnings` 를 싣는데 **프론트 소비처가 0** 이었다.
 * 검출돼도 화면에 아무것도 안 나왔고, 가드가 붙이는 신뢰도 강등 문구는
 * *"— integrity_warnings 참조."* 라 **화면에 없는 것을 참조하라**고 말했다.
 *
 * ★소스 검사가 아니라 **실제 렌더**로 잠근다 — 소스 grep 만 남기면 주석 처리·필드
 *   바꿔치기 변이에 뚫린다(이 저장소가 반복해 데인 형태).
 *
 * ★픽스처가 두 모집단을 가른다: 검출 있음 / 없음. 후자에서 배너가 없어야
 *   "항상 그리는 구현"이 걸린다(공허한 초록 차단).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const routes = new Map<string, () => Promise<unknown>>();
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>((path: string) => {
  const h = routes.get(path);
  return h ? h() : Promise.resolve({});
});
function onPost(path: string, handler: () => Promise<unknown>) {
  routes.set(path, handler);
}
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(async () => ({ providers: [] }));

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));
vi.mock("@/components/precheck/SatongMapShell", () => ({ SatongMapShell: () => null }));

import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const ADDRESS = "경북 포항시 남구 호미곶면 대보리 산1-1";

/** 라이브 가드가 실제로 만드는 모양(`check_against_legal` 의 issues 항목). */
const ISSUE = {
  type: "층수제한초과",
  claim: "5층",
  severity: "high",
  note: "자연녹지지역은 4층(약 13m) 이하 제한이 있으나 5층이 제시됨 — 근거 미제시(할루시네이션 의심).",
};

function core(integrity: unknown[] | null) {
  return {
    address: ADDRESS,
    zone_type: "자연녹지지역",
    land_area_sqm: 152826,
    developability: "POSSIBLE",
    ai_interpretation: null,
    ai_interpretation_status: { status: "deferred", reason: "다음 단계" },
    integrity_warnings: integrity,
  };
}

async function runAnalysis(integrity: unknown[] | null) {
  onPost("/analysis/comprehensive", async () => core(integrity));
  useProjectContextStore.setState({
    siteAnalysis: { address: ADDRESS, zoneCode: "자연녹지지역" } as never,
  });
  render(<ComprehensiveAnalysisPanel />);
  const btn = await screen.findByRole("button", { name: /종합 분석 시작/ });
  await waitFor(() => expect(btn).not.toBeDisabled());
  await userEvent.click(btn);
}

beforeEach(() => {
  post.mockClear();
  routes.clear();
  onPost("/site-score/poi-infra", async () => ({ score: 60 }));
  onPost("/development-methods/scenarios", async () => ({}));
});

describe("종합분석 — 법정초과 가드 경고 배선", () => {
  it("★검출되면 화면에 나온다(백엔드 원문 그대로)", async () => {
    await runAnalysis([ISSUE]);
    const box = await screen.findByTestId("integrity-warnings");
    expect(box.textContent).toContain("층수제한초과");
    expect(box.textContent, "백엔드 note 원문이 안 실렸다").toContain("할루시네이션 의심");
    expect(box.textContent, "high 인데 근거 미확인 표기가 없다").toContain("근거 미확인");
  });

  it("★대조군 — 검출이 없으면 배너가 없다(항상 그리는 구현 차단)", async () => {
    await runAnalysis([]);
    // ★전제: 분석 자체는 끝났다(공허한 초록 방지 — 화면이 안 그려져서 없는 게 아니다).
    await waitFor(() => expect(post).toHaveBeenCalledWith("/analysis/comprehensive", expect.anything()));
    await waitFor(() => expect(screen.queryByTestId("integrity-warnings")).toBeNull());
  });
});
