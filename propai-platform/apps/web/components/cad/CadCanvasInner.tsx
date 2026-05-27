"use client";

import React, { useCallback, useMemo, useRef, useState, useEffect } from "react";
import type Konva from "konva";
import { useCadStore } from "@/store/use-cad-store";
import type { CadPoint, CadLine, CadPolygon, CadRect, CadCircle, CadText } from "@/components/cad/types";

/** react-konva 동적 로드 모듈 타입. */
type ReactKonvaModules = {
  Stage: React.ComponentType<Record<string, unknown>>;
  Layer: React.ComponentType<Record<string, unknown>>;
  Group: React.ComponentType<Record<string, unknown>>;
  Line: React.ComponentType<Record<string, unknown>>;
  Circle: React.ComponentType<Record<string, unknown>>;
  Rect: React.ComponentType<Record<string, unknown>>;
  Text: React.ComponentType<Record<string, unknown>>;
  Transformer: React.ComponentType<Record<string, unknown>>;
};

type GridLine = { points: number[]; vertical: boolean; label: string };
type LineDimension = { id: string; mx: number; my: number; lenM: number; offset: number };

// react-konva 19.2.4 officially supports React 19 — no shim needed.

type CadCanvasInnerProps = {
  width: number;
  height: number;
};

const POINT_RADIUS = 6;
const POINT_SELECTED_RADIUS = 9;
const LINE_STROKE = 2;
const GRID_COLOR = "rgba(19,33,47,0.06)";
const GRID_LABEL_COLOR = "rgba(19,33,47,0.28)";
const POINT_COLOR = "#0e7490";
const POINT_SELECTED_COLOR = "#d97706";
const LINE_COLOR = "#13212f";
const PENDING_LINE_COLOR = "rgba(217,119,6,0.6)";
const RECT_FILL = "rgba(14,116,144,0.08)";
const CIRCLE_FILL = "rgba(99,102,241,0.08)";
const TEXT_COLOR = "#2d3436";
const DIMS_COLOR = "#d63031";

const SCALE_BY = 1.08;
const MIN_SCALE = 0.1;
const MAX_SCALE = 10;

export function CadCanvasInner({ width, height }: CadCanvasInnerProps) {
  const [mounted, setMounted] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [rk, setRK] = useState<ReactKonvaModules | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const modules = require("react-konva") as ReactKonvaModules;
      setRK(modules);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "react-konva 로드 실패";
      console.error("[CadCanvasInner]", msg);
      setLoadError(msg);
    }
    setMounted(true);
    setIsReady(true);
  }, []);

  const stageRef = useRef<Konva.Stage>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const shapeRefs = useRef<Map<string, Konva.Node>>(new Map());

  const points = useCadStore((s) => s.points);
  const lines = useCadStore((s) => s.lines);
  const polygons = useCadStore((s) => s.polygons);
  const rects = useCadStore((s) => s.rects);
  const circles = useCadStore((s) => s.circles);
  const texts = useCadStore((s) => s.texts);
  const selectedId = useCadStore((s) => s.selectedId);
  const selectedIds = useCadStore((s) => s.selectedIds);
  const tool = useCadStore((s) => s.tool);
  const gridSize = useCadStore((s) => s.gridSize);
  const cadScale = useCadStore((s) => s.scale);
  const pendingPointIds = useCadStore((s) => s.pendingPointIds);
  const pendingOrigin = useCadStore((s) => s.pendingOrigin);
  const analysisMarkers = useCadStore((s) => s.analysisMarkers);
  const handleCanvasClick = useCadStore((s) => s.handleCanvasClick);
  const movePoint = useCadStore((s) => s.movePoint);
  const setSelected = useCadStore((s) => s.setSelected);
  const toggleSelected = useCadStore((s) => s.toggleSelected);
  const clearSelection = useCadStore((s) => s.clearSelection);
  const setCursorPos = useCadStore((s) => s.setCursorPos);
  const setViewScale = useCadStore((s) => s.setViewScale);

  const pointMap = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const p of points) {
      map.set(p.id, { x: p.x, y: p.y });
    }
    return map;
  }, [points]);

  const gridLines = useMemo(() => {
    const result: Array<{ points: number[]; vertical: boolean; label: string }> = [];
    for (let x = 0; x <= width * 2; x += gridSize) {
      result.push({
        points: [x, -height, x, height * 2],
        vertical: true,
        label: `${x}`,
      });
    }
    for (let y = -height; y <= height * 2; y += gridSize) {
      result.push({
        points: [-width, y, width * 2, y],
        vertical: false,
        label: `${y}`,
      });
    }
    return result;
  }, [width, height, gridSize]);

  // Transformer 노드 동기화
  useEffect(() => {
    const tr = transformerRef.current;
    if (!tr) return;
    const nodes: Konva.Node[] = [];
    for (const id of selectedIds) {
      const node = shapeRefs.current.get(id);
      if (node) nodes.push(node);
    }
    tr.nodes(nodes);
    tr.getLayer()?.batchDraw();
  }, [selectedIds, rects, circles, texts, points, polygons]);

  // shape ref 등록 헬퍼
  const registerRef = useCallback((id: string, node: Konva.Node | null) => {
    if (node) {
      shapeRefs.current.set(id, node);
    } else {
      shapeRefs.current.delete(id);
    }
  }, []);

  // 선택된 ID 세트 (렌더링 성능)
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  // 줌/팬: 마우스 휠
  const onWheel = useCallback(
    (e: Konva.KonvaEventObject<WheelEvent>) => {
      e.evt.preventDefault();
      const stage = stageRef.current;
      if (!stage) return;
      const oldScale = stage.scaleX();
      const pointer = stage.getPointerPosition();
      if (!pointer) return;
      const newScale = e.evt.deltaY < 0 ? oldScale * SCALE_BY : oldScale / SCALE_BY;
      const clampedScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
      stage.scale({ x: clampedScale, y: clampedScale });
      const newPos = {
        x: pointer.x - (pointer.x - stage.x()) * (clampedScale / oldScale),
        y: pointer.y - (pointer.y - stage.y()) * (clampedScale / oldScale),
      };
      stage.position(newPos);
      setViewScale(clampedScale);
    },
    [setViewScale],
  );

  // 스테이지에서 실제 좌표 계산 (줌/팬 역변환)
  const getScenePos = useCallback((stage: Konva.Stage): { x: number; y: number } | null => {
    const pointer = stage.getPointerPosition();
    if (!pointer) return null;
    const scale = stage.scaleX();
    return {
      x: (pointer.x - stage.x()) / scale,
      y: (pointer.y - stage.y()) / scale,
    };
  }, []);

  const onStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      // select 모드에서 빈 영역 클릭 → 선택 해제
      if (tool === "select") {
        const clickedOnEmpty = e.target === e.target.getStage();
        if (clickedOnEmpty) {
          clearSelection();
        }
        return;
      }
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = getScenePos(stage);
      if (!pos) return;
      handleCanvasClick(pos.x, pos.y);
    },
    [tool, handleCanvasClick, getScenePos, clearSelection],
  );

  const onStageMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = getScenePos(stage);
      if (pos) setCursorPos(pos.x, pos.y);
    },
    [getScenePos, setCursorPos],
  );

  const onPointDragEnd = useCallback(
    (id: string, e: Konva.KonvaEventObject<DragEvent>) => {
      movePoint(id, e.target.x(), e.target.y());
    },
    [movePoint],
  );

  const onPointClick = useCallback(
    (id: string, e: Konva.KonvaEventObject<MouseEvent>) => {
      e.cancelBubble = true;
      if (tool === "select") {
        if (e.evt.shiftKey) {
          toggleSelected(id);
        } else {
          setSelected(id);
        }
      }
    },
    [tool, setSelected, toggleSelected],
  );

  // 치수선 데이터 (라인 길이)
  const lineDimensions = useMemo((): LineDimension[] => {
    return lines.map((ln) => {
      const sp = pointMap.get(ln.startPointId);
      const ep = pointMap.get(ln.endPointId);
      if (!sp || !ep) return null;
      const dx = ep.x - sp.x;
      const dy = ep.y - sp.y;
      const len = Math.sqrt(dx * dx + dy * dy);
      const mx = (sp.x + ep.x) / 2;
      const my = (sp.y + ep.y) / 2;
      const lenM = len / cadScale;
      return { id: ln.id, mx, my, lenM, offset: -12 };
    }).filter((d): d is LineDimension => d !== null);
  }, [lines, pointMap, cadScale]);

  if (loadError) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[var(--surface-soft)]" role="alert">
        <div className="text-sm font-semibold text-red-500">
          캔버스 로드 실패: {loadError}
        </div>
      </div>
    );
  }

  if (!mounted || !isReady || !rk) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[var(--surface-soft)]">
        <div className="text-sm font-semibold text-[var(--text-tertiary)] animate-pulse">
          캔버스 준비 중...
        </div>
      </div>
    );
  }

  const { Stage, Layer, Group, Line, Circle, Rect, Text, Transformer } = rk;

  return (
    <Stage
      ref={stageRef}
      width={width}
      height={height}
      onClick={onStageClick}
      onWheel={onWheel}
      onMouseMove={onStageMouseMove}
      draggable
      style={{ cursor: tool === "select" ? "default" : "crosshair" }}
      aria-label="CAD 파라메트릭 에디터. 마우스로 도형을 그리거나 커맨드라인에 명령어를 입력하세요."
      role="application"
    >
      {/* 그리드 레이어 */}
      <Layer listening={false}>
        {gridLines.map((g: GridLine, i: number) => (
          <Group key={i}>
            <Line points={g.points} stroke={GRID_COLOR} strokeWidth={1} />
            {i % 5 === 0 && (
              <Text
                x={g.vertical ? g.points[0] + 2 : 2}
                y={g.vertical ? 2 : g.points[1] + 2}
                text={g.label}
                fontSize={9}
                fill={GRID_LABEL_COLOR}
              />
            )}
          </Group>
        ))}
      </Layer>

      {/* 도형 레이어 */}
      <Layer>
        {/* 폴리곤 */}
        {polygons.map((pg: CadPolygon) => {
          const flatPoints = pg.pointIds.flatMap((pid: string) => {
            const pt = pointMap.get(pid);
            return pt ? [pt.x, pt.y] : [];
          });
          if (flatPoints.length < 6) return null;
          const isSel = selectedSet.has(pg.id);
          return (
            <Line
              key={pg.id}
              points={flatPoints}
              closed
              fill={pg.fill}
              stroke={isSel ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={isSel ? 2.5 : 1.5}
              onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.cancelBubble = true;
                if (tool === "select") {
                  if (e.evt.shiftKey) toggleSelected(pg.id);
                  else setSelected(pg.id);
                }
              }}
            />
          );
        })}

        {/* 진행 중인 폴리곤 미리보기 */}
        {pendingPointIds.length >= 2 && (
          <Line
            points={pendingPointIds.flatMap((pid: string) => {
              const pt = pointMap.get(pid);
              return pt ? [pt.x, pt.y] : [];
            })}
            stroke={PENDING_LINE_COLOR}
            strokeWidth={1.5}
            dash={[6, 4]}
          />
        )}

        {/* 사각형 (Rect) */}
        {rects.map((rc: CadRect) => {
          const isSel = selectedSet.has(rc.id);
          return (
            <Rect
              key={rc.id}
              ref={(node: Konva.Node | null) => registerRef(rc.id, node)}
              x={rc.x}
              y={rc.y}
              width={rc.width}
              height={rc.height}
              rotation={rc.rotation ?? 0}
              fill={RECT_FILL}
              stroke={isSel ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={isSel ? 2.5 : 1.5}
              draggable={tool === "select"}
              onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.cancelBubble = true;
                if (tool === "select") {
                  if (e.evt.shiftKey) toggleSelected(rc.id);
                  else setSelected(rc.id);
                }
              }}
            />
          );
        })}

        {/* 원 (Circle) */}
        {circles.map((ci: CadCircle) => {
          const isSel = selectedSet.has(ci.id);
          return (
            <Circle
              key={ci.id}
              ref={(node: Konva.Node | null) => registerRef(ci.id, node)}
              x={ci.cx}
              y={ci.cy}
              radius={ci.radius}
              fill={CIRCLE_FILL}
              stroke={isSel ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={isSel ? 2.5 : 1.5}
              draggable={tool === "select"}
              onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.cancelBubble = true;
                if (tool === "select") {
                  if (e.evt.shiftKey) toggleSelected(ci.id);
                  else setSelected(ci.id);
                }
              }}
            />
          );
        })}

        {/* 텍스트 (Text) */}
        {texts.map((tx: CadText) => {
          const isSel = selectedSet.has(tx.id);
          return (
            <Text
              key={tx.id}
              ref={(node: Konva.Node | null) => registerRef(tx.id, node)}
              x={tx.x}
              y={tx.y}
              text={tx.text}
              fontSize={tx.fontSize ?? 14}
              rotation={tx.rotation ?? 0}
              fill={isSel ? POINT_SELECTED_COLOR : TEXT_COLOR}
              draggable={tool === "select"}
              onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.cancelBubble = true;
                if (tool === "select") {
                  if (e.evt.shiftKey) toggleSelected(tx.id);
                  else setSelected(tx.id);
                }
              }}
            />
          );
        })}

        {/* 진행 중인 Rect 미리보기 */}
        {tool === "rect" && pendingOrigin && (
          <Rect
            x={pendingOrigin.x}
            y={pendingOrigin.y}
            width={2}
            height={2}
            stroke={PENDING_LINE_COLOR}
            strokeWidth={1.5}
            dash={[6, 4]}
            listening={false}
          />
        )}

        {/* 진행 중인 Circle 미리보기 */}
        {tool === "circle" && pendingOrigin && (
          <Group listening={false}>
            <Circle
              x={pendingOrigin.x}
              y={pendingOrigin.y}
              radius={4}
              fill={PENDING_LINE_COLOR}
            />
            <Text
              x={pendingOrigin.x + 8}
              y={pendingOrigin.y - 6}
              text="반지름 클릭"
              fontSize={10}
              fill={PENDING_LINE_COLOR}
            />
          </Group>
        )}

        {/* 라인 */}
        {lines.map((ln: CadLine) => {
          const sp = pointMap.get(ln.startPointId);
          const ep = pointMap.get(ln.endPointId);
          if (!sp || !ep) return null;
          const isSel = selectedSet.has(ln.id);
          return (
            <Line
              key={ln.id}
              points={[sp.x, sp.y, ep.x, ep.y]}
              stroke={isSel ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={isSel ? 3 : LINE_STROKE}
              hitStrokeWidth={12}
              onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
                e.cancelBubble = true;
                if (tool === "select") {
                  if (e.evt.shiftKey) toggleSelected(ln.id);
                  else setSelected(ln.id);
                }
              }}
            />
          );
        })}

        {/* 포인트 */}
        {points.map((pt: CadPoint) => {
          const isSelected = selectedSet.has(pt.id);
          const isPending = pendingPointIds.includes(pt.id);
          return (
            <Group key={pt.id}>
              <Circle
                x={pt.x}
                y={pt.y}
                radius={isSelected ? POINT_SELECTED_RADIUS : POINT_RADIUS}
                fill={isSelected ? POINT_SELECTED_COLOR : isPending ? PENDING_LINE_COLOR : POINT_COLOR}
                stroke="#fff"
                strokeWidth={2}
                draggable={tool === "select"}
                onDragEnd={(e: Konva.KonvaEventObject<DragEvent>) => onPointDragEnd(pt.id, e)}
                onClick={(e: Konva.KonvaEventObject<MouseEvent>) => onPointClick(pt.id, e)}
                onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
                  const container = e.target.getStage()?.container();
                  if (container) container.style.cursor = "grab";
                }}
                onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
                  const container = e.target.getStage()?.container();
                  if (container) {
                    container.style.cursor = tool === "select" ? "default" : "crosshair";
                  }
                }}
              />
              {pt.label && (
                <Text
                  x={pt.x + 10}
                  y={pt.y - 6}
                  text={pt.label}
                  fontSize={11}
                  fill={LINE_COLOR}
                />
              )}
            </Group>
          );
        })}
      </Layer>

      {/* 치수선 레이어 (A-DIMS) */}
      <Layer listening={false}>
        {/* 라인 길이 표시 */}
        {lineDimensions.map((dim: LineDimension) => (
          <Text
            key={`dim-${dim.id}`}
            x={dim.mx}
            y={dim.my + dim.offset}
            text={`${dim.lenM.toFixed(1)}m`}
            fontSize={10}
            fill={DIMS_COLOR}
            fontStyle="bold"
          />
        ))}

        {/* Rect 치수 표시 */}
        {rects.map((rc: CadRect) => {
          const wM = (rc.width / cadScale).toFixed(1);
          const hM = (rc.height / cadScale).toFixed(1);
          return (
            <Group key={`dim-${rc.id}`}>
              <Text
                x={rc.x + rc.width / 2 - 20}
                y={rc.y - 14}
                text={`${wM}m`}
                fontSize={10}
                fill={DIMS_COLOR}
              />
              <Text
                x={rc.x + rc.width + 4}
                y={rc.y + rc.height / 2 - 6}
                text={`${hM}m`}
                fontSize={10}
                fill={DIMS_COLOR}
              />
            </Group>
          );
        })}

        {/* Circle 반지름 표시 */}
        {circles.map((ci: CadCircle) => {
          const rM = (ci.radius / cadScale).toFixed(1);
          return (
            <Text
              key={`dim-${ci.id}`}
              x={ci.cx + 4}
              y={ci.cy - ci.radius - 14}
              text={`r=${rM}m`}
              fontSize={10}
              fill={DIMS_COLOR}
            />
          );
        })}

        {/* 폴리곤 면적 표시 */}
        {polygons.map((pg: CadPolygon) => {
          const pts = pg.pointIds
            .map((pid: string) => pointMap.get(pid))
            .filter((p): p is CadPoint => p !== undefined);
          if (pts.length < 3) return null;
          // Shoelace formula
          let area = 0;
          for (let i = 0; i < pts.length; i++) {
            const j = (i + 1) % pts.length;
            area += pts[i].x * pts[j].y;
            area -= pts[j].x * pts[i].y;
          }
          area = Math.abs(area) / 2;
          const areaM2 = area / (cadScale * cadScale);
          // Centroid
          const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
          const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
          return (
            <Text
              key={`area-${pg.id}`}
              x={cx - 20}
              y={cy - 6}
              text={`${areaM2.toFixed(1)}m²`}
              fontSize={11}
              fill={DIMS_COLOR}
              fontStyle="bold"
            />
          );
        })}
      </Layer>

      {/* Transformer 레이어 (다중 선택 + 변환) */}
      {tool === "select" && selectedIds.length > 0 && (
        <Layer>
          <Transformer
            ref={transformerRef}
            boundBoxFunc={(_oldBox: { x: number; y: number; width: number; height: number }, newBox: { x: number; y: number; width: number; height: number }) => newBox}
            rotateEnabled={true}
            enabledAnchors={["top-left", "top-right", "bottom-left", "bottom-right", "middle-left", "middle-right", "top-center", "bottom-center"]}
            borderStroke={POINT_SELECTED_COLOR}
            borderStrokeWidth={1.5}
            borderDash={[4, 3]}
            anchorStroke={POINT_SELECTED_COLOR}
            anchorFill="#fff"
            anchorSize={8}
            anchorCornerRadius={2}
          />
        </Layer>
      )}

      {/* 분석 마커 레이어 */}
      {analysisMarkers.length > 0 && (
        <Layer>
          {analysisMarkers.map((m: { id: string; x: number; y: number; severity: string; desc: string }) => (
            <Group key={m.id} x={m.x} y={m.y}>
              <Circle
                radius={8}
                fill={m.severity === "high" ? "#ef4444" : m.severity === "med" ? "#f59e0b" : "#3b82f6"}
                stroke="#fff"
                strokeWidth={2}
                shadowBlur={10}
                shadowColor="rgba(0,0,0,0.3)"
              />
              <Text
                text="!"
                fill="#fff"
                fontSize={10}
                fontStyle="bold"
                x={-2}
                y={-5}
              />
            </Group>
          ))}
        </Layer>
      )}
    </Stage>
  );
}
