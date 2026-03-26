"use client";

import { useCallback, useMemo, useRef } from "react";
import { Circle, Group, Layer, Line, Rect, Stage, Text } from "react-konva";
import type Konva from "konva";
import { useCadStore } from "@/store/use-cad-store";

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

export function CadCanvasInner({ width, height }: CadCanvasInnerProps) {
  const stageRef = useRef<Konva.Stage>(null);

  const points = useCadStore((s) => s.points);
  const lines = useCadStore((s) => s.lines);
  const polygons = useCadStore((s) => s.polygons);
  const selectedId = useCadStore((s) => s.selectedId);
  const tool = useCadStore((s) => s.tool);
  const gridSize = useCadStore((s) => s.gridSize);
  const pendingPointIds = useCadStore((s) => s.pendingPointIds);
  const handleCanvasClick = useCadStore((s) => s.handleCanvasClick);
  const movePoint = useCadStore((s) => s.movePoint);
  const setSelected = useCadStore((s) => s.setSelected);

  const pointMap = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const p of points) {
      map.set(p.id, { x: p.x, y: p.y });
    }
    return map;
  }, [points]);

  const gridLines = useMemo(() => {
    const result: Array<{ points: number[]; vertical: boolean; label: string }> = [];
    for (let x = 0; x <= width; x += gridSize) {
      result.push({
        points: [x, 0, x, height],
        vertical: true,
        label: `${x}`,
      });
    }
    for (let y = 0; y <= height; y += gridSize) {
      result.push({
        points: [0, y, width, y],
        vertical: false,
        label: `${y}`,
      });
    }
    return result;
  }, [width, height, gridSize]);

  const onStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (tool === "select") return;
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = stage.getPointerPosition();
      if (!pos) return;
      handleCanvasClick(pos.x, pos.y);
    },
    [tool, handleCanvasClick],
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
        setSelected(id);
      }
    },
    [tool, setSelected],
  );

  return (
    <Stage
      ref={stageRef}
      width={width}
      height={height}
      onClick={onStageClick}
      style={{ cursor: tool === "select" ? "default" : "crosshair" }}
      aria-label="CAD 캔버스"
      role="img"
    >
      {/* 그리드 레이어 */}
      <Layer listening={false}>
        {gridLines.map((g, i) => (
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
        {polygons.map((pg) => {
          const flatPoints = pg.pointIds.flatMap((pid) => {
            const pt = pointMap.get(pid);
            return pt ? [pt.x, pt.y] : [];
          });
          if (flatPoints.length < 6) return null;
          return (
            <Line
              key={pg.id}
              points={flatPoints}
              closed
              fill={pg.fill}
              stroke={selectedId === pg.id ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={selectedId === pg.id ? 2.5 : 1.5}
              onClick={(e) => {
                e.cancelBubble = true;
                if (tool === "select") setSelected(pg.id);
              }}
            />
          );
        })}

        {/* 진행 중인 폴리곤 미리보기 */}
        {pendingPointIds.length >= 2 && (
          <Line
            points={pendingPointIds.flatMap((pid) => {
              const pt = pointMap.get(pid);
              return pt ? [pt.x, pt.y] : [];
            })}
            stroke={PENDING_LINE_COLOR}
            strokeWidth={1.5}
            dash={[6, 4]}
          />
        )}

        {/* 라인 */}
        {lines.map((ln) => {
          const sp = pointMap.get(ln.startPointId);
          const ep = pointMap.get(ln.endPointId);
          if (!sp || !ep) return null;
          return (
            <Line
              key={ln.id}
              points={[sp.x, sp.y, ep.x, ep.y]}
              stroke={selectedId === ln.id ? POINT_SELECTED_COLOR : LINE_COLOR}
              strokeWidth={selectedId === ln.id ? 3 : LINE_STROKE}
              hitStrokeWidth={12}
              onClick={(e) => {
                e.cancelBubble = true;
                if (tool === "select") setSelected(ln.id);
              }}
            />
          );
        })}

        {/* 포인트 */}
        {points.map((pt) => {
          const isSelected = selectedId === pt.id;
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
                onDragEnd={(e) => onPointDragEnd(pt.id, e)}
                onClick={(e) => onPointClick(pt.id, e)}
                onMouseEnter={(e) => {
                  const container = e.target.getStage()?.container();
                  if (container) container.style.cursor = "grab";
                }}
                onMouseLeave={(e) => {
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

      {/* 선택 표시 레이어 */}
      {selectedId && tool === "select" && (
        <Layer listening={false}>
          {(() => {
            const pt = points.find((p) => p.id === selectedId);
            if (pt) {
              return (
                <Rect
                  x={pt.x - 14}
                  y={pt.y - 14}
                  width={28}
                  height={28}
                  stroke={POINT_SELECTED_COLOR}
                  strokeWidth={1.5}
                  dash={[4, 3]}
                  cornerRadius={4}
                />
              );
            }
            return null;
          })()}
        </Layer>
      )}
    </Stage>
  );
}
