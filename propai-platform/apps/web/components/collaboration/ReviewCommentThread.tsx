"use client";

/**
 * SP6 회의방 의견교환(심의 스레드) — 문서별 댓글·답변(무제한 중첩) + 루트 해결.
 *
 * 서버는 flat 목록을 주고 buildCommentTree로 트리를 조립한다(deleted 가시성 규칙 포함). resolved는
 * 문서 review_state와 별개 사람주도 트랙(자동판정 아님). 권한은 서버가 강제 — 작성자만 수정/삭제,
 * 심의자·관리자만 해결, 외부 게스트는 scope내 문서만(실패는 errorByDoc로 표면화).
 */

import { useEffect, useMemo, useState } from "react";
import { useReviewCommentStore } from "@/store/use-review-comment-store";
import {
  buildCommentTree,
  commentStateBadge,
  canResolve,
  displayBody,
  INDENT_CAP,
  type ReviewCommentNode,
} from "@/lib/review-comments";

const TONE_CLASS: Record<string, string> = {
  ok: "text-[var(--status-success)]",
  warn: "text-[var(--status-warning)]",
  muted: "text-[var(--text-hint)]",
};

function CommentNode({
  node,
  projectId,
  docId,
}: {
  node: ReviewCommentNode;
  projectId: string;
  docId: string;
}) {
  const { postComment, editComment, deleteComment, resolveComment } = useReviewCommentStore();
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editText, setEditText] = useState(node.body ?? "");
  const badge = commentStateBadge(node);
  const isDeleted = node.status !== "active";
  const indent = Math.min(node.depth, INDENT_CAP) * 16;

  const submitReply = async () => {
    if (!replyText.trim()) return;
    await postComment(projectId, docId, { body: replyText, parentId: node.id });
    setReplyText("");
    setReplyOpen(false);
  };
  const submitEdit = async () => {
    if (!editText.trim()) return;
    await editComment(projectId, docId, node.id, editText);
    setEditOpen(false);
  };

  return (
    <li data-testid="review-comment" className="list-none">
      <div
        className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
        style={{ marginLeft: indent }}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[10px] text-[var(--text-hint)]">
            {node.anchor && (
              <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-bold text-[var(--text-secondary)]">
                지적 {node.anchor}
              </span>
            )}
            {node.edited && !isDeleted && <span>수정됨</span>}
            {badge && <span className={`font-black ${TONE_CLASS[badge.tone]}`}>{badge.label}</span>}
          </div>
          {!isDeleted && (
            <div className="flex shrink-0 items-center gap-2 text-[10px] font-bold">
              <button
                type="button"
                onClick={() => setReplyOpen((v) => !v)}
                className="text-[var(--accent-strong)]"
              >
                답변
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditOpen((v) => !v);
                  setEditText(node.body ?? "");
                }}
                className="text-[var(--text-secondary)]"
              >
                수정
              </button>
              <button
                type="button"
                onClick={() => void deleteComment(projectId, docId, node.id)}
                className="text-[var(--status-error)]"
              >
                삭제
              </button>
              {canResolve(node.parent_id) && (
                <button
                  type="button"
                  onClick={() => void resolveComment(projectId, docId, node.id, !node.resolved)}
                  className="text-[var(--text-secondary)]"
                >
                  {node.resolved ? "재오픈" : "해결"}
                </button>
              )}
            </div>
          )}
        </div>
        {editOpen && !isDeleted ? (
          <div className="mt-1 flex gap-1">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
            />
            <button
              type="button"
              onClick={() => void submitEdit()}
              className="rounded bg-[var(--accent-strong)] px-2 text-[10px] font-bold text-white"
            >
              저장
            </button>
          </div>
        ) : (
          <p
            className={`mt-1 whitespace-pre-wrap text-xs ${
              isDeleted ? "italic text-[var(--text-hint)]" : "text-[var(--text-primary)]"
            }`}
          >
            {displayBody(node)}
          </p>
        )}
        {replyOpen && (
          <div className="mt-1 flex gap-1">
            <input
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="답변 입력…"
              className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
            />
            <button
              type="button"
              onClick={() => void submitReply()}
              className="rounded bg-[var(--accent-strong)] px-2 text-[10px] font-bold text-white"
            >
              등록
            </button>
          </div>
        )}
      </div>
      {node.children.length > 0 && (
        <ul className="mt-1 flex flex-col gap-1">
          {node.children.map((ch) => (
            <CommentNode key={ch.id} node={ch} projectId={projectId} docId={docId} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ReviewCommentThread({ projectId, docId }: { projectId: string; docId: string }) {
  const { commentsByDoc, loadingByDoc, errorByDoc, loadComments, postComment } =
    useReviewCommentStore();
  const [rootText, setRootText] = useState("");
  const [anchor, setAnchor] = useState("");

  useEffect(() => {
    void loadComments(projectId, docId);
  }, [projectId, docId, loadComments]);

  const flat = commentsByDoc[docId] ?? [];
  const tree = useMemo(() => buildCommentTree(flat), [flat]);

  const submitRoot = async () => {
    if (!rootText.trim()) return;
    await postComment(projectId, docId, { body: rootText, anchor: anchor.trim() || null });
    setRootText("");
    setAnchor("");
  };

  return (
    <div data-testid="review-comment-thread" className="mt-2 border-t border-[var(--line)] pt-2">
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <input
          data-testid="review-comment-anchor"
          value={anchor}
          onChange={(e) => setAnchor(e.target.value)}
          placeholder="지적 앵커(선택)"
          className="w-28 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-[11px]"
        />
        <input
          data-testid="review-comment-input"
          value={rootText}
          onChange={(e) => setRootText(e.target.value)}
          placeholder="의견을 입력하세요…"
          className="flex-1 rounded border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs"
        />
        <button
          type="button"
          data-testid="review-comment-submit"
          onClick={() => void submitRoot()}
          className="rounded bg-[var(--accent-strong)] px-3 py-1 text-[11px] font-black text-white"
        >
          등록
        </button>
      </div>
      {tree.length === 0 ? (
        <p className="text-[11px] text-[var(--text-hint)]">
          {loadingByDoc[docId] ? "불러오는 중…" : "아직 의견이 없습니다."}
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {tree.map((n) => (
            <CommentNode key={n.id} node={n} projectId={projectId} docId={docId} />
          ))}
        </ul>
      )}
      {errorByDoc[docId] && (
        <p data-testid="review-comment-error" className="mt-1 text-[11px] text-[var(--status-error)]">
          {errorByDoc[docId]}
        </p>
      )}
    </div>
  );
}
