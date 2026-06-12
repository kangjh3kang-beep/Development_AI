import { describe, it, expect } from "vitest";
import {
  type CadShape,
  LAYER_KEYS,
  LAYER_LABELS,
  findOutline,
  outlineRing,
  rectToRing,
  shapesToLegacy,
  legacyToShapes,
  sanitizeShapes,
  snapToVertex,
  ringAreaPx,
  ringBbox,
  unitToMeters,
  dxfImportToShapes,
  newShapeId,
} from "./cad-shapes";

/** 테스트용 outline polygon 도형 생성. */
function makeOutline(pts: Array<[number, number]>, id = "o1"): CadShape {
  return {
    id,
    kind: "polygon",
    layer: "outline",
    points: pts.map(([x, y], i) => ({ id: `${id}p${i}`, x, y })),
  };
}

describe("cad-shapes", () => {
  // ── 레이어 상수 ──
  describe("LAYER_LABELS", () => {
    it("4개 레이어 키 모두 한글 라벨을 가진다", () => {
      expect(LAYER_KEYS).toEqual(["outline", "wall", "dim", "note"]);
      for (const k of LAYER_KEYS) {
        expect(LAYER_LABELS[k]).toBeTruthy();
      }
    });
  });

  // ── findOutline / outlineRing ──
  describe("findOutline", () => {
    it("outline 레이어의 첫 polygon을 반환한다", () => {
      const wall: CadShape = {
        id: "w1", kind: "line", layer: "wall",
        points: [{ id: "a", x: 0, y: 0 }, { id: "b", x: 10, y: 0 }],
      };
      const o1 = makeOutline([[0, 0], [100, 0], [100, 80]], "o1");
      const o2 = makeOutline([[0, 0], [50, 0], [50, 50]], "o2");
      expect(findOutline([wall, o1, o2])?.id).toBe("o1");
    });

    it("outline 레이어의 rect도 외곽으로 인정한다", () => {
      const rect: CadShape = {
        id: "r1", kind: "rect", layer: "outline",
        points: [{ id: "a", x: 10, y: 20 }, { id: "b", x: 110, y: 100 }],
      };
      expect(findOutline([rect])?.id).toBe("r1");
      const ring = outlineRing(rect);
      expect(ring).toHaveLength(4);
      expect(ring[0]).toMatchObject({ x: 10, y: 20 });
      expect(ring[2]).toMatchObject({ x: 110, y: 100 });
    });

    it("outline 레이어의 label/line은 외곽이 아니다", () => {
      const label: CadShape = {
        id: "t1", kind: "label", layer: "outline",
        points: [{ id: "a", x: 0, y: 0 }], text: "메모",
      };
      expect(findOutline([label])).toBeNull();
      expect(outlineRing(null)).toEqual([]);
    });
  });

  describe("rectToRing", () => {
    it("대각 2점 rect를 4코너 ring으로 전개한다(좌표 정규화)", () => {
      const rect: CadShape = {
        id: "r1", kind: "rect", layer: "wall",
        points: [{ id: "a", x: 100, y: 80 }, { id: "b", x: 20, y: 10 }],
      };
      const ring = rectToRing(rect);
      expect(ring.map((p) => [p.x, p.y])).toEqual([
        [20, 10], [100, 10], [100, 80], [20, 80],
      ]);
    });

    it("점 2개 미만이면 빈 배열", () => {
      const rect: CadShape = {
        id: "r1", kind: "rect", layer: "wall", points: [{ id: "a", x: 0, y: 0 }],
      };
      expect(rectToRing(rect)).toEqual([]);
    });
  });

  // ── 신·구 계약 왕복 ──
  describe("왕복 보존(legacy ↔ shapes)", () => {
    const legacy = {
      points: [
        { id: "a", x: 0, y: 0 },
        { id: "b", x: 100, y: 0 },
        { id: "c", x: 100, y: 80 },
        { id: "d", x: 0, y: 80 },
      ],
      surfaces: [{ id: "s1", point_ids: ["a", "b", "c", "d"] }],
    };

    it("legacy → shapes → legacy가 좌표·순서·ID를 보존한다", () => {
      const shapes = legacyToShapes(legacy);
      expect(shapes).toHaveLength(1);
      expect(shapes[0].kind).toBe("polygon");
      expect(shapes[0].layer).toBe("outline");
      const back = shapesToLegacy(shapes);
      expect(back.points).toEqual(legacy.points);
      expect(back.surfaces).toEqual([{ id: "s1", point_ids: ["a", "b", "c", "d"] }]);
      expect(back.lines).toHaveLength(4);
      expect(back.lines[0]).toEqual({ id: "l0", start_point_id: "a", end_point_id: "b" });
      expect(back.lines[3]).toEqual({ id: "l3", start_point_id: "d", end_point_id: "a" });
    });

    it("shapes → legacy → shapes가 외곽 기하를 보존한다", () => {
      const original = makeOutline([[0, 0], [200, 0], [200, 100], [0, 100]]);
      const restored = legacyToShapes(shapesToLegacy([original]));
      expect(restored).toHaveLength(1);
      expect(restored[0].points.map((p) => [p.x, p.y])).toEqual(
        original.points.map((p) => [p.x, p.y]),
      );
    });
  });

  // ── v1 마이그레이션 ──
  describe("legacyToShapes(v1 마이그레이션)", () => {
    it("surfaces[0].point_ids 순서로 ring을 복원한다(points 배열 순서 무시)", () => {
      const shapes = legacyToShapes({
        points: [
          { id: "c", x: 100, y: 80 },
          { id: "a", x: 0, y: 0 },
          { id: "b", x: 100, y: 0 },
        ],
        surfaces: [{ point_ids: ["a", "b", "c"] }],
      });
      expect(shapes[0].points.map((p) => p.id)).toEqual(["a", "b", "c"]);
    });

    it("surfaces가 없으면 points 순서를 그대로 사용한다", () => {
      const shapes = legacyToShapes({
        points: [
          { id: "a", x: 0, y: 0 },
          { id: "b", x: 10, y: 0 },
          { id: "c", x: 10, y: 10 },
        ],
      });
      expect(shapes[0].points.map((p) => p.id)).toEqual(["a", "b", "c"]);
    });

    it("정점 3개 미만·무효 입력이면 빈 배열(시드 경로로 폴백)", () => {
      expect(legacyToShapes({ points: [{ id: "a", x: 0, y: 0 }] })).toEqual([]);
      expect(legacyToShapes(null)).toEqual([]);
      expect(legacyToShapes(undefined)).toEqual([]);
      expect(legacyToShapes({})).toEqual([]);
    });

    it("좌표가 숫자가 아닌 정점은 버린다", () => {
      const shapes = legacyToShapes({
        points: [
          { id: "a", x: 0, y: 0 },
          { id: "b", x: "broken", y: 0 },
          { id: "c", x: 10, y: 10 },
          { id: "d", x: 0, y: 10 },
        ],
        surfaces: [{ point_ids: ["a", "b", "c", "d"] }],
      });
      expect(shapes[0].points.map((p) => p.id)).toEqual(["a", "c", "d"]);
    });
  });

  // ── outline 부재 시 빈 파생 ──
  describe("shapesToLegacy(outline 부재)", () => {
    it("outline이 없으면 빈 points/lines/surfaces를 반환한다(가짜 도형 금지)", () => {
      const wallOnly: CadShape[] = [
        {
          id: "w1", kind: "polygon", layer: "wall",
          points: [
            { id: "a", x: 0, y: 0 }, { id: "b", x: 10, y: 0 }, { id: "c", x: 10, y: 10 },
          ],
        },
      ];
      expect(shapesToLegacy(wallOnly)).toEqual({ points: [], lines: [], surfaces: [] });
      expect(shapesToLegacy([])).toEqual({ points: [], lines: [], surfaces: [] });
    });

    it("outline rect는 4코너 ring으로 파생된다", () => {
      const rect: CadShape = {
        id: "r1", kind: "rect", layer: "outline",
        points: [{ id: "a", x: 0, y: 0 }, { id: "b", x: 100, y: 50 }],
      };
      const legacy = shapesToLegacy([rect]);
      expect(legacy.points).toHaveLength(4);
      expect(legacy.surfaces[0].point_ids).toHaveLength(4);
      expect(legacy.lines).toHaveLength(4);
    });
  });

  // ── snapToVertex 경계 ──
  describe("snapToVertex", () => {
    const shapes: CadShape[] = [
      makeOutline([[100, 100], [200, 100], [200, 200]], "o1"),
      {
        id: "w1", kind: "line", layer: "wall",
        points: [{ id: "wp1", x: 0, y: 0 }, { id: "wp2", x: 5, y: 0 }],
      },
    ];

    it("tolerance 경계(거리==tolerance)에서 스냅된다", () => {
      const hit = snapToVertex(110, 100, shapes, 10);
      expect(hit).toMatchObject({ x: 100, y: 100, shapeId: "o1", pointId: "o1p0" });
    });

    it("tolerance를 넘으면 null", () => {
      expect(snapToVertex(111, 100, shapes, 10)).toBeNull();
    });

    it("여러 후보 중 가장 가까운 정점을 고른다", () => {
      const hit = snapToVertex(3, 0, shapes, 10);
      expect(hit).toMatchObject({ x: 5, y: 0, pointId: "wp2" });
    });

    it("excludeShapeId로 자기 자신 정점을 제외한다", () => {
      expect(snapToVertex(0, 0, shapes, 10, "w1")).toBeNull();
    });

    it("도형이 없으면 null", () => {
      expect(snapToVertex(0, 0, [], 10)).toBeNull();
    });
  });

  // ── 면적·bbox ──
  describe("ringAreaPx / ringBbox", () => {
    it("정사각형 면적(신발끈)", () => {
      const sq = [
        { x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }, { x: 0, y: 100 },
      ];
      expect(ringAreaPx(sq)).toBe(10000);
      // 역방향(시계/반시계 무관 절대값)
      expect(ringAreaPx([...sq].reverse())).toBe(10000);
    });

    it("삼각형 면적", () => {
      expect(ringAreaPx([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 10 }])).toBe(50);
    });

    it("정점 3개 미만이면 0", () => {
      expect(ringAreaPx([])).toBe(0);
      expect(ringAreaPx([{ x: 0, y: 0 }, { x: 10, y: 10 }])).toBe(0);
    });

    it("bbox 폭·높이 계산, 빈 ring은 null", () => {
      const bb = ringBbox([{ x: 10, y: 20 }, { x: 110, y: 100 }, { x: 50, y: 30 }]);
      expect(bb).toMatchObject({ minX: 10, minY: 20, maxX: 110, maxY: 100, widthPx: 100, heightPx: 80 });
      expect(ringBbox([])).toBeNull();
    });
  });

  // ── sanitizeShapes ──
  describe("sanitizeShapes", () => {
    it("유효 도형만 통과시키고 무효 kind/layer/정점부족을 버린다", () => {
      const raw = [
        { id: "ok1", kind: "line", layer: "wall", points: [{ id: "a", x: 0, y: 0 }, { id: "b", x: 1, y: 1 }] },
        { id: "bad-kind", kind: "blob", layer: "wall", points: [{ x: 0, y: 0 }] },
        { id: "bad-layer", kind: "line", layer: "기둥", points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] },
        { id: "few-pts", kind: "polygon", layer: "wall", points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] },
        { id: "lbl", kind: "label", layer: "note", points: [{ id: "p", x: 5, y: 5 }], text: "메모" },
        null,
        "garbage",
      ];
      const out = sanitizeShapes(raw);
      expect(out.map((s) => s.id)).toEqual(["ok1", "lbl"]);
      expect(out[1].text).toBe("메모");
    });

    it("circle은 radius를 보정한다(무효 → 10)", () => {
      const out = sanitizeShapes([
        { id: "c1", kind: "circle", layer: "wall", points: [{ x: 0, y: 0 }], radius: -5 },
        { id: "c2", kind: "circle", layer: "wall", points: [{ x: 0, y: 0 }], radius: 25 },
      ]);
      expect(out[0].radius).toBe(10);
      expect(out[1].radius).toBe(25);
    });

    it("배열이 아니면 빈 배열", () => {
      expect(sanitizeShapes(null)).toEqual([]);
      expect(sanitizeShapes({})).toEqual([]);
    });
  });

  // ── DXF 가져오기 변환 ──
  describe("dxfImportToShapes", () => {
    it("닫힌 폴리라인 → polygon, main_outline_index → outline 레이어", () => {
      const shapes = dxfImportToShapes(
        {
          polylines: [
            { points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 8 }, { x: 0, y: 8 }], closed: true },
            { points: [{ x: 2, y: 2 }, { x: 8, y: 2 }], closed: false },
          ],
          main_outline_index: 0,
          unit: "m",
        },
        { scalePxPerM: 10, marginPx: 40 },
      );
      expect(shapes).toHaveLength(2);
      expect(shapes[0]).toMatchObject({ kind: "polygon", layer: "outline" });
      expect(shapes[1]).toMatchObject({ kind: "line", layer: "wall" });
      // y-up → y-down 반전: (0,0)은 캔버스 좌하단 → y = (8-0)*10+40 = 120
      expect(shapes[0].points[0]).toMatchObject({ x: 40, y: 120 });
      expect(shapes[0].points[2]).toMatchObject({ x: 140, y: 40 });
    });

    it("첫점 반복 종결 폴리라인은 중복 정점 제거 후 polygon", () => {
      const shapes = dxfImportToShapes({
        polylines: [
          { points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 5, y: 5 }, { x: 0, y: 0 }] },
        ],
      });
      expect(shapes[0].kind).toBe("polygon");
      expect(shapes[0].points).toHaveLength(3);
    });

    it("mm 단위는 m로 환산해 스케일한다", () => {
      const shapes = dxfImportToShapes(
        {
          polylines: [
            { points: [{ x: 0, y: 0 }, { x: 10000, y: 0 }, { x: 10000, y: 8000 }], closed: true },
          ],
          unit: "mm",
        },
        { scalePxPerM: 10, marginPx: 0, flipY: false },
      );
      // 10000mm = 10m → 100px (부동소수 오차 허용)
      expect(shapes[0].points[1].x).toBeCloseTo(100, 9);
      expect(shapes[0].points[1].y).toBeCloseTo(0, 9);
      expect(shapes[0].points[2].x).toBeCloseTo(100, 9);
      expect(shapes[0].points[2].y).toBeCloseTo(80, 9);
    });

    it("DXF 레이어명으로 dim/note를 분류한다", () => {
      const shapes = dxfImportToShapes({
        polylines: [
          { points: [{ x: 0, y: 0 }, { x: 1, y: 0 }], layer: "A-DIMS" },
          { points: [{ x: 0, y: 1 }, { x: 1, y: 1 }], layer: "ANNO-TEXT" },
          { points: [{ x: 0, y: 2 }, { x: 1, y: 2 }], layer: "A-WALL" },
        ],
      });
      expect(shapes.map((s) => s.layer)).toEqual(["dim", "note", "wall"]);
    });

    it("외곽 지정이어도 정점 3개 미만이면 polygon 불가 → line으로 강등", () => {
      const shapes = dxfImportToShapes({
        polylines: [{ points: [{ x: 0, y: 0 }, { x: 10, y: 0 }] }],
        main_outline_index: 0,
      });
      expect(shapes[0].kind).toBe("line");
      expect(shapes[0].layer).toBe("wall");
    });

    it("빈/무효 입력은 빈 배열(정점 부족 폴리라인 제외)", () => {
      expect(dxfImportToShapes(null)).toEqual([]);
      expect(dxfImportToShapes({})).toEqual([]);
      expect(dxfImportToShapes({ polylines: [] })).toEqual([]);
      expect(dxfImportToShapes({ polylines: [{ points: [{ x: 1, y: 1 }] }] })).toEqual([]);
    });

    it("unitToMeters — 모르는 단위는 1(1단위=1m 가정)", () => {
      expect(unitToMeters("mm")).toBe(0.001);
      expect(unitToMeters("cm")).toBe(0.01);
      expect(unitToMeters("m")).toBe(1);
      expect(unitToMeters("ft")).toBeCloseTo(0.3048);
      expect(unitToMeters("furlong")).toBe(1);
      expect(unitToMeters(undefined)).toBe(1);
    });
  });

  // ── DXF 가져오기(신규 백엔드 shapes[] 형태 — px 좌표) ──
  describe("dxfImportToShapes(shapes 형태 — 신규 백엔드)", () => {
    it("shapes를 polylines보다 우선 읽고 px 좌표를 재스케일 없이 그대로 쓴다", () => {
      const out = dxfImportToShapes(
        {
          shapes: [
            {
              kind: "polyline",
              layer: "outline",
              source_layer: "WALL",
              closed: true,
              points: [
                { x: 40, y: 120 },
                { x: 140, y: 120 },
                { x: 140, y: 40 },
                { x: 40, y: 40 },
              ],
            },
            {
              kind: "polyline",
              layer: "wall",
              source_layer: "WALL_INTERIOR",
              closed: false,
              points: [
                { x: 60, y: 100 },
                { x: 120, y: 100 },
              ],
            },
          ],
          // 레거시 폴백이 무시되는지 검증 — shapes가 있으면 polylines는 읽지 않는다.
          polylines: [{ points: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }], closed: true }],
          main_outline_index: 0,
          unit: { detected: "mm", source: "insunits" },
          scale_px_per_m: 10,
        },
        { scalePxPerM: 10, marginPx: 40 },
      );
      expect(out).toHaveLength(2);
      expect(out[0]).toMatchObject({ kind: "polygon", layer: "outline" });
      // 백엔드 px 좌표를 그대로 보존(재스케일·반전·마진 미적용)
      expect(out[0].points.map((p) => [p.x, p.y])).toEqual([
        [40, 120], [140, 120], [140, 40], [40, 40],
      ]);
      expect(out[1]).toMatchObject({ kind: "line", layer: "wall" });
      expect(out[1].points.map((p) => [p.x, p.y])).toEqual([[60, 100], [120, 100]]);
    });

    it("line(x1/y1/x2/y2)·circle(cx/cy/r)·label(x/y/text)을 각각 매핑한다", () => {
      const out = dxfImportToShapes({
        shapes: [
          { kind: "line", layer: "wall", x1: 10, y1: 20, x2: 30, y2: 40 },
          { kind: "circle", layer: "dim", cx: 50, cy: 60, r: 8 },
          { kind: "label", layer: "note", x: 70, y: 80, text: "기둥 P1" },
        ],
      });
      expect(out).toHaveLength(3);
      expect(out[0]).toMatchObject({ kind: "line", layer: "wall" });
      expect(out[0].points.map((p) => [p.x, p.y])).toEqual([[10, 20], [30, 40]]);
      expect(out[1]).toMatchObject({ kind: "circle", layer: "dim", radius: 8 });
      expect(out[1].points[0]).toMatchObject({ x: 50, y: 60 });
      expect(out[2]).toMatchObject({ kind: "label", layer: "note", text: "기둥 P1" });
      expect(out[2].points[0]).toMatchObject({ x: 70, y: 80 });
    });

    it("닫힌 polyline 중 main_outline_index만 outline, 나머지는 layer/소스로 분류", () => {
      const out = dxfImportToShapes({
        shapes: [
          {
            kind: "polyline", layer: "wall", closed: true,
            points: [{ x: 0, y: 0 }, { x: 5, y: 0 }, { x: 5, y: 5 }],
          },
          {
            kind: "polyline", layer: "outline", closed: true,
            points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }],
          },
        ],
        main_outline_index: 1,
      });
      expect(out[0]).toMatchObject({ kind: "polygon", layer: "wall" });
      expect(out[1]).toMatchObject({ kind: "polygon", layer: "outline" });
    });

    it("알 수 없는 layer는 source_layer 휴리스틱으로 분류(DIM→dim)", () => {
      const out = dxfImportToShapes({
        shapes: [
          { kind: "line", layer: "기둥", source_layer: "A-DIMS", x1: 0, y1: 0, x2: 1, y2: 0 },
        ],
      });
      expect(out[0].layer).toBe("dim");
    });

    it("좌표 부족 셰이프는 제외하고, circle 반경 무효는 10으로 보정", () => {
      const out = dxfImportToShapes({
        shapes: [
          { kind: "line", layer: "wall", x1: 0, y1: 0, x2: "x", y2: 1 }, // 무효 → 제외
          { kind: "polyline", layer: "wall", closed: false, points: [{ x: 1, y: 1 }] }, // 1점 → 제외
          { kind: "circle", layer: "wall", cx: 5, cy: 5, r: -3 }, // 반경 무효 → 10
        ],
      });
      expect(out).toHaveLength(1);
      expect(out[0]).toMatchObject({ kind: "circle", radius: 10 });
    });

    it("빈 shapes 배열이면 polylines 폴백으로 내려간다", () => {
      const out = dxfImportToShapes(
        {
          shapes: [],
          polylines: [
            { points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 8 }], closed: true },
          ],
          unit: "m",
        },
        { scalePxPerM: 10, marginPx: 40 },
      );
      expect(out).toHaveLength(1);
      expect(out[0].kind).toBe("polygon");
    });
  });

  // ── ID 생성 ──
  describe("newShapeId", () => {
    it("호출마다 고유 ID를 생성한다", () => {
      const a = newShapeId();
      const b = newShapeId();
      expect(a).not.toBe(b);
      expect(newShapeId("outline").startsWith("outline-")).toBe(true);
    });
  });
});
