// Stage1 통합 의사결정 브리프 — 프론트 컴포넌트 테스트.
//
// 검증: ①verdict 분기 GO/CONDITIONAL/HOLD 렌더(배지·한줄결론) ②part unavailable 정직표기
// ③일반인/전문가 모드 토글(전문가에서만 KPI 그리드·blockers 노출) ④도메인 카드 N개 렌더
// ⑤자동 전체실행(주소 있으면 마운트 시 apiClient.post 자동 호출) ⑥주소 없으면 정직 안내.
//
// apiClient는 mock(실호출 차단). store는 setState로 초기화. next/navigation useParams는 mock.

import { StrictMode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

// apiClient mock — POST 실호출 차단·관측. ApiClientError는 실제 클래스 형태로 둔다(상태코드 분류).
const post = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { post: (...a: unknown[]) => post(...a) },
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.name = "ApiClientError";
      this.status = status;
      this.payload = payload;
    }
  },
}));

// next/navigation useParams — locale prefix 책임 검증용.
vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
}));

import { DecisionBriefPanel } from "@/components/projects/DecisionBriefPanel";
import { DecisionVerdictCard } from "@/components/projects/DecisionVerdictCard";
import { DomainSummaryCard } from "@/components/projects/DomainSummaryCard";
import { DecisionReuseBanner } from "@/components/projects/DecisionReuseBanner";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  findDecisionPart,
  type DecisionBrief,
  type DecisionBriefPart,
} from "@/components/projects/decision-brief-types";

// ── 백엔드 표준 계약 형태의 픽스처(decision_brief_service.py 반환 구조와 1:1) ──

function makePart(over: Partial<DecisionBriefPart> = {}): DecisionBriefPart {
  return {
    part: "site_market",
    title: "부지·입지·시장",
    summary_oneliner: "일반상업지역 · 실효 용적률 700% · 계획 GFA 7000㎡",
    key_metrics: [
      { label: "용도지역", value: "일반상업지역", unit: "" },
      { label: "대지면적", value: 1000, unit: "㎡" },
      { label: "실효 용적률", value: 700, unit: "%" },
      { label: "계획 연면적(GFA)", value: 7000, unit: "㎡" },
      { label: "예상 분양가", value: 5000, unit: "만원/평" },
    ],
    evidence: [{ label: "용적률 한도", value: "700%" }],
    legal_links: [
      { label: "국토의 계획 및 이용에 관한 법률 제78조", url: "https://law.go.kr/x" },
    ],
    confidence: "high",
    detail_route: "/projects/{id}/canvas",
    status: "ok",
    ...over,
  };
}

function makeBrief(over: Partial<DecisionBrief> = {}): DecisionBrief {
  return {
    address: "서울특별시 강남구 역삼동 123",
    project_id: "p1",
    parcel_count: 1,
    parts: [
      makePart(),
      makePart({
        part: "regulation",
        title: "법규·규제",
        summary_oneliner: "일반상업지역 · 적용 규제 2건",
        confidence: "medium",
        detail_route: "/projects/{id}/legal",
      }),
      makePart({
        part: "permit_design",
        title: "인허가·사업모델 Top3",
        summary_oneliner: "추천 주상복합 · ROI 12.5% · 2개 Top 모델",
        key_metrics: [
          { label: "추천 1순위 모델", value: "주상복합", unit: "" },
          { label: "1순위 ROI(사업수익률)", value: 12.5, unit: "%" },
        ],
        evidence: [],
        legal_links: [],
        confidence: "high",
        detail_route: "/projects/{id}/feasibility",
      }),
    ],
    verdict: {
      decision: "GO",
      confidence: "high",
      reasons: ["디벨로퍼 Go/No-Go: Go(추진 권고)", "Top1 주상복합 등급 A·ROI 12.5%"],
      blockers: [],
      go_nogo: { decision: "Go(추진 권고)", top1: "주상복합", grade: "A", roi_pct: 12.5, status: "go" },
      gate: "PASS",
    },
    billing: { use_llm: false, estimated_fee_krw: 0 },
    meta: { use_llm: false, deploy_pending: true, deploy_pending_note: "배포 환경에서만 동작합니다." },
    ...over,
  };
}

beforeEach(() => {
  post.mockReset();
  useProjectContextStore.setState({
    projectId: "p1",
    siteAnalysis: {
      estimatedValue: null,
      landAreaSqm: 1000,
      zoneCode: "일반상업지역",
      pnu: null,
      address: "서울특별시 강남구 역삼동 123",
    },
    decisionBrief: null,
    // staleness 통합 테스트 격리 — 모듈 타임스탬프 초기화(이전 테스트 잔류 차단).
    updatedAt: {},
    manualFields: {},
  });
});

describe("DecisionVerdictCard — verdict 분기 렌더", () => {
  it("GO → 녹색 추진 배지 + 일반인 한줄결론", () => {
    render(<DecisionVerdictCard brief={makeBrief()} />);
    expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy();
    expect(screen.getByText(/추진해 볼 만합니다/)).toBeTruthy();
    // 디벨로퍼 Go/No-Go 배지 패스스루.
    expect(screen.getByText(/디벨로퍼 Go\(추진 권고\)/)).toBeTruthy();
  });

  it("CONDITIONAL → 조건부 배지 + 잠정 결론", () => {
    const brief = makeBrief({
      verdict: {
        decision: "CONDITIONAL",
        confidence: "medium",
        reasons: ["선행절차/공시지가 신뢰성 전제 — 조건부"],
        blockers: ["특이부지/도로·인허가 선행절차 전제 — 확정 GO 강등(잠정)."],
        go_nogo: { decision: "보류(선행절차/신뢰성 전제)", status: "conditional" },
        gate: "TENTATIVE",
      },
    });
    render(<DecisionVerdictCard brief={brief} />);
    expect(screen.getByText(/조건부 추진 \(CONDITIONAL\)/)).toBeTruthy();
    expect(screen.getByText(/선행 조건을 충족하면/)).toBeTruthy();
    // 게이트 배지(PASS 아니면 노출).
    expect(screen.getByText(/게이트 TENTATIVE/)).toBeTruthy();
  });

  it("★게이트 강등: 디벨로퍼 'Go(추진 권고)'인데 최종 CONDITIONAL → '(게이트 강등)' 보조표기", () => {
    const brief = makeBrief({
      verdict: {
        decision: "CONDITIONAL",
        confidence: "medium",
        reasons: ["디벨로퍼 Go/No-Go: Go(추진 권고)"],
        blockers: ["특이부지/도로·인허가 선행절차 전제 — 확정 GO 강등(잠정)."],
        // 디벨로퍼 원 권고는 Go 인데, 게이트 강등으로 최종은 CONDITIONAL(status 도 conditional).
        go_nogo: { decision: "Go(추진 권고)", top1: "주상복합", grade: "A", roi_pct: 12.5, status: "conditional" },
        gate: "TENTATIVE",
      },
    });
    render(<DecisionVerdictCard brief={brief} />);
    // 디벨로퍼 원 권고 텍스트(Go) + 게이트 강등 보조표기가 함께 노출돼 모순 오인을 막는다.
    expect(screen.getByText(/디벨로퍼 Go\(추진 권고\)/)).toBeTruthy();
    expect(screen.getByText(/\(게이트 강등\)/)).toBeTruthy();
  });

  it("★강등 아님: 디벨로퍼·최종이 동일(GO/GO)이면 '(게이트 강등)' 표기 없음", () => {
    // makeBrief 기본 = go_nogo Go + 최종 GO → 강등 아님.
    render(<DecisionVerdictCard brief={makeBrief()} />);
    expect(screen.getByText(/디벨로퍼 Go\(추진 권고\)/)).toBeTruthy();
    expect(screen.queryByText(/\(게이트 강등\)/)).toBeNull();
  });

  it("HOLD → 적색 보류 배지", () => {
    const brief = makeBrief({
      verdict: {
        decision: "HOLD",
        confidence: "low",
        reasons: ["사업타당성(Top3) 미확보 — 판정 보류"],
        blockers: ["특이부지/법규 차단 — 통상 절차로 해결 불가능한 제약."],
        go_nogo: null,
        gate: "BLOCK",
      },
    });
    render(<DecisionVerdictCard brief={brief} />);
    expect(screen.getByText(/보류 \(HOLD\)/)).toBeTruthy();
    expect(screen.getByText(/추진을 보류/)).toBeTruthy();
  });
});

describe("DecisionVerdictCard — 일반인/전문가 모드 토글", () => {
  it("일반인 모드는 KPI 그리드·차단사유 숨김 → 전문가 모드에서 노출", () => {
    const brief = makeBrief({
      verdict: {
        decision: "HOLD",
        confidence: "low",
        reasons: ["근거1", "근거2", "근거3", "근거4"],
        blockers: ["법규 차단 사유A"],
        go_nogo: null,
        gate: "BLOCK",
      },
    });
    render(<DecisionVerdictCard brief={brief} />);
    // 일반인(기본): 차단사유 헤더·4번째 근거 미노출(상위 3개만).
    expect(screen.queryByText("차단 사유")).toBeNull();
    expect(screen.queryByText(/근거4/)).toBeNull();
    // 전문가 토글 → KPI/차단사유 노출.
    fireEvent.click(screen.getByText("전문가"));
    expect(screen.getByText("차단 사유")).toBeTruthy();
    expect(screen.getByText(/법규 차단 사유A/)).toBeTruthy();
    // KPI(실효 용적률 등) 그리드 노출.
    expect(screen.getByText("실효 용적률")).toBeTruthy();
    expect(screen.getByText(/근거4/)).toBeTruthy();
  });
});

describe("DomainSummaryCard — 표준 카드 + unavailable 정직표기", () => {
  it("ok part → 제목·한줄요약·KPI·상세 CTA(locale prefix) 렌더", () => {
    render(
      <DomainSummaryCard part={makePart()} detailHref="/ko/projects/p1/canvas" />,
    );
    expect(screen.getByText("부지·입지·시장")).toBeTruthy();
    expect(screen.getByText(/실효 용적률 700%/)).toBeTruthy();
    const cta = screen.getByText("상세 분석").closest("a");
    expect(cta?.getAttribute("href")).toBe("/ko/projects/p1/canvas");
  });

  it("unavailable part → '데이터 없음' + 정직 사유(가짜값 금지)", () => {
    const part = makePart({
      status: "unavailable",
      reason: "VWORLD 조회 타임아웃",
      key_metrics: [],
      evidence: [],
      legal_links: [],
      confidence: "low",
    });
    render(<DomainSummaryCard part={part} detailHref={null} />);
    expect(screen.getByText("데이터 없음")).toBeTruthy();
    expect(screen.getByText("VWORLD 조회 타임아웃")).toBeTruthy();
  });
});

describe("DecisionBriefPanel — 자동 전체실행 + N개 도메인 카드", () => {
  it("주소가 있으면 마운트 시 자동 호출 → verdict + 도메인 카드 렌더", async () => {
    post.mockResolvedValueOnce(makeBrief());
    render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    // POST 경로 정합.
    expect(post.mock.calls[0][0]).toBe("/projects/p1/decision-brief");
    // verdict + 3개 part 제목 렌더.
    await waitFor(() => expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy());
    expect(screen.getByText("부지·입지·시장")).toBeTruthy();
    expect(screen.getByText("법규·규제")).toBeTruthy();
    expect(screen.getByText("인허가·사업모델 Top3")).toBeTruthy();
    // deploy-pending 정직 고지.
    expect(screen.getByText(/배포 환경에서만 동작합니다/)).toBeTruthy();
  });

  it("주소 미확보면 자동 호출하지 않고 정직 안내(silent 금지)", async () => {
    useProjectContextStore.setState({
      siteAnalysis: { estimatedValue: null, landAreaSqm: null, zoneCode: null, pnu: null, address: null },
    });
    render(<DecisionBriefPanel projectId="p1" autoRun />);
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText("분석할 주소가 없습니다")).toBeTruthy();
  });

  it("404(미배포) → 정직 에러 표기(deploy-pending 메시지·상태코드)", async () => {
    const { ApiClientError } = await import("@/lib/api-client");
    post.mockRejectedValueOnce(new ApiClientError("not found", 404, null));
    render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() =>
      expect(screen.getByText(/아직 배포되지 않았습니다/)).toBeTruthy(),
    );
    expect(screen.getByText(/상태 코드: 404/)).toBeTruthy();
  });

  it("★면적 override 괴리 경고(meta.area_override.warning) → 경고배너 렌더(dead-wire 해소)", async () => {
    post.mockResolvedValueOnce(
      makeBrief({
        meta: {
          use_llm: false,
          deploy_pending: true,
          deploy_pending_note: "배포 환경에서만 동작합니다.",
          area_override: {
            override_area_sqm: 6000,
            engine_area_sqm: 1000,
            ratio: 6.0,
            warning:
              "입력 통합면적이 엔진 대표면적과 5배 이상 차이납니다 — 면적/필지 입력을 확인하세요.",
          },
        },
      }),
    );
    render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText(/5배 이상 차이납니다/)).toBeTruthy(),
    );
  });

  it("★면적 괴리 없으면(warning 부재) 경고배너 미렌더(잡음 방지)", async () => {
    post.mockResolvedValueOnce(
      makeBrief({
        meta: {
          use_llm: false,
          deploy_pending: true,
          deploy_pending_note: "배포 환경에서만 동작합니다.",
          // warning 없는 정상 범위(3배) area_override.
          area_override: { override_area_sqm: 3000, engine_area_sqm: 1000, ratio: 3.0 },
        },
      }),
    );
    render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy());
    expect(screen.queryByText(/차이납니다/)).toBeNull();
  });

  it("동일 주소·동일 면적 리렌더 → 중복 분석 호출 안 함(dedup 가드)", async () => {
    // 1차 마운트: 자동 호출 1회.
    post.mockResolvedValue(makeBrief());
    const { rerender } = render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    // 같은 입력(주소·면적)으로 리렌더 → inputSig 불변 → 자동호출 useEffect 미발화·가드 차단.
    rerender(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy());
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("★stale-brief: 다필지 통합면적 변경 → 브리프 리셋 후 새 면적으로 재분석", async () => {
    // 1차: 대표면적(1000㎡)로 자동 분석.
    post.mockResolvedValue(makeBrief());
    const { rerender } = render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toMatchObject({ body: { land_area_sqm: 1000 } });

    // 다필지 보강: 통합면적(landAreaSqmTotal=3000)·parcelCount=3 갱신(주소 동일).
    // updateSiteAnalysis가 유효면적 변경을 감지해 decisionBrief를 null로 리셋해야 한다.
    act(() => {
      useProjectContextStore.getState().updateSiteAnalysis({
        landAreaSqmTotal: 3000,
        parcelCount: 3,
      });
    });
    expect(useProjectContextStore.getState().decisionBrief).toBeNull();

    // 면적 시그니처 변경 → 자동 재분석(통합면적 3000 전송).
    rerender(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toMatchObject({ body: { land_area_sqm: 3000 } });
  });
});

describe("DecisionVerdictCard — KPI key 조회(라벨 강결합 제거)", () => {
  it("라벨이 바뀌어도 안정 key로 KPI를 찾는다(silent-null 제거)", () => {
    // 백엔드가 라벨 문구를 바꾼 상황을 시뮬레이션 — key만 안정 유지.
    const brief = makeBrief({
      parts: [
        makePart({
          key_metrics: [
            // 라벨은 임의로 변경, key는 계약대로 유지.
            { key: "effective_far", label: "용적률(변경된 라벨)", value: 700, unit: "%" },
            { key: "gfa", label: "연면적-신규문구", value: 7000, unit: "㎡" },
          ],
        }),
        makePart({
          part: "permit_design",
          title: "인허가·사업모델 Top3",
          key_metrics: [
            { key: "roi", label: "수익률(라벨변경)", value: 12.5, unit: "%" },
          ],
        }),
      ],
    });
    render(<DecisionVerdictCard brief={brief} />);
    // 전문가 모드로 KPI 그리드 노출.
    fireEvent.click(screen.getByText("전문가"));
    // 라벨이 바뀌었어도 key 조회로 값이 정상 렌더(700%·7,000㎡·12.5%).
    expect(screen.getByText("700%")).toBeTruthy();
    expect(screen.getByText("7,000㎡")).toBeTruthy();
    expect(screen.getByText("12.5%")).toBeTruthy();
  });

  it("구 응답(key 없음) → label 폴백으로 하위호환 동작", () => {
    // key 없는 구 응답 시뮬레이션 — 정본 라벨로 폴백 매칭되어야 한다.
    const brief = makeBrief({
      parts: [
        makePart({
          key_metrics: [
            { label: "실효 용적률", value: 500, unit: "%" },
          ],
        }),
        makePart({ part: "permit_design", title: "인허가·사업모델 Top3", key_metrics: [] }),
      ],
    });
    render(<DecisionVerdictCard brief={brief} />);
    fireEvent.click(screen.getByText("전문가"));
    expect(screen.getByText("500%")).toBeTruthy();
  });

  it("go_nogo.decision 없으면 status 한국어 폴백 라벨 노출(영문 status 금지)", () => {
    const brief = makeBrief({
      verdict: {
        decision: "CONDITIONAL",
        confidence: "medium",
        reasons: [],
        blockers: [],
        // decision 문구 없이 status만 — 한국어 '조건부'로 폴백돼야 한다.
        go_nogo: { status: "conditional" },
        gate: "TENTATIVE",
      },
    });
    render(<DecisionVerdictCard brief={brief} />);
    expect(screen.getByText(/디벨로퍼\s*조건부/)).toBeTruthy();
    // 영문 raw status는 노출되지 않아야 한다.
    expect(screen.queryByText(/conditional/)).toBeNull();
  });
});

describe("DecisionBriefPanel — in-flight dedup + latest-input-wins(StrictMode 경합 방지)", () => {
  it("★StrictMode 이중 마운트 → POST 정확히 1회(in-flight dedup)", async () => {
    // StrictMode는 개발 모드에서 effect를 이중 실행한다. await 이전 inFlightSig 가드로
    // 같은 입력의 동시 2발이 1회로 합쳐져야 한다(응답역순 last-write-wins 차단의 1차 방어).
    let resolve: ((v: DecisionBrief) => void) | null = null;
    post.mockImplementation(
      () =>
        new Promise<DecisionBrief>((r) => {
          resolve = r;
        }),
    );
    render(
      <StrictMode>
        <DecisionBriefPanel projectId="p1" />
      </StrictMode>,
    );
    // 마운트 직후(아직 응답 전) — in-flight 가드로 POST는 1회만.
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await act(async () => {
      resolve?.(makeBrief());
    });
    await waitFor(() => expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy());
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("★면적 연속변경 → 마지막 면적 응답만 커밋(latest-input-wins·응답역순 폐기)", async () => {
    // 1차(1000㎡) 요청은 늦게, 2차(3000㎡) 요청은 먼저 응답하도록 역순 도착을 강제한다.
    // 시퀀스 토큰이 '마지막으로 시작한' 요청(3000)만 커밋해야 한다(1000 응답은 폐기).
    const brief1000 = makeBrief({ parcel_count: 1 });
    const brief3000 = makeBrief({
      parcel_count: 3,
      parts: [
        makePart({
          key_metrics: [{ key: "land_area", label: "대지면적", value: 3000, unit: "㎡" }],
        }),
        makePart({ part: "regulation", title: "법규·규제" }),
        makePart({ part: "permit_design", title: "인허가·사업모델 Top3" }),
      ],
    });
    const resolvers: Array<(v: DecisionBrief) => void> = [];
    post.mockImplementation(
      () => new Promise<DecisionBrief>((r) => resolvers.push(r)),
    );

    const { rerender } = render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toMatchObject({ body: { land_area_sqm: 1000 } });

    // 면적 변경(3000) → inputSig 변경 → 2차 자동 요청 발사.
    act(() => {
      useProjectContextStore.getState().updateSiteAnalysis({
        landAreaSqmTotal: 3000,
        parcelCount: 3,
      });
    });
    rerender(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toMatchObject({ body: { land_area_sqm: 3000 } });

    // ★응답 역순 도착: 2차(3000)가 먼저, 1차(1000)가 나중에 resolve.
    await act(async () => {
      resolvers[1]?.(brief3000);
      resolvers[0]?.(brief1000);
    });

    // 커밋된 브리프는 '마지막으로 시작한' 3000 요청의 것(1000 폐기) — parcel_count=3.
    await waitFor(() =>
      expect(useProjectContextStore.getState().decisionBrief?.parcel_count).toBe(3),
    );
  });
});

// ── P2 ① staleness 통합(모세혈관) — store 레벨 ──
describe("store.isStale('decisionBrief') — staleness 캐스케이드 편입", () => {
  it("setDecisionBrief가 updatedAt.decisionBrief를 stamp한다(이전엔 미기록)", () => {
    const st = useProjectContextStore.getState();
    expect(useProjectContextStore.getState().updatedAt.decisionBrief).toBeUndefined();
    act(() => st.setDecisionBrief(makeBrief()));
    expect(
      useProjectContextStore.getState().updatedAt.decisionBrief,
    ).toBeTypeOf("number");
    // 브리프 직후 stale 아님(업스트림이 더 최신이 아니므로).
    expect(useProjectContextStore.getState().isStale("decisionBrief")).toBe(false);
  });

  it("브리프 보존 + 업스트림(용도지역만) 갱신 → isStale('decisionBrief')=true(재분석 게이트)", async () => {
    const st = useProjectContextStore.getState();
    act(() => st.setDecisionBrief(makeBrief()));
    // 주소/유효면적은 그대로, 용도지역만 변경 → 브리프 null 리셋 안 됨(보존) + siteAnalysis stamp.
    await new Promise((r) => setTimeout(r, 2)); // 타임스탬프 단조 증가 보장.
    act(() =>
      useProjectContextStore.getState().updateSiteAnalysis({ zoneCode: "제2종일반주거지역" }),
    );
    // 브리프는 보존(주소/면적 불변)되고, 부지분석이 더 최신 → stale.
    expect(useProjectContextStore.getState().decisionBrief).not.toBeNull();
    expect(useProjectContextStore.getState().isStale("decisionBrief")).toBe(true);
  });

  it("주소/유효면적 변경 → 브리프 null 리셋 + updatedAt.decisionBrief도 제거(stale 아님)", () => {
    const st = useProjectContextStore.getState();
    act(() => st.setDecisionBrief(makeBrief()));
    expect(useProjectContextStore.getState().updatedAt.decisionBrief).toBeTypeOf("number");
    // 유효면적 변경(다필지 통합면적) → 리셋 경로.
    act(() =>
      useProjectContextStore.getState().updateSiteAnalysis({
        landAreaSqmTotal: 9000,
        parcelCount: 3,
      }),
    );
    // 브리프 null + 타임스탬프 제거 → own==null → isStale=false(브리프 없는데 stale 오판 금지).
    expect(useProjectContextStore.getState().decisionBrief).toBeNull();
    expect(useProjectContextStore.getState().updatedAt.decisionBrief).toBeUndefined();
    expect(useProjectContextStore.getState().isStale("decisionBrief")).toBe(false);
  });

  it("setDecisionBrief(null) → 타임스탬프도 함께 제거(리셋 vs stale표기 일원화)", () => {
    const st = useProjectContextStore.getState();
    act(() => st.setDecisionBrief(makeBrief()));
    expect(useProjectContextStore.getState().updatedAt.decisionBrief).toBeTypeOf("number");
    act(() => useProjectContextStore.getState().setDecisionBrief(null));
    expect(useProjectContextStore.getState().updatedAt.decisionBrief).toBeUndefined();
  });
});

// ── P2 ① staleness 통합 — 패널 재분석 CTA(인간게이트·자동재실행 금지) ──
describe("DecisionBriefPanel — stale 재분석 CTA(자동재실행 금지)", () => {
  it("브리프 보존된 채 부지분석(용도지역만)이 더 최신이면 '재분석' 배지/CTA 노출", async () => {
    // 1차: 자동 전체실행으로 브리프 산출(ready) → POST 1회.
    post.mockResolvedValue(makeBrief());
    render(<DecisionBriefPanel projectId="p1" />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/추진 권고 \(GO\)/)).toBeTruthy());

    // 부지분석에서 주소/유효면적이 아닌 '용도지역'만 변경 → inputSig 불변(자동재실행 미발화)
    //   + 브리프 보존 + siteAnalysis 타임스탬프가 브리프보다 최신 → stale.
    await new Promise((r) => setTimeout(r, 2));
    act(() =>
      useProjectContextStore.getState().updateSiteAnalysis({ zoneCode: "제2종일반주거지역" }),
    );
    // stale 배지 + 재분석 버튼 노출(자동재실행 금지 — POST는 추가로 발사되지 않음).
    await waitFor(() =>
      expect(screen.getByText(/최신이 아닐 수 있습니다/)).toBeTruthy(),
    );
    expect(screen.getByRole("button", { name: "재분석" })).toBeTruthy();
    // ★자동재실행 금지(인간게이트) — 용도지역 변경만으로 POST가 재발사되지 않아야 한다.
    expect(post).toHaveBeenCalledTimes(1);
  });
});

// ── P2 ② Tier2 드릴다운 재사용 — DecisionReuseBanner + findDecisionPart ──
describe("findDecisionPart — parts 안전조회(SSOT)", () => {
  it("존재하는 part는 반환, 없으면 null(폴백)", () => {
    const brief = makeBrief();
    expect(findDecisionPart(brief, "permit_design")?.part).toBe("permit_design");
    expect(findDecisionPart(brief, "site_market")?.part).toBe("site_market");
    expect(findDecisionPart(null, "permit_design")).toBeNull();
    expect(
      findDecisionPart({ ...brief, parts: [] }, "permit_design"),
    ).toBeNull();
  });
});

describe("DecisionReuseBanner — Tier2 재사용 프리필/폴백", () => {
  it("part 있으면 'Stage1 통합분석 기반' + 한줄요약 렌더", () => {
    const part = makePart({
      part: "permit_design",
      summary_oneliner: "추천 주상복합 · ROI 12.5% · 2개 Top 모델",
    });
    render(<DecisionReuseBanner part={part} />);
    expect(screen.getByText("Stage1 통합분석 기반")).toBeTruthy();
    expect(screen.getByText(/추천 주상복합 · ROI 12.5%/)).toBeTruthy();
  });

  it("part 없으면(null) 아무것도 렌더하지 않음(기존 동작 폴백·무회귀)", () => {
    const { container } = render(<DecisionReuseBanner part={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("unavailable part는 가짜 요약 위장 금지(미렌더)", () => {
    const part = makePart({
      part: "permit_design",
      status: "unavailable",
      reason: "site_id 미확보",
    });
    const { container } = render(<DecisionReuseBanner part={part} />);
    expect(container.firstChild).toBeNull();
  });

  it("stale=true면 정직 고지(최신 아닐 수 있음) 동반", () => {
    const part = makePart({ part: "permit_design" });
    render(<DecisionReuseBanner part={part} stale />);
    expect(screen.getByText(/최신이 아닐 수 있습니다/)).toBeTruthy();
  });
});
