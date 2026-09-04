/**
 * 모듈 안내문구 정직성 — **거짓 단정이 되돌아오지 못하게 한다**(2026-08-16).
 *
 * ★배경(실측): `modulePlaceholders.<모듈>.items` 는 `✓` 와 함께 렌더되는 단정문이었다.
 *   소비되는 16개 모듈 × 3줄 = 48건을 파일:라인 근거로 전수 대조한 결과 —
 *   **BACKED 11 · OVERSTATED 11 · FALSE 22 · UNVERIFIABLE 4.** 절반 가까이가 거짓이었다.
 *
 *   대표 사례:
 *     · `operations` — 유일한 백엔드 호출이 **리터럴 dict** 를 돌려준다
 *       (`apps/api/routers/projects.py:91-106`, `occupancy_rate_pct: 92.5` 하드코딩).
 *     · `construction` — "4D 간섭 체크"는 연면적 기반 2D 간트, "IoT 실시간 기성"은 수기 입력.
 *     · `drone` — 정사영상·토공량·열화상 전부 없음(실재는 외부 비전 API 결함 탐지).
 *     · `permit` — `seumter_permit_service.py:3` 이 스스로 *"★오칭 주의: 세움터 API 를
 *       호출하지 않는다"* 라고 적어 두었는데 화면은 단정하고 있었다.
 *
 * ★최대 오염원은 개별 모듈이 아니라 **복사된 보일러플레이트**였다:
 *   `"✓ 데이터 실시간 연동 대기 / ✓ 보안 컴플라이언스 통과 / ✓ 워크플로우 상태 라우팅"`
 *   이 11개 모듈에 글자 그대로 들어 있었고, 코드 생성 스크립트(`fix-dict.js:45`)가 일괄
 *   주입한 필러였다. **한 곳을 걷어내니 11개가 동시에 정직해졌다.**
 *
 * ★표기 규약은 `maintenance`(#634)가 세운 것을 따른다 — `· <하는 일> — <상태>`,
 *   미배선은 `— 미연결`. `✓`(검증·완료 표시)는 쓰지 않는다.
 *
 * ★한계(정직 바운딩): 이 검사는 **문구의 형태**를 잠근다. 각 문구가 지금도 사실인지는
 *   배선이 바뀌면 다시 대조해야 한다 — 그건 테스트가 아니라 사람의 일이다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const LOCALES = ["ko", "en", "zh-CN"] as const;
const HANGUL = /[가-힣]/;

/** 되돌아오면 안 되는 문구(실측된 원문). 전부 코드 근거가 0이었다. */
const BANNED = [
  "보안 컴플라이언스 통과",
  "데이터 실시간 연동 대기",
  "IoT 센서 22개소",
  "Predictive ML",
  "센서 기반 예지",
];

type Module = { title: string; description: string; items: string[] };

function load(loc: string): Record<string, Module> {
  const raw = readFileSync(
    resolve(process.cwd(), `public/locales/${loc}/common.json`),
    "utf-8",
  );
  return (JSON.parse(raw) as { modulePlaceholders: Record<string, Module> })
    .modulePlaceholders;
}

describe("모듈 안내문구 정직성", () => {
  it.each(LOCALES)("%s — 전제: 검사 대상이 존재한다(공허 진리 방지)", (loc) => {
    const mp = load(loc);
    expect(Object.keys(mp).length, "모듈이 없다 — 검사가 공허하다").toBeGreaterThan(10);
    const items = Object.values(mp).flatMap((m) => m.items ?? []);
    expect(items.length, "항목이 없다 — 검사가 공허하다").toBeGreaterThan(30);
  });

  /**
   * `✓` 는 "검증됐다·완료됐다"로 읽힌다. 배선을 확인하지 않은 문구에 이 표시를 붙이는 것이
   * 이 결함의 형태였다 — 표시 자체를 금지해 같은 형태가 재발하지 못하게 한다.
   */
  it.each(LOCALES)("%s — 완료 표시(✓)를 사실 단정에 쓰지 않는다", (loc) => {
    const offenders = Object.entries(load(loc)).flatMap(([k, m]) =>
      (m.items ?? []).filter((i) => i.includes("✓")).map((i) => `${k}: ${i}`),
    );
    expect(
      offenders,
      `✓ 로 단정한 문구 ${offenders.length}건 — 규약은 "· <하는 일> — <상태>" 다`,
    ).toEqual([]);
  });

  it.each(LOCALES)("%s — 근거 0으로 실측된 문구가 되돌아오지 않는다", (loc) => {
    const mp = load(loc);
    const offenders: string[] = [];
    for (const [k, m] of Object.entries(mp)) {
      const blob = `${m.title} ${m.description} ${(m.items ?? []).join(" ")}`;
      for (const banned of BANNED) {
        if (blob.includes(banned)) offenders.push(`${k}: "${banned}"`);
      }
    }
    expect(offenders, `근거 0 문구가 되돌아왔다 ${offenders.length}건`).toEqual([]);
  });

  /**
   * ★미배선 모듈은 **그 사실을 밝혀야 한다.** 문구를 지우기만 하면 "말하지 않음"이 되고,
   *   사용자는 여전히 되는 줄 안다. 감사에서 3줄 전부 FALSE 로 확인된 모듈이 대상이다.
   */
  const UNWIRED = ["operations", "construction", "drone", "maintenance"] as const;
  it.each(UNWIRED)("%s — 미연결 사실을 실제로 밝힌다", (mod) => {
    const m = load("ko")[mod];
    expect(m, `${mod} 모듈이 사전에서 사라졌다 — 검사가 공허해진다`).toBeTruthy();
    const blob = `${m.description} ${(m.items ?? []).join(" ")}`;
    expect(blob, `${mod}: 무엇이 미연결인지 밝히지 않는다`).toMatch(/미연결|연결되지 않/);
  });

  /**
   * ★i18n — 내비게이션과 같은 결함이 여기에도 있었다(en·zh-CN 에 한국어 원문 방치).
   *   `nav-i18n.coverage.test.ts` 의 형제 검사다.
   */
  it.each(["en", "zh-CN"] as const)("%s — 한국어 원문이 남지 않는다", (loc) => {
    const leaked: string[] = [];
    for (const [k, m] of Object.entries(load(loc))) {
      for (const [field, val] of Object.entries({
        title: m.title,
        description: m.description,
      })) {
        if (HANGUL.test(String(val ?? ""))) leaked.push(`${k}.${field}`);
      }
      for (const i of m.items ?? []) {
        if (HANGUL.test(i)) leaked.push(`${k}.items: "${i}"`);
      }
    }
    expect(leaked, `${loc} 에 한국어가 남았다 ${leaked.length}건`).toEqual([]);
  });

  /** 세 로케일의 모듈 집합·항목 수가 어긋나면 한쪽만 고친 것이다. */
  it("세 로케일의 모듈 집합과 항목 수가 일치한다", () => {
    const [ko, en, zh] = LOCALES.map(load);
    expect(Object.keys(en).sort()).toEqual(Object.keys(ko).sort());
    expect(Object.keys(zh).sort()).toEqual(Object.keys(ko).sort());
    for (const k of Object.keys(ko)) {
      expect(en[k].items?.length, `${k}: en 항목 수 불일치`).toBe(ko[k].items?.length);
      expect(zh[k].items?.length, `${k}: zh-CN 항목 수 불일치`).toBe(ko[k].items?.length);
    }
  });
});
