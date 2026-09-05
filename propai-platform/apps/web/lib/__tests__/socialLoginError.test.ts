import { describe, expect, it } from "vitest";

import {
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

  it("모르는 로케일은 한국어로 떨어진다(문구 없음이 아니라)", () => {
    const msg = socialLoginErrorMessage(classifySocialLoginError("invalid_client"), "fr");
    expect(msg).toBeTruthy();
    expect(msg as string).toContain("invalid_client");
  });
});
