/**
 * 내비게이션 i18n 전수 커버리지 — **목록이 아니라 레지스트리에서 파생한다**(2026-08-16).
 *
 * ★왜: `route-registry.ts` 의 라벨이 한국어 하드코딩이라 `/en`·`/zh-CN` 사용자에게
 *   하위 내비게이션 전체가 한국어로 나왔다. 번역을 붙였지만, **다음에 라우트를 추가하는
 *   사람이 번역을 잊으면 같은 결함이 조용히 되돌아온다.**
 *
 * ★그래서 사람이 센 목록을 쓰지 않는다. `PRIMARY_ROUTE_REGISTRY` 와 `PRIMARY_NAV_SECTIONS`
 *   에서 **파생**해 전수 검사하므로, 새 항목은 번역 없이는 여기서 빨강이 된다.
 *   (이 저장소가 반복해 데인 형태: 사람이 센 목록 5 vs 실제 11 — CLAUDE.md §A.4)
 *
 * ★공허 진리 방지: 대상 개수의 하한을 먼저 단언한다. 레지스트리가 비면 "위반 0" 이
 *   참이 되는데 그건 검사가 죽은 것이지 통과가 아니다.
 */
import { describe, expect, it } from "vitest";

import { LIFECYCLE_STAGES, STAGE_META } from "@/lib/lifecycle-stages";
import {
  NAV_ITEM_LABELS,
  NAV_SECTION_TITLES,
  STAGE_LABELS,
  resolveNavLabel,
  resolveNavSectionTitle,
  resolveStageLabel,
  type TranslatedLocale,
} from "@/lib/navigation/nav-i18n";
import {
  buildPrimaryRegistrySections,
  PRIMARY_NAV_SECTIONS,
  PRIMARY_ROUTE_REGISTRY,
} from "@/lib/navigation/route-registry";

const LOCALES: TranslatedLocale[] = ["en", "zh-CN"];
const HANGUL = /[ㄱ-ㆎ가-힣]/;

describe("내비게이션 i18n 커버리지", () => {
  it("전제 — 검사 대상이 실제로 존재한다(공허 진리 방지)", () => {
    expect(PRIMARY_ROUTE_REGISTRY.length).toBeGreaterThan(20);
    expect(PRIMARY_NAV_SECTIONS.length).toBeGreaterThan(3);
  });

  it.each(LOCALES)("%s — 모든 레지스트리 항목에 번역이 있다", (loc) => {
    const missing = PRIMARY_ROUTE_REGISTRY.filter(
      (item) => !NAV_ITEM_LABELS[item.id]?.[loc],
    ).map((item) => `${item.id}("${item.label}")`);

    expect(
      missing,
      `${loc} 번역 누락 ${missing.length}건 — lib/navigation/nav-i18n.ts 에 추가할 것`,
    ).toEqual([]);
  });

  it.each(LOCALES)("%s — 모든 섹션 제목에 번역이 있다", (loc) => {
    const missing = PRIMARY_NAV_SECTIONS.filter(
      (s) => !NAV_SECTION_TITLES[s.id]?.[loc],
    ).map((s) => `${s.id}("${s.title}")`);

    expect(missing, `${loc} 섹션 제목 누락 ${missing.length}건`).toEqual([]);
  });

  /**
   * ★여기가 진짜 잠금이다 — 사전에 키가 **있다**가 아니라, 실제로 빌드된 트리에
   *   **한글이 남아 있지 않다**를 본다. 사전만 검사하면 리졸버 배선을 끊어도 통과한다
   *   (이 저장소가 반복해 뚫린 "정의만 하고 소비처 0" 형태 — CLAUDE.md 검증 규율).
   */
  it.each(LOCALES)("%s — 빌드된 내비 트리에 한글이 남지 않는다", (loc) => {
    const sections = buildPrimaryRegistrySections(loc);
    expect(sections.length, "섹션이 0개 — 검사가 공허하다").toBeGreaterThan(3);

    const leaked: string[] = [];
    let visited = 0;
    const walk = (nodes: { id: string; label: string; children?: unknown[] }[]) => {
      for (const n of nodes) {
        visited += 1;
        if (HANGUL.test(n.label)) leaked.push(`${n.id}: "${n.label}"`);
        if (Array.isArray(n.children)) {
          walk(n.children as { id: string; label: string; children?: unknown[] }[]);
        }
      }
    };
    for (const s of sections) {
      if (HANGUL.test(s.title)) leaked.push(`[섹션] ${s.id}: "${s.title}"`);
      walk(s.items as { id: string; label: string; children?: unknown[] }[]);
    }

    // 대상이 실제로 순회됐는가 — 0개를 돌고 "누출 0" 이면 무의미하다.
    expect(visited, "순회한 항목이 0개 — 검사가 공허하다").toBeGreaterThan(20);
    expect(leaked, `${loc} 화면에 한국어가 남았다 ${leaked.length}건`).toEqual([]);
  });

  it("ko 는 레지스트리 원문을 그대로 쓴다(폴백 경로가 살아 있다)", () => {
    const sections = buildPrimaryRegistrySections("ko");
    const first = PRIMARY_ROUTE_REGISTRY.find((i) => !i.parentId);
    expect(first).toBeTruthy();
    const found = sections
      .flatMap((s) => s.items)
      .find((i) => i.id === first!.id);
    expect(found?.label).toBe(first!.label);
  });

  it("번역이 없는 id 는 한국어로 폴백한다(빈 문자열·id 노출 금지)", () => {
    expect(resolveNavLabel("존재하지-않는-id", "한국어원문", "en")).toBe("한국어원문");
    expect(resolveNavSectionTitle("없는섹션", "섹션원문", "zh-CN")).toBe("섹션원문");
    expect(resolveStageLabel("없는단계", "단계원문", "en")).toBe("단계원문");
  });

  /**
   * ★형제 자리 — `lib/lifecycle-stages.ts` 의 `STAGE_META[].label` 도 한국어 하드코딩이었다.
   *   레지스트리만 고쳤을 때 **프로젝트 상세의 진행레일은 그대로 한국어**였다(실측: 봉합 후
   *   e2e DOM 이 안 바뀌었다). 한 자리를 고치면 형제를 스윕해야 한다 — 그 규율을 여기서 잠근다.
   */
  it.each(LOCALES)("%s — 모든 라이프사이클 단계에 번역이 있다", (loc) => {
    expect(LIFECYCLE_STAGES.length, "단계가 0개 — 검사가 공허하다").toBeGreaterThan(5);

    const missing = LIFECYCLE_STAGES.filter(
      (s) => !STAGE_LABELS[s]?.[loc],
    ).map((s) => `${s}("${STAGE_META[s]?.label ?? "?"}")`);

    expect(
      missing,
      `${loc} 단계 번역 누락 ${missing.length}건 — lib/navigation/nav-i18n.ts 에 추가할 것`,
    ).toEqual([]);
  });

  it.each(LOCALES)("%s — 단계 라벨을 옮기면 한글이 남지 않는다", (loc) => {
    const leaked = LIFECYCLE_STAGES.filter((s) =>
      HANGUL.test(resolveStageLabel(s, STAGE_META[s].label, loc)),
    ).map((s) => `${s}: "${resolveStageLabel(s, STAGE_META[s].label, loc)}"`);

    expect(leaked, `${loc} 단계 라벨에 한국어가 남았다 ${leaked.length}건`).toEqual([]);
  });
});
