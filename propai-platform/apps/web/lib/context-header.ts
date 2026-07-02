// 생성허브 공용 대상 컨텍스트 헤더 — 표시 데이터 파생 유틸(순수 함수·무목업).
//
// 왜 필요한가(쉬운 설명):
// 후보지진단서·사업성검토서·시장분양리포트·인허가체크리스트·AI설계검토서·건축개요CAD 등
// "생성허브 6산출물"은 각기 다른 셸에 흩어져 있어, 사용자가 "이 산출물이 '어느 프로젝트·어느
// 토지'를 대상으로 분석한 것인지" 화면에서 알 수 없었다. 이 유틸은 프로젝트 컨텍스트 스토어
// (useProjectContextStore)의 단일 진실원천(SSOT)에서 표시용 값(프로젝트명·주소·PNU·용도지역·
// 대지면적·다필지 통합 여부)을 뽑아 ContextHeader 공용 컴포넌트가 6페이지 어디서나 동일하게
// 상시 표시하도록 한다(한 곳을 고치면 6페이지가 따라옴).
//
// ★기존 헬퍼 재사용(그린필드 재발명 금지):
//   - effectiveLandAreaSqm(lib/site-area): 다필지면 통합면적 우선(경합 면역).
//   - resolveDominantZone(lib/zoning-ssot): 통합 dominant_zone 우선 → 단일 zoneCode 폴백.
//   - normalizeZoning(lib/kr-building-regulations): 용도지역 라벨 정규화(코드/변형→정식 한글).
//
// ★무목업: 컨텍스트가 없으면 값은 null(가짜 생성 금지). 소비 컴포넌트가 "대상 미선택"으로
//   정직하게 안내한다.

import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveDominantZone } from "@/lib/zoning-ssot";
import { normalizeZoning } from "@/lib/kr-building-regulations";

/** ContextHeader가 읽는 프로젝트 컨텍스트 입력(스토어 필드의 부분 집합). */
export interface ContextHeaderInput {
  projectId: string | null;
  projectName: string;
  siteAnalysis: SiteAnalysisData | null;
}

/** ContextHeader 표시용 파생 결과 — 미확보 값은 전부 null(무목업). */
export interface ContextHeaderData {
  /** 대상 컨텍스트가 하나라도 있는가(프로젝트 선택 또는 부지 주소 확보). false면 "대상 미선택". */
  hasContext: boolean;
  /** 프로젝트명(빈 문자열이면 null). */
  projectName: string | null;
  /** 대상 부지 주소(없으면 null). */
  address: string | null;
  /** 필지고유번호(PNU) — 없으면 null. */
  pnu: string | null;
  /** 용도지역 표시 라벨(정규화된 정식 한글, 정규화 실패 시 원문 코드, 미확보 시 null). */
  zoneLabel: string | null;
  /** 유효 대지면적(㎡·다필지면 통합면적) — 미확보 시 null. */
  landAreaSqm: number | null;
  /** 유효 필지 수(다필지 판정용). 단일/미확보면 1 또는 null. */
  parcelCount: number | null;
  /** 다필지 통합 여부(parcelCount >= 2). */
  isMultiParcel: boolean;
}

/** 문자열 정규화(공백 trim, 빈값이면 null). */
function str(v: string | null | undefined): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/**
 * 용도지역 코드/라벨 → 표시용 정식 한글 라벨.
 * normalizeZoning으로 정규화(예: "2R"·"제2종일반주거"→"제2종일반주거지역"), 실패하면 원문 그대로
 * 표시(미상 코드를 버리지 않고 정직하게 노출). 미확보 시 null.
 */
export function zoneDisplayLabel(zoneCode: string | null | undefined): string | null {
  const raw = str(zoneCode);
  if (!raw) return null;
  return normalizeZoning(raw) ?? raw;
}

/**
 * 프로젝트 컨텍스트(SSOT)에서 ContextHeader 표시 데이터를 파생한다(순수 함수).
 *
 * - 대지면적: effectiveLandAreaSqm(다필지=통합 우선)로 경합 면역 읽기.
 * - 용도지역: resolveDominantZone(통합 dominant > 단일 zoneCode) 후 표시 라벨 정규화.
 * - hasContext: 프로젝트 선택 또는 주소 확보 중 하나라도 있으면 true(무목업 안내 분기).
 */
export function deriveContextHeaderData(ctx: ContextHeaderInput): ContextHeaderData {
  const sa = ctx.siteAnalysis;
  const address = str(sa?.address);
  const pnu = str(sa?.pnu);
  const projectName = str(ctx.projectName);
  const parcelCount =
    typeof sa?.parcelCount === "number" && sa.parcelCount > 0
      ? sa.parcelCount
      : null;
  const isMultiParcel = (parcelCount ?? 1) > 1;
  const zoneLabel = zoneDisplayLabel(resolveDominantZone(sa));
  const landAreaSqm = effectiveLandAreaSqm(sa);
  const hasContext = !!(ctx.projectId || address || projectName);

  return {
    hasContext,
    projectName,
    address,
    pnu,
    zoneLabel,
    landAreaSqm,
    parcelCount,
    isMultiParcel,
  };
}
