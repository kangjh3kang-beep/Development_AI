"use client";

/**
 * Phase 1-G — 수수료 더치페이(합의기반 분배 · 다자동의 · 변경재동의 · 해시체인).
 *
 * 한 계약(contract)의 수수료 총액을 참여자(조직노드/사용자)별로 비율(%) 또는 금액으로
 * 분배하는 '합의'를 만들고, 참여자 전원의 동의(서명)로 확정한다. 카카오뱅크 더치페이처럼
 * 참여자별 카드 + 합계바로 실시간 검증하고, 변경 시 전원 재동의가 강제됨을 안내한다.
 *
 * 백엔드(commission_agreement_router, prefix /sales):
 *   POST   /commission/agreements                 합의 생성(pending)
 *   GET    /commission/agreements?contract_id=     계약별 합의 목록
 *   GET    /commission/agreements/{id}             합의 상세(상태·동의현황·해시)
 *   POST   /commission/agreements/{id}/consent     본인 동의 → 전원 시 confirmed
 *   POST   /commission/agreements/{id}/reject      본인 거부 → rejected
 *   PATCH  /commission/agreements/{id}             분배 변경 → 동의 리셋(전원 재동의)
 *
 * 권한: 생성/변경=현장 관리자(또는 변경은 참여자), 동의/거부=참여자 본인.
 *       비참여자 동의/거부는 백엔드 403 → 안내로 처리.
 * site_token: salesApi(siteId)가 저장된 X-Site-Token을 자동 첨부(1-A).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { PenLine } from "lucide-react";
import { salesApi, won } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { NumberInput } from "@/components/common/NumberInput";
import { TrustBadge } from "@/components/common/TrustBadge";

// ── 타입(백엔드 응답 스키마 정합) ─────────────────────────────────────────────
type Basis = "RATIO" | "AMOUNT";
type AgreementStatus = "pending" | "confirmed" | "rejected";
type ConsentStatus = "pending" | "consented" | "rejected";

interface AgreementParticipant {
  seq: number;
  user_id: string | null;
  node_id: string | null;
  ratio: number | null;
  amount: number | null;
  status: ConsentStatus;
  decided_at: string | null;
  decided_round: number;
}

interface ConsentProgress {
  consented: number;
  total: number;
  all_consented: boolean;
}

interface AgreementLedger {
  version: number;
  content_hash: string;
  created_at?: string;
}

interface Agreement {
  id: string;
  site_id: string;
  contract_id: string;
  total_amount: number;
  basis: Basis;
  status: AgreementStatus;
  version: number;
  participants: AgreementParticipant[];
  consent_progress: ConsentProgress;
  ledger?: AgreementLedger | null;
  created_by?: string | null;
  created_at?: string | null;
  confirmed_at?: string | null;
}

interface AgreementListResp {
  items: Agreement[];
  count: number;
}

interface OrgNode {
  id: string;
  path: string;
  node_type: string;
  display_name?: string | null;
}

interface ContractRow {
  id: string;
  unit_id?: string | null;
  total_price?: number | null;
  stage?: string | null;
  status?: string | null;
}

// 폼에서 다루는 참여자(작성중). target은 노드 id, kind는 node/user 구분.
interface DraftParticipant {
  key: string;
  kind: "node" | "user";
  target_id: string; // node_id 또는 user_id
  label: string;
  ratio: number | null; // basis=RATIO
  amount: number | null; // basis=AMOUNT
}

// ── 표시 상수 ────────────────────────────────────────────────────────────────
const NODE_TYPE_LABEL: Record<string, string> = {
  AGENCY: "분양대행사",
  SUBAGENCY: "대대행",
  GM_DIRECTOR: "총괄본부장",
  DIRECTOR: "본부장",
  TEAM_LEADER: "팀장",
  MEMBER: "팀원",
};

const STATUS_META: Record<AgreementStatus, { label: string; cls: string }> = {
  pending: { label: "동의 대기", cls: "border-amber-400/40 bg-amber-500/10 text-amber-300" },
  confirmed: { label: "확정 완료", cls: "border-emerald-400/40 bg-emerald-500/10 text-emerald-300" },
  rejected: { label: "거부됨", cls: "border-rose-400/40 bg-rose-500/10 text-rose-300" },
};

const CONSENT_META: Record<ConsentStatus, { label: string; cls: string; dot: string }> = {
  consented: { label: "동의", cls: "text-emerald-300", dot: "bg-emerald-400" },
  pending: { label: "대기", cls: "text-amber-300", dot: "bg-amber-400" },
  rejected: { label: "거부", cls: "text-rose-300", dot: "bg-rose-400" },
};

const fcls =
  "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

const RATIO_TOL = 0.01;
const AMOUNT_TOL = 1;

let _draftSeq = 0;
const newDraftKey = () => `d${++_draftSeq}`;

function nodeLabel(n: OrgNode): string {
  const t = NODE_TYPE_LABEL[n.node_type] ?? n.node_type;
  return n.display_name ? `${n.display_name} (${t})` : t;
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────
export default function CommissionDutchPay({ siteCode }: { siteCode: string }) {
  const api = useMemo(() => salesApi(siteCode), [siteCode]);

  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [nodes, setNodes] = useState<OrgNode[]>([]);
  const [contractId, setContractId] = useState("");
  const [agreements, setAgreements] = useState<Agreement[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Agreement | null>(null);

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");

  // ── 합의 생성/변경 폼 ──
  const [editing, setEditing] = useState(false); // 새 합의 작성 또는 변경제안 모드
  const [editTargetId, setEditTargetId] = useState(""); // 변경 대상 합의 id(빈값=신규 생성)
  const [totalAmount, setTotalAmount] = useState<number | null>(null);
  const [basis, setBasis] = useState<Basis>("RATIO");
  const [drafts, setDrafts] = useState<DraftParticipant[]>([]);
  const [addNodeId, setAddNodeId] = useState("");

  // 계약/조직 로딩(1회)
  useEffect(() => {
    api
      .get<ContractRow[]>("/contracts")
      .then((r) => {
        const list = Array.isArray(r) ? r : [];
        setContracts(list);
        if (list[0]) setContractId((prev) => prev || list[0].id);
      })
      .catch(() => setContracts([]));
    api
      .get<OrgNode[]>("/org/tree")
      .then((r) => setNodes(Array.isArray(r) ? r : []))
      .catch(() => setNodes([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  const loadAgreements = useCallback(
    (cid: string) => {
      if (!cid) {
        setAgreements([]);
        return;
      }
      setLoading(true);
      api
        .get<AgreementListResp>(`/commission/agreements?contract_id=${encodeURIComponent(cid)}`)
        .then((r) => {
          const items = r?.items ?? [];
          setAgreements(items);
          setErr("");
        })
        .catch(() => setErr("합의 목록을 불러오지 못했습니다."))
        .finally(() => setLoading(false));
    },
    [api],
  );

  useEffect(() => {
    loadAgreements(contractId);
  }, [contractId, loadAgreements]);

  // 선택된 합의 상세(해시·동의현황) 로딩
  const loadDetail = useCallback(
    (id: string) => {
      if (!id) {
        setDetail(null);
        return;
      }
      api
        .get<Agreement>(`/commission/agreements/${id}`)
        .then((r) => setDetail(r))
        .catch((e) => {
          if (e instanceof ApiClientError && e.status === 403) {
            setDetail(null);
            setErr("이 합의의 참여자가 아니어서 상세를 볼 수 없습니다.");
          } else {
            setErr("합의 상세를 불러오지 못했습니다.");
          }
        });
    },
    [api],
  );

  useEffect(() => {
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const contractLabel = useCallback(
    (c: ContractRow) => {
      const idx = contracts.findIndex((x) => x.id === c.id);
      const short = c.id.slice(0, 8);
      const price = c.total_price ? ` · ${won(c.total_price)}` : "";
      return `계약 #${idx >= 0 ? idx + 1 : "?"} (${short})${price}`;
    },
    [contracts],
  );

  // ── 작성 폼 합계 검증 ──
  const draftSums = useMemo(() => {
    const ratioSum = drafts.reduce((s, d) => s + (d.ratio ?? 0), 0);
    const amountSum = drafts.reduce((s, d) => s + (d.amount ?? 0), 0);
    const ratioOk = drafts.length > 0 && Math.abs(ratioSum - 100) <= RATIO_TOL;
    const amountOk =
      drafts.length > 0 &&
      (totalAmount ?? 0) > 0 &&
      Math.abs(amountSum - (totalAmount ?? 0)) <= AMOUNT_TOL;
    return { ratioSum, amountSum, ratioOk, amountOk, ok: basis === "RATIO" ? ratioOk : amountOk };
  }, [drafts, basis, totalAmount]);

  // ── 폼 액션 ──
  const startCreate = () => {
    setEditing(true);
    setEditTargetId("");
    setBasis("RATIO");
    setTotalAmount(null);
    setDrafts([]);
    setAddNodeId(nodes[0]?.id ?? "");
    setNotice("");
    setErr("");
  };

  const startAmend = (a: Agreement) => {
    setEditing(true);
    setEditTargetId(a.id);
    setBasis(a.basis);
    setTotalAmount(a.total_amount);
    setDrafts(
      (a.participants ?? []).map((p) => {
        const node = p.node_id ? nodes.find((n) => n.id === p.node_id) : undefined;
        return {
          key: newDraftKey(),
          kind: p.node_id ? ("node" as const) : ("user" as const),
          target_id: (p.node_id ?? p.user_id) ?? "",
          label: node ? nodeLabel(node) : p.node_id ? "조직노드" : "사용자",
          ratio: p.ratio,
          amount: p.amount,
        };
      }),
    );
    setAddNodeId(nodes[0]?.id ?? "");
    setNotice("변경 시 기존 동의는 모두 초기화되어 전원이 다시 동의해야 합니다.");
    setErr("");
  };

  const cancelEdit = () => {
    setEditing(false);
    setEditTargetId("");
    setDrafts([]);
    setNotice("");
  };

  const addParticipant = () => {
    const node = nodes.find((n) => n.id === addNodeId);
    if (!node) return;
    if (drafts.some((d) => d.kind === "node" && d.target_id === node.id)) {
      setErr("이미 추가된 참여자입니다.");
      return;
    }
    setErr("");
    setDrafts((prev) => [
      ...prev,
      {
        key: newDraftKey(),
        kind: "node",
        target_id: node.id,
        label: nodeLabel(node),
        ratio: null,
        amount: null,
      },
    ]);
  };

  const removeDraft = (key: string) => setDrafts((prev) => prev.filter((d) => d.key !== key));

  const setDraftRatio = (key: string, v: number | null) =>
    setDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, ratio: v } : d)));
  const setDraftAmount = (key: string, v: number | null) =>
    setDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, amount: v } : d)));

  // 금액 균등분배 헬퍼(더치페이 '1/N')
  const splitEvenly = () => {
    if (drafts.length === 0) return;
    if (basis === "RATIO") {
      const each = Math.round((10000 / drafts.length)) / 100; // 소수 2자리
      const rest = Math.round((100 - each * (drafts.length - 1)) * 100) / 100;
      setDrafts((prev) =>
        prev.map((d, i) => ({ ...d, ratio: i === prev.length - 1 ? rest : each })),
      );
    } else {
      const tot = totalAmount ?? 0;
      const each = Math.floor(tot / drafts.length);
      const rest = tot - each * (drafts.length - 1);
      setDrafts((prev) =>
        prev.map((d, i) => ({ ...d, amount: i === prev.length - 1 ? rest : each })),
      );
    }
  };

  const buildPayloadParticipants = () =>
    drafts.map((d) => ({
      ...(d.kind === "node" ? { node_id: d.target_id } : { user_id: d.target_id }),
      ...(basis === "RATIO" ? { ratio: d.ratio ?? 0 } : { amount: d.amount ?? 0 }),
    }));

  const submitForm = async () => {
    setErr("");
    if (!editTargetId && !contractId) {
      setErr("계약을 선택하세요.");
      return;
    }
    if ((totalAmount ?? 0) <= 0) {
      setErr("총 수수료를 입력하세요.");
      return;
    }
    if (drafts.length === 0) {
      setErr("참여자를 1명 이상 추가하세요.");
      return;
    }
    if (!draftSums.ok) {
      setErr(
        basis === "RATIO"
          ? `비율 합이 100%가 아닙니다(현재 ${draftSums.ratioSum.toFixed(2)}%).`
          : `금액 합이 총 수수료와 일치하지 않습니다(현재 ${won(draftSums.amountSum)}).`,
      );
      return;
    }
    setBusy(true);
    try {
      if (editTargetId) {
        const res = await api.patch<Agreement>(`/commission/agreements/${editTargetId}`, {
          participants: buildPayloadParticipants(),
          total_amount: totalAmount,
        });
        setNotice("분배가 변경되었습니다. 전원 재동의가 필요합니다.");
        setSelectedId(res.id);
      } else {
        const res = await api.post<Agreement>("/commission/agreements", {
          contract_id: contractId,
          total_amount: totalAmount,
          basis,
          participants: buildPayloadParticipants(),
        });
        setNotice("합의가 생성되었습니다. 참여자 동의를 기다립니다.");
        setSelectedId(res.id);
      }
      cancelEdit();
      loadAgreements(contractId);
    } catch (e) {
      const msg =
        e instanceof ApiClientError
          ? e.status === 403
            ? "권한이 없습니다(현장 관리자 또는 참여자만 가능)."
            : (e.message || "요청이 거부되었습니다.")
          : "처리 중 오류가 발생했습니다.";
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  // ── 동의 / 거부 ──
  const decide = async (id: string, action: "consent" | "reject") => {
    setErr("");
    setBusy(true);
    try {
      await api.post(`/commission/agreements/${id}/${action}`);
      setNotice(action === "consent" ? "동의가 기록되었습니다." : "거부가 기록되었습니다.");
      loadDetail(id);
      loadAgreements(contractId);
    } catch (e) {
      const msg =
        e instanceof ApiClientError && e.status === 403
          ? "이 합의의 참여자가 아니어서 동의/거부할 수 없습니다."
          : "처리 중 오류가 발생했습니다.";
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  const participantLabel = (p: AgreementParticipant): string => {
    if (p.node_id) {
      const node = nodes.find((n) => n.id === p.node_id);
      return node ? nodeLabel(node) : `조직노드 ${p.node_id.slice(0, 8)}`;
    }
    if (p.user_id) return `사용자 ${p.user_id.slice(0, 8)}`;
    return "참여자";
  };

  // ── 렌더 ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* 헤더 + 신뢰 표식 */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h3 className="text-base font-black text-[var(--text-primary)]">더치페이 분배 합의</h3>
          <p className="text-xs text-[var(--text-secondary)]">
            계약별 수수료를 참여자별로 나누고, 전원이 동의해야 확정됩니다.
          </p>
        </div>
        <TrustBadge
          className="ml-auto"
          label="합의·변경 이력 위변조 방지(해시체인)"
          note="합의 생성·동의·변경·확정 이력이 해시체인 원장에 봉인되어 위·변조 시 즉시 탐지됩니다."
        />
      </div>

      {/* 알림/에러 */}
      {err && (
        <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-300">
          {err}
        </div>
      )}
      {notice && !err && (
        <div className="rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-2.5 text-sm font-semibold text-emerald-300">
          {notice}
        </div>
      )}

      {/* 계약 선택 + 생성 버튼 */}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-[var(--text-tertiary)]">
          계약
          <select
            value={contractId}
            onChange={(e) => {
              setContractId(e.target.value);
              setSelectedId("");
              setDetail(null);
            }}
            className={`${fcls} w-64`}
          >
            {contracts.length === 0 && <option value="">계약 없음</option>}
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>
                {contractLabel(c)}
              </option>
            ))}
          </select>
        </label>
        {!editing && (
          <button
            onClick={startCreate}
            disabled={!contractId}
            className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
          >
            ＋ 더치페이 합의 만들기
          </button>
        )}
      </div>

      {/* ── 작성/변경 폼 ── */}
      {editing && (
        <div className="space-y-4 rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--surface-soft)] p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-black text-[var(--text-primary)]">
              {editTargetId ? "분배 변경(재동의 필요)" : "새 더치페이 합의"}
            </h4>
            {editTargetId && (
              <span className="rounded-md border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-bold text-amber-300">
                변경 시 전원 재동의 필요
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs text-[var(--text-tertiary)]">
              총 수수료(원)
              <NumberInput
                value={totalAmount}
                onChange={(n) => setTotalAmount(n)}
                placeholder="총 수수료"
                className={`${fcls} w-40`}
              />
            </label>
            <div className="flex flex-col gap-1 text-xs text-[var(--text-tertiary)]">
              분배 기준
              <div className="inline-flex overflow-hidden rounded-lg border border-[var(--line)]">
                {(["RATIO", "AMOUNT"] as Basis[]).map((b) => (
                  <button
                    key={b}
                    type="button"
                    disabled={!!editTargetId}
                    onClick={() => setBasis(b)}
                    className={`px-3 py-1.5 text-sm font-bold transition disabled:opacity-60 ${
                      basis === b
                        ? "bg-[var(--accent-strong)] text-white"
                        : "bg-[var(--surface-strong)] text-[var(--text-secondary)]"
                    }`}
                  >
                    {b === "RATIO" ? "비율(%)" : "금액(원)"}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={splitEvenly}
              disabled={drafts.length === 0 || (basis === "AMOUNT" && (totalAmount ?? 0) <= 0)}
              className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)] disabled:opacity-50"
            >
              ÷ 1/N 균등분배
            </button>
          </div>

          {/* 참여자 추가 */}
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-[var(--text-tertiary)]">
              참여자(조직)
              <select
                value={addNodeId}
                onChange={(e) => setAddNodeId(e.target.value)}
                className={`${fcls} w-56`}
              >
                {nodes.length === 0 && <option value="">조직노드 없음</option>}
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {nodeLabel(n)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={addParticipant}
              disabled={!addNodeId}
              className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-2 text-xs font-bold text-[var(--accent-strong)] disabled:opacity-50"
            >
              ＋ 참여자 추가
            </button>
          </div>

          {/* 참여자 카드 (더치페이 느낌) */}
          <div className="grid gap-2 sm:grid-cols-2">
            {drafts.map((d) => (
              <div
                key={d.key}
                className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2.5"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-xs font-black text-[var(--accent-strong)]">
                  {d.label.slice(0, 1)}
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-bold text-[var(--text-primary)]">
                  {d.label}
                </span>
                {basis === "RATIO" ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="0.01"
                      value={d.ratio ?? ""}
                      onChange={(e) =>
                        setDraftRatio(d.key, e.target.value === "" ? null : Number(e.target.value))
                      }
                      placeholder="0"
                      className={`${fcls} w-20 text-right`}
                    />
                    <span className="text-xs text-[var(--text-tertiary)]">%</span>
                  </div>
                ) : (
                  <NumberInput
                    value={d.amount}
                    onChange={(n) => setDraftAmount(d.key, n)}
                    placeholder="0"
                    className={`${fcls} w-28 text-right`}
                  />
                )}
                <button
                  type="button"
                  onClick={() => removeDraft(d.key)}
                  className="text-rose-400 hover:text-rose-300"
                  aria-label="참여자 제거"
                >
                  ✕
                </button>
              </div>
            ))}
            {drafts.length === 0 && (
              <p className="text-sm text-[var(--text-tertiary)]">
                참여자를 추가하세요. 비율 합 100% 또는 금액 합 = 총 수수료여야 합니다.
              </p>
            )}
          </div>

          {/* 합계바 */}
          {drafts.length > 0 && (
            <div
              className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-bold ${
                draftSums.ok
                  ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                  : "border-rose-400/40 bg-rose-500/10 text-rose-300"
              }`}
            >
              {basis === "RATIO" ? (
                <>
                  <span>비율 합계 {draftSums.ratioSum.toFixed(2)}% / 100%</span>
                  <span className="ml-auto">{draftSums.ratioOk ? "✓ 정상" : "✕ 100% 불일치"}</span>
                </>
              ) : (
                <>
                  <span>
                    금액 합계 {won(draftSums.amountSum)} / {won(totalAmount ?? 0)}
                  </span>
                  <span className="ml-auto">{draftSums.amountOk ? "✓ 정상" : "✕ 총액 불일치"}</span>
                </>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={submitForm}
              disabled={busy || !draftSums.ok}
              className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
            >
              {editTargetId ? "변경 제안(재동의 요청)" : "합의 생성"}
            </button>
            <button
              onClick={cancelEdit}
              disabled={busy}
              className="rounded-lg border border-[var(--line)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)]"
            >
              취소
            </button>
          </div>
        </div>
      )}

      {/* ── 합의 목록 ── */}
      <div className="space-y-2">
        <h4 className="text-sm font-black text-[var(--text-secondary)]">합의 현황</h4>
        {loading && (
          <div className="h-16 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]" />
        )}
        {!loading && agreements.length === 0 && (
          <p className="rounded-xl border border-dashed border-[var(--line)] px-4 py-6 text-center text-sm text-[var(--text-tertiary)]">
            이 계약의 더치페이 합의가 없습니다. 위에서 새로 만들어 보세요.
          </p>
        )}
        {agreements.map((a) => {
          const meta = STATUS_META[a.status];
          const cp = a.consent_progress;
          const pct = cp.total > 0 ? Math.round((cp.consented / cp.total) * 100) : 0;
          const open = selectedId === a.id;
          const view = open && detail?.id === a.id ? detail : a;
          return (
            <div
              key={a.id}
              className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
            >
              <button
                onClick={() => setSelectedId(open ? "" : a.id)}
                className="flex w-full flex-wrap items-center gap-3 text-left"
              >
                <span
                  className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${meta.cls}`}
                >
                  {meta.label}
                </span>
                <span className="text-sm font-black text-[var(--text-primary)]">
                  {won(a.total_amount)}
                </span>
                <span className="text-xs text-[var(--text-tertiary)]">
                  {a.basis === "RATIO" ? "비율 분배" : "금액 분배"} · v{a.version} · {cp.total}명
                </span>
                <span className="ml-auto text-xs font-bold text-[var(--text-secondary)]">
                  {cp.consented}/{cp.total} 동의
                </span>
              </button>

              {/* 동의 진행바 */}
              <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-[var(--surface-strong)]">
                <div
                  className={`h-full rounded-full transition-all ${
                    a.status === "rejected"
                      ? "bg-rose-400"
                      : cp.all_consented
                        ? "bg-emerald-400"
                        : "bg-amber-400"
                  }`}
                  style={{ width: `${a.status === "rejected" ? 100 : pct}%` }}
                />
              </div>

              {/* 상세(펼침) */}
              {open && (
                <div className="mt-4 space-y-3">
                  {/* 참여자별 동의 상태 */}
                  <div className="space-y-1.5">
                    {(view.participants ?? []).map((p) => {
                      const cm = CONSENT_META[p.status];
                      const share =
                        view.basis === "RATIO"
                          ? `${(p.ratio ?? 0).toFixed(2)}%`
                          : won(p.amount ?? 0);
                      return (
                        <div
                          key={p.seq}
                          className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2"
                        >
                          <span className={`h-2 w-2 shrink-0 rounded-full ${cm.dot}`} />
                          <span className="min-w-0 flex-1 truncate text-sm font-bold text-[var(--text-primary)]">
                            {participantLabel(p)}
                          </span>
                          <span className="text-sm font-black text-[var(--text-secondary)]">
                            {share}
                          </span>
                          <span className={`w-12 text-right text-xs font-bold ${cm.cls}`}>
                            {cm.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* 동의/거부 + 변경제안 */}
                  {view.status === "pending" && (
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => decide(a.id, "consent")}
                        disabled={busy}
                        className="rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-black text-white disabled:opacity-50"
                      >
                        ✓ 내 분배에 동의
                      </button>
                      <button
                        onClick={() => decide(a.id, "reject")}
                        disabled={busy}
                        className="rounded-lg border border-rose-400/50 px-4 py-2 text-sm font-bold text-rose-300 disabled:opacity-50"
                      >
                        ✕ 거부
                      </button>
                      <button
                        onClick={() => startAmend(view)}
                        disabled={busy}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)]"
                      >
                        <PenLine className="size-4" aria-hidden />분배 변경(재동의)
                      </button>
                    </div>
                  )}
                  <p className="text-[11px] text-[var(--text-hint)]">
                    동의/거부는 본인 참여분에만 적용됩니다(비참여자는 거부됨). 전원 동의 시 자동
                    확정됩니다.
                  </p>

                  {/* 무결성(해시체인) */}
                  {view.ledger?.content_hash && (
                    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
                      <span className="text-[11px] font-bold text-emerald-300">
                        해시체인 봉인 v{view.ledger.version}
                      </span>
                      <code className="truncate text-[11px] text-[var(--text-tertiary)]">
                        {view.ledger.content_hash.slice(0, 24)}…
                      </code>
                      <span className="ml-auto text-[11px] text-[var(--text-hint)]">
                        합의·변경 이력 위변조 방지
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
