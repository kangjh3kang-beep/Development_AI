import { describe, it, expect, vi } from "vitest";

import { formatArea } from "./formatters";

/**
 * formatArea 출력 고정 테스트(UX 트랙 A R2 — R1 리뷰어 지적 반영).
 *
 * ■ 왜 필요한가
 *   formatArea 가 SatongMapShell·ComprehensiveAnalysisPanel·SiteAnalysisDetail 4개소의
 *   로컬 중복 구현(㎡ vs m²·"약" 유무·en-US/ko-KR·0/NaN 처리 5중 분기)을 흡수해 SSOT로
 *   승격됐는데, 정작 이 함수 자체의 출력을 고정하는 테스트가 하나도 없었다
 *   (area-ssot-contract.test.ts 는 raw-read 여부만 스캔·satong-measure.test.ts 는 완전히
 *   다른 함수 formatAreaSqm 를 검증). 이 파일이 그 공백을 메운다 — 이후 누군가 로케일/
 *   자릿수/무효값 처리를 되돌려도 여기서 즉시 잡힌다.
 *
 * ■ 실사용 콜사이트는 4개소다(SatongMapShell·ComprehensiveAnalysisPanel·
 *   SiteAnalysisDetail 의 2개 지점) — 커밋 당시 "5개소 단일화"라고 적었던 것은 부정확한
 *   표현이었다. 이 lib/formatters.ts 자체의 구 formatArea 는 리팩토링 전까지 앱 어디서도
 *   import 되지 않던 사코드(dead code)였으므로 콜사이트로 셀 수 없다.
 */
describe("formatArea — 면적 표시 SSOT", () => {
  it("㎡+평 병기 · ko-KR 로케일(기본, 소수 최대 3자리 — 호출부 기존 표기 보존)", () => {
    // 3305.785 는 소수 3자리 그대로 남아야 기존 SiteAnalysisDetail/ComprehensiveAnalysisPanel
    // 로컬 구현(무옵션 toLocaleString)과 육안 동일성을 보존했는지 드러난다.
    expect(formatArea(3305.785)).toBe("3,305.785㎡ (1000.0평)");
    expect(formatArea(1000)).toBe("1,000㎡ (302.5평)");
  });

  it('"약" 접두 없음 — 반올림 근사이므로 접두 생략(구 formatters.ts 사코드는 "약"을 붙였었다)', () => {
    expect(formatArea(1000)).not.toMatch(/약/);
  });

  it("fractionDigits=0 — 정수 반올림(SatongMapShell 콜사이트의 기존 Math.round 계약 보존)", () => {
    expect(formatArea(3305.785, 0)).toBe("3,306㎡ (1000.0평)");
  });

  it('로케일 인자 = "ko-KR"가 실제로 전달된다(문자열 출력 비교로는 못 잡는 구멍을 spy로 메움)', () => {
    // ★뮤테이션 실측: "ko-KR"→"en-US"로 되돌려도 이 Node ICU 환경에서는 일반 소수(그룹 콤마·
    // 마침표 소수점)의 렌더링 결과가 완전히 동일해 출력-문자열 비교 테스트로는 검출되지 않음을
    // 확인했다(예: (3305.785).toLocaleString("ko-KR") === (3305.785).toLocaleString("en-US")).
    // 그래서 인자 자체를 spy로 고정 — 이 테스트는 로케일 뮤테이션을 확실히 잡는다.
    const spy = vi.spyOn(Number.prototype, "toLocaleString");
    formatArea(1234.5);
    expect(spy).toHaveBeenCalledWith("ko-KR", undefined);
    spy.mockRestore();
  });

  it('null/undefined/NaN → "-"(가짜 "0㎡"·"NaN㎡" 날조 금지)', () => {
    expect(formatArea(null)).toBe("-");
    expect(formatArea(undefined)).toBe("-");
    // ★R1 리뷰어 확인 항목: 구 SiteAnalysisDetail 로컬 formatArea(sqm: unknown)는
    //   `typeof sqm !== "number" || sqm <= 0` 만 체크했다 — typeof NaN === "number"이고
    //   NaN <= 0 은 false이므로 이 가드를 모두 통과해 "NaN m² (NaN평)"이 실제로 표시됐다.
    //   Number.isFinite 가드로 이 선재 버그가 여기서 함께 막히는지 고정한다.
    expect(formatArea(Number.NaN)).toBe("-");
  });

  it('0·음수 → "-"(무효 입력을 실측값처럼 보이게 하지 않는다 — formatCurrencyKRW 등과 동일 원칙)', () => {
    expect(formatArea(0)).toBe("-");
    expect(formatArea(-500)).toBe("-");
  });
});
