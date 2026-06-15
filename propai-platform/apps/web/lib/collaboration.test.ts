import { describe, it, expect } from "vitest";
import {
  roleLabel,
  categoryLabel,
  REVIEW_CATEGORIES,
  isValidEmail,
  toggleCategory,
  memberStatusBadge,
  isDesignKind,
  purposeLabel,
  auditStatusBadge,
  reviewStateBadge,
  nextReviewState,
  formatBytes,
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
  it("REVIEW_CATEGORIES는 8종(백엔드 정합 — 건축설계·도시계획 추가)", () => {
    expect(REVIEW_CATEGORIES).toEqual([
      "traffic", "environment", "civil", "landscape", "architecture", "fire",
      "architectural_design", "urban_planning",
    ]);
  });
  it("추가 카테고리 라벨", () => {
    expect(categoryLabel("architectural_design")).toBe("건축설계");
    expect(categoryLabel("urban_planning")).toBe("도시계획");
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

describe("isDesignKind", () => {
  it("design만 8엔진 대상", () => {
    expect(isDesignKind("design")).toBe(true);
    expect(isDesignKind("document")).toBe(false);
  });
});

describe("purposeLabel", () => {
  it("용도 라벨", () => {
    expect(purposeLabel("analysis")).toBe("분석용 (8엔진)");
    expect(purposeLabel("storage")).toBe("저장·공유용");
    expect(purposeLabel("weird")).toBe("저장·공유용"); // 미지→저장·공유용
  });
});

describe("auditStatusBadge", () => {
  it("상태→배지", () => {
    expect(auditStatusBadge("completed")).toEqual({ label: "8엔진 검증완료", tone: "ok" });
    expect(auditStatusBadge("failed")).toEqual({ label: "검증 실패", tone: "warn" });
    expect(auditStatusBadge("unsupported")).toEqual({
      label: "자동검증 미지원 형식",
      tone: "muted",
    });
  });
  it("null/미지는 배지 없음(과대표기 금지)", () => {
    expect(auditStatusBadge(null)).toBeNull();
    expect(auditStatusBadge(undefined)).toBeNull();
    expect(auditStatusBadge("weird")).toBeNull();
  });
});

describe("reviewStateBadge / nextReviewState", () => {
  it("심의 상태→배지(표기용)", () => {
    expect(reviewStateBadge("requested")).toEqual({ label: "검토요청", tone: "warn" });
    expect(reviewStateBadge("acknowledged")).toEqual({ label: "확인됨", tone: "muted" });
    expect(reviewStateBadge("addressed")).toEqual({ label: "처리완료", tone: "ok" });
  });
  it("다음 상태는 전진 전용(백엔드 규칙 정합)", () => {
    expect(nextReviewState("requested")).toBe("acknowledged");
    expect(nextReviewState("acknowledged")).toBe("addressed");
    expect(nextReviewState("addressed")).toBeNull(); // 종료
    expect(nextReviewState("weird")).toBeNull();
  });
});

describe("formatBytes", () => {
  it("사람이 읽는 크기", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
  it("비정상은 —", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(-1)).toBe("—");
  });
});
