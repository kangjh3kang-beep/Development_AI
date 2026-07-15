"use client";

/**
 * Phase C — 공유·바이럴(MGM 추천) UI.
 *
 * 백엔드 계약(_workspace/63 §7, prefix /api/v1/sales, X-Site-Token 자동 첨부):
 *   - POST /referral/codes {kind staff|site, site_id?} → {code,kind,site_id,created} (멱등)
 *   - GET  /referral/codes → {items:[{code,kind,site_id,active,created_at}]}
 *   - GET  /referral/share?code=&site_id= → {share_url,qr_data,default_text,notice,web_share{title,text,url}}
 *   - GET  /referral/stats?code=&from=&to= → {funnel{click,visit,lead,contract},attributions,conversion{...}}
 *
 * 구성: 내 추천코드 발급/표시 → 공유링크(복사)·QR(무의존성 생성·다운로드)·Web Share → 퍼널 통계(기간필터).
 * 정직성: QR/Web Share 미지원 폴백, 도용주의 안내, 정보통신망법 고지, 빈상태·로딩·에러.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Upload } from "lucide-react";
import { salesApi } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { generateQrMatrix } from "@/lib/qr";

// ── 타입(백엔드 §7 정합) ────────────────────────────────────────────
interface ReferralCode {
  code: string;
  kind: "staff" | "site";
  site_id?: string | null;
  active?: boolean;
  created_at?: string;
}
interface SharePayload {
  code: string;
  share_url: string;
  qr_data: string;
  default_text?: string;
  site_id?: string | null;
  notice?: string;
  web_share?: { title?: string; text?: string; url?: string };
}
interface Funnel {
  click: number;
  visit: number;
  lead: number;
  contract: number;
}
interface Conversion {
  click_to_visit?: number;
  visit_to_lead?: number;
  lead_to_contract?: number;
  click_to_contract?: number;
}
interface StatsPayload {
  code: string;
  funnel: Funnel;
  attributions?: number;
  conversion?: Conversion;
}

const BTN_PRIMARY =
  "rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50";
const BTN_OUTLINE =
  "rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)] disabled:opacity-50";

function pct(v?: number): string {
  if (v == null || Number.isNaN(v)) return "0%";
  // 백엔드가 0~1 비율 또는 0~100 중 무엇을 주든 표시 안정화.
  const ratio = v <= 1 ? v * 100 : v;
  return `${Math.round(ratio * 10) / 10}%`;
}

export default function ReferralSharePanel({ siteId }: { siteId: string }) {
  const api = useMemo(() => salesApi(siteId), [siteId]);

  const [codes, setCodes] = useState<ReferralCode[]>([]);
  const [loadingCodes, setLoadingCodes] = useState(true);
  const [activeCode, setActiveCode] = useState<string>("");
  const [issuing, setIssuing] = useState(false);
  const [err, setErr] = useState("");

  const loadCodes = useCallback(() => {
    api
      .get<{ items: ReferralCode[] }>("/referral/codes")
      .then((r) => {
        const items = r?.items ?? [];
        setCodes(items);
        setActiveCode((cur) => cur || items[0]?.code || "");
        setErr("");
      })
      .catch((e) => {
        if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
          setErr("추천코드 조회 권한이 없습니다. 현장에 다시 진입해 주세요.");
        } else {
          setErr("추천코드를 불러오지 못했습니다.");
        }
      })
      .finally(() => setLoadingCodes(false));
  }, [api]);

  useEffect(() => {
    // setState는 effect 본문이 아닌 microtask에서(cascading render 방지, 코드베이스 관례).
    Promise.resolve().then(() => setLoadingCodes(true));
    loadCodes();
  }, [loadCodes]);

  const issue = (kind: "staff" | "site") => {
    setIssuing(true);
    setErr("");
    const body: Record<string, unknown> = { kind };
    if (kind === "site") body.site_id = siteId;
    api
      .post<ReferralCode>("/referral/codes", body)
      .then((r) => {
        setActiveCode(r.code);
        loadCodes();
      })
      .catch((e) => {
        setErr(e instanceof ApiClientError ? e.message : "추천코드 발급에 실패했습니다.");
      })
      .finally(() => setIssuing(false));
  };

  const hasStaff = codes.some((c) => c.kind === "staff");
  const hasSite = codes.some((c) => c.kind === "site" && c.site_id === siteId);

  return (
    <div className="space-y-5">
      {/* 헤더 */}
      <div className="space-y-1">
        <h2 className="text-base font-black text-[var(--text-primary)]">공유·홍보 (추천코드)</h2>
        <p className="text-xs text-[var(--text-secondary)]">
          내 추천코드로 만든 공유링크·QR로 고객을 초대하면, 방문·계약 실적이 내게 귀속됩니다.
        </p>
      </div>

      {err && <p className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-300">{err}</p>}

      {/* 코드 발급/선택 */}
      <div className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-bold text-[var(--text-primary)]">내 추천코드</p>
          <div className="ml-auto flex gap-2">
            <button onClick={() => issue("staff")} disabled={issuing} className={BTN_OUTLINE}>
              {hasStaff ? "내 코드 재확인" : "내 코드 발급"}
            </button>
            <button onClick={() => issue("site")} disabled={issuing} className={BTN_OUTLINE}>
              {hasSite ? "현장코드 재확인" : "현장 전용코드"}
            </button>
          </div>
        </div>

        {loadingCodes ? (
          <div className="h-12 animate-pulse rounded-xl bg-[var(--surface-soft)]" />
        ) : codes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-6 text-center text-sm text-[var(--text-secondary)]">
            아직 발급된 추천코드가 없습니다. &lsquo;내 코드 발급&rsquo;을 눌러 시작하세요.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {codes.map((c) => (
              <button
                key={c.code}
                onClick={() => setActiveCode(c.code)}
                className={`rounded-lg px-3 py-2 text-left transition ${
                  activeCode === c.code
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="block text-[10px] font-bold opacity-80">{c.kind === "site" ? "현장 전용" : "개인(상담사)"}</span>
                <span className="block font-mono text-sm font-black tracking-wider">{c.code}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 공유 영역(선택 코드 기준) */}
      {activeCode && <ShareBlock api={api} code={activeCode} siteId={siteId} />}

      {/* 퍼널 통계 */}
      {activeCode && <StatsBlock api={api} code={activeCode} />}

      {/* 도용주의 */}
      <p className="flex items-start gap-1.5 text-[11px] text-[var(--text-hint)]">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>추천코드는 개인 실적 귀속에 사용됩니다. 타인에게 양도·도용 시 실적·수수료 분쟁이 발생할 수 있으니 본인만
        사용하세요. 공유링크는 누구나 접속할 수 있으나, 귀속은 최초 접촉(first-touch) 기준입니다.</span>
      </p>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 공유: share_url 복사 · QR 생성/다운로드 · Web Share · 정보통신망법 고지
// ════════════════════════════════════════════════════════════════════
function ShareBlock({ api, code, siteId }: { api: ReturnType<typeof salesApi>; code: string; siteId: string }) {
  const [share, setShare] = useState<SharePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [shareMsg, setShareMsg] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    Promise.resolve().then(() => setLoading(true));
    api
      .get<SharePayload>(`/referral/share?code=${encodeURIComponent(code)}&site_id=${encodeURIComponent(siteId)}`)
      .then((r) => {
        setShare(r);
        setErr("");
      })
      .catch(() => setErr("공유 정보를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [api, code, siteId]);

  // QR 렌더(무의존성 generateQrMatrix → canvas). qr_data 우선, 없으면 share_url.
  const qrSource = share?.qr_data || share?.share_url || "";
  const qrMatrix = useMemo(() => (qrSource ? generateQrMatrix(qrSource) : null), [qrSource]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !qrMatrix) return;
    const n = qrMatrix.length;
    const quiet = 4; // quiet zone(여백) 모듈.
    const scale = 6; // 모듈당 픽셀.
    const dim = (n + quiet * 2) * scale;
    canvas.width = dim;
    canvas.height = dim;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, dim, dim);
    ctx.fillStyle = "#000000";
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        if (qrMatrix[r][c]) {
          ctx.fillRect((c + quiet) * scale, (r + quiet) * scale, scale, scale);
        }
      }
    }
  }, [qrMatrix]);

  const shareUrl = share?.share_url || "";

  const copyLink = async () => {
    if (!shareUrl) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        // 폴백: 임시 textarea.
        const ta = document.createElement("textarea");
        ta.value = shareUrl;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setShareMsg("복사에 실패했습니다. 링크를 길게 눌러 복사하세요.");
    }
  };

  const webShare = async () => {
    setShareMsg("");
    const ws = share?.web_share;
    const payload = {
      title: ws?.title || "분양 현장 안내",
      text: ws?.text || share?.default_text || "분양 현장 정보를 확인해 보세요.",
      url: ws?.url || shareUrl,
    };
    // Web Share API 가능 시.
    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share(payload);
        return;
      } catch (e) {
        // 사용자가 취소하면 조용히 무시.
        if (e instanceof DOMException && e.name === "AbortError") return;
      }
    }
    // 폴백: 링크 복사.
    await copyLink();
    setShareMsg("이 기기는 공유 기능을 지원하지 않아 링크를 복사했습니다. 원하는 앱에 붙여넣어 공유하세요.");
  };

  const downloadQr = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `referral-${code}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setShareMsg("QR 다운로드에 실패했습니다.");
    }
  };

  if (loading) return <div className="h-40 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />;
  if (err) return <p className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-300">{err}</p>;
  if (!share) return null;

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
      <p className="text-sm font-bold text-[var(--text-primary)]">공유하기</p>

      {/* 공유링크 — 크게 표시 + 복사 */}
      <div className="space-y-2">
        <p className="text-xs font-bold text-[var(--text-secondary)]">공유 링크</p>
        <div className="flex items-stretch gap-2">
          <div className="flex-1 truncate rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2.5 font-mono text-sm text-[var(--text-primary)]">
            {shareUrl}
          </div>
          <button onClick={copyLink} className={BTN_PRIMARY}>
            {copied ? "복사됨 ✓" : "복사"}
          </button>
        </div>
      </div>

      {/* Web Share */}
      <button onClick={webShare} className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]">
        <Upload className="size-4" aria-hidden /> 공유하기 (카카오톡·문자·앱)
      </button>

      {/* QR */}
      {/* @ink-contract-ignore — QR 은 흰 배경이어야 스캔된다(테마 불변). 자식은 각자 색 선언. */}
      <div className="flex flex-col items-center gap-2 rounded-xl border border-[var(--line)] bg-white p-4">
        {qrMatrix ? (
          <>
            <canvas ref={canvasRef} className="h-auto w-44 max-w-full" aria-label="추천코드 QR" />
            <button onClick={downloadQr} className={BTN_OUTLINE}>
              QR 이미지 저장
            </button>
          </>
        ) : (
          <p className="px-4 py-6 text-center text-xs font-semibold text-neutral-500">
            QR 생성이 불가한 환경입니다. 위 공유 링크를 복사해 사용하세요.
          </p>
        )}
      </div>

      {shareMsg && <p className="text-xs font-semibold text-amber-300">{shareMsg}</p>}

      {/* 정보통신망법 고지(notice) */}
      <div className="space-y-1 rounded-xl border border-amber-400/20 bg-amber-500/5 px-3 py-2.5 text-[11px] text-amber-200/90">
        <p className="inline-flex items-center gap-1.5 font-bold text-amber-300"><AlertTriangle className="size-3.5" aria-hidden />공유 시 유의사항(정보통신망법)</p>
        <p>{share.notice || "광고성 정보 전송 시 수신자의 사전 동의가 필요하며, 야간(오후 9시~익일 오전 8시) 전송은 제한됩니다. 수신거부 방법을 함께 안내하세요."}</p>
        <p className="text-amber-200/70">카카오톡 등으로 공유할 때는 수신자가 직접 동의·요청한 경우에만 발송하세요.</p>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 퍼널 통계: click → visit → lead → contract + 전환율 + 기간 필터
// ════════════════════════════════════════════════════════════════════
function StatsBlock({ api, code }: { api: ReturnType<typeof salesApi>; code: string }) {
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const load = useCallback(() => {
    const qs = new URLSearchParams({ code });
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    api
      .get<StatsPayload>(`/referral/stats?${qs.toString()}`)
      .then((r) => {
        setStats(r);
        setErr("");
      })
      .catch(() => setErr("통계를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [api, code, from, to]);

  useEffect(() => {
    Promise.resolve().then(() => setLoading(true));
    load();
  }, [load]);

  // 사용자 조회(버튼) — 즉시 로딩 표시 후 재조회.
  const refresh = () => {
    setLoading(true);
    load();
  };

  const funnel = stats?.funnel;
  const conv = stats?.conversion;
  const steps: { key: keyof Funnel; label: string; conv?: string }[] = [
    { key: "click", label: "클릭" },
    { key: "visit", label: "방문", conv: pct(conv?.click_to_visit) },
    { key: "lead", label: "리드(상담)", conv: pct(conv?.visit_to_lead) },
    { key: "contract", label: "계약", conv: pct(conv?.lead_to_contract) },
  ];
  const maxVal = funnel ? Math.max(funnel.click, funnel.visit, funnel.lead, funnel.contract, 1) : 1;
  const isEmpty = funnel ? funnel.click + funnel.visit + funnel.lead + funnel.contract === 0 : true;

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-bold text-[var(--text-primary)]">전환 퍼널</p>
        <div className="ml-auto flex flex-wrap items-center gap-1.5 text-xs">
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-[var(--text-primary)]"
          />
          <span className="text-[var(--text-tertiary)]">~</span>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-[var(--text-primary)]"
          />
          <button onClick={refresh} className={BTN_OUTLINE}>
            조회
          </button>
        </div>
      </div>

      {err && <p className="text-sm font-semibold text-rose-300">{err}</p>}

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-9 animate-pulse rounded-lg bg-[var(--surface-soft)]" />
          ))}
        </div>
      ) : isEmpty ? (
        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
          아직 집계된 유입이 없습니다. 공유 링크를 배포하면 클릭·방문·계약이 여기에 집계됩니다.
        </div>
      ) : (
        <>
          <div className="space-y-2.5">
            {steps.map((s) => {
              const val = funnel ? funnel[s.key] : 0;
              const w = Math.max(4, Math.round((val / maxVal) * 100));
              return (
                <div key={s.key} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-[var(--text-primary)]">
                      {s.label}
                      {s.conv && <span className="ml-1.5 text-[10px] font-semibold text-[var(--text-tertiary)]">전환 {s.conv}</span>}
                    </span>
                    <span className="font-black text-[var(--text-primary)]">{val.toLocaleString("ko-KR")}</span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-[var(--surface-soft)]">
                    <div className="h-full rounded-full bg-[var(--accent-strong)] transition-all" style={{ width: `${w}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-3 border-t border-[var(--line)] pt-3 text-xs">
            <div>
              <span className="text-[var(--text-tertiary)]">귀속 고객</span>{" "}
              <span className="font-black text-[var(--text-primary)]">{(stats?.attributions ?? 0).toLocaleString("ko-KR")}명</span>
            </div>
            <div>
              <span className="text-[var(--text-tertiary)]">클릭→계약 전환</span>{" "}
              <span className="font-black text-[var(--accent-strong)]">{pct(conv?.click_to_contract)}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
