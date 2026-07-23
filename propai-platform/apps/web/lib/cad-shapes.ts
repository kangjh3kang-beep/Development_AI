/**
 * CAD 2.0 다중 도형 모델 — 레이어 기반 CadShape[]와 기존 단일 외곽
 * 계약(points/lines/surfaces) 간 변환을 담당하는 순수 유틸 모듈.
 *
 * 하위호환 원칙(additive):
 * - 기존 소비자(export-edited-dxf·building-compliance·GLB 매스 역산)는
 *   points/lines/surfaces만 읽는다 → 저장 시 shapesToLegacy로 외곽 ring을
 *   기존 계약 그대로 파생해 동봉한다(키·형식 불변 — 소비자 무수정).
 * - 구버전 저장본(points+surfaces)은 legacyToShapes가 outline polygon 1개로 복원.
 * - 렌더·편집은 CADEditor가 담당하고, 본 모듈은 순수 함수만 둔다(vitest 검증).
 */

/* ───────────── 타입 ───────────── */

export type LayerKey = "outline" | "wall" | "dim" | "note";

export const LAYER_KEYS: readonly LayerKey[] = ["outline", "wall", "dim", "note"];

export const LAYER_LABELS: Record<LayerKey, string> = {
  outline: "외곽",
  wall: "벽체",
  dim: "치수",
  note: "주석",
};

export interface CadShapePoint {
  id: string;
  x: number;
  y: number;
}

export interface CadShape {
  id: string;
  kind: "polygon" | "rect" | "line" | "circle" | "label";
  layer: LayerKey;
  /** polygon: 정점 ring(≥3) · rect: 대각 2점(또는 ≥3코너) · line: 폴리라인 정점(≥2) · circle/label: 기준점 1개. */
  points: CadShapePoint[];
  /** circle 전용 반지름(px). */
  radius?: number;
  /** label 전용 텍스트. */
  text?: string;
}

/** 기존 저장 계약(WP-16 CADSaveRequest의 points/lines/surfaces) — 키·형식 불변. */
export interface LegacyDrawing {
  points: Array<{ id: string; x: number; y: number }>;
  lines: Array<{ id: string; start_point_id: string; end_point_id: string }>;
  surfaces: Array<{ id: string; point_ids: string[] }>;
}

/* ───────────── ID 생성 ───────────── */

let _shapeSeq = 0;

/** 도형 ID 생성(시퀀스+난수 suffix — 저장본 재로드 ID와의 충돌 최소화). */
export function newShapeId(prefix = "shp"): string {
  return `${prefix}-${++_shapeSeq}-${Math.random().toString(36).slice(2, 7)}`;
}

/* ───────────── 외곽(outline) 파생 ───────────── */

/** rect 도형(대각 2점 저장)을 4코너 ring으로 전개한다(이미 ≥3점이면 그대로). */
export function rectToRing(shape: CadShape): CadShapePoint[] {
  if (shape.points.length >= 3) return shape.points;
  if (shape.points.length < 2) return [];
  const [a, b] = shape.points;
  const minX = Math.min(a.x, b.x);
  const maxX = Math.max(a.x, b.x);
  const minY = Math.min(a.y, b.y);
  const maxY = Math.max(a.y, b.y);
  return [
    { id: `${shape.id}-c0`, x: minX, y: minY },
    { id: `${shape.id}-c1`, x: maxX, y: minY },
    { id: `${shape.id}-c2`, x: maxX, y: maxY },
    { id: `${shape.id}-c3`, x: minX, y: maxY },
  ];
}

/**
 * 폭×깊이(m) 직사각형 외곽 1개를 CadShape[]로 구성(px 스케일 적용).
 *
 * 좌표를 지어내는 게 아니라 실치수(설계 스튜디오 매스 massGeom.buildingWidthM/DepthM 등)의
 * 원점(0,0) 기준 기하학적 전개다 — 값이 없으면 호출부가 애초에 부르지 않는다(무날조).
 * design-audit 기하 브릿지(P1 — massGeomToGeometry)의 유일 소비처.
 */
export function rectangleOutlineShapes(
  widthM: number,
  depthM: number,
  scalePxPerM = 10,
): CadShape[] {
  const id = newShapeId("outline");
  const w = widthM * scalePxPerM;
  const d = depthM * scalePxPerM;
  return [
    {
      id,
      kind: "polygon",
      layer: "outline",
      points: [
        { id: `${id}-p0`, x: 0, y: 0 },
        { id: `${id}-p1`, x: w, y: 0 },
        { id: `${id}-p2`, x: w, y: d },
        { id: `${id}-p3`, x: 0, y: d },
      ],
    },
  ];
}

/** outline 레이어의 첫 polygon|rect 도형(법규·면적·저장 계약의 기준 외곽). 없으면 null. */
export function findOutline(shapes: CadShape[]): CadShape | null {
  return (
    shapes.find(
      (s) => s.layer === "outline" && (s.kind === "polygon" || s.kind === "rect"),
    ) ?? null
  );
}

/** 외곽 도형의 정점 ring(polygon→points, rect→4코너). 외곽 없으면 []. */
export function outlineRing(shape: CadShape | null): CadShapePoint[] {
  if (!shape) return [];
  if (shape.kind === "rect") return rectToRing(shape);
  return shape.points;
}

/* ───────────── 신·구 계약 변환 ───────────── */

/**
 * shapes[] → 기존 저장 계약(points/lines/surfaces) 파생.
 * outline ring만 기존 계약으로 내보낸다(기존 소비자는 단일 외곽만 이해).
 * outline이 없거나 정점 3개 미만이면 빈 배열(가짜 도형 생성 금지 — 정직 파생).
 */
export function shapesToLegacy(shapes: CadShape[]): LegacyDrawing {
  const ring = outlineRing(findOutline(shapes));
  if (ring.length < 3) return { points: [], lines: [], surfaces: [] };
  const points = ring.map((p) => ({ id: p.id, x: p.x, y: p.y }));
  const lines = ring.map((p, i) => ({
    id: `l${i}`,
    start_point_id: p.id,
    end_point_id: ring[(i + 1) % ring.length].id,
  }));
  const surfaces = [{ id: "s1", point_ids: ring.map((p) => p.id) }];
  return { points, lines, surfaces };
}

/**
 * 구버전(v1) 저장본 → shapes[] 마이그레이션.
 * surfaces[0].point_ids로 정점 순서를 복원(없으면 points 순서)해
 * outline polygon 1개로 승격한다. 정점 3개 미만이면 [](빈 캔버스 → 시드 경로).
 */
export function legacyToShapes(
  data:
    | {
        points?: Array<{ id?: unknown; x?: unknown; y?: unknown }> | null;
        surfaces?: Array<{ point_ids?: unknown }> | null;
      }
    | null
    | undefined,
): CadShape[] {
  const rawPoints = data && Array.isArray(data.points) ? data.points : [];
  if (rawPoints.length < 3) return [];
  const pmap: Record<string, CadShapePoint> = {};
  for (const p of rawPoints) {
    const x = Number(p?.x);
    const y = Number(p?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const id = String(p?.id ?? "");
    if (!id) continue;
    pmap[id] = { id, x, y };
  }
  const firstSurface = data && Array.isArray(data.surfaces) ? data.surfaces[0] : undefined;
  const order: string[] =
    firstSurface && Array.isArray(firstSurface.point_ids)
      ? (firstSurface.point_ids as unknown[]).map(String)
      : rawPoints.map((p) => String(p?.id ?? ""));
  const ring = order.map((id) => pmap[id]).filter(Boolean);
  if (ring.length < 3) return [];
  return [{ id: newShapeId("outline"), kind: "polygon", layer: "outline", points: ring }];
}

/* ───────────── 기하 유틸 ───────────── */

/** 신발끈 공식 면적(px²). 정점 3개 미만이면 0. */
export function ringAreaPx(ring: Array<{ x: number; y: number }>): number {
  if (ring.length < 3) return 0;
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i];
    const q = ring[(i + 1) % ring.length];
    a += p.x * q.y - q.x * p.y;
  }
  return Math.abs(a) / 2;
}

/** ring 경계상자(px). 빈 ring이면 null. */
export function ringBbox(
  ring: Array<{ x: number; y: number }>,
):
  | { minX: number; minY: number; maxX: number; maxY: number; widthPx: number; heightPx: number }
  | null {
  if (ring.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of ring) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY, widthPx: maxX - minX, heightPx: maxY - minY };
}

export interface SnapHit {
  x: number;
  y: number;
  shapeId: string;
  pointId: string;
}

/**
 * (x,y)에서 tolerancePx 이내의 가장 가까운 기존 정점으로 스냅.
 * 경계 포함(거리 == tolerance → 스냅). 없으면 null. excludeShapeId로 자기 자신 제외 가능.
 */
export function snapToVertex(
  x: number,
  y: number,
  shapes: CadShape[],
  tolerancePx = 10,
  excludeShapeId?: string,
): SnapHit | null {
  let best: SnapHit | null = null;
  let bestDist = Infinity;
  for (const s of shapes) {
    if (excludeShapeId && s.id === excludeShapeId) continue;
    for (const p of s.points) {
      const d = Math.hypot(p.x - x, p.y - y);
      if (d <= tolerancePx && d < bestDist) {
        bestDist = d;
        best = { x: p.x, y: p.y, shapeId: s.id, pointId: p.id };
      }
    }
  }
  return best;
}

/* ───────────── 저장본 복원 검증 ───────────── */

const VALID_KINDS: ReadonlySet<string> = new Set(["polygon", "rect", "line", "circle", "label"]);
const VALID_LAYERS: ReadonlySet<string> = new Set(LAYER_KEYS);

/**
 * 저장본/외부 입력의 shapes 배열을 검증·정제한다.
 * kind·layer가 모르는 값이거나 정점 수가 부족한 도형은 버린다(무효 데이터 무시 — 정직 복원).
 */
export function sanitizeShapes(raw: unknown): CadShape[] {
  if (!Array.isArray(raw)) return [];
  const out: CadShape[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const s = item as Record<string, unknown>;
    const kind = String(s.kind ?? "");
    const layer = String(s.layer ?? "");
    if (!VALID_KINDS.has(kind) || !VALID_LAYERS.has(layer)) continue;
    const ptsRaw = Array.isArray(s.points) ? s.points : [];
    const points: CadShapePoint[] = [];
    for (const p of ptsRaw) {
      const rec = p as Record<string, unknown> | null;
      const x = Number(rec?.x);
      const y = Number(rec?.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      points.push({ id: String(rec?.id ?? newShapeId("pt")), x, y });
    }
    const minPts = kind === "polygon" ? 3 : kind === "line" || kind === "rect" ? 2 : 1;
    if (points.length < minPts) continue;
    const shape: CadShape = {
      id: String(s.id ?? newShapeId()),
      kind: kind as CadShape["kind"],
      layer: layer as LayerKey,
      points,
    };
    if (kind === "circle") {
      const radius = Number(s.radius);
      shape.radius = Number.isFinite(radius) && radius > 0 ? radius : 10;
    }
    if (kind === "label") shape.text = typeof s.text === "string" ? s.text : "";
    out.push(shape);
  }
  return out;
}

/* ───────────── DXF 가져오기 변환 ───────────── */

export interface DxfImportPolyline {
  points: Array<{ x: number; y: number }>;
  closed?: boolean;
  layer?: string | null;
}

/**
 * POST import-dxf 응답의 신규 셰이프 항목(백엔드 parse_dxf_to_shapes 실제 출력).
 * 좌표는 백엔드가 이미 px로 변환·y축 하향·bbox 정규화를 마쳤다 — 프론트는 재스케일 금지.
 * - polyline: closed + points[{x,y}]
 * - line: x1/y1/x2/y2(별도 좌표 — points 배열 아님)
 * - circle: cx/cy/r
 * - label: x/y/text
 * layer는 이미 CAD2.0 레이어 키(outline|wall|dim|note), source_layer는 원본 DXF 레이어명.
 */
export interface DxfImportShape {
  kind?: string | null;
  layer?: string | null;
  source_layer?: string | null;
  closed?: boolean | null;
  points?: Array<{ x?: unknown; y?: unknown }> | null;
  x1?: unknown;
  y1?: unknown;
  x2?: unknown;
  y2?: unknown;
  cx?: unknown;
  cy?: unknown;
  r?: unknown;
  x?: unknown;
  y?: unknown;
  text?: string | null;
  [key: string]: unknown;
}

/** POST import-dxf 응답(관용 파싱 — 알 수 없는 키는 무시, 없는 키는 정직 폴백). */
export interface DxfImportResult {
  /** 신규 백엔드 실제 형태 — px 좌표 셰이프 배열(1차 소스). */
  shapes?: DxfImportShape[] | null;
  /** 레거시 폴백 — m 단위 폴리라인 배열(shapes 부재 시에만 px 변환). */
  polylines?: DxfImportPolyline[] | null;
  main_outline_index?: number | null;
  /** 신규 백엔드는 {detected,source} 객체, 레거시는 문자열 — 둘 다 수용. */
  unit?: string | { detected?: string | null; source?: string | null } | null;
  [key: string]: unknown;
}

export interface DxfImportOptions {
  /** 캔버스 px/m 스케일(기본 10 — CADEditor 기본값과 동일). */
  scalePxPerM?: number;
  /** 캔버스 좌상단 여백(px, 기본 40). */
  marginPx?: number;
  /** DXF y-up → 캔버스 y-down 반전(기본 true). */
  flipY?: boolean;
}

/** DXF 단위 문자열 → 미터 환산계수. 미상이면 1(1단위=1m 가정 — 호출부가 정직 고지). */
export function unitToMeters(unit?: string | null): number {
  const u = (unit ?? "").trim().toLowerCase();
  if (u === "mm" || u === "millimeter" || u === "millimeters") return 0.001;
  if (u === "cm" || u === "centimeter" || u === "centimeters") return 0.01;
  if (u === "in" || u === "inch" || u === "inches") return 0.0254;
  if (u === "ft" || u === "foot" || u === "feet") return 0.3048;
  return 1; // m 또는 미상
}

/** DXF 레이어명 → CAD2.0 레이어 분류(외곽 인덱스는 dxfImportToShapes가 우선 지정). */
function classifyImportLayer(name?: string | null): LayerKey {
  const n = (name ?? "").toUpperCase();
  if (n.includes("DIM")) return "dim";
  if (n.includes("TEXT") || n.includes("NOTE") || n.includes("ANNO")) return "note";
  return "wall";
}

/**
 * 셰이프의 layer 값을 CAD2.0 레이어 키로 확정한다.
 * 백엔드가 이미 유효 키(outline|wall|dim|note)를 주면 그대로 신뢰하고,
 * 아니면 source_layer 원본명으로 휴리스틱 분류(가짜 분류 금지 — 알려진 값 우선).
 */
function resolveShapeLayer(layer?: string | null, sourceLayer?: string | null): LayerKey {
  const v = String(layer ?? "");
  if (VALID_LAYERS.has(v)) return v as LayerKey;
  return classifyImportLayer(sourceLayer ?? layer);
}

/**
 * import-dxf 신규 응답의 shapes[](백엔드 px 좌표)를 CadShape[]로 변환한다.
 * 좌표는 백엔드가 이미 px·y하향·정규화를 마쳤으므로 재스케일/반전/마진 적용 금지 — 그대로 사용.
 * - polyline: closed(또는 첫점==끝점)면 polygon, 아니면 line. main_outline_index는 outline 레이어.
 * - line: x1/y1/x2/y2 → 2점 line. circle: cx/cy/r → circle. label: x/y/text → label.
 * - 정점·좌표 부족 셰이프는 제외(변환 불가 — 호출부가 개수 차이로 정직 표기).
 */
function shapesResultToShapes(
  rawShapes: DxfImportShape[],
  mainOutlineIndex: number,
): CadShape[] {
  const out: CadShape[] = [];
  rawShapes.forEach((s, idx) => {
    if (!s || typeof s !== "object") return;
    const kind = String(s.kind ?? "");
    const layerKey = resolveShapeLayer(s.layer, s.source_layer);

    if (kind === "polyline") {
      const isMain = idx === mainOutlineIndex;
      const id = newShapeId(isMain ? "outline" : "imp");
      const valid = (Array.isArray(s.points) ? s.points : []).filter(
        (p) => Number.isFinite(Number(p?.x)) && Number.isFinite(Number(p?.y)),
      );
      if (valid.length < 2) return;
      let pts: CadShapePoint[] = valid.map((p, i) => ({
        id: `${id}-p${i}`,
        x: Number(p?.x),
        y: Number(p?.y),
      }));
      // 첫점 반복 종결(first==last)이면 마지막 정점 제거 + 닫힘 처리.
      const first = pts[0];
      const last = pts[pts.length - 1];
      const dupClosed =
        pts.length >= 2 &&
        Math.abs(first.x - last.x) < 1e-6 &&
        Math.abs(first.y - last.y) < 1e-6;
      if (dupClosed) pts = pts.slice(0, -1);
      const closed = Boolean(s.closed) || dupClosed || isMain;
      if (closed && pts.length >= 3) {
        out.push({
          id,
          kind: "polygon",
          layer: isMain ? "outline" : layerKey,
          points: pts,
        });
      } else if (pts.length >= 2) {
        // 외곽 지정이어도 정점 3개 미만이면 polygon 불가 → line으로 정직 강등.
        out.push({ id, kind: "line", layer: layerKey, points: pts });
      }
    } else if (kind === "line") {
      const x1 = Number(s.x1);
      const y1 = Number(s.y1);
      const x2 = Number(s.x2);
      const y2 = Number(s.y2);
      if (![x1, y1, x2, y2].every(Number.isFinite)) return;
      const id = newShapeId("imp");
      out.push({
        id,
        kind: "line",
        layer: layerKey,
        points: [
          { id: `${id}-p0`, x: x1, y: y1 },
          { id: `${id}-p1`, x: x2, y: y2 },
        ],
      });
    } else if (kind === "circle") {
      const cx = Number(s.cx);
      const cy = Number(s.cy);
      const r = Number(s.r);
      if (!Number.isFinite(cx) || !Number.isFinite(cy)) return;
      const id = newShapeId("imp");
      out.push({
        id,
        kind: "circle",
        layer: layerKey,
        points: [{ id: `${id}-c`, x: cx, y: cy }],
        radius: Number.isFinite(r) && r > 0 ? r : 10,
      });
    } else if (kind === "label") {
      const x = Number(s.x);
      const y = Number(s.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      const id = newShapeId("imp");
      out.push({
        id,
        kind: "label",
        layer: layerKey,
        points: [{ id: `${id}-l`, x, y }],
        text: typeof s.text === "string" ? s.text : "",
      });
    }
    // 알 수 없는 kind는 조용히 무시(백엔드 ignored 보고와 별개 — 가짜 변환 금지).
  });
  return out;
}

/**
 * import-dxf 응답을 CadShape[]로 변환한다.
 *
 * 1차: result.shapes(신규 백엔드 parse_dxf_to_shapes 실제 출력 — px 좌표).
 *   - polyline closed(또는 첫점==끝점) → polygon, open → line. main_outline_index → outline.
 *   - line(x1/y1/x2/y2) → line, circle(cx/cy/r) → circle, label(x/y/text) → label.
 *   - 좌표는 백엔드가 이미 px·y하향·정규화 완료 → 재스케일/반전/마진 적용 금지(그대로 사용).
 * 폴백: result.shapes 부재 시에만 result.polylines(레거시 m단위 폴리라인) → 단위·스케일·반전 적용.
 *   - 닫힌 폴리라인 → polygon, 열린 폴리라인 → line, main_outline_index → outline 레이어.
 *   - 좌표는 단위 환산(unit→m) 후 px 스케일, 전체 bbox 기준 원점(margin) 정규화 + y축 반전.
 * 둘 다 없으면 빈 배열(가짜 도형 생성 금지). 정점·좌표 부족 셰이프는 제외.
 */
export function dxfImportToShapes(
  result: DxfImportResult | null | undefined,
  options?: DxfImportOptions,
): CadShape[] {
  // 1차: 신규 백엔드 shapes[](px 좌표) — 존재하면 폴리라인 폴백보다 우선.
  if (result && Array.isArray(result.shapes) && result.shapes.length > 0) {
    const mainIdxRaw = result.main_outline_index;
    const mainIdx = typeof mainIdxRaw === "number" ? mainIdxRaw : -1;
    return shapesResultToShapes(result.shapes, mainIdx);
  }

  // 폴백: 레거시 polylines[](m 단위) — px 변환(scale·flipY·margin) 적용.
  const polylines = result && Array.isArray(result.polylines) ? result.polylines : [];
  if (polylines.length === 0) return [];
  const scale = options?.scalePxPerM ?? 10;
  const margin = options?.marginPx ?? 40;
  const flipY = options?.flipY ?? true;
  // unit은 신규 객체({detected,source}) 또는 레거시 문자열 — 문자열일 때만 환산(객체면 1m 가정).
  const u = unitToMeters(typeof result?.unit === "string" ? result.unit : null);

  // 전체 bbox(원본 단위) — 캔버스 원점(margin) 정규화 + DXF y-up → 캔버스 y-down 반전 기준.
  let minX = Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let any = false;
  for (const pl of polylines) {
    if (!pl || !Array.isArray(pl.points)) continue;
    for (const p of pl.points) {
      const x = Number(p?.x);
      const y = Number(p?.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      any = true;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (!any) return [];

  const toPx = (p: { x: number; y: number }) => ({
    x: (Number(p.x) - minX) * u * scale + margin,
    y: (flipY ? maxY - Number(p.y) : Number(p.y) - minY) * u * scale + margin,
  });

  const mainIdxRaw = result ? result.main_outline_index : null;
  const mainIdx = typeof mainIdxRaw === "number" ? mainIdxRaw : -1;
  const shapes: CadShape[] = [];
  polylines.forEach((pl, idx) => {
    if (!pl || !Array.isArray(pl.points)) return;
    const valid = pl.points.filter(
      (p) => Number.isFinite(Number(p?.x)) && Number.isFinite(Number(p?.y)),
    );
    if (valid.length < 2) return;
    const isMain = idx === mainIdx;
    const id = newShapeId(isMain ? "outline" : "imp");
    let pts: CadShapePoint[] = valid.map((p, i) => ({ id: `${id}-p${i}`, ...toPx(p) }));
    // 첫점 반복 종결(first==last)이면 마지막 정점 제거 + 닫힘 처리
    const first = pts[0];
    const last = pts[pts.length - 1];
    const dupClosed =
      pts.length >= 2 && Math.abs(first.x - last.x) < 1e-6 && Math.abs(first.y - last.y) < 1e-6;
    if (dupClosed) pts = pts.slice(0, -1);
    const closed = Boolean(pl.closed) || dupClosed || isMain;
    if (closed && pts.length >= 3) {
      shapes.push({
        id,
        kind: "polygon",
        layer: isMain ? "outline" : classifyImportLayer(pl.layer),
        points: pts,
      });
    } else if (pts.length >= 2) {
      // 외곽 지정이어도 정점 3개 미만이면 polygon 불가 → line(벽체)으로 정직 강등.
      shapes.push({ id, kind: "line", layer: classifyImportLayer(pl.layer), points: pts });
    }
  });
  return shapes;
}
