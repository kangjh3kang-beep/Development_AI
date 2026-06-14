"use client";

/**
 * Phase 1-F — 전자 해촉증명서 패널(역할분기 2뷰).
 *
 * 백엔드 계약(prefix /api/v1/sales, site 컨텍스트 X-Site-Code + X-Site-Token, salesApi 자동첨부):
 *   발급주체(시행/대행 본부장↑·admin)
 *     POST /cert/issuers · GET /cert/issuers
 *     POST /cert/issue {issuer_id, targets:[{user_id, period_start?, period_end?, income?…}]}
 *   프리랜서(전원)
 *     GET /cert/my-history · POST /cert/request {sites:[…]} · GET /cert/my-requests
 *     GET /cert/my-certs?year=&site_id= · GET /cert/{id}/pdf(inline) · POST /cert/bulk-pdf {ids:[…]}(zip)
 *
 * 재사용: salesApi(siteId)(X-Site-Token 자동), ImageUpload(/uploads/image → stamp_url),
 *         PDF/ZIP 바이너리는 apiClient(JSON 파서)로 못 받으므로 raw fetch(인증/토큰 헤더 직조립).
 *
 * 정직성: 법정 통일양식 아님·세무신고(3.3%) 참고용. 민감정보(주민번호 등) 입력은 받지 않으며
 *         기간/소득은 백엔드 근무이력·원천징수에서 자동채움한다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { resolveApiOrigin } from "@/lib/api-client";
import { salesApi, activeSiteTokenValue, won } from "@/lib/salesApi";
import { ImageUpload } from "@/components/ui/ImageUpload";

const ISSUER_ROLES = new Set(["SUPERADMIN", "DEVELOPER", "AGENCY", "GM_DIRECTOR"]);

const fcls =
  "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";
const cardCls = "rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4";

// ── 타입(백엔드 응답 정합) ────────────────────────────────────────────────────
interface Issuer {
  id: string;
  issuer_type?: string;
  company_name: string;
  biz_reg_no?: string | null;
  ceo_name?: string | null;
  stamp_url?: string | null;
  created_at?: string;
}
interface HistoryItem {
  site_id: string;
  site_name: string;
  active?: boolean;
  period_start?: string | null;
  period_end?: string | null;
  display_name?: string | null;
}
interface RequestItem {
  id: string;
  site_id: string;
  site_name: string;
  period_start?: string | null;
  period_end?: string | null;
  status: string;
  certificate_id?: string | null;
  created_at?: string;
}
interface CertItem {
  id: string;
  certificate_no: string;
  site_id: string;
  site_name: string;
  period_start?: string | null;
  period_end?: string | null;
  income_total: number;
  withholding_total: number;
  net_total: number;
  tax_year?: number | null;
  issued_at?: string | null;
  issuer_company_name?: string | null;
}
interface IssueTargetRow {
  user_id: string;
  period_start?: string;
  period_end?: string;
  income?: number;
}

// ── 공용: PDF/ZIP raw fetch(인증·현장토큰 헤더 직조립) ────────────────────────
function buildSalesHeaders(siteId: string): Record<string, string> {
  const headers: Record<string, string> = { "X-Site-Code": siteId };
  const token = activeSiteTokenValue(siteId);
  if (token) headers["X-Site-Token"] = token;
  try {
    const at = window.localStorage.getItem("propai_access_token")?.trim();
    if (at) headers["Authorization"] = `Bearer ${at}`;
  } catch {
    /* localStorage 비활성 무시 */
  }
  return headers;
}

/** 사용자친화 에러 메시지(503 reportlab 미설치 등). */
async function readError(res: Response): Promise<string> {
  if (res.status === 503) return "PDF 생성 모듈이 서버에 설치되지 않았습니다(관리자 문의).";
  if (res.status === 403) return "본인 또는 발급 현장 관리자만 열람할 수 있습니다.";
  if (res.status === 404) return "증명서를 찾을 수 없습니다.";
  try {
    const data = (await res.json()) as { detail?: string };
    if (data?.detail) return data.detail;
  } catch {
    /* noop */
  }
  return `요청 실패(${res.status})`;
}

const fmtPeriod = (s?: string | null, e?: string | null) =>
  `${s ? s.slice(0, 10) : "—"} ~ ${e ? e.slice(0, 10) : "현재"}`;

export default function TerminationCertPanel({
  siteCode,
  role,
}: {
  siteCode: string;
  role: string;
}) {
  const api = useMemo(() => salesApi(siteCode), [siteCode]);
  const isIssuer = ISSUER_ROLES.has(role);
  const [view, setView] = useState<"freelancer" | "issuer">("freelancer");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-black text-[var(--text-primary)]">전자 해촉증명서</h2>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-tertiary)]">
            ※ 법정 통일양식이 아니며, 프리랜서(3.3%) 세무신고 참고용입니다. 주민번호 등 민감정보는
            입력하지 않으며, 근무기간·소득은 현장 기록에서 자동으로 채워집니다.
          </p>
        </div>
        {isIssuer && (
          <div className="flex gap-1 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-1">
            <button
              onClick={() => setView("freelancer")}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                view === "freelancer"
                  ? "bg-[var(--accent-strong)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              내 증명서
            </button>
            <button
              onClick={() => setView("issuer")}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                view === "issuer"
                  ? "bg-[var(--accent-strong)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              발급 관리
            </button>
          </div>
        )}
      </div>

      {isIssuer && view === "issuer" ? (
        <IssuerView api={api} />
      ) : (
        <FreelancerView api={api} siteCode={siteCode} />
      )}
    </div>
  );
}

type SalesApi = ReturnType<typeof salesApi>;

// ── 발급주체뷰 ────────────────────────────────────────────────────────────────
function IssuerView({ api }: { api: SalesApi }) {
  const [issuers, setIssuers] = useState<Issuer[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // 발급주체 등록 폼
  const [companyName, setCompanyName] = useState("");
  const [bizRegNo, setBizRegNo] = useState("");
  const [ceoName, setCeoName] = useState("");
  const [stampUrl, setStampUrl] = useState("");
  const [issuerType, setIssuerType] = useState("AGENCY");
  const [savingIssuer, setSavingIssuer] = useState(false);

  // 발급 실행
  const [selectedIssuer, setSelectedIssuer] = useState("");
  const [targets, setTargets] = useState<IssueTargetRow[]>([{ user_id: "" }]);
  const [issuing, setIssuing] = useState(false);
  const [issueResult, setIssueResult] = useState<string>("");

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<{ items: Issuer[] }>("/cert/issuers")
      .then((r) => {
        const items = r?.items ?? [];
        setIssuers(items);
        setErr("");
        if (items[0]) setSelectedIssuer((cur) => cur || items[0].id);
      })
      .catch(() => setErr("발급주체 목록을 불러오지 못했습니다(권한 확인)."))
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const saveIssuer = async () => {
    if (!companyName.trim()) {
      setErr("법인명을 입력하세요.");
      return;
    }
    setSavingIssuer(true);
    setErr("");
    try {
      await api.post("/cert/issuers", {
        company_name: companyName.trim(),
        biz_reg_no: bizRegNo.trim() || undefined,
        ceo_name: ceoName.trim() || undefined,
        stamp_url: stampUrl || undefined,
        issuer_type: issuerType,
      });
      setCompanyName("");
      setBizRegNo("");
      setCeoName("");
      setStampUrl("");
      load();
    } catch {
      setErr("발급주체 등록에 실패했습니다(시행/대행 본부장↑·관리자만 가능).");
    } finally {
      setSavingIssuer(false);
    }
  };

  const updateTarget = (idx: number, patch: Partial<IssueTargetRow>) =>
    setTargets((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const addTarget = () => setTargets((rows) => [...rows, { user_id: "" }]);
  const removeTarget = (idx: number) =>
    setTargets((rows) => (rows.length <= 1 ? rows : rows.filter((_, i) => i !== idx)));

  const issue = async () => {
    if (!selectedIssuer) {
      setErr("발급주체를 선택하세요.");
      return;
    }
    const valid = targets.filter((t) => t.user_id.trim());
    if (valid.length === 0) {
      setErr("발급 대상(사용자 ID)을 1명 이상 입력하세요.");
      return;
    }
    setIssuing(true);
    setErr("");
    setIssueResult("");
    try {
      const res = await api.post<{ issued: { certificate_no: string }[]; count: number }>(
        "/cert/issue",
        {
          issuer_id: selectedIssuer,
          targets: valid.map((t) => ({
            user_id: t.user_id.trim(),
            period_start: t.period_start || undefined,
            period_end: t.period_end || undefined,
            income: typeof t.income === "number" ? t.income : undefined,
          })),
        },
      );
      setIssueResult(`${res?.count ?? 0}건 발급 완료 (${(res?.issued ?? []).map((i) => i.certificate_no).join(", ")})`);
      setTargets([{ user_id: "" }]);
    } catch {
      setErr("발급에 실패했습니다(발급주체·대상·권한을 확인하세요).");
    } finally {
      setIssuing(false);
    }
  };

  return (
    <div className="space-y-5">
      {err && (
        <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-300">
          {err}
        </div>
      )}

      {/* 발급주체 등록 */}
      <div className={cardCls}>
        <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">발급주체(법인) 등록</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[var(--text-tertiary)]">법인명 *</span>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="예: ㈜프롭에이아이" className={fcls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[var(--text-tertiary)]">사업자등록번호</span>
            <input value={bizRegNo} onChange={(e) => setBizRegNo(e.target.value)} placeholder="000-00-00000" className={fcls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[var(--text-tertiary)]">대표자명</span>
            <input value={ceoName} onChange={(e) => setCeoName(e.target.value)} placeholder="예: 홍길동" className={fcls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[var(--text-tertiary)]">구분</span>
            <select value={issuerType} onChange={(e) => setIssuerType(e.target.value)} className={fcls}>
              <option value="AGENCY">분양대행(법인)</option>
              <option value="DEVELOPER">시행(법인)</option>
            </select>
          </label>
        </div>
        <div className="mt-3">
          <span className="mb-1 block text-[11px] text-[var(--text-tertiary)]">직인 이미지(날인용)</span>
          <ImageUpload value={stampUrl} onChange={setStampUrl} label="직인 이미지를 업로드하세요(클릭/드래그)" />
        </div>
        <div className="mt-3 flex justify-end">
          <button
            onClick={saveIssuer}
            disabled={savingIssuer}
            className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
          >
            {savingIssuer ? "등록 중…" : "＋ 발급주체 등록"}
          </button>
        </div>
      </div>

      {/* 발급주체 목록 */}
      <div className={cardCls}>
        <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">등록된 발급주체</h3>
        {loading ? (
          <div className="h-12 animate-pulse rounded-xl bg-[var(--surface-strong)]" />
        ) : issuers.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">등록된 발급주체가 없습니다. 위에서 등록하세요.</p>
        ) : (
          <ul className="space-y-2">
            {issuers.map((iss) => (
              <li
                key={iss.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2"
              >
                {iss.stamp_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={iss.stamp_url} alt="직인" className="h-10 w-10 rounded-md object-contain" />
                ) : (
                  <div className="flex h-10 w-10 items-center justify-center rounded-md border border-dashed border-[var(--line)] text-[9px] text-[var(--text-hint)]">
                    직인
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-[var(--text-primary)]">{iss.company_name}</p>
                  <p className="truncate text-xs text-[var(--text-tertiary)]">
                    {iss.biz_reg_no || "사업자번호 미등록"} · 대표 {iss.ceo_name || "—"}
                  </p>
                </div>
                <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                  {iss.issuer_type === "DEVELOPER" ? "시행" : "대행"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 발급 실행(개별/일괄) */}
      <div className={cardCls}>
        <h3 className="mb-1 text-sm font-black text-[var(--text-primary)]">증명서 발급(개별/일괄)</h3>
        <p className="mb-3 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
          대상 프리랜서의 사용자 ID를 입력해 일괄 발급합니다. 기간·소득을 비우면 현장 근무이력·원천징수에서
          자동으로 채워집니다.
        </p>
        <label className="mb-3 flex flex-col gap-1">
          <span className="text-[11px] text-[var(--text-tertiary)]">발급주체</span>
          <select value={selectedIssuer} onChange={(e) => setSelectedIssuer(e.target.value)} className={`${fcls} max-w-md`}>
            {issuers.length === 0 && <option value="">발급주체를 먼저 등록하세요</option>}
            {issuers.map((iss) => (
              <option key={iss.id} value={iss.id}>
                {iss.company_name}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-2">
          {targets.map((t, idx) => (
            <div key={idx} className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-2.5">
              <label className="flex flex-1 flex-col gap-1">
                <span className="text-[10px] text-[var(--text-tertiary)]">대상 사용자 ID *</span>
                <input
                  value={t.user_id}
                  onChange={(e) => updateTarget(idx, { user_id: e.target.value })}
                  placeholder="프리랜서 user_id (UUID)"
                  className={`${fcls} min-w-[200px]`}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[var(--text-tertiary)]">시작(자동)</span>
                <input type="date" value={t.period_start ?? ""} onChange={(e) => updateTarget(idx, { period_start: e.target.value })} className={fcls} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[var(--text-tertiary)]">종료(자동)</span>
                <input type="date" value={t.period_end ?? ""} onChange={(e) => updateTarget(idx, { period_end: e.target.value })} className={fcls} />
              </label>
              <button
                onClick={() => removeTarget(idx)}
                disabled={targets.length <= 1}
                className="rounded-lg border border-[var(--line)] px-2.5 py-1.5 text-xs font-bold text-[var(--text-tertiary)] hover:text-rose-300 disabled:opacity-40"
                title="대상 제거"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={addTarget}
            className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)]"
          >
            ＋ 대상 추가
          </button>
          <button
            onClick={issue}
            disabled={issuing || issuers.length === 0}
            className="ml-auto rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
          >
            {issuing ? "발급 중…" : `발급 실행(${targets.filter((t) => t.user_id.trim()).length}명)`}
          </button>
        </div>

        {issueResult && (
          <div className="mt-3 rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-300">
            {issueResult}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 프리랜서뷰 ────────────────────────────────────────────────────────────────
function FreelancerView({ api, siteCode }: { api: SalesApi; siteCode: string }) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [certs, setCerts] = useState<CertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // 근무이력 일괄선택(현장)
  const [pickedSites, setPickedSites] = useState<Set<string>>(new Set());
  // 증명서 일괄선택(id)
  const [pickedCerts, setPickedCerts] = useState<Set<string>>(new Set());
  // 증명서 필터
  const [filterYear, setFilterYear] = useState("");
  const [filterSite, setFilterSite] = useState("");

  const loadRequests = useCallback(() => {
    api
      .get<{ items: RequestItem[] }>("/cert/my-requests")
      .then((r) => setRequests(r?.items ?? []))
      .catch(() => setRequests([]));
  }, [api]);

  const loadCerts = useCallback(() => {
    const q = new URLSearchParams();
    if (filterYear.trim()) q.set("year", filterYear.trim());
    if (filterSite) q.set("site_id", filterSite);
    const qs = q.toString();
    api
      .get<{ items: CertItem[] }>(`/cert/my-certs${qs ? `?${qs}` : ""}`)
      .then((r) => setCerts(r?.items ?? []))
      .catch(() => setCerts([]));
  }, [api, filterYear, filterSite]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get<{ items: HistoryItem[] }>("/cert/my-history").then((r) => setHistory(r?.items ?? [])).catch(() => setHistory([])),
      api.get<{ items: RequestItem[] }>("/cert/my-requests").then((r) => setRequests(r?.items ?? [])).catch(() => setRequests([])),
      api.get<{ items: CertItem[] }>("/cert/my-certs").then((r) => setCerts(r?.items ?? [])).catch(() => setCerts([])),
    ]).finally(() => setLoading(false));
  }, [api]);

  // 필터 변경 시 증명서만 재조회
  useEffect(() => {
    loadCerts();
  }, [loadCerts]);

  const toggleSite = (siteId: string) =>
    setPickedSites((prev) => {
      const next = new Set(prev);
      if (next.has(siteId)) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  const allSitesPicked = history.length > 0 && pickedSites.size === history.length;
  const toggleAllSites = () =>
    setPickedSites(allSitesPicked ? new Set() : new Set(history.map((h) => h.site_id)));

  const toggleCert = (id: string) =>
    setPickedCerts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allCertsPicked = certs.length > 0 && pickedCerts.size === certs.length;
  const toggleAllCerts = () =>
    setPickedCerts(allCertsPicked ? new Set() : new Set(certs.map((c) => c.id)));

  const requestCert = async () => {
    if (pickedSites.size === 0) {
      setErr("발급신청할 현장을 1개 이상 선택하세요.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await api.post("/cert/request", { sites: Array.from(pickedSites) });
      setPickedSites(new Set());
      loadRequests();
    } catch {
      setErr("발급신청에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  // 개별 PDF: 새 창(inline). 토큰 헤더가 필요하므로 blob URL로 연다.
  const openPdf = async (cert: CertItem) => {
    setErr("");
    try {
      const res = await fetch(`${resolveApiOrigin()}/api/v1/sales/cert/${cert.id}/pdf`, {
        headers: buildSalesHeaders(siteCode),
      });
      if (!res.ok) {
        setErr(await readError(res));
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      // 새 창이 로드한 뒤 정리(즉시 revoke 시 일부 브라우저 표시 실패).
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setErr("PDF를 여는 데 실패했습니다.");
    }
  };

  // 개별 이미지(PNG/JPEG): 새 창(inline). 인쇄·공유용. 토큰 헤더 필요 → blob URL.
  const openImage = async (cert: CertItem, fmt: "png" | "jpeg") => {
    setErr("");
    try {
      const res = await fetch(`${resolveApiOrigin()}/api/v1/sales/cert/${cert.id}/image?fmt=${fmt}`, {
        headers: buildSalesHeaders(siteCode),
      });
      if (!res.ok) { setErr(await readError(res)); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setErr("이미지를 여는 데 실패했습니다.");
    }
  };

  const downloadBulk = async () => {
    if (pickedCerts.size === 0) {
      setErr("다운로드할 증명서를 선택하세요.");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      const res = await fetch(`${resolveApiOrigin()}/api/v1/sales/cert/bulk-pdf`, {
        method: "POST",
        headers: { ...buildSalesHeaders(siteCode), "Content-Type": "application/json" },
        body: JSON.stringify({ ids: Array.from(pickedCerts) }),
      });
      if (!res.ok) {
        setErr(await readError(res));
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "certs.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setErr("일괄 다운로드에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const statusBadge = (s: string) => {
    const map: Record<string, { label: string; cls: string }> = {
      PENDING: { label: "신청중", cls: "bg-amber-500/15 text-amber-300" },
      ISSUED: { label: "발급완료", cls: "bg-emerald-500/15 text-emerald-300" },
      REJECTED: { label: "반려", cls: "bg-rose-500/15 text-rose-300" },
    };
    const m = map[s] ?? { label: s, cls: "bg-[var(--accent-soft)] text-[var(--accent-strong)]" };
    return <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${m.cls}`}>{m.label}</span>;
  };

  if (loading) {
    return <div className="h-40 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />;
  }

  return (
    <div className="space-y-5">
      {err && (
        <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-300">
          {err}
        </div>
      )}

      {/* 근무이력 → 발급신청 */}
      <div className={cardCls}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-black text-[var(--text-primary)]">내 근무이력</h3>
          {history.length > 0 && (
            <button onClick={toggleAllSites} className="text-xs font-bold text-[var(--accent-strong)]">
              {allSitesPicked ? "전체 해제" : "전체 선택"}
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">근무이력이 없습니다.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {history.map((h) => (
              <label
                key={h.site_id}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 transition ${
                  pickedSites.has(h.site_id)
                    ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                    : "border-[var(--line)] bg-[var(--surface-strong)]"
                }`}
              >
                <input
                  type="checkbox"
                  checked={pickedSites.has(h.site_id)}
                  onChange={() => toggleSite(h.site_id)}
                  className="mt-1 h-4 w-4 accent-[var(--accent-strong)]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-[var(--text-primary)]">{h.site_name}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">{fmtPeriod(h.period_start, h.period_end)}</p>
                  {h.active && (
                    <span className="mt-1 inline-block rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-bold text-emerald-300">
                      재직중
                    </span>
                  )}
                </div>
              </label>
            ))}
          </div>
        )}
        <div className="mt-3 flex justify-end">
          <button
            onClick={requestCert}
            disabled={busy || pickedSites.size === 0}
            className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
          >
            선택 현장 발급신청({pickedSites.size})
          </button>
        </div>
      </div>

      {/* 신청 현황 */}
      <div className={cardCls}>
        <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">내 발급신청 현황</h3>
        {requests.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">발급신청 내역이 없습니다.</p>
        ) : (
          <ul className="space-y-2">
            {requests.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-[var(--text-primary)]">{r.site_name}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">{fmtPeriod(r.period_start, r.period_end)}</p>
                </div>
                {statusBadge(r.status)}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 발급받은 증명서 */}
      <div className={cardCls}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-black text-[var(--text-primary)]">발급받은 증명서</h3>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={filterYear}
              onChange={(e) => setFilterYear(e.target.value.replace(/[^0-9]/g, ""))}
              placeholder="연도"
              inputMode="numeric"
              className={`${fcls} w-20`}
            />
            <select value={filterSite} onChange={(e) => setFilterSite(e.target.value)} className={`${fcls} max-w-[180px]`}>
              <option value="">전체 현장</option>
              {history.map((h) => (
                <option key={h.site_id} value={h.site_id}>
                  {h.site_name}
                </option>
              ))}
            </select>
            {certs.length > 0 && (
              <button onClick={toggleAllCerts} className="text-xs font-bold text-[var(--accent-strong)]">
                {allCertsPicked ? "전체 해제" : "전체 선택"}
              </button>
            )}
          </div>
        </div>

        {certs.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">발급받은 증명서가 없습니다.</p>
        ) : (
          <ul className="space-y-2">
            {certs.map((c) => (
              <li
                key={c.id}
                className={`flex flex-wrap items-center gap-3 rounded-xl border px-3 py-2.5 transition ${
                  pickedCerts.has(c.id)
                    ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                    : "border-[var(--line)] bg-[var(--surface-strong)]"
                }`}
              >
                <input
                  type="checkbox"
                  checked={pickedCerts.has(c.id)}
                  onChange={() => toggleCert(c.id)}
                  className="h-4 w-4 accent-[var(--accent-strong)]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-[var(--text-primary)]">
                    {c.site_name}
                    <span className="ml-2 text-xs font-medium text-[var(--text-tertiary)]">{c.certificate_no}</span>
                  </p>
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {fmtPeriod(c.period_start, c.period_end)} · 소득 {won(c.income_total)} · 원천징수 {won(c.withholding_total)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    onClick={() => openPdf(c)}
                    className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)] active:scale-95"
                  >
                    PDF
                  </button>
                  <button
                    onClick={() => openImage(c, "png")}
                    className="rounded-lg border border-[var(--line)] px-2.5 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] active:scale-95"
                  >
                    PNG
                  </button>
                  <button
                    onClick={() => openImage(c, "jpeg")}
                    className="rounded-lg border border-[var(--line)] px-2.5 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] active:scale-95"
                  >
                    JPEG
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {certs.length > 0 && (
          <div className="mt-3 flex justify-end">
            <button
              onClick={downloadBulk}
              disabled={busy || pickedCerts.size === 0}
              className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
            >
              선택 일괄 PDF(ZIP) 다운로드({pickedCerts.size})
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
