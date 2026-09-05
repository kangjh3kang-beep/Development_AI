import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { buildConstructionParams, perPyeongToPerSqm } from "../construction-cost-params";

const REPO = path.resolve(__dirname, "../../../..");
const WEB = path.resolve(__dirname, "../..");

describe("④ 공사비 배선 — 단위·폴백·정본", () => {
  /**
   * ★계획 §5-2. 이 저장소가 방금 #980 에서 고친 결함이 **단위 다른 두 수**였다.
   * 평당값을 ㎡ 칸에 넣으면 3.3배 과대인데 **결과가 그럴듯한 큰 수**라 화면으로 안 걸린다.
   */
  it("평당→㎡ 변환이 정확하고, 방향이 반대가 아니다", () => {
    // 아파트 기본 단가 실측: 2,400,000 원/㎡ = 평당 7,933,920 원
    expect(perPyeongToPerSqm(7_933_920)).toBe(2_400_000);
    // ★방향 락 — 나누기를 곱하기로 바꾸면 잡힌다(부호 없는 배수라 크기로만 갈린다)
    expect(perPyeongToPerSqm(1_000_000)).toBeLessThan(1_000_000);
  });

  /**
   * ★모집단은 **프로덕션 코드**다 — 테스트는 뺀다.
   *   첫 판은 안 뺐고, **이 파일 자신의 테스트 제목**에 그 숫자가 있어서 **첫 실행이 빨갛게** 났다.
   *   저장소가 이름 붙인 함정(*«주석에 예시를 적으면 그 예시가 다음 검사의 위양성이 된다»*)의
   *   테스트판이다 — 제목은 주석이 아니라 **문자열 인자**라 주석 스트립을 통과한다.
   * ★대신 **양성 대조군**(정본 자신이 잡히는가)을 남겨 스캐너 사망과 구별한다.
   */
  it("★평당↔㎡ 배수가 프로덕션 코드에서 이 모듈 밖에 있으면 실패한다(SSOT)", () => {
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.name === "node_modules" || e.name === ".next" || e.name.startsWith(".")) continue;
        if (e.isDirectory() && e.name === "__tests__") continue;
        const f = path.join(dir, e.name);
        if (e.isDirectory()) { walk(f); continue; }
        if (!/\.(ts|tsx)$/.test(e.name)) continue;
        if (/\.(test|spec)\.tsx?$/.test(e.name)) continue;   // 테스트는 모집단 밖
        const src = fs.readFileSync(f, "utf8");
        // 주석·설명은 배제하고 코드 줄만 본다(이 테스트 자신이 그 숫자를 설명에 쓴다)
        const code = src.split("\n").map((l) => l.replace(/\/\/.*$/, "")).join("\n")
          .replace(/\/\*[\s\S]*?\*\//g, "");
        if (/3\.3058/.test(code)) hits.push(path.relative(WEB, f));
      }
    };
    walk(path.join(WEB, "lib"));
    walk(path.join(WEB, "components"));
    walk(path.join(WEB, "store"));
    // ★공허진리 방지 — 조회기가 살아 있는가(정본 자신은 반드시 잡혀야 한다)
    expect(hits, "조회기 사망 — 정본조차 못 찾았다").toContain("lib/construction-cost-params.ts");
    expect(hits, `평당↔㎡ 배수가 여러 곳에 있다: ${hits.join(", ")}`).toEqual([
      "lib/construction-cost-params.ts",
    ]);
  });

  /**
   * ★계획 §5-3 — **두 모집단.** "값이 실린다"만 보면 «아무것도 안 하는 구현»도 통과한다.
   * 미입력이면 **키 자체가 없어야** 백엔드 폴백(연면적 × ₩/㎡)이 보존된다.
   */
  it("미입력 축은 **키를 만들지 않는다** ↔ 입력 축은 값이 실린다", () => {
    expect(buildConstructionParams(null)).toEqual({});
    expect(buildConstructionParams({})).toEqual({});
    // ★0·NaN·음수는 「모름」이지 「0층」이 아니다 — 키가 생기면 폴백을 잃는다
    expect(buildConstructionParams({ floors_above: 0, floors_below: 0, unit_cost_per_pyeong: 0 }))
      .toEqual({});
    expect(buildConstructionParams({ floors_above: NaN, structure_type: "   " })).toEqual({});
    // 대조군 — 값을 주면 반드시 실린다
    expect(buildConstructionParams({ floors_above: 15, floors_below: 3, structure_type: "SRC" }))
      .toEqual({ floor_count_above: 15, floor_count_below: 3, structure_type: "SRC" });
  });

  it("총공사비 직접입력은 산출 축을 **배타적으로** 대체한다", () => {
    // 백엔드는 override 를 먼저 보고 즉시 반환한다 — 산출 축을 같이 보내면
    // 어느 것이 쓰였는지 사후에 못 가른다.
    const p = buildConstructionParams({
      construction_cost_override_won: 50_000_000_000,
      floors_above: 15, structure_type: "SRC", unit_cost_per_pyeong: 8_000_000,
    });
    expect(p).toEqual({ construction_cost_override_won: 50_000_000_000 });
  });

  /**
   * ★★계획 §5-4 — **배선 락.** 위 넷은 전부 `buildConstructionParams` 를 **직접** 태운다.
   *   그래서 **스토어가 그 함수를 아예 안 불러도 넷 다 초록**이다 — 이 저장소가 이름 붙인
   *   *«함수 안에만 변이를 넣으면 5/5 CAUGHT 인데 배선은 무잠금»* 그대로다.
   *   그리고 이 PR 이 고치는 결함 자체가 **«백엔드는 받는데 화면이 안 보낸다»**였다 —
   *   **같은 형태를 내 락에서 재발시키지 않는다.**
   * ★판정은 「이름이 있다」가 아니라 **「호출 결과가 요청 본문에 실린다」**여야 한다.
   */
  it("★스토어가 사용자 공사비 입력을 **요청 body 의 params 로 실제로 싣는다**", () => {
    const src = fs.readFileSync(path.join(WEB, "store/use-feasibility-v2-store.ts"), "utf8");
    const code = src.split("\n").map((l) => l.replace(/\/\/.*$/, "")).join("\n")
      .replace(/\/\*[\s\S]*?\*\//g, "");

    // ① 호출이 실재한다
    expect(code, "스토어가 buildConstructionParams 를 호출하지 않는다 — 입력칸이 무의미해진다")
      .toMatch(/buildConstructionParams\s*\(/);
    // ② 그 **결과가 params 에 전개**된다(이름만 있고 버려지면 무의미)
    const call = code.match(/const\s+(\w+)\s*=\s*buildConstructionParams\s*\(/);
    expect(call, "호출 결과를 변수에 담지 않는다").toBeTruthy();
    const varName = call![1];
    const paramsBlock = code.slice(code.indexOf("const params = {"), code.indexOf("apiClient.postV2"));
    expect(paramsBlock, `params 조립에 ${varName} 가 전개되지 않는다 — 결과가 버려진다`)
      .toContain(`...${varName}`);
    // ③ 그 params 가 **요청 body** 에 실린다
    const body = code.slice(code.indexOf("apiClient.postV2"), code.indexOf("apiClient.postV2") + 400);
    expect(body, "조립한 params 가 요청 body 에 안 실린다").toMatch(/body:\s*\{[^}]*params/);
    // ★공허진리 방지 — 다섯 축이 전부 스토어 입력에서 온다
    for (const k of ["floors_above", "floors_below", "structure_type",
                     "unit_cost_per_pyeong", "construction_cost_override_won"]) {
      expect(code, `스토어가 ${k} 를 리졸버에 넘기지 않는다`).toContain(k);
    }
  });

  /**
   * ★⑤ 미러 락 — 프론트 항목 키가 백엔드 `_OTHER_ITEM_SHARE` 와 **같아야** 한다.
   *   어긋나면 그 항목은 **조용히 무시**되고(백엔드가 모르는 키), 사용자는 값을 넣었는데
   *   반영이 안 된 채 **표준분이 대신 들어간다** — 화면상 그럴듯해서 안 걸린다.
   */
  it("★기타경비 항목 키가 백엔드 몫 표와 일치한다(양방향)", () => {
    const be = fs.readFileSync(
      path.join(REPO, "apps/api/app/services/feasibility/modules/common/cost_blocks.py"), "utf8");
    // ★**선언**에 앵커를 건다 — 첫 판은 `indexOf("_OTHER_ITEM_SHARE")` 라 **내가 쓴 주석의
    //   언급**을 집어 키를 1개만 봤다(저장소가 이름 붙인 «설명문의 낱말을 집는다» 그대로).
    const declAt = be.indexOf("_OTHER_ITEM_SHARE: dict");
    expect(declAt, "몫 표 **선언**을 못 찾았다 — 조회기 사망").toBeGreaterThan(-1);
    const block = be.slice(declAt, be.indexOf("}", declAt));
    const beKeys = [...block.matchAll(/"([a-z_]+_won)"\s*:/g)].map((m) => m[1]).sort();
    expect(beKeys.length, "백엔드 몫 표를 못 읽었다 — 조회기 사망").toBeGreaterThanOrEqual(3);

    const feSrc = fs.readFileSync(path.join(WEB, "lib/construction-cost-params.ts"), "utf8");
    const feBlock = feSrc.slice(feSrc.indexOf("const OTHER_COST_KEYS"), feSrc.indexOf("] as const", feSrc.indexOf("const OTHER_COST_KEYS")));
    const feKeys = [...feBlock.matchAll(/"([a-z_]+_won)"/g)].map((m) => m[1]).sort();
    expect(feKeys.length, "프론트 키 목록을 못 읽었다 — 조회기 사망").toBeGreaterThanOrEqual(3);
    // ★양방향 — 한쪽만 보면 「빠뜨림」과 「군더더기」 중 하나를 못 잡는다
    expect(feKeys, "프론트가 보내는 기타경비 키가 백엔드 몫 표와 다르다").toEqual(beKeys);
  });

  it("★기타경비는 공사비 직접입력과 **함께** 실린다(축이 다르다)", () => {
    const p = buildConstructionParams({
      construction_cost_override_won: 50_000_000_000,
      marketing_cost_won: 100_000_000,
    });
    expect(p.construction_cost_override_won).toBe(50_000_000_000);
    expect(p.marketing_cost_won, "공사비 override 가 기타경비를 삼켰다").toBe(100_000_000);
  });

  /**
   * ★계획 §5-5 — 구조유형 선택지가 **백엔드 정본의 부분집합**이어야 한다.
   * 없는 표기를 보내면 백엔드가 **조용히 RC(1.0)로 떨어진다**(실측: 경고 0).
   */
  it("★구조유형 선택지가 백엔드 계수표에 전부 실재한다", () => {
    const be = fs.readFileSync(
      path.join(REPO, "apps/api/app/services/cost/overview_estimator.py"), "utf8");
    const known = new Set(
      [...be.matchAll(/"([^"]+)"\s*:\s*[01]\.\d+/g)].map((m) => m[1]));
    // ★공허진리 방지 — 표를 못 읽으면 무엇이든 통과한다
    expect(known.size, "백엔드 구조계수표를 못 읽었다 — 조회기 사망").toBeGreaterThanOrEqual(5);
    expect(known.has("RC")).toBe(true);

    const fe = fs.readFileSync(
      path.join(WEB, "components/feasibility/ModuleInputForm.tsx"), "utf8");
    const block = fe.slice(fe.indexOf("const STRUCTURE_TYPES"), fe.indexOf("] as const;", fe.indexOf("const STRUCTURE_TYPES")));
    const feVals = [...block.matchAll(/value:\s*"([^"]*)"/g)].map((m) => m[1]).filter(Boolean);
    expect(feVals.length, "구조 선택지를 못 읽었다 — 조회기 사망").toBeGreaterThanOrEqual(4);

    const unknown = feVals.filter((v) => !known.has(v));
    expect(unknown,
      `백엔드가 모르는 구조표기 — **조용히 RC 로 떨어진다**: ${unknown.join(", ")}`).toEqual([]);
  });
});
