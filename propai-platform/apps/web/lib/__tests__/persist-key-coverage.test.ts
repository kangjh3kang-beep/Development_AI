/**
 * 계정 격리 와이프 목록이 **낡지 않게** — 목록형은 반드시 낡는다.
 *
 * ## 무엇이 있었나(실측)
 *
 * `lib/projectSync.ts` 의 접두 목록에 `"propai_verification_"` 이 적혀 있었는데
 * **실제 키는 `propai_verify_`** 였다. 그래서 그 스윕은 **한 번도 매치된 적이 없고**,
 * 계정을 바꿔도 이전 계정의 검증 배지 캐시가 그대로 남았다. 목록은 초록이었다 —
 * 아무도 "목록에 적힌 접두가 실재하는 키인가"를 묻지 않았기 때문이다.
 *
 * ## 이 파일이 잠그는 두 방향
 *
 * ① **죽은 항목**: 목록에 적힌 키/접두가 소스 어디에서도 안 쓰이면 걷는 시늉만 하는 것이다.
 * ② **누락**: 소스에 있는 `propai_*` 저장 키가 목록에도 없고 등재부에도 없으면 잡는다.
 *
 * ★등재부(`WIPE_EXEMPT`)는 **사유를 지닌다** — "왜 안 지우는가"를 못 적으면 그건 누락이다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..");
const SKIP_DIR = new Set(["node_modules", ".next", "dist", "coverage", "__tests__"]);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIR.has(entry)) continue;
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(p);
  }
  return out;
}

/** 소스에 리터럴로 등장하는 `propai_*` / `propai-*` 저장 키(접두 포함). */
function collectStorageKeys(): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const file of walk(WEB_ROOT)) {
    // ★주석·문서의 예시 문자열이 "실사용 키"로 잡히면 안 된다(내 설명 주석이 내 탐지기에
    //   걸렸다 — 이 저장소가 반복해 데인 형태). 실행되는 줄만 본다.
    const src = __stripCommentsForScan(readFileSync(file, "utf8"), file);
    for (const m of src.matchAll(/["'`](propai[-_][A-Za-z0-9_-]*)["'`$]/g)) {
      const key = m[1];
      // `propai-`·`propai_` 처럼 네임스페이스만 남은 조각은 템플릿 리터럴의 앞부분이지 키가 아니다.
      if (key.length <= "propai_".length) continue;
      const where = found.get(key) ?? [];
      where.push(relative(WEB_ROOT, file));
      found.set(key, where);
    }
  }
  return found;
}

/** 지우지 않는 키 — **사유를 지닌다**(뭉뚱그리지 않는다). */
const WIPE_EXEMPT: Record<string, string> = {
  propai_access_token: "인증 토큰 — 계정 격리 와이프의 대상이 아니라 별도 로그아웃 경로가 관리한다",
  propai_refresh_token: "인증 토큰 — 계정 격리 와이프가 아니라 로그아웃·갱신 경로가 수명을 관리한다",
  propai_data_owner: "격리 판정자 자신 — 이걸 지우면 다음 로드에서 소유자 비교가 불가능해진다",
  "propai_pipeline_history__": "계정별 격리 키 — 키 자체가 갈려 있어 와이프가 불필요하고, 지우면 본인 이력이 사라진다(그들이 고친 결함의 재발)",
  // ★#817(다른 세션)이 세션키 커버리지 락에서 **인프라 키로 판정**했다 — 그 판정을 받아
  //   미분류에서 옮긴다. 같은 것을 두 번 조사하지 않는다.
  propai_growth_session: "성장엔진 세션 식별자 — 계정 데이터가 아니라 인프라 키다(#817 이 세션키 락에서 과잉 와이프 대조군으로 고정)",
  // ★2026-08-26 — **해소됐다.** 종전 사유는 *"격리는 계정별 키로 풀어야 한다(별건)"* 이었고,
  //   그 별건이 `lib/account-scoped-storage.ts` 로 착지했다. 두 키는 이제 **레거시 원본**이다:
  //   실제 저장은 `<base>__<uid>` 로 가고(계정별 격리), 이 공유키는 **읽기 전용 승계 원본**이다.
  //   ★그래서 여전히 **지우지 않는다** — 지우면 계정별 키로 옮겨 가기 전의 유료 산출물이
  //     고아가 된다(렌더 3,000원/건 · 등기 권리분석 1,200원/필지). 사유가 *부채*에서
  //     *설계*로 바뀐 것이지, 안 지우는 결론은 같다.
  //   ★사유를 갱신하는 이유: 낡은 사유는 다음 사람에게 **아직 안 고쳐진 것**으로 읽힌다
  //     ("미수정"과 "고쳤으나 다른 이유로 유지"는 다르게 읽혀야 한다).
  //   잠그는 곳: `lib/__tests__/paid-artifact-account-isolation.test.ts`
  "propai-paid-renders":
    "레거시 공유키 — 현행 저장은 계정별 `propai-paid-renders__<uid>`. 이 키는 읽기 전용 승계 원본이라 지우면 승계 전 유료 렌더(3,000원/건)가 고아가 된다",
  "propai-registry-analysis":
    "레거시 공유키 — 현행 저장은 계정별 `propai-registry-analysis__<uid>`. 이 키는 읽기 전용 승계 원본이라 지우면 승계 전 권리분석(1,200원/필지)이 고아가 된다",
  // ★2026-08-26 — **미분류에서 트리아지해 옮겼다.** 유료 산출물은 아니지만 누출 클래스가
  //   같고(계정 전환 뒤 다음 계정이 이전 계정의 프로젝트별 개발계획·수동입력을 봤다),
  //   두 유료 스토어와 **구조가 같아**(`byProject`) 같은 승계 기계로 덮인다.
  //   파생형 락이 이 항목을 지목해서 알았다 — 목록형이었으면 계속 미분류로 남았을 것이다.
  "propai-development-plan":
    "레거시 공유키 — 현행 저장은 계정별 `propai-development-plan__<uid>`. 읽기 전용 승계 원본이라 지우면 승계 전 개발계획(수동입력 포함)이 고아가 된다",
};

/**
 * ★이 락을 켜자마자 드러난 **미분류 저장 키**들. 지금 한 번에 트리아지하지 않는다 —
 *   각각 "지워야 하나"가 제품 판단이고, 근거 없이 목록에 밀어 넣으면 계정 격리를 깨거나
 *   반대로 사용자 데이터를 지운다(파이프라인 이력이 정확히 그 사례였다).
 *
 * ★그래서 **감추지 않고 세어 둔다** — 이 집합은 **늘어나면 실패**한다. 새 키가 조용히
 *   새는 것은 막고, 기존 부채는 초록 안에서 보이게 남긴다.
 *   트리아지해서 목록/등재부로 옮길 때마다 여기서 지운다.
 */
const UNTRIAGED_KEYS = [
  "propai-field-app", "propai-nav-expanded",
  "propai-orchestration", "propai-project-tools-expanded", "propai-pwa-test",
  "propai-report-",
  "propai_ai_insight_", "propai_buildcost_", "propai_cad_help_seen",
  "propai_guest_analysis_count", "propai_legal_discovery_",
  "propai_onboarding_completed", "propai_ref_code", "propai_reg_digest_",
  "propai_visitor_ref",
] as const;

describe("계정 격리 와이프 목록 — 낡음 방지", () => {
  const src = __stripCommentsForScan(
    readFileSync(join(WEB_ROOT, "lib", "projectSync.ts"), "utf8"),
    "lib/projectSync.ts",
  );
  const keys = collectStorageKeys();

  it("★탐지기가 살아 있다 — 이미 아는 키가 실제로 수집된다(공허한 초록 방지)", () => {
    expect(keys.size, "저장 키를 하나도 못 모았다 — 수집기가 죽었거나 경로가 바뀌었다").toBeGreaterThan(5);
    expect(keys.has("propai_access_token")).toBe(true);
    expect(keys.has("propai-project-context")).toBe(true);
  });

  it("★목록에 적힌 접두는 **실재하는 키**여야 한다 — 죽은 항목은 걷는 시늉만 한다", () => {
    // 접두 상수는 정본에서 온다(손으로 적지 않는다). 목록이 참조하는 이름을 소스에서 확인.
    expect(src, "정본 상수를 안 쓰고 문자열을 손으로 적으면 또 갈린다").toContain(
      "VERIFY_CACHE_PREFIX",
    );
    expect(
      src,
      "실재하지 않는 접두(propai_verification_)가 아직 남아 있다 — 한 번도 매치되지 않는다",
    ).not.toMatch(/["']propai_verification_["']/);
  });

  it("★소스의 저장 키가 목록·등재부 어디에도 없으면 걸린다(새 키가 조용히 새지 않게)", () => {
    const covered = (k: string) =>
      src.includes(`"${k}"`) ||
      Object.keys(WIPE_EXEMPT).some((e) => k.startsWith(e)) ||
      (UNTRIAGED_KEYS as readonly string[]).includes(k) ||
      // 접두 스윕으로 덮이는 동적 키
      ["propai_panel_", "propai_scenario_", "propai_verify_"].some((p) => k.startsWith(p));

    const missing = [...keys.keys()].filter((k) => !covered(k)).sort();
    expect(
      missing,
      `와이프 목록·등재부·미분류 래칫 어디에도 없는 **새** 저장 키: ${missing.join(", ")}\n` +
        "→ 지워야 하면 PROJECT_PERSIST_KEYS 에, 안 지워야 하면 WIPE_EXEMPT 에 **사유와 함께** 등재하라.",
    ).toEqual([]);
  });

  it("★미분류 래칫은 **늘어나지 않는다** — 줄이는 방향으로만 움직인다", () => {
    // 죽은 항목도 막는다: 래칫에 적어 놓고 소스에서 사라진 키는 지워야 목록이 안 낡는다.
    const stale = (UNTRIAGED_KEYS as readonly string[]).filter((k) => !keys.has(k));
    expect(stale, `소스에 없는 미분류 키가 남아 있다: ${stale.join(", ")}`).toEqual([]);
  });

  it("★등재부의 사유가 비어 있지 않다 — 부채를 뭉뚱그리지 마라", () => {
    for (const [k, why] of Object.entries(WIPE_EXEMPT)) {
      expect(why.length, `${k} 의 사유가 너무 짧다`).toBeGreaterThan(20);
    }
  });
});
