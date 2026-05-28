"use client";

import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useCadStore } from "@/store/use-cad-store";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { Button, Card, CardContent } from "@propai/ui";

/* ── Types ── */

interface BimGenerateResult {
  total_floor_area_sqm: number;
  total_volume_m3: number;
  floor_count: number;
  structural_elements: number;
  materials: Array<{
    name: string;
    quantity: number;
    unit: string;
  }>;
  ifc_url?: string;
}

/* ── Component ── */

type CadBimSidePanelProps = {
  projectId: string;
};

export function CadBimSidePanel({ projectId }: CadBimSidePanelProps) {
  const { locale } = useParams() as { locale: string };
  const router = useRouter();

  const rects = useCadStore((s) => s.rects);
  const polygons = useCadStore((s) => s.polygons);
  const points = useCadStore((s) => s.points);
  const cadScale = useCadStore((s) => s.scale);
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);
  const toDesignPayload = useCadStore((s) => s.toDesignPayload);

  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);

  const [result, setResult] = useState<BimGenerateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // BIM 물량 산출
  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = toDesignPayload();
      const data = await (async () => ({} as BimGenerateResult))();
      setResult(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "BIM 물량 산출에 실패했습니다.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [projectId, toDesignPayload, floorCount, buildingHeightM]);

  // 공사비 산출 페이지로 이동
  const handleNavigateConstruction = useCallback(() => {
    if (result) {
      // 프로젝트 컨텍스트에 설계 데이터 저장
      updateDesignData({
        totalGfaSqm: result.total_floor_area_sqm,
        floorCount: result.floor_count,
        buildingType: null,
        bcr: null,
        far: null,
      });
    }
    router.push(`/${locale}/projects/${projectId}/construction`);
  }, [result, updateDesignData, router, locale, projectId]);

  return (
    <Card className="border-[var(--line)] bg-[var(--surface)]">
      <CardContent className="flex flex-col gap-4 p-4">
        <h3 className="text-sm font-bold text-[var(--text-primary)]">
          BIM 물량 산출
        </h3>

        <Button
          onClick={handleGenerate}
          disabled={loading}
          className="w-full justify-center"
        >
          {loading ? "산출 중..." : "BIM 물량 산출"}
        </Button>

        {error && <p className="text-xs text-red-500">{error}</p>}

        {result && (
          <div className="flex flex-col gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            {/* 요약 수치 */}
            <div className="grid grid-cols-2 gap-2">
              <BimStat label="총 연면적" value={result.total_floor_area_sqm.toFixed(1)} unit="m\u00B2" />
              <BimStat label="총 체적" value={result.total_volume_m3.toFixed(1)} unit="m\u00B3" />
              <BimStat label="층수" value={String(result.floor_count)} unit="층" />
              <BimStat label="구조 요소 수" value={String(result.structural_elements)} unit="개" />
            </div>

            {/* 자재 목록 */}
            {result.materials.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
                  자재 목록
                </p>
                <div className="max-h-40 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-left text-[var(--text-hint)]">
                        <th className="pb-1 font-medium">자재</th>
                        <th className="pb-1 text-right font-medium">수량</th>
                        <th className="pb-1 text-right font-medium">단위</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.materials.map((mat, i) => (
                        <tr key={i} className="border-b border-[var(--line)]/50">
                          <td className="py-1 text-[var(--text-primary)]">{mat.name}</td>
                          <td className="py-1 text-right text-[var(--text-secondary)]">
                            {mat.quantity.toLocaleString()}
                          </td>
                          <td className="py-1 text-right text-[var(--text-hint)]">{mat.unit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 공사비 산출 이동 */}
            <Button
              onClick={handleNavigateConstruction}
              className="w-full justify-center"
            >
              공사비 산출으로 이동
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Sub-components ── */

function BimStat({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="flex flex-col rounded-lg bg-[var(--surface)] p-2">
      <span className="text-[10px] font-medium text-[var(--text-hint)]">{label}</span>
      <span className="text-sm font-bold text-[var(--text-primary)]">
        {value}
        <span className="ml-0.5 text-[10px] font-normal text-[var(--text-secondary)]">
          {unit}
        </span>
      </span>
    </div>
  );
}
