"use client";

/**
 * 프로젝트 **실거래 신고내역 현황분석** 패널 — 생성허브.
 *
 * ★이 패널의 존재 이유: `#837` 이 MOLIT **계약상태 6필드**(해제·해제일·거래유형·등기일자·
 *   매수/매도 법인개인)를 파서에 보존했는데 **읽는 화면이 하나도 없었다**(2026-08-26 실측).
 *   이 패널이 그 첫 소비 표면이다.
 *
 * ★★**"필지별"이 아니다 — 그렇게 말하면 거짓이다.**
 *   국토부 공개자료는 토지 거래의 **지번을 마스킹**한다(라이브 실측: 114건 전수, 예 `"1*"`).
 *   그래서 서버는 **법정동 단위**로 집계하고 그 사유를 `parcel_level_match_absent` 로 싣는다.
 *   화면은 그 사유를 **그대로 보여 준다**(백엔드가 말한 것을 화면이 지어내지 않는다).
 *
 * ★필지는 **DB 에 없다**(라이브 `parcels` 테이블 0행). 프론트 `useLandScheduleStore` 가
 *   유일한 출처라 **클라이언트가 서버로 보낸다.**
 */

import { resolveAbsentLabel } from "@/lib/withheld/absent-reasons";
import { AlertTriangle, Download, FileSearch, Loader2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { apiClient } from "@/lib/api-client";
import { useLandScheduleStore } from "@/store/useLandScheduleStore";
import { useProjectStore } from "@/store/useProjectStore";

type Tx = {
  deal_date?: string; dong?: string; jibun?: string; jimok?: string;
  area_m2?: number; price_10k_won?: number;
  // ★단가는 **서버가 계산해 보낸 것**을 그대로 쓴다 — 화면에서 다시 나누지 않는다.
  //   `/realtx-report/download` 가 *"산식을 여기서 다시 계산하지 않는다"* 를 선언하고 있어,
  //   화면에서 계산하면 그 값이 **PDF·PPTX·DOCX 에는 없는** 상태가 된다.
  price_per_pyeong_10k?: number | null;
  price_per_pyeong_10k_absent?: string;
  price_per_pyeong_10k_basis?: string;
  cancel_type?: string; cancel_date?: string; dealing_type?: string;
  registered_date?: string; buyer_type?: string; seller_type?: string;
  share_dealing_type?: string;
};
type Summary = {
  total: number; cancelled: number; cancelled_pct: number;
  direct: number; brokered: number; registered: number; registered_pct: number;
  corporate_buyer: number; corporate_seller: number; share_deals: number;
};
type Group = {
  lawd_cd: string; dong: string; parcels: unknown[]; summary: Summary; transactions: Tx[];
  parcel_level_match: null; parcel_level_match_absent?: string; parcel_level_match_basis?: string;
};
type Report = {
  months: string[]; groups: Group[]; unlocated_parcels: { pnu?: string | null; transactions_basis?: string }[];
  fetch_errors: { lawd_cd: string; deal_ym: string; error: string }[];
  meta: { parcel_count: number; lawd_count: number; month_count: number; molit_calls: number; unlocated_count: number };
  note: string;
};
/** ★silent-fail 금지 — 실패를 상태로 들고 화면에 말한다(`DecisionBriefPanel` 관례). */
type Fetch =
  | { s: "idle" } | { s: "loading" }
  | { s: "error"; message: string } | { s: "ready"; data: Report };

//: 보류 사유 → 화면에 쓸 짧은 말. ★`"—"` 하나로 뭉개지 않는다 — 면적 열이 이미 `"—"` 를
//  쓰므로, 같은 글리프면 「해제라 해당 없음」과 「원천이 가림」이 구별되지 않는다.
//  (이 저장소가 `0㎡ × 0원/㎡` 로 값을 치른 형태다.)

/** 만원/평 — 서버가 실은 값만 그린다. 없으면 **왜 없는지**를 찍는다(지어내지 않는다). */
function perPyeong(t: Tx) {
  const v = t.price_per_pyeong_10k;
  if (typeof v === "number" && Number.isFinite(v) && v > 0) {
    // ★서버가 이미 유효숫자 3자리로 반올림했다 — 여기서 다시 깎지 않는다.
    //   1만원/평 미만(지방 임야 등)을 정수로 만들면 **0 이 된다**(문서 어댑터와 같은 규칙).
    const text = v >= 1 ? Math.round(v).toLocaleString() : String(v);
    return <span className="font-semibold">{text}</span>;
  }
  // ★사유는 **공용 어휘 하나**에서 나온다. `"—"` 는 **사유 코드 자체가 없을 때**만이다 —
  //   「사유가 없다」와 「모르는 사유다」는 다른 사실이고, 후자를 `"—"` 로 뭉개는 것이 결함이었다.
  //   ★종전 이 파일의 3종 목록이 **모집단**이라 생산자가 내는 `insufficient_coverage` 가
  //     `"—"` 로 떨어졌다. 적대 리뷰 실측(2026-09-04): 첫 봉합이 그 목록을 «오버라이드» 로
  //     남겼는데 **세 항목이 공용 어휘와 글자까지 같아** 잉여였고, 지워도 락이 전부 초록이었다.
  //   ★「해제」라고 쓰지 않는다는 이 열의 판단은 `ABSENT_SHORT` 로 옮겼고, D14 가 **렌더
  //     결과로**(두 열이 다른 말을 한다) 고정한다 — 문구를 못 박지 않으므로 취약하지 않다.
  const label = resolveAbsentLabel(t.price_per_pyeong_10k_absent, { variant: "short" }) ?? "—";
  return (
    <span className="text-[var(--text-hint)]" title={t.price_per_pyeong_10k_basis ?? undefined}>
      {label}
    </span>
  );
}

const won = (man?: number) =>
  man == null ? "—" : man >= 10_000 ? `${(man / 10_000).toFixed(1)}억` : `${man.toLocaleString()}만`;

/** 보고서 파일을 받는다 — `apiClient` 는 JSON 전용이라 **raw fetch + Bearer** 를 쓴다
 *  (저장소 관례: `DecisionBriefPanel`·`ReportDownloadMenu`·`RegistryRightsReportButton` 동일). */
async function downloadReport(
  parcels: unknown[], fmt: "pdf" | "pptx" | "docx",
): Promise<void> {
  const { apiBaseUrl } = apiClient.getRuntimeConfig();
  const token = typeof window !== "undefined"
    ? localStorage.getItem("propai_access_token") ?? "" : "";
  const res = await fetch(`${apiBaseUrl}/market/realtx-report/download?format=${fmt}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ parcels, months: 6, prop_type: "land" }),
  });
  if (!res.ok) {
    // ★상태코드를 분류해 **정직한 사유**를 말한다(형제 관례) — 침묵 금지.
    const detail = res.status === 404
      ? "보고서 엔드포인트가 아직 배포되지 않았습니다(deploy-pending)."
      : res.status === 401 || res.status === 403
        ? "보고서를 받으려면 로그인 또는 권한이 필요합니다."
        : res.status === 429
          ? "요청이 많아 잠시 후 다시 시도해야 합니다."
          : `보고서 생성에 실패했습니다 (HTTP ${res.status}).`;
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `realtx_report.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function RealtxReportPanel() {
  const projects = useProjectStore((s) => s.projects);
  const byProject = useLandScheduleStore((s) => s.byProject);
  const [pid, setPid] = useState<string>("");
  const [fetchState, setFetch] = useState<Fetch>({ s: "idle" });
  const [dl, setDl] = useState<{ s: "idle" | "busy" } | { s: "error"; m: string }>({ s: "idle" });

  // ★필지를 **가진** 프로젝트만 고르게 한다 — 빈 프로젝트를 골라 "0건"을 보는 것은
  //   사용자에게 *"거래가 없다"* 는 거짓 인상을 준다(실제로는 조회 대상이 없는 것).
  const selectable = useMemo(
    () => projects.filter((p) => (byProject[p.id] || []).length > 0),
    [projects, byProject],
  );
  const rows = useMemo(() => byProject[pid] || [], [byProject, pid]);

  const run = useCallback(async () => {
    if (!pid || rows.length === 0) return;
    setFetch({ s: "loading" });
    try {
      const data = await apiClient.post<Report>("/market/realtx-report", {
        body: {
          parcels: rows.map((r) => ({
            pnu: r.pnu ?? null, jibun: r.jibun, area_sqm: r.area_sqm,
            zone_code: r.zone_code, owner_type: r.owner_type,
          })),
          months: 6,
          prop_type: "land",
        },
      });
      setFetch({ s: "ready", data });
    } catch (e) {
      setFetch({ s: "error", message: e instanceof Error ? e.message : "조회 실패" });
    }
  }, [pid, rows]);

  const save = useCallback(async (fmt: "pdf" | "pptx" | "docx") => {
    if (rows.length === 0) return;
    setDl({ s: "busy" });
    try {
      await downloadReport(
        rows.map((r) => ({
          pnu: r.pnu ?? null, jibun: r.jibun, area_sqm: r.area_sqm,
          zone_code: r.zone_code, owner_type: r.owner_type,
        })),
        fmt,
      );
      setDl({ s: "idle" });
    } catch (e) {
      setDl({ s: "error", m: e instanceof Error ? e.message : "보고서 생성 실패" });
    }
  }, [rows]);

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
          <FileSearch className="size-4 text-[var(--accent-strong)]" aria-hidden />
          실거래 신고내역 현황분석
        </span>
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="realtx-project">분석할 프로젝트</label>
          <select
            id="realtx-project"
            value={pid}
            onChange={(e) => { setPid(e.target.value); setFetch({ s: "idle" }); }}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs text-[var(--text-primary)]"
          >
            <option value="">프로젝트 선택…</option>
            {selectable.map((p) => (
              <option key={p.id} value={p.id}>{p.name} · 필지 {(byProject[p.id] || []).length}</option>
            ))}
          </select>
          <button
            onClick={run}
            disabled={!pid || fetchState.s === "loading"}
            className="rounded-lg border border-[var(--accent-strong)] px-2.5 py-1 text-xs font-bold text-[var(--accent-strong)] disabled:opacity-40"
          >
            {fetchState.s === "loading" ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : "분석"}
          </button>
        </div>
      </div>

      {selectable.length === 0 && (
        <p className="rounded-lg border border-dashed border-[var(--line)] px-3 py-4 text-center text-xs text-[var(--text-hint)]">
          토지조서에 필지가 등록된 프로젝트가 없습니다. 사통맵에서 필지를 담으면 분석할 수 있습니다.
        </p>
      )}

      {fetchState.s === "error" && (
        <p className="rounded-lg border border-[var(--status-error)]/40 bg-[var(--status-error)]/10 px-3 py-2 text-xs text-[var(--status-error)]">
          조회 실패 — {fetchState.message}
        </p>
      )}

      {fetchState.s === "ready" && (
        <>
          <ReportView data={fetchState.data} />
          {/* ★보고서 저장 — 화면과 **같은 값**을 정본 통로(render/)로 문서화한다. */}
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-3">
            <span className="text-[10px] text-[var(--text-tertiary)]">보고서 저장</span>
            {(["pdf", "pptx", "docx"] as const).map((f) => (
              <button
                key={f}
                onClick={() => save(f)}
                disabled={dl.s === "busy"}
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] px-2 py-1 text-[11px] font-bold text-[var(--accent-strong)] disabled:opacity-40"
              >
                {dl.s === "busy" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : <Download className="size-3" aria-hidden />}
                {f.toUpperCase()}
              </button>
            ))}
            {dl.s === "error" && (
              <span className="text-[11px] text-[var(--status-error)]">{dl.m}</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ReportView({ data }: { data: Report }) {
  const { meta, groups, fetch_errors: errors, unlocated_parcels: unlocated } = data;
  return (
    <div className="space-y-3">
      {/* ★관측 가능성 — 쿼터 접기가 실제로 작동했는지 **수**로 보여 준다(주장이 아니라). */}
      <p className="text-[10px] text-[var(--text-hint)]">
        필지 {meta.parcel_count} · 시군구 {meta.lawd_count} · {meta.month_count}개월 ·
        국토부 조회 <b>{meta.molit_calls}회</b>
        {meta.unlocated_count > 0 && <> · 측위불가 {meta.unlocated_count}</>}
      </p>

      {/* ★조회 실패를 "거래 0건"으로 보여 주지 않는다 — 그건 거짓 사실이다. */}
      {errors.length > 0 && (
        <div className="rounded-lg border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-2.5 py-2 text-[11px] text-[var(--status-warning)]">
          <b className="flex items-center gap-1.5">
            <AlertTriangle className="size-3.5" aria-hidden />일부 기간을 조회하지 못했습니다 · {errors.length}건
          </b>
          <span className="ml-1 text-[var(--text-secondary)]">
            아래 집계에 <b>그 기간은 빠져 있습니다</b> — 거래가 없었던 것이 아닙니다.
          </span>
        </div>
      )}

      {groups.length === 0 && errors.length === 0 && (
        <p className="rounded-lg border border-[var(--line)] px-3 py-3 text-xs text-[var(--text-hint)]">
          해당 기간에 신고된 토지 실거래가 없습니다.
        </p>
      )}

      {groups.map((g) => (
        <div key={`${g.lawd_cd}-${g.dong}`} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <b className="text-sm text-[var(--text-primary)]">{g.dong}</b>
            <span className="text-[10px] text-[var(--text-tertiary)]">
              이 동의 프로젝트 필지 {g.parcels.length}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-[var(--line-subtle)] sm:grid-cols-4">
            <Stat label="신고 건수" value={`${g.summary.total}건`} />
            <Stat label="계약 해제" value={`${g.summary.cancelled}건`} sub={`${g.summary.cancelled_pct}%`} warn={g.summary.cancelled > 0} />
            <Stat label="등기 기재" value={`${g.summary.registered}건`} sub={`${g.summary.registered_pct}%`} />
            <Stat label="직거래 / 중개" value={`${g.summary.direct} / ${g.summary.brokered}`} />
          </div>
          {(g.summary.corporate_buyer > 0 || g.summary.corporate_seller > 0 || g.summary.share_deals > 0) && (
            <p className="mt-1.5 text-[10px] text-[var(--text-secondary)]">
              법인 매수 {g.summary.corporate_buyer} · 법인 매도 {g.summary.corporate_seller} · 지분거래 {g.summary.share_deals}
            </p>
          )}

          {/* ★백엔드가 말한 **마스킹 사유**를 그대로 보여 준다 — 화면이 지어내지 않는다. */}
          {g.parcel_level_match_basis && (
            <p className="mt-2 rounded-lg border border-[var(--status-info)]/40 bg-[var(--status-info)]/10 px-2.5 py-1.5 text-[10px] text-[var(--text-secondary)]">
              <b className="text-[var(--status-info)]">필지 단위 귀속 불가</b>
              <span className="ml-1">{g.parcel_level_match_basis}</span>
            </p>
          )}

          {g.transactions.length > 0 && (
            <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-[var(--line)]">
              <table className="w-full min-w-[640px] whitespace-nowrap text-[11px]">
                <thead className="sticky top-0 bg-[var(--surface-strong)]">
                  <tr className="text-[var(--text-hint)]">
                    <th className="px-2 py-1 text-left font-medium">거래일</th>
                    <th className="px-2 py-1 text-left font-medium">지목</th>
                    <th className="px-2 py-1 text-right font-medium">면적</th>
                    <th className="px-2 py-1 text-right font-medium">거래가</th>
                    <th
                      className="px-2 py-1 text-right font-medium"
                      title="거래금액 ÷ 면적. 원천이 평 단위로 정한 단가를 되돌린 값이라 유효숫자 3자리로 표기합니다. 지목·지분·해제가 섞여 있으니 행끼리 그대로 비교하지 마십시오."
                    >
                      만원/평
                    </th>
                    <th className="px-2 py-1 text-left font-medium">거래유형</th>
                    <th className="px-2 py-1 text-left font-medium">등기일자</th>
                    <th className="px-2 py-1 text-left font-medium">매수/매도</th>
                    <th className="px-2 py-1 text-left font-medium">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {g.transactions.map((t, i) => (
                    <tr key={`${t.deal_date}-${i}`} className="border-t border-[var(--line)]/50">
                      <td className="px-2 py-1 text-[var(--text-secondary)]">{t.deal_date || "—"}</td>
                      <td className="px-2 py-1 text-[var(--text-tertiary)]">{t.jimok || "—"}</td>
                      <td className="px-2 py-1 text-right text-[var(--text-primary)]">{t.area_m2 ? `${t.area_m2.toLocaleString()}㎡` : "—"}</td>
                      <td className="px-2 py-1 text-right font-semibold text-[var(--text-primary)]">{won(t.price_10k_won)}</td>
                      {/* ★`won()` 을 쓰지 않는다 — 억 절단이 14,623 과 14,999 를 **둘 다 "1.5억"** 으로
                          만들어 이 열의 존재이유(정밀도)를 지운다. */}
                      <td className="px-2 py-1 text-right text-[var(--text-primary)]">
                        {perPyeong(t)}
                      </td>
                      <td className="px-2 py-1 text-[var(--text-secondary)]">
                        {t.dealing_type || "—"}
                        {t.share_dealing_type === "지분" && <span className="ml-1 text-[9px] text-[var(--status-warning)]">지분</span>}
                      </td>
                      {/* ★등기일자는 원천에서 약 30%만 채워진다 — 빈 값이 '미등기'라는 뜻이 아니다. */}
                      <td className="px-2 py-1 text-[var(--text-tertiary)]" title="원천에서 약 30%만 기재됩니다 — 공란이 미등기를 뜻하지 않습니다">
                        {t.registered_date || "미기재"}
                      </td>
                      <td className="px-2 py-1 text-[var(--text-tertiary)]">
                        {(t.buyer_type || "—")}/{(t.seller_type || "—")}
                      </td>
                      <td className="px-2 py-1">
                        {t.cancel_type?.trim()
                          ? <b className="text-[var(--status-error)]">해제{t.cancel_date ? ` (${t.cancel_date})` : ""}</b>
                          : <span className="text-[var(--text-hint)]">정상</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}

      {unlocated.length > 0 && (
        <p className="rounded-lg border border-[var(--line)] px-2.5 py-2 text-[10px] text-[var(--text-secondary)]">
          <b>조회 대상에서 제외 · {unlocated.length}필지</b>
          <span className="ml-1">{unlocated[0]?.transactions_basis}</span>
        </p>
      )}

      <p className="text-[10px] leading-relaxed text-[var(--text-hint)]">{data.note}</p>
    </div>
  );
}

function Stat({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className="bg-[var(--surface-soft)] px-3 py-2 text-center">
      <p className="text-[9px] text-[var(--text-tertiary)]">{label}</p>
      <p className={`mt-0.5 text-sm font-bold ${warn ? "text-[var(--status-error)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub && <p className="text-[9px] text-[var(--text-tertiary)]">{sub}</p>}
    </div>
  );
}
