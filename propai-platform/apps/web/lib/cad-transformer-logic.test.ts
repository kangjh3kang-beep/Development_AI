import { describe, it, expect } from "vitest";

/**
 * CadCanvasInner의 Transformer 연동 로직 시뮬레이션 테스트.
 *
 * Konva Canvas는 jsdom에서 렌더링 불가하므로,
 * selectedSet / registerRef / Transformer 노드 동기화 로직을 순수 함수로 추출하여 검증한다.
 */

// ── selectedSet 생성 로직 (useMemo) ──

function createSelectedSet(selectedIds: string[]): Set<string> {
  return new Set(selectedIds);
}

// ── shapeRefs 관리 로직 ──

function registerRef(
  refs: Map<string, { id: string }>,
  id: string,
  node: { id: string } | null,
) {
  if (node) {
    refs.set(id, node);
  } else {
    refs.delete(id);
  }
}

// ── Transformer 노드 수집 로직 ──

function collectTransformerNodes(
  selectedIds: string[],
  shapeRefs: Map<string, { id: string }>,
): Array<{ id: string }> {
  const nodes: Array<{ id: string }> = [];
  for (const id of selectedIds) {
    const node = shapeRefs.get(id);
    if (node) nodes.push(node);
  }
  return nodes;
}

// ── Shift+클릭 핸들러 로직 ──

function handleShapeClick(
  shiftKey: boolean,
  id: string,
  setSelected: (id: string) => void,
  toggleSelected: (id: string) => void,
) {
  if (shiftKey) {
    toggleSelected(id);
  } else {
    setSelected(id);
  }
}

describe("CadCanvasInner Transformer 로직 시뮬레이션", () => {
  // ── selectedSet ──

  describe("selectedSet 생성", () => {
    it("빈 배열 → 빈 Set", () => {
      const set = createSelectedSet([]);
      expect(set.size).toBe(0);
    });

    it("중복 없는 Set 생성", () => {
      const set = createSelectedSet(["rc-1", "ci-1", "tx-1"]);
      expect(set.size).toBe(3);
      expect(set.has("rc-1")).toBe(true);
      expect(set.has("ci-1")).toBe(true);
      expect(set.has("tx-1")).toBe(true);
      expect(set.has("rc-2")).toBe(false);
    });

    it("선택 상태에 따라 도형 스타일 결정", () => {
      const set = createSelectedSet(["rc-1", "ci-2"]);
      const SELECTED_COLOR = "#2563eb";
      const NORMAL_COLOR = "#333333";

      // 선택된 도형
      const rc1Stroke = set.has("rc-1") ? SELECTED_COLOR : NORMAL_COLOR;
      expect(rc1Stroke).toBe(SELECTED_COLOR);

      // 선택 안 된 도형
      const rc2Stroke = set.has("rc-2") ? SELECTED_COLOR : NORMAL_COLOR;
      expect(rc2Stroke).toBe(NORMAL_COLOR);
    });
  });

  // ── shapeRefs 관리 ──

  describe("shapeRefs 등록/해제", () => {
    it("ref 등록", () => {
      const refs = new Map<string, { id: string }>();
      const mockNode = { id: "rc-1" };
      registerRef(refs, "rc-1", mockNode);
      expect(refs.has("rc-1")).toBe(true);
      expect(refs.get("rc-1")).toBe(mockNode);
    });

    it("ref 해제 (null 전달)", () => {
      const refs = new Map<string, { id: string }>();
      refs.set("rc-1", { id: "rc-1" });
      registerRef(refs, "rc-1", null);
      expect(refs.has("rc-1")).toBe(false);
    });

    it("여러 도형 ref 동시 관리", () => {
      const refs = new Map<string, { id: string }>();
      registerRef(refs, "rc-1", { id: "rc-1" });
      registerRef(refs, "ci-1", { id: "ci-1" });
      registerRef(refs, "tx-1", { id: "tx-1" });
      expect(refs.size).toBe(3);

      registerRef(refs, "ci-1", null); // 원 제거
      expect(refs.size).toBe(2);
      expect(refs.has("ci-1")).toBe(false);
    });
  });

  // ── Transformer 노드 수집 ──

  describe("Transformer 노드 동기화", () => {
    it("선택된 ID에 해당하는 노드만 수집", () => {
      const refs = new Map<string, { id: string }>();
      refs.set("rc-1", { id: "rc-1" });
      refs.set("rc-2", { id: "rc-2" });
      refs.set("ci-1", { id: "ci-1" });

      const nodes = collectTransformerNodes(["rc-1", "ci-1"], refs);
      expect(nodes.length).toBe(2);
      expect(nodes.map((n) => n.id)).toEqual(["rc-1", "ci-1"]);
    });

    it("삭제된 도형의 ref가 없으면 건너뜀", () => {
      const refs = new Map<string, { id: string }>();
      refs.set("rc-1", { id: "rc-1" });
      // rc-2는 삭제되어 ref 없음

      const nodes = collectTransformerNodes(["rc-1", "rc-2"], refs);
      expect(nodes.length).toBe(1);
    });

    it("빈 선택 → 빈 노드 배열", () => {
      const refs = new Map<string, { id: string }>();
      refs.set("rc-1", { id: "rc-1" });

      const nodes = collectTransformerNodes([], refs);
      expect(nodes.length).toBe(0);
    });

    it("전체 선택 → 모든 노드 수집", () => {
      const refs = new Map<string, { id: string }>();
      const ids = ["rc-1", "rc-2", "ci-1", "tx-1"];
      for (const id of ids) refs.set(id, { id });

      const nodes = collectTransformerNodes(ids, refs);
      expect(nodes.length).toBe(4);
    });
  });

  // ── Shift+클릭 핸들러 ──

  describe("Shift+클릭 핸들러", () => {
    it("일반 클릭 → setSelected 호출", () => {
      let calledWith = "";
      const setSelected = (id: string) => { calledWith = id; };
      const toggleSelected = () => { /* not called */ };

      handleShapeClick(false, "rc-1", setSelected, toggleSelected);
      expect(calledWith).toBe("rc-1");
    });

    it("Shift+클릭 → toggleSelected 호출", () => {
      let calledWith = "";
      const setSelected = () => { /* not called */ };
      const toggleSelected = (id: string) => { calledWith = id; };

      handleShapeClick(true, "rc-1", setSelected, toggleSelected);
      expect(calledWith).toBe("rc-1");
    });
  });

  // ── 복합 시나리오 ──

  describe("Transformer 전체 워크플로우 시뮬레이션", () => {
    it("도형 생성 → ref 등록 → 멀티셀렉트 → Transformer 노드 → 삭제 → ref 정리", () => {
      const refs = new Map<string, { id: string }>();

      // 1. 도형 3개 생성 & ref 등록
      registerRef(refs, "rc-1", { id: "rc-1" });
      registerRef(refs, "ci-1", { id: "ci-1" });
      registerRef(refs, "tx-1", { id: "tx-1" });
      expect(refs.size).toBe(3);

      // 2. 멀티셀렉트 → selectedSet 생성
      const selectedIds = ["rc-1", "ci-1"];
      const set = createSelectedSet(selectedIds);
      expect(set.has("rc-1")).toBe(true);
      expect(set.has("tx-1")).toBe(false);

      // 3. Transformer 노드 수집
      const nodes = collectTransformerNodes(selectedIds, refs);
      expect(nodes.length).toBe(2);

      // 4. 선택된 도형 삭제 → ref 정리
      for (const id of selectedIds) {
        registerRef(refs, id, null);
      }
      expect(refs.size).toBe(1);
      expect(refs.has("tx-1")).toBe(true);

      // 5. 선택 해제 후 Transformer 노드 재수집
      const emptyNodes = collectTransformerNodes([], refs);
      expect(emptyNodes.length).toBe(0);
    });
  });
});
