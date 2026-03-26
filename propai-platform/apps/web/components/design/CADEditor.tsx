"use client";

import React, { useState, useCallback, useRef, useEffect } from "react";
import { Stage, Layer, Circle, Line, Text, Group } from "react-konva";
import Konva from "konva";

/* ───────────── 타입 정의 ───────────── */
interface DesignPoint {
  id: string;
  x: number;
  y: number;
}

interface DesignLine {
  id: string;
  start_point_id: string;
  end_point_id: string;
}

interface DesignSurface {
  id: string;
  point_ids: string[];
}

interface ComplianceViolation {
  type: string;
  message: string;
  severity: "error" | "warning";
  current_value: number;
  limit_value: number;
}

interface CorrectionAlternative {
  alternative_id: string;
  description: string;
  corrected_design: Record<string, unknown>;
  estimated_cost_change_krw: number;
  far_after: number;
  bcr_after: number;
}

interface CADEditorProps {
  projectId: string;
  apiBaseUrl?: string;
  width?: number;
  height?: number;
  gridSize?: number;
  snapGrid?: boolean;
}

/* ───────────── 상수 ───────────── */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEBOUNCE_MS = Number(
  process.env.NEXT_PUBLIC_COMPLIANCE_DEBOUNCE_MS ?? "500"
);
const GRID_STEP = 20; // px

/* ───────────── 컴포넌트 ───────────── */
export default function CADEditor({
  projectId,
  apiBaseUrl = API_BASE,
  width = 800,
  height = 600,
  gridSize = GRID_STEP,
  snapGrid = true,
}: CADEditorProps) {
  /* ── 상태 ── */
  const [points, setPoints] = useState<DesignPoint[]>([
    { id: "p1", x: 100, y: 100 },
    { id: "p2", x: 400, y: 100 },
    { id: "p3", x: 400, y: 350 },
    { id: "p4", x: 100, y: 350 },
  ]);
  const [lines] = useState<DesignLine[]>([
    { id: "l1", start_point_id: "p1", end_point_id: "p2" },
    { id: "l2", start_point_id: "p2", end_point_id: "p3" },
    { id: "l3", start_point_id: "p3", end_point_id: "p4" },
    { id: "l4", start_point_id: "p4", end_point_id: "p1" },
  ]);
  const [surfaces] = useState<DesignSurface[]>([
    { id: "s1", point_ids: ["p1", "p2", "p3", "p4"] },
  ]);
  const [violations, setViolations] = useState<ComplianceViolation[]>([]);
  const [alternatives, setAlternatives] = useState<CorrectionAlternative[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const [floorCount, setFloorCount] = useState(5);
  const [buildingHeight, setBuildingHeight] = useState(15);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── 스냅 ── */
  const snap = useCallback(
    (v: number) => (snapGrid ? Math.round(v / gridSize) * gridSize : v),
    [snapGrid, gridSize]
  );

  /* ── 법규 검증 API 호출 ── */
  const checkCompliance = useCallback(
    async (pts: DesignPoint[]) => {
      setIsChecking(true);
      try {
        const body = {
          project_id: projectId,
          design: {
            points: pts.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
            scale: 10.0,
          },
        };
        console.log(
          "[CADEditor] POST /api/v1/building-compliance/check",
          JSON.stringify(body)
        );
        const res = await fetch(
          `${apiBaseUrl}/api/v1/building-compliance/check`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        const data = await res.json();
        console.log("[CADEditor] 법규 검증 결과:", JSON.stringify(data));
        setViolations(data.violations ?? []);
        if (data.violations?.length) {
          console.warn(
            `[CADEditor] 법규 위반 ${data.violations.length}건 감지!`
          );
        }
      } catch (err) {
        console.error("[CADEditor] 법규 검증 API 오류:", err);
      } finally {
        setIsChecking(false);
      }
    },
    [projectId, apiBaseUrl, lines, surfaces, floorCount, buildingHeight]
  );

  /* ── 자동 보정 API 호출 ── */
  const requestAutoCorrect = useCallback(
    async (violationType: string) => {
      try {
        const body = {
          project_id: projectId,
          design: {
            points: points.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
            scale: 10.0,
          },
          violation_type: violationType,
        };
        console.log(
          "[CADEditor] POST /api/v1/building-compliance/auto-correct",
          JSON.stringify(body)
        );
        const res = await fetch(
          `${apiBaseUrl}/api/v1/building-compliance/auto-correct`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        const data = await res.json();
        console.log("[CADEditor] 자동 보정 결과:", JSON.stringify(data));
        setAlternatives(data.alternatives ?? []);
      } catch (err) {
        console.error("[CADEditor] 자동 보정 API 오류:", err);
      }
    },
    [projectId, apiBaseUrl, points, lines, surfaces, floorCount, buildingHeight]
  );

  /* ── 디바운스 검증 ── */
  const debouncedCheck = useCallback(
    (pts: DesignPoint[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => checkCompliance(pts), DEBOUNCE_MS);
    },
    [checkCompliance]
  );

  /* ── 초기 검증 ── */
  useEffect(() => {
    checkCompliance(points);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── 포인트 드래그 핸들러 ── */
  const handleDragEnd = useCallback(
    (idx: number, e: Konva.KonvaEventObject<DragEvent>) => {
      const newX = snap(e.target.x());
      const newY = snap(e.target.y());
      setPoints((prev) => {
        const next = [...prev];
        next[idx] = { ...next[idx], x: newX, y: newY };
        console.log(
          `[CADEditor] 점 ${next[idx].id} 이동 → (${newX}, ${newY})`
        );
        debouncedCheck(next);
        return next;
      });
    },
    [snap, debouncedCheck]
  );

  /* ── 그리드 렌더링 ── */
  const gridLines: React.ReactElement[] = [];
  for (let i = 0; i <= width; i += gridSize) {
    gridLines.push(
      <Line
        key={`gv-${i}`}
        points={[i, 0, i, height]}
        stroke="#e5e7eb"
        strokeWidth={0.5}
      />
    );
  }
  for (let j = 0; j <= height; j += gridSize) {
    gridLines.push(
      <Line
        key={`gh-${j}`}
        points={[0, j, width, j]}
        stroke="#e5e7eb"
        strokeWidth={0.5}
      />
    );
  }

  /* ── 포인트 맵 ── */
  const pointMap = Object.fromEntries(points.map((p) => [p.id, p]));

  /* ── 면 좌표 ── */
  const surfaceCoords = surfaces.flatMap((s) =>
    s.point_ids
      .filter((pid) => pointMap[pid])
      .flatMap((pid) => [pointMap[pid].x, pointMap[pid].y])
  );

  /* ── 선 좌표 ── */
  const lineElements = lines.map((l) => {
    const sp = pointMap[l.start_point_id];
    const ep = pointMap[l.end_point_id];
    if (!sp || !ep) return null;
    return (
      <Line
        key={l.id}
        points={[sp.x, sp.y, ep.x, ep.y]}
        stroke="#1e40af"
        strokeWidth={2}
      />
    );
  });

  return (
    <div style={{ display: "flex", gap: 16 }}>
      {/* ── 캔버스 ── */}
      <div
        style={{
          border: "2px solid #3b82f6",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <Stage width={width} height={height}>
          <Layer>
            {/* 그리드 */}
            {gridLines}

            {/* 면 (반투명 채움) */}
            {surfaceCoords.length >= 6 && (
              <Line
                points={surfaceCoords}
                closed
                fill="rgba(59,130,246,0.12)"
                stroke="#3b82f6"
                strokeWidth={1}
              />
            )}

            {/* 선 */}
            {lineElements}

            {/* 점 (드래그 가능) */}
            {points.map((p, idx) => (
              <Group key={p.id}>
                <Circle
                  x={p.x}
                  y={p.y}
                  radius={8}
                  fill="#2563eb"
                  stroke="#1e3a8a"
                  strokeWidth={2}
                  draggable
                  onDragEnd={(e) => handleDragEnd(idx, e)}
                  style={{ cursor: "grab" }}
                />
                <Text
                  x={p.x + 10}
                  y={p.y - 6}
                  text={p.id}
                  fontSize={11}
                  fill="#64748b"
                />
              </Group>
            ))}
          </Layer>
        </Stage>
      </div>

      {/* ── 사이드 패널 ── */}
      <div style={{ width: 320, fontFamily: "sans-serif", fontSize: 13 }}>
        <h3 style={{ marginBottom: 8 }}>
          건축 법규 검증 패널{" "}
          {isChecking && <span style={{ color: "#f59e0b" }}>검증 중...</span>}
        </h3>

        {/* 층수 / 높이 컨트롤 */}
        <div style={{ marginBottom: 12 }}>
          <label>
            층수:{" "}
            <input
              type="number"
              value={floorCount}
              min={1}
              max={50}
              onChange={(e) => {
                const v = Number(e.target.value);
                setFloorCount(v);
                debouncedCheck(points);
              }}
              style={{ width: 60 }}
            />
          </label>
          <label style={{ marginLeft: 12 }}>
            높이(m):{" "}
            <input
              type="number"
              value={buildingHeight}
              min={0}
              max={200}
              onChange={(e) => {
                const v = Number(e.target.value);
                setBuildingHeight(v);
                debouncedCheck(points);
              }}
              style={{ width: 60 }}
            />
          </label>
        </div>

        {/* 위반 목록 */}
        {violations.length === 0 ? (
          <div
            style={{
              padding: 12,
              background: "#ecfdf5",
              borderRadius: 6,
              color: "#065f46",
            }}
          >
            법규 준수 상태 (위반 없음)
          </div>
        ) : (
          <div>
            {violations.map((v, i) => (
              <div
                key={i}
                style={{
                  padding: 10,
                  marginBottom: 6,
                  background:
                    v.severity === "error" ? "#fef2f2" : "#fffbeb",
                  border: `1px solid ${
                    v.severity === "error" ? "#fca5a5" : "#fcd34d"
                  }`,
                  borderRadius: 6,
                }}
              >
                <strong style={{ color: v.severity === "error" ? "#dc2626" : "#d97706" }}>
                  [{v.severity === "error" ? "위반" : "경고"}] {v.type}
                </strong>
                <p style={{ margin: "4px 0 0" }}>{v.message}</p>
                {v.severity === "error" && (
                  <button
                    onClick={() => requestAutoCorrect(v.type)}
                    style={{
                      marginTop: 6,
                      padding: "4px 10px",
                      background: "#2563eb",
                      color: "#fff",
                      border: "none",
                      borderRadius: 4,
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    자동 보정 요청
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 보정 대안 */}
        {alternatives.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <h4>보정 대안</h4>
            {alternatives.map((alt) => (
              <div
                key={alt.alternative_id}
                style={{
                  padding: 10,
                  marginBottom: 6,
                  background: "#eff6ff",
                  border: "1px solid #93c5fd",
                  borderRadius: 6,
                }}
              >
                <strong>대안 {alt.alternative_id}</strong>
                <p style={{ margin: "4px 0" }}>{alt.description}</p>
                <p style={{ margin: 0, fontSize: 11, color: "#6b7280" }}>
                  예상 공사비 변동: {alt.estimated_cost_change_krw.toLocaleString()}원
                  | BCR: {(alt.bcr_after * 100).toFixed(1)}% | FAR:{" "}
                  {(alt.far_after * 100).toFixed(1)}%
                </p>
                <button
                  onClick={() => {
                    const cd = alt.corrected_design as Record<string, unknown>;
                    if (Array.isArray(cd.points)) {
                      setPoints(
                        (cd.points as { id: string; x: number; y: number }[]).map(
                          (p) => ({ id: p.id, x: p.x, y: p.y })
                        )
                      );
                      console.log("[CADEditor] 보정 대안 적용:", alt.alternative_id);
                      checkCompliance(
                        (cd.points as { id: string; x: number; y: number }[]).map(
                          (p) => ({ id: p.id, x: p.x, y: p.y })
                        )
                      );
                    }
                    if (cd.building_height_m !== undefined) {
                      setBuildingHeight(cd.building_height_m as number);
                    }
                    setAlternatives([]);
                  }}
                  style={{
                    marginTop: 6,
                    padding: "4px 10px",
                    background: "#16a34a",
                    color: "#fff",
                    border: "none",
                    borderRadius: 4,
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                >
                  이 대안 적용
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
