/**
 * SP2 프로젝트 회의방(F3) Zustand 스토어 — 멤버/초대 상태 + /api/v2/collaboration 호출.
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/lib/api-client";

export interface CollabMember {
  id: string;
  project_id: string;
  user_id: string | null;
  project_role: string;
  status: string;
  created_at?: string | null;
}

export interface CollabInvite {
  id?: string | null;
  project_id: string;
  email: string;
  project_role: string;
  scope_categories: string[];
  status: string;
  expires_at: string;
  invite_token?: string | null; // 생성 직후 1회만 노출(공유용)
}

export interface InviteInput {
  email: string;
  project_role?: string;
  scope_categories: string[];
  ttl_days?: number;
}

export interface CollabDocument {
  id: string;
  project_id: string;
  uploaded_by: string | null;
  original_filename: string;
  content_type?: string | null;
  size_bytes?: number | null;
  category?: string | null;
  purpose: string; // analysis(8엔진) / storage(공유·저장)
  doc_kind: string; // design(DXF/IFC, 8엔진 대상) / document(표기용)
  audit_status?: string | null; // pending/completed/skipped/unsupported/failed
  audit_summary?: Record<string, unknown> | null;
  review_state: string; // requested/acknowledged/addressed(표기용·자동판정 아님)
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  file_url?: string | null; // 비공개버킷 서명URL(TTL 후 만료)
  created_at?: string | null;
}

interface CollaborationState {
  members: CollabMember[];
  lastInvite: CollabInvite | null;
  loading: boolean;
  error: string | null;
  // SP3 자료교환
  documents: CollabDocument[];
  docLoading: boolean;
  docError: string | null;
  loadMembers: (projectId: string) => Promise<void>;
  createInvite: (projectId: string, input: InviteInput) => Promise<CollabInvite | null>;
  revokeInvite: (projectId: string, inviteId: string) => Promise<void>;
  loadDocuments: (projectId: string) => Promise<void>;
  uploadDocument: (
    projectId: string,
    file: File,
    category?: string,
    purpose?: string,
  ) => Promise<CollabDocument | null>;
  deleteDocument: (projectId: string, docId: string) => Promise<void>;
  setDocReviewState: (
    projectId: string,
    docId: string,
    target: string,
  ) => Promise<CollabDocument | null>;
  reset: () => void;
}

export const useCollaborationStore = create<CollaborationState>()(
  immer((set) => ({
    members: [],
    lastInvite: null,
    loading: false,
    error: null,
    documents: [],
    docLoading: false,
    docError: null,

    async loadMembers(projectId) {
      set((s) => {
        s.loading = true;
        s.error = null;
      });
      try {
        const res = await apiClient.getV2<CollabMember[]>(
          `/collaboration/projects/${projectId}/members`,
        );
        set((s) => {
          s.members = res ?? [];
          s.loading = false;
        });
      } catch (e: unknown) {
        set((s) => {
          s.error = e instanceof Error ? e.message : "멤버 조회 실패";
          s.loading = false;
        });
      }
    },

    async createInvite(projectId, input) {
      set((s) => {
        s.loading = true;
        s.error = null;
      });
      try {
        const res = await apiClient.postV2<CollabInvite>(
          `/collaboration/projects/${projectId}/invites`,
          {
            body: {
              email: input.email,
              project_role: input.project_role ?? "external_reviewer",
              scope_categories: input.scope_categories,
              ttl_days: input.ttl_days ?? 14,
            },
          },
        );
        set((s) => {
          s.lastInvite = res;
          s.loading = false;
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.error = e instanceof Error ? e.message : "초대 발급 실패";
          s.loading = false;
        });
        return null;
      }
    },

    async revokeInvite(projectId, inviteId) {
      set((s) => {
        s.loading = true;
        s.error = null;
      });
      try {
        await apiClient.postV2(
          `/collaboration/projects/${projectId}/invites/${inviteId}/revoke`,
        );
        set((s) => {
          s.loading = false;
        });
      } catch (e: unknown) {
        set((s) => {
          s.error = e instanceof Error ? e.message : "초대 회수 실패";
          s.loading = false;
        });
      }
    },

    // ── SP3 자료교환 ──

    async loadDocuments(projectId) {
      set((s) => {
        s.docLoading = true;
        s.docError = null;
      });
      try {
        const res = await apiClient.getV2<CollabDocument[]>(
          `/collaboration/projects/${projectId}/documents`,
        );
        set((s) => {
          s.documents = res ?? [];
          s.docLoading = false;
        });
      } catch (e: unknown) {
        set((s) => {
          s.docError = e instanceof Error ? e.message : "문서 조회 실패";
          s.docLoading = false;
        });
      }
    },

    async uploadDocument(projectId, file, category, purpose) {
      set((s) => {
        s.docLoading = true;
        s.docError = null;
      });
      try {
        const fd = new FormData();
        fd.append("file", file);
        if (category) fd.append("category", category);
        if (purpose) fd.append("purpose", purpose);
        const res = await apiClient.postV2<CollabDocument>(
          `/collaboration/projects/${projectId}/documents`,
          { body: fd },
        );
        set((s) => {
          if (res) s.documents.unshift(res); // 최신순(목록과 동일)
          s.docLoading = false;
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.docError = e instanceof Error ? e.message : "문서 업로드 실패";
          s.docLoading = false;
        });
        return null;
      }
    },

    async deleteDocument(projectId, docId) {
      try {
        await apiClient.deleteV2(
          `/collaboration/projects/${projectId}/documents/${docId}`,
        );
        set((s) => {
          s.documents = s.documents.filter((d) => d.id !== docId);
        });
      } catch (e: unknown) {
        set((s) => {
          s.docError = e instanceof Error ? e.message : "문서 삭제 실패";
        });
      }
    },

    async setDocReviewState(projectId, docId, target) {
      try {
        const res = await apiClient.postV2<CollabDocument>(
          `/collaboration/projects/${projectId}/documents/${docId}/review-state`,
          { body: { target_state: target } },
        );
        set((s) => {
          if (res) {
            const i = s.documents.findIndex((d) => d.id === docId);
            if (i >= 0) s.documents[i] = res;
          }
        });
        return res;
      } catch (e: unknown) {
        set((s) => {
          s.docError = e instanceof Error ? e.message : "심의 상태 변경 실패";
        });
        return null;
      }
    },

    reset() {
      set((s) => {
        s.members = [];
        s.lastInvite = null;
        s.loading = false;
        s.error = null;
        s.documents = [];
        s.docLoading = false;
        s.docError = null;
      });
    },
  })),
);
