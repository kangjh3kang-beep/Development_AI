"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useCadStore } from "@/store/use-cad-store";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { Button, Card, CardContent } from "@propai/ui";

/* ── Types ── */

interface DrawingSetResult {
  drawings: Array<{
    type: string;
    label: string;
    svg: string;
  }>;
}

const DRAWING_TYPES = [
  { id: "site_plan", label: "배치도" },
  { id: "floor_plan", label: "평면도" },
  { id: "section", label: "단면도" },
  { id: "elevation", label: "입면도" },
  { id: "parking_plan", label: "주차장 배치도" },
] as const;

/* ── Component ── */

type CadExportPanelProps = {
  projectId: string;
};

/** 연면적·층수에서 실제 건물 치수를 역산(CadBimIntegrationPanel과 동일 규칙으로 CAD↔BIM 일치). */
function deriveDims(gfa: number | null | undefined, floors: number | null | undefined, landArea: number | null | undefined) {
  const r2 = (n: number) => Math.round(n * 100) / 100;
  if (gfa && floors && floors > 0) {
    const footprint = gfa / floors;                       // 1개 층 바닥면적
    const depth = Math.max(8, Math.min(40, Math.sqrt(footprint / 1.6)));
    const width = Math.max(8, footprint / depth);
    // 대지(부지) 치수: 대지면적이 있으면 정사각형 근사, 없으면 건물+여유(세트백)로 추정
    const siteSide = landArea && landArea > 0 ? Math.sqrt(landArea) : 0;
    return {
      building_width_m: r2(width),
      building_depth_m: r2(depth),
      site_width_m: r2(siteSide > 0 ? siteSide : width + 12),
      site_depth_m: r2(siteSide > 0 ? siteSide : depth + 12),
      hasReal: true,
    };
  }
  return null;
}

export function CadExportPanel({ projectId }: CadExportPanelProps) {
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);

  // 컨텍스트(SSOT)의 선택한 건축개요에서 실치수를 역산 — 하드코딩 30×15m 제거
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const dims = useMemo(
    () => deriveDims(designData?.totalGfaSqm, designData?.floorCount, siteAnalysis?.landAreaSqm),
    [designData?.totalGfaSqm, designData?.floorCount, siteAnalysis?.landAreaSqm],
  );

  const [selected, setSelected] = useState<Set<string>>(
    new Set(DRAWING_TYPES.map((d) => d.id)),
  );
  const [drawings, setDrawings] = useState<DrawingSetResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [exportingDxf, setExportingDxf] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleType = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // 도면 세트 생성
  const handleGenerateSet = useCallback(async () => {
    if (selected.size === 0) return;
    setGenerating(true);
    setError(null);
    try {
      const result = await apiClient.post<DrawingSetResult>(
        `/design/${projectId}/generate-full-set`,
        {
          body: {
            drawing_types: Array.from(selected),
            // 설계개요가 있으면 역산 실치수, 없으면 표준 매스(폴백)로 생성
            floor_count: designData?.floorCount ?? floorCount,
            floor_height_m: buildingHeightM / Math.max(designData?.floorCount ?? floorCount, 1),
            building_width_m: dims?.building_width_m ?? 30,
            building_depth_m: dims?.building_depth_m ?? 15,
            site_width_m: dims?.site_width_m ?? 60,
            site_depth_m: dims?.site_depth_m ?? 40,
            setback_m: 3.0,
            basement_floors: 1,
            unit_width_m: 8.0,
            parking_count: 50,
          },
        },
      );
      setDrawings(result);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "도면 세트 생성에 실패했습니다.";
      setError(message);
    } finally {
      setGenerating(false);
    }
  }, [projectId, selected, floorCount, buildingHeightM, designData?.floorCount, dims]);

  // DXF 내보내기
  const handleExportDxf = useCallback(async () => {
    setExportingDxf(true);
    setError(null);
    try {
      const result = await apiClient.post<{ message: string }>(
        "/drawing/export-dxf",
        {
          body: {
            building_width_m: dims?.building_width_m ?? 30,
            building_depth_m: dims?.building_depth_m ?? 15,
            floor_count: designData?.floorCount ?? floorCount,
            floor_height_m: buildingHeightM / Math.max(designData?.floorCount ?? floorCount, 1),
            unit_width_m: 8.0,
            corridor_width_m: 1.8,
            basement_floors: 1,
            site_width_m: dims?.site_width_m ?? 60,
            site_depth_m: dims?.site_depth_m ?? 40,
            setback_m: 3.0,
            parking_count: 50,
            drawing_type: "floor_plan",
          },
        },
      );
      const text = typeof result === "string" ? result : (result as { message: string }).message ?? "";
      const blob = new Blob([text], { type: "application/dxf" });
      triggerDownload(blob, `${projectId}_drawings.dxf`);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "DXF 내보내기에 실패했습니다.";
      setError(message);
    } finally {
      setExportingDxf(false);
    }
  }, [projectId, floorCount, buildingHeightM, designData?.floorCount, dims]);

  // PDF 내보내기 (SVG들을 모아서)
  const handleExportPdf = useCallback(async () => {
    if (!drawings || drawings.drawings?.length === 0) return;
    setExportingPdf(true);
    setError(null);
    try {
      // SVG 결합하여 간이 HTML→print 방식 PDF 생성
      const svgContent = drawings.drawings
        .map(
          (d) =>
            `<div style="page-break-after:always;padding:20px;"><h2 style="font-family:sans-serif;margin-bottom:10px;">${d.label}</h2>${d.svg}</div>`,
        )
        .join("");

      const html = `<!DOCTYPE html><html><head><title>도면 세트</title></head><body>${svgContent}</body></html>`;
      const blob = new Blob([html], { type: "text/html" });

      // 새 창에서 인쇄 → PDF
      const url = URL.createObjectURL(blob);
      const win = window.open(url, "_blank");
      if (win) {
        win.onload = () => {
          win.print();
        };
      }
      URL.revokeObjectURL(url);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "PDF 내보내기에 실패했습니다.";
      setError(message);
    } finally {
      setExportingPdf(false);
    }
  }, [drawings]);

  return (
    <Card className="border-[var(--line)] bg-[var(--surface)]">
      <CardContent className="flex flex-col gap-4 p-4">
        {/* 도면 세트 생성 */}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            도면 세트 생성
          </h3>

          {/* 실치수 안내 — 하드코딩 대신 선택한 건축개요에서 역산한 값을 정직 표기 */}
          {dims ? (
            <p className="text-[10px] text-[var(--text-hint)]">
              적용 치수: 건물 {dims.building_width_m}×{dims.building_depth_m}m · 대지 {dims.site_width_m}×{dims.site_depth_m}m
              {designData?.floorCount ? ` · ${designData.floorCount}층` : ""}
            </p>
          ) : (
            <p className="text-[10px] text-[var(--spot)]">
              ※ 건축개요(연면적·층수)가 없어 표준 매스로 생성합니다. 설계를 먼저 생성하면 실치수가 반영됩니다.
            </p>
          )}

          <div className="flex flex-col gap-1.5">
            {DRAWING_TYPES.map((dt) => (
              <label
                key={dt.id}
                className="flex items-center gap-2 text-xs text-[var(--text-primary)] cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.has(dt.id)}
                  onChange={() => toggleType(dt.id)}
                  className="accent-[var(--accent)]"
                />
                {dt.label}
              </label>
            ))}
          </div>

          <Button
            onClick={handleGenerateSet}
            disabled={generating || selected.size === 0}
            className="w-full justify-center"
          >
            {generating ? "생성 중..." : "도면 세트 생성"}
          </Button>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        {/* 생성된 도면 미리보기 */}
        {drawings && drawings.drawings?.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
              생성된 도면
            </p>
            <div className="grid grid-cols-2 gap-2">
              {(drawings.drawings ?? []).map((d, i) => (
                <SafeSvgPreview key={i} label={d.label} svg={d.svg} />
              ))}
            </div>
          </div>
        )}

        {/* 내보내기 */}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            내보내기
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <Button
              onClick={handleExportDxf}
              disabled={exportingDxf}
              className="justify-center"
            >
              {exportingDxf ? "변환 중..." : "DXF 다운로드"}
            </Button>
            <Button
              onClick={handleExportPdf}
              disabled={exportingPdf || !drawings}
              className="justify-center"
            >
              {exportingPdf ? "변환 중..." : "PDF 다운로드"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── SafeSvgPreview: XSS 방지를 위해 object URL 방식으로 SVG 렌더링 ── */

function SafeSvgPreview({ label, svg }: { label: string; svg: string }) {
  const objectUrl = useMemo(
    () => URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" })),
    [svg],
  );

  useEffect(() => {
    return () => URL.revokeObjectURL(objectUrl);
  }, [objectUrl]);

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-2">
      <span className="text-[10px] font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      <div className="aspect-square w-full overflow-hidden rounded bg-white">
        <img
          src={objectUrl}
          alt={label}
          className="h-full w-full object-contain"
        />
      </div>
    </div>
  );
}

/* ── Helpers ── */

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
