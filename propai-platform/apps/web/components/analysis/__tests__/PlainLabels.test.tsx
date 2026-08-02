/**
 * W4-1 회귀락 — 원시 코드 미노출 + '다음 행동'은 백엔드 근거로만.
 *
 * 잠그는 것 두 가지:
 *  1. 개발자용 코드(`NEEDS_OFFICIAL_SURVEY`)가 화면에 그대로 나오지 않는다. 라벨 SSOT는 이미
 *     있었는데 이 경로만 안 타서 코드가 노출되고 있었다.
 *  2. "이 제약을 푸는 방법" 문장은 **백엔드가 준 필드에서만** 온다. 프론트가 지어내면
 *     필지 유형이 다를 때 정반대 조언이 나간다(임야=산지전용허가 vs 맹지=진입도로 확보).
 *     → 백엔드 필드를 비우면 문장이 사라져야 한다(변이로 확인).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { developabilityLabel } from "@/lib/zoning-ssot";

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

/** 라이브 프로덕션 응답에서 그대로 가져온 임야 factor(2026-08-02 실측). */
const FOREST_FACTOR = {
  category: "임야(산지)",
  developability: "NEEDS_OFFICIAL_SURVEY",
  resolution_paths: ["산지전용허가 + 대체산림자원조성비 납부", "경사도·표고·입목축적 기준 충족"],
  permit_prerequisites: ["산지전용허가", "산림조사서·평균경사도조사서 작성(산림기술사 등 자격)"],
  alternatives: ["전용비용 반영", "기준 초과 구역 제외(부분개발)"],
};

function coreWith(factors: unknown[], developability = "NEEDS_OFFICIAL_SURVEY") {
  return {
    address: ADDRESS,
    zone_type: "보전관리지역",
    land_area_sqm: 152826,
    developability,
    special_parcel: {
      is_special: true,
      developability,
      honest_disclosure: "공식 산림조사가 필요합니다.",
      factors,
    },
    ai_interpretation: null,
    ai_interpretation_status: { status: "deferred", reason: "다음 단계" },
  };
}

async function runAnalysis() {
  useProjectContextStore.setState({
    siteAnalysis: { address: ADDRESS, zoneCode: "보전관리지역" } as never,
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
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

/* ── 라벨 SSOT ── */

describe("developabilityLabel — 미등재 코드에 이름을 지어내지 않는다", () => {
  it("등재 코드는 한국어 라벨, known=true", () => {
    expect(developabilityLabel("NEEDS_OFFICIAL_SURVEY")).toEqual({
      text: "공식 산림조사 필요(참고안 — 확정 아님)",
      known: true,
    });
    // ★UNKNOWN은 '제약 없음'이 아니라 '못 봤음'이다 — 문구가 그 뜻을 담아야 한다.
    expect(developabilityLabel("UNKNOWN").known).toBe(true);
    expect(developabilityLabel("UNKNOWN").text).toMatch(/판정 불가/);
  });

  it("미등재 코드는 원문 + known=false(소비처가 '설명 준비 중'을 붙이게)", () => {
    expect(developabilityLabel("FUTURE_GATE_X")).toEqual({ text: "FUTURE_GATE_X", known: false });
    expect(developabilityLabel(null)).toEqual({ text: "", known: false });
  });
});

/* ── 화면: 원시 코드 미노출 ── */

describe("배선 — 개발자용 코드가 화면에 나오지 않는다", () => {
  it("★특이부지 배지가 원시 enum 대신 한국어 라벨을 보여준다", async () => {
    onPost("/analysis/comprehensive", async () => coreWith([FOREST_FACTOR]));
    await runAnalysis();
    await waitFor(() =>
      expect(screen.getByText(/공식 산림조사 필요/)).toBeTruthy(),
    );
    // 원시 코드는 본문 어디에도 없어야 한다(title 속성에는 남겨 개발자 추적은 가능).
    expect(screen.queryByText("NEEDS_OFFICIAL_SURVEY")).toBeNull();
  });

  it("미등재 코드는 지어내지 않고 원문 + '설명 준비 중'으로 표기한다", async () => {
    onPost("/analysis/comprehensive", async () =>
      coreWith([{ ...FOREST_FACTOR, developability: "FUTURE_GATE_X" }], "FUTURE_GATE_X"),
    );
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/설명 준비 중/)).toBeTruthy());
  });
});

/* ── 화면: '다음 행동'은 백엔드 근거로만 ── */

describe("표면 — 해결 절차를 프론트가 지어내지 않는다", () => {
  it("백엔드가 준 절차·요건·대안을 그대로 보여준다", async () => {
    onPost("/analysis/comprehensive", async () => coreWith([FOREST_FACTOR]));
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/이 제약을 푸는 방법/)).toBeTruthy());
    expect(screen.getByText(/산지전용허가 \+ 대체산림자원조성비 납부/)).toBeTruthy();
    expect(screen.getByText(/산림조사서·평균경사도조사서 작성/)).toBeTruthy();
    expect(screen.getByText(/기준 초과 구역 제외\(부분개발\)/)).toBeTruthy();
  });

  it("★백엔드 근거가 비면 조언이 사라진다(날조 금지 잠금)", async () => {
    // ★이게 이 PR의 핵심 안전장치다. 프론트가 "산림조사서를 발급받으세요"를 하드코딩하면
    //   이 테스트가 실패한다 — 근거가 없는데도 문장이 남기 때문이다.
    onPost("/analysis/comprehensive", async () =>
      coreWith([{ category: "임야(산지)", developability: "NEEDS_OFFICIAL_SURVEY" }]),
    );
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/공식 산림조사 필요/)).toBeTruthy());

    expect(screen.queryByText(/이 제약을 푸는 방법/)).toBeNull();
    expect(screen.queryByText(/산지전용허가/)).toBeNull();
    expect(screen.queryByText(/산림조사서/)).toBeNull();
  });
});
