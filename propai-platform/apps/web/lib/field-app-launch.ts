"use client";

import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * 현장앱(분양앱)을 **독자 창으로 여는 단일 통로**.
 *
 * ## 왜 함수로 빼는가 (2026-09-08)
 *
 * 종전에는 `FieldAppAffordance.tsx` 안에 팝업 features 문자열과 차단 폴백이 **인라인**으로
 * 있었다. 그런데 사용자 신고로 **두 번째 소비처**(플랫폼 → 현장앱 진입)가 필요해졌고,
 * 그것을 각자 구현하면 이 저장소가 반복해서 데인 형태가 그대로 재현된다 —
 * ★*"고친 자리의 형제·미러를 놓친다"*. 한쪽만 폴백을 고치면 다른 쪽은 조용히 옛 동작을 유지한다.
 *
 * 그래서 **창을 여는 판정은 여기 하나뿐**이고, `field-app-launch.wiring.test.ts` 가
 * 「`window.open` 을 담은 파일」을 **파생형**으로 세어 새 소비처가 자동으로 감시망에 들어오게 한다.
 *
 * ## 반환값이 3분기인 이유
 *
 * 호출부는 **기본 이동을 막을지**를 알아야 한다. 창이 떴으면 막아야 하고(안 막으면 원래 창까지
 * 현장앱으로 이동해 **사용자가 플랫폼을 잃는다** — 이 신고의 본체다), 못 떴으면 막으면 안 된다
 * (막으면 아무 데도 못 간다). 불리언으로 뭉개면 그 구별이 사라진다.
 *
 * ★`location=no` 를 넣지 않는다 — 현대 브라우저가 무시하므로 **지키지 못할 약속**이다
 *   (2026-09-07 라이브 실측: 팝업에 주소창이 남았다. 종전 주석이 거짓이었다).
 */

/** 창 열기 결과 — 호출부가 `preventDefault` 여부를 이것으로 정한다. */
export type FieldAppLaunchResult =
  /** 이름 있는 전용 창이 떴다. 호출부는 기본 이동을 **막아야 한다**. */
  | "window"
  /** 팝업이 막혀 새 탭으로 떴다. 원래 창은 보존됐으므로 역시 **막아야 한다**. */
  | "tab"
  /** 둘 다 막혔다. 호출부는 기본 이동을 **막으면 안 된다**(같은 창 이동 = 오늘의 동작). */
  | "same";

/** 팝업 크기 — 화면보다 크게 요청하지 않는다(일부 브라우저가 요청을 통째로 무시한다). */
function popupFeatures(): string {
  const w = Math.min(1180, Math.max(360, window.screen?.availWidth ?? 1180));
  const h = Math.min(900, Math.max(480, window.screen?.availHeight ?? 900));
  const left = Math.max(0, Math.round(((window.screen?.availWidth ?? w) - w) / 2));
  const top = Math.max(0, Math.round(((window.screen?.availHeight ?? h) - h) / 2));
  return `popup=yes,width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,status=no,resizable=yes,scrollbars=yes`;
}

/**
 * 현장앱을 독자 창으로 연다.
 *
 * @param url 열 주소. 생략하면 현재 주소(어포던스의 「별도 창으로 열기」가 그렇게 쓴다).
 * @returns 무엇으로 열렸는지 — 호출부가 기본 이동 차단 여부를 판단하는 근거.
 */
export function launchFieldApp(url?: string): FieldAppLaunchResult {
  if (typeof window === "undefined") return "same";
  const target = url ?? window.location.href;

  // ①이름 있는 전용 창 — 같은 이름으로 다시 열면 **그 창이 재사용**된다(창이 늘어나지 않는다).
  //   그 이름이 곧 현장앱 정체성 판별자다(`useFieldAppShell` 의 `inSeparateWindow`).
  const win = window.open(target, FIELD_APP_WINDOW_NAME, popupFeatures());
  if (win) {
    try {
      win.focus();
    } catch {
      /* 포커스는 부가 기능이다 — 실패해도 창은 떴다. */
    }
    return "window";
  }

  // ②팝업 차단 → 새 탭. 원래 창(플랫폼)이 남는다는 목적은 이것으로도 달성된다.
  //   ★`noopener` 를 준다 — 이름을 못 주는 대신 역참조를 끊는다.
  const tab = window.open(target, "_blank", "noopener,noreferrer");
  if (tab) return "tab";

  // ③둘 다 막혔다. 여기서 조용히 실패하면 **버튼이 죽은 것처럼 보인다** —
  //   호출부가 기본 이동을 그대로 두게 해서 최소한 오늘의 동작은 보장한다.
  return "same";
}
