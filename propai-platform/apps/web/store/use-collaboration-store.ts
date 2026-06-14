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

interface CollaborationState {
  members: CollabMember[];
  lastInvite: CollabInvite | null;
  loading: boolean;
  error: string | null;
  loadMembers: (projectId: string) => Promise<void>;
  createInvite: (projectId: string, input: InviteInput) => Promise<CollabInvite | null>;
  revokeInvite: (projectId: string, inviteId: string) => Promise<void>;
  reset: () => void;
}

export const useCollaborationStore = create<CollaborationState>()(
  immer((set) => ({
    members: [],
    lastInvite: null,
    loading: false,
    error: null,

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

    reset() {
      set((s) => {
        s.members = [];
        s.lastInvite = null;
        s.loading = false;
        s.error = null;
      });
    },
  })),
);
