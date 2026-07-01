"use client";

import { useCallback, useState } from "react";
import DOMPurify from "dompurify";
import { AlertTriangle } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import type {
  AssembleResponse,
  AutoDesignSummary,
  DesignPayload,
  SimilarRefV2,
  SimilarScorePart,
} from "@/components/cad/types";

/**
 * U4 · 템플릿 조립 카드(R6~R8) — 유사 표준설계 사례 1건을
 *  · 썸네일(inline SVG — script 등 위험 마크업 제거 가드 후에만 렌더)
 *  · 적합도(similarity) + 점수 분해(score_breakdown) 미니바(basis 근거)
 *  · 기하 보유(has_geometry) 시 '이 사례로 초안 생성'
 *    → POST /design-references/{id}/assemble → 조립 미리보기
 *    (적응 내역·검증 위반 — 전부 서버 산출 그대로, 추정·가공 금지)
 *  · 검증 통과 시에만 '스튜디오 적용' → onApply(payload, summary)
 *    (기존 SSOT(applyDesign) 경로 재사용 — 2D/3D/BIM/QTO 단일기하 전파)
 * 로 보여준다. v2 확장 필드 부재(구버전 응답)면 메타만 표시(하위호환).
 */

export type ReferenceSiteContext = {
  siteArea: number;
  zoneCode: string;
  buildingUse: string;
  unitTypes: string[];
};

type ReferenceAssemblyCardProps = {
  item: SimilarRefV2;
  siteContext: ReferenceSiteContext;
  /** 검증 통과 초안만 호출됨 — 호스트의 SSOT 적용 경로(applyDesign) 재사용. */
  onApply: (payload: DesignPayload, summary: AutoDesignSummary) => void;
};

/**
 * 인라인 SVG 정화 가드 — DOMPurify(파서 기반)로 SVG 프로파일만 허용한다(P2-8).
 *
 * (이전: 자체 regex 치환 — 파서가 아니라 중첩/인코딩 변형(예: <scr<script>ipt>,
 * 엔티티 우회)에 취약했다.) 비SVG 입력·SSR(window 부재)·정화 후에도 위험 마크업이
 * 잔존하면 null(미렌더 — 가짜 안전 보장 금지). 잔존 검사는 심층 방어로 유지.
 */
export function sanitizeSvgMarkup(raw: string | null | undefined): string | null {
  if (!raw || typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!/^<svg[\s>]/i.test(trimmed)) return null;
  // DOMPurify 는 DOM 이 필요하다 — SSR 에선 정직하게 미렌더(클라이언트에서 정화 렌더).
  if (typeof window === "undefined") return null;
  const cleaned = DOMPurify.sanitize(trimmed, {
    USE_PROFILES: { svg: true, svgFilters: true },
    // svg 프로파일이 이미 script 등을 배제하나, 위험 컨테이너는 명시적으로 재금지(심층 방어).
    FORBID_TAGS: ["script", "foreignObject", "iframe", "object", "embed", "style"],
    FORBID_ATTR: ["href", "xlink:href"], // 썸네일 SVG 에 링크 불필요 — javascript:/외부참조 원천 차단
  });
  const result = cleaned.trim();
  // 정화가 SVG 골격 자체를 바꿨거나 위험 마크업이 잔존하면 렌더 포기(안전 우선).
  if (!/^<svg[\s>]/i.test(result)) return null;
  if (/<\s*(script|iframe|object|embed|foreignobject)\b/i.test(result)) return null;
  if (/javascript:/i.test(result)) return null;
  if (/\son\w+\s*=/i.test(result)) return null;
  return result;
}

/** 문자열/{message} 혼합 배열 → 사람이 읽는 메시지 목록(형태 불명 항목 제외). */
function toMessages(arr: Array<string | { message?: unknown }> | undefined | null): string[] {
  if (!Array.isArray(arr)) return [];
  return arr
    .map((v) =>
      typeof v === "string"
        ? v
        : v && typeof v === "object" && typeof v.message === "string"
          ? v.message
          : "",
    )
    .map((s) => s.trim())
    .filter(Boolean);
}

/** legal_fit(boolean | 객체) → 칩 표시값. 판정 불가(부재·형태 불명)는 null(미표시). */
function readLegalFit(v: SimilarRefV2["legal_fit"]): { fit: boolean; note: string | null } | null {
  if (typeof v === "boolean") return { fit: v, note: null };
  if (v && typeof v === "object" && typeof v.fit === "boolean") {
    const note =
      typeof v.message === "string" && v.message.trim()
        ? v.message.trim()
        : typeof v.basis === "string" && v.basis.trim()
          ? v.basis.trim()
          : null;
    return { fit: v.fit, note };
  }
  return null;
}

/** 조립 API 오류 → 사용자 행동 가능 메시지(상태코드 정직 표기). */
function describeAssembleError(e: unknown): string {
  if (e instanceof ApiClientError) {
    switch (e.status) {
      case 401:
        return "로그인이 필요합니다 — 로그인 후 다시 시도해 주세요.";
      case 404:
        return "이 사례의 기하 데이터를 찾을 수 없습니다(조립 불가).";
      case 422:
        return "입력값을 확인해 주세요(요청 형식 오류).";
      case 501:
        return "이 기능의 서버 구성이 아직 완료되지 않았습니다 — 관리자에게 문의해 주세요.";
      default:
        return `초안 생성에 실패했습니다 (HTTP ${e.status})`;
    }
  }
  return e instanceof Error && e.message ? e.message : "초안 생성에 실패했습니다.";
}

export function ReferenceAssemblyCard({ item, siteContext, onApply }: ReferenceAssemblyCardProps) {
  const [assembling, setAssembling] = useState(false);
  const [result, setResult] = useState<AssembleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  const handleAssemble = useCallback(async () => {
    setAssembling(true);
    setError(null);
    setApplied(false);
    try {
      const res = await apiClient.post<AssembleResponse>(
        `/design-references/${encodeURIComponent(item.id)}/assemble`,
        {
          body: {
            site_area_sqm: siteContext.siteArea,
            zone_code: siteContext.zoneCode,
            building_use: siteContext.buildingUse,
            target_unit_types: siteContext.unitTypes,
          },
          useMock: false,
        },
      );
      setResult(res);
    } catch (e) {
      setResult(null);
      setError(describeAssembleError(e));
    } finally {
      setAssembling(false);
    }
  }, [item.id, siteContext]);

  const thumbnail = sanitizeSvgMarkup(item.thumbnail_svg);
  const legalFit = readLegalFit(item.legal_fit);
  const breakdown = Array.isArray(item.score_breakdown)
    ? item.score_breakdown.filter((p) => p && typeof p.score === "number" && Number.isFinite(p.score))
    : [];

  // ── 조립 결과 정직 게이트 — passed·violations 둘 다 없으면 검증 미제공(적용 차단) ──
  const adaptations = toMessages(result?.adaptations);
  const adaptationCount = Array.isArray(result?.adaptations) ? result.adaptations.length : 0;
  const violationMsgs = toMessages(result?.violations);
  const violationCount = Array.isArray(result?.violations) ? result.violations.length : 0;
  const hasVerdict =
    !!result && (typeof result.passed === "boolean" || Array.isArray(result.violations));
  const passed = result
    ? typeof result.passed === "boolean"
      ? result.passed
      : Array.isArray(result.violations) && violationCount === 0
    : false;
  const canApply = !!result && hasVerdict && passed && !!result.design_payload && !!result.summary;
  const verdictText = !hasVerdict
    ? "결과 미제공"
    : passed
      ? "통과"
      : violationCount > 0
        ? `위반 ${violationCount}건`
        : "위반";

  const meta = [
    item.building_use,
    item.area_sqm ? `${Math.round(item.area_sqm)}㎡` : "",
    item.total_units ? `${item.total_units}세대` : "",
    item.floors ? `${item.floors}층` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="flex items-start gap-3">
        {/* 썸네일 — 정화 가드 통과한 inline SVG만 렌더(부재·정화불능 시 미표시) */}
        {thumbnail && (
          <div
            className="h-20 w-24 shrink-0 overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] [&_svg]:h-full [&_svg]:w-full"
            role="img"
            aria-label={`${item.title} 도면 썸네일`}
            dangerouslySetInnerHTML={{ __html: thumbnail }}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-black text-[var(--text-primary)]">{item.title}</p>
            <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-black text-[var(--accent-strong)]">
              적합도 {item.similarity}%
            </span>
            {legalFit && (
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-black"
                title={legalFit.note ?? undefined}
                style={{
                  color: legalFit.fit ? "var(--status-success)" : "var(--status-warning)",
                  background: `color-mix(in srgb, ${
                    legalFit.fit ? "var(--status-success)" : "var(--status-warning)"
                  } 14%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${
                    legalFit.fit ? "var(--status-success)" : "var(--status-warning)"
                  } 40%, transparent)`,
                }}
              >
                {legalFit.fit ? "법규 적합" : "법규 검토"}
              </span>
            )}
          </div>
          {meta && <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{meta}</p>}
          {item.unit_types?.length > 0 && (
            <p className="text-[10px] text-[var(--text-hint)]">{item.unit_types.join(", ")}</p>
          )}
          {legalFit?.note && (
            <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">{legalFit.note}</p>
          )}
        </div>
        {item.file_url && (
          <a
            href={item.file_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 text-[11px] font-bold text-[var(--accent-strong)]"
          >
            도면 ↗
          </a>
        )}
      </div>

      {/* 점수 분해 미니바(basis 근거) — 서버 제공 시에만(구버전 응답은 미표시) */}
      {breakdown.length > 0 && <ScoreBreakdownBars parts={breakdown} />}

      {/* 조립 액션 — 기하 보유 사례만. 기하 없음이 확인된 사례는 메타 참고용 고지 */}
      {item.has_geometry === true ? (
        <div className="mt-3">
          {!result && (
            <button
              type="button"
              onClick={handleAssemble}
              disabled={assembling}
              className="w-full rounded-xl bg-[var(--accent-strong)] px-3 py-2 text-xs font-black text-white transition-opacity disabled:opacity-40"
            >
              {assembling ? "초안 생성 중…" : "이 사례로 초안 생성"}
            </button>
          )}
          {error && (
            <p className="mt-2 text-[11px] font-bold text-[var(--status-error)]" role="alert">
              {error}
            </p>
          )}

          {/* 조립 미리보기 — 원본·적응·검증 전부 서버 산출 그대로(정직 표기) */}
          {result && (
            <div className="mt-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <p className="text-[11px] font-black text-[var(--text-primary)]">
                원본 {result.source_title || item.title} · 적응 {adaptationCount}건 · 검증{" "}
                <span
                  style={{
                    color: !hasVerdict
                      ? "var(--text-hint)"
                      : passed
                        ? "var(--status-success)"
                        : "var(--status-warning)",
                  }}
                >
                  {verdictText}
                </span>
              </p>

              {result.summary && (
                <div className="mt-2 grid grid-cols-4 gap-2">
                  <PreviewMetric label="세대" value={`${result.summary.total_units}`} />
                  <PreviewMetric label="층수" value={`${result.summary.num_floors}F`} />
                  <PreviewMetric label="건폐율" value={`${result.summary.bcr_percent.toFixed(0)}%`} />
                  <PreviewMetric label="용적률" value={`${result.summary.far_percent.toFixed(0)}%`} />
                </div>
              )}

              {adaptations.length > 0 && (
                <div className="mt-2 space-y-0.5">
                  <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
                    적응 내역
                  </span>
                  {adaptations.map((a, i) => (
                    <p key={`a${i}`} className="text-[11px] text-[var(--text-secondary)]">
                      · {a}
                    </p>
                  ))}
                </div>
              )}

              {violationMsgs.length > 0 && (
                <div className="mt-2 space-y-0.5">
                  <span className="text-[9px] font-black uppercase tracking-widest text-[var(--status-warning)]">
                    검증 위반
                  </span>
                  {violationMsgs.map((v, i) => (
                    <p key={`v${i}`} className="inline-flex items-center gap-1.5 text-[11px] font-bold text-red-400">
                      <AlertTriangle className="size-3.5" aria-hidden />{v}
                    </p>
                  ))}
                </div>
              )}

              {!hasVerdict && (
                <p className="mt-2 text-[10px] text-[var(--text-hint)]">
                  서버가 검증 결과를 제공하지 않아 적용할 수 없습니다(정직 게이트).
                </p>
              )}

              {canApply && !applied && (
                <button
                  type="button"
                  onClick={() => {
                    if (result.design_payload && result.summary) {
                      onApply(result.design_payload, result.summary);
                      setApplied(true);
                    }
                  }}
                  className="mt-2 w-full rounded-xl bg-[var(--accent-strong)] px-3 py-2 text-xs font-black text-white"
                >
                  스튜디오 적용
                </button>
              )}
              {hasVerdict && !passed && (
                <p className="mt-2 text-[10px] font-bold text-[var(--status-warning)]">
                  법규 검증 위반 — 위반이 해소된 초안만 스튜디오에 적용할 수 있습니다.
                </p>
              )}
              {applied && (
                <p className="mt-2 text-[10px] font-black text-[var(--accent-strong)]">
                  ✓ 스튜디오에 적용됨 — 2D/3D가 이 초안으로 갱신됩니다
                </p>
              )}

              <button
                type="button"
                onClick={handleAssemble}
                disabled={assembling}
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-soft)] disabled:opacity-40"
              >
                {assembling ? "다시 생성 중…" : "다시 생성"}
              </button>
            </div>
          )}
        </div>
      ) : (
        item.has_geometry === false && (
          <p className="mt-2 text-[10px] text-[var(--text-hint)]">
            기하 데이터 없음 — 메타 참고용 사례입니다(관리자가 DXF 기하를 등록하면 조립 가능).
          </p>
        )
      )}
    </div>
  );
}

/** 점수 분해 미니바 — score/max 전부 서버값(가공 없음). max 부재 시 0~100 가정 클램프만. */
function ScoreBreakdownBars({ parts }: { parts: SimilarScorePart[] }) {
  return (
    <div className="mt-3 space-y-1.5">
      <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
        적합도 산출 근거
      </span>
      {parts.map((p) => {
        const max = typeof p.max === "number" && Number.isFinite(p.max) && p.max > 0 ? p.max : 100;
        const pct = Math.max(0, Math.min(100, (p.score / max) * 100));
        const label = (typeof p.label === "string" && p.label.trim()) || p.key;
        return (
          <div key={p.key}>
            <div className="flex items-center justify-between text-[10px]">
              <span className="font-bold text-[var(--text-secondary)]">{label}</span>
              <span className="font-black tabular-nums text-[var(--text-primary)]">
                {Math.round(p.score)}
                {typeof p.max === "number" && Number.isFinite(p.max) && p.max > 0
                  ? `/${Math.round(p.max)}`
                  : ""}
              </span>
            </div>
            <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
              <div
                className="h-full rounded-full bg-[var(--accent-strong)]"
                style={{ width: `${pct}%` }}
              />
            </div>
            {typeof p.basis === "string" && p.basis.trim() && (
              <p className="mt-0.5 text-[9px] text-[var(--text-hint)]">{p.basis.trim()}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PreviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--surface)] px-2 py-1.5 text-center">
      <div className="cc-num text-sm leading-none">{value}</div>
      <div className="mt-1 text-[9px] font-bold uppercase tracking-wide text-[var(--text-hint)]">
        {label}
      </div>
    </div>
  );
}
