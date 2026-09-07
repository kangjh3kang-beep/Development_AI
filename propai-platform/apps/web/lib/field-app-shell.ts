"use client";

/**
 * 현장앱 「앱 어포던스」의 **공용 판별자** — 한 셸 안에서 형제마다 가드가 달라선 안 된다
 * (DESIGN.md B3.3).
 *
 * ## 왜 이 파일이 생겼나 (2026-09-07 사용자 신고)
 *
 * `InstallGuide` 는 `standalone` 이면 안내를 숨기고 있었는데, **같은 셸 헤더의
 * 「앱으로 열기」 버튼에는 조건이 하나도 없었다**(`SiteWorkspaceClient.tsx:255-274`).
 * 그래서 사용자가 **앱 안에 들어와 있는데도 그 버튼이 계속 보였다.**
 * 가드를 각자 들고 있으면 이렇게 한쪽만 빠진다 — 판별을 한 곳으로 모은다.
 *
 * ## 두 명제를 구분한다 (섞으면 사용자가 속는다)
 *
 * · **설치**(PWA): 설치하면 OS 아이콘으로 `display-mode: standalone` 실행 = **진짜 앱**.
 * · **창 모드**(`window.open`): 이것은 **앱이 아니다.** 현대 브라우저는 팝업에서
 *   `location=no` 를 무시해 **주소창이 남는다**(2026-09-07 라이브 실측 — 사용자 스크린샷).
 *   종전 코드 주석은 *"브라우저 크롬 없는 팝업(주소창 숨김)"* 이라 단언했으나 **거짓**이었다.
 *   그래서 라벨을 「앱으로 열기」라고 쓰지 않는다 — 라벨은 실제로 일어나는 일을 말한다.
 *
 * ## ★두 값은 **이중화가 아니다** — 서로 다른 모집단을 덮는다 (2026-09-07 적대 리뷰 정정)
 *
 * 한때 이 주석은 *"둘 다 보므로 한쪽이 틀려도 원래 결함으로 돌아가지 않는다"* 고 적었다.
 * **거짓이다.** `standalone` 은 「설치본으로 실행 중」, `inSeparateWindow` 는 「별도 창 안」 —
 * **배타적 커버**이지 같은 명제의 중복 판별자가 아니다. 그래서:
 *
 *   · 사용자가 신고한 모집단은 **별도 창**이다(팝업 스크린샷에 주소창이 있었다).
 *   · 그 축의 판별자는 `window.name` **하나뿐**이다. 이것이 실제 브라우저에서 유지되지
 *     않으면 **신고자 모집단이 통째로 무보호**가 된다. `standalone` 은 그 자리를 못 메운다.
 *
 * ★`window.opener` 를 두 번째 판별자로 쓰지 않는 이유: 우리 목록 화면에서 `target=_blank`
 *   로 연 **평범한 탭**도 `opener` 를 갖는다 — 「앱 안」이 아닌 것을 앱 안으로 읽는 위양성이
 *   커서, 위음성 하나를 줄이려다 정상 화면에서 어포던스를 지우게 된다.
 *   ⇒ **판별자는 하나다. 그 사실을 숨기지 않고 적는다.** 잔여 위험은 계획서 §3 에 있다.
 *   ★이 축은 jsdom 으로는 원리적으로 못 잰다(테스트가 `window.name` 을 **직접 대입**한다).
 *     Playwright 로 실제 팝업을 열어 재는 계약 테스트가 `field-app-window-name.spec.ts` 다.
 */

import { useSyncExternalStore } from "react";
import { usePwaRuntime } from "@/components/pwa/PwaRuntimeProvider";

/**
 * 현장앱을 별도 창으로 열 때 쓰는 창 이름 — 그 창이 **자기를 다시 알아보는 표식**이다.
 * 여는 쪽(`window.open`)과 판별하는 쪽이 **같은 상수**를 써야 한다(문자열 두 벌 금지).
 */
/*
 * ★변이 생존 설명(2026-09-07 · scripts/mutate_changed.py) — 점수를 부풀리지 않기 위해 적는다.
 *   이 상수의 **값을 바꾸는 변이는 생존한다.** 구멍이 아니다 — 값 자체는 임의이고, 계약은
 *   *"여는 이름과 판별하는 이름이 **같다**"* 이기 때문이다. 양쪽이 이 상수를 쓰므로 값이 함께
 *   움직이면 동작이 같다. **어긋나는 쪽**은 따로 잠가 뒀다(증거 파일의 `mut7`: window.open 의 이름을
 *   리터럴로 바꾸면 CAUGHT). 값을 단언하면 그건 자기지시적 기대값이라 아무것도 못 잡는다.
 */
export const FIELD_APP_WINDOW_NAME = "propai-field-app";

export type FieldAppShellState = {
  /** PWA 로 설치돼 standalone 으로 실행 중. */
  standalone: boolean;
  /** `window.open(..., FIELD_APP_WINDOW_NAME, ...)` 로 연 별도 창 안. */
  inSeparateWindow: boolean;
};

/*
 * ★한때 여기에 `inAppShell: standalone || inSeparateWindow` 가 있었고, 그것 하나로
 *   어포던스와 **설치 유도를 함께** 껐다 — 팝업 안에서 설치가 원천 봉쇄되고 iOS 의 유일한
 *   설치 경로가 닫히는 BLOCKER 였다(적대 리뷰). 되돌린 뒤 **필드를 지웠다**:
 *   소비처 0 인 채 남겨 두면 다음 사람이 집어 쓰면서 같은 결함이 조용히 재발한다
 *   (§27-d — 갈아 끼우는 변경에 옛 심볼이 남으면 그 자체가 미완 배선의 신호다).
 *   **축은 각자 고른다**: 설치 억제 = `standalone` · 창 열기 억제 = `inSeparateWindow`.
 */

/** `window.name` 은 세션 중에 바뀌지 않는다 — 구독할 것이 없다(참조 안정성 위해 모듈 상수). */
const noSubscribe = () => () => {};
const readSeparateWindow = () =>
  typeof window !== "undefined" && window.name === FIELD_APP_WINDOW_NAME;
/** 서버에는 window 가 없다 — 스냅샷을 false 로 둬 하이드레이션 불일치를 만들지 않는다. */
const serverSnapshot = () => false;

export function useFieldAppShell(): FieldAppShellState {
  const { standalone } = usePwaRuntime();
  // ★`useEffect` + `setState` 가 아니라 `useSyncExternalStore` 를 쓴다.
  //   ①외부 값을 읽는 정석이고 ②effect 안 setState 로 인한 연쇄 렌더가 없으며
  //   ③이 저장소의 **파일별 lint 경고 래칫**(scripts/ci/lint_ratchet.py)에서 새 파일의
  //     하한은 0이라 경고 하나만 늘어도 CI 가 빨개진다 — 경고를 남기지 않는 쪽을 고른다.
  const inSeparateWindow = useSyncExternalStore(noSubscribe, readSeparateWindow, serverSnapshot);

  return { standalone, inSeparateWindow };
}
