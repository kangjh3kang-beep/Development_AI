/**
 * SP6 회의방 의견교환(심의 스레드) Zustand 스토어 — 문서별 댓글 상태 + /api/v2/collaboration 호출.
 *
 * 댓글은 문서(doc_id)별로 분리 보관한다(commentsByDoc). 서버는 flat 목록을 주고 트리 조립은
 * lib/review-comments.buildCommentTree(컴포넌트)가 담당한다. 수정은 PUT(apiClient putV2 — patchV2 부재).
 * 삭제는 소프트(행 유지·본문 가림)로 로컬 반영해 트리를 보존한다.
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/lib/api-client";
import type { ReviewComment } from "@/lib/review-comments";

interface ReviewCommentState {
  commentsByDoc: Record<string, ReviewComment[]>;
  loadingByDoc: Record<string, boolean>;
  errorByDoc: Record<string, string | null>;
  loadComments: (projectId: string, docId: string) => Promise<void>;
  postComment: (
    projectId: string,
    docId: string,
    input: { body: string; parentId?: string | null; anchor?: string | null },
  ) => Promise<ReviewComment | null>;
  editComment: (
    projectId: string,
    docId: string,
    commentId: string,
    body: string,
  ) => Promise<ReviewComment | null>;
  deleteComment: (projectId: string, docId: string, commentId: string) => Promise<void>;
  resolveComment: (
    projectId: string,
    docId: string,
    commentId: string,
    resolved: boolean,
  ) => Promise<ReviewComment | null>;
  reset: () => void;
}

const base = (projectId: string, docId: string) =>
  `/collaboration/projects/${projectId}/documents/${docId}/comments`;

export const useReviewCommentStore = create<ReviewCommentState>()(
  immer((set) => ({
    commentsByDoc: {},
    loadingByDoc: {},
    errorByDoc: {},

    async loadComments(projectId, docId) {
      set((s) => {
        s.loadingByDoc[docId] = true;
        s.errorByDoc[docId] = null;
      });
      try {
        const res = await apiClient.getV2<ReviewComment[]>(base(projectId, docId));
        set((s) => {
          s.commentsByDoc[docId] = res ?? [];
          s.loadingByDoc[docId] = false;
        });
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 조회 실패";
          s.loadingByDoc[docId] = false;
        });
      }
    },

    async postComment(projectId, docId, input) {
      try {
        const res = await apiClient.postV2<ReviewComment>(base(projectId, docId), {
          body: {
            body: input.body,
            parent_id: input.parentId ?? null,
            anchor: input.anchor ?? null,
          },
        });
        set((s) => {
          if (res) {
            if (!s.commentsByDoc[docId]) s.commentsByDoc[docId] = [];
            s.commentsByDoc[docId].push(res); // 서버와 동일 오래된→최신 순
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 작성 실패";
        });
        return null;
      }
    },

    async editComment(projectId, docId, commentId, body) {
      try {
        const res = await apiClient.putV2<ReviewComment>(`${base(projectId, docId)}/${commentId}`, {
          body: { body },
        });
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (res && list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) list[i] = res;
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 수정 실패";
        });
        return null;
      }
    },

    async deleteComment(projectId, docId, commentId) {
      try {
        await apiClient.deleteV2(`${base(projectId, docId)}/${commentId}`);
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) {
              // 소프트삭제 로컬 반영(immer 관용 mutation — 구조적 공유 보존)
              list[i].status = "deleted";
              list[i].body = null;
            }
          }
        });
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "댓글 삭제 실패";
        });
      }
    },

    async resolveComment(projectId, docId, commentId, resolved) {
      try {
        const res = await apiClient.postV2<ReviewComment>(
          `${base(projectId, docId)}/${commentId}/resolve`,
          { body: { resolved } },
        );
        set((s) => {
          const list = s.commentsByDoc[docId];
          if (res && list) {
            const i = list.findIndex((x) => x.id === commentId);
            if (i >= 0) list[i] = res;
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.errorByDoc[docId] = e instanceof Error ? e.message : "해결 상태 변경 실패";
        });
        return null;
      }
    },

    reset() {
      set((s) => {
        s.commentsByDoc = {};
        s.loadingByDoc = {};
        s.errorByDoc = {};
      });
    },
  })),
);
