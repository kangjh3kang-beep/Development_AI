/**
 * 법정초과 가드 경고 — **모든 소비 표면**이 렌더한다 (2026-08-24).
 *
 * ## 왜 래칫인가
 *
 * 백엔드 `apply_legal_hotpath_guard` 의 결과를 **네 표면**이 응답에 싣는데
 * 프론트 소비처가 **0** 이었다. 표면을 하나씩 손으로 배선하면 **다음 표면을 또 놓친다**
 * (이 저장소가 반복해 데인 형태 — *"목록형이 아니라 전수/파생형"*).
 *
 * → 백엔드에서 **emit 하는 표면 수**를 세고, 프론트에서 **렌더하는 표면 수**를 세어
 *   둘이 어긋나면 실패시킨다. 새 백엔드 표면이 `integrity_warnings` 를 실으면 여기서 먼저 걸린다.
 *
 * ★소스 검사이지만 주석에 뚫리지 않는다 — `__stripCommentsForScan` 을 경유하고,
 *   그 면역을 **대조군으로 실측**한다(주장하지 않는다).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..", "..");
const API_ROOT = join(WEB_ROOT, "..", "api");

/** 백엔드에서 `integrity_warnings` 를 **응답에 싣는** 파일(실측으로 확정). */
const API_EMITTERS = [
  "routers/auto_zoning.py",
  "app/services/precheck/precheck_service.py",
  "app/services/feasibility/rough_feasibility_orchestrator.py",
] as const;

/** 그 응답을 받아 **화면에 그리는** 프론트 표면. */
const WEB_RENDERERS = [
  "components/analysis/ComprehensiveAnalysisPanel.tsx",
  "components/projects/LandIntelligencePanel.tsx",
  "components/precheck/PreCheckInstantPanel.tsx",
  "components/feasibility/RoughScenarioPanel.tsx",
] as const;

function code(root: string, rel: string): string {
  return __stripCommentsForScan(readFileSync(join(root, rel), "utf8"), rel);
}

/** 파이썬 소스의 **실행되는 줄**만 — `__stripCommentsForScan` 은 TS 파서라 `.py` 를
 *  정직하게 거부한다(거짓 초록 대신 중단). 그래서 여기서는 줄 주석만 걷어낸다.
 *  ★한계를 적어 둔다: 문자열 리터럴 안의 `#` 는 구분하지 못한다. 아래 검사는
 *  **dict 키 형태**(`"integrity_warnings":`)만 보므로 그 한계에 영향받지 않는다. */
function pyCode(rel: string): string {
  return readFileSync(join(API_ROOT, rel), "utf8")
    .split("\n")
    .filter((ln) => !ln.trimStart().startsWith("#"))
    .join("\n");
}

describe("법정초과 가드 — 표면 계약", () => {
  it("★백엔드가 싣는 표면이 실재한다(전제 — 계약의 근거가 사라지면 알아야 한다)", () => {
    let emitting = 0;
    for (const rel of API_EMITTERS) {
      const src = pyCode(rel);
      expect(src.length, `${rel} 를 못 읽었다 — 경로가 바뀌었다`).toBeGreaterThan(200);
      // ★dict 키 형태만 센다 — 주석·설명문에 이름이 등장해도 세지 않는다.
      if (src.includes('"integrity_warnings":')) emitting += 1;
    }
    // ★공허 진리 방지 — 백엔드가 아무 데서도 안 싣게 되면 이 계약 자체가 무의미하다.
    expect(emitting, "백엔드가 integrity_warnings 를 더는 싣지 않는다 — 계약을 재검토하라")
      .toBeGreaterThanOrEqual(3);
  });

  it("★★모든 소비 표면이 IntegrityWarnings 를 렌더한다 — 하나만 배선되면 그 화면은 침묵한다", () => {
    expect(WEB_RENDERERS.length).toBeGreaterThanOrEqual(4);
    for (const rel of WEB_RENDERERS) {
      const src = code(WEB_ROOT, rel);
      expect(src.length, `${rel} 를 못 읽었다`).toBeGreaterThan(200);
      expect(src, `${rel} 가 가드 경고를 렌더하지 않는다 — 그 화면에서 법정초과가 침묵한다`)
        .toContain("<IntegrityWarnings");
      expect(src, `${rel} 가 integrity_warnings 를 넘기지 않는다(빈 items 배선 방지)`)
        .toMatch(/integrity_warnings/);
    }
  });

  it("★대조군 — 검사가 주석에 속지 않는다(면역을 주장하지 않고 실측)", () => {
    const stripped = __stripCommentsForScan(
      "// <IntegrityWarnings integrity_warnings\n/* <IntegrityWarnings */\nconst x = 1;\n",
      "probe.ts",
    );
    expect(stripped).not.toContain("IntegrityWarnings");
    expect(stripped).toContain("const x = 1");
  });

  it("★대조군 — 파이썬 줄 주석도 세지 않는다", () => {
    // `pyCode` 와 같은 규칙을 여기서 재현해 대조한다(구현과 다른 경로로 같은 답).
    const strip = (src: string) =>
      src.split("\n").filter((l) => !l.trimStart().startsWith("#")).join("\n");
    expect(strip('# "integrity_warnings": 주석\nX = 1\n')).not.toContain("integrity_warnings");
    expect(strip('    "integrity_warnings": issues,\n')).toContain('"integrity_warnings":');
  });
});
