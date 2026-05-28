"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useCadStore } from "@/store/use-cad-store";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { getZoningSpec } from "@/lib/kr-building-regulations";
import { Button, Card, CardContent, Badge } from "@propai/ui";

/* ── Types (백엔드 /cad-correction 스키마) ── */

interface ViolationItem {
  item: string;
  current_value: number;
  limit_value: number;
  excess: number;
}

interface CheckResponse {
  is_compliant: boolean;
  violations: ViolationItem[];
  building_info: {
    bcr: number;
    far: number;
    height_m: number;
    gross_floor_area_sqm: number;
  };
}

interface CorrectionResponse {
  original: Record<string, number>;
  corrected: Record<string, number>;
  violations_before: ViolationItem[];
  violations_after: ViolationItem[];
  iterations: number;
  is_compliant: boolean;
  corrections_applied: string[];
}

/* ── Helpers ── */

function severityFromExcess(excess: number) {
  if (excess > 20) return "high";
  if (excess > 5) return "med";
  return "low";
}

function severityVariant(severity: string) {
  switch (severity) {
    case "high":
      return "error" as const;
    case "med":
      return "warning" as const;
    default:
      return "info" as const;
  }
}

function severityLabel(severity: string) {
  switch (severity) {
    case "high":
      return "심각";
    case "med":
      return "주의";
    default:
      return "정보";
  }
}

/* ── Component ── */

type CadCompliancePanelProps = {
  projectId: string;
};

export function CadCompliancePanel({ projectId }: CadCompliancePanelProps) {
  const rects = useCadStore((s) => s.rects);
  const polygons = useCadStore((s) => s.polygons);
  const points = useCadStore((s) => s.points);
  const cadScale = useCadStore((s) => s.scale);
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);

  // 부지분석 데이터에서 대지면적/용도지역 가져오기
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const siteAreaFromContext = siteAnalysis?.landAreaSqm ?? null;
  const zoneCodeFromContext = siteAnalysis?.zoneCode ?? null;

  // 용도지역에서 법규 한도 조회
  const zoningSpec = zoneCodeFromContext ? getZoningSpec(zoneCodeFromContext) : null;
  const maxBcr = zoningSpec?.buildingCoverageMax ?? 60;
  const maxFar = zoningSpec?.floorAreaRatioMax ?? 200;
  const maxHeightM = zoningSpec?.heightLimit ?? 0;

  const [checkResult, setCheckResult] = useState<CheckResponse | null>(null);
  const [correction, setCorrection] = useState<CorrectionResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 건물 바닥면적 계산 (rects + polygons)
  const calculateBuildingFootprint = useCallback(() => {
    let footprint = 0;
    for (const rc of rects) {
      footprint += (rc.width / cadScale) * (rc.height / cadScale);
    }
    for (const pg of polygons) {
      const pts = pg.pointIds
        .map((pid) => points.find((p) => p.id === pid))
        .filter((p): p is NonNullable<typeof p> => p !== undefined);
      if (pts.length < 3) continue;
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const j = (i + 1) % pts.length;
        area += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
      }
      footprint += Math.abs(area) / 2 / (cadScale * cadScale);
    }
    return footprint;
  }, [rects, polygons, points, cadScale]);

  const getSiteArea = useCallback(() => {
    return siteAreaFromContext && siteAreaFromContext > 0 ? siteAreaFromContext : 500;
  }, [siteAreaFromContext]);

  const handleCheck = useCallback(async () => {
    setChecking(true);
    setError(null);
    try {
      const footprint = calculateBuildingFootprint();
      const siteArea = getSiteArea();
      const result = await apiClient.post<CheckResponse>("/cad-correction/check", {
        body: {
          building: {
            site_area_sqm: siteArea,
            building_area_sqm: footprint > 0 ? footprint : siteArea * 0.5,
            num_floors: floorCount,
            floor_height_m: floorCount > 0 ? buildingHeightM / floorCount : 3.0,
          },
          regulation: { max_bcr: maxBcr, max_far: maxFar, max_height_m: maxHeightM },
        },
      });
      setCheckResult(result);
      setCorrection(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "법규 검증에 실패했습니다.");
    } finally {
      setChecking(false);
    }
  }, [calculateBuildingFootprint, getSiteArea, floorCount, buildingHeightM, maxBcr, maxFar, maxHeightM]);

  const handleAutoCorrect = useCallback(async () => {
    if (!checkResult || checkResult.is_compliant) return;
    setCorrecting(true);
    setError(null);
    try {
      const footprint = calculateBuildingFootprint();
      const siteArea = getSiteArea();
      const result = await apiClient.post<CorrectionResponse>("/cad-correction/auto-correct", {
        body: {
          building: {
            site_area_sqm: siteArea,
            building_area_sqm: footprint > 0 ? footprint : siteArea * 0.5,
            num_floors: floorCount,
            floor_height_m: floorCount > 0 ? buildingHeightM / floorCount : 3.0,
          },
          regulation: { max_bcr: maxBcr, max_far: maxFar, max_height_m: maxHeightM },
          max_iter: 100,
        },
      });
      setCorrection(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "자동 보정에 실패했습니다.");
    } finally {
      setCorrecting(false);
    }
  }, [checkResult, calculateBuildingFootprint, getSiteArea, floorCount, buildingHeightM, maxBcr, maxFar, maxHeightM]);

  const handleApplyCorrection = useCallback(() => {
    if (!correction) return;
    const store = useCadStore.getState();
    const correctedHeight = correction.corrected?.height_m;
    if (correctedHeight && correctedHeight !== store.buildingHeightM) {
      store.setBuildingHeight(correctedHeight);
    }
    setCheckResult(null);
    setCorrection(null);
  }, [correction]);

  const hasViolations = checkResult && !checkResult.is_compliant;

  return (
    <Card className="border-[var(--line)] bg-[var(--surface)]">
      <CardContent className="flex flex-col gap-4 p-4">
        <div className="rounded-lg bg-[var(--surface-soft)] p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)] mb-1">적용 법규</p>
          <p className="text-xs text-[var(--text-secondary)]">{zoneCodeFromContext || "용도지역 미설정 (기본값 적용)"}</p>
          <p className="text-xs text-[var(--text-hint)] mt-1">
            대지면적: {getSiteArea().toLocaleString()}m&sup2; &middot; 건폐율 {maxBcr}% &middot; 용적률 {maxFar}%
            {maxHeightM > 0 && ` \u00B7 높이 ${maxHeightM}m`}
          </p>
          {!siteAreaFromContext && (
            <p className="text-[10px] text-amber-500 mt-1">부지분석을 먼저 실행하면 실제 대지면적/용도지역이 자동 반영됩니다.</p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">법규 검증</h3>
          <Button onClick={handleCheck} disabled={checking} className="w-full justify-center">
            {checking ? "검증 중..." : "법규 검증 실행"}
          </Button>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        {checkResult && (
          <div className="flex flex-col gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <span className={`text-xs font-bold ${checkResult.is_compliant ? "text-emerald-500" : "text-red-500"}`}>
              {checkResult.is_compliant ? "적합" : "부적합"}
            </span>
            <ComplianceRow label="건폐율 (BCR)" planned={checkResult.building_info.bcr} limit={maxBcr} compliant={!checkResult.violations.some((v) => v.item.includes("건폐율") || v.item.includes("bcr"))} unit="%" />
            <ComplianceRow label="용적률 (FAR)" planned={checkResult.building_info.far} limit={maxFar} compliant={!checkResult.violations.some((v) => v.item.includes("용적률") || v.item.includes("far"))} unit="%" />
            <ComplianceRow label="높이" planned={checkResult.building_info.height_m} limit={maxHeightM || 999} compliant={!checkResult.violations.some((v) => v.item.includes("높이") || v.item.includes("height"))} unit="m" />
            {checkResult.violations.length > 0 && (
              <div className="mt-2 flex flex-col gap-1">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">위반 사항</p>
                {checkResult.violations.map((v, i) => (
                  <div key={i} className="flex items-start gap-2 rounded-lg bg-[var(--surface)] p-2">
                    <Badge variant={severityVariant(severityFromExcess(v.excess))}>{severityLabel(severityFromExcess(v.excess))}</Badge>
                    <span className="text-xs text-[var(--text-secondary)]">{v.item}: {v.current_value.toFixed(1)} (한도 {v.limit_value.toFixed(1)}, 초과 {v.excess.toFixed(1)})</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">자동 보정</h3>
          <Button onClick={handleAutoCorrect} disabled={!hasViolations || correcting} className="w-full justify-center">
            {correcting ? "보정 중..." : "자동 보정"}
          </Button>
        </div>

        {correction && (
          <div className="flex flex-col gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">보정 결과 ({correction.iterations}회)</p>
            <CorrectionRow label="건폐율" before={correction.original?.bcr ?? 0} after={correction.corrected?.bcr ?? 0} unit="%" />
            <CorrectionRow label="용적률" before={correction.original?.far ?? 0} after={correction.corrected?.far ?? 0} unit="%" />
            <CorrectionRow label="높이" before={correction.original?.height_m ?? 0} after={correction.corrected?.height_m ?? 0} unit="m" />
            {correction.corrections_applied.length > 0 && (
              <ul className="mt-1 list-inside list-disc text-xs text-[var(--text-secondary)]">
                {correction.corrections_applied.map((desc, i) => <li key={i}>{desc}</li>)}
              </ul>
            )}
            <span className={`text-xs font-bold ${correction.is_compliant ? "text-emerald-500" : "text-amber-500"}`}>
              {correction.is_compliant ? "보정 후 적합" : "추가 검토 필요"}
            </span>
            <Button onClick={handleApplyCorrection} className="mt-2 w-full justify-center">보정안 적용</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ComplianceRow({ label, planned, limit, compliant, unit }: { label: string; planned: number; limit: number; compliant: boolean; unit: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="font-medium text-[var(--text-primary)]">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className={compliant ? "text-emerald-600" : "text-red-500"}>{compliant ? "\u2705" : "\u274C"}</span>
        <span className="text-[var(--text-secondary)]">{planned.toFixed(1)}{unit} / {limit.toFixed(1)}{unit}</span>
      </span>
    </div>
  );
}

function CorrectionRow({ label, before, after, unit }: { label: string; before: number; after: number; unit: string }) {
  const changed = Math.abs(before - after) > 0.01;
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="font-medium text-[var(--text-primary)]">{label}</span>
      <span className="text-[var(--text-secondary)]">
        {before.toFixed(1)}{unit}
        {changed && <>{" \u2192 "}<span className="font-bold text-emerald-600">{after.toFixed(1)}{unit}</span></>}
      </span>
    </div>
  );
}
