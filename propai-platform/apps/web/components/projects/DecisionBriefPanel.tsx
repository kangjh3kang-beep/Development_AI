"use client";

/**
 * DecisionBriefPanel — Stage1 통합 의사결정 브리프 패널(자급식).
 *
 * 주소(SSOT) 하나로 3개 통합 도메인 카드(부지·입지·시장 통합 / 법규·규제 / 인허가·사업모델
 * Top3·설계개요)를 한 번에 모아 단일 종합 판정(GO/CONDITIONAL/HOLD)을 보여주는 Tier1 기본
 * 진입점이다. 비전문가가 "이 땅, 추진할까?"에 한 화면에서 답을 얻게 한다(인간개입 최소화·전문가 대행).
 *
 * 동작:
 *   - POST /api/v1/projects/{id}/decision-brief 호출(apiClient.post).
 *   - ★자동 전체실행: 주소(effectiveLandAreaSqm 짝의 SSOT.address)가 있으면 마운트 시 자동 호출.
 *   - 로딩/에러/부분 unavailable 상태를 정직하게 표기(catch silent-hide 금지 — 상태코드 분류).
 *   - 결과를 useProjectContextStore.decisionBrief에 적재(Tier2 재사용·중복분석 방지).
 *   - ★자급식(canvas 비의존)으로 export — 향후 SiteCanvas 요약탭에도 그대로 마운트 가능.
 *
 * SSOT: address·통합면적은 useProjectContextStore + effectiveLandAreaSqm 단일 출처에서만 읽는다.
 * lucide-react 아이콘(이모지 금지)·디자인 토큰(CSS 변수)만 사용.
 *
 * ★라이브·실배포=deploy-pending: 백엔드 라우트는 배포 환경에서만 동작한다(샌드박스 불가).
 *   meta.deploy_pending이면 그 사실을 화면에 정직 고지한다(가짜 동작 위장 금지).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2, RefreshCw, AlertTriangle, Compass } from "lucide-react";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm, analysisInputSignature } from "@/lib/site-area";
import { DecisionVerdictCard } from "@/components/projects/DecisionVerdictCard";
import { DomainSummaryCard } from "@/components/projects/DomainSummaryCard";
import type { DecisionBrief } from "@/components/projects/decision-brief-types";

/** 호출 상태 — 로딩/에러/완료를 명시적으로 구분(silent-fail 금지). */
type FetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; status: number | null; message: string }
  | { kind: "ready" };

/**
 * detail_route('/projects/{id}/canvas' 등)에 projectId·locale prefix를 적용해 실제 href로 변환.
 * locale prefix 책임은 프론트(이 함수). {id}가 없거나 projectId가 없으면 prefix만 적용.
 */
function toDetailHref(
  detailRoute: string | null | undefined,
  projectId: string | null,
  locale: string,
): string | null {
  if (!detailRoute) return null;
  const filled = projectId ? detailRoute.replace("{id}", projectId) : detailRoute;
  // 이미 절대(/로 시작)면 locale prefix만 한 번 붙인다.
  const path = filled.startsWith("/") ? filled : `/${filled}`;
  return `/${locale}${path}`;
}

export function DecisionBriefPanel({
  projectId,
  /** 자동 전체실행(주소 있으면 마운트 시 자동 호출). 기본 true. */
  autoRun = true,
}: {
  projectId: string;
  autoRun?: boolean;
}) {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";

  // SSOT 단일 출처 — address·통합면적(effectiveLandAreaSqm)은 store에서만 읽는다.
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const decisionBrief = useProjectContextStore((s) => s.decisionBrief);
  const setDecisionBrief = useProjectContextStore((s) => s.setDecisionBrief);
  const address = siteAnalysis?.address ?? null;
  const landAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  // ★dedup/staleness 시그니처 = 주소 + 유효면적(다필지 통합면적 우선). 주소만이 아니라 면적까지
  //   봐서, 다필지 보강으로 통합면적이 바뀌면 시그니처가 달라져 옛 대표면적 브리프 재사용을 막는다
  //   (HIGH 'stale-brief' 경합 해소 — lib/site-area.analysisInputSignature 공용 헬퍼로 일원화).
  const inputSig = analysisInputSignature(siteAnalysis);

  const [state, setState] = useState<FetchState>({ kind: "idle" });
  // 같은 입력(주소+면적 시그니처)으로 중복 호출을 막는 두 단계 가드(force면 무시):
  //   - lastFetchedSig: '완료된' 입력(응답 커밋됨) — 재실행 불필요 판정용.
  //   - inFlightSig: '지금 비행 중'인 입력 — ★await 이전에 즉시 세팅해 StrictMode 이중 마운트나
  //     동시 2발(같은 inputSig)이 둘 다 통과하는 경합을 차단한다(POST 정확히 1회).
  const lastFetchedSig = useRef<string | null>(null);
  const inFlightSig = useRef<string | null>(null);
  // ★시퀀스 토큰: 응답 역순 도착(면적 연속변경 등) 시 '마지막으로 시작한' 요청의 응답만 커밋한다
  //   (last-write-wins 가 아니라 latest-input-wins). 매 요청 시작 시 증가시키고, 응답·에러 커밋
  //   직전에 자신이 최신인지 확인한다(낡은 응답 폐기).
  const reqSeq = useRef(0);

  const run = useCallback(
    async (force = false) => {
      if (!address) {
        // 주소 미확보 — silent 금지. 정직 안내 상태로 둔다(idle 유지).
        setState({ kind: "idle" });
        return;
      }
      if (
        !force &&
        inputSig &&
        lastFetchedSig.current === inputSig &&
        decisionBrief
      ) {
        // 같은 입력(주소+면적)으로 이미 적재됨 → 중복 분석 방지(store 재사용).
        setState({ kind: "ready" });
        return;
      }
      // ★in-flight dedup — 같은 입력이 이미 비행 중이면 새 호출을 발사하지 않는다(force 제외).
      //   await 이전에 동기적으로 검사·세팅하므로 StrictMode 이중 호출도 1회로 합쳐진다.
      if (!force && inputSig && inFlightSig.current === inputSig) {
        return;
      }
      const mySeq = ++reqSeq.current;
      inFlightSig.current = inputSig;
      setState({ kind: "loading" });
      try {
        const body: Record<string, unknown> = { address };
        if (typeof landAreaSqm === "number" && landAreaSqm > 0) {
          body.land_area_sqm = landAreaSqm;
        }
        if (force) body.force_refresh = true;
        const data = await apiClient.post<DecisionBrief>(
          `/projects/${encodeURIComponent(projectId)}/decision-brief`,
          { body },
        );
        // ★최신 요청만 커밋 — 더 늦게 시작된 요청이 있으면(낡은 응답) 폐기한다.
        if (mySeq !== reqSeq.current) return;
        setDecisionBrief(data);
        lastFetchedSig.current = inputSig;
        setState({ kind: "ready" });
      } catch (err) {
        // 낡은 요청의 에러는 최신 상태를 덮어쓰지 않는다(latest-input-wins).
        if (mySeq !== reqSeq.current) return;
        // ★silent-hide 금지: 상태코드를 분류해 정직 에러 상태로 표면화한다.
        if (err instanceof ApiClientError) {
          const msg =
            err.status === 404
              ? "통합 의사결정 엔드포인트가 아직 배포되지 않았습니다(deploy-pending)."
              : err.status === 401 || err.status === 403
                ? "이 분석을 보려면 로그인 또는 권한이 필요합니다."
                : err.status === 429
                  ? "요청이 많아 잠시 후 다시 시도해야 합니다(요청 한도 초과)."
                  : err.status === 408 || err.status === 504
                    ? "분석 응답이 지연되어 시간이 초과되었습니다. 잠시 후 다시 시도하세요."
                    : err.status === 502 || err.status === 503
                      ? "분석 서버가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도하세요."
                      : "통합 의사결정 분석에 실패했습니다.";
          setState({ kind: "error", status: err.status, message: msg });
        } else {
          setState({
            kind: "error",
            status: null,
            message:
              "네트워크 오류로 통합 의사결정 분석을 불러오지 못했습니다.",
          });
        }
      } finally {
        // 비행 종료 — 단, 그 사이 더 새 요청이 시작됐으면 그 요청의 inFlightSig 를 보존한다.
        if (mySeq === reqSeq.current) inFlightSig.current = null;
      }
    },
    [address, projectId, landAreaSqm, inputSig, decisionBrief, setDecisionBrief],
  );

  // ★자동 전체실행 — 주소/유효면적(inputSig) 변경 시 자동 호출(중복은 run 내부 가드로 차단).
  //   inputSig를 트리거로 두어, 다필지 보강으로 통합면적이 바뀌면 자동 재분석된다(stale 방지).
  useEffect(() => {
    if (!autoRun || !inputSig) return;
    void run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, inputSig]);

  // ── 주소 미확보: 정직 안내(가짜 분석 금지) ──
  if (!address) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-[3rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-12 text-center">
        <Compass className="size-10 text-[var(--text-tertiary)]" aria-hidden />
        <p className="text-base font-black text-[var(--text-primary)]">
          분석할 주소가 없습니다
        </p>
        <p className="max-w-md text-sm leading-relaxed text-[var(--text-secondary)]">
          부지 주소를 입력하면 부지·입지·시장·법규·인허가·설계 Top3를 한 번에 모아
          통합 의사결정(추진할까?)을 자동으로 산출합니다.
        </p>
      </div>
    );
  }

  const brief = state.kind === "ready" ? decisionBrief : null;
  const deployPending = brief?.meta?.deploy_pending === true;
  // ★면적 override 괴리 경고(dead-wire 해소): 백엔드 meta.area_override.warning 이 있으면
  //   (통합면적이 엔진 대표면적과 5배 초과 괴리=잘못된 면적 가능성) 정직하게 경고배너를 띄운다.
  //   warning 이 없으면(정상 범위·override 미적용) 배너를 렌더하지 않는다(잡음 방지).
  const areaWarning = brief?.meta?.area_override?.warning || null;

  return (
    <div className="flex flex-col gap-6">
      {/* 헤더 + 재분석 버튼 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-[1000] tracking-tight text-[var(--text-primary)]">
            통합 의사결정 브리프
          </h3>
          <p className="text-xs text-[var(--text-tertiary)]">{address}</p>
        </div>
        <button
          type="button"
          onClick={() => void run(true)}
          disabled={state.kind === "loading"}
          className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-[11px] font-black uppercase tracking-wider text-[var(--text-secondary)] transition-all hover:text-[var(--text-primary)] disabled:opacity-50"
        >
          {state.kind === "loading" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-3.5" aria-hidden />
          )}
          다시 분석
        </button>
      </div>

      {/* 로딩 */}
      {state.kind === "loading" && (
        <div className="flex flex-col items-center gap-3 rounded-[2.5rem] border border-[var(--line)] bg-[var(--surface-soft)] p-12 text-center">
          <Loader2 className="size-8 animate-spin text-[var(--accent-strong)]" aria-hidden />
          <p className="text-sm font-bold text-[var(--text-secondary)]">
            부지·시장·법규·인허가를 모아 통합 판정을 산출하는 중...
          </p>
        </div>
      )}

      {/* 에러 — 정직 표기(상태코드 분류 메시지) */}
      {state.kind === "error" && (
        <div className="flex flex-col items-center gap-3 rounded-[2.5rem] border border-[color-mix(in_srgb,var(--status-error)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_6%,transparent)] p-10 text-center">
          <AlertTriangle className="size-8 text-[var(--status-error)]" aria-hidden />
          <p className="text-sm font-black text-[var(--text-primary)]">
            {state.message}
          </p>
          {state.status != null && (
            <p className="text-[11px] font-bold text-[var(--text-tertiary)]">
              상태 코드: {state.status}
            </p>
          )}
          <button
            type="button"
            onClick={() => void run(true)}
            className="mt-1 rounded-full bg-[var(--accent-strong)] px-5 py-2 text-[11px] font-black uppercase tracking-wider text-white"
          >
            다시 시도
          </button>
        </div>
      )}

      {/* 완료 — 종합 판정 + 3개 통합 도메인 카드(부지·시장/법규/인허가·Top3) */}
      {state.kind === "ready" && brief && (
        <div className="flex flex-col gap-6">
          {deployPending && (
            <div className="flex items-start gap-2.5 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] px-4 py-3">
              <AlertTriangle
                className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]"
                aria-hidden
              />
              <p className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">
                {brief.meta?.deploy_pending_note ||
                  "라이브 데이터·공공API·LLM 실호출은 배포 환경에서만 동작합니다(현재 deploy-pending)."}
              </p>
            </div>
          )}

          {/* ★면적 override 괴리 경고 — 통합면적이 엔진 대표면적과 과도(5배 초과)하게 다르면 표면화 */}
          {areaWarning && (
            <div
              className="flex items-start gap-2.5 rounded-2xl border px-4 py-3"
              style={{
                borderColor:
                  "color-mix(in srgb, var(--status-warning) 35%, transparent)",
                backgroundColor:
                  "color-mix(in srgb, var(--status-warning) 8%, transparent)",
              }}
              role="alert"
            >
              <AlertTriangle
                className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]"
                aria-hidden
              />
              <p className="text-[11px] font-bold leading-relaxed text-[var(--text-secondary)]">
                {areaWarning}
              </p>
            </div>
          )}

          <DecisionVerdictCard brief={brief} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {brief.parts.map((part) => (
              <DomainSummaryCard
                key={part.part}
                part={part}
                detailHref={toDetailHref(part.detail_route, projectId, locale)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
