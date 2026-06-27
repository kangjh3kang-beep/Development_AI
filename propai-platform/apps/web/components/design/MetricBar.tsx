"use client";

/**
 * 설계 스튜디오 하단 "정본 메트릭바" — 한 창에서 부지·설계 핵심 수치를 상시 확인하는 띠.
 *
 * 왜 필요한가(쉬운 설명): 설계 스튜디오는 부지·설계생성·도면 단계를 오가는데, 사용자가
 *   "지금 이 부지의 대지면적·용도지역·건폐율/용적률·연면적·층수·세대수"를 어느 단계에서든
 *   바로 보고 싶어 한다. 이 띠는 그 7개 핵심 수치를 store(단일 진실원천)에서 직접 읽어
 *   화면 하단에 고정한다(어떤 단계든 같은 정본을 본다).
 *
 * 단일 진실원천(SSOT): 모든 값은 useProjectContextStore의 designData·siteAnalysis에서만
 *   읽고, 면적·용도지역·건폐율/용적률은 공용 리졸버(lib/zoning-ssot·lib/site-area)로 통일해
 *   "통합값 우선 → 실효 → 법정" 같은 우선순위를 한 곳에서 따른다(읽기 분기 방지).
 *
 * 무날조 원칙: 어떤 칩이든 값이 없으면(null/undefined) "—"로만 표기한다(가짜 0/임의값 금지).
 *   designData·siteAnalysis가 둘 다 없으면 띠 자체를 그리지 않는다("—" 7개 노출 방지).
 */

import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import {
  resolveBcrPct,
  resolveFarPct,
  resolveDominantZone,
} from "@/lib/zoning-ssot";

// 정수 ㎡ 표기(천단위 콤마). 미확보(null)면 "—". (가짜 0 금지 — 호출부에서 null 그대로 전달)
function fmtSqm(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${Math.round(v).toLocaleString()}㎡`;
}

// 퍼센트 표기(소수 그대로). 미확보면 "—".
function fmtPct(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${v}%`;
}

// 정수 + 단위 표기(층/세대 등). 미확보면 "—".
function fmtCount(v: number | null | undefined, suffix: string): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${v}${suffix}`;
}

// 문자열 표기(용도지역 등). 빈값/미확보면 "—".
function fmtText(v: string | null | undefined): string {
  return typeof v === "string" && v.trim() ? v.trim() : "—";
}

// 칩 1개 — 라벨(작은 글씨) + 값(모노 계기 수치). 좁은 화면에선 가로스크롤(shrink-0).
function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-[6.5rem] shrink-0 flex-col justify-center gap-0.5 px-3">
      <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{label}</span>
      <span className="cc-num text-sm text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

export function MetricBar({ className }: { className?: string }) {
  // store 직접 구독(자체 SSOT 읽기) — props로 값을 받지 않아 어느 단계에서든 같은 정본을 본다.
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 데이터 전무(둘 다 없음)면 띠 자체를 렌더하지 않는다(빈 "—" 7개 노출 방지).
  if (!designData && !siteAnalysis) return null;

  // 대지면적 — 다필지 통합 우선 유효 면적(공용 헬퍼). 미확보 시 null.
  const landAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  // 용도지역 — resolveDominantZone이 내부에서 dominantZoneCode ?? zoneCode를 이미 폴백(단일경유).
  const zone = resolveDominantZone(siteAnalysis);
  // 건폐율/용적률 — 설계 산출(designData) 우선, 없으면 부지 실효값(공용 리졸버). 미확보 시 null.
  const bcr = designData?.bcr ?? resolveBcrPct(siteAnalysis) ?? null;
  const far = designData?.far ?? resolveFarPct(siteAnalysis) ?? null;
  // 연면적·정본 층수·세대수 — 설계 산출(designData)에서만. 미확보 시 null → "—".
  const gfa = designData?.totalGfaSqm ?? null;
  const floors = designData?.floorCount ?? null; // ★INC1이 canonicalFloors로 기록한 정본 층수
  const units = designData?.unitCount ?? null;

  return (
    <div
      className={[
        // grid 행으로 물리 분리되므로 z-index 비의존. 좁으면 가로스크롤, 모바일은 줄바꿈 허용.
        "cc-panel flex min-h-[64px] items-center gap-1 overflow-x-auto px-2 py-2",
        "max-md:flex-wrap max-md:overflow-x-visible",
        className ?? "",
      ].join(" ")}
      role="group"
      aria-label="정본 메트릭"
    >
      <Chip label="대지면적" value={fmtSqm(landAreaSqm)} />
      <Chip label="용도지역" value={fmtText(zone)} />
      <Chip label="건폐율" value={fmtPct(bcr)} />
      <Chip label="용적률" value={fmtPct(far)} />
      <Chip label="연면적" value={fmtSqm(gfa)} />
      <Chip label="층수" value={fmtCount(floors, "층")} />
      <Chip label="세대수" value={fmtCount(units, "세대")} />
    </div>
  );
}
