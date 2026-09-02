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
  type KnownCharacteristicStatus,
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

  it("빈 값·null·undefined 는 미지이며 key 가 null 이다", () => {
    for (const empty of ["", "   ", null, undefined]) {
      const r = resolveKnown(TABLE, empty);
      expect(r.known).toBe(false);
      expect(r.key).toBeNull();
    }
  });

  it("★비문자열도 미지이되 **원값을 버리지 않는다**(진단 불가는 그 자체로 장애다)", () => {
    // 종전엔 key 를 null 로 버려서 배지가 "판정 불명"만 띄웠다 — 무엇이 왔는지 알 수 없었다.
    expect(resolveKnown(TABLE, 3)).toMatchObject({ known: false, value: null, key: "3" });
    expect(resolveKnown(TABLE, true)).toMatchObject({ known: false, key: "true" });
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
    // ★키를 유니온으로 받는다 — 표가 닫힌 유니온에 결속돼 string 색인이 tsc 에서 막힌다
    //   (그 막힘 자체가 「표가 실제로 결속됐다」는 증거다).
    const keys = Object.keys(CHARACTERISTIC_STATUS_COLORS) as KnownCharacteristicStatus[];
    for (const k of keys) {
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

  it("미지 표기가 **어떤 상태 토큰도** 쓰지 않는다(중립이어야 한다)", () => {
    // 특정 토큰 2개만 배제하면 --status-info 로 바꿔도 통과한다 — 전 계열을 배제한다.
    expect(UNKNOWN_CHARACTERISTIC_CLS).not.toMatch(/--status-/);
    expect(UNKNOWN_CHARACTERISTIC_CLS).not.toMatch(/\b(?:red|green|emerald|rose)-\d/);
  });

  /**
   * ★동료 세션 `-0b` 의 실측 경고를 반영한 형태다: *"「구별된다」를 문자열 부등호로 잠그면
   * 잠긴 게 아니다 — 같은 초록을 다른 철자로 쓰면 통과한다"*(그쪽 락이 그렇게 뚫렸다).
   *
   * 그래서 **철자가 아니라 토큰 정체**로 본다. `danger` 값을 초록으로 바꾸는 공격이
   * `text-green-500` 이든 `--status-success` 든 **성공 계열 토큰을 쓰는 순간** 잡힌다.
   *
   * ★한계(정직하게): 이것도 **완전한 색 구별 검사는 아니다.** 서로 다른 토큰이
   * 시각적으로 같은 색일 가능성은 남는다 — 그건 oklab 거리로 재야 하고 **이 PR 의
   * 계약(미지값 접힘)이 아니다.** 여기서는 「위험이 안전처럼 보이는 것」만 막는다.
   */
  it("★danger·warning 이 **성공 계열 토큰을 쓰지 않는다**(철자가 아니라 토큰으로 본다)", () => {
    const SUCCESSISH = /--status-success|\b(?:green|emerald|lime|teal)-\d/;
    for (const k of ["danger", "warning"] as const) {
      expect(
        CHARACTERISTIC_STATUS_COLORS[k],
        `${k} 가 성공 계열 색을 쓴다 — 위험이 안전처럼 보인다`,
      ).not.toMatch(SUCCESSISH);
    }
    // [대조군] safe 는 성공 계열이어야 한다 — 없으면 "전부 회색" 구현도 통과한다.
    expect(CHARACTERISTIC_STATUS_COLORS.safe).toMatch(SUCCESSISH);
    // 미지는 셋 중 어느 것과도 같지 않다.
    expect(Object.values(CHARACTERISTIC_STATUS_COLORS)).not.toContain(UNKNOWN_CHARACTERISTIC_CLS);
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
  it("필지 특성 칩이 공용 판정 결과를 **렌더한다**", () => {
    assertWiredThrough({
      file: "components/projects/LandIntelligencePanel.tsx",
      // scope 는 레이아웃 클래스로 고른다 — mustContain 을 함의하지 않게(공허한 참 방지).
      scope: /className=\{`flex flex-col gap-1 rounded-lg border p-2/,
      mustContain: "statusChip.cls",
      mustNotContain: /statusColors/,
      minMatches: 1,
    });
  });

  /**
   * ★이 케이스가 없어서 결함이 **락 23건 전부 초록인 채 복원 가능**했다.
   *
   * 위 락은 `assertWiredThrough` 가 **줄 단위**라 "st.cls 가 쓰였는가"만 본다 —
   * `st` 가 **어디서 왔는지**는 그 락 밖이다. 독립 적대 리뷰가 실제로 뚫었다:
   *
   *   const SAFE_FALLBACK = CHARACTERISTIC_STATUS_COLORS.safe;
   *   const statusChip = { cls: CHARACTERISTIC_STATUS_COLORS[c.status] || SAFE_FALLBACK, unknown: false };
   *   → 23 passed. SURVIVED.
   *
   * 변이를 **함수 안에만** 넣으면 전부 CAUGHT 인데 **배선은 무잠금**이던 그 자리다.
   */
  it("★필지 특성 칩이 공용 판정을 **유도한다**(별칭 상수로 되돌리면 빨개진다)", () => {
    assertWiredThrough({
      file: "components/projects/LandIntelligencePanel.tsx",
      scope: /const statusChip = /,
      mustContain: "resolveCharacteristicStatus",
      mustNotContain: /CHARACTERISTIC_STATUS_COLORS\s*\[/,
      minMatches: 1,
    });
  });

  it("★패널이 색 표를 직접 들여오지 않는다(우회 경로 차단)", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, "components/projects/LandIntelligencePanel.tsx"), "utf-8"),
      "components/projects/LandIntelligencePanel.tsx",
    );
    expect(src).not.toContain("CHARACTERISTIC_STATUS_COLORS");
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
const STATUS_SEGMENTS = new Set([
  "status", "severity", "risk", "verdict", "confidence", "grade", "level",
]);

/**
 * 식별자를 **세그먼트로 갈라 정확일치**시킨다. 부분일치로 하면 정상 코드를 위반으로
 * 신고한다 — 독립 리뷰 실측 위양성: `stateMachine`·`levelsByFloor`·`severalRenderers`·
 * `upgradeSteps`·`realEstateMap`(부동산 저장소에서 특히 위험). **가드의 위양성도 결함이다.**
 */
function isStatusTable(name: string): boolean {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .some((seg) => STATUS_SEGMENTS.has(seg.toLowerCase()));
}

/**
 * 판정이 끝난 자리 — **각 항목에 사유가 있어야 한다**(사유 없는 면제는 부채를 숨긴다).
 * 여기 없는 새 항목이 나타나면 실패한다. 항목이 **사라지는 것**은 허용한다(다른 세션이
 * 같은 결함을 고치는 중이라 머지 순서에 따라 줄어들 수 있다).
 */
type Adjudication = {
  readonly reason: string;
  /** 다른 세션이 고치는 중이라 **사라질 수 있는** 항목. 그 외에는 사라지면 실패한다. */
  readonly transient?: true;
};

const ADJUDICATED: Record<string, Adjudication> = {
  "components/analysis/ComprehensiveAnalysisPanel.tsx":
    {
      transient: true,
      reason:
        "★진짜 결함(RISK_LEVEL_STYLE ?? \"낮음\"). 동료 세션 PR #877 에서 수정 중 — 머지되면 이 항목이 사라지므로 transient 다. 이 저장소에서 유일하게 「고쳐야 하는데 면제된」 항목이라 아래 it.todo 로도 초록 안에 드러낸다.",
    },
  "components/analysis/FieldAuditNotice.tsx":
    { reason: "오탐(도달 불가). 백엔드 field_audit/contracts.py 가 pydantic Literal[\"P0\",\"P1\",\"P2\"] + extra=\"forbid\" 로 닫혀 있다(대입 리터럴 전수 P2×4·P1×3·P0×1, 이탈 0)." },
  "components/feasibility/AIRecommendationPanel.tsx":
    { reason: "오탐(도달 불가). 생산자 ai_recommendation.py 가 critical/warning/info 3개로 닫혀 있고 프론트 표와 정확히 일치한다. ★부채: 백엔드에 severity 가 추가되면 info(가장 약함)로 접히므로 그때 재판정할 것." },
  "components/feasibility/AutoRecommendPanel.tsx":
    { reason: "오탐. GRADE_COLORS ?? .C 는 A~F 의 **중간**(amber)이라 안심 방향이 아니다. 다만 미지를 C 로 단정하는 것은 별개 성격의 부정확이다." },
  "components/feasibility/LegacyLedgerTable.tsx":
    { reason: "★정답 패턴. VERDICT_STYLE ?? .UNKNOWN 이고 UNKNOWN 은 \"판정 불가\" + 중립색이다. 소스 주석에 「판정 불가를 초록으로 그리지 않는다」고 명시돼 있다 — 이 파일이 이 저장소의 본보기다." },
  "components/map/SatongMultiMap.tsx":
    { reason: "오탐 2건. PRESALE_STATUS_COLORS ?? \"미정\" 은 정직한 미상 표기이고, AUCTION_STATUS_COLORS ?? \"진행\" 은 #ef4444 빨강이라 안심 방향이 아니다." },
  "components/orchestration/PersonaPanel.tsx":
    { reason: "오탐. STATUS_BADGE ?? .partial 은 \"일부 미확보\" + --text-tertiary 중립 회색으로, 오히려 정직한 방향이다." },
  "components/precheck/PreCheckWorkspace.tsx":
    { reason: "오탐. LEVEL_CHIP.low 는 위험도가 아니라 **신호 강도 약함**이고 색이 중립 회색이다(high=--status-success 초록)." },
  "components/precheck/ZoningSignalMap.tsx":
    { reason: "오탐. LEVEL_COLOR.low = #64748b 회색 중립. 위 항목과 같은 이유." },
  "components/projects/DomainSummaryCard.tsx":
    { reason: "오탐. CONFIDENCE_META.low = { label:\"신뢰도 낮음\", token:\"--status-error\" } — 빨강이라 안심 방향이 아니다." },
  "components/sales-app/FieldHome.tsx":
    { reason: "오탐(도달 불가). 생산자 sales/views.py:216 이 grade = \"A\" if score>=60 else \"B\" if score>=30 else \"C\" 로 A/B/C 에 닫혀 있고 GRADE_CLASS 와 정확히 일치한다." },
};

describe("파생형 래칫 — 새 안심 폴백이 들어오면 실패한다", () => {
  const files = collectSources(WEB_ROOT);

  /** 상태성 표의 안심 폴백만 골라낸다. */
  function statusFallbacksIn(src: string): string[] {
    const hits: string[] = [];
    FALLBACK_SHAPE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = FALLBACK_SHAPE.exec(src)) !== null) {
      if (isStatusTable(m[1])) hits.push(m[1]);
    }
    return hits;
  }

  it("[조회기 생존] 스캔이 실제로 파일을 읽었다", () => {
    if (files.length < 500) {
      throw new ScannerDeadError(
        `수집 ${files.length}건 — 이 수집기 모집단(테스트 제외 .ts/.tsx) 실측 **699** 에 못 미친다. 수집기가 죽었다.`,
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
    // ★독립 리뷰가 실측한 위양성들 — 부분일치로 좁히면 이 정상 코드들이 빨개진다.
    for (const legit of [
      "const a = stateMachine[ev] ?? stateMachine.idle;",
      "const b = levelsByFloor[i] ?? levelsByFloor.ground;",
      "const c = severalRenderers[k] ?? severalRenderers.plain;",
      "const d = upgradeSteps[v] ?? upgradeSteps.first;",
      "const e = realEstateMap[k] ?? realEstateMap.def;",
    ]) {
      expect(statusFallbacksIn(legit), `정상 코드를 위반으로 신고했다: ${legit}`).toEqual([]);
    }
  });

  /** 안심 폴백을 가진 파일(상대경로)을 전수로 모은다. */
  function scanFound(): string[] {
    const hits: string[] = [];
    for (const full of files) {
      const src = __stripCommentsForScan(readFileSync(full, "utf-8"), full);
      if (statusFallbacksIn(src).length > 0) {
        hits.push(relative(WEB_ROOT, full).replace(/\\/g, "/"));
      }
    }
    return hits;
  }

  it("★판정되지 않은 새 안심 폴백이 없다", () => {
    const found = scanFound();
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
    for (const [file, adj] of Object.entries(ADJUDICATED)) {
      expect(adj.reason.length, `${file} 의 사유가 비었다`).toBeGreaterThan(20);
    }
  });

  /**
   * ★죽은 면제도 실패시킨다(CLAUDE.md §G-2 36). 고쳐졌는데 면제가 남으면 다음 사람이
   * "여긴 판정 끝났다"고 읽고 지나간다 — 면제는 초록 안에 숨는 부채다.
   * `transient` 만 예외다(다른 세션이 고치는 중이라 머지 순서로 사라질 수 있다).
   */
  it("★죽은 면제가 없다 — 고쳐진 자리의 면제는 지운다", () => {
    const found = new Set(scanFound());
    const dead = Object.entries(ADJUDICATED)
      .filter(([f, adj]) => !adj.transient && !found.has(f))
      .map(([f]) => f);
    expect(dead, `이미 고쳐졌거나 사라진 면제(지워야 한다):\n${dead.join("\n")}`).toEqual([]);
  });

  it.todo(
    "★부채: ComprehensiveAnalysisPanel 의 RISK_LEVEL_STYLE ?? \"낮음\" 은 **진짜 결함**인데 " +
      "지금 면제로 초록 안에 있다 — 동료 PR #877 머지 후 이 면제를 지우고 이 todo 를 닫는다.",
  );
});
