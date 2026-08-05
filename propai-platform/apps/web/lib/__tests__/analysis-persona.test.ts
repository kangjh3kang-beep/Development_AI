/**
 * 관점(페르소나)별 스토리라인 계약.
 *
 * ★이 기능이 깨지는 방식은 "안 보이는 것"이다 — 순서를 바꾸다 섹션 하나가 목록에서 빠지면
 *   그 관점을 고른 사용자에게만 조용히 사라진다. 그래서 순서 정의를 **자유 목록이 아니라
 *   전수 커버 계약**으로 잠근다.
 */
import { describe, it, expect } from "vitest";
import {
  PERSONAS, NEUTRAL_SECTION_ORDER, sectionOrderFor, isExpandedFor, personaByKey,
} from "@/lib/analysis-persona";

describe("중립(기본) 동작 — 무회귀", () => {
  it("관점을 안 고르면 종전과 정확히 같은 순서", () => {
    expect(sectionOrderFor(null)).toEqual([...NEUTRAL_SECTION_ORDER]);
    expect(sectionOrderFor(undefined)).toEqual([...NEUTRAL_SECTION_ORDER]);
  });

  it("모르는 관점 키는 중립으로 떨어진다 — 저장된 옛 값이 화면을 깨뜨리지 않는다", () => {
    expect(sectionOrderFor("not_a_persona")).toEqual([...NEUTRAL_SECTION_ORDER]);
    expect(personaByKey("not_a_persona")).toBeNull();
  });

  it("중립에서는 펼침 기본값을 관점이 건드리지 않는다(null = 소비처 기본값 유지)", () => {
    expect(isExpandedFor(null, "effective-far")).toBeNull();
    expect(isExpandedFor("not_a_persona", "land-price")).toBeNull();
  });
});

describe("★섹션 전수 커버 — 관점을 골랐다고 섹션이 사라지면 안 된다", () => {
  it.each(PERSONAS.map((p) => [p.key, p] as const))("%s: 모든 섹션이 정확히 한 번씩", (_key, spec) => {
    const order = sectionOrderFor(spec.key);
    expect([...order].sort()).toEqual([...NEUTRAL_SECTION_ORDER].sort());
    expect(new Set(order).size).toBe(order.length);
  });

  it("강조 순서에 명시되지 않은 섹션은 뒤에 중립 순서로 붙는다", () => {
    // designer는 시세·실거래·분양가를 명시하지 않는다 — 그래도 사라지지 않아야 한다.
    const order = sectionOrderFor("designer");
    expect(order).toContain("land-price");
    expect(order).toContain("transactions");
    expect(order).toContain("sale-price");
    // 뒤에 붙은 것들끼리는 중립 순서를 유지한다.
    const tail = order.filter((id) => !PERSONAS[0].order.includes(id));
    const neutralTail = NEUTRAL_SECTION_ORDER.filter((id) => tail.includes(id));
    expect(tail).toEqual(neutralTail);
  });

  it("정의에 없는 섹션 id를 order에 넣어도 결과를 오염시키지 않는다", () => {
    // 오타·삭제된 섹션이 남아 있어도 렌더 대상은 실제 섹션 집합을 벗어나지 않는다.
    for (const spec of PERSONAS) {
      for (const id of sectionOrderFor(spec.key)) {
        expect(NEUTRAL_SECTION_ORDER).toContain(id);
      }
    }
  });
});

describe("관점 정의 자체의 계약", () => {
  it("백엔드 페르소나 레지스트리와 같은 키를 쓴다 — 같은 개념에 두 이름을 만들지 않는다", () => {
    const keys = PERSONAS.map((p) => p.key);
    for (const k of ["designer", "developer", "constructor"]) {
      expect(keys).toContain(k);
    }
    // 금융은 아직 백엔드 러너가 없는 화면 전용 축이다(신설 합의).
    expect(keys).toContain("finance");
  });

  it("라벨·요약문이 비어 있지 않다", () => {
    for (const spec of PERSONAS) {
      expect(spec.label.trim().length).toBeGreaterThan(0);
      expect(spec.summary.trim().length).toBeGreaterThan(10);
    }
  });

  it("펼침 대상은 그 관점의 강조 순서 앞머리에 있다 — 접힌 걸 먼저 보라고 하지 않는다", () => {
    for (const spec of PERSONAS) {
      expect(spec.expanded.length).toBeGreaterThan(0);
      for (const id of spec.expanded) {
        expect(spec.order.indexOf(id)).toBeGreaterThanOrEqual(0);
        expect(spec.order.indexOf(id)).toBeLessThan(3);
      }
    }
  });

  it("★이 보고서에 없는 것을 요구하는 관점은 그 사실을 명시한다(무날조)", () => {
    // 시공=공사비·공정, 금융=수지·LTV는 이 보고서 범위 밖이다. 이름만 붙이고 침묵하면
    // 사용자는 없는 것을 있다고 오해한다.
    for (const key of ["constructor", "finance"]) {
      const spec = personaByKey(key)!;
      expect(spec.outOfScope).toBeDefined();
      expect(spec.outOfScope!.what.trim().length).toBeGreaterThan(0);
      expect(spec.outOfScope!.where.trim().length).toBeGreaterThan(0);
    }
  });

  it("관점마다 순서가 실제로 다르다 — 이름만 다른 껍데기가 아니다", () => {
    const signatures = new Set(PERSONAS.map((p) => sectionOrderFor(p.key).join(">")));
    expect(signatures.size).toBe(PERSONAS.length);
    for (const spec of PERSONAS) {
      expect(sectionOrderFor(spec.key)).not.toEqual([...NEUTRAL_SECTION_ORDER]);
    }
  });
});

describe("합의된 강조 순서(사용자 확인본) 고정", () => {
  it.each([
    ["designer", "effective-far"],
    ["developer", "sale-price"],
    ["constructor", "supply-area"],
    ["finance", "land-price"],
  ])("%s의 첫 섹션은 %s", (key, first) => {
    expect(sectionOrderFor(key)[0]).toBe(first);
  });
});
