/**
 * 결제 오류 → 사용자 문구 + **조치** 락.
 *
 * ★이 저장소에는 코드→조치 매핑이 없었다(실측: `extractErrorMessage` 계열 **31개 중복**,
 *   어느 것도 코드로 분기하지 않고 어느 것도 조치를 붙이지 않는다). 그래서 새로 만든
 *   이 표가 **비어 있지 않은지**를 파생형으로 잠근다.
 */

import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  TOSS_FAIL_CODES,
  fromApiError,
  fromTossFailUrl,
} from "@/lib/payments/payment-error";
import { RECEIPT_EVENT_LABELS } from "@/components/mypage/CoinsClient";

describe("토스 failUrl 번역", () => {
  it.each(TOSS_FAIL_CODES)("%s 는 문구와 **조치**를 모두 갖는다", (code) => {
    const v = fromTossFailUrl(code, null);
    expect(v.message.trim().length).toBeGreaterThan(0);
    expect(v.remediation.trim().length).toBeGreaterThan(0);
    // ★문구와 조치가 같으면 조치가 없는 것과 같다.
    expect(v.message).not.toBe(v.remediation);
    expect(v.code).toBe(code);
  });

  it("★표가 비어 있지 않다(공허한 초록 방지)", () => {
    expect(TOSS_FAIL_CODES.length).toBeGreaterThanOrEqual(8);
  });

  it("★모르는 코드도 **침묵하지 않는다** — 벤더 문구를 그대로 보여 준다", () => {
    const v = fromTossFailUrl("BRAND_NEW_2099", "벤더가 준 문구");
    expect(v.message).toBe("벤더가 준 문구");
    expect(v.remediation.trim().length).toBeGreaterThan(0);
  });

  it("★두 모집단 — 취소와 카드거절은 **다른 안내**를 받는다", () => {
    const canceled = fromTossFailUrl("PAY_PROCESS_CANCELED", null);
    const rejected = fromTossFailUrl("REJECT_CARD_COMPANY", null);
    expect(canceled.message).not.toBe(rejected.message);
    expect(canceled.remediation).not.toBe(rejected.remediation);
  });
});

describe("서버 오류 번역", () => {
  it("★`payload.detail` 을 읽는다 — `message` 는 항상 상수라 쓸모없다", () => {
    // 실측: HTTP 오류의 `ApiClientError.message` 는 언제나 이 문자열이다.
    const err = {
      name: "ApiClientError",
      message: "API 요청 처리에 실패했습니다.",
      status: 400,
      payload: {
        detail: {
          code: "REJECT_CARD_COMPANY",
          message: "카드사에서 결제를 거절했습니다.",
          remediation: "다른 카드로 결제해 주세요.",
          outcome: "rejected",
          retryable: true,
        },
      },
    };
    const v = fromApiError(err, "기본 문구");
    expect(v.code).toBe("REJECT_CARD_COMPANY");
    expect(v.message).toBe("카드사에서 결제를 거절했습니다.");
    expect(v.remediation).toBe("다른 카드로 결제해 주세요.");
    expect(v.outcome).toBe("rejected");
    // ★상수 message 가 새어 나오면 안 된다.
    expect(v.message).not.toContain("API 요청 처리에 실패");
  });

  it("★미확정(`unresolved`)을 **거절과 구별**한다 — 실패로 말하면 이중결제를 부른다", () => {
    const err = {
      payload: {
        detail: {
          code: "PAYMENT_UNRESOLVED",
          message: "결제 결과를 확인하지 못했습니다.",
          remediation: "중복 결제하지 마세요.",
          outcome: "unresolved",
        },
      },
    };
    const v = fromApiError(err, "x");
    expect(v.outcome).toBe("unresolved");
    // 두 모집단이 실제로 갈리는지
    const rejected = fromApiError(
      { payload: { detail: { message: "a", remediation: "b", outcome: "rejected" } } },
      "x",
    );
    expect(v.outcome).not.toBe(rejected.outcome);
  });

  it("구조화되지 않은 오류도 조치를 준다", () => {
    const v = fromApiError(new Error("네트워크"), "결제를 시작하지 못했습니다.");
    expect(v.message).toBe("결제를 시작하지 못했습니다.");
    expect(v.remediation.trim().length).toBeGreaterThan(0);
  });
});

describe("★영수증 라벨 정합 — 백엔드 어휘에서 **파생**", () => {
  /**
   * 이 저장소가 반복해 데인 형태: 백엔드 enum 11종 ↔ 프론트 표 7종이라
   * **4종이 영문 raw** 로 화면에 떴다. 손으로 센 표는 곧 상한이 된다.
   *
   * ★그래서 파이썬 원본에서 **읽어서** 대조한다.
   */
  const py = path.resolve(
    __dirname,
    "../../../../api/app/services/billing/payment_receipts.py",
  );

  it("★추출기가 살아 있다(공허한 초록 방지)", () => {
    expect(fs.existsSync(py), `백엔드 원본을 못 찾았다: ${py}`).toBe(true);
  });

  it("백엔드가 내는 모든 이벤트에 한국어 라벨이 있다", () => {
    const src = fs.readFileSync(py, "utf-8");
    // `EVENT_XXX = "value"` 선언에서 파생 — 주석/독스트링이 아니라 **선언**을 본다.
    const events = [...src.matchAll(/^EVENT_[A-Z_]+ = "([a-z_]+)"$/gm)].map((m) => m[1]);
    expect(events.length, "★이벤트 추출 0건 — 추출기가 죽었다(위반 아님)").toBeGreaterThanOrEqual(8);
    const missing = events.filter((e) => !(e in RECEIPT_EVENT_LABELS));
    expect(missing, `라벨 없는 이벤트(화면에 영문 raw 로 뜬다): ${missing.join(", ")}`).toEqual([]);
  });

  it("★역방향 — 존재하지 않는 이벤트의 유령 라벨이 없다", () => {
    const src = fs.readFileSync(py, "utf-8");
    const events = new Set(
      [...src.matchAll(/^EVENT_[A-Z_]+ = "([a-z_]+)"$/gm)].map((m) => m[1]),
    );
    const ghosts = Object.keys(RECEIPT_EVENT_LABELS).filter((k) => !events.has(k));
    expect(ghosts, `백엔드에 없는 유령 라벨: ${ghosts.join(", ")}`).toEqual([]);
  });
});
