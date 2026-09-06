import { describe, expect, it } from "vitest";

import {
  USER_CANCELLED,
  classifySocialLoginError,
  socialLoginErrorMessage,
} from "@/lib/socialLoginError";

/**
 * ★두 모집단을 같은 실행에서 대조한다.
 *   하나만 보면 「전부 misconfigured」나 「전부 cancelled」인 구현도 통과한다.
 */
describe("classifySocialLoginError", () => {
  it("error 가 없으면 none — 기존 성공 경로를 바꾸지 않는다(회귀 축)", () => {
    for (const v of [null, undefined, "", "   "]) {
      const r = classifySocialLoginError(v as string | null);
      expect(r.kind).toBe("none");
      expect(r.rawCode).toBeNull();
    }
    // ★대조군: 값이 있으면 none 이 아니어야 한다(위 단언이 공허하지 않음을 증명)
    expect(classifySocialLoginError("access_denied").kind).not.toBe("none");
  });

  it("사용자 취소와 설정 오류를 가른다 — 다음 행동이 다르기 때문", () => {
    // 모집단 A: 사용자가 스스로 취소
    for (const code of ["access_denied", "user_cancel", "ACCESS_DENIED"]) {
      expect(classifySocialLoginError(code).kind).toBe("cancelled");
    }
    // 모집단 B: 설정 오류 — 사용자가 다시 해도 안 된다
    for (const code of [
      "redirect_uri_mismatch",
      "invalid_client",
      "unauthorized_client",
      "disp_stat_207",
    ]) {
      expect(classifySocialLoginError(code).kind).toBe("misconfigured");
    }
  });

  it("원문 코드와 설명을 보존한다 — 진단 가능성", () => {
    const r = classifySocialLoginError("redirect_uri_mismatch", "  등록되지 않은 URI  ");
    expect(r.rawCode).toBe("redirect_uri_mismatch");
    expect(r.rawDescription).toBe("등록되지 않은 URI");
  });
});

describe("socialLoginErrorMessage", () => {
  it("none 이면 문구가 없다 — 호출부가 종전 경로를 타야 한다", () => {
    expect(socialLoginErrorMessage(classifySocialLoginError(null), "ko")).toBeNull();
  });

  it("★설정 오류 문구는 원문 코드를 반드시 포함한다(진단 불가 방지)", () => {
    for (const locale of ["ko", "en", "zh-CN"]) {
      const msg = socialLoginErrorMessage(
        classifySocialLoginError("redirect_uri_mismatch"),
        locale,
      );
      expect(msg).toBeTruthy();
      expect(msg as string).toContain("redirect_uri_mismatch");
    }
  });

  it("★취소 문구와 설정오류 문구가 서로 다르다(공허한 통과 방지)", () => {
    const cancelled = socialLoginErrorMessage(
      classifySocialLoginError("access_denied"),
      "ko",
    );
    const broken = socialLoginErrorMessage(
      classifySocialLoginError("redirect_uri_mismatch"),
      "ko",
    );
    expect(cancelled).toBeTruthy();
    expect(broken).toBeTruthy();
    expect(cancelled).not.toBe(broken);
    // 취소 문구는 원문 코드를 노출하지 않는다(사용자 잘못이 아니므로 기술용어를 안 보인다)
    expect(cancelled as string).not.toContain("access_denied");
  });

  // ★목록이 아니라 **집합에서 파생**한다 — 여섯 번째 코드가 추가돼도 자동으로 편입된다.
  //   기계 변이 감사가 이 자리를 짚었다: 5종 중 2종만 태우고 있었다.
  it("취소 코드는 **전수**가 cancelled 로 분류된다(파생형)", () => {
    const codes = [...USER_CANCELLED];
    expect(codes.length, "취소 코드 집합이 비었다 — 조회기 사망").toBeGreaterThanOrEqual(5);
    for (const c of codes) {
      expect(classifySocialLoginError(c).kind, `${c} 가 cancelled 가 아니다`).toBe("cancelled");
      // 대소문자가 달라도 같은 판정이어야 한다(공급자 표기가 흔들린다)
      expect(classifySocialLoginError(c.toUpperCase()).kind).toBe("cancelled");
    }
  });

  // ★음성 대조군 — 이것이 없으면 「전부 cancelled」인 구현도 위 단언을 만족한다.
  it("집합 밖 코드는 misconfigured 이고 원문 코드를 화면까지 싣는다", () => {
    for (const c of ["invalid_client", "redirect_uri_mismatch", "unauthorized_client"]) {
      expect(USER_CANCELLED.has(c), `대조군 ${c} 가 집합 안에 있다 — 대조군이 무효`).toBe(false);
      const v = classifySocialLoginError(c);
      expect(v.kind).toBe("misconfigured");
      expect(socialLoginErrorMessage(v, "ko") as string).toContain(c);
    }
  });

  it("모르는 로케일은 한국어로 떨어진다(문구 없음이 아니라)", () => {
    const msg = socialLoginErrorMessage(classifySocialLoginError("invalid_client"), "fr");
    expect(msg).toBeTruthy();
    expect(msg as string).toContain("invalid_client");
  });
});
