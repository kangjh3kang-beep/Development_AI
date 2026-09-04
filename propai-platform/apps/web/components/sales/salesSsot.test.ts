import { describe, it, expect } from "vitest";
import {
  UNIT_STATUSES,
  UNIT_STATUS_LABEL,
  UNIT_STATUS_CELL_CLASS,
  UNIT_STATUS_HEX,
  unitStatusLabel,
  unitStatusCellClass,
  unitStatusHex,
} from "./unitStatus";
import {
  NODE_TYPE_LABEL,
  ORG_NODE_TYPES,
  nodeTypeLabel,
  nodeTypeOptions,
  ROLE_LABEL,
} from "@/components/sales-app/roleConfig";

/**
 * 분양앱 SSOT 라벨 봉합(2026-07-22) 회귀 고정.
 * ① 세대 상태(unitStatus): 5상태 전 화면 동일 라벨/색 + 미지 상태를 '분양가능(초록)'으로 위장 안 함.
 * ② 조직 node_type(roleConfig): 백엔드 site_auth._ROLE_LABEL 정본과 byte-동일(수수료/조직도 공용).
 */

// AVAILABLE 색은 이 초록 계열이면 안 되는 폴백 검증에 쓴다.
const GREEN_CLASS = UNIT_STATUS_CELL_CLASS.AVAILABLE;
const GREEN_HEX = UNIT_STATUS_HEX.AVAILABLE;

describe("세대 상태 SSOT(unitStatus)", () => {
  it("5상태 전부 라벨·색·hex 를 갖는다(누락 없음)", () => {
    expect(UNIT_STATUSES).toEqual(["AVAILABLE", "HOLD", "APPLIED", "CONTRACTED", "CANCELLED"]);
    for (const s of UNIT_STATUSES) {
      expect(UNIT_STATUS_LABEL[s]).toBeTruthy();
      expect(UNIT_STATUS_CELL_CLASS[s]).toBeTruthy();
      expect(typeof UNIT_STATUS_HEX[s]).toBe("number");
    }
  });

  it("정본 라벨 값(전 화면 동일 표기)", () => {
    expect(UNIT_STATUS_LABEL).toEqual({
      AVAILABLE: "분양가능",
      HOLD: "지정대기",
      APPLIED: "계약대기",
      CONTRACTED: "계약완료",
      CANCELLED: "취소",
    });
  });

  it("라벨/색/hex 헬퍼는 알려진 상태를 정확히 반환", () => {
    expect(unitStatusLabel("CANCELLED")).toBe("취소");
    expect(unitStatusCellClass("CANCELLED")).toBe(UNIT_STATUS_CELL_CLASS.CANCELLED);
    expect(unitStatusHex("CONTRACTED")).toBe(UNIT_STATUS_HEX.CONTRACTED);
  });

  it("★미지 상태는 라벨=원문·색/hex=중립(분양가능 초록으로 위장 금지)", () => {
    // 실시간 보드가 3상태만 알아 CANCELLED 를 초록(AVAILABLE)으로 오표시하던 결함의 회귀 가드.
    expect(unitStatusLabel("WHATEVER")).toBe("WHATEVER");
    expect(unitStatusCellClass("WHATEVER")).not.toBe(GREEN_CLASS);
    expect(unitStatusHex("WHATEVER")).not.toBe(GREEN_HEX);
    // CANCELLED 는 이제 알려진 상태라 초록이 아니라 취소색(zinc)으로 정확히 표기된다.
    expect(unitStatusCellClass("CANCELLED")).not.toBe(GREEN_CLASS);
  });
});

describe("조직 node_type 라벨 SSOT(roleConfig)", () => {
  const EXPECTED: Record<string, string> = {
    AGENCY: "대행본사",
    SUBAGENCY: "대행지사",
    GM_DIRECTOR: "본부장",
    DIRECTOR: "이사",
    TEAM_LEADER: "팀장",
    MEMBER: "직원",
  };

  it("NODE_TYPE_LABEL == 백엔드 정본(byte-동일)", () => {
    for (const [k, v] of Object.entries(EXPECTED)) expect(NODE_TYPE_LABEL[k as keyof typeof NODE_TYPE_LABEL]).toBe(v);
  });

  it("NODE_TYPE_LABEL 은 ROLE_LABEL(로그인 역할 라벨)과 6개 전부 동일 파생", () => {
    for (const t of ORG_NODE_TYPES) expect(NODE_TYPE_LABEL[t]).toBe(ROLE_LABEL[t]);
  });

  it("nodeTypeLabel: 미등록 값은 원문 폴백", () => {
    expect(nodeTypeLabel("DIRECTOR")).toBe("이사");
    expect(nodeTypeLabel("MGM")).toBe("MGM"); // 조직 node_type 아님 → 소비처가 로컬 라벨 부여
  });

  it("nodeTypeOptions: 부분집합 선택 시 순서·라벨 유지(수수료 화면 계약)", () => {
    const opts = nodeTypeOptions(["SUBAGENCY", "DIRECTOR", "MEMBER"]);
    expect(opts).toEqual([
      { value: "SUBAGENCY", label: "대행지사" },
      { value: "DIRECTOR", label: "이사" }, // ★과거 수수료 화면은 '본부장'으로 오표시
      { value: "MEMBER", label: "직원" }, // ★과거 '팀원'
    ]);
  });
});
