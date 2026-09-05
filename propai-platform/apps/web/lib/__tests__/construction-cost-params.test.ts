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
