"use client";

/**
 * 심의분석 결과 패널 — 플랫폼 BFF(POST /api/v1/deliberation/analyze) 결과 렌더.
 *
 * 쉬운 설명: 설계도서/규칙을 심의분석엔진에 보내 "법규 판정·구획 보고서·준수율"을 받아 화면에 보여준다.
 * 엔진이 아직 안 켜졌거나 연결이 끊기면 BFF가 degraded(연결 대기) 상태를 정직하게 돌려주므로,
 * 이 패널은 에러로 깨지지 않고 "심의엔진 연결 대기 — 결과 산출 시 표시"라고 안내만 한다.
 *
 * 무목업 원칙: 값이 없으면 아예 안 그린다('—'/'분석 전' 금지). degraded는 정직 안내, 결과는 실데이터만.
 * 근거 표기: run_id·input_hash(엔진이 산출을 재현·추적하는 결정론 키)를 함께 노출한다.
 *
 * #185 안전: 렌더 중 setState 금지, 새 객체/배열 셀렉터 미사용(로컬 useState만 보유).
 */

import { useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ── BFF 응답 계약(apps/api/app/routers/deliberation.py audit 노드 래핑) ── */
// 판정 1건(엔진 finding 미러). measured/limit은 정량 비교값(없을 수 있음).
type DeliberationFinding = {
  rule_id?: string;
  verdict?: string;
  measured_value?: number | null;
  limit_value?: number | null;
  basis_article?: string | null;
  requires_committee?: boolean;
};

// 구획 보고서 한 항목.
type SectionItem = { item_id?: string };

// 성공/degraded 공용 — 빠진 필드는 옵셔널(degraded면 findings:[], complianceScore:null 등).
type DeliberationResult = {
  status: string; // "ok" | "degraded"
  reason?: string | null; // degraded 사유(engine_unreachable·timeout·engine_rejected·invalid_response 등)
  run_id?: string | null;
  complianceScore?: number | null; // CONFIRMED 비율(0~100)
  finalStatus?: string | null; // BLOCKED > NEEDS_REVIEW > CONFIRMED
  findings?: DeliberationFinding[];
  sections?: Record<string, SectionItem[]>;
  skipped?: string[];
  snapshot_id?: string | null;
  input_hash?: string | null;
};

/* ── 판정/상태 색상 토큰 ── */
const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: "var(--status-success)",
  COMPLIANT: "var(--status-success)",
  NEEDS_REVIEW: "var(--status-warning)",
  CONDITIONAL: "var(--status-warning)",
  BLOCKED: "var(--status-error)",
  NON_COMPLIANT: "var(--status-error)",
};

// degraded 사유 → 쉬운 한국어 안내.
const REASON_LABEL: Record<string, string> = {
  engine_unreachable: "심의엔진에 연결할 수 없습니다",
  timeout: "심의엔진 응답이 지연되었습니다",
  engine_rejected: "심의엔진이 입력을 거절했습니다",
  invalid_response: "심의엔진 응답 형식이 올바르지 않습니다",
  circuit_open: "연속 장애로 호출이 일시 차단되었습니다",
};

function StatusTag({ value }: { value: string }) {
  const color = STATUS_COLOR[value] ?? "var(--text-tertiary)";
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-[11px] font-bold"
      style={{ color, borderColor: color }}
    >
      {value}
    </span>
  );
}

/**
 * 심의분석을 실행할 입력 페이로드.
 * 엔진 AnalysisInput 계약(미러 24필드)과 정합 — 라이브 검증용 기본 샘플.
 */
const SAMPLE_PAYLOAD = {
  pnu: "1111010100100000002",
  application_date: "2026-01-01",
  axis_date: "2026-01-01",
  drawing: { scale_text: "1:100" },
  calc_targets: [
    {
      target: "building_area",
      payload: { outer_area: 600.0 },
      elements: [{ semantic_type: "PILOTIS", area: 100.0, confidence: 0.95 }],
    },
  ],
  rules: [
    {
      rule: { rule_id: "far_limit", comparator: "<=", basis_article: "국토계획법 시행령" },
      measured: 250.0,
      limit: 200.0,
      confidence: 0.9,
    },
    {
      rule: { rule_id: "height_limit", comparator: "<=", basis_article: "건축법 시행령" },
      measured: 30.0,
      limit: 20.0,
      confidence: 0.9,
    },
  ],
};

export function DeliberationResultPanel() {
  const [result, setResult] = useState<DeliberationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // BFF는 인증 필수(apiClient가 토큰 자동 주입). 경로는 /api/v1 자동 prefix.
      const res = await apiClient.post<DeliberationResult>("/deliberation/analyze", {
        body: { payload: SAMPLE_PAYLOAD },
      });
      setResult(res);
    } catch (e) {
      // BFF는 degraded도 200으로 돌려주므로 여기 오는 건 인증/네트워크/서버 실제 오류뿐.
      if (e instanceof ApiClientError) {
        setError(
          e.status === 401 || e.status === 403
            ? "로그인이 필요합니다(심의분석은 인증 사용자 전용)."
            : `심의분석 호출 실패(HTTP ${e.status}).`,
        );
      } else {
        setError(`심의분석 호출 실패: ${(e as Error).message}`);
      }
    } finally {
      setLoading(false);
    }
  }

  // degraded 판정: BFF가 status를 'ok'가 아닌 값(주로 "degraded")으로 응답하면 결과 미산출.
  // ★run_id 부재는 degraded 신호가 아니다 — 멱등 재사용·캐시 경로 등에서 status:"ok"이면서도
  //   run_id가 비어 올 수 있으므로 결과를 degraded로 오판하면 안 된다(근거키 누락은 별도 표기).
  const isDegraded = !!result && result.status !== "ok";
  const degradedReason = result?.reason ?? "";
  const findings = result?.findings ?? [];
  const sections = result?.sections ?? {};
  const sectionEntries = Object.entries(sections).filter(([, items]) => items && items.length > 0);
  const skipped = result?.skipped ?? [];

  return (
    <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-6">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />

      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-black text-[var(--text-primary)]">심의분석 결과(BFF)</h2>
        <span className="cc-meta text-[var(--text-tertiary)]">POST /api/v1/deliberation/analyze</span>
      </div>
      <p className="relative z-10 mt-1 text-xs text-[var(--text-secondary)]">
        설계 산출(건폐율·용적률·높이)을 심의분석엔진 규칙으로 판정한다. 결정론·근거추적·무음 오판 0.
      </p>

      <div className="relative z-10 mt-4">
        <button
          onClick={run}
          disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
        >
          {loading ? "심의분석 중…" : "심의분석 실행"}
        </button>
      </div>

      {/* 실제 호출 오류(인증/네트워크) — degraded와 구분해 정직 표기. */}
      {error && (
        <p className="relative z-10 mt-4 whitespace-pre-wrap rounded-xl border border-[var(--status-error)] bg-[var(--surface-muted)] p-3 text-xs text-[var(--status-error)]">
          {error}
        </p>
      )}

      {/* degraded — 엔진 미연결/지연/거절. 에러로 깨지지 않고 정직 안내만. */}
      {isDegraded && (
        <div className="relative z-10 mt-4 rounded-xl border border-[var(--status-warning)] bg-[var(--surface-muted)] p-4">
          <div className="flex items-center gap-2">
            <StatusTag value="대기" />
            <span className="text-sm font-bold text-[var(--text-primary)]">
              심의엔진 연결 대기 — 결과 산출 시 표시
            </span>
          </div>
          {degradedReason && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              {REASON_LABEL[degradedReason] ?? degradedReason}
            </p>
          )}
        </div>
      )}

      {/* 정상 결과 — 값이 있는 것만 렌더(무목업). */}
      {result && !isDegraded && (
        <div className="relative z-10 mt-4 space-y-4">
          {/* 종합 판정·준수율 요약 */}
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3">
            {result.finalStatus && (
              <div className="flex items-center gap-2">
                <span className="cc-label text-[var(--text-tertiary)]">최종 판정</span>
                <StatusTag value={result.finalStatus} />
              </div>
            )}
            {result.complianceScore != null && (
              <div className="flex items-center gap-2">
                <span className="cc-label text-[var(--text-tertiary)]">준수율</span>
                <span className="text-sm font-black text-[var(--text-primary)]">
                  {Math.round(result.complianceScore)}%
                </span>
              </div>
            )}
          </div>

          {/* 구획 보고서(L5/L6) */}
          {sectionEntries.length > 0 && (
            <div>
              <div className="cc-label text-[var(--text-tertiary)]">구획 보고서</div>
              <div className="mt-1.5 space-y-1.5">
                {sectionEntries.map(([key, items]) => (
                  <div key={key} className="flex flex-wrap items-center gap-2">
                    <StatusTag value={key} />
                    <span className="text-xs text-[var(--text-secondary)]">
                      {items
                        .map((i) => i.item_id)
                        .filter((id): id is string => !!id)
                        .join(", ")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 판정 상세(R3) */}
          {findings.length > 0 && (
            <div>
              <div className="cc-label text-[var(--text-tertiary)]">판정 상세</div>
              <div className="mt-1.5 space-y-1.5">
                {findings.map((f, idx) => (
                  <div
                    key={f.rule_id ?? idx}
                    className="flex flex-wrap items-center gap-2 text-xs"
                  >
                    {f.rule_id && (
                      <span className="font-semibold text-[var(--text-primary)]">{f.rule_id}</span>
                    )}
                    {f.verdict && <StatusTag value={f.verdict} />}
                    {(f.measured_value != null || f.limit_value != null) && (
                      <span className="text-[var(--text-tertiary)]">
                        {f.measured_value != null ? f.measured_value : "?"} /{" "}
                        {f.limit_value != null ? f.limit_value : "?"}
                      </span>
                    )}
                    {f.basis_article && (
                      <span className="text-[var(--text-tertiary)]">· {f.basis_article}</span>
                    )}
                    {f.requires_committee && (
                      <span className="text-[var(--status-warning)]">· 위원확인</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 미수행 계층 */}
          {skipped.length > 0 && (
            <p className="text-[11px] text-[var(--text-tertiary)]">
              미수행 계층: {skipped.join(" · ")}
            </p>
          )}

          {/* 근거(결정론 추적 키) — run_id·input_hash */}
          {(result.run_id || result.input_hash) && (
            <div className="border-t border-[var(--line)] pt-2 text-[11px] text-[var(--text-tertiary)]">
              {result.run_id && (
                <span>
                  run_id <code className="text-[var(--accent-strong)]">{result.run_id}</code>
                </span>
              )}
              {result.input_hash && (
                <span className="ml-2">
                  input_hash{" "}
                  <code className="text-[var(--accent-strong)]">
                    {result.input_hash.slice(0, 16)}…
                  </code>
                </span>
              )}
              {result.snapshot_id && (
                <span className="ml-2">snapshot {result.snapshot_id}</span>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
