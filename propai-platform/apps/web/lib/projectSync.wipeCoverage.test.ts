/**
 * ★계정 격리 — **와이프 목록이 세션 키 전수를 덮는가**(파생형·fail-closed).
 *
 * ## 왜 인스턴스 테스트로는 부족한가
 *
 * `projectSync.satongLeak.test.ts` 는 키를 **하나씩** 잠근다. 그래서 누군가 새 키를 만들면
 * 그 테스트는 **초록인 채로** 구멍이 생긴다. 실제로 그렇게 났다 —
 * `clearAllProjectData` 주석이 *"새 뷰 캐시 키는 만드는 즉시 이 목록에 등재한다"* 를
 * **W1·W2·W3·W4 네 번** 반복하는데도 2026-08-24 실측에서 **2건이 빠져 있었다**:
 *
 *   · `propai:market-report:active-job` — `{jobId, startedAt, **address**}` 저장.
 *     이전 계정이 분석한 **부지 주소**가 다음 계정 화면에 복원될 수 있었다.
 *   · `propai:design-audit:active-job` — **컴포넌트 안에 숨어 있어** 구조적으로 누락
 *     (교훈이 예측한 그대로: *"키를 컴포넌트 안에 숨기면 구조적으로 누락된다"*).
 *
 * 산문 지시가 네 번 반복돼도 못 막았다 → **파생형 락**으로 바꾼다.
 *
 * ## 계약 (fail-closed)
 *
 * 소스에서 sessionStorage 키를 **전수 추출**하고, 각각이 다음 중 하나여야 한다:
 *   ① `clearAllProjectData` 가 지운다            → 계정 격리 대상
 *   ② 아래 `INFRA_KEYS` 에 **사유와 함께** 등재   → 계정 무관 인프라 키
 *
 * 새 키를 만들면 **둘 중 하나를 반드시 선택**해야 한다 — 잊는 것이 불가능해진다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";

import { clearAllProjectData } from "@/lib/projectSync";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, "..");

/**
 * 계정과 무관한 인프라 키 — 지우면 **오히려 해롭다**. 사유를 함께 적는다.
 * ★여기 등재는 "면제"가 아니라 **판단의 기록**이다. 사유 없이 추가하지 말 것.
 */
const INFRA_KEYS: Record<string, string> = {
  propai_growth_session: "성장 계측 세션 UUID — 계정이 아니라 브라우저 세션 식별자",
  kakao_oauth_state: "OAuth CSRF state — 로그인 진행 중 소비되며 계정 데이터가 아니다",
  naver_oauth_state: "OAuth CSRF state — 위와 같음",
  google_oauth_state: "OAuth CSRF state — 위와 같음",
  "vworld-relay": "VWorld 릴레이 서킷브레이커 — 인프라 상태이지 사용자 데이터가 아니다",
};

/** 소스 전수에서 sessionStorage 키 **문자열 리터럴**을 뽑는다. */
function sessionKeyLiterals(): Set<string> {
  const out = new Set<string>();
  // 상수 선언에서(정본 패턴 — 대부분 이 형태다).
  const files = [
    "lib/market-report-job.ts",
    "components/design-audit/DesignAuditWorkspace.tsx",
    "components/precheck/satong-map-selection.ts",
    "lib/growth/event-collector.ts",
  ];
  for (const rel of files) {
    let src = "";
    try { src = readFileSync(resolve(WEB, rel), "utf-8"); } catch { continue; }
    const live = src.split("\n")
      .map((ln) => ln.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");
    for (const m of live.matchAll(
      /(?:export\s+)?const\s+[A-Z_]*(?:KEY|PREFIX)[A-Z_]*\s*=\s*["'`]([^"'`]+)["'`]/g,
    )) out.add(m[1]);
  }
  return out;
}

describe("★계정 격리 — 세션 키 와이프 커버리지(파생형)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it("추출이 비어 있지 않다(공허한 초록 방지)", () => {
    // ★이 가드가 단언 **앞에** 있어야 한다 — 정규식이 깨져 0건이면 아래가 공허하게 참이다.
    expect(sessionKeyLiterals().size).toBeGreaterThanOrEqual(4);
  });

  it("★실제 와이프 동작 — 진행 잡 페이로드가 계정 전환에 살아남지 않는다", () => {
    // 값 검사가 아니라 **동작** 검사다(소스에 이름만 있고 안 지우면 소스검사는 통과한다).
    window.sessionStorage.setItem(
      "propai:market-report:active-job",
      JSON.stringify({ jobId: "prev", startedAt: 1, address: "이전 계정 부지 주소" }),
    );
    window.sessionStorage.setItem(
      "propai:design-audit:active-job",
      JSON.stringify({ jobId: "prev-audit", startedAt: 1 }),
    );

    clearAllProjectData();

    expect(window.sessionStorage.getItem("propai:market-report:active-job")).toBeNull();
    expect(window.sessionStorage.getItem("propai:design-audit:active-job")).toBeNull();
  });

  it("★대조군 — 인프라 키는 **지우지 않는다**(과잉 와이프도 결함이다)", () => {
    // 전부 지우는 것은 잠금이 아니라 파괴다. OAuth state 를 지우면 로그인이 깨진다.
    window.sessionStorage.setItem("kakao_oauth_state", "csrf-token");
    window.sessionStorage.setItem("propai_growth_session", "uuid");

    clearAllProjectData();

    expect(window.sessionStorage.getItem("kakao_oauth_state")).toBe("csrf-token");
    expect(window.sessionStorage.getItem("propai_growth_session")).toBe("uuid");
  });

  it("★fail-closed — 모든 세션 키는 '와이프' 아니면 '사유 있는 인프라 등재' 둘 중 하나다", () => {
    // ★소스 문자열 매칭이 아니라 **동작**으로 판정한다.
    //   첫 구현은 상수명↔리터럴을 문자열로 대조하다 **위양성 4건**을 냈다(실제로 지워지는
    //   satong_* 키들을 미등재로 신고). 가드의 위양성도 결함이다 — 정상 코드를 막는다.
    //   전부 심어 놓고 지운 뒤 **살아남은 것**을 보면 heuristic 이 필요 없다.
    const keys = [...sessionKeyLiterals()];
    expect(keys.length).toBeGreaterThanOrEqual(4);       // 공허한 초록 방지
    for (const k of keys) window.sessionStorage.setItem(k, "probe");

    clearAllProjectData();

    const survived = keys.filter((k) => window.sessionStorage.getItem(k) !== null);
    const unaccounted = survived.filter((k) => !(k in INFRA_KEYS));
    expect(
      unaccounted,
      `세션 키가 와이프되지도, INFRA_KEYS 에 등재되지도 않았다 — 계정 전환 시 이전 계정 ` +
      `데이터가 남는다: ${unaccounted.join(", ")}\n` +
      "→ 계정 데이터면 clearAllProjectData 에, 인프라면 INFRA_KEYS 에 **사유와 함께** 등재하라.",
    ).toEqual([]);
  });

  it("INFRA_KEYS 등재에는 **사유**가 붙어 있다(빈 면제 금지)", () => {
    for (const [k, why] of Object.entries(INFRA_KEYS)) {
      expect(why.length, `${k} 의 면제 사유가 비었다`).toBeGreaterThan(10);
    }
  });
});
