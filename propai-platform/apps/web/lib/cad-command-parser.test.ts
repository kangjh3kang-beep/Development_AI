import { describe, it, expect, vi } from "vitest";
import {
  executeCommand,
  getCompletions,
  getCommandHint,
  getAllCommandHints,
  type CommandResult,
} from "./cad-command-parser";

/** 테스트용 mock store 생성. */
function createMockStore(overrides?: Partial<Parameters<typeof executeCommand>[1]>) {
  return {
    addPoint: vi.fn().mockReturnValue("pt-1"),
    addLine: vi.fn(),
    addRect: vi.fn(),
    addCircle: vi.fn(),
    addText: vi.fn(),
    addPolygon: vi.fn(),
    removeSelected: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    setSelected: vi.fn(),
    movePoint: vi.fn(),
    points: [] as Array<{ id: string; x: number; y: number }>,
    lines: [] as Array<{ id: string; startPointId: string; endPointId: string }>,
    polygons: [] as Array<{ id: string; pointIds: string[] }>,
    rects: [] as Array<{ id: string; x: number; y: number; width: number; height: number }>,
    circles: [] as Array<{ id: string; cx: number; cy: number; radius: number }>,
    texts: [] as Array<{ id: string; x: number; y: number; text: string }>,
    selectedId: null as string | null,
    selectedIds: [] as string[],
    scale: 10,
    ...overrides,
  };
}

describe("cad-command-parser", () => {
  // ── 그리기 명령 ──

  describe("LINE", () => {
    it("두 좌표로 선을 생성한다", () => {
      const store = createMockStore();
      const result = executeCommand("LINE 0,0 10,5", store);
      expect(result.ok).toBe(true);
      expect(store.addPoint).toHaveBeenCalledTimes(2);
      expect(store.addPoint).toHaveBeenCalledWith(0, 0);
      expect(store.addPoint).toHaveBeenCalledWith(100, 50);
      expect(store.addLine).toHaveBeenCalledTimes(1);
    });

    it("한글 alias '선' 으로 동작한다", () => {
      const store = createMockStore();
      const result = executeCommand("선 1,2 3,4", store);
      expect(result.ok).toBe(true);
    });

    it("좌표 부족 시 에러 반환", () => {
      const store = createMockStore();
      const result = executeCommand("LINE 0,0", store);
      expect(result.ok).toBe(false);
    });

    it("alias L 으로 동작한다", () => {
      const store = createMockStore();
      const result = executeCommand("L 5,5 10,10", store);
      expect(result.ok).toBe(true);
    });
  });

  describe("RECT", () => {
    it("좌상단 + 가로 세로로 사각형 생성", () => {
      const store = createMockStore();
      const result = executeCommand("RECT 1,2 8 4", store);
      expect(result.ok).toBe(true);
      expect(store.addRect).toHaveBeenCalledWith(10, 20, 80, 40);
    });

    it("파라미터 부족 시 에러", () => {
      const store = createMockStore();
      const result = executeCommand("RECT 1,2", store);
      expect(result.ok).toBe(false);
    });
  });

  describe("CIRCLE", () => {
    it("중심 + 반지름으로 원 생성", () => {
      const store = createMockStore();
      const result = executeCommand("CIRCLE 5,5 3", store);
      expect(result.ok).toBe(true);
      expect(store.addCircle).toHaveBeenCalledWith(50, 50, 30);
    });
  });

  describe("POINT", () => {
    it("좌표로 점 생성", () => {
      const store = createMockStore();
      const result = executeCommand("POINT 7,3", store);
      expect(result.ok).toBe(true);
      expect(store.addPoint).toHaveBeenCalledWith(70, 30);
    });

    it("한글 alias '점' 동작", () => {
      const store = createMockStore();
      const result = executeCommand("점 1,1", store);
      expect(result.ok).toBe(true);
    });
  });

  describe("TEXT", () => {
    it('좌표 + 따옴표 텍스트 추가', () => {
      const store = createMockStore();
      const result = executeCommand('TEXT 2,3 "거실"', store);
      expect(result.ok).toBe(true);
      expect(store.addText).toHaveBeenCalledWith(20, 30, "거실");
    });

    it("따옴표 없이도 동작", () => {
      const store = createMockStore();
      const result = executeCommand("TEXT 0,0 테스트", store);
      expect(result.ok).toBe(true);
      expect(store.addText).toHaveBeenCalledWith(0, 0, "테스트");
    });
  });

  describe("POLYGON", () => {
    it("3개 이상 좌표로 다각형 생성", () => {
      const store = createMockStore();
      const result = executeCommand("POLYGON 0,0 10,0 10,10", store);
      expect(result.ok).toBe(true);
      expect(store.addPoint).toHaveBeenCalledTimes(3);
      expect(store.addPolygon).toHaveBeenCalledTimes(1);
    });

    it("2개 좌표 시 에러", () => {
      const store = createMockStore();
      const result = executeCommand("POLYGON 0,0 10,0", store);
      expect(result.ok).toBe(false);
    });
  });

  // ── 수정 명령 ──

  describe("MOVE", () => {
    it("선택된 점 이동", () => {
      const store = createMockStore({
        selectedId: "pt-1",
        points: [{ id: "pt-1", x: 100, y: 100 }],
      });
      const result = executeCommand("MOVE 5,5", store);
      expect(result.ok).toBe(true);
      expect(store.movePoint).toHaveBeenCalledWith("pt-1", 150, 150);
    });

    it("선택 없이 이동 시 에러", () => {
      const store = createMockStore();
      const result = executeCommand("MOVE 1,1", store);
      expect(result.ok).toBe(false);
    });

    it("사각형 이동", () => {
      const store = createMockStore({
        selectedId: "rc-1",
        rects: [{ id: "rc-1", x: 10, y: 20, width: 80, height: 40 }],
      });
      const result = executeCommand("MOVE 2,3", store);
      expect(result.ok).toBe(true);
      expect(store.removeSelected).toHaveBeenCalled();
      expect(store.addRect).toHaveBeenCalledWith(30, 50, 80, 40);
    });
  });

  describe("COPY", () => {
    it("점 복사", () => {
      const store = createMockStore({
        selectedId: "pt-1",
        points: [{ id: "pt-1", x: 100, y: 100 }],
      });
      const result = executeCommand("COPY 5,0", store);
      expect(result.ok).toBe(true);
      expect(store.addPoint).toHaveBeenCalledWith(150, 100);
    });

    it("사각형 복사", () => {
      const store = createMockStore({
        selectedId: "rc-1",
        rects: [{ id: "rc-1", x: 10, y: 20, width: 80, height: 40 }],
      });
      const result = executeCommand("COPY 3,0", store);
      expect(result.ok).toBe(true);
      expect(store.addRect).toHaveBeenCalledWith(40, 20, 80, 40);
    });

    it("텍스트 복사", () => {
      const store = createMockStore({
        selectedId: "tx-1",
        texts: [{ id: "tx-1", x: 50, y: 60, text: "거실" }],
      });
      const result = executeCommand("COPY 1,1", store);
      expect(result.ok).toBe(true);
      expect(store.addText).toHaveBeenCalledWith(60, 70, "거실");
    });

    it("라인 복사", () => {
      const store = createMockStore({
        selectedId: "ln-1",
        lines: [{ id: "ln-1", startPointId: "pt-1", endPointId: "pt-2" }],
        points: [
          { id: "pt-1", x: 0, y: 0 },
          { id: "pt-2", x: 100, y: 0 },
        ],
      });
      store.addPoint.mockReturnValueOnce("pt-3").mockReturnValueOnce("pt-4");
      const result = executeCommand("COPY 0,5", store);
      expect(result.ok).toBe(true);
      expect(store.addPoint).toHaveBeenCalledWith(0, 50);
      expect(store.addPoint).toHaveBeenCalledWith(100, 50);
      expect(store.addLine).toHaveBeenCalledWith("pt-3", "pt-4");
    });
  });

  describe("ERASE", () => {
    it("선택 요소 삭제", () => {
      const store = createMockStore({ selectedId: "pt-1", selectedIds: ["pt-1"] });
      const result = executeCommand("ERASE", store);
      expect(result.ok).toBe(true);
      expect(store.removeSelected).toHaveBeenCalled();
      expect(result.message).toContain("1개");
    });

    it("다중 선택 삭제", () => {
      const store = createMockStore({ selectedId: "pt-2", selectedIds: ["pt-1", "pt-2", "rc-1"] });
      const result = executeCommand("ERASE", store);
      expect(result.ok).toBe(true);
      expect(result.message).toContain("3개");
    });

    it("선택 없이 삭제 시 에러", () => {
      const store = createMockStore();
      const result = executeCommand("ERASE", store);
      expect(result.ok).toBe(false);
    });
  });

  // ── 조회 명령 ──

  describe("DIST", () => {
    it("두 점 사이 거리 계산", () => {
      const store = createMockStore();
      const result = executeCommand("DIST 0,0 3,4", store);
      expect(result.ok).toBe(true);
      expect(result.message).toContain("5.00m");
    });
  });

  describe("AREA", () => {
    it("폴리곤 면적 계산 (Shoelace)", () => {
      const store = createMockStore({
        selectedId: "pg-1",
        polygons: [{ id: "pg-1", pointIds: ["p1", "p2", "p3", "p4"] }],
        points: [
          { id: "p1", x: 0, y: 0 },
          { id: "p2", x: 100, y: 0 },
          { id: "p3", x: 100, y: 100 },
          { id: "p4", x: 0, y: 100 },
        ],
      });
      const result = executeCommand("AREA", store);
      expect(result.ok).toBe(true);
      // 100x100 px / (10*10) = 100 m²
      expect(result.message).toContain("100.00m²");
    });
  });

  describe("LIST", () => {
    it("요소 카운트 반환", () => {
      const store = createMockStore({
        points: [{ id: "p1", x: 0, y: 0 }],
        rects: [{ id: "r1", x: 0, y: 0, width: 10, height: 10 }],
      });
      const result = executeCommand("LIST", store);
      expect(result.ok).toBe(true);
      expect(result.message).toContain("점 1");
      expect(result.message).toContain("사각형 1");
    });

    it("선택 요소가 있으면 선택 개수도 표시", () => {
      const store = createMockStore({
        points: [{ id: "p1", x: 0, y: 0 }],
        selectedIds: ["p1", "r1"],
      });
      const result = executeCommand("LIST", store);
      expect(result.ok).toBe(true);
      expect(result.message).toContain("선택: 2");
    });

    it("선택 없으면 선택 정보 미표시", () => {
      const store = createMockStore({
        points: [{ id: "p1", x: 0, y: 0 }],
        selectedIds: [],
      });
      const result = executeCommand("LIST", store);
      expect(result.ok).toBe(true);
      expect(result.message).not.toContain("선택:");
    });
  });

  // ── 기타 ──

  describe("UNDO/REDO", () => {
    it("UNDO 호출", () => {
      const store = createMockStore();
      executeCommand("UNDO", store);
      expect(store.undo).toHaveBeenCalled();
    });

    it("REDO 호출", () => {
      const store = createMockStore();
      executeCommand("REDO", store);
      expect(store.redo).toHaveBeenCalled();
    });
  });

  describe("HELP", () => {
    it("명령어 목록 반환", () => {
      const store = createMockStore();
      const result = executeCommand("HELP", store);
      expect(result.ok).toBe(true);
      expect(result.message).toContain("LINE");
      expect(result.message).toContain("RECT");
    });
  });

  describe("알 수 없는 명령", () => {
    it("에러 메시지 반환", () => {
      const store = createMockStore();
      const result = executeCommand("INVALIDCMD", store);
      expect(result.ok).toBe(false);
      expect(result.message).toContain("알 수 없는 명령");
    });

    it("빈 문자열", () => {
      const store = createMockStore();
      const result = executeCommand("", store);
      expect(result.ok).toBe(false);
    });
  });

  // ── 자동완성 ──

  describe("getCompletions", () => {
    it("빈 입력 시 전체 명령어 반환", () => {
      const list = getCompletions("");
      expect(list.length).toBeGreaterThan(10);
    });

    it("접두사 매칭", () => {
      const list = getCompletions("LI");
      expect(list).toContain("LINE");
      expect(list).toContain("LIST");
    });

    it("한글 alias 매칭", () => {
      const list = getCompletions("선");
      expect(list).toContain("LINE");
    });

    it("대소문자 무관", () => {
      const list = getCompletions("rect");
      expect(list).toContain("RECT");
    });
  });

  describe("getCommandHint", () => {
    it("명령 이름으로 힌트 반환", () => {
      const hint = getCommandHint("LINE");
      expect(hint).toContain("x1,y1");
    });

    it("alias로 힌트 반환", () => {
      const hint = getCommandHint("L");
      expect(hint).toContain("LINE");
    });

    it("없는 명령 시 빈 문자열", () => {
      const hint = getCommandHint("NOTEXIST");
      expect(hint).toBe("");
    });
  });

  describe("getAllCommandHints", () => {
    it("전체 힌트 배열 반환", () => {
      const hints = getAllCommandHints();
      expect(hints.length).toBeGreaterThan(10);
      expect(hints[0]).toContain("LINE");
    });
  });
});
