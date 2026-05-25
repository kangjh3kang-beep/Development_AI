import { describe, it, expect, beforeEach } from "vitest";
import { useCadStore } from "@/store/use-cad-store";

/**
 * CAD Store 멀티셀렉트 기능 시뮬레이션 테스트.
 *
 * 전체 워크플로우를 실제 Zustand store로 검증한다:
 * - 단일 선택 / 다중 선택 / 토글 / 전체 해제
 * - 다중 삭제 (점, 선, 사각형, 원, 텍스트 혼합)
 * - Undo/Redo와 멀티셀렉트 연동
 * - loadDesignPayload / resetCanvas 시 선택 초기화
 */

function resetStore() {
  const s = useCadStore.getState();
  s.resetCanvas();
  // undo 스택도 클리어
  useCadStore.setState({ undoStack: [], redoStack: [] });
}

describe("use-cad-store 멀티셀렉트", () => {
  beforeEach(() => {
    resetStore();
  });

  // ── 기본 선택 ──

  describe("setSelected (단일 선택)", () => {
    it("selectedId와 selectedIds가 동기화된다", () => {
      const s = useCadStore.getState();
      s.addPoint(100, 100); // pt-N
      const state = useCadStore.getState();
      const ptId = state.points[0].id;

      s.setSelected(ptId);
      const after = useCadStore.getState();
      expect(after.selectedId).toBe(ptId);
      expect(after.selectedIds).toEqual([ptId]);
    });

    it("null 선택 시 모두 초기화된다", () => {
      const s = useCadStore.getState();
      s.addPoint(100, 100);
      const ptId = useCadStore.getState().points[0].id;
      s.setSelected(ptId);
      s.setSelected(null);
      const after = useCadStore.getState();
      expect(after.selectedId).toBeNull();
      expect(after.selectedIds).toEqual([]);
    });
  });

  // ── 멀티 선택 ──

  describe("toggleSelected (Shift+클릭)", () => {
    it("추가 선택", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addPoint(50, 50);
      const [pt1, pt2] = useCadStore.getState().points;

      s.toggleSelected(pt1.id);
      s.toggleSelected(pt2.id);

      const after = useCadStore.getState();
      expect(after.selectedIds).toContain(pt1.id);
      expect(after.selectedIds).toContain(pt2.id);
      expect(after.selectedIds.length).toBe(2);
      expect(after.selectedId).toBe(pt2.id); // 마지막 선택
    });

    it("토글 해제", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addPoint(50, 50);
      const [pt1, pt2] = useCadStore.getState().points;

      s.toggleSelected(pt1.id);
      s.toggleSelected(pt2.id);
      s.toggleSelected(pt1.id); // 해제

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([pt2.id]);
      expect(after.selectedId).toBe(pt2.id);
    });

    it("전부 토글 해제하면 selectedId도 null", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      const ptId = useCadStore.getState().points[0].id;

      s.toggleSelected(ptId);
      s.toggleSelected(ptId); // 해제

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
    });
  });

  // ── clearSelection ──

  describe("clearSelection", () => {
    it("모든 선택 해제", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addPoint(50, 50);
      const [pt1, pt2] = useCadStore.getState().points;

      s.toggleSelected(pt1.id);
      s.toggleSelected(pt2.id);
      s.clearSelection();

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
    });
  });

  // ── 다중 삭제 ──

  describe("removeSelected (다중 삭제)", () => {
    it("혼합 요소 일괄 삭제 (점 + 사각형 + 원)", () => {
      const s = useCadStore.getState();
      const ptId = s.addPoint(10, 10);
      s.addRect(0, 0, 100, 50);
      s.addCircle(200, 200, 30);

      const state = useCadStore.getState();
      const rcId = state.rects[0].id;
      const ciId = state.circles[0].id;

      // 3개 모두 선택
      s.toggleSelected(ptId);
      s.toggleSelected(rcId);
      s.toggleSelected(ciId);
      expect(useCadStore.getState().selectedIds.length).toBe(3);

      // 일괄 삭제
      s.removeSelected();

      const after = useCadStore.getState();
      expect(after.points.length).toBe(0);
      expect(after.rects.length).toBe(0);
      expect(after.circles.length).toBe(0);
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
    });

    it("선 삭제 시 관련 포인트도 연쇄 제거", () => {
      const s = useCadStore.getState();
      const p1 = s.addPoint(0, 0);
      const p2 = s.addPoint(100, 0);
      s.addLine(p1, p2);
      const lnId = useCadStore.getState().lines[0].id;

      // 선만 선택하여 삭제
      s.setSelected(lnId);
      s.removeSelected();

      const after = useCadStore.getState();
      expect(after.lines.length).toBe(0);
      // 포인트는 남아있어야 함 (선만 삭제)
      expect(after.points.length).toBe(2);
    });

    it("포인트 삭제 시 해당 포인트를 참조하는 선도 제거", () => {
      const s = useCadStore.getState();
      const p1 = s.addPoint(0, 0);
      const p2 = s.addPoint(100, 0);
      s.addLine(p1, p2);

      // p1 선택하여 삭제
      s.setSelected(p1);
      s.removeSelected();

      const after = useCadStore.getState();
      expect(after.points.length).toBe(1);
      expect(after.lines.length).toBe(0); // p1을 참조하는 선도 제거
    });

    it("텍스트 다중 삭제", () => {
      const s = useCadStore.getState();
      s.addText(10, 10, "거실");
      s.addText(100, 100, "주방");
      s.addText(200, 200, "침실");

      const state = useCadStore.getState();
      const [t1, t2] = state.texts;

      s.toggleSelected(t1.id);
      s.toggleSelected(t2.id);
      s.removeSelected();

      const after = useCadStore.getState();
      expect(after.texts.length).toBe(1);
      expect(after.texts[0].text).toBe("침실");
    });

    it("빈 선택 시 아무 일도 안 일어남", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.clearSelection();
      s.removeSelected();

      expect(useCadStore.getState().points.length).toBe(1);
    });
  });

  // ── Undo/Redo 연동 ──

  describe("Undo/Redo + 멀티셀렉트", () => {
    it("다중 삭제 후 Undo로 복원", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addRect(0, 0, 100, 50);
      s.addCircle(200, 200, 30);

      const state = useCadStore.getState();
      const ptId = state.points[0].id;
      const rcId = state.rects[0].id;
      const ciId = state.circles[0].id;

      s.toggleSelected(ptId);
      s.toggleSelected(rcId);
      s.toggleSelected(ciId);
      s.removeSelected();

      expect(useCadStore.getState().points.length).toBe(0);
      expect(useCadStore.getState().rects.length).toBe(0);
      expect(useCadStore.getState().circles.length).toBe(0);

      // Undo → 복원
      s.undo();

      const restored = useCadStore.getState();
      expect(restored.points.length).toBe(1);
      expect(restored.rects.length).toBe(1);
      expect(restored.circles.length).toBe(1);
    });

    it("Undo 후 Redo로 재삭제", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      const ptId = useCadStore.getState().points[0].id;

      s.setSelected(ptId);
      s.removeSelected();

      expect(useCadStore.getState().points.length).toBe(0);

      s.undo();
      expect(useCadStore.getState().points.length).toBe(1);

      s.redo();
      expect(useCadStore.getState().points.length).toBe(0);
    });
  });

  // ── 도구 전환 시 선택 초기화 ──

  describe("setTool 시 선택 초기화", () => {
    it("도구 변경 시 selectedIds도 초기화", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addPoint(50, 50);
      const [pt1, pt2] = useCadStore.getState().points;

      s.toggleSelected(pt1.id);
      s.toggleSelected(pt2.id);
      expect(useCadStore.getState().selectedIds.length).toBe(2);

      s.setTool("line");

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
      expect(after.tool).toBe("line");
    });
  });

  // ── resetCanvas ──

  describe("resetCanvas 시 선택 초기화", () => {
    it("캔버스 리셋 시 selectedIds도 초기화", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      s.addRect(0, 0, 100, 50);
      const ptId = useCadStore.getState().points[0].id;
      const rcId = useCadStore.getState().rects[0].id;

      s.toggleSelected(ptId);
      s.toggleSelected(rcId);
      s.resetCanvas();

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
      expect(after.points.length).toBe(0);
    });
  });

  // ── loadDesignPayload ──

  describe("loadDesignPayload 시 선택 초기화", () => {
    it("페이로드 로드 시 selectedIds 초기화", () => {
      const s = useCadStore.getState();
      s.addPoint(10, 10);
      const ptId = useCadStore.getState().points[0].id;
      s.setSelected(ptId);

      s.loadDesignPayload({
        points: [{ id: "new-pt", x: 50, y: 50 }],
        lines: [],
        surfaces: [],
        rects: [],
        circles: [],
        texts: [],
        floor_count: 5,
        building_height_m: 15,
        scale: 10,
      });

      const after = useCadStore.getState();
      expect(after.selectedIds).toEqual([]);
      expect(after.selectedId).toBeNull();
      expect(after.points.length).toBe(1);
      expect(after.floorCount).toBe(5);
    });
  });

  // ── 복합 시나리오: 실제 사용 워크플로우 시뮬레이션 ──

  describe("실제 워크플로우 시뮬레이션", () => {
    it("건축 설계 워크플로우: 도형 생성 → 멀티셀렉트 → 부분 삭제 → Undo", () => {
      const s = useCadStore.getState();

      // 1. 건물 외곽 사각형
      s.addRect(100, 100, 400, 300);

      // 2. 내부 파티션 선
      const p1 = s.addPoint(300, 100);
      const p2 = s.addPoint(300, 400);
      s.addLine(p1, p2);

      // 3. 기둥 원
      s.addCircle(200, 200, 15);
      s.addCircle(400, 200, 15);

      // 4. 라벨 텍스트
      s.addText(150, 250, "거실");
      s.addText(350, 250, "주방");

      const state1 = useCadStore.getState();
      expect(state1.rects.length).toBe(1);
      expect(state1.lines.length).toBe(1);
      expect(state1.circles.length).toBe(2);
      expect(state1.texts.length).toBe(2);

      // 5. Shift+클릭으로 기둥 2개 + 주방 텍스트 선택
      const ci1 = state1.circles[0].id;
      const ci2 = state1.circles[1].id;
      const txKitchen = state1.texts[1].id;

      s.toggleSelected(ci1);
      s.toggleSelected(ci2);
      s.toggleSelected(txKitchen);

      expect(useCadStore.getState().selectedIds.length).toBe(3);

      // 6. 일괄 삭제
      s.removeSelected();

      const state2 = useCadStore.getState();
      expect(state2.circles.length).toBe(0);
      expect(state2.texts.length).toBe(1);
      expect(state2.texts[0].text).toBe("거실");
      expect(state2.rects.length).toBe(1); // 외곽은 유지
      expect(state2.lines.length).toBe(1); // 파티션 유지

      // 7. Undo → 삭제 전 상태 복원
      s.undo();

      const state3 = useCadStore.getState();
      expect(state3.circles.length).toBe(2);
      expect(state3.texts.length).toBe(2);

      // 8. 건물 외곽만 선택하여 단일 삭제
      const rcId = state3.rects[0].id;
      s.setSelected(rcId);
      expect(useCadStore.getState().selectedIds).toEqual([rcId]);
      s.removeSelected();

      const state4 = useCadStore.getState();
      expect(state4.rects.length).toBe(0);
      expect(state4.circles.length).toBe(2); // 다른 요소는 유지
    });

    it("전체 선택 → 전체 삭제 워크플로우", () => {
      const s = useCadStore.getState();

      s.addPoint(0, 0);
      s.addRect(10, 10, 50, 50);
      s.addCircle(100, 100, 20);
      s.addText(200, 200, "테스트");

      const state = useCadStore.getState();
      const allIds = [
        state.points[0].id,
        state.rects[0].id,
        state.circles[0].id,
        state.texts[0].id,
      ];

      // 전부 Shift+클릭
      for (const id of allIds) {
        s.toggleSelected(id);
      }
      expect(useCadStore.getState().selectedIds.length).toBe(4);

      s.removeSelected();

      const after = useCadStore.getState();
      expect(after.points.length).toBe(0);
      expect(after.rects.length).toBe(0);
      expect(after.circles.length).toBe(0);
      expect(after.texts.length).toBe(0);
    });
  });
});
