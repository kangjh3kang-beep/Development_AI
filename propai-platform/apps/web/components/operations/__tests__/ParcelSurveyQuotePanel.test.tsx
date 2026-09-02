/**
 * 토지필지 종합분석 P0(견적·선별) 화면 — 정직성 계약 회귀망.
 *
 * ■ 무엇을 막는가
 *   이 화면의 존재 이유는 "비용 사고 방지"다 — 아래 항목이 조용히 빠지면 그 목적이
 *   무너진다: ①비용을 단일 숫자로 뭉개는 것 ②건축물 미상으로 인한 범위인 이유를 안 밝히는 것
 *   ③"실제 청구는 발급 성공분만"을 숨기는 것 ④폴리곤 미확보 필지를 안 알리는 것
 *   ⑤preview.note를 재단정 문구로 바꿔치는 것 ⑥선택 변경 시 견적을 재호출하지 않는 것.
 *
 * apiClient는 mock(실호출 차단·요청 payload 관측). @propai/ui는 jsxDEV 사전번들 이슈로
 * 단순 래퍼 mock(OrchestratorPanel.test.tsx와 동일 패턴).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const post = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (...a: unknown[]) => post(...a),
  },
}));

vi.mock("@propai/ui", () => ({
  Card: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
  CardContent: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
}));

import { ParcelSurveyQuotePanel } from "@/components/operations/ParcelSurveyQuotePanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const RANGE_RESPONSE = {
  quote: {
    parcel_count: 2,
    fee_per_unit: { issue: 1200, analysis: 2000, total: 3200 },
    units: { min: 2, max: 3 },
    estimated_cost: { min: 6400, max: 9600 },
    building_status: { with_building: 0, land_only: 1, unknown: 1 },
    geometry: {
      available: 1,
      missing: ["서울특별시 동작구 상도동 211-376"],
      note: "폴리곤 미확보 필지는 제척 가능/불가 위상판정이 **불가**합니다(권리분석은 가능).",
    },
    billing_basis: "issued_count",
    note: "**실제 청구는 발급에 성공한 건수만** 집계되므로 아래 견적보다 낮을 수 있습니다.",
  },
  preview: {
    available: true,
    graph: { articulation_points: ["서울특별시 동작구 상도동 211-376"] },
    note: "제거 시 필지 집합이 끊기는 필지(articulation)는 **제척 불가 후보**입니다. 최종 분류는 사업방식·사용권원 확보율이 정해져야 확정됩니다.",
  },
};

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue(RANGE_RESPONSE);
  useProjectContextStore.setState({ projectId: null, siteAnalysis: null } as never);
});

function addPastedLines(text: string) {
  const textarea = screen.getByPlaceholderText(/지번을 한 줄에 하나씩/);
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /목록에 추가/ }));
}

describe("ParcelSurveyQuotePanel — 견적·선별 정직성 계약", () => {
  it("여러 줄 붙여넣기(줄바꿈 분리)로 필지 목록이 생기고, 선택된 필지로 견적을 호출한다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("서울특별시 동작구 상도동 211-376\n경기도 광주시 회안대로 637-36");

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, opts] = post.mock.calls[0] as [string, { body: { parcels: Array<{ address: string }> } }];
    expect(path).toBe("/registry/survey/quote");
    expect(opts.body.parcels.map((p) => p.address)).toEqual([
      "서울특별시 동작구 상도동 211-376",
      "경기도 광주시 회안대로 637-36",
    ]);
  });

  it("비용을 min===max로 뭉개지 않고 범위(~)로 보여준다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");
    await waitFor(() => expect(post).toHaveBeenCalled());

    expect(await screen.findByText("6,400~9,600원")).toBeInTheDocument();
  });

  it("건축물 미상 건수가 있으면 범위인 이유를 문장으로 보여준다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");
    await waitFor(() => expect(post).toHaveBeenCalled());

    expect(await screen.findByText(/건축물 유무가 확인되지 않은 필지가 1건/)).toBeInTheDocument();
  });

  it("billing_basis=issued_count — 실제 청구는 발급 성공분만이라는 사실을 노출한다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");

    // ★MarkdownLite가 "**실제 청구는 발급에 성공한 건수만**"을 <strong>으로 렌더한다.
    //   매칭 문구는 **그 굵게 구간 안쪽**에만 걸쳐야 한다. 이유는 testing-library 의
    //   `getNodeText` 가 각 요소의 **직계 텍스트 노드만** 이어 붙이기 때문이다:
    //     · <strong> 의 텍스트  = "실제 청구는 발급에 성공한 건수만"        → 매치
    //     · 부모 <p> 의 직계텍스트 = <strong> 내용을 **뺀** 나머지("… 집계되므로 …") → 불일치
    //   그래서 안쪽 문구는 <strong> 한 곳에만 걸린다(유일 매치).
    // ★반대로 굵게 경계를 **넘나드는** 문구(예: /발급에 성공한 건수만 집계되므로/)는 어느 한
    //   요소의 직계텍스트로도 완성되지 않아 "broken up by multiple elements"로 **실패**한다.
    //   ★이건 추정이 아니라 실측이다 — 실제로 그 문구로 CI 가 빨갛게 났고(#633),
    //     안쪽 문구로 바꾼 뒤 초록이 됐다. 이전 주석은 이 인과를 **거꾸로** 적고 있었다.
    expect(await screen.findByText(/발급에 성공한 건수만/)).toBeInTheDocument();
  });

  it("geometry.missing이 있으면 필지 목록과 함께 위상판정 불가 경고를 보여준다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");

    expect(await screen.findByText(/폴리곤 미확보 1필지/)).toBeInTheDocument();
    expect(await screen.findByText("서울특별시 동작구 상도동 211-376")).toBeInTheDocument();
  });

  it("preview.note를 그대로 노출한다(새 단정 문구를 만들지 않는다)", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");

    expect(await screen.findByText(/최종 분류는 사업방식·사용권원 확보율이 정해져야 확정됩니다/)).toBeInTheDocument();
  });

  it("체크박스로 필지 선택을 해제하면 견적을 재계산(재호출)한다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A\nB");
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    const secondCall = post.mock.calls[1] as [string, { body: { parcels: Array<{ address: string }> } }];
    expect(secondCall[1].body.parcels).toHaveLength(1);
  });

  it("선택 필지가 0건이면 재호출하지 않고 안내만 보여준다", async () => {
    render(<ParcelSurveyQuotePanel locale="ko" />);
    addPastedLines("A");
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() =>
      expect(screen.getByText(/선택된 필지가 없습니다/)).toBeInTheDocument(),
    );
    expect(post).toHaveBeenCalledTimes(1);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-09-02 — **배선 락**. 종전엔 접힘방지 규칙이 이 패널에 **인라인**이었고 테스트는 그것을
// `lib/pnu.test.ts` 안에서 **재구현**해 검사했다. 그래서 규칙을 옛 형태
// (`p.pnu ? parcelDedupKey(p) : project-idx…`)로 되돌리는 변이가 **어떤 테스트도 깨지 않았다**
// (실측 SURVIVED). 여기서는 **패널 자신**을 태운다 — 스토어에 필지를 넣고 버튼을 눌러
// 견적 요청 본문을 본다.
//
// ★두 모집단을 **같은 실행에서** 가른다:
//   A 진짜 PNU 3건(주소 동일)   → 3건이 살아남는다
//   B 오염 PNU 3건(값도 동일)   → **3건이 살아남는다** ← 옛 조건에서는 1건으로 접혔다
// A 만 보면 «가짜를 그냥 키로 써도» 통과한다(가짜끼리 값이 다르면). B 가 그것을 가른다.
// ────────────────────────────────────────────────────────────────────────────

const 동주소 = "경기도 오산시 내삼미동";

function 프로젝트필지주입(parcels: Array<{ address: string; pnu?: string | null }>) {
  useProjectContextStore.setState({
    projectId: "p-test",
    siteAnalysis: { address: 동주소, parcels },
  } as never);
}

async function 불러오기후_견적필지() {
  fireEvent.click(screen.getByRole("button", { name: /현재 프로젝트 필지 불러오기/ }));
  await waitFor(() => expect(post).toHaveBeenCalled());
  const last = post.mock.calls[post.mock.calls.length - 1] as [
    string,
    { body: { parcels: Array<{ address: string; pnu?: string }> } },
  ];
  return last[1].body.parcels;
}

describe("★배선 — 프로젝트 필지 불러오기가 오염된 PNU 로 접히지 않는다", () => {
  it("모집단 A(진짜 PNU · 주소 동일) — 3건이 3건으로 들어온다", async () => {
    프로젝트필지주입([
      { address: 동주소, pnu: "4137011000104670001" },
      { address: 동주소, pnu: "4137011000104670002" },
      { address: 동주소, pnu: "4137011000104670003" },
    ]);
    render(<ParcelSurveyQuotePanel locale="ko" />);
    expect((await 불러오기후_견적필지()).length).toBe(3);
  });

  it("★모집단 B(오염 PNU · **값까지 동일**) — 그래도 3건이다(77→1 재발 방지)", async () => {
    // 생산자 `satong-map-selection.ts` 의 `store-rep-${address}` 는 **주소 파생**이라
    // 같은 동의 필지가 전부 **똑같은 값**을 받는다. 옛 조건은 이걸 truthy 로 보고
    // 인덱스 탈출구를 건너뛰어 3건을 1건으로 접었다.
    const 오염 = `store-rep-${동주소}`;
    프로젝트필지주입([
      { address: 동주소, pnu: 오염 },
      { address: 동주소, pnu: 오염 },
      { address: 동주소, pnu: 오염 },
    ]);
    render(<ParcelSurveyQuotePanel locale="ko" />);
    const parcels = await 불러오기후_견적필지();
    expect(parcels.length).toBe(3);
    // ★그리고 오염값이 **요청 본문으로 새어 나가지 않는다** — 나가면 서버가 그대로 echo 하고
    //   `jibun:null·area_sqm:0` 을 돌려준다(볼트 2026-08-20 실측).
    expect(parcels.some((p) => typeof p.pnu === "string" && p.pnu.includes("store-rep"))).toBe(false);
  });

  it("★음성 대조 — 진짜 PNU 는 요청 본문에 **실려 나간다**(과잉 제거가 아님을 가른다)", async () => {
    프로젝트필지주입([{ address: 동주소, pnu: "4137011000104670001" }]);
    render(<ParcelSurveyQuotePanel locale="ko" />);
    const parcels = await 불러오기후_견적필지();
    expect(parcels.map((p) => p.pnu)).toEqual(["4137011000104670001"]);
  });
});
