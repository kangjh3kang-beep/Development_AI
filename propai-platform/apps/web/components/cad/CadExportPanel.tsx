"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useCadStore } from "@/store/use-cad-store";
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

export function CadExportPanel({ projectId }: CadExportPanelProps) {
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);
  const toDesignPayload = useCadStore((s) => s.toDesignPayload);

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
            floor_count: floorCount,
            floor_height_m: buildingHeightM / Math.max(floorCount, 1),
            building_width_m: 30,
            building_depth_m: 15,
            site_width_m: 60,
            site_depth_m: 40,
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
  }, [projectId, selected, floorCount, buildingHeightM]);

  // DXF 내보내기
  const handleExportDxf = useCallback(async () => {
    setExportingDxf(true);
    setError(null);
    try {
      const result = await apiClient.post<{ message: string }>(
        "/drawing/export-dxf",
        {
          body: {
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
  }, [projectId, floorCount, buildingHeightM]);

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
