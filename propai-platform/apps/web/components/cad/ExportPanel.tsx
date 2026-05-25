"use client";

import { useCallback, useState } from "react";
import { useCadStore } from "@/store/use-cad-store";

type ExportPanelProps = {
  projectId: string;
};

const DXF_TYPES = [
  { id: "floor_plan", label: "DXF 평면도" },
  { id: "detailed", label: "DXF 상세 평면도" },
  { id: "section", label: "DXF 단면도" },
  { id: "elevation_front", label: "DXF 정면 입면도" },
  { id: "elevation_side", label: "DXF 측면 입면도" },
  { id: "site_plan", label: "DXF 배치도" },
] as const;

export function ExportPanel({ projectId }: ExportPanelProps) {
  const points = useCadStore((s) => s.points);
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);
  const hasElements = points.length > 0;

  const [downloading, setDownloading] = useState<string | null>(null);

  const handleExportDxf = useCallback(
    async (drawingType: string) => {
      setDownloading(drawingType);
      try {
        const res = await fetch("/api/v1/drawing/export-dxf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            building_width_m: 30,
            building_depth_m: 15,
            floor_count: floorCount,
            floor_height_m: buildingHeightM / Math.max(floorCount, 1),
            unit_width_m: 8.0,
            corridor_width_m: 1.8,
            basement_floors: 1,
            site_width_m: 60,
            site_depth_m: 40,
            setback_m: 3.0,
            parking_count: 50,
            drawing_type: drawingType,
          }),
        });
        if (!res.ok) throw new Error("DXF 내보내기 실패");
        const blob = await res.blob();
        triggerDownload(blob, `${drawingType}.dxf`);
      } catch {
        // silent
      } finally {
        setDownloading(null);
      }
    },
    [floorCount, buildingHeightM],
  );

  const handleExportSvgSite = useCallback(async () => {
    setDownloading("svg-site");
    try {
      const res = await fetch("/api/v1/drawing/site-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          site_width_m: 40,
          site_depth_m: 30,
          building_width_m: 30,
          building_depth_m: 15,
          setback_m: 3.0,
        }),
      });
      if (!res.ok) throw new Error("SVG 내보내기 실패");
      const text = await res.text();
      const blob = new Blob([text], { type: "image/svg+xml" });
      triggerDownload(blob, "site_plan.svg");
    } catch {
      // silent
    } finally {
      setDownloading(null);
    }
  }, []);

  const handleExportSvgFloor = useCallback(async () => {
    setDownloading("svg-floor");
    try {
      const res = await fetch("/api/v1/drawing/floor-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          total_floor_area_sqm: 500,
          unit_type: "84A",
          core_count: 2,
          parking_count: 50,
        }),
      });
      if (!res.ok) throw new Error("SVG 내보내기 실패");
      const text = await res.text();
      const blob = new Blob([text], { type: "image/svg+xml" });
      triggerDownload(blob, "floor_plan.svg");
    } catch {
      // silent
    } finally {
      setDownloading(null);
    }
  }, []);

  const handleExportFullSet = useCallback(async () => {
    setDownloading("full-set");
    try {
      const res = await fetch(
        `/api/v1/design/${projectId}/generate-full-set`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            site_width_m: 60,
            site_depth_m: 40,
            building_width_m: 30,
            building_depth_m: 15,
            floor_count: floorCount,
            floor_height_m: 3.0,
            basement_floors: 1,
            unit_width_m: 8.0,
            setback_m: 3.0,
            parking_count: 50,
          }),
        },
      );
      if (!res.ok) throw new Error("전체 도면 세트 생성 실패");
      const data = await res.json();
      // JSON 결과를 다운로드 (도면 목록)
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      triggerDownload(blob, "full_drawing_set.json");
    } catch {
      // silent
    } finally {
      setDownloading(null);
    }
  }, [projectId, floorCount]);

  if (!hasElements) return null;

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
        도면 내보내기
      </h3>

      {/* DXF 도면 유형별 내보내기 */}
      <div className="grid gap-1.5">
        <p className="text-xs text-[var(--text-hint)] mt-1">CAD (DXF)</p>
        {DXF_TYPES.map((t) => (
          <ExportButton
            key={t.id}
            label={t.label}
            loading={downloading === t.id}
            onClick={() => handleExportDxf(t.id)}
          />
        ))}
      </div>

      {/* SVG 내보내기 */}
      <div className="grid gap-1.5 mt-2">
        <p className="text-xs text-[var(--text-hint)]">SVG</p>
        <ExportButton
          label="SVG 배치도"
          loading={downloading === "svg-site"}
          onClick={handleExportSvgSite}
        />
        <ExportButton
          label="SVG 평면도"
          loading={downloading === "svg-floor"}
          onClick={handleExportSvgFloor}
        />
      </div>

      {/* 전체 도면 세트 */}
      <div className="grid gap-1.5 mt-2">
        <p className="text-xs text-[var(--text-hint)]">전체 세트</p>
        <ExportButton
          label="전체 도면 세트 생성 (B-01~C-03)"
          loading={downloading === "full-set"}
          onClick={handleExportFullSet}
        />
      </div>
    </div>
  );
}

function ExportButton({
  label,
  loading,
  onClick,
}: {
  label: string;
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-opacity hover:bg-[var(--surface-muted)] disabled:opacity-50"
    >
      {loading ? "다운로드 중..." : label}
    </button>
  );
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
