"use client";

/**
 * Phase 1-D — 고객카드 상세 드로어.
 *   · GET  /sales/customers/{id}/history  → 시간순 타임라인(상담/방문/단계변경/문자/메모 아이콘 구분)
 *   · POST /sales/customers/{id}/history  → 기록 추가(kind: consult/visit/note/stage[+stage_to])
 *   · POST /sales/customers/{id}/message  → 문자/알림톡 발송(status SENT/BLOCKED/SKIPPED + blocked_reason)
 *
 * 컨텍스트: 현장별(scope=site)에서만 평문 상세 노출. salesApi(siteCode)로 X-Site-Token 자동첨부.
 * 통합(scope=all) 마스킹 카드는 드로어를 열지 않고 "현장 진입 후 열람" 유도(부모 CrmPanel 처리).
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";

export interface HistoryItem {
  id?: string;
  kind: string; // consult | visit | stage | message | note
  content?: string | null;
  stage_from?: string | null;
  stage_to?: string | null;
  status?: string | null; // message 결과(SENT/BLOCKED/SKIPPED) 동반 시
  channel?: string | null;
  created_at?: string | null;
  actor?: string | null;
}

interface MessageResult {
  status?: string; // SENT | BLOCKED | SKIPPED | FAILED
  blocked_reason?: string | null;
  opt_out_notice?: string | null;
}

// 단계(status) 화이트리스트 — 백엔드 _STAGES 정합(stage_to 전송용).
const STAGES: { key: string; label: string }[] = [
  { key: "LEAD", label: "리드" },
  { key: "CONSULT", label: "상담" },
  { key: "VISIT", label: "방문" },
  { key: "RESERVED", label: "예약" },
  { key: "SIGNED", label: "계약" },
  { key: "MIDDLE", label: "중도금" },
  { key: "BALANCE", label: "잔금" },
  { key: "LOST", label: "이탈" },
];
const STAGE_LABEL: Record<string, string> = Object.fromEntries(STAGES.map((s) => [s.key, s.label]));

const KIND_META: Record<string, { icon: string; label: string; cls: string }> = {
  consult: { icon: "💬", label: "상담", cls: "border-sky-500/40 bg-sky-500/10 text-sky-300" },
  visit: { icon: "🚶", label: "방문", cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  stage: { icon: "🔀", label: "단계변경", cls: "border-violet-500/40 bg-violet-500/10 text-violet-300" },
  message: { icon: "✉️", label: "문자/알림톡", cls: "border-amber-500/40 bg-amber-500/10 text-amber-300" },
  note: { icon: "📝", label: "메모", cls: "border-slate-500/40 bg-slate-500/10 text-slate-300" },
};

// 차단/스킵 사유 친화 라벨(정보통신망법 제50조 안내).
const BLOCK_REASON: Record<string, string> = {
  no_consent: "수신동의 없음 — 마케팅 수신동의 후 발송 가능합니다.",
  consent: "수신동의 없음 — 마케팅 수신동의 후 발송 가능합니다.",
  night: "야간 광고 제한(21~08시) — 주간에 발송하세요.",
  night_block: "야간 광고 제한(21~08시) — 주간에 발송하세요.",
  no_sender: "발신번호 미등록 — 발신프로필 등록 후 발송됩니다.",
  sender: "발신번호 미등록 — 발신프로필 등록 후 발송됩니다.",
  no_key: "발송 채널 미설정 — 키 등록 전까지 기록만 보관됩니다.",
};
function friendlyReason(reason?: string | null): string {
  if (!reason) return "발송이 처리되지 않았습니다.";
  return BLOCK_REASON[reason] ?? reason;
}

const KINDS: { key: string; label: string }[] = [
  { key: "consult", label: "상담" },
  { key: "visit", label: "방문" },
  { key: "note", label: "메모" },
  { key: "stage", label: "단계변경" },
];

const fcls =
  "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

function fmtTime(s?: string | null): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function CustomerCardDrawer({
  siteCode,
  customerId,
  customerName,
  onClose,
  onChanged,
}: {
  siteCode: string;
  customerId: string;
  customerName?: string | null;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const api = salesApi(siteCode);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // 기록 추가 폼
  const [kind, setKind] = useState("consult");
  const [content, setContent] = useState("");
  const [stageTo, setStageTo] = useState("CONSULT");
  const [saving, setSaving] = useState(false);

  // 문자 발송 폼
  const [channel, setChannel] = useState<"sms" | "alimtalk">("sms");
  const [template, setTemplate] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ tone: "ok" | "warn" | "err"; text: string } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      // 백엔드는 활동 이력을 `timeline` 키로 준다(예전엔 history/items만 읽어 항상 빈 타임라인이었음).
      .get<{ timeline?: HistoryItem[]; history?: HistoryItem[]; items?: HistoryItem[] }>(`/customers/${customerId}/history`)
      .then((r) => {
        setItems(r.timeline ?? r.history ?? r.items ?? []);
        setErr("");
      })
      .catch(() => setErr("히스토리를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode, customerId]);

  useEffect(() => {
    load();
  }, [load]);

  const addHistory = async () => {
    if (kind !== "stage" && !content.trim()) {
      setToast({ tone: "warn", text: "내용을 입력하세요." });
      return;
    }
    setSaving(true);
    try {
      await api.post(`/customers/${customerId}/history`, {
        kind,
        content: content.trim() || undefined,
        stage_to: kind === "stage" ? stageTo : undefined,
      });
      setContent("");
      load();
      onChanged?.();
      setToast({ tone: "ok", text: "기록이 추가되었습니다." });
    } catch {
      setToast({ tone: "err", text: "기록 추가에 실패했습니다." });
    } finally {
      setSaving(false);
    }
  };

  const sendMessage = async () => {
    if (!body.trim()) {
      setToast({ tone: "warn", text: "본문을 입력하세요." });
      return;
    }
    setSending(true);
    try {
      const r = await api.post<MessageResult>(`/customers/${customerId}/message`, {
        channel,
        template: template.trim() || undefined,
        body: body.trim(),
      });
      const status = (r.status || "").toUpperCase();
      if (status === "SENT") {
        setToast({ tone: "ok", text: "발송되었습니다." });
        setBody("");
        setTemplate("");
      } else if (status === "BLOCKED") {
        setToast({ tone: "warn", text: `발송 차단: ${friendlyReason(r.blocked_reason)}` });
      } else if (status === "SKIPPED") {
        setToast({ tone: "warn", text: `발송 보류: ${friendlyReason(r.blocked_reason)}` });
      } else {
        setToast({ tone: "err", text: "발송 실패 — 잠시 후 다시 시도하세요." });
      }
      load();
      onChanged?.();
    } catch {
      setToast({ tone: "err", text: "발송 요청에 실패했습니다." });
    } finally {
      setSending(false);
    }
  };

  const toastCls =
    toast?.tone === "ok"
      ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
      : toast?.tone === "warn"
        ? "border-amber-400/40 bg-amber-500/10 text-amber-300"
        : "border-rose-400/40 bg-rose-500/10 text-rose-300";

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="닫기"
        onClick={onClose}
        className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
      />
      <div className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-[var(--line)] bg-[var(--surface)] p-4 shadow-[var(--shadow-lg)] sm:p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-black text-[var(--text-primary)]">
            {customerName || "고객"} <span className="text-xs font-normal text-[var(--text-tertiary)]">상세</span>
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1 text-xs font-bold text-[var(--text-secondary)]"
          >
            닫기
          </button>
        </div>

        {toast && (
          <div className={`mb-3 rounded-lg border px-3 py-2 text-xs font-semibold ${toastCls}`} role="status">
            {toast.text}
          </div>
        )}

        {/* 문자/알림톡 발송 */}
        <section className="mb-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <h3 className="mb-2 text-sm font-black text-[var(--text-primary)]">✉️ 문자 / 알림톡 발송</h3>
          <div className="mb-2 flex gap-2">
            {(["sms", "alimtalk"] as const).map((c) => (
              <button
                key={c}
                onClick={() => setChannel(c)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                  channel === c
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line)] text-[var(--text-secondary)]"
                }`}
              >
                {c === "sms" ? "문자(SMS)" : "알림톡"}
              </button>
            ))}
          </div>
          {channel === "alimtalk" && (
            <input
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="템플릿 코드(선택)"
              className={`${fcls} mb-2 w-full`}
            />
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="발송 본문을 입력하세요."
            rows={3}
            className={`${fcls} w-full resize-y`}
          />
          <button
            onClick={sendMessage}
            disabled={sending}
            className="mt-2 w-full rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-black text-white disabled:opacity-50"
          >
            {sending ? "발송 중…" : "발송"}
          </button>
          <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-hint)]">
            정보통신망법 제50조: 마케팅 수신동의·야간(21~08시) 광고제한·발신번호 사전등록이 확인된 경우에만 발송됩니다.
            미충족 시 차단/보류되며 기록만 남습니다(수신거부 080 안내 포함).
          </p>
        </section>

        {/* 기록 추가 */}
        <section className="mb-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <h3 className="mb-2 text-sm font-black text-[var(--text-primary)]">＋ 기록 추가</h3>
          <div className="mb-2 flex flex-wrap gap-2">
            {KINDS.map((k) => (
              <button
                key={k.key}
                onClick={() => setKind(k.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                  kind === k.key
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line)] text-[var(--text-secondary)]"
                }`}
              >
                {k.label}
              </button>
            ))}
          </div>
          {kind === "stage" && (
            <select value={stageTo} onChange={(e) => setStageTo(e.target.value)} className={`${fcls} mb-2 w-full`}>
              {STAGES.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          )}
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={kind === "stage" ? "변경 사유(선택)" : "내용을 입력하세요."}
            rows={2}
            className={`${fcls} w-full resize-y`}
          />
          <button
            onClick={addHistory}
            disabled={saving}
            className="mt-2 w-full rounded-lg border border-[var(--accent-strong)] px-3 py-2 text-sm font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)] disabled:opacity-50"
          >
            {saving ? "저장 중…" : "기록 추가"}
          </button>
        </section>

        {/* 타임라인 */}
        <section>
          <h3 className="mb-2 text-sm font-black text-[var(--text-primary)]">🕑 활동 타임라인</h3>
          {loading ? (
            <div className="h-16 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ) : err ? (
            <p className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-300">
              {err}
            </p>
          ) : items.length === 0 ? (
            <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-4 text-xs text-[var(--text-secondary)]">
              기록이 없습니다. 위에서 상담·방문·메모를 추가하세요.
            </p>
          ) : (
            <ol className="space-y-2">
              {items.map((it, i) => {
                const m = KIND_META[it.kind] ?? { icon: "•", label: it.kind, cls: "border-[var(--line)] text-[var(--text-secondary)]" };
                return (
                  <li
                    key={it.id ?? i}
                    className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-2.5"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-black ${m.cls}`}>
                        {m.icon} {m.label}
                      </span>
                      {it.kind === "stage" && (
                        <span className="text-[11px] text-[var(--text-secondary)]">
                          {STAGE_LABEL[it.stage_from ?? ""] ?? it.stage_from ?? "?"} →{" "}
                          <b className="text-[var(--text-primary)]">
                            {STAGE_LABEL[it.stage_to ?? ""] ?? it.stage_to ?? "?"}
                          </b>
                        </span>
                      )}
                      {it.kind === "message" && it.status && (
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                            it.status.toUpperCase() === "SENT"
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-amber-500/15 text-amber-300"
                          }`}
                        >
                          {it.channel ? `${it.channel} · ` : ""}
                          {it.status}
                        </span>
                      )}
                      <span className="ml-auto text-[10px] text-[var(--text-tertiary)]">{fmtTime(it.created_at)}</span>
                    </div>
                    {it.content && (
                      <p className="whitespace-pre-wrap text-xs text-[var(--text-secondary)]">{it.content}</p>
                    )}
                    {it.actor && <p className="mt-1 text-[10px] text-[var(--text-hint)]">by {it.actor}</p>}
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
