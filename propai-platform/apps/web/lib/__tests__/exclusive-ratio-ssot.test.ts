/**
 * 전용률 **사본 래칫** — 값이 갈리는 것을 기계로 막는다.
 *
 * ## 왜 (2026-09-07 실측)
 *
 * 이 저장소에 전용률 정의가 **여섯 벌**이었고 **값이 갈렸다**:
 *
 *     suggest._JEONYULRYUL              0.747   (백엔드)
 *     area-notation FALLBACK            0.75    ← 갈린 값
 *     PricingBandPanel                  0.747   "미러(신규 계수 금지)" 라고 적어 두고 사본
 *     sale_price_resolver 사례 관례      0.747   (이번에 추가 — 파생으로 바꿈)
 *     dev-type-presets 15유형 표         (이번에 추가 — 근거가 죽어 삭제)
 *
 * ★프론트 안에서만 84㎡ 기준 공급면적이 **112.0㎡(33.88평) ↔ 112.4㎡(34.02평)** 로 갈렸다.
 * ★★***"미러"라고 적는 것은 동기화가 아니다*** — 원본이 움직여도 사본은 따라오지 않고,
 *   **갈렸을 때 아무 소리도 내지 않는다.**
 */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  EXCLUSIVE_TO_SUPPLY_RATIO,
  REF_EXCLUSIVE_SQM,
  REF_SUPPLY_SQM,
  formatAreaDual,
  toPyeonghyeong,
} from "../area-notation";

const WEB = path.resolve(__dirname, "..", "..");

/** 소스 파일 전수(테스트 제외 — 내가 쓴 예시가 위양성이 되는 것을 막는다). */
function sources(): { rel: string; src: string }[] {
  const out: { rel: string; src: string }[] = [];
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (["node_modules", ".next", "__tests__", "dist"].includes(e.name)) continue;
        walk(p);
      } else if (/\.tsx?$/.test(e.name) && !/\.(test|spec)\.tsx?$/.test(e.name)) {
        out.push({ rel: path.relative(WEB, p), src: fs.readFileSync(p, "utf8") });
      }
    }
  };
  for (const d of ["lib", "components", "store", "app"]) {
    const p = path.join(WEB, d);
    if (fs.existsSync(p)) walk(p);
  }
  return out;
}

describe("전용률 SSOT", () => {
  it("★스캔이 실제로 파일을 읽는다(공허진리 차단)", () => {
    const files = sources();
    expect(files.length).toBeGreaterThan(200);
    expect(files.some((f) => f.rel.endsWith("area-notation.ts"))).toBe(true);
  });

  it("정본은 리터럴이 아니라 표준 공급면적에서 **파생**된다", () => {
    // 기대값을 상수에서 파생시킨다 — 리터럴을 적으면 그 리터럴이 일곱 번째 사본이다.
    expect(EXCLUSIVE_TO_SUPPLY_RATIO).toBe(
      Math.round((REF_EXCLUSIVE_SQM / REF_SUPPLY_SQM) * 1000) / 1000,
    );
    // ★사용자 확인과 정합: 전용 84㎡ → 공급 34평형.
    expect(toPyeonghyeong(REF_EXCLUSIVE_SQM)!.pyeong).toBe(
      Math.round(REF_SUPPLY_SQM / 3.305785),
    );
  });

  it("★래칫 — 전용률 리터럴 사본이 늘지 않는다", () => {
    // ★면제는 **사유와 함께**만 존재한다(죽은 면제도 실패시킨다 — 아래 별도 it).
    const EXEMPT: Record<string, string> = {
      "lib/orchestration/node-body-builders.ts":
        "★**다른 축이다.** 여기 `SELLABLE_EFFICIENCY` 는 «연면적→전용면적」이고, " +
        "이 파일의 정본은 «전용→공급 평당가」다. 둘 다 주석에서 「전용률」이라 불려 " +
        "혼동을 부르지만 분모가 다르다. 백엔드 `unit_standards.SELLABLE_EFFICIENCY_" +
        "BY_BUILDING_TYPE` 과 교차언어 계약 테스트 2종이 이미 그 축을 지킨다.",
    };
    // ★위양성 차단 — CSS `opacity: 0.75` 가 전용률로 잡혔다(실측 2건).
    //   숫자만 보면 못 가른다. **앞 문맥**을 함께 본다.
    const RATIO_LITERAL = /(?<!opacity:\s*)(?<!opacity=\{)\b0\.7[4-6][0-9]?\b/;
    const offenders = sources()
      .filter((f) => !f.rel.endsWith("area-notation.ts"))
      .filter((f) => !(f.rel in EXEMPT))
      .filter((f) =>
        stripComments(f.src)
          .split("\n")
          .some((ln) => !/opacity/.test(ln) && RATIO_LITERAL.test(ln)),
      )
      .map((f) => f.rel);
    expect(offenders, `전용률 리터럴 사본이 늘었다: ${offenders.join(", ")}\n` +
      "→ `area-notation` 의 EXCLUSIVE_TO_SUPPLY_RATIO 를 import 하라. " +
      "«미러» 주석은 동기화가 아니다(원본이 움직여도 따라오지 않는다).").toEqual([]);
  });

  it("★면제는 사유와 함께만 — 그리고 죽은 면제는 실패한다", () => {
    // 면제 대상 파일이 사라졌거나 더는 리터럴을 갖지 않으면 면제를 지워야 한다.
    const files = new Map(sources().map((f) => [f.rel, f.src]));
    const rel = "lib/orchestration/node-body-builders.ts";
    const src = files.get(rel);
    expect(src, `면제 목록의 파일이 없다: ${rel}`).toBeDefined();
    // ★양성 대조군 — 면제가 실제로 «필요한» 상태인지 확인한다. 필요 없어졌으면
    //   면제를 남기는 것이 곧 무잠금이다.
    expect(/\b0\.7[4-6][0-9]?\b/.test(stripComments(src!))).toBe(true);
  });

  it("★정본이 **실제로 호출된다** — 임포트 존재는 소비가 아니다", () => {
    // ★★2026-09-07 자체 적발: 첫 판은 `from "…area-notation"` **임포트 존재**만 봤다.
    //   변이(JSX 사용만 지우고 임포트는 남김)가 **통과**했다 — 저장소가 경고한
    //   *"주석 처리 + 임포트 유지 변이에 뚫린다"* 그 형태다.
    //   → **호출 형태(괄호까지)** 로 못 박는다. 그리고 주석은 걷어내고 본다.
    const CALL = /\b(formatAreaDual|formatPyeonghyeong|toPyeonghyeong)\s*\(/;
    const callers = sources()
      .filter((f) => !f.rel.endsWith("area-notation.ts"))
      .filter((f) => CALL.test(stripComments(f.src)))
      .map((f) => f.rel);
    expect(callers.length,
      "area-notation 을 **부르는** 곳이 0이다 — 임포트만 남은 배선은 소비가 아니다.\n" +
      "만들어 놓고 안 쓰면 이 모듈의 락은 초록인 채 화면을 하나도 지키지 않는다.",
    ).toBeGreaterThan(0);
    // 상수도 함께 소비되는지(값 축) — 호출 축과 별개다.
    const constUsers = sources()
      .filter((f) => !f.rel.endsWith("area-notation.ts"))
      .filter((f) => /\bEXCLUSIVE_TO_SUPPLY_RATIO\b|\bREF_EXCLUSIVE_SQM\b/.test(stripComments(f.src)));
    expect(constUsers.length, "정본 상수를 쓰는 곳이 0이다 — 사본이 다시 생겼을 수 있다")
      .toBeGreaterThan(0);
  });

  it("병행 표기가 두 기준을 **각각** 말한다", () => {
    const s = formatAreaDual(84);
    expect(s).toContain("전용");
    expect(s).toContain("공급");
    // 「34」가 공급 쪽에만 붙어야 한다 — 이 판별자가 없으면 옛 모호 형식도 통과한다.
    expect(s.slice(s.indexOf("공급"))).toContain("34");
    expect(s.slice(0, s.indexOf("공급"))).not.toContain("34");
  });
});

/** 주석·JSDoc 제거 — 설명문에 적은 예시값이 위양성이 되는 것을 막는다. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}
