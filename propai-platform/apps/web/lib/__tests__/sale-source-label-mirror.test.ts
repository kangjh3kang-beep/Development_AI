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

import { saleSourceLabel } from "@/lib/sale-source-label";

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
  const m = src.match(/SALE_PRICE_SOURCE_VOCAB[^=]*=\s*\(([\s\S]*?)\)/);
  if (!m) return [];
  return [...m[1].matchAll(/"([a-z_:]+)"/g)].map((x) => x[1]);
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

  it("음성 대조군 — 정말 모르는 코드는 **코드 그대로**(거짓 라벨보다 낫다)", () => {
    expect(saleSourceLabel("zzz_not_a_real_code")).toBe("zzz_not_a_real_code");
  });
});
