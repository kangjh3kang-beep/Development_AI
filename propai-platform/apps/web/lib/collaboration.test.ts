import { describe, it, expect } from "vitest";
import {
  roleLabel,
  categoryLabel,
  REVIEW_CATEGORIES,
  isValidEmail,
  toggleCategory,
  memberStatusBadge,
} from "./collaboration";

describe("roleLabel / categoryLabel", () => {
  it("알려진 역할/카테고리는 한글 라벨", () => {
    expect(roleLabel("external_reviewer")).toBe("외부 협력업체");
    expect(roleLabel("owner")).toBe("소유자");
    expect(categoryLabel("traffic")).toBe("교통영향평가");
    expect(categoryLabel("fire")).toBe("소방");
  });
  it("미지값은 원문 폴백(가짜 라벨 금지)", () => {
    expect(roleLabel("unknown_role")).toBe("unknown_role");
    expect(categoryLabel("xxx")).toBe("xxx");
  });
  it("REVIEW_CATEGORIES는 6종(백엔드 정합)", () => {
    expect(REVIEW_CATEGORIES).toEqual([
      "traffic", "environment", "civil", "landscape", "architecture", "fire",
    ]);
  });
});

describe("isValidEmail", () => {
  it("유효 이메일 통과", () => {
    expect(isValidEmail("vendor@traffic.co")).toBe(true);
    expect(isValidEmail(" A@B.com ")).toBe(true); // trim 허용
  });
  it("무효 이메일 거부", () => {
    expect(isValidEmail("no-at-sign")).toBe(false);
    expect(isValidEmail("@b.com")).toBe(false);
    expect(isValidEmail("a@")).toBe(false);
    expect(isValidEmail("")).toBe(false);
  });
});

describe("toggleCategory", () => {
  it("없으면 추가, 있으면 제거(순서 보존)", () => {
    expect(toggleCategory(["traffic"], "fire")).toEqual(["traffic", "fire"]);
    expect(toggleCategory(["traffic", "fire"], "traffic")).toEqual(["fire"]);
  });
  it("유효 카테고리만 추가(가짜 거부)", () => {
    expect(toggleCategory([], "hacking")).toEqual([]);
  });
});

describe("memberStatusBadge", () => {
  it("상태→라벨·톤", () => {
    expect(memberStatusBadge("active")).toEqual({ label: "활성", tone: "ok" });
    expect(memberStatusBadge("suspended")).toEqual({ label: "정지", tone: "warn" });
    expect(memberStatusBadge("removed")).toEqual({ label: "해제", tone: "muted" });
  });
  it("미지 상태는 원문·muted", () => {
    expect(memberStatusBadge("weird")).toEqual({ label: "weird", tone: "muted" });
  });
});
