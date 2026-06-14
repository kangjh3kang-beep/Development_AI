"use client";

/**
 * SP4-3 DXF 경량 CAD 뷰어(읽기전용) — 회의방 자료교환의 설계도면(DXF)을 플랫폼 내부에서 본다.
 *
 * 백엔드(/documents/{id}/shapes)가 parse_dxf_to_shapes로 파싱한 CAD2.0 셰이프(@/lib/cad-shapes 모델)를
 * read-only SVG로 렌더한다(편집 없음). CADEditor와 동일 데이터모델·레이어 색을 공유한다.
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { sanitizeShapes, type CadShape, type LayerKey } from "@/lib/cad-shapes";

const LAYER_STROKE: Record<LayerKey, string> = {
  outline: "#2dd4bf",
  wall: "#60a5fa",
  dim: "#f59e0b",
  note: "#a78bfa",
};
const LAYER_FILL: Record<LayerKey, string> = {
  outline: "rgba(45,212,191,0.10)",
  wall: "rgba(96,165,250,0.08)",
  dim: "none",
  note: "none",
};

function ptsAttr(points: CadShape["points"]): string {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

function Shape({ s }: { s: CadShape }) {
  const stroke = LAYER_STROKE[s.layer] ?? "#94a3b8";
  const fill = LAYER_FILL[s.layer] ?? "none";
  const common = { stroke, strokeWidth: 1.5, vectorEffect: "non-scaling-stroke" as const };
  if (s.kind === "circle") {
    const c = s.points[0];
    if (!c) return null;
    return <circle cx={c.x} cy={c.y} r={s.radius ?? 4} fill={fill} {...common} />;
  }
  if (s.kind === "label") {
    const c = s.points[0];
    if (!c) return null;
    return (
      <text x={c.x} y={c.y} fill={stroke} fontSize={12} vectorEffect="non-scaling-stroke">
        {s.text ?? ""}
      </text>
    );
  }
  if (s.kind === "line") {
    return <polyline points={ptsAttr(s.points)} fill="none" {...common} />;
  }
  if (s.kind === "rect" && s.points.length === 2) {
    const [a, b] = s.points;
    return (
      <rect
        x={Math.min(a.x, b.x)}
        y={Math.min(a.y, b.y)}
        width={Math.abs(b.x - a.x)}
        height={Math.abs(b.y - a.y)}
        fill={fill}
        {...common}
      />
    );
  }
  // polygon (또는 ≥3코너 rect)
  return <polygon points={ptsAttr(s.points)} fill={fill} {...common} />;
}

export function CadDocViewer({ projectId, docId }: { projectId: string; docId: string }) {
  const [shapes, setShapes] = useState<CadShape[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setShapes(null);
    setError(null);
    apiClient
      .getV2<{ shapes?: unknown }>(`/collaboration/projects/${projectId}/documents/${docId}/shapes`)
      .then((r) => {
        if (alive) setShapes(sanitizeShapes(r?.shapes));
      })
      .catch(() => {
        if (alive) setError("도면을 불러오지 못했습니다");
      });
    return () => {
      alive = false;
    };
  }, [projectId, docId]);

  if (error) {
    return <p className="py-8 text-center text-sm text-[var(--text-hint)]">{error} — 상단 “새 탭”으로 받아주세요.</p>;
  }
  if (!shapes) {
    return <p className="py-8 text-center text-xs text-[var(--text-hint)]">도면 불러오는 중…</p>;
  }
  if (!shapes.length) {
    return <p className="py-8 text-center text-xs text-[var(--text-hint)]">표시할 도형이 없습니다(빈 도면).</p>;
  }

  const xs = shapes.flatMap((s) => s.points.map((p) => p.x));
  const ys = shapes.flatMap((s) => s.points.map((p) => p.y));
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const w = Math.max(...xs) - minX || 1;
  const h = Math.max(...ys) - minY || 1;
  const pad = Math.max(w, h) * 0.05 + 8;

  return (
    <div className="w-full">
      <svg
        viewBox={`${minX - pad} ${minY - pad} ${w + pad * 2} ${h + pad * 2}`}
        className="max-h-[74vh] w-full rounded-lg border border-[var(--line)] bg-[var(--surface-soft)]"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="DXF 설계도면 미리보기"
      >
        {shapes.map((s) => (
          <Shape key={s.id} s={s} />
        ))}
      </svg>
      <p className="mt-2 text-center text-[10px] text-[var(--text-hint)]">
        DXF 경량 뷰어(읽기전용) · 편집은 AI 설계도면(CAD)에서
      </p>
    </div>
  );
}
