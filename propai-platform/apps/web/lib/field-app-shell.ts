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
 * ★`standalone` 과 별도 창을 **둘 다** 본다. 어느 하나만으로 단정하지 않는 이유:
 *   `window.name` 이 열린 창에서 유지되는지는 **실기기 브라우저 실측 전까지 미측정**이다
 *   (계획서 §3). 두 판별자를 OR 로 두면 한쪽이 틀려도 「앱 안인데 버튼이 보이는」
 *   원래 결함으로는 돌아가지 않는다.
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
 *   움직이면 동작이 같다. **어긋나는 쪽**은 따로 잠가 뒀다(손 변이 ⑦: window.open 의 이름을
 *   리터럴로 바꾸면 CAUGHT). 값을 단언하면 그건 자기지시적 기대값이라 아무것도 못 잡는다.
 */
export const FIELD_APP_WINDOW_NAME = "propai-field-app";

export type FieldAppShellState = {
  /** PWA 로 설치돼 standalone 으로 실행 중. */
  standalone: boolean;
  /** `window.open(..., FIELD_APP_WINDOW_NAME, ...)` 로 연 별도 창 안. */
  inSeparateWindow: boolean;
  /** ★둘 중 하나라도 참이면 **이미 앱 안**이다 — 앱 어포던스를 노출하지 않는다. */
  inAppShell: boolean;
};

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

  return { standalone, inSeparateWindow, inAppShell: standalone || inSeparateWindow };
}
