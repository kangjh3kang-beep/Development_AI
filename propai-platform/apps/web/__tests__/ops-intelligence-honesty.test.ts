/**
 * 운영 인텔리전스 — **추정을 분석으로 보이게 하지 않는다**(무목업·정직 표기).
 *
 * ★사실관계(2026-08-13 실측): `/en/maintenance` 의 "정비 분석" 버튼을 눌러도 **API 요청이 0건**이고,
 *   `OperationsIntelligenceWorkspaceClient` 가 폼 입력값으로 **브라우저에서 산술**해 결과를 만든다
 *   (각 실행부에 `setTimeout` 가짜 지연만 있다). 백엔드에는 해당 라우터가 없다(DB 테이블만 존재).
 *   그런데 화면 문구는 *"설비의 **센서 기반** 예지 정비"* · *"✓ 설비 IoT 센서 22개소 실시간 연동"* ·
 *   *"✓ 예지 정비(Predictive ML) 모델 가동"* 이라고 **사실처럼 단언**하고 있었다.
 *
 * ★이 파일이 잠그는 것은 **문구와 전제**다:
 *   ① 거짓 주장 문구가 **다시 들어오지 않는다**(3개 로케일 전부)
 *   ② 아직 로컬 산출이라는 **전제**가 유지된다(서버로 배선되면 여기서 빨강 → 함께 갱신)
 *   ※ 고지의 **개수·자리**는 소스가 아니라 렌더로 잠근다 —
 *      짝 파일 `ops-intelligence-notice-placement.test.tsx`.
 *
 * ※ 범위: 이 커밋은 **증명한 것만** 고쳤다. 같은 `modulePlaceholders` 사전에는 검증하지 않은
 *   사실 단언이 더 있다(실측 27개 모듈·37개 항목). 그것들은 모듈별 확인 없이 손대지 않는다 —
 *   검증 안 한 주장을 다른 주장으로 바꾸는 것도 같은 잘못이다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const LOCALES = ["ko", "en", "zh-CN"] as const;

/** 로케일별 "미연결"의 실제 표기 — 한 언어의 단어를 전 로케일에 요구하지 않는다. */
const UNWIRED_MARK: Record<(typeof LOCALES)[number], RegExp> = {
  ko: /미연결|연결되지 않/,
  en: /not connected/i,
  "zh-CN": /未接入|尚未接入/,
};

/** 되돌아오면 안 되는 거짓 주장(실측된 원문). */
const FALSE_CLAIMS = [
  "센서 기반 예지",
  "IoT 센서 22개소",
  "Predictive ML",
];

describe("운영 인텔리전스 정직 표기", () => {
  it.each(LOCALES)("%s 로케일에 거짓 주장이 없다", (loc) => {
    const raw = readFileSync(resolve(process.cwd(), `public/locales/${loc}/common.json`), "utf-8");
    const dict = JSON.parse(raw) as {
      modulePlaceholders: Record<string, { description: string; items: string[] }>;
    };
    const m = dict.modulePlaceholders.maintenance;

    // 공허 진리 방지 — 대상 블록이 사라지면 이 검사는 무의미하다.
    expect(m, `${loc}: modulePlaceholders.maintenance 가 없다 — 검사가 공허해진다`).toBeTruthy();
    expect(m.items.length, `${loc}: items 가 비었다`).toBeGreaterThan(0);

    const blob = `${m.description} ${m.items.join(" ")}`;
    for (const claim of FALSE_CLAIMS) {
      expect(blob.includes(claim), `${loc}: 검증되지 않은 주장이 되돌아왔다 — "${claim}"`).toBe(false);
    }
    // 미연결 사실을 실제로 밝히고 있는가(정직의 존재를 함께 단언 — 삭제만으로는 부족하다).
    //
    // ★2026-08-16 정정: 종전에는 세 로케일 **전부**에 한국어 `미연결` 을 요구했다.
    //   그건 en·zh-CN 에 한국어 원문이 방치돼 있어야만 통과하는 단언이었다 —
    //   **테스트가 i18n 결함을 요구하고 있었다.** 로케일을 번역하자 이 줄이 빨강이 됐고,
    //   정답은 번역을 되돌리는 게 아니라 단언을 고치는 것이었다
    //   (하루 전 같은 형태를 만났다: 회귀망이 잘못된 계약을 잠그면 결함을 통과시킨다).
    expect(blob, `${loc}: 무엇이 미연결인지 밝히지 않는다`).toMatch(UNWIRED_MARK[loc]);
  });

  /**
   * ★여기서 잠그는 것은 **전제**뿐이다 — "아직 로컬 산출인가".
   *
   *   고지의 **개수·자리**는 세지 않는다. 종전에는 `<LocalEstimateNotice />` 의 소스 출현 수를
   *   가짜 지연 수와 비교했는데, 그 단언은 두 번 틀렸다:
   *     ① 소스 문자열만 보므로 **주석 처리해도 초록**이고 렌더 여부를 모른다
   *        (이 저장소에서 2회 실증된 구멍 — CLAUDE.md §A.3).
   *     ② 계약 자체가 틀렸다. 고지는 **결과 묶음(섹션)당 1개**이지 계산 횟수만큼이 아니다.
   *        피드백·만족도는 결과 그리드 하나를 공유하므로 산출 4에 고지 3이 정답이다.
   *        "산출 수 이상"을 요구한 탓에 오히려 **그리드 안에 고지를 중복 배치한 결함이 통과**했다
   *        (#634 R1 — 같은 문장이 두 번 보이고 격자 칸을 차지했다).
   *
   *   개수와 자리는 렌더로 잠근다 → `ops-intelligence-notice-placement.test.tsx`.
   *   그쪽은 섹션 전집합에서 파생되므로 섹션이 늘면 자동으로 감시망에 들어온다.
   */
  it("전제 — 아직 로컬 산출이다(서버로 배선되면 고지와 이 검사를 함께 갱신할 것)", () => {
    const src = readFileSync(
      resolve(process.cwd(), "components/analytics/OperationsIntelligenceWorkspaceClient.tsx"),
      "utf-8",
    );

    const fakeDelays = src.match(/new Promise\(\(r\) => setTimeout\(r, \d+\)\)/g) ?? [];
    expect(
      fakeDelays.length,
      "가짜 지연이 사라졌다 — 서버로 배선됐다면 고지·이 검사·짝 렌더 검사를 함께 갱신할 것",
    ).toBeGreaterThan(0);

    expect(src, "정직 고지 컴포넌트가 없다").toContain("function LocalEstimateNotice()");
  });
});
