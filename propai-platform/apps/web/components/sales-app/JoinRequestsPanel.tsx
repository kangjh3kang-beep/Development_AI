"use client";

/**
 * Stage 2 — **승인자 화면**: 현장에 들어온 등록신청을 보고 수락/거절한다.
 *
 * ## 왜 (2026-09-09 · 적대 리뷰 B-4)
 *
 * 앞 판은 백엔드 엔드포인트 5개를 만들고 **3개를 아무도 안 불렀다**:
 * 신청 목록 · 결정 · 취소. 사용자 요구 원문은
 * *"…등록신청을 하고 **관리자 및 상위레벨이 승인할경우**…"* 인데,
 * 승인 화면이 없으면 **파이프라인이 완결되지 않는다.**
 *
 * ★더 나쁜 자리: `decide` 는 `membership_reason` 을 돌려주는데 **읽는 쪽이 없었다.**
 *   조직도가 없는 현장에서 승인하면 — 신청은 `approved` 가 되고, 멤버십은 안 생기고,
 *   사유는 어디에도 안 뜬다. **승인자는 승인했다고 믿고, 신청자는 아무 일도 없었다고 본다.**
 *   그 유령 상태를 막겠다고 백엔드에 사유를 만들어 놓고 표면에 안 실은 것이다.
 *   저장소에 이미 그 사유를 사람 말로 옮기는 **공용 모듈**이 있다(`lib/sales-app/membership-reason`)
 *   — 형제 문(`JobMarketPanel`)은 그것을 쓴다. 이 문도 **같은 것**을 쓴다.
 */
import { useCallback, useEffect, useState } from "react";
import { Check, X, Users } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { membershipNote } from "@/lib/sales-app/membership-reason";

export interface JoinRequestRow {
  request_id: string;
  user_id: string;
  name?: string | null;
  email?: string | null;
  message?: string | null;
  status: string;
  created_at?: string | null;
}

export default function JoinRequestsPanel({ siteId }: { siteId: string }) {
  const [rows, setRows] = useState<JoinRequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busyId, setBusyId] = useState("");
  /** 승인 권한이 없으면 이 패널 자체를 그리지 않는다(403 을 오류로 보여 주지 않는다). */
  const [allowed, setAllowed] = useState(true);

  const load = useCallback(() => {
    apiClient
      .get<{ items?: JoinRequestRow[] }>(`/sales/sites/${siteId}/join-requests`)
      .then((r) => {
        setRows(r?.items ?? []);
        setErr("");
        setAllowed(true);
      })
      .catch((e) => {
        // 403 = 승인자가 아니다. 그건 오류가 아니라 **이 화면이 내 것이 아니라는 뜻**이다.
        if ((e as { status?: number })?.status === 403) setAllowed(false);
        else setErr("신청 목록을 불러오지 못했습니다.");
      })
      .finally(() => setLoading(false));
  }, [siteId]);

  useEffect(() => {
    load();
  }, [load]);

  const decide = (requestId: string, approve: boolean) => {
    setBusyId(requestId);
    setNote("");
    apiClient
      .post<{ membership_linked?: boolean; membership_reason?: string }>(
        `/sales/join-requests/${requestId}/decide`,
        { body: { approve } },
      )
      .then((r) => {
        // ★★승인했는데 멤버십이 안 붙었으면 **왜인지 말한다.**
        //   조용히 넘어가면 «승인했는데 조직도엔 아무도 없는» 유령 상태가 된다.
        if (approve && r?.membership_linked === false) {
          setNote(membershipNote(r?.membership_reason));
        }
        return load();
      })
      .catch(() => setErr("처리에 실패했습니다."))
      .finally(() => setBusyId(""));
  };

  if (!allowed) return null;
  if (loading) return <div className="sa-skeleton h-20 rounded-2xl" />;

  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-base font-black text-[var(--text-primary)]">등록신청 대기</h2>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          수락하면 내 조직 아래에 배치됩니다
        </span>
      </div>

      {err && <p className="text-sm font-semibold text-[var(--status-error)]">{err}</p>}
      {note && <p className="text-sm font-semibold text-amber-300">{note}</p>}

      {rows.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)]">대기 중인 등록신청이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li
              key={r.request_id}
              className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-3"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[var(--surface-soft)] text-[var(--text-tertiary)]">
                <Users className="size-4" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <b className="block truncate text-sm text-[var(--text-primary)]">
                  {r.name || r.email || "신청자"}
                </b>
                {r.message && (
                  <span className="block truncate text-[11px] text-[var(--text-tertiary)]">
                    {r.message}
                  </span>
                )}
              </span>
              <button
                onClick={() => decide(r.request_id, true)}
                disabled={busyId === r.request_id}
                className="flex shrink-0 items-center gap-1 rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-black text-white transition hover:opacity-90 disabled:opacity-50"
              >
                <Check className="size-3.5" aria-hidden /> 수락
              </button>
              <button
                onClick={() => decide(r.request_id, false)}
                disabled={busyId === r.request_id}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-[var(--line)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] disabled:opacity-50"
              >
                <X className="size-3.5" aria-hidden /> 거절
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
