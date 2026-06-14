/**
 * §4-C 법규주석 — 설계 compliance(엔진 산출)를 도면 finding·기하로 변환하는 순수 로직.
 *
 * GenerativeDesignPanel에서 분리해 단위 테스트 가능하게 한다(정직성 핵심 분기 검증).
 * 모두 순수 함수 — 동일 입력 = 동일 출력, 부작용 없음.
 */

import type {
  AnnotatedSiteGeometry,
  AutoDesignCompliance,
  AutoDesignSummary,
  LegalFinding,
  LegalLimitsResponse,
} from "@/components/cad/types";

/**
 * 설계 compliance를 법규주석 도면 finding으로 변환(정직 — 실 산출값).
 * 건폐율·용적률·높이를 status(pass/fail)·현재/한도로 표기. *_ok가 **명시 false**일 때만
 * fail로 한다(undefined를 fail로 오판 금지). 높이 한도가 0/무제한이면 높이 항목 생략.
 */
export function buildLegalFindings(
  s: AutoDesignSummary,
  c: AutoDesignCompliance,
  lim?: LegalLimitsResponse,
): LegalFinding[] {
  const out: LegalFinding[] = [
    {
      check_id: "rules8_건폐율", engine: "rules8",
      status: c.bcr_ok === false ? "fail" : "pass",
      current: s.bcr_percent, limit: lim?.max_bcr_percent ?? null,
    },
    {
      check_id: "rules8_용적률", engine: "rules8",
      status: c.far_ok === false ? "fail" : "pass",
      current: s.far_percent, limit: lim?.max_far_percent ?? null,
    },
  ];
  if (lim?.max_height_m && lim.max_height_m > 0) {
    out.push({
      check_id: "rules8_높이", engine: "rules8",
      status: c.height_ok === false ? "fail" : "pass",
      current: s.building_height_m, limit: lim.max_height_m,
    });
  }
  return out;
}

/**
 * 주석 배치도 기하 — 건물 치수는 엔진 산출(정직), 부지 경계는 대지면적 기반 개략(도식).
 * 건물이 개략 부지에 들어가도록 부지변=max(√면적, 건물변+여유). 건물 치수 산출 불가 시 null.
 * building_width/depth_m 미제공(구버전) 시 building_area_sqm √근사로 폴백.
 */
export function annotatedGeometryFor(
  siteArea: number,
  s: AutoDesignSummary,
): AnnotatedSiteGeometry | null {
  const fallback = Math.sqrt(Math.max(0, s.building_area_sqm || 0));
  const bw = typeof s.building_width_m === "number" && s.building_width_m > 0 ? s.building_width_m : fallback;
  const bd = typeof s.building_depth_m === "number" && s.building_depth_m > 0 ? s.building_depth_m : fallback;
  if (!(bw > 0 && bd > 0)) return null;
  const side = Math.sqrt(Math.max(1, siteArea));
  const r1 = (v: number) => Math.round(v * 10) / 10;
  return {
    site_width_m: r1(Math.max(side, bw + 4)),
    site_depth_m: r1(Math.max(side, bd + 4)),
    building_width_m: r1(bw),
    building_depth_m: r1(bd),
    setback_m: 3,
  };
}

/** compliance.all_pass를 정직 판정 라벨로(불리언일 때만 단정, undefined면 보류 null). */
export function complianceVerdict(c: Pick<AutoDesignCompliance, "all_pass">): string | null {
  if (c.all_pass === true) return "적합";
  if (c.all_pass === false) return "부적합";
  return null;
}
