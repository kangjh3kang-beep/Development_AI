import { describe, it, expect } from "vitest";
import {
  buildCommentTree,
  commentStateBadge,
  canResolve,
  displayBody,
  type ReviewComment,
} from "@/lib/review-comments";

function c(over: Partial<ReviewComment> & { id: string }): ReviewComment {
  return {
    project_id: "p",
    document_id: "d",
    parent_id: null,
    anchor: null,
    author_id: "u",
    body: "본문",
    resolved: false,
    resolved_by: null,
    resolved_at: null,
    edited: false,
    status: "active",
    created_at: null,
    ...over,
  };
}

describe("buildCommentTree", () => {
  it("nests replies under parents (무제한 중첩)", () => {
    const tree = buildCommentTree([
      c({ id: "1" }),
      c({ id: "2", parent_id: "1" }),
      c({ id: "3", parent_id: "2" }),
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].children[0].id).toBe("2");
    expect(tree[0].children[0].children[0].id).toBe("3");
    expect(tree[0].children[0].children[0].depth).toBe(2);
  });

  it("keeps deleted-with-children as placeholder, drops deleted leaf", () => {
    const tree = buildCommentTree([
      c({ id: "1", status: "deleted", body: null }),
      c({ id: "2", parent_id: "1" }),
      c({ id: "9", status: "deleted", body: null }),
    ]);
    const ids = tree.map((n) => n.id);
    expect(ids).toContain("1");
    expect(ids).not.toContain("9");
    expect(tree.find((n) => n.id === "1")!.children[0].id).toBe("2");
  });

  it("promotes orphan (missing parent) to root", () => {
    const tree = buildCommentTree([c({ id: "2", parent_id: "missing" })]);
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("2");
  });
});

describe("commentStateBadge", () => {
  it("resolved → 해결됨", () => {
    expect(commentStateBadge({ resolved: true, status: "active" })?.label).toBe("해결됨");
  });
  it("deleted → 삭제됨", () => {
    expect(commentStateBadge({ resolved: false, status: "deleted" })?.label).toBe("삭제됨");
  });
  it("plain active → null", () => {
    expect(commentStateBadge({ resolved: false, status: "active" })).toBeNull();
  });
  it("deleted wins over resolved (삭제 우선)", () => {
    expect(commentStateBadge({ resolved: true, status: "deleted" })?.label).toBe("삭제됨");
  });
});

describe("canResolve / displayBody", () => {
  it("canResolve only roots", () => {
    expect(canResolve(null)).toBe(true);
    expect(canResolve("1")).toBe(false);
    expect(canResolve(undefined)).toBe(true);
  });
  it("displayBody hides deleted", () => {
    expect(displayBody({ status: "deleted", body: null })).toBe("삭제된 댓글");
    expect(displayBody({ status: "active", body: "x" })).toBe("x");
    expect(displayBody({ status: "active", body: null })).toBe("");
  });
});
