"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useCadStore } from "@/store/use-cad-store";
import { Button, Card, CardContent, Badge } from "@propai/ui";

/* ── Types ── */

interface ComplianceCheckResult {
  bcr: { planned: number; limit: number; compliant: boolean };
  far: { planned: number; limit: number; compliant: boolean };
  height: { planned: number; limit: number; compliant: boolean };
  violations: Array<{
    code: string;
    description: string;
    severity: "high" | "med" | "low";
  }>;
}

interface CorrectionResult {
  before: { bcr: number; far: number; height: number };
  after: { bcr: number; far: number; height: number };
  adjustments: Array<{ field: string; description: string }>;
}

/* ── Helpers ── */

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

  const [checkResult, setCheckResult] = useState<ComplianceCheckResult | null>(null);
  const [correction, setCorrection] = useState<CorrectionResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 건물 바닥면적 계산 (rects + polygons)
  const calculateBuildingFootprint = useCallback(() => {
    let footprint = 0;

    // Rect 면적 합산
    for (const rc of rects) {
      const wM = rc.width / cadScale;
      const hM = rc.height / cadScale;
      footprint += wM * hM;
    }

    // Polygon 면적 (Shoelace)
    for (const pg of polygons) {
      const pts = pg.pointIds
        .map((pid) => points.find((p) => p.id === pid))
        .filter((p): p is NonNullable<typeof p> => p !== undefined);
      if (pts.length < 3) continue;
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const j = (i + 1) % pts.length;
        area += pts[i].x * pts[j].y;
        area -= pts[j].x * pts[i].y;
      }
      footprint += Math.abs(area) / 2 / (cadScale * cadScale);
    }

    return footprint;
  }, [rects, polygons, points, cadScale]);

  // 법규 검증 실행
  const handleCheck = useCallback(async () => {
    setChecking(true);
    setError(null);
    try {
      const footprint = calculateBuildingFootprint();
      const siteArea = 1000; // 기본 대지면적 (추후 프로젝트 설정에서)
      const totalFloorArea = footprint * floorCount;
      const plannedBcr = (footprint / siteArea) * 100;
      const plannedFar = (totalFloorArea / siteArea) * 100;

      const result = await apiClient.post<ComplianceCheckResult>(
        "/cad-correction/check",
        {
          body: {
            address: "",
            zone_code: "2종일반주거",
            planned_bcr: plannedBcr,
            planned_far: plannedFar,
            planned_height_m: buildingHeightM,
            planned_floors: floorCount,
          },
        },
      );
      setCheckResult(result);
      setCorrection(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "법규 검증에 실패했습니다.";
      setError(message);
    } finally {
      setChecking(false);
    }
  }, [calculateBuildingFootprint, floorCount, buildingHeightM]);

  // 자동 보정
  const handleAutoCorrect = useCallback(async () => {
    if (!checkResult) return;
    setCorrecting(true);
    setError(null);
    try {
      const footprint = calculateBuildingFootprint();
      const siteArea = 1000;
      const totalFloorArea = footprint * floorCount;

      const result = await apiClient.post<CorrectionResult>(
        "/cad-correction/auto-correct",
        {
          body: {
            address: "",
            zone_code: "2종일반주거",
            planned_bcr: (footprint / siteArea) * 100,
            planned_far: (totalFloorArea / siteArea) * 100,
            planned_height_m: buildingHeightM,
            planned_floors: floorCount,
          },
        },
      );
      setCorrection(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "자동 보정에 실패했습니다.";
      setError(message);
    } finally {
      setCorrecting(false);
    }
  }, [checkResult, calculateBuildingFootprint, floorCount, buildingHeightM]);

  // 보정안 적용 (높이 / 층수 업데이트)
  const handleApplyCorrection = useCallback(() => {
    if (!correction) return;
    const store = useCadStore.getState();
    // 높이 보정 적용
    if (correction.after.height !== store.buildingHeightM) {
      store.setBuildingHeight(correction.after.height);
    }
    // BCR/FAR 보정은 rect 스케일링으로 반영
    // 간이: 보정 비율로 첫 번째 rect 크기 조정
    if (correction.after.bcr < correction.before.bcr && store.rects.length > 0) {
      const ratio = correction.after.bcr / Math.max(correction.before.bcr, 0.01);
      const rc = store.rects[0];
      const newW = rc.width * Math.sqrt(ratio);
      const newH = rc.height * Math.sqrt(ratio);
      const updatedRects = store.rects.map((r, i) =>
        i === 0 ? { ...r, width: newW, height: newH } : r,
      );
      useCadStore.setState({ rects: updatedRects });
    }
    setCheckResult(null);
    setCorrection(null);
  }, [correction]);

  const hasViolations =
    checkResult &&
    (!checkResult.bcr.compliant ||
      !checkResult.far.compliant ||
      !checkResult.height.compliant);

  return (
    <Card className="border-[var(--line)] bg-[var(--surface)]">
      <CardContent className="flex flex-col gap-4 p-4">
        {/* 법규 검증 */}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            법규 검증
          </h3>
          <Button
            onClick={handleCheck}
            disabled={checking}
            className="w-full justify-center"
          >
            {checking ? "검증 중..." : "법규 검증 실행"}
          </Button>
        </div>

        {error && (
          <p className="text-xs text-red-500">{error}</p>
        )}

        {checkResult && (
          <div className="flex flex-col gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <ComplianceRow
              label="건폐율 (BCR)"
              planned={checkResult.bcr.planned}
              limit={checkResult.bcr.limit}
              compliant={checkResult.bcr.compliant}
              unit="%"
            />
            <ComplianceRow
              label="용적률 (FAR)"
              planned={checkResult.far.planned}
              limit={checkResult.far.limit}
              compliant={checkResult.far.compliant}
              unit="%"
            />
            <ComplianceRow
              label="높이"
              planned={checkResult.height.planned}
              limit={checkResult.height.limit}
              compliant={checkResult.height.compliant}
              unit="m"
            />

            {checkResult.violations.length > 0 && (
              <div className="mt-2 flex flex-col gap-1">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
                  위반 사항
                </p>
                {checkResult.violations.map((v, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 rounded-lg bg-[var(--surface)] p-2"
                  >
                    <Badge variant={severityVariant(v.severity)}>
                      {severityLabel(v.severity)}
                    </Badge>
                    <span className="text-xs text-[var(--text-secondary)]">
                      {v.description}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 자동 보정 */}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            자동 보정
          </h3>
          <Button
            onClick={handleAutoCorrect}
            disabled={!hasViolations || correcting}
            className="w-full justify-center"
          >
            {correcting ? "보정 중..." : "자동 보정"}
          </Button>
        </div>

        {correction && (
          <div className="flex flex-col gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
              보정 결과 (변경 전 → 변경 후)
            </p>
            <CorrectionRow
              label="건폐율"
              before={correction.before.bcr}
              after={correction.after.bcr}
              unit="%"
            />
            <CorrectionRow
              label="용적률"
              before={correction.before.far}
              after={correction.after.far}
              unit="%"
            />
            <CorrectionRow
              label="높이"
              before={correction.before.height}
              after={correction.after.height}
              unit="m"
            />

            {correction.adjustments.length > 0 && (
              <ul className="mt-1 list-inside list-disc text-xs text-[var(--text-secondary)]">
                {correction.adjustments.map((a, i) => (
                  <li key={i}>{a.description}</li>
                ))}
              </ul>
            )}

            <Button
              onClick={handleApplyCorrection}
              className="mt-2 w-full justify-center"
            >
              보정안 적용
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Sub-components ── */

function ComplianceRow({
  label,
  planned,
  limit,
  compliant,
  unit,
}: {
  label: string;
  planned: number;
  limit: number;
  compliant: boolean;
  unit: string;
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="font-medium text-[var(--text-primary)]">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className={compliant ? "text-emerald-600" : "text-red-500"}>
          {compliant ? "\u2705" : "\u274C"}
        </span>
        <span className="text-[var(--text-secondary)]">
          {planned.toFixed(1)}{unit} / {limit.toFixed(1)}{unit}
        </span>
      </span>
    </div>
  );
}

function CorrectionRow({
  label,
  before,
  after,
  unit,
}: {
  label: string;
  before: number;
  after: number;
  unit: string;
}) {
  const changed = Math.abs(before - after) > 0.01;
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="font-medium text-[var(--text-primary)]">{label}</span>
      <span className="text-[var(--text-secondary)]">
        {before.toFixed(1)}{unit}
        {changed && (
          <>
            {" → "}
            <span className="font-bold text-emerald-600">
              {after.toFixed(1)}{unit}
            </span>
          </>
        )}
      </span>
    </div>
  );
}
