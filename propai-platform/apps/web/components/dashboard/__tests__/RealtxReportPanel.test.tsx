/**
 * 실거래 신고내역 패널 — **정직성 보장**을 잠근다(모양이 아니라 주장).
 *
 * ★이 패널이 말하면 안 되는 것 세 가지:
 *   ① "필지별"       — 원천이 지번을 마스킹한다(라이브 114/114). 사유를 **백엔드 문구 그대로** 보여야 한다.
 *   ② "거래 0건"     — 조회 실패를 0건으로 그리면 *"거래가 없었다"* 는 **거짓 사실**이 된다.
 *   ③ "등기 미완"    — 등기일자는 원천에서 약 30%만 채워진다. 공란이 미등기가 아니다.
 *
 * ★렌더 테스트로 잠근다 — 소스 문자열 검사는 주석·SyntaxError 에 뚫린 전례가 있다.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const post = vi.fn();
// ★보고서 다운로드는 apiClient 가 아니라 **raw fetch**(blob)를 쓴다 — 그 경로를 따로 잠근다.
const fetchSpy = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (...a: unknown[]) => post(...a),
    getRuntimeConfig: () => ({ apiBaseUrl: "https://api.test/api/v1" }),
  },
}));

const rows = [{ id: "r1", pnu: "1159010200102100453", jibun: "서울특별시 동작구 상도동 210-453",
  owner: "", share: "", area_sqm: 53, owner_type: "사유지" as const,
  expected_price: null, purchase_price: null, contracted: false,
  land_use_consent: false, district_consent: false, operator_consent: false }];

vi.mock("@/store/useProjectStore", () => ({
  useProjectStore: (sel: (s: unknown) => unknown) => sel({ projects: [{ id: "P1", name: "테스트프로젝트" }] }),
}));
vi.mock("@/store/useLandScheduleStore", () => ({
  useLandScheduleStore: (sel: (s: unknown) => unknown) => sel({ byProject: { P1: rows } }),
}));

import { RealtxReportPanel } from "@/components/dashboard/RealtxReportPanel";

const BASIS = "국토부 실거래 공개자료는 토지 거래의 지번을 마스킹합니다(ZZ고유토큰).";
function reportWith(over: Record<string, unknown> = {}) {
  return {
    months: ["202608"], groups: [{
      lawd_cd: "11590", dong: "상도동", parcels: [{}],
      summary: { total: 2, cancelled: 1, cancelled_pct: 50, direct: 1, brokered: 1,
        registered: 1, registered_pct: 50, corporate_buyer: 1, corporate_seller: 0, share_deals: 1 },
      transactions: [
        { deal_date: "2026년 7월 1일", jimok: "임야", area_m2: 1795, price_10k_won: 12000,
          dealing_type: "직거래", registered_date: "", buyer_type: "법인", seller_type: "개인",
          cancel_type: "O", cancel_date: "26.07.20", share_dealing_type: "지분",
          // ★해제 행 — 서버가 값 대신 사유를 싣는다
          price_per_pyeong_10k: null, price_per_pyeong_10k_absent: "not_applicable",
          price_per_pyeong_10k_basis: "계약이 해제된 신고 건이라 거래 단가를 산정하지 않습니다." },
        { deal_date: "2026년 7월 5일", jimok: "전", area_m2: 300, price_10k_won: 5000,
          dealing_type: "중개거래", registered_date: "26.07.10", buyer_type: "개인",
          seller_type: "개인", cancel_type: " ", share_dealing_type: "",
          // ★정상 행 — 값이 실린다(억 절단이면 "1.5억"이 된다)
          price_per_pyeong_10k: 14623 },
      ],
      parcel_level_match: null, parcel_level_match_absent: "masked_by_source",
      parcel_level_match_basis: BASIS,
    }],
    unlocated_parcels: [], fetch_errors: [],
    meta: { parcel_count: 1, lawd_count: 1, month_count: 6, molit_calls: 6, unlocated_count: 0 },
    note: "실거래 신고내역은 국토교통부 공개자료 기준입니다.",
    ...over,
  };
}

async function analyze() {
  render(<RealtxReportPanel />);
  fireEvent.change(screen.getByLabelText("분석할 프로젝트"), { target: { value: "P1" } });
  fireEvent.click(screen.getByText("분석"));
}

beforeEach(() => { post.mockReset(); fetchSpy.mockReset(); });

describe("실거래 신고내역 패널 — 정직성", () => {
  it("D1 ★마스킹 사유를 **백엔드 문구 그대로** 보여 준다(화면이 지어내지 않는다)", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await waitFor(() => expect(screen.getByText(BASIS)).toBeTruthy());
  });

  it("D2 ★조회 실패를 '거래 0건'으로 그리지 않는다", async () => {
    post.mockResolvedValue(reportWith({
      groups: [], fetch_errors: [{ lawd_cd: "11590", deal_ym: "202607", error: "RuntimeError" }],
    }));
    await analyze();
    const warn = await screen.findByText(/일부 기간을 조회하지 못했습니다/);
    expect(warn.textContent).toContain("1건");
    // ★"거래가 없습니다" 라고 말하면 거짓이다 — 그 문구가 나오면 안 된다
    expect(screen.queryByText(/신고된 토지 실거래가 없습니다/)).toBeNull();
  });

  it("D3 특이도 — 실패가 없고 그룹도 없을 때만 '없습니다'라고 말한다", async () => {
    post.mockResolvedValue(reportWith({ groups: [], fetch_errors: [] }));
    await analyze();
    await waitFor(() => expect(screen.getByText(/신고된 토지 실거래가 없습니다/)).toBeTruthy());
    expect(screen.queryByText(/일부 기간을 조회하지 못했습니다/)).toBeNull();
  });

  it("D4 ★해제 건을 해제로, 스페이스는 정상으로 표기한다", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await waitFor(() => expect(screen.getByText(/해제 \(26\.07\.20\)/)).toBeTruthy());
    // 두 번째 행의 cancel_type 은 " "(스페이스) → **정상**이어야 한다
    expect(screen.getAllByText("정상").length).toBe(1);
  });

  it("D5 ★등기 공란을 '미기재'로 쓴다(미등기라고 단정하지 않는다)", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await waitFor(() => expect(screen.getByText("미기재")).toBeTruthy());
    expect(screen.queryByText(/미등기/)).toBeNull();
  });

  it("D6 ★쿼터 접기를 **수**로 보여 준다(주장이 아니라)", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    const meta = await screen.findByText(/국토부 조회/);
    expect(meta.textContent).toContain("6회");
    expect(meta.textContent).toContain("시군구 1");
  });

  it("D7 배선 — 서버에 **필지 PNU 를 실제로 보낸다**", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await waitFor(() => expect(post).toHaveBeenCalled());
    const [path, opts] = post.mock.calls[0] as [string, { body: { parcels: { pnu: string }[] } }];
    expect(path).toBe("/market/realtx-report");
    expect(opts.body.parcels[0].pnu).toBe("1159010200102100453");
  });

  it("D8 필지 없는 프로젝트는 고를 수 없다(빈 결과를 '거래 없음'으로 오독시키지 않는다)", async () => {
    render(<RealtxReportPanel />);
    const opts = Array.from(screen.getByLabelText("분석할 프로젝트").querySelectorAll("option"));
    expect(opts.map((o) => o.textContent)).toContain("테스트프로젝트 · 필지 1");
  });

  it("D10 ★배선 — 보고서 저장이 **정본 다운로드 경로**를 호출한다", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await screen.findByText(/국토부 조회/);   // ★이 패널의 실제 문구(다른 컴포넌트 것을 쓰지 않는다)
    // ★스텁은 **렌더가 끝난 뒤**에 건다 — 먼저 걸면 렌더 경로의 fetch 까지 가로채
    //   화면이 안 그려지고, 그러면 이 테스트가 **다른 이유로** 실패한다(실측).
    // blob URL API 는 jsdom 에 없다 — 최소 스텁(★렌더 뒤에 건다)
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => "blob:x");
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    fetchSpy.mockResolvedValue({ ok: true, blob: async () => new Blob(["x"]) });
    vi.stubGlobal("fetch", fetchSpy);
    fireEvent.click(screen.getByText("PDF"));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const [url, opts] = fetchSpy.mock.calls[0] as [string, { body: string }];
    expect(url).toContain("/market/realtx-report/download");
    expect(url).toContain("format=pdf");
    // ★필지를 실제로 보낸다(빈 요청으로 "보고서"를 만들지 않는다)
    expect(JSON.parse(opts.body).parcels[0].pnu).toBe("1159010200102100453");
    vi.unstubAllGlobals();
  });

  it("D11 다운로드 실패 시 침묵하지 않는다", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await screen.findByText(/국토부 조회/);   // ★이 패널의 실제 문구(다른 컴포넌트 것을 쓰지 않는다)
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 403 });
    vi.stubGlobal("fetch", fetchSpy);
    fireEvent.click(screen.getByText("DOCX"));
    await waitFor(() => expect(screen.getByText(/권한이 필요합니다/)).toBeTruthy());
    vi.unstubAllGlobals();
  });

  it("D9 실패 시 침묵하지 않는다", async () => {
    // ★**동기 throw** 를 쓴다 — 거부된 promise 를 만들면 vitest 가 그것을 미처리 거부로
    //   집어 **테스트가 통과해도 파일이 실패**한다(실측: post 를 호출조차 안 해도 발생).
    //   컴포넌트의 try/catch 는 동기 throw 도 똑같이 잡으므로 검증 대상은 동일하다.
    post.mockImplementationOnce(() => { throw new Error("HTTP 500"); });
    await analyze();
    const el = await screen.findByText(/조회 실패/);
    expect(el.textContent).toContain("HTTP 500");
  });
});

describe("만원/평 열 — 정밀도와 보류", () => {
  it("D12 ★`won()` 억 절단을 쓰지 않는다 — 14,623 이 「1.5억」으로 뭉개지면 이 열은 무의미하다", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    // 값이 그대로 보인다
    await waitFor(() => expect(screen.getByText("14,623")).toBeTruthy());
    // ★음성 대조군 — 억 절단 표기가 이 열에 나타나면 안 된다.
    //   (거래가 열의 억 표기는 정당하므로, 단가값 자체가 절단되지 않았는지로 판정한다)
    expect(screen.queryByText("1.5억")).toBeNull();
  });

  it("D13 ★해제 행은 값이 아니라 **사유**를 보여 준다(0 이나 계산값을 흘리지 않는다)", async () => {
    post.mockResolvedValue(reportWith());
    await analyze();
    await waitFor(() => expect(screen.getByText("해당없음")).toBeTruthy());
    // 해제 행의 원시 단가(12000/(1795/3.305785)=22)가 새어 나오면 안 된다
    expect(screen.queryByText("22")).toBeNull();
  });

  it("D14 ★두 보류 사유가 **서로 다른 말**로 보인다(한 글리프로 뭉개지 않는다)", async () => {
    post.mockResolvedValue(reportWith({
      groups: [{
        ...reportWith().groups[0],
        transactions: [
          { deal_date: "d1", jimok: "대", area_m2: 100, price_10k_won: 1000, cancel_type: "O",
            price_per_pyeong_10k: null, price_per_pyeong_10k_absent: "not_applicable",
            price_per_pyeong_10k_basis: "해제 사유" },
          { deal_date: "d2", jimok: "대", area_m2: null, price_10k_won: 1000, cancel_type: " ",
            price_per_pyeong_10k: null, price_per_pyeong_10k_absent: "masked_by_source",
            price_per_pyeong_10k_basis: "원천 미제공 사유" },
        ],
      }],
    }));
    await analyze();
    await waitFor(() => expect(screen.getByText("원천미제공")).toBeTruthy());
    expect(screen.getByText("해당없음")).toBeTruthy();
    // ★파티션형 — 두 사유가 같은 문자열이면 이 단언이 죽는다
    expect(screen.queryByText("원천미제공")).not.toBe(screen.queryByText("해당없음"));
    // ★그리고 상태 열의 「해제」와 **다른 말**이어야 한다(두 열이 같은 말을 하면 정보가 0이다)
    expect(screen.queryByText("해당없음")).not.toBe(screen.queryByText("해제"));
  });
});
