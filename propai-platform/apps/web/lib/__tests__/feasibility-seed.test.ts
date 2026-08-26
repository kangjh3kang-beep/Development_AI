/**
 * 부지 파생 수지 시드 — **세 경로가 같은 것을 보내는가**.
 *
 * ## 무엇이 있었나
 *
 * `node-body-builders.ts:259` 가 `official_price_per_sqm?` 를 **계약으로 선언**해 놓고
 * 그 파일의 `body.official_price_per_sqm` 대입은 **0건**이었다(대조군: `body.` 대입 31건).
 * 오케스트레이션 수지는 **공시지가 0** 으로 토지비를 잡았고, 형제(`ModuleInputForm`)는
 * 이미 올바르게 보내고 있었다. ★§G30 — 동작 주장은 그 자체가 검증 대상이다.
 *
 * ## 왜 파생형인가
 *
 * *"이 세 필드를 보내는가"* 를 **손으로 나열**하면 네 번째 필드가 생길 때 조용히 빠진다.
 * 계약을 `SITE_DERIVED_REQUEST_FIELDS` **한 곳에서 파생**시키고, 각 경로의 소스를 그 목록으로
 * 검사한다 — 새 필드를 계약에 추가하면 **경로들이 자동으로 감시 대상**이 된다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import {
  SITE_DERIVED_REQUEST_FIELDS,
  siteDerivedFeasibilityFields,
} from "@/lib/feasibility-seed";

const WEB_ROOT = join(__dirname, "..", "..");
const read = (rel: string) =>
  __stripCommentsForScan(readFileSync(join(WEB_ROOT, rel), "utf8"), rel);

// ── 축 ① 판정 — 순수 함수를 합성 입력으로 태운다 ────────────────────────
describe("시드 산출 — 합성 입력", () => {
  const site = (o: Record<string, unknown>) => o as never;

  it("★전제: 정상 입력에서 세 값이 모두 나온다(공허한 초록 방지)", () => {
    const r = siteDerivedFeasibilityFields(
      site({ address: "울산광역시 동구 화정동 637-11", landAreaSqm: 1000,
             officialPrices: [{ pricePerSqm: 3_000_000 }] }),
    );
    expect(r.totalLandAreaSqm).toBe(1000);
    expect(r.officialPricePerSqm).toBe(3_000_000);
    expect(r.sidoName).toBe("울산광역시");
  });

  it("★0 은 「0원」이 아니라 「모름」이다 — null 로 돌려준다(무목업)", () => {
    const r = siteDerivedFeasibilityFields(
      site({ address: "", landAreaSqm: 0, officialPrices: [{ pricePerSqm: 0 }] }),
    );
    expect(r.officialPricePerSqm).toBeNull();
    expect(r.totalLandAreaSqm).toBeNull();
    expect(r.sidoName).toBeNull();
  });

  it("음수·NaN·미확보도 null", () => {
    expect(siteDerivedFeasibilityFields(null).officialPricePerSqm).toBeNull();
    expect(
      siteDerivedFeasibilityFields(site({ officialPrices: [{ pricePerSqm: -1 }] })).officialPricePerSqm,
    ).toBeNull();
    expect(
      siteDerivedFeasibilityFields(site({ officialPrices: [{ pricePerSqm: "x" }] })).officialPricePerSqm,
    ).toBeNull();
  });

  it("주소 첫 토큰이 시도명 — 공백만 있는 주소는 null", () => {
    expect(siteDerivedFeasibilityFields(site({ address: "   " })).sidoName).toBeNull();
    expect(siteDerivedFeasibilityFields(site({ address: "경기도 성남시" })).sidoName).toBe("경기도");
  });

  // ── 시군구 — **이 필드가 없으면 상하수도 원인자부담금이 조용히 사라진다** ──
  //   백엔드 B03(수도법 §71)·B04(하수도법 §61)는 `sigungu_name` 으로 시군구 조례 단가표를
  //   조회한다. 빈 문자열이면 `unavailable` 로 강등돼 합계에서 빠지는데, 화면엔
  //   「미등록 지역」처럼 보인다 — 실제로는 **우리가 안 보낸 것**이다.
  it("★★둘째 토큰이 시군구명 — 값을 못 박는다(존재검사로는 `= \"\"` 가 살아남는다)", () => {
    const r = siteDerivedFeasibilityFields(
      site({ address: "울산광역시 동구 화정동 637-11" }),
    );
    expect(r.sidoName).toBe("울산광역시");
    expect(r.sigunguName).toBe("동구");
  });

  it("★두 모집단이 갈린다 — 토큰 2개 이상이면 시군구가 나오고, 1개면 null 이다", () => {
    // 이 두 줄이 **같은 값**을 내면 시군구 배선을 끊어도 통과한다.
    const many = siteDerivedFeasibilityFields(site({ address: "경기도 성남시 분당구" }));
    const one = siteDerivedFeasibilityFields(site({ address: "세종특별자치시" }));
    expect(many.sigunguName).toBe("성남시");
    expect(one.sigunguName).toBeNull();
    expect(many.sigunguName).not.toBe(one.sigunguName);
    // 시도는 **둘 다** 나와야 한다 — 시군구가 없다고 시도까지 잃으면 B01 판정이 죽는다.
    expect(one.sidoName).toBe("세종특별자치시");
  });

  it("★연속 공백·탭에도 토큰이 밀리지 않는다 — 형제와 같은 `/\\s+/` 규칙", () => {
    // 종전 `split(" ")` 는 빈 토큰을 만들어 `sido_name=""` 를 보냈다(형제가 옳았다).
    const r = siteDerivedFeasibilityFields(site({ address: "  부산광역시   해운대구\t우동 " }));
    expect(r.sidoName).toBe("부산광역시");
    expect(r.sigunguName).toBe("해운대구");
  });
});

// ── 축 ② 배선 — 세 경로가 **공용 산출처**를 쓰는가 ──────────────────────
describe("배선 — 세 경로가 같은 산출처를 쓴다", () => {
  const PATHS = [
    "lib/orchestration/node-body-builders.ts",
    "components/feasibility/ModuleInputForm.tsx",
  ] as const;

  it("★전제: 대상 파일을 실제로 읽었다(공허한 초록 방지)", () => {
    for (const p of PATHS) {
      const src = read(p);
      expect(src.length, `${p} 를 못 읽었다`).toBeGreaterThan(1000);
      expect(src, `${p} 가 수지 경로가 아니다 — 검사 전제가 깨졌다`).toMatch(
        /feasibility|Feasibility/,
      );
    }
  });

  it("★두 경로 모두 공용 헬퍼를 경유한다 — 각자 만들면 네 번째가 또 빠진다", () => {
    for (const p of PATHS) {
      expect(read(p), `${p}: 공용 산출처를 안 쓴다`).toContain("siteDerivedFeasibilityFields");
    }
  });

  it("★★공시지가·시도명을 **실제로 대입**한다 — 주석의 계약 선언은 대입이 아니다", () => {
    const orch = read("lib/orchestration/node-body-builders.ts");
    // 주석은 __stripCommentsForScan 이 걷었으므로 남은 것은 실행 줄뿐이다.
    expect(
      orch,
      "official_price_per_sqm 대입이 없다 — 계약만 선언하고 안 보내던 그 상태다",
    ).toMatch(/body\.official_price_per_sqm\s*=/);
    expect(orch, "sido_name 대입이 없다").toMatch(/body\.sido_name\s*=/);
  });

  // ★★래칫이 스스로 무장해제되지 않게 — 변이 실증(2026-08-26).
  //   계약 목록에서 이름 한 줄을 지우면 아래 파생형 락은 그 필드를 **더 이상 안 본다**.
  //   즉 목록 자체가 래칫이면 **래칫을 낮출 수 있다**(변이 M5 SURVIVED).
  //   그래서 계약을 **헬퍼가 실제로 산출하는 키**에서 파생시켜 대조한다 — 산출은 하는데
  //   계약에 없으면 빨개진다. 이제 목록을 줄이는 것만으로는 통과할 수 없다.
  it("★★계약 목록이 헬퍼 산출과 1:1 이다 — 목록을 줄여 락을 끄지 못한다", () => {
    const produced = siteDerivedFeasibilityFields({
      address: "울산광역시 동구 화정동",
      landAreaSqm: 1,
      officialPrices: [{ pricePerSqm: 1 }],
    } as never);
    const snake = (k: string) => k.replace(/[A-Z]/g, (c) => "_" + c.toLowerCase());
    // 헬퍼의 camelCase 키 → 요청 필드명(snake_case). 이름 규칙이 어긋나면 여기서 드러난다.
    const expected = Object.keys(produced).map(snake).sort();
    expect(expected.length, "헬퍼가 아무것도 산출하지 않는다 — 검사 전제가 깨졌다").toBeGreaterThan(2);
    expect(
      [...SITE_DERIVED_REQUEST_FIELDS].sort(),
      "계약 목록과 헬퍼 산출이 어긋난다 — 산출은 하는데 계약에 없거나(경로가 안 보냄) 그 반대다",
    ).toEqual(expected);
  });

  it("★파생형 — 계약 목록의 필드가 각 경로 소스에 전부 나타난다(새 필드가 조용히 빠지지 않게)", () => {
    expect(SITE_DERIVED_REQUEST_FIELDS.length, "계약 목록이 비었다").toBeGreaterThan(2);
    const missing: string[] = [];
    for (const p of PATHS) {
      const src = read(p);
      for (const f of SITE_DERIVED_REQUEST_FIELDS) {
        if (!src.includes(f)) missing.push(`${p} ← ${f}`);
      }
    }
    expect(
      missing,
      "계약이 선언한 부지 파생 필드를 안 보내는 경로가 있다:\n" + missing.join("\n"),
    ).toEqual([]);
  });

  it("★음성 대조군 — 수지와 무관한 노드는 이 헬퍼를 쓰지 않는다(무차별 치환 배제)", () => {
    const src = read("lib/orchestration/node-body-builders.ts");
    // 헬퍼는 feasibility case 안에서만 호출돼야 한다 — 파일 전체에서 1회.
    const calls = src.match(/siteDerivedFeasibilityFields\s*\(/g) ?? [];
    expect(calls.length, "헬퍼가 여러 노드에 무차별로 뿌려졌다").toBe(1);
  });

  // ★부채를 초록 안에서 보이게(규율 C-13). 커밋 메시지에만 적으면 안 드러난다.
  //   다필지에서 **면적은 합산, 단가는 대표 1필지**(officialPrices[0])라 기준이 갈릴 수 있다.
  //   이 커밋이 만든 것이 아니라 **옮겨 온** 것이고, 여기서 고치면 배선 수정과 값 변경이 섞인다.
  it.todo("다필지 공시지가 — 면적가중 단가로 바꿀지 판단(값 차이 미측정)");
});
