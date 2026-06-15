"use client";

/**
 * SP2 프로젝트 회의방(F3) — 팀·협력업체 명부 + 외부 협력업체(심의) 초대.
 * 화상회의(LiveKit)·자료교환·의견교환·심의검증은 후속(Phase 2/3) — 정직 플레이스홀더.
 */

import { useEffect, useState } from "react";
import { useCollaborationStore } from "@/store/use-collaboration-store";
import { ProjectCollaborationDocumentExchange } from "@/components/collaboration/ProjectCollaborationDocumentExchange";
import { LiveKitRoom } from "@/features/webrtc/LiveKitRoom";
import {
  REVIEW_CATEGORIES,
  roleLabel,
  categoryLabel,
  isValidEmail,
  toggleCategory,
  memberStatusBadge,
} from "@/lib/collaboration";

const TONE_CLASS: Record<string, string> = {
  ok: "text-[var(--status-success)]",
  warn: "text-[var(--status-warning)]",
  muted: "text-[var(--text-hint)]",
};

export function ProjectCollaborationWorkspaceClient({ projectId }: { projectId: string }) {
  const { members, lastInvite, loading, error, loadMembers, createInvite } =
    useCollaborationStore();

  const [email, setEmail] = useState("");
  const [cats, setCats] = useState<string[]>([]);
  const [ttl, setTtl] = useState(14);

  useEffect(() => {
    void loadMembers(projectId);
  }, [projectId, loadMembers]);

  const emailOk = isValidEmail(email);

  const submit = async () => {
    if (!emailOk) return;
    await createInvite(projectId, { email: email.trim(), scope_categories: cats, ttl_days: ttl });
    setEmail("");
    setCats([]);
  };

  return (
    <div data-testid="collab-workspace" className="flex flex-col gap-8">
      {/* 팀·협력업체 명부 */}
      <section
        data-testid="collab-roster"
        className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6"
      >
        <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">팀 · 협력업체 명부</h3>
        {members.length === 0 ? (
          <p className="text-xs text-[var(--text-hint)]">
            {loading ? "불러오는 중…" : "아직 등록된 멤버가 없습니다."}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {members.map((m) => {
              const badge = memberStatusBadge(m.status);
              return (
                <li
                  key={m.id}
                  className="flex items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs"
                >
                  <span className="font-bold text-[var(--text-primary)]">{roleLabel(m.project_role)}</span>
                  <span className="text-[var(--text-hint)]">{m.user_id ?? "—"}</span>
                  <span className={`font-black ${TONE_CLASS[badge.tone]}`}>{badge.label}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 외부 협력업체 초대(심의) */}
      <section
        data-testid="collab-invite"
        className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6"
      >
        <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">외부 협력업체 초대 (심의)</h3>

        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          협력업체 이메일
        </label>
        <input
          data-testid="collab-invite-email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="예) traffic@vendor.co.kr"
          className="mb-1 w-full max-w-md rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm"
        />
        {email && !emailOk && (
          <p className="mb-2 text-[11px] text-[var(--status-error)]">유효한 이메일을 입력하세요.</p>
        )}

        <p className="mb-1 mt-3 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          접근 허용 심의 카테고리
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {REVIEW_CATEGORIES.map((c) => (
            <label
              key={c}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-[var(--line)] px-3 py-1 text-[11px]"
            >
              <input
                type="checkbox"
                checked={cats.includes(c)}
                onChange={() => setCats(toggleCategory(cats, c))}
              />
              {categoryLabel(c)}
            </label>
          ))}
        </div>

        <div className="mb-3 flex items-center gap-2 text-xs">
          <span className="text-[var(--text-hint)]">만료</span>
          <input
            type="number"
            min={1}
            max={90}
            value={ttl}
            onChange={(e) => setTtl(Math.max(1, Math.min(90, Number(e.target.value) || 14)))}
            className="w-16 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1"
          />
          <span className="text-[var(--text-hint)]">일 후</span>
        </div>

        <button
          type="button"
          data-testid="collab-invite-submit"
          disabled={!emailOk || loading}
          onClick={submit}
          className="rounded-lg bg-[var(--accent-strong)] px-5 py-2 text-[11px] font-black uppercase tracking-widest text-white disabled:opacity-40"
        >
          {loading ? "발급 중…" : "초대 발급"}
        </button>

        {lastInvite?.invite_token && (
          <div
            data-testid="collab-invite-token"
            className="mt-3 rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-3 text-xs"
          >
            <p className="font-black text-[var(--accent-strong)]">초대 링크 토큰(1회 노출 — 협력업체에 공유)</p>
            <p className="mt-1 break-all font-mono text-[var(--text-primary)]">{lastInvite.invite_token}</p>
            <p className="mt-1 text-[var(--text-hint)]">
              허용 카테고리: {lastInvite.scope_categories.map(categoryLabel).join(", ") || "없음"} ·{" "}
              만료 {new Date(lastInvite.expires_at).toLocaleDateString()}
            </p>
          </div>
        )}
      </section>

      {/* SP3 자료교환(협력업체 업로드자료) + 정직 8엔진 검증·표기용 심의상태 + 의견교환(SP6 토글) */}
      <ProjectCollaborationDocumentExchange projectId={projectId} />

      {/* LiveKit 화상회의 — 구성(키) 시 동작, 미구성 시 입장에서 정직 degrade */}
      <LiveKitRoom projectId={projectId} />

      {/* 정직 표기 — 자료교환·8엔진 검증·의견교환은 위 제공, 화상회의는 LiveKit 구성 시 동작 */}
      <p className="text-[11px] text-[var(--text-hint)]">
        ※ 화상회의는 LiveKit 구성(관리자) 후 동작합니다. 자료교환·설계파일 8엔진 자동검증·의견교환은
        위에서 제공됩니다(문서형식은 심의자 표기용).
      </p>

      {error && (
        <p data-testid="collab-error" className="text-xs text-[var(--status-error)]">
          {error}
        </p>
      )}
    </div>
  );
}
