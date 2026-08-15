/**
 * 운영 인텔리전스 — **추정을 분석으로 보이게 하지 않는다**(무목업·정직 표기).
 *
 * ★사실관계(2026-08-13 실측): `/en/maintenance` 의 "정비 분석" 버튼을 눌러도 **API 요청이 0건**이고,
 *   `OperationsIntelligenceWorkspaceClient` 가 폼 입력값으로 **브라우저에서 산술**해 결과를 만든다
 *   (각 실행부에 `setTimeout` 가짜 지연만 있다). 백엔드에는 해당 라우터가 없다(DB 테이블만 존재).
 *   그런데 화면 문구는 *"설비의 **센서 기반** 예지 정비"* · *"✓ 설비 IoT 센서 22개소 실시간 연동"* ·
 *   *"✓ 예지 정비(Predictive ML) 모델 가동"* 이라고 **사실처럼 단언**하고 있었다.
 *
 * ★이 검사는 두 방향을 함께 잠근다:
 *   ① 거짓 주장 문구가 **다시 들어오지 않는다**(3개 로케일 전부)
 *   ② 로컬 산출 결과에는 **정직 고지가 붙어 있다**(고지 컴포넌트가 실행부와 함께 존재)
 *
 * ※ 범위: 이 커밋은 **증명한 것만** 고쳤다. 같은 `modulePlaceholders` 사전에는 검증하지 않은
 *   사실 단언이 더 있다(실측 27개 모듈·37개 항목). 그것들은 모듈별 확인 없이 손대지 않는다 —
 *   검증 안 한 주장을 다른 주장으로 바꾸는 것도 같은 잘못이다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const LOCALES = ["ko", "en", "zh-CN"] as const;

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
    expect(blob, `${loc}: 무엇이 미연결인지 밝히지 않는다`).toMatch(/미연결/);
  });

  it("★로컬 산출 결과 4종에 정직 고지가 붙어 있다", () => {
    const src = readFileSync(
      resolve(process.cwd(), "components/analytics/OperationsIntelligenceWorkspaceClient.tsx"),
      "utf-8",
    );

    // 전제 — 로컬 산출(가짜 지연)이 실제로 몇 개인가. 이게 0이면 고지 검사가 공허하다.
    const fakeDelays = src.match(/new Promise\(\(r\) => setTimeout\(r, \d+\)\)/g) ?? [];
    expect(
      fakeDelays.length,
      "가짜 지연이 사라졌다 — 서버 배선으로 바뀌었다면 이 검사와 고지를 함께 걷어낼 것",
    ).toBeGreaterThan(0);

    // 고지 컴포넌트가 정의돼 있고, 산출 결과 수만큼 배치돼 있는가.
    expect(src, "정직 고지 컴포넌트가 없다").toContain("function LocalEstimateNotice()");
    const placements = src.match(/<LocalEstimateNotice \/>/g) ?? [];
    expect(
      placements.length,
      `고지 배치(${placements.length})가 로컬 산출(${fakeDelays.length})보다 적다 — 일부 결과가 추정임을 안 밝힌다`,
    ).toBeGreaterThanOrEqual(fakeDelays.length);
  });
});
