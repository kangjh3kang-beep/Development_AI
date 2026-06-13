/**
 * §4-C 후속: design-audit 리포트(8엔진 findings)를 법규주석 배치도 입력으로 변환하는 순수 로직.
 *
 * 워크스페이스(DesignAuditWorkspace)는 findings + 대지면적만 있고 건물 치수는 없으므로, 면적과
 * 건폐율 finding으로 개략(도식) 배치를 도출한다(건폐율 없으면 null — 가짜 금지). AuditFinding의
 * 한/영 혼용 status(부적합⊃적합·조건부적합⊃부적합)를 안전 순서로 매핑한다.
 * 모두 순수 함수 — 단위 테스트 가능(§4-C legalAnnotation 패턴).
 */

import type { AnnotatedSiteGeometry, LegalFinding } from "@/components/cad/types";
import type { DesignAuditReport } from "./AuditReportView";

function toNum(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const n = Number(v.replace(/[^0-9.\-]/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * 한/영 혼용 status → pass|warning|fail|null. 부분문자 함정(부적합⊃적합, 조건부적합⊃부적합)을
 * 피하려 **조건부 → 부적합 → 적합** 순으로 판정. 판정불가/skipped/info/빈값은 null(제외).
 */
export function mapAuditStatus(s: string | null | undefined): "pass" | "warning" | "fail" | null {
  const v = (s ?? "").toString().toLowerCase().trim();
  if (!v) return null;
  if (/조건부|warn/.test(v)) return "warning";
  if (/부적합|fail/.test(v)) return "fail";
  if (/적합|pass/.test(v)) return "pass";
  return null;
}

/** 리포트 sections의 findings를 평탄화해 LegalFinding[]으로 변환(판정 가능분만, solar 엔진 인식). */
export function auditFindingsToLegal(report: DesignAuditReport): LegalFinding[] {
  const out: LegalFinding[] = [];
  for (const sec of report.sections ?? []) {
    for (const f of sec.findings ?? []) {
      const status = mapAuditStatus(f.status);
      if (!status) continue;
      const name = (f.item ?? f.label ?? "").toString().trim();
      const isSolar = /일조|정북/.test(name);
      out.push({
        check_id: isSolar ? "solar_envelope" : `rules8_${name || "검토"}`,
        engine: isSolar ? "solar_envelope" : "rules8",
        status,
        current: toNum(f.current),
        limit: toNum(f.limit),
      });
    }
  }
  return out;
}

/**
 * 대지면적 + 건폐율 finding으로 개략 배치도 기하(도식)를 도출. 건폐율 finding이 없으면 건물
 * footprint를 정직하게 도출할 수 없어 null(카드 미표시). 부지=√면적 정사각, 건물=√footprint.
 */
export function auditSchematicGeometry(
  landAreaSqm: number | null | undefined,
  legalFindings: LegalFinding[],
): AnnotatedSiteGeometry | null {
  if (!landAreaSqm || landAreaSqm <= 0) return null;
  const bcrF = legalFindings.find((f) => (f.check_id ?? "").includes("건폐"));
  const bcr = bcrF && typeof bcrF.current === "number" && bcrF.current > 0 ? bcrF.current : null;
  if (!bcr) return null;
  const side = Math.sqrt(landAreaSqm);
  const bside = Math.sqrt(landAreaSqm * (bcr / 100));
  const r1 = (x: number) => Math.round(x * 10) / 10;
  const b = r1(Math.min(bside, side - 1));
  if (!(b > 0)) return null;
  return {
    site_width_m: r1(side),
    site_depth_m: r1(side),
    building_width_m: b,
    building_depth_m: b,
    setback_m: 3,
  };
}

/** 리포트 verdict → 적합/조건부적합/부적합 (부분문자 함정 회피, 불명은 null). */
export function auditVerdict(report: DesignAuditReport): string | null {
  const v = (report.verdict ?? report.verdict_label ?? "").toString().toLowerCase();
  if (/조건부|conditional/.test(v)) return "조건부적합";
  if (/부적합|non.?compliant/.test(v)) return "부적합";
  if (/적합|compliant/.test(v)) return "적합";
  return null;
}
