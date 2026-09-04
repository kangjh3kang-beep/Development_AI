"use client";

/**
 * 필지 경사도 섹션 — 필지 상세 온디맨드(사통맵 v2 W2).
 *
 * 시공사·디벨로퍼가 토공비를 가늠하려면 "이 필지가 얼마나 기울었나"가 필요하다. 값은 전부
 * 서버 산정(POST /api/v1/terrain/analyze — DEM 격자 중앙차분)이고 이 컴포넌트는 표시만 한다
 * (프론트에서 경사도를 다시 계산하거나 등급을 재정의하지 않는다).
 *
 * ★왜 버튼 온디맨드인가(측정 근거):
 *   표고 원천 OpenTopoData는 **1 req/s 공개 제한**이고 서버에 캐시가 없다(필지당 ~1초, 121점
 *   2배치 사이에 sleep(1.05) 강제). 필지를 열 때마다 자동 조회하면 사용자가 필지를 빠르게
 *   훑는 순간 동시 요청이 그 제한을 넘긴다(전역 리미터 없음). 그래서 **명시적 요청**으로 두고
 *   세션 캐시로 재조회를 없앤다 — 플랫폼의 "선택형 분석 기본(선택분만 실행)" 원칙과도 맞는다.
 *
 * ★정직 표기(이 컴포넌트의 존재 이유):
 *   ① 서버가 만든 `note`(SRTM 30m 한계·필지가 DEM 셀보다 작아 미세지형 분해 불가 등)를
 *      **그대로** 옮긴다. 요약·의역하면 한계가 흐려진다.
 *   ② `confidence`를 배지로 노출한다 — 낮은 신뢰도를 숫자만 보고 실측으로 오독하지 않게.
 *   ③ ok:false는 "경사도 0%"가 아니라 **조회 실패**로 표기한다(무날조).
 */

import { Mountain } from "lucide-react";

import type { TerrainResult } from "@/components/terrain/types";

export type ParcelSlopeStatus = "idle" | "loading" | "done" | "error";

/** 신뢰도(0~1) → 라벨. 서버 confidence를 그대로 구간화만 한다(값 재산정 없음). */
function confidenceLabel(confidence: number | undefined): string {
  if (typeof confidence !== "number") return "미상";
  if (confidence >= 0.7) return "비교적 높음";
  if (confidence >= 0.4) return "보통";
  return "낮음";
}

function confidenceColor(confidence: number | undefined): string {
  if (typeof confidence !== "number") return "var(--text-hint)";
  if (confidence >= 0.7) return "var(--status-success)";
  if (confidence >= 0.4) return "var(--status-warning)";
  return "var(--status-error)";
}

export function ParcelSlopeSection({
  status,
  result,
  errorMessage,
  otherRequestInFlight,
  onRequest,
}: {
  status: ParcelSlopeStatus;
  result?: TerrainResult | null;
  errorMessage?: string | null;
  /** 다른 필지의 조회가 진행 중 — 전역 1건 잠금이라 지금 누르면 무시된다는 사실을 고지한다. */
  otherRequestInFlight?: boolean;
  onRequest: () => void;
}) {
  const slope = result?.slope;

  return (
    <div
      data-testid="parcel-slope-section"
      className="col-span-2 border-t border-[var(--border-muted)] pt-2"
    >
      <div className="flex items-center justify-between gap-2">
        <dt className="flex items-center gap-1.5 font-black text-[var(--text-hint)]">
          <Mountain className="size-3.5 shrink-0" aria-hidden />
          경사도(DEM 추정)
        </dt>
        {status === "idle" || status === "error" ? (
          <button
            type="button"
            onClick={onRequest}
            data-testid="parcel-slope-request"
            /* ★모바일 IA P2(R1 봉합) — py-0.5+text-[10px] ≈ 18px 로 이 상세 패널에서 가장 작았다.
               필지 상세 팝오버 안이라 빗나간 탭이 팝오버 밖 지도로 샌다. */
            className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-[var(--border-muted)] px-2 py-0.5 text-[10px] font-black text-[var(--accent-strong)] transition hover:bg-[var(--surface-muted)]"
          >
            {status === "error" ? "다시 조회" : "경사도 조회"}
          </button>
        ) : null}
      </div>

      {status === "idle" ? (
        // ★조회 전에는 숫자를 만들지 않는다 — 비용(1req/s)과 이유를 함께 밝힌다.
        <p className="mt-1 text-[10px] font-semibold text-[var(--text-hint)]">
          미조회 — 표고(SRTM 30m) 조회에 약 1초가 걸려 필요할 때만 실행합니다.
        </p>
      ) : null}

      {otherRequestInFlight ? (
        // ★전역 1건 잠금이라 지금 누르면 조용히 무시된다 — 그 사실을 밝힌다(죽은 버튼 방지).
        <p
          data-testid="parcel-slope-busy-other"
          className="mt-1 text-[10px] font-semibold text-[var(--status-warning)]"
        >
          다른 필지 경사도를 조회하는 중입니다 — 끝난 뒤 다시 시도해 주세요.
        </p>
      ) : null}

      {status === "loading" ? (
        <p
          data-testid="parcel-slope-loading"
          className="mt-1 text-[11px] font-semibold text-[var(--text-hint)]"
        >
          표고 격자 조회 중…
        </p>
      ) : null}

      {status === "error" ? (
        <p
          data-testid="parcel-slope-error"
          className="mt-1 break-keep text-[11px] font-semibold text-[var(--status-error)]"
        >
          {/* ★실패를 "경사도 0%"로 표기하지 않는다(무날조). */}
          조회 실패 — {errorMessage || "표고 데이터를 가져오지 못했습니다."}
        </p>
      ) : null}

      {status === "done" && slope ? (
        <>
          <dd className="mt-1 grid grid-cols-3 gap-x-2 text-center">
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">평균</p>
              <p
                data-testid="parcel-slope-mean"
                className="font-mono font-bold text-[var(--text-primary)]"
              >
                {slope.mean_pct}%
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">최대</p>
              <p
                data-testid="parcel-slope-max"
                className="font-mono font-bold text-[var(--text-primary)]"
              >
                {slope.max_pct}%
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">등급</p>
              <p className="font-bold text-[var(--text-primary)]">{slope.class}</p>
            </div>
          </dd>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span
              data-testid="parcel-slope-confidence"
              className="rounded-full px-1.5 py-px text-[10px] font-black"
              style={{
                color: confidenceColor(result?.confidence),
                border: `1px solid ${confidenceColor(result?.confidence)}`,
              }}
              title="DEM 해상도·표고 취득률·폴리곤 클립으로 산정된 서버 신뢰도"
            >
              신뢰도 {confidenceLabel(result?.confidence)}
              {typeof result?.confidence === "number" ? ` (${result.confidence})` : ""}
            </span>
            <span className="rounded-full border border-[var(--status-warning)] px-1.5 py-px text-[10px] font-black text-[var(--status-warning)]">
              참고값 · 실측 필요
            </span>
          </div>
          {slope.detail ? (
            <p className="mt-1 break-keep text-[11px] font-semibold text-[var(--text-secondary)]">
              {slope.detail}
            </p>
          ) : null}
          {result?.note ? (
            // ★서버가 만든 한계 문구를 **그대로** 옮긴다(요약·의역 금지 — 한계가 흐려진다).
            <p
              data-testid="parcel-slope-note"
              className="mt-1 break-keep text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]"
            >
              {result.note}
            </p>
          ) : null}
        </>
      ) : null}

      {status === "done" && !slope ? (
        <p className="mt-1 text-[11px] font-semibold text-[var(--text-hint)]">
          경사도 산출 불가 — 표고 표본이 부족합니다(임의 수치 미생성).
        </p>
      ) : null}
    </div>
  );
}

export default ParcelSlopeSection;
