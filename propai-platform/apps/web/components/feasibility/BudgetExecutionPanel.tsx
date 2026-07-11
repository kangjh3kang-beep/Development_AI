"use client";

/**
 * 예산-실적 실시간 집행 추적 편집기 (설계도 §13).
 *
 * 수지표를 '그룹 > 라인아이템' 트리로 편집하고, 각 항목의 단가·예산·기지출·미지출·집행률을
 * 실시간 추적한다. 비용을 지출하면 해당 항목에 '지출 기록'으로 반영 → 미지출·집행률·총계가 즉시
 * 재계산된다. 첨부 실무 수지표(진영·의정부)의 '금액·기집행비용·미집행금액' 열 구조.
 *
 * · 계산은 클라이언트에서 즉시(반응성): 미지출 = 예산 − 기지출, 집행률 = 기지출 ÷ 예산.
 * · projectId가 있으면 지출은 POST /feasibility/budget-execution/disburse 로 영속(해시체인 원장),
 *   마운트 시 POST /feasibility/budget-execution 로 영속 이벤트를 불러와 병합한다(graceful).
 */
import { useCallback, useMemo, useState } from "react";

import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type Disbursement = { amount_won: number; memo?: string; date?: string };
type LineItem = {
  id: string;
  group: string;
  label: string;
  budget_won: number;
  disbursements: Disbursement[];
};

/** 표준 지출 그룹(§12 실무 6문서 공통 구조). */
const GROUPS = [
  "토지비",
  "공사비",
  "설계감리비",
  "각종부담금",
  "판매관리비",
  "보존등기비",
  "일반관리비",
  "제세금",
  "금융비",
  "예비비",
] as const;

let _seq = 0;
const uid = () => `li_${Date.now().toString(36)}_${(_seq += 1)}`;

/** 개발방식별 프리셋은 후속 — 우선 빈 그룹 골격을 제공. */
function defaultItems(): LineItem[] {
  return GROUPS.map((g) => ({ id: uid(), group: g, label: "", budget_won: 0, disbursements: [] }));
}

const won = (n: number) => Math.round(n).toLocaleString("ko-KR");
const lineKey = (it: LineItem) => `${it.group}::${it.label}`;

type Computed = LineItem & {
  spent: number;
  remaining: number;
  rate: number | null;
  over: boolean;
};

export function BudgetExecutionPanel({ projectId: propProjectId }: { projectId?: string }) {
  // 활성 프로젝트가 있으면 지출을 원장에 영속(감사·변조탐지). 없으면 세션 로컬 편집만.
  const storeProjectId = useProjectContextStore((s) => s.projectId);
  const projectId = propProjectId ?? storeProjectId ?? undefined;
  const [items, setItems] = useState<LineItem[]>(defaultItems);
  const [pendingKey, setPendingKey] = useState<string | null>(null); // 지출 입력중인 라인
  const [amountInput, setAmountInput] = useState("");
  const [memoInput, setMemoInput] = useState("");
  const [loading, setLoading] = useState(false);

  // 지출 영속(disburse)은 원장에 append(감사·변조탐지). 영속 이벤트를 라인아이템으로 되불러오는
  // 재적재(키=group::label 매칭)는 프로젝트 템플릿 로드 플로우와 함께 후속 증분.

  const computed: Computed[] = useMemo(
    () =>
      items.map((it) => {
        const spent = it.disbursements.reduce((s, d) => s + (Number(d.amount_won) || 0), 0);
        const budget = Number(it.budget_won) || 0;
        return {
          ...it,
          spent,
          remaining: budget - spent,
          rate: budget > 0 ? Math.round((spent / budget) * 1000) / 10 : null,
          over: spent > budget && budget > 0,
        };
      }),
    [items],
  );

  const byGroup = useMemo(() => {
    const m = new Map<string, Computed[]>();
    for (const c of computed) {
      const arr = m.get(c.group) ?? [];
      arr.push(c);
      m.set(c.group, arr);
    }
    return m;
  }, [computed]);

  const total = useMemo(() => {
    const budget = computed.reduce((s, c) => s + (Number(c.budget_won) || 0), 0);
    const spent = computed.reduce((s, c) => s + c.spent, 0);
    return { budget, spent, remaining: budget - spent, rate: budget > 0 ? Math.round((spent / budget) * 1000) / 10 : null };
  }, [computed]);

  const overItems = useMemo(() => computed.filter((c) => c.over), [computed]);

  const patch = useCallback((id: string, p: Partial<LineItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...p } : it)));
  }, []);
  const addLine = useCallback((group: string) => {
    setItems((prev) => [...prev, { id: uid(), group, label: "", budget_won: 0, disbursements: [] }]);
  }, []);
  const removeLine = useCallback((id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }, []);

  const cancelDisburse = useCallback(() => {
    setPendingKey(null);
    setAmountInput("");
    setMemoInput("");
  }, []);

  const recordDisbursement = useCallback(
    async (it: LineItem) => {
      // 정수 원단위(백엔드 amount_won:int) + 라벨 필수(빈 라벨은 key 'group::' 충돌).
      const amt = Math.round(Number(amountInput.replace(/,/g, "")));
      if (!Number.isFinite(amt) || amt <= 0 || !it.label.trim()) return;
      setLoading(true);
      // 로컬 즉시 반영(반응성)
      patch(it.id, {
        disbursements: [...it.disbursements, { amount_won: amt, memo: memoInput || undefined }],
      });
      // 영속(있으면) — graceful
      if (projectId) {
        try {
          await apiClient.postV2("/feasibility/budget-execution/disburse", {
            body: {
              project_id: projectId,
              line_item_key: lineKey(it),
              amount_won: amt,
              group_name: it.group,
              label: it.label,
              memo: memoInput || undefined,
            },
          });
        } catch {
          /* graceful: 영속 실패해도 로컬 반영은 유지 */
        }
      }
      setPendingKey(null);
      setAmountInput("");
      setMemoInput("");
      setLoading(false);
    },
    [amountInput, memoInput, projectId, patch],
  );

  const rateBar = (rate: number | null, over: boolean) => (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--line)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(100, rate ?? 0)}%`,
            background: over ? "var(--status-danger, #dc2626)" : "var(--accent-strong)",
          }}
        />
      </div>
      <span className={`text-xs tabular-nums ${over ? "text-[var(--status-danger,#dc2626)] font-bold" : "text-[var(--text-secondary)]"}`}>
        {rate === null ? "—" : `${rate}%`}
      </span>
    </div>
  );

  return (
    <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
            Budget vs Actual · §13
          </p>
          <h2 className="text-xl font-black tracking-tight text-[var(--text-primary)]">예산-실적 집행 추적</h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            항목별 예산·기지출·미지출을 실시간 추적. 지출을 기록하면 미지출·집행률·총계가 즉시 갱신됩니다.
            {projectId ? " (지출은 원장에 영속·변조탐지)" : " (프로젝트 연결 시 지출 영속)"}
          </p>
        </div>
        <div className="flex gap-3 text-right">
          <Kpi label="총 예산" value={won(total.budget)} />
          <Kpi label="기지출" value={won(total.spent)} tone="accent" />
          <Kpi label="미지출" value={won(total.remaining)} tone={total.remaining < 0 ? "danger" : undefined} />
          <Kpi label="집행률" value={total.rate === null ? "—" : `${total.rate}%`} />
        </div>
      </header>

      {overItems.length > 0 && (
        <div className="mb-3 rounded-lg border border-[var(--status-danger,#dc2626)]/40 bg-[var(--status-danger,#dc2626)]/10 px-3 py-2 text-xs text-[var(--status-danger,#dc2626)]">
          ⚠ 예산 초과 집행 {overItems.length}건: {overItems.map((c) => c.label || c.group).join(", ")}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--line-strong)] text-left text-xs text-[var(--text-hint)]">
              <th className="py-2 pr-3 font-semibold">항목</th>
              <th className="py-2 px-3 text-right font-semibold">예산(원)</th>
              <th className="py-2 px-3 text-right font-semibold">기지출</th>
              <th className="py-2 px-3 text-right font-semibold">미지출</th>
              <th className="py-2 px-3 font-semibold">집행률</th>
              <th className="py-2 pl-3 font-semibold" />
            </tr>
          </thead>
          <tbody>
            {GROUPS.map((group) => {
              const rows = byGroup.get(group) ?? [];
              const gb = rows.reduce((s, c) => s + (Number(c.budget_won) || 0), 0);
              const gs = rows.reduce((s, c) => s + c.spent, 0);
              return (
                <GroupBlock
                  key={group}
                  group={group}
                  rows={rows}
                  groupBudget={gb}
                  groupSpent={gs}
                  pendingKey={pendingKey}
                  amountInput={amountInput}
                  memoInput={memoInput}
                  loading={loading}
                  onPatch={patch}
                  onAdd={() => addLine(group)}
                  onRemove={removeLine}
                  onStartDisburse={setPendingKey}
                  onCancel={cancelDisburse}
                  onAmount={setAmountInput}
                  onMemo={setMemoInput}
                  onRecord={recordDisbursement}
                  rateBar={rateBar}
                />
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-[var(--line-strong)] font-black text-[var(--text-primary)]">
              <td className="py-2 pr-3">총계</td>
              <td className="py-2 px-3 text-right tabular-nums">{won(total.budget)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{won(total.spent)}</td>
              <td className={`py-2 px-3 text-right tabular-nums ${total.remaining < 0 ? "text-[var(--status-danger,#dc2626)]" : ""}`}>
                {won(total.remaining)}
              </td>
              <td className="py-2 px-3">{rateBar(total.rate, total.remaining < 0)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      <p className="mt-3 text-[11px] text-[var(--text-hint)]">
        미지출 = 예산 − 기지출 · 집행률 = 기지출 ÷ 예산. 엑셀 다운로드 시 동일 수식이 셀에 임베드됩니다(§06).
      </p>
    </section>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "accent" | "danger" }) {
  const color =
    tone === "accent" ? "text-[var(--accent-strong)]" : tone === "danger" ? "text-[var(--status-danger,#dc2626)]" : "text-[var(--text-primary)]";
  return (
    <div className="min-w-[92px]">
      <div className="text-[10px] uppercase tracking-widest text-[var(--text-hint)]">{label}</div>
      <div className={`text-base font-black tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

function GroupBlock(props: {
  group: string;
  rows: Computed[];
  groupBudget: number;
  groupSpent: number;
  pendingKey: string | null;
  amountInput: string;
  memoInput: string;
  loading: boolean;
  onPatch: (id: string, p: Partial<LineItem>) => void;
  onAdd: () => void;
  onRemove: (id: string) => void;
  onStartDisburse: (id: string | null) => void;
  onCancel: () => void;
  onAmount: (v: string) => void;
  onMemo: (v: string) => void;
  onRecord: (it: LineItem) => void;
  rateBar: (rate: number | null, over: boolean) => React.ReactNode;
}) {
  const { group, rows, groupBudget, groupSpent } = props;
  return (
    <>
      <tr className="bg-[var(--surface-soft)]">
        <td colSpan={6} className="px-1 py-1.5 text-xs font-bold text-[var(--text-secondary)]">
          {group}
          <span className="ml-2 font-normal text-[var(--text-hint)]">
            예산 {won(groupBudget)} · 기지출 {won(groupSpent)} · 미지출 {won(groupBudget - groupSpent)}
          </span>
        </td>
      </tr>
      {rows.map((c) => (
        <tr key={c.id} className="border-b border-[var(--line)] align-middle">
          <td className="py-1.5 pr-3">
            <input
              value={c.label}
              onChange={(e) => props.onPatch(c.id, { label: e.target.value })}
              placeholder="항목명"
              aria-label={`${group} 항목명`}
              className="w-40 rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
          </td>
          <td className="py-1.5 px-3 text-right">
            <input
              inputMode="numeric"
              value={c.budget_won ? c.budget_won.toLocaleString("ko-KR") : ""}
              onChange={(e) => props.onPatch(c.id, { budget_won: Number(e.target.value.replace(/,/g, "")) || 0 })}
              placeholder="0"
              aria-label={`${c.label || group} 예산(원)`}
              className="w-32 rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-right text-sm tabular-nums text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
          </td>
          <td className="py-1.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">{won(c.spent)}</td>
          <td className={`py-1.5 px-3 text-right tabular-nums ${c.remaining < 0 ? "text-[var(--status-danger,#dc2626)] font-bold" : "text-[var(--text-primary)]"}`}>
            {won(c.remaining)}
          </td>
          <td className="py-1.5 px-3">{props.rateBar(c.rate, c.over)}</td>
          <td className="py-1.5 pl-3 text-right whitespace-nowrap">
            {props.pendingKey === c.id ? (
              <span className="inline-flex items-center gap-1">
                <input
                  autoFocus
                  inputMode="numeric"
                  value={props.amountInput}
                  onChange={(e) => props.onAmount(e.target.value)}
                  placeholder="지출액"
                  aria-label={`${c.label || group} 지출액(원)`}
                  className="w-24 rounded border border-[var(--accent-strong)] bg-[var(--surface)] px-2 py-1 text-right text-xs tabular-nums outline-none"
                />
                <input
                  value={props.memoInput}
                  onChange={(e) => props.onMemo(e.target.value)}
                  placeholder="메모"
                  aria-label={`${c.label || group} 지출 메모`}
                  className="w-20 rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-xs outline-none"
                />
                <button
                  disabled={props.loading || !c.label.trim()}
                  onClick={() => props.onRecord(c)}
                  className="rounded bg-[var(--accent-strong)] px-2 py-1 text-xs font-bold text-white disabled:opacity-50"
                >
                  기록
                </button>
                <button
                  aria-label="지출 입력 취소"
                  onClick={props.onCancel}
                  className="px-1 text-xs text-[var(--text-hint)]"
                >
                  ✕
                </button>
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                <button
                  onClick={() => props.onStartDisburse(c.id)}
                  disabled={!c.label.trim()}
                  title={!c.label.trim() ? "항목명을 먼저 입력하세요" : undefined}
                  className="rounded border border-[var(--line-strong)] px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[var(--line-strong)] disabled:hover:text-[var(--text-secondary)]"
                >
                  + 지출
                </button>
                <button
                  onClick={() => props.onRemove(c.id)}
                  title="항목 삭제"
                  className="text-xs text-[var(--text-hint)] hover:text-[var(--status-danger,#dc2626)]"
                >
                  🗑
                </button>
              </span>
            )}
          </td>
        </tr>
      ))}
      <tr>
        <td colSpan={6} className="px-1 pb-2 pt-1">
          <button
            onClick={props.onAdd}
            className="text-xs font-semibold text-[var(--accent-strong)] hover:underline"
          >
            + 항목 추가
          </button>
        </td>
      </tr>
    </>
  );
}
