/**
 * SP6 회의방 의견교환(심의 스레드) 프론트 순수코어 — 트리 조립·상태배지·해결가능판정.
 *
 * 백엔드 review_comments(ReviewComment)와 정합. 서버는 flat 목록(오래된→최신)을 주고, 본 모듈이
 * parent_id로 무제한 중첩 트리를 조립한다(deleted 가시성 규칙 포함). UI(컴포넌트)에서 분리해 vitest로
 * 결정론 검증한다(네트워크·DOM 무관). lib/collaboration.ts와 동형.
 */

import type { StatusTone } from "@/lib/collaboration";

export interface ReviewComment {
  id: string;
  project_id: string;
  document_id: string;
  parent_id?: string | null;
  anchor?: string | null;
  author_id?: string | null;
  body?: string | null; // soft 삭제 시 null
  resolved: boolean;
  resolved_by?: string | null;
  resolved_at?: string | null;
  edited: boolean;
  status: string; // active/deleted
  created_at?: string | null;
}

export interface ReviewCommentNode extends ReviewComment {
  children: ReviewCommentNode[];
  depth: number;
}

/** 시각 들여쓰기 상한(데이터는 무제한 중첩, 렌더 깊이만 캡). 렌더 레이어에서 Math.min(depth, INDENT_CAP)로 클램프. */
export const INDENT_CAP = 5;

/**
 * flat 목록 → 무제한 중첩 트리. 입력순(서버 created_at asc) 보존. parent 미존재 댓글은 루트로 승격.
 * 가시성: 자식 있는 deleted는 플레이스홀더로 유지, 자식 없는 deleted 잎은 제외(트리 정직 보존·캐스케이드).
 */
export function buildCommentTree(flat: ReviewComment[]): ReviewCommentNode[] {
  const nodes = new Map<string, ReviewCommentNode>();
  for (const cmt of flat) {
    nodes.set(cmt.id, { ...cmt, children: [], depth: 0 });
  }
  const roots: ReviewCommentNode[] = [];
  for (const cmt of flat) {
    const node = nodes.get(cmt.id)!;
    const parent = cmt.parent_id ? nodes.get(cmt.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const prune = (list: ReviewCommentNode[], depth: number): ReviewCommentNode[] => {
    const out: ReviewCommentNode[] = [];
    for (const n of list) {
      n.depth = depth;
      n.children = prune(n.children, depth + 1);
      const isDeletedLeaf = n.status !== "active" && n.children.length === 0;
      if (!isDeletedLeaf) out.push(n);
    }
    return out;
  };
  return prune(roots, 0);
}

/** 댓글 상태 배지 — 삭제/해결 표기(정직). 평범한 active는 배지 없음.
 *  우선순위 삭제>해결: 삭제된 스레드는 resolved 여부와 무관하게 "삭제됨"(본문이 사라졌으므로 삭제가 지배 상태). */
export function commentStateBadge(
  c: Pick<ReviewComment, "resolved" | "status">,
): { label: string; tone: StatusTone } | null {
  if (c.status !== "active") return { label: "삭제됨", tone: "muted" };
  if (c.resolved) return { label: "해결됨", tone: "ok" };
  return null;
}

/** 해결 토글 가능 여부 — 루트(부모 없음)만. */
export function canResolve(parentId: string | null | undefined): boolean {
  return parentId == null;
}

/** 본문 표시 — 삭제(soft)는 플레이스홀더, active는 원문. */
export function displayBody(c: Pick<ReviewComment, "status" | "body">): string {
  if (c.status !== "active") return "삭제된 댓글";
  return c.body ?? "";
}
