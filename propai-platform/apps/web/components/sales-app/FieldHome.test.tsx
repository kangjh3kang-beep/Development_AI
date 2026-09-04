import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import FieldHome from "@/components/sales-app/FieldHome";

/**
 * 역할별 홈(FieldHome) 계약 회귀 — 적대리뷰 BLOCKING/MAJOR 재발 방지.
 *  ① grade-suggestions 는 배열이 아니라 {customers[]}·필드=suggested_grade (데드-와이어 방지)
 *  ② /units/board 로드 실패는 '0%·0세대'로 위장하지 않고 정직 실패상태 (무목업)
 *  ③ CTA/빠른이동은 내 권한 노출 탭만 (고아 탭 이동·feature 게이트 우회 방지)
 * salesApi 는 경로별 응답을 주입해 격리(실 네트워크 없음).
 */

// 테스트별로 갈아끼우는 경로→응답 맵(거부하려면 함수가 reject).
let responses: Record<string, unknown | (() => Promise<unknown>)>;

vi.mock("@/lib/salesApi", () => ({
  salesApi: () => ({
    get: vi.fn((path: string) => {
      const v = responses[path];
      if (typeof v === "function") return (v as () => Promise<unknown>)();
      if (v === undefined) return Promise.reject(new Error(`no mock: ${path}`));
      return Promise.resolve(v);
    }),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    del: vi.fn().mockResolvedValue({}),
  }),
}));

const MEMBER = { role: "MEMBER", role_label: "직원" };
// MEMBER 의 features 노출 탭(alwaysOn + units/customers) — subscription(contracts) 없음.
const MEMBER_TABS = ["home", "units", "customers", "worklog", "cert", "market", "profile", "social", "referral"];

const BOARD_OK = { counts: { AVAILABLE: 10, HOLD: 2, CONTRACTED: 8, CANCELLED: 0 }, units: [] };

beforeEach(() => {
  responses = {};
});

describe("FieldHome 계약", () => {
  it("① grade-suggestions {customers[]}·suggested_grade 를 소비해 가망고객을 렌더(데드-와이어 방지)", async () => {
    responses["/units/board"] = BOARD_OK;
    responses["/crm/grade-suggestions"] = {
      count: 1,
      customers: [
        { name: "홍길동", phone: "01012345678", suggested_grade: "A", score: 80, reasons: ["상담 3회"], next_action: "계약 권유" },
      ],
    };
    render(<FieldHome siteCode="s1" role={MEMBER} onNavigate={() => {}} visibleTabKeys={MEMBER_TABS} />);

    expect(await screen.findByText("홍길동")).toBeTruthy();
    expect(screen.getByText("A")).toBeTruthy(); // suggested_grade 뱃지
    expect(screen.getByText("010****5678")).toBeTruthy(); // 전화 마스킹
    // '데이터 아직 없음' 거짓 빈 상태가 뜨면 안 된다.
    expect(screen.queryByText(/예측할 고객 데이터가 아직 없습니다/)).toBeNull();
  });

  it("② /units/board 실패는 0%가 아니라 정직 실패상태로 표기(무목업)", async () => {
    responses["/units/board"] = () => Promise.reject(new Error("503"));
    responses["/crm/grade-suggestions"] = { count: 0, customers: [] };
    render(<FieldHome siteCode="s1" role={MEMBER} onNavigate={() => {}} visibleTabKeys={MEMBER_TABS} />);

    expect(await screen.findByText(/핵심 지표를 불러오지 못했습니다/)).toBeTruthy();
    // 0% KPI 위장이 뜨면 안 된다.
    expect(screen.queryByText("0%")).toBeNull();
    expect(screen.queryByText("분양률")).toBeNull();
  });

  it("③ 빠른이동은 노출 탭만 — MEMBER(subscription 미노출)에 '청약·당첨' 버튼 없음", async () => {
    responses["/units/board"] = BOARD_OK;
    responses["/crm/grade-suggestions"] = { count: 0, customers: [] };
    render(<FieldHome siteCode="s1" role={MEMBER} onNavigate={() => {}} visibleTabKeys={MEMBER_TABS} />);

    // 홈 로드 완료 대기(빠른이동 섹션 렌더).
    await waitFor(() => expect(screen.getByText("빠른 이동")).toBeTruthy());
    expect(screen.queryByText("청약·당첨")).toBeNull(); // subscription 미노출 → 버튼 없음
    expect(screen.getByText("세대 배치도")).toBeTruthy(); // units 노출 → 버튼 있음
  });
});
