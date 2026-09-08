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

/**
 * 팝업 크기 — ★**화면보다 크게 요청하지 않는다.** 일부 브라우저는 화면을 넘는 요청을
 * 통째로 무시해 크기 지정이 전부 날아간다.
 *
 * ★2026-09-08 적대 리뷰 M-4 정정: 종전 판(`Math.max(360, …)`)은 **이 주석을 스스로 깼다** —
 *   `availWidth=320`(초소형 단말)에서 `w=360 > 320` 이 된다. 하한을 바깥에 두면 상한이 무의미하다.
 *   **화면 크기로 한 번 더 clamp** 해서 주석이 참이 되게 한다(경계는 양방향으로 건다).
 *
 * ★그리고 **치수가 바뀐 것을 선언한다**(종전 인라인은 1440×960, 지금은 1180×900).
 *   리팩토링 커밋이 *"동작은 동일"* 이라 적었는데 **거짓이었다** — 값이 달랐다.
 *   현장앱은 모바일 우선 레이아웃이라 1180 이면 충분하고, 넓은 창은 사용자가 늘릴 수 있다.
 */
const POPUP_MAX_W = 1180;
const POPUP_MAX_H = 900;
const POPUP_MIN_W = 360;
const POPUP_MIN_H = 480;

function popupFeatures(): string {
  const availW = window.screen?.availWidth ?? POPUP_MAX_W;
  const availH = window.screen?.availHeight ?? POPUP_MAX_H;
  // 하한을 걸되 **화면을 넘지 않게** 다시 clamp — 이 두 번째 clamp 가 주석을 참으로 만든다.
  const w = Math.min(availW, Math.max(POPUP_MIN_W, Math.min(POPUP_MAX_W, availW)));
  const h = Math.min(availH, Math.max(POPUP_MIN_H, Math.min(POPUP_MAX_H, availH)));
  const left = Math.max(0, Math.round((availW - w) / 2));
  const top = Math.max(0, Math.round((availH - h) / 2));
  return `popup=yes,width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,status=no,resizable=yes,scrollbars=yes`;
}

/**
 * ★**클릭을 가로챌 것인가** — 이 판정도 공용이다(2026-09-08 적대 리뷰 M-3).
 *
 * 종전엔 `FieldAppLaunchLink` 와 `SidebarNav` 가 **각자** 판정했고 실제로 갈려 있었다:
 * 한쪽은 `defaultPrevented`·`button` 을 보고 다른 쪽은 안 봤다. 공용화가 «창을 여는 함수»
 * 까지만 가고 **«무엇을 가로챌지»는 두 벌로 남은** 것이다 — 이 PR 이 막겠다고 선언한 그 형태다.
 *
 * ★`button !== 0` 과 `defaultPrevented` 는 **도달 불가일 수 있다**(정직하게 적는다):
 *   현대 브라우저에서 가운데클릭은 `auxclick`, 우클릭은 `contextmenu` 를 내므로 `click` 의
 *   `button` 은 사실상 항상 0 이고, 이 앵커에 `preventDefault` 를 부르는 다른 핸들러도 없다.
 *   **jsdom 으로는 원리적으로 못 재므로 미측정**이다. 방어로 남기되 «실동작한다»고 말하지 않는다.
 */
export function shouldInterceptFieldAppClick(e: {
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  defaultPrevented: boolean;
}): boolean {
  if (e.defaultPrevented) return false;
  if (e.button !== 0) return false;
  // 수식키 클릭은 사용자가 **명시적으로** 새 탭·새 창을 요구한 것이다 — 브라우저에 맡긴다.
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
  return true;
}

/**
 * 현장앱을 독자 창으로 연다.
 *
 * @param url 열 주소. 생략하면 현재 주소(어포던스의 「별도 창으로 열기」가 그렇게 쓴다).
 * @returns 무엇으로 열렸는지 — 호출부가 기본 이동 차단 여부를 판단하는 근거.
 */
/**
 * 대상이 **우리 오리진**인가 — `noopener` 를 뺄 수 있는지의 유일한 판정자.
 *
 * ★동일 오리진에서는 `noopener` 가 **얻는 것이 없다**(SOP 상 이미 접근 가능하다). 반면
 *   잃는 것은 크다 — sessionStorage 상속이 끊겨 **현장 비밀번호를 다시 묻게 된다**(실측).
 *   교차 오리진에서는 반대로 `noopener` 가 실재하는 방어이므로 **유지한다.**
 *   상대 URL 은 현재 주소를 기준으로 해석된다(오늘의 모든 호출부가 상대 경로다).
 */
function sameOrigin(target: string): boolean {
  try {
    return new URL(target, window.location.href).origin === window.location.origin;
  } catch {
    return false; // 파싱 불가는 «모른다» 이고, 모르면 안전한 쪽(noopener)으로 간다.
  }
}

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

  // ②팝업 차단 → **같은 이름의 탭**. 원래 창(플랫폼)이 남는다는 목적은 이것으로도 달성된다.
  //
  // ★★`_blank` + `noopener` 를 쓰지 않는다 — **실측으로 갈렸다**(Chromium · 2026-09-08):
  //
  //     window.open(url, "propai-field-app", features)  → sessionStorage **상속**  · name 유지
  //     window.open(url, "propai-field-app")            → sessionStorage **상속**  · name 유지
  //     window.open(url, "_blank", "noopener,…")        → sessionStorage **새로 시작**(null) · name ""
  //
  //   현장 진입 토큰(`propai_site_token:*`)은 **sessionStorage** 에 산다. 그래서 `noopener`
  //   폴백은 **현장 비밀번호를 다시 묻게 만든다** — 같은 탭 이동보다도 나쁘다(회귀).
  //   그리고 이름을 잃으면 그 창이 「현장앱 창」으로 판정되지 않아 어포던스도 틀린 답을 낸다.
  //
  //   ★`noopener` 를 버리는 것이 안전한 이유: 대상이 **동일 오리진**이다. `noopener` 는
  //   교차 오리진에서 역참조를 끊는 장치이고, 동일 오리진은 어차피 SOP 상 접근 가능하므로
  //   여기서는 **얻는 것이 없고 잃는 것만 있었다.**
  //   ★그러나 **동일 오리진일 때만** 그렇다. 교차 오리진 대상에는 `noopener` 를 유지한다 —
  //     그때는 역탭내빙이 실재하는 위험이고, sessionStorage 도 어차피 공유되지 않는다.
  //     (이 분기가 없으면 적대 리뷰가 넣어 둔 F1 가드를 **사유 없이 무력화**하는 것이 된다.)
  const tab = sameOrigin(target)
    ? window.open(target, FIELD_APP_WINDOW_NAME)
    : window.open(target, "_blank", "noopener,noreferrer");
  if (tab) {
    try {
      tab.focus();
    } catch {
      /* 포커스는 부가 기능이다(교차 오리진이면 접근 자체가 막힐 수 있다). */
    }
    return "tab";
  }

  // ③둘 다 막혔다. 여기서 조용히 실패하면 **버튼이 죽은 것처럼 보인다** —
  //   호출부가 기본 이동을 그대로 두게 해서 최소한 오늘의 동작은 보장한다.
  return "same";
}
