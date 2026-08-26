/**
 * 미지값이 「안심 기본값」으로 접히지 않는다 — 행위 락 + 배선 락 + 파생형 래칫.
 *
 * ## 무엇을 잠그는가
 *
 * 결함: `표[서버값] ?? 표.안심키`. 폴백이 **유효값**이라 「모른다」와 「안전하다고 관측됐다」가
 * 화면에서 구별되지 않는다. 실측 2건(2026-08-27):
 *   · `statusColors[c.status] || statusColors.safe`      → 미지 status 가 **초록**
 *   · `VERDICT_META[result.verdict] || VERDICT_META.warn` → `"FAIL"` 이 **"주의"로 강등**
 *
 * ## 왜 이 형태인가
 *
 * · **두 모집단을 같은 실행에서 가른다.** 미지가 안심값이 아님만 보면 *"전부 unknown 으로
 *   만드는"* 구현도 통과한다 → 정상 입력이 **종전과 같은** 표기를 내는지 대조군으로 함께 본다.
 * · **값 단언이 아니라 관계 단언**을 쓴다. 클래스 문자열을 통째로 못 박으면 디자인 토큰을
 *   다듬을 때마다 깨지는 취약한 락이 되고, 틀린 규약도 초록으로 굳는다.
 * · **배선을 따로 잠근다.** 함수 안에만 변이를 넣으면 호출부 한 줄을 되돌려도 전부 초록이다.
 * · **래칫은 파생형이다.** 손으로 센 목록은 곧 상한이 된다 — 이 결함을 처음 판 동료의
 *   수집 축이 `[A-Z][A-Z0-9_]*` 라 **camelCase 표(`statusColors`)를 구조적으로 못 봤고**,
 *   그게 가장 심각한 1건이었다.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  CHARACTERISTIC_STATUS_COLORS,
  UNKNOWN_CHARACTERISTIC_CLS,
  resolveCharacteristicStatus,
} from "@/lib/land-characteristic-status";
import { __stripCommentsForScan, assertWiredThrough } from "@/lib/source-invariant";
import { resolveKnown } from "@/lib/unknown-value";
import { UNKNOWN_VERDICT_CLS, VERDICT_META, resolveVerdictMeta } from "@/lib/verification-verdict";

/** 추출·수집 실패는 **위반과 다른 예외**로 죽인다(뭉치면 "스캐너가 죽었다"가 "깨끗하다"로 읽힌다). */
class ScannerDeadError extends Error {}

describe("resolveKnown — 미지값을 표의 어떤 값으로도 접지 않는다", () => {
  const TABLE = { safe: "S", warning: "W", danger: "D" } as const;

  it("정상 키는 그대로 돌려준다 [대조군 — 이게 없으면 '전부 unknown' 구현도 통과한다]", () => {
    for (const k of Object.keys(TABLE) as (keyof typeof TABLE)[]) {
      const r = resolveKnown(TABLE, k);
      expect(r.known).toBe(true);
      expect(r.value).toBe(TABLE[k]);
    }
  });

  it("표에 없는 값은 known:false 이고 value 가 표의 어떤 값도 아니다", () => {
    for (const bad of ["위험", "high", "critical", "unknown", "SAFEISH"]) {
      const r = resolveKnown(TABLE, bad);
      expect(r.known).toBe(false);
      expect(r.value).toBeNull();
      expect(Object.values(TABLE)).not.toContain(r.value);
    }
  });

  it("표기 흔들림은 강등이 아니라 **복원**이다", () => {
    for (const shaky of ["SAFE", " safe ", "Safe"]) {
      const r = resolveKnown(TABLE, shaky);
      expect(r.known).toBe(true);
      expect(r.value).toBe(TABLE.safe);
    }
  });

  it("빈 값·비문자열은 미지이며 key 가 null 이다", () => {
    for (const empty of ["", "   ", null, undefined, 3, {}]) {
      const r = resolveKnown(TABLE, empty);
      expect(r.known).toBe(false);
      expect(r.key).toBeNull();
    }
  });

  it("프로토타입 키를 표의 값으로 오인하지 않는다", () => {
    for (const proto of ["toString", "constructor", "__proto__"]) {
      expect(resolveKnown(TABLE, proto).known).toBe(false);
    }
  });

  it("미지값의 원값을 key 로 실어 보낸다(진단 불가는 그 자체로 장애다)", () => {
    expect(resolveKnown(TABLE, "  위험  ").key).toBe("위험");
  });
});

describe("필지 특성 칩 — 미지 status 가 safe(초록)로 떨어지지 않는다", () => {
  it("[대조군] 정상 status 는 종전과 같은 표의 클래스를 낸다", () => {
    for (const k of Object.keys(CHARACTERISTIC_STATUS_COLORS)) {
      const st = resolveCharacteristicStatus(k);
      expect(st.unknown).toBe(false);
      expect(st.cls).toBe(CHARACTERISTIC_STATUS_COLORS[k]);
    }
  });

  it("★미지 status 는 safe 의 클래스가 **아니고**, 표의 어떤 클래스도 아니다", () => {
    // 생산자가 검증 0의 LLM JSON 이라 실제로 이런 값들이 올 수 있다.
    for (const bad of ["위험", "high", "critical", "caution", "OK?"]) {
      const st = resolveCharacteristicStatus(bad);
      expect(st.unknown).toBe(true);
      expect(st.cls).not.toBe(CHARACTERISTIC_STATUS_COLORS.safe);
      expect(Object.values(CHARACTERISTIC_STATUS_COLORS)).not.toContain(st.cls);
      expect(st.cls).toBe(UNKNOWN_CHARACTERISTIC_CLS);
    }
  });

  it("미지 표기가 성공 토큰을 쓰지 않는다(중립이어야 한다)", () => {
    expect(UNKNOWN_CHARACTERISTIC_CLS).not.toContain("--status-success");
    expect(UNKNOWN_CHARACTERISTIC_CLS).not.toContain("--status-error");
  });

  it("danger 가 미지에 가려지지 않는다 — 두 표기가 서로 다르다", () => {
    expect(UNKNOWN_CHARACTERISTIC_CLS).not.toBe(CHARACTERISTIC_STATUS_COLORS.danger);
    expect(CHARACTERISTIC_STATUS_COLORS.danger).not.toBe(CHARACTERISTIC_STATUS_COLORS.safe);
  });
});

describe("AI 검증 배지 — 미지 판정이 warn 으로 강등되지 않는다", () => {
  it("[대조군] 알려진 판정은 종전과 같은 라벨·클래스를 낸다", () => {
    expect(resolveVerdictMeta("pass").label).toBe(VERDICT_META.pass.label);
    expect(resolveVerdictMeta("warn").label).toBe(VERDICT_META.warn.label);
    expect(resolveVerdictMeta("fail").label).toBe(VERDICT_META.fail.label);
    expect(resolveVerdictMeta("fail").cls).toBe(VERDICT_META.fail.cls);
  });

  it("★LLM 표기 흔들림은 복원한다 — \"FAIL\" 이 \"주의\"가 되지 않는다", () => {
    for (const shaky of ["FAIL", " fail ", "Fail"]) {
      const m = resolveVerdictMeta(shaky);
      expect(m.label).toBe(VERDICT_META.fail.label);
      expect(m.label).not.toBe(VERDICT_META.warn.label);
    }
  });

  it("★진짜 미지 판정은 warn 도 pass 도 아니고, 원값을 표면에 싣는다", () => {
    const m = resolveVerdictMeta("오류있음");
    expect(m.label).not.toBe(VERDICT_META.warn.label);
    expect(m.label).not.toBe(VERDICT_META.pass.label);
    expect(m.cls).toBe(UNKNOWN_VERDICT_CLS);
    expect(m.label).toContain("오류있음"); // 진단 가능해야 한다
  });

  it("결과가 없을 때의 미지 표기는 원값 없이도 성립한다", () => {
    const m = resolveVerdictMeta(null);
    expect(m.cls).toBe(UNKNOWN_VERDICT_CLS);
    expect(m.label).not.toBe(VERDICT_META.warn.label);
  });

  it("미지 표기가 성공/경고 토큰을 쓰지 않는다", () => {
    expect(UNKNOWN_VERDICT_CLS).not.toContain("--status-success");
    expect(UNKNOWN_VERDICT_CLS).not.toContain("--status-warning");
  });
});

describe("배선 락 — 호출부를 되돌리면 빨개진다", () => {
  it("필지 특성 칩이 공용 판정을 경유한다", () => {
    assertWiredThrough({
      file: "components/projects/LandIntelligencePanel.tsx",
      // scope 는 레이아웃 클래스로 고른다 — mustContain 을 함의하지 않게(공허한 참 방지).
      scope: /className=\{`flex flex-col gap-1 rounded-lg border p-2/,
      mustContain: "st.cls",
      mustNotContain: /statusColors/,
      minMatches: 1,
    });
  });

  it("검증 배지가 공용 판정을 경유한다", () => {
    assertWiredThrough({
      file: "components/common/VerificationBadge.tsx",
      scope: /const meta = result \?/,
      mustContain: "resolveVerdictMeta",
      mustNotContain: /VERDICT_META/,
      minMatches: 1,
    });
  });
});

/* ── 파생형 래칫 — 새 「안심 폴백」이 들어오면 빨개진다 ───────────────────────── */

const WEB_ROOT = resolve(process.cwd());
const SKIP_DIRS = new Set(["node_modules", ".next", ".turbo", "e2e", "dist", "coverage"]);

/** `.ts/.tsx` 를 **파생**으로 모은다 — 손 목록은 곧 상한이 된다. */
function collectSources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name) || name.startsWith(".")) continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) collectSources(full, out);
    else if (/\.tsx?$/.test(name) && !/\.(test|spec)\.tsx?$/.test(name)) out.push(full);
  }
  return out;
}

/**
 * `표[키] ?? 표.기본` / `표[키] || 표["기본"]` 형태를 **대소문자 무관**으로 집는다.
 * ★이 결함을 처음 판 축이 `[A-Z][A-Z0-9_]*` 라 **camelCase 표(`statusColors`)를 구조적으로
 *   배제**했고, 그게 가장 심각한 1건이었다. 여기서는 배제하지 않는다.
 */
const FALLBACK_SHAPE =
  /([A-Za-z_$][A-Za-z0-9_$]*)\s*\[[^\]]*\]\s*(?:\?\?|\|\|)\s*\1\s*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[\s*"[^"]*"\s*\])/g;

/**
 * 이 형태 자체는 흔하고 대부분 무해하다(실측: 전체 46파일). 결함이 되는 것은 표가
 * **상태·심각도를 말할 때**뿐이므로 **표 이름**으로 좁힌다(실측 14파일).
 *
 * ★왜 「안심어」로 좁히지 않는가: 그것이 이 결함을 처음 판 축을 문 함정이다 —
 *   `SEVERITY_STYLES ?? .info` 는 정규식은 통과했는데 **키워드 목록에 `info` 가 없어**
 *   탈락했다. **모집단을 자른 것이 수집기가 아니라 그 뒤의 필터**였고, 필터의 절단은
 *   수집기의 절단보다 조용하다. 그래서 여기서는 폴백 **값**이 아니라 표의 **정체**를 본다.
 *
 * ★알려진 한계(정직하게 적는다): 상태를 다루면서도 이름에 상태 어휘가 없는 표
 *   (`APP_STYLE`·`LAYER_FILL` 등)는 **이 래칫이 못 본다.** 그 자리들은 2026-08-27 에
 *   손으로 판정했고(전부 오탐) 아래 목록에 남겨 둔다 — 이름이 바뀌면 자동으로 걸린다.
 */
const STATUS_TABLE_NAME =
  /status|severity|level|risk|verdict|confidence|grade|state|health|priority|sev/i;

/**
 * 판정이 끝난 자리 — **각 항목에 사유가 있어야 한다**(사유 없는 면제는 부채를 숨긴다).
 * 여기 없는 새 항목이 나타나면 실패한다. 항목이 **사라지는 것**은 허용한다(다른 세션이
 * 같은 결함을 고치는 중이라 머지 순서에 따라 줄어들 수 있다).
 */
const ADJUDICATED: Record<string, string> = {
  "components/analysis/ComprehensiveAnalysisPanel.tsx":
    "진짜 결함(RISK_LEVEL_STYLE ?? \"낮음\"). 동료 세션이 fix/risk-level-label-parity 에서 수정 중 — 머지되면 이 항목은 사라진다.",
  "components/analysis/FieldAuditNotice.tsx":
    "오탐(도달 불가). 백엔드 field_audit/contracts.py 가 pydantic Literal[\"P0\",\"P1\",\"P2\"] + extra=\"forbid\" 로 닫혀 있다(대입 리터럴 전수 P2×4·P1×3·P0×1, 이탈 0).",
  "components/feasibility/AIRecommendationPanel.tsx":
    "오탐(도달 불가). 생산자 ai_recommendation.py 가 critical/warning/info 3개로 닫혀 있고 프론트 표와 정확히 일치한다. ★부채: 백엔드에 severity 가 추가되면 info(가장 약함)로 접히므로 그때 재판정할 것.",
  "components/feasibility/AutoRecommendPanel.tsx":
    "오탐. GRADE_COLORS ?? .C 는 A~F 의 **중간**(amber)이라 안심 방향이 아니다. 다만 미지를 C 로 단정하는 것은 별개 성격의 부정확이다.",
  "components/feasibility/LegacyLedgerTable.tsx":
    "★정답 패턴. VERDICT_STYLE ?? .UNKNOWN 이고 UNKNOWN 은 \"판정 불가\" + 중립색이다. 소스 주석에 「판정 불가를 초록으로 그리지 않는다」고 명시돼 있다 — 이 파일이 이 저장소의 본보기다.",
  "components/map/SatongMultiMap.tsx":
    "오탐 2건. PRESALE_STATUS_COLORS ?? \"미정\" 은 정직한 미상 표기이고, AUCTION_STATUS_COLORS ?? \"진행\" 은 #ef4444 빨강이라 안심 방향이 아니다.",
  "components/orchestration/PersonaPanel.tsx":
    "오탐. STATUS_BADGE ?? .partial 은 \"일부 미확보\" + --text-tertiary 중립 회색으로, 오히려 정직한 방향이다.",
  "components/precheck/PreCheckWorkspace.tsx":
    "오탐. LEVEL_CHIP.low 는 위험도가 아니라 **신호 강도 약함**이고 색이 중립 회색이다(high=--status-success 초록).",
  "components/precheck/ZoningSignalMap.tsx":
    "오탐. LEVEL_COLOR.low = #64748b 회색 중립. 위 항목과 같은 이유.",
  "components/projects/DomainSummaryCard.tsx":
    "오탐. CONFIDENCE_META.low = { label:\"신뢰도 낮음\", token:\"--status-error\" } — 빨강이라 안심 방향이 아니다.",
  "components/sales-app/FieldHome.tsx":
    "오탐(도달 불가). 생산자 sales/views.py:216 이 grade = \"A\" if score>=60 else \"B\" if score>=30 else \"C\" 로 A/B/C 에 닫혀 있고 GRADE_CLASS 와 정확히 일치한다.",
};

describe("파생형 래칫 — 새 안심 폴백이 들어오면 실패한다", () => {
  const files = collectSources(WEB_ROOT);

  /** 상태성 표의 안심 폴백만 골라낸다. */
  function statusFallbacksIn(src: string): string[] {
    const hits: string[] = [];
    FALLBACK_SHAPE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = FALLBACK_SHAPE.exec(src)) !== null) {
      if (STATUS_TABLE_NAME.test(m[1])) hits.push(m[1]);
    }
    return hits;
  }

  it("[조회기 생존] 스캔이 실제로 파일을 읽었다", () => {
    if (files.length < 500) {
      throw new ScannerDeadError(
        `수집 ${files.length}건 — apps/web 규모(실측 1,063)에 못 미친다. 수집기가 죽었다.`,
      );
    }
    expect(files.length).toBeGreaterThan(500);
  });

  it("[양성 대조군] 실제로 있었던 결함 3형태를 전부 집는다", () => {
    const known = [
      'RISK_LEVEL_STYLE[devPlans.risk_level as string] || RISK_LEVEL_STYLE["낮음"]',
      "statusColors[c.status] || statusColors.safe", // camelCase — 원래 축이 놓친 것
      "VERDICT_META[result.verdict] || VERDICT_META.warn",
    ];
    for (const probe of known) {
      if (statusFallbacksIn(probe).length === 0) {
        throw new ScannerDeadError(`패턴이 알려진 결함 형태를 못 집는다: ${probe}`);
      }
    }
  });

  it("[특이도] 상태와 무관한 표·정상 코드를 신고하지 않는다", () => {
    expect(statusFallbacksIn("const y = a[k] ?? b.safe;")).toEqual([]);
    expect(statusFallbacksIn("const t = byGroup[g] ?? byGroup.fallbackRows;")).toEqual([]);
    expect(statusFallbacksIn("const c = cache[key] ?? cache.miss;")).toEqual([]);
  });

  it("★판정되지 않은 새 안심 폴백이 없다", () => {
    const found: string[] = [];
    for (const full of files) {
      const src = __stripCommentsForScan(readFileSync(full, "utf-8"), full);
      if (statusFallbacksIn(src).length > 0) {
        found.push(relative(WEB_ROOT, full).replace(/\\/g, "/"));
      }
    }
    if (found.length === 0) {
      throw new ScannerDeadError(
        "발견 0건 — 판정된 자리가 아직 남아 있어야 한다(오탐으로 남긴 것들). 스캔이 죽었다.",
      );
    }
    const unjudged = found.filter((f) => !(f in ADJUDICATED));
    expect(unjudged, `판정되지 않은 안심 폴백:\n${unjudged.join("\n")}`).toEqual([]);
  });

  it("★내가 고친 두 파일은 더 이상 그 형태가 아니다", () => {
    for (const f of [
      "components/projects/LandIntelligencePanel.tsx",
      "components/common/VerificationBadge.tsx",
    ]) {
      const src = __stripCommentsForScan(readFileSync(join(WEB_ROOT, f), "utf-8"), f);
      expect(statusFallbacksIn(src), `${f} 에 안심 폴백이 남아 있다`).toEqual([]);
    }
  });

  it("면제에는 전부 사유가 적혀 있다", () => {
    for (const [file, reason] of Object.entries(ADJUDICATED)) {
      expect(reason.length, `${file} 의 사유가 비었다`).toBeGreaterThan(20);
    }
  });
});
