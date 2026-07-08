/**
 * CAD 텍스트 커맨드 파서 + 실행기.
 *
 * AutoCAD 스타일 명령어를 파싱하여 Zustand store에 직접 적용한다.
 * 모든 좌표는 m 단위 입력 → 내부적으로 scale 곱하여 px 변환.
 */

import { PYEONG_SQM } from "@/lib/formatters";

// ── 타입 ──

export type CommandResult = {
  ok: boolean;
  message: string;
};

type StoreApi = {
  addPoint: (x: number, y: number) => string;
  addLine: (startId: string, endId: string) => void;
  addRect: (x: number, y: number, w: number, h: number) => void;
  addCircle: (cx: number, cy: number, r: number) => void;
  addText: (x: number, y: number, text: string) => void;
  addPolygon: (pointIds: string[]) => void;
  removeSelected: () => void;
  undo: () => void;
  redo: () => void;
  setSelected: (id: string | null) => void;
  points: Array<{ id: string; x: number; y: number }>;
  lines: Array<{ id: string; startPointId: string; endPointId: string }>;
  polygons: Array<{ id: string; pointIds: string[] }>;
  rects: Array<{ id: string; x: number; y: number; width: number; height: number }>;
  circles: Array<{ id: string; cx: number; cy: number; radius: number }>;
  texts: Array<{ id: string; x: number; y: number; text: string }>;
  selectedId: string | null;
  selectedIds: string[];
  scale: number;
  movePoint: (id: string, x: number, y: number) => void;
};

type CommandDef = {
  name: string;
  aliases: string[];
  hint: string;
  execute: (args: string, store: StoreApi) => CommandResult;
};

// ── 좌표 파싱 유틸 ──

function parseCoord(token: string): { x: number; y: number } | null {
  const parts = token.split(",").map((s) => parseFloat(s.trim()));
  if (parts.length === 2 && parts.every((n) => !isNaN(n))) {
    return { x: parts[0], y: parts[1] };
  }
  return null;
}

function parseNumber(token: string): number | null {
  const n = parseFloat(token.trim());
  return isNaN(n) ? null : n;
}

// ── 명령어 정의 ──

const COMMANDS: CommandDef[] = [
  // ── 그리기 ──
  {
    name: "LINE",
    aliases: ["L", "선"],
    hint: "LINE x1,y1 x2,y2 — 두 점 사이 직선",
    execute: (args, store) => {
      const tokens = args.trim().split(/\s+/);
      if (tokens.length < 2) return { ok: false, message: "사용법: LINE x1,y1 x2,y2" };
      const p1 = parseCoord(tokens[0]);
      const p2 = parseCoord(tokens[1]);
      if (!p1 || !p2) return { ok: false, message: "좌표 형식: x,y (예: 10,20)" };
      const s = store.scale;
      const id1 = store.addPoint(p1.x * s, p1.y * s);
      const id2 = store.addPoint(p2.x * s, p2.y * s);
      store.addLine(id1, id2);
      return { ok: true, message: `선 생성: (${p1.x},${p1.y}) → (${p2.x},${p2.y})` };
    },
  },
  {
    name: "RECT",
    aliases: ["R", "REC", "사각형"],
    hint: "RECT x,y w h — 사각형 (좌상단 + 가로 세로)",
    execute: (args, store) => {
      const tokens = args.trim().split(/\s+/);
      if (tokens.length < 3) return { ok: false, message: "사용법: RECT x,y w h" };
      const origin = parseCoord(tokens[0]);
      const w = parseNumber(tokens[1]);
      const h = parseNumber(tokens[2]);
      if (!origin || w == null || h == null) return { ok: false, message: "사용법: RECT x,y w h" };
      const s = store.scale;
      store.addRect(origin.x * s, origin.y * s, w * s, h * s);
      return { ok: true, message: `사각형 생성: (${origin.x},${origin.y}) ${w}×${h}m` };
    },
  },
  {
    name: "CIRCLE",
    aliases: ["C", "원"],
    hint: "CIRCLE cx,cy r — 원 (중심 + 반지름)",
    execute: (args, store) => {
      const tokens = args.trim().split(/\s+/);
      if (tokens.length < 2) return { ok: false, message: "사용법: CIRCLE cx,cy r" };
      const center = parseCoord(tokens[0]);
      const r = parseNumber(tokens[1]);
      if (!center || r == null) return { ok: false, message: "사용법: CIRCLE cx,cy r" };
      const s = store.scale;
      store.addCircle(center.x * s, center.y * s, r * s);
      return { ok: true, message: `원 생성: 중심(${center.x},${center.y}) 반지름 ${r}m` };
    },
  },
  {
    name: "POINT",
    aliases: ["P", "점"],
    hint: "POINT x,y — 점 추가",
    execute: (args, store) => {
      const coord = parseCoord(args.trim());
      if (!coord) return { ok: false, message: "사용법: POINT x,y" };
      const s = store.scale;
      store.addPoint(coord.x * s, coord.y * s);
      return { ok: true, message: `점 생성: (${coord.x},${coord.y})` };
    },
  },
  {
    name: "TEXT",
    aliases: ["T", "문자"],
    hint: 'TEXT x,y "내용" — 텍스트 추가',
    execute: (args, store) => {
      const match = args.trim().match(/^(\S+)\s+"?(.+?)"?$/);
      if (!match) return { ok: false, message: '사용법: TEXT x,y "내용"' };
      const coord = parseCoord(match[1]);
      const text = match[2];
      if (!coord) return { ok: false, message: "좌표 형식: x,y" };
      const s = store.scale;
      store.addText(coord.x * s, coord.y * s, text);
      return { ok: true, message: `텍스트 추가: "${text}"` };
    },
  },
  {
    name: "POLYGON",
    aliases: ["PG", "면"],
    hint: "POLYGON x1,y1 x2,y2 x3,y3 ... — 다각형",
    execute: (args, store) => {
      const tokens = args.trim().split(/\s+/);
      if (tokens.length < 3) return { ok: false, message: "최소 3개 좌표 필요" };
      const coords = tokens.map(parseCoord);
      if (coords.some((c) => !c)) return { ok: false, message: "좌표 형식 오류" };
      const s = store.scale;
      const ids = (coords as Array<{ x: number; y: number }>).map((c) =>
        store.addPoint(c.x * s, c.y * s),
      );
      store.addPolygon(ids);
      return { ok: true, message: `다각형 생성: ${ids.length}개 꼭짓점` };
    },
  },

  // ── 수정 ──
  {
    name: "MOVE",
    aliases: ["M", "이동"],
    hint: "MOVE dx,dy — 선택 요소 이동",
    execute: (args, store) => {
      const delta = parseCoord(args.trim());
      if (!delta) return { ok: false, message: "사용법: MOVE dx,dy" };
      if (!store.selectedId) return { ok: false, message: "요소를 먼저 선택하세요" };
      const s = store.scale;
      const id = store.selectedId;
      const dx = delta.x * s;
      const dy = delta.y * s;
      // 포인트 이동
      const pt = store.points.find((p) => p.id === id);
      if (pt) {
        store.movePoint(id, pt.x + dx, pt.y + dy);
        return { ok: true, message: `점 이동: (${delta.x},${delta.y})m` };
      }
      // 사각형 이동 — 삭제 후 재생성
      const rc = store.rects.find((r) => r.id === id);
      if (rc) {
        store.removeSelected();
        store.addRect(rc.x + dx, rc.y + dy, rc.width, rc.height);
        return { ok: true, message: `사각형 이동: (${delta.x},${delta.y})m` };
      }
      // 원 이동
      const ci = store.circles.find((c) => c.id === id);
      if (ci) {
        store.removeSelected();
        store.addCircle(ci.cx + dx, ci.cy + dy, ci.radius);
        return { ok: true, message: `원 이동: (${delta.x},${delta.y})m` };
      }
      // 텍스트 이동
      const tx = store.texts.find((t) => t.id === id);
      if (tx) {
        store.removeSelected();
        store.addText(tx.x + dx, tx.y + dy, tx.text);
        return { ok: true, message: `텍스트 이동: (${delta.x},${delta.y})m` };
      }
      return { ok: false, message: "이동할 수 없는 요소입니다" };
    },
  },
  {
    name: "COPY",
    aliases: ["CO", "복사"],
    hint: "COPY dx,dy — 선택 요소 복사 (오프셋)",
    execute: (args, store) => {
      const delta = parseCoord(args.trim());
      if (!delta) return { ok: false, message: "사용법: COPY dx,dy" };
      if (!store.selectedId) return { ok: false, message: "요소를 먼저 선택하세요" };
      const s = store.scale;
      const id = store.selectedId;
      const pt = store.points.find((p) => p.id === id);
      if (pt) {
        store.addPoint(pt.x + delta.x * s, pt.y + delta.y * s);
        return { ok: true, message: `복사: 오프셋 (${delta.x},${delta.y})m` };
      }
      const rc = store.rects.find((r) => r.id === id);
      if (rc) {
        store.addRect(rc.x + delta.x * s, rc.y + delta.y * s, rc.width, rc.height);
        return { ok: true, message: `사각형 복사: 오프셋 (${delta.x},${delta.y})m` };
      }
      const ci = store.circles.find((c) => c.id === id);
      if (ci) {
        store.addCircle(ci.cx + delta.x * s, ci.cy + delta.y * s, ci.radius);
        return { ok: true, message: `원 복사: 오프셋 (${delta.x},${delta.y})m` };
      }
      // 텍스트 복사
      const tx = store.texts.find((t) => t.id === id);
      if (tx) {
        store.addText(tx.x + delta.x * s, tx.y + delta.y * s, tx.text);
        return { ok: true, message: `텍스트 복사: 오프셋 (${delta.x},${delta.y})m` };
      }
      // 라인 복사 (양쪽 포인트 + 라인)
      const ln = store.lines.find((l) => l.id === id);
      if (ln) {
        const sp = store.points.find((p) => p.id === ln.startPointId);
        const ep = store.points.find((p) => p.id === ln.endPointId);
        if (sp && ep) {
          const newStart = store.addPoint(sp.x + delta.x * s, sp.y + delta.y * s);
          const newEnd = store.addPoint(ep.x + delta.x * s, ep.y + delta.y * s);
          store.addLine(newStart, newEnd);
          return { ok: true, message: `선 복사: 오프셋 (${delta.x},${delta.y})m` };
        }
      }
      // 폴리곤 복사 (모든 포인트 + 폴리곤)
      const pg = store.polygons.find((p) => p.id === id);
      if (pg) {
        const newIds = pg.pointIds.map((pid: string) => {
          const pt = store.points.find((p) => p.id === pid);
          return pt ? store.addPoint(pt.x + delta.x * s, pt.y + delta.y * s) : pid;
        });
        store.addPolygon(newIds);
        return { ok: true, message: `면 복사: 오프셋 (${delta.x},${delta.y})m` };
      }
      return { ok: false, message: "복사할 수 없는 요소입니다" };
    },
  },
  {
    name: "ERASE",
    aliases: ["E", "DEL", "삭제"],
    hint: "ERASE — 선택 요소 삭제",
    execute: (_args, store) => {
      const count = store.selectedIds.length || (store.selectedId ? 1 : 0);
      if (count === 0) return { ok: false, message: "요소를 먼저 선택하세요" };
      store.removeSelected();
      return { ok: true, message: `${count}개 요소 삭제 완료` };
    },
  },

  // ── 조회 ──
  {
    name: "DIST",
    aliases: ["DI", "거리"],
    hint: "DIST x1,y1 x2,y2 — 두 점 사이 거리",
    execute: (args, _store) => {
      const tokens = args.trim().split(/\s+/);
      if (tokens.length < 2) return { ok: false, message: "사용법: DIST x1,y1 x2,y2" };
      const p1 = parseCoord(tokens[0]);
      const p2 = parseCoord(tokens[1]);
      if (!p1 || !p2) return { ok: false, message: "좌표 형식 오류" };
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      return { ok: true, message: `거리: ${dist.toFixed(2)}m (Δx=${dx.toFixed(1)}, Δy=${dy.toFixed(1)})` };
    },
  },
  {
    name: "AREA",
    aliases: ["AA", "면적"],
    hint: "AREA — 선택된 폴리곤 면적 계산",
    execute: (_args, store) => {
      if (!store.selectedId) return { ok: false, message: "폴리곤을 먼저 선택하세요" };
      const pg = store.polygons.find((p) => p.id === store.selectedId);
      if (!pg) return { ok: false, message: "선택된 요소가 폴리곤이 아닙니다" };
      const pts = pg.pointIds
        .map((pid: string) => store.points.find((p) => p.id === pid))
        .filter(Boolean) as Array<{ x: number; y: number }>;
      if (pts.length < 3) return { ok: false, message: "유효하지 않은 폴리곤" };
      // Shoelace formula
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const j = (i + 1) % pts.length;
        area += pts[i].x * pts[j].y;
        area -= pts[j].x * pts[i].y;
      }
      area = Math.abs(area) / 2;
      const areaM2 = area / (store.scale * store.scale);
      return { ok: true, message: `면적: ${areaM2.toFixed(2)}m² (${(areaM2 / PYEONG_SQM).toFixed(1)}평)` };
    },
  },
  {
    name: "LIST",
    aliases: ["LS", "목록"],
    hint: "LIST — 전체 요소 목록",
    execute: (_args, store) => {
      const counts = [
        `점 ${store.points.length}`,
        `선 ${store.lines.length}`,
        `면 ${store.polygons.length}`,
        `사각형 ${store.rects.length}`,
        `원 ${store.circles.length}`,
        `문자 ${store.texts.length}`,
      ].join(", ");
      const selInfo = store.selectedIds.length > 0 ? ` | 선택: ${store.selectedIds.length}` : "";
      return { ok: true, message: `요소: ${counts}${selInfo}` };
    },
  },

  // ── 기타 ──
  {
    name: "UNDO",
    aliases: ["U"],
    hint: "UNDO — 실행 취소",
    execute: (_args, store) => {
      store.undo();
      return { ok: true, message: "실행 취소" };
    },
  },
  {
    name: "REDO",
    aliases: [],
    hint: "REDO — 다시 실행",
    execute: (_args, store) => {
      store.redo();
      return { ok: true, message: "다시 실행" };
    },
  },
  {
    name: "HELP",
    aliases: ["?", "도움말"],
    hint: "HELP — 명령어 목록",
    execute: () => {
      const list = COMMANDS.map(
        (c) => `${c.name}${c.aliases.length ? ` (${c.aliases.join("/")})` : ""}: ${c.hint}`,
      ).join("\n");
      return { ok: true, message: list };
    },
  },
];

// ── 공개 API ──

/** 명령 문자열 자동완성 후보 목록 반환. */
export function getCompletions(input: string): string[] {
  const upper = input.toUpperCase().trim();
  if (!upper) return COMMANDS.map((c) => c.name);
  return COMMANDS.filter(
    (c) =>
      c.name.startsWith(upper) ||
      c.aliases.some((a) => a.toUpperCase().startsWith(upper)),
  ).map((c) => c.name);
}

/** 명령 문자열 실행. */
export function executeCommand(input: string, store: StoreApi): CommandResult {
  const trimmed = input.trim();
  if (!trimmed) return { ok: false, message: "" };

  const spaceIdx = trimmed.indexOf(" ");
  const cmdToken = (spaceIdx === -1 ? trimmed : trimmed.slice(0, spaceIdx)).toUpperCase();
  const args = spaceIdx === -1 ? "" : trimmed.slice(spaceIdx + 1);

  const cmd = COMMANDS.find(
    (c) =>
      c.name === cmdToken ||
      c.aliases.some((a) => a.toUpperCase() === cmdToken),
  );

  if (!cmd) {
    return { ok: false, message: `알 수 없는 명령: ${cmdToken}. HELP로 목록 확인` };
  }

  return cmd.execute(args, store);
}

/** 특정 명령어의 파라미터 힌트 반환. */
export function getCommandHint(name: string): string {
  const upper = name.toUpperCase().trim();
  const cmd = COMMANDS.find(
    (c) => c.name === upper || c.aliases.some((a) => a.toUpperCase() === upper),
  );
  return cmd?.hint ?? "";
}

/** 모든 명령어 힌트 반환. */
export function getAllCommandHints(): string[] {
  return COMMANDS.map((c) => c.hint);
}
