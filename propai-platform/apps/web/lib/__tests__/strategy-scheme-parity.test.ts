/**
 * P2 매입전략 — 프론트 사업방식 목록이 **백엔드 정본과 어긋나지 않게** 잠근다.
 *
 * 【왜 필요한가】사용자가 고른 사업방식이 상류에서 미등록으로 떨어지면
 * `governing_act=null` 이 되어 **전건 판정보류**가 나온다. 화면은 정상처럼 동작하고
 * 결과만 전부 "판정보류" 라서 **조용한 실패**다. 오타 하나·개명 하나로 그렇게 된다.
 *
 * 【★★2026-09-05 축 교정 — 이 락은 **틀린 사전을 재고 있었다**】
 * 위 선언(*"미등록이면 `governing_act=null` → 전건 판정보류"*)은 **옳다.** 그런데 검사 대상이
 * `_SCHEME_LEGAL_KEYS`(18키)였고 **`governing_act` 를 정하는 정본은 `MAGDO_RULES`(7키)** 다.
 * 전자는 *근거법령 딥링크 매핑*, 후자는 *매도청구·수용 정책표*이고 `scheme_legal_profile()` 은
 * **후자만 읽는다**(`scenario_simulator.py`).
 *
 *     프론트 9종 vs _SCHEME_LEGAL_KEYS(18) → 미등록 0  ⇒ 락 100% 초록
 *     프론트 9종 vs MAGDO_RULES(7)         → 미등록 5  ⇒ 사고 실재
 *     ★판별력 0 vs 5
 *
 * ***선언이 옳아도 결속된 축이 틀리면 락은 장식이다.***
 *
 * 【그래서 부분집합이 아니라 **래칫**이다】정본(`MAGDO_RULES`)으로 옮기면 현재 5종이 즉시
 * 위반이라 `main` 이 빨개진다. 그러나 **그 5종을 지우는 것은 답이 아니다** — 미등록은
 * **플랫폼의 결손**이지 법적 부적용이 아니다(소규모재건축·소규모재개발·자율주택은
 * 소규모주택정비특례법 §35 매도청구 대상이다). 그래서 **현재 수를 기록하고 늘지 않게** 잠근다.
 *
 * 【★판정 가능성은 두 축이다 — 한 축만 보면 절반을 못 본다】
 * `_row_action` 은 **두 갈래**에서 똑같이 전 행 판정보류를 낸다:
 *   ① `governing_act is None`  — 정책표 미등록(**개발자**가 고칠 것)
 *   ② `requires_track_input`   — 트랙(시행자 유형·관리지역) 미입력(**사용자**가 채울 것)
 * 사유가 다르므로 **따로 센다.** 뭉치면 «무엇을 하면 풀리는지» 가 사라진다.
 *
 * 【상한도 함께】`MAX_STRATEGY_PARCELS` 는 백엔드 `MAX_BULK_ITEMS` 와 같은 값이어야 한다.
 * 어긋나면 프론트가 통과시킨 요청을 상류가 422 로 거부한다(사용자에겐 원인 불명의 실패).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { MAX_STRATEGY_PARCELS, STRATEGY_SCHEMES } from "@/components/operations/ParcelPurchaseStrategyPanel";

const API_ROOT = join(__dirname, "..", "..", "..", "api");

function readApi(rel: string): string {
  return readFileSync(join(API_ROOT, rel), "utf8");
}

/** 근거법령 **딥링크 매핑**(18키). ★`governing_act` 를 정하지 **않는다** — 판정 축이 아니다. */
function legalRefKeys(): string[] {
  const src = readApi("app/services/development/scenario_simulator.py");
  const block = /_SCHEME_LEGAL_KEYS:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{([\s\S]*?)\n\}/.exec(src);
  if (!block) return [];
  return [...block[1].matchAll(/^\s*"([^"]+)"\s*:/gm)].map((m) => m[1]);
}

/**
 * ★**판정 정본** — `governing_act`·`requires_track_input` 을 정하는 정책표.
 *   최상위 키만 뽑는다(값이 중첩 dict 라 들여쓰기 깊이로 가른다).
 */
function magdoRules(): { scheme: string; requiresTrack: boolean }[] {
  const src = readApi("app/services/development/scenario_simulator.py");
  const block = /MAGDO_RULES:\s*dict\[str,\s*dict\[str,\s*Any\]\]\s*=\s*\{([\s\S]*?)\n\}/.exec(src);
  if (!block) return [];
  const body = block[1];
  // 최상위 항목 = 들여쓰기 4칸의 `"키": {` — 그 블록 안에서 requires_track_input 을 본다.
  const out: { scheme: string; requiresTrack: boolean }[] = [];
  const re = /^ {4}"([^"]+)":\s*\{([\s\S]*?)^ {4}\},?$/gm;
  for (const m of body.matchAll(re)) {
    out.push({ scheme: m[1], requiresTrack: /"requires_track_input":\s*True/.test(m[2]) });
  }
  return out;
}

describe("P2 사업방식 — 판정 가능성이 측정되고, 나빠지지 않는다", () => {
  const legalKeys = legalRefKeys();
  const magdo = magdoRules();
  const magdoNames = magdo.map((r) => r.scheme);

  it("전제: 두 정본을 실제로 읽어냈다(공허한 초록 방지)", () => {
    // ★파서가 죽으면 빈 배열이 되고 아래 「미등록 0」 이 **공허하게 참**이 된다.
    //   그래서 하한을 **먼저** 단언한다 — 이 락이 종전에 틀린 사전을 재고도 초록이었던 이유가
    //   그 축이 아니라 **결속 대상**이었으므로, 생존 단언은 두 축 모두에 건다.
    expect(legalKeys.length, "_SCHEME_LEGAL_KEYS 파싱 실패 — 조회기가 죽었다").toBeGreaterThan(10);
    expect(magdo.length, "MAGDO_RULES 파싱 실패 — 조회기가 죽었다").toBeGreaterThan(3);
    expect(STRATEGY_SCHEMES.length, "프론트 목록이 비었다").toBeGreaterThan(0);
    // ★두 사전이 **실제로 다르다**(같으면 축을 옮긴 의미가 없고, 다시 대리 변수를 재게 된다).
    expect(magdo.length).toBeLessThan(legalKeys.length);
  });

  /**
   * ★**래칫이지 부분집합이 아니다.** 현재 미등록 방식이 실재하고(플랫폼 결손),
   *   그것을 드롭다운에서 지우면 «법적으로 매도청구 대상이 아니다» 로 오독된다.
   *   그래서 **늘지 않게** 잠그고 실제 수를 초록 안에 드러낸다.
   */
  const UNREGISTERED_MAX = 5;   // 2026-09-05 실측
  const TRACK_PENDING_MAX = 2;  // 2026-09-05 실측(가로주택·모아주택)

  it("★① 정책표 미등록이 늘지 않는다 — 개발자가 고칠 축", () => {
    const missing = STRATEGY_SCHEMES.filter((s) => !magdoNames.includes(s));
    expect(
      missing.length,
      `정책표(MAGDO_RULES) 미등록이 늘었다 — 고르면 전 행 판정보류다:\n${missing.join("\n")}`,
    ).toBeLessThanOrEqual(UNREGISTERED_MAX);
    // ★하한도 건다 — 줄었으면 래칫을 조여야 한다(경계는 양방향으로 건다).
    expect(
      missing.length,
      `미등록이 줄었다(${missing.length}) — UNREGISTERED_MAX 를 그 값으로 낮춰라`,
    ).toBe(UNREGISTERED_MAX);
  });

  it("★② 트랙 미입력이 늘지 않는다 — 사용자가 채울 축(사유가 ①과 다르다)", () => {
    const pending = STRATEGY_SCHEMES.filter((s) =>
      magdo.some((r) => r.scheme === s && r.requiresTrack),
    );
    expect(pending.length, `트랙 입력 필요 방식:\n${pending.join("\n")}`).toBe(TRACK_PENDING_MAX);
  });

  it("★③ 두 축을 합치면 판정이 나오는 방식이 몇 종인지 드러난다", () => {
    const undecidable = STRATEGY_SCHEMES.filter(
      (s) => !magdoNames.includes(s) || magdo.some((r) => r.scheme === s && r.requiresTrack),
    );
    const decidable = STRATEGY_SCHEMES.length - undecidable.length;
    // ★이 수가 이 기능의 실제 크기다. 종전 락은 이것을 **0으로 보고 있었다**.
    expect(undecidable.length).toBe(UNREGISTERED_MAX + TRACK_PENDING_MAX);
    expect(decidable, "판정이 나오는 방식이 사라졌다").toBeGreaterThan(0);
  });

  it("대조군: 존재하지 않는 방식은 어느 축에도 없다(락이 무엇이든 통과시키지 않는다)", () => {
    expect(magdoNames.includes("존재하지않는사업방식XYZ")).toBe(false);
    expect(legalKeys.includes("존재하지않는사업방식XYZ")).toBe(false);
  });

  it("부축: 딥링크 매핑은 여전히 프론트 전부를 덮는다 — ★단 이것은 판정 축이 아니다", () => {
    // 이름에 적는다 — 다음 사람이 이 초록을 「판정 가능성이 잠겼다」로 오독하지 않게.
    expect(STRATEGY_SCHEMES.filter((s) => !legalKeys.includes(s))).toEqual([]);
  });

  it("★필지 상한이 백엔드와 같다", () => {
    // ★★2026-09-05 — 축을 옮기며 이 단언을 **통째로 날렸다가 린트가 잡았다**
    //   (`MAX_STRATEGY_PARCELS` 가 미사용으로 남았다). docstring §「상한도 함께」는 그대로였으므로
    //   **선언은 남고 잠금만 사라진** 상태였다 — 이 저장소가 반복 경고한 그 형태다.
    //   ***락을 고칠 때 그 락이 이미 잠그던 것을 세라.***
    const src = readApi("routers/registry.py");
    const m = /^MAX_BULK_ITEMS\s*=\s*(\d+)/m.exec(src);
    expect(m, "MAX_BULK_ITEMS 를 못 찾았다 — 조회기가 죽었다").not.toBeNull();
    expect(
      MAX_STRATEGY_PARCELS,
      "프론트 상한이 백엔드와 다르다 — 통과시킨 요청을 상류가 422 로 거부한다",
    ).toBe(Number(m?.[1]));
  });

  // ★★부채 — 이 락은 **목록의 축**만 잠근다. 「미등록 방식을 고르면 유료 실행 전에 고지한다」는
  //   행위 축이라 여기서 못 잠근다(그 고지가 아직 유료 호출 뒤에만 뜬다).
  it.todo("★부채: 미등록 방식 선택 시 유료 실행 **전에** 고지하는지 잠근다(/survey/quote 경유)");
});
