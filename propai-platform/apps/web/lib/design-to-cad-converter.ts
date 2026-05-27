/**
 * Design AI 평면도 결과를 CAD 엔티티 배열로 변환하는 유틸리티.
 *
 * Design 모듈에서 생성된 FloorPlanResult를 use-cad-store가
 * 이해하는 CadEntity 형식으로 매핑한다.
 */

/* ── Types ── */

export interface FloorPlanResult {
  rooms: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
  }>;
  walls: Array<{
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  }>;
  cores: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
  dimensions: {
    totalWidth: number;
    totalDepth: number;
  };
}

export interface CadEntity {
  id: string;
  type: "rect" | "line" | "text";
  x: number;
  y: number;
  width?: number;
  height?: number;
  x2?: number;
  y2?: number;
  label?: string;
  layer: string;
  style?: Record<string, string>;
}

/* ── ID Generator ── */

let entitySeq = 0;

function nextId(prefix: string): string {
  return `${prefix}-conv-${++entitySeq}`;
}

/** 외부에서 시퀀스를 초기화할 때 사용. */
export function resetConverterSequence(): void {
  entitySeq = 0;
}

/* ── Converter ── */

/**
 * FloorPlanResult를 CadEntity 배열로 변환한다.
 *
 * - rooms → rect (A-WALL 레이어) + text (A-TEXT 레이어)
 * - walls → line (A-WALL 레이어)
 * - cores → rect (A-CORE 레이어, 별도 스타일)
 * - 외곽 치수선 → line + text (A-DIMS 레이어)
 *
 * @param plan  Design AI가 반환한 평면도 데이터
 * @param scale px/m 비율 (기본 10)
 * @returns CadEntity 배열
 */
export function convertFloorPlanToCadEntities(
  plan: FloorPlanResult,
  scale = 10,
): CadEntity[] {
  const entities: CadEntity[] = [];

  // ── 실 (Rooms) → rect + label text ──
  for (const room of plan.rooms) {
    const rx = room.x * scale;
    const ry = room.y * scale;
    const rw = room.width * scale;
    const rh = room.height * scale;

    entities.push({
      id: nextId("rc"),
      type: "rect",
      x: rx,
      y: ry,
      width: rw,
      height: rh,
      layer: "A-WALL",
      style: {
        fill: "rgba(14,116,144,0.08)",
        stroke: "#13212f",
        strokeWidth: "1.5",
      },
    });

    // 실 라벨 (중앙)
    if (room.label) {
      entities.push({
        id: nextId("tx"),
        type: "text",
        x: rx + rw / 2 - 10,
        y: ry + rh / 2 - 6,
        label: room.label,
        layer: "A-TEXT",
        style: {
          fontSize: "12",
          fill: "#2d3436",
        },
      });
    }
  }

  // ── 벽체 (Walls) → line ──
  for (const wall of plan.walls) {
    entities.push({
      id: nextId("ln"),
      type: "line",
      x: wall.x1 * scale,
      y: wall.y1 * scale,
      x2: wall.x2 * scale,
      y2: wall.y2 * scale,
      layer: "A-WALL",
      style: {
        stroke: "#000000",
        strokeWidth: "2",
      },
    });
  }

  // ── 코어 (Cores) → rect ──
  for (const core of plan.cores) {
    entities.push({
      id: nextId("rc"),
      type: "rect",
      x: core.x * scale,
      y: core.y * scale,
      width: core.width * scale,
      height: core.height * scale,
      layer: "A-CORE",
      style: {
        fill: "rgba(99,102,241,0.15)",
        stroke: "#6366f1",
        strokeWidth: "2",
      },
    });
  }

  // ── 외곽 치수선 ──
  const totalW = plan.dimensions.totalWidth * scale;
  const totalD = plan.dimensions.totalDepth * scale;
  const dimOffset = 20;

  // 가로 치수선 (상단)
  entities.push({
    id: nextId("ln"),
    type: "line",
    x: 0,
    y: -dimOffset,
    x2: totalW,
    y2: -dimOffset,
    layer: "A-DIMS",
    style: {
      stroke: "#d63031",
      strokeWidth: "0.5",
    },
  });

  entities.push({
    id: nextId("tx"),
    type: "text",
    x: totalW / 2 - 15,
    y: -dimOffset - 14,
    label: `${plan.dimensions.totalWidth.toFixed(1)}m`,
    layer: "A-DIMS",
    style: {
      fontSize: "10",
      fill: "#d63031",
      fontStyle: "bold",
    },
  });

  // 세로 치수선 (우측)
  entities.push({
    id: nextId("ln"),
    type: "line",
    x: totalW + dimOffset,
    y: 0,
    x2: totalW + dimOffset,
    y2: totalD,
    layer: "A-DIMS",
    style: {
      stroke: "#d63031",
      strokeWidth: "0.5",
    },
  });

  entities.push({
    id: nextId("tx"),
    type: "text",
    x: totalW + dimOffset + 4,
    y: totalD / 2 - 6,
    label: `${plan.dimensions.totalDepth.toFixed(1)}m`,
    layer: "A-DIMS",
    style: {
      fontSize: "10",
      fill: "#d63031",
      fontStyle: "bold",
    },
  });

  return entities;
}

/**
 * CadEntity 배열을 use-cad-store의 loadDesignPayload 형식으로 변환한다.
 */
export function cadEntitiesToDesignPayload(entities: CadEntity[]) {
  const points: Array<{ id: string; x: number; y: number }> = [];
  const lines: Array<{ id: string; startPointId: string; endPointId: string }> = [];
  const surfaces: Array<{ id: string; pointIds: string[] }> = [];
  const rects: Array<{ id: string; x: number; y: number; width: number; height: number }> = [];
  const circles: Array<{ id: string; cx: number; cy: number; radius: number }> = [];
  const texts: Array<{ id: string; x: number; y: number; text: string }> = [];

  for (const e of entities) {
    switch (e.type) {
      case "rect":
        rects.push({
          id: e.id,
          x: e.x,
          y: e.y,
          width: e.width ?? 0,
          height: e.height ?? 0,
        });
        break;

      case "line": {
        const pid1 = `${e.id}-sp`;
        const pid2 = `${e.id}-ep`;
        points.push({ id: pid1, x: e.x, y: e.y });
        points.push({ id: pid2, x: e.x2 ?? e.x, y: e.y2 ?? e.y });
        lines.push({ id: e.id, startPointId: pid1, endPointId: pid2 });
        break;
      }

      case "text":
        texts.push({
          id: e.id,
          x: e.x,
          y: e.y,
          text: e.label ?? "",
        });
        break;
    }
  }

  return {
    points,
    lines,
    surfaces,
    rects,
    circles,
    texts,
    floor_count: 1,
    building_height_m: 3.0,
    scale: 10.0,
  };
}
