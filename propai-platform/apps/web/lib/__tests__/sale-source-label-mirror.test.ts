/**
 * **분양가 산정근거 라벨** — 프론트 어휘가 백엔드 어휘를 덮는가(미러 락).
 *
 * ## 왜 이 파일이 있나
 *
 * 백엔드가 `sale_price_source` 로 내는 값을 화면이 **손 목록**으로 한글화한다.
 * `CLAUDE.md` 가 명문으로 경고하는 자리다 — *"고친 자리의 형제·미러를 반드시 스윕한다
 * (백엔드만 고치고 프론트 미러를 놓치는 일이 반복됐다)"*.
 *
 * 실측(2026-09-05): 백엔드 8종 중 **`avm_blended`·`national_default_fallback` 이 빠져
 * 있었고**(선재 결함), 거기에 `single_source:<key>` 라는 **접두 계열**이 추가됐다.
 * ★그 계열은 «출처 하나만 남았다» = **블렌딩이 안 됐다**는 뜻이고, 그것이 바로
 *   «블렌딩이 안 됐는데 됐다고 말하던» 결함을 드러내려 만든 값이다.
 *   **그 값이 raw 토큰으로 보이면 사용자는 여전히 원인을 못 본다.**
 *
 * ★**손 목록이 아니라 백엔드 소스에서 파생**한다 — 백엔드가 라벨을 추가하면 여기가 빨개진다.
 */
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { SALE_SOURCE_LABEL, saleSourceLabel } from "@/lib/sale-source-label";

const API = path.resolve(__dirname, "../../../api");

/**
 * ★백엔드의 **어휘 선언**(`SALE_PRICE_SOURCE_VOCAB`)을 읽는다.
 *
 * ★소스를 정규식으로 긁는 방식은 **위양성 투성이**였다 — 키 이름 자체(`sale_price_source`)와
 *   **다른 필드의 값**(`market_price_basis == "national_default"`)까지 집었다(두 번 겪었다).
 *   → 백엔드가 **선언**하고, 그 선언이 생산자와 맞는지는 **백엔드 락**
 *     (`tests/test_sale_price_source_vocab.py`)이 `ast` 로 잠근다. 여기는 선언만 읽는다.
 *   *선언은 자기를 검증하지 않는다 — 그래서 검증을 생산자 쪽에 뒀다.*
 */
function backendVocabulary(): string[] {
  const p = path.join(API, "app/services/feasibility/market_revaluation_service.py");
  const src = fs.readFileSync(p, "utf8");
  // ★★비탐욕 `[\s\S]*?\)` 는 **첫 `)` 에서 멈춘다** — 그 `)` 가 튜플 **마지막 주석 안**에
  //   있어서, 스캐너가 **주석의 값**을 집고(선언에서 뺐다고 그 주석이 직접 말하는
  //   `"unavailable"`) 그 뒤의 진짜 항목은 **못 봤다**.
  //   ★이 파일 독스트링이 *"정규식으로 긁는 방식은 위양성 투성이라 선언을 읽는다"* 고
  //     적어 놓고 **다시 주석을 긁고 있었다.**
  //   → ①`#` 이후를 **먼저 스트립** ②닫는 괄호를 **줄 시작 앵커**(`^\)`)로 잡는다.
  const decl = src.match(/^SALE_PRICE_SOURCE_VOCAB[^=]*=\s*\(([\s\S]*?)^\)/m);
  if (!decl) return [];
  const codeOnly = decl[1]
    .split("\n")
    .map((l) => l.replace(/#.*$/, ""))
    .join("\n");
  return [...codeOnly.matchAll(/"([a-z_:]+)"/g)].map((x) => x[1]);
}

/** 주석·설명에 속지 않게 줄/블록 주석을 걷는다(두 배선 락이 같은 전처리를 쓴다) */
function stripComments(raw: string): string {
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((l) => l.replace(/\/\/.*$/, ""))
    .join("\n");
}

describe("분양가 산정근거 라벨 미러", () => {
  it("★조회기가 살아 있다(백엔드 어휘를 실제로 집는가)", () => {
    const vocab = backendVocabulary();
    expect(vocab.length).toBeGreaterThanOrEqual(4);
    // 양성 대조군 — 반드시 있어야 할 값
    expect(vocab).toContain("market_blended");
  });

  it("★백엔드 어휘가 **전부** 한글화된다(코드가 그대로 노출되지 않는다)", () => {
    const raw = backendVocabulary()
      // f-string 자리표시자는 실제 값으로 바꿔서 본다
      .map((v) => v.replace(/\{[a-z_]+\}/, "regional"));
    const untranslated = raw.filter((v) => saleSourceLabel(v) === v);
    expect(
      untranslated,
      `백엔드가 내는데 화면이 코드 그대로 보여 주는 값: ${untranslated.join(", ")}`,
    ).toEqual([]);
  });

  it("★`single_source:` 계열은 **접두로** 처리된다 — 목록이 상한이 되지 않게", () => {
    // 알려진 하위 출처
    expect(saleSourceLabel("single_source:regional")).toContain("단일 출처");
    expect(saleSourceLabel("single_source:molit_real")).toContain("국토부");
    // ★모르는 하위 출처가 새로 생겨도 **한글 껍데기**는 붙는다(raw 토큰 노출 방지)
    const unknown = saleSourceLabel("single_source:brand_new_source");
    expect(unknown).toContain("단일 출처");
    expect(unknown).not.toBe("single_source:brand_new_source");
  });

  it("★주석에 적은 값은 어휘로 세지 않는다(스캐너 위양성 방지)", () => {
    // 선언 주석에 `"unavailable"` 이 나오는데, 그것은 **뺐다고 말하는 문장**이다.
    // 종전 스캐너는 그것을 어휘로 집었다 — 그리고 **주석 뒤 진짜 항목은 못 봤다**.
    expect(backendVocabulary()).not.toContain("unavailable");
    // 양성 대조군: 주석 **뒤**에 있는 실제 항목도 잡히는가(잘림 방지)
    expect(backendVocabulary()).toContain("national_default_no_address");
  });

  it("음성 대조군 — 정말 모르는 코드는 **코드 그대로**(거짓 라벨보다 낫다)", () => {
    expect(saleSourceLabel("zzz_not_a_real_code")).toBe("zzz_not_a_real_code");
  });
});

describe("★배선 — 화면이 그 함수를 실제로 경유하는가", () => {
  /**
   * ★★**이 저장소에서 같은 클래스가 세 번째다** — «함수만 잠그고 배선을 안 잠갔다».
   *
   * 미러 락이 막겠다고 **선언한 결함**은 *"그 값이 화면에 raw 토큰으로 나오면 사용자는
   * 여전히 원인을 못 본다"* 인데, `saleSourceLabel(value)` → `value` 한 줄 변경으로
   * 그 결함이 **그대로 부활**하는데 모든 락이 초록이었다(4차 리뷰 MAJOR-4).
   *
   * ★렌더 단언이 이상적이지만 그 패널은 무거운 의존을 끌어온다 —
   *   그래서 **주석을 걷어낸 소스**를 파서로 본다(문자열 grep 이 아니다).
   */
  it("`sale_price_source` 를 표시하는 자리는 `saleSourceLabel` 을 경유한다", () => {
    const p = path.resolve(__dirname, "../../components/pipeline/ProjectPipelinePanel.tsx");
    const code = stripComments(fs.readFileSync(p, "utf8"));

    // ★공허진리 방지 — 그 분기가 실재하는가(조회기 생존)
    const branch = code.match(/key === "sale_price_source"[\s\S]{0,220}/);
    expect(branch, "sale_price_source 분기를 못 찾았다 — 조회기 사망").toBeTruthy();

    expect(
      branch![0],
      "화면이 `saleSourceLabel` 을 경유하지 않는다 — 코드가 raw 토큰으로 노출된다",
    ).toContain("saleSourceLabel(");
    // 음성 대조군: 그 분기가 값을 **그대로** 돌려주지 않는다
    expect(branch![0]).not.toMatch(/return\s+value\s*;/);
  });

  /**
   * ★★**한 층 위가 무잠금이었다** — 위 락은 `displayFieldValue` **안**이 `saleSourceLabel`
   * 을 부르는 것을 잠근다. **화면이 `displayFieldValue` 를 거치는지**는 안 잠갔다.
   * 5차 리뷰가 렌더 자리에서 두 변이로 실증했다(둘 다 SURVIVED · 락 전부 초록):
   *
   *     {displayFieldValue(key, value)} → {String(value)}
   *     → {key === "sale_price_source" ? String(value) : displayFieldValue(key, value)}
   *
   * 두 번째는 헬퍼가 계속 쓰이므로 **린트·타입도 초록**이다 — 다른 게이트가 없다.
   * ★그래서 **「포함한다」로 잠그면 안 된다**(위 변이는 `displayFieldValue(` 를 **포함한다**).
   *   축을 뒤집어 **렌더 자리에서 파생**한다: 값 격자의 보간 중 `value` 를 나르는 것은
   *   **오직 `displayFieldValue(key, value)` 뿐**이어야 한다. 우회 경로는 전부 식을 더한다.
   */
  it("★값 격자에서 `value` 가 화면에 닿는 경로는 `displayFieldValue` **하나뿐**이다", () => {
    const p = path.resolve(__dirname, "../../components/pipeline/ProjectPipelinePanel.tsx");
    const code = stripComments(fs.readFileSync(p, "utf8"));

    // 격자 블록을 **렌더 자리에서** 잘라낸다(손 목록이 아니다)
    const start = code.indexOf("Object.entries(stage.data)");
    expect(start, "값 격자를 못 찾았다 — 조회기 사망").toBeGreaterThan(-1);
    const grid = code.slice(start, start + 1600);

    // 그 블록의 JSX 보간 중 식별자 `value` 를 나르는 것만 모은다(파생형)
    const carriers = (grid.match(/\{[^{}]*\bvalue\b[^{}]*\}/g) || [])
      .map((m) => m.slice(1, -1).replace(/\s+/g, " ").trim())
      // 화살표 인자 선언(`([key, value]) =>`)과 필터 술어는 렌더가 아니다
      .filter((e) => !e.includes("=>"));
    expect(carriers.length, "`value` 를 나르는 보간이 0개 — 조회기 사망").toBeGreaterThan(0);

    const bypass = carriers.filter((e) => e !== "displayFieldValue(key, value)");
    expect(
      bypass,
      `값이 **\`displayFieldValue\` 를 우회해** 화면에 닿는다: ${JSON.stringify(bypass)} — ` +
        "이 경로로 `single_source:regional` 같은 raw 토큰이 그대로 노출된다",
    ).toEqual([]);
  });

  it("★프론트 맵에 백엔드가 안 내는 값이 남아 있지 않다(역방향)", () => {
    // 미러 락이 백엔드→프론트 **한 방향**만 봤다. 백엔드에서 「죽은 어휘」로 뺀 값이
    // 프론트에 남으면, 그 규칙을 한쪽에만 적용한 것이다(4차 리뷰 Minor-4).
    const vocab = new Set(backendVocabulary());
    const feKeys = Object.keys(SALE_SOURCE_LABEL);
    expect(feKeys.length).toBeGreaterThanOrEqual(5);   // 공허진리 방지
    // ★★축을 좁혔다 — 첫 판은 «백엔드 선언에 없으면 죽은 어휘» 로 봐서 **위양성 5건**을 냈다.
    //   `avm`·`user_override`·`unavailable` 은 **다른 문맥**(AVM 해석기·파이프라인 override
    //   플래그·보류 표기)에서 쓰이는 값이고, 프론트 맵이 그것들을 라벨로 갖는 것은
    //   **레거시 호환**이지 결함이 아니다. ★**위양성도 결함이다** — 가드가 정상 코드를
    //   지우게 하면 라벨이 사라져 사용자에게 raw 토큰이 간다(이 락이 막으려는 그것).
    //   → **백엔드 선언에서 명시적으로 「뺀」 값**만 죽은 어휘로 본다.
    const REMOVED_FROM_BACKEND = ["unavailable"];   // 선언 주석이 «뺐다» 고 적은 값
    const stale = feKeys.filter(
      (k) => !vocab.has(k) && REMOVED_FROM_BACKEND.includes(k));
    expect(
      stale,
      `백엔드가 **명시적으로 뺀** 값이 프론트 맵에 남았다: ${stale.join(", ")} — ` +
        "규칙을 한쪽에만 적용한 것이다",
    ).toEqual([]);
    // ★공허진리 방지 — 이 검사가 실제로 무언가를 볼 수 있는가
    expect(REMOVED_FROM_BACKEND.length).toBeGreaterThan(0);
  });
});
