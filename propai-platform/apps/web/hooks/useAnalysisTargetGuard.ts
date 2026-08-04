"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * 화면에 떠 있는 분석 결과가 **지금 보고 있는 대상의 것인지** 지키는 가드.
 *
 * 막는 사고 3가지(전부 실제로 가능한 경로다):
 *
 *  1) **대상이 바뀌었는데 옛 결과가 남는다** — 프로젝트를 바꾸면 머리글은 새 프로젝트인데
 *     본문은 이전 프로젝트의 분석이 그대로 떠 있었다. 어느 쪽이 진짜인지 알 수 없다.
 *  2) **주소가 없는 프로젝트로 바꿔도 안 지워진다** — 지울지 말지를 주소 문자열로만
 *     판정하면, 주소가 빈 값인 프로젝트(다필지 프로젝트가 그렇다)에서는 판정이 아예
 *     성립하지 않아 옛 결과가 남는다.
 *  3) **분석 도중에 대상이 바뀐다** — 종합분석은 오래 걸린다. 응답을 기다리는 사이에
 *     사용자가 프로젝트를 바꾸면, 뒤늦게 도착한 **옛 대상의 응답**이 새 대상 화면에
 *     붙는다. 이건 지우는 것으로는 못 막는다 — 도착한 응답을 버려야 한다.
 *
 * 그래서 이 훅은 두 가지를 준다: 대상이 바뀌면 화면을 비우는 것(1·2), 그리고 응답을
 * 붙이기 전에 "아직 그 대상이 맞나"를 물어보는 것(3).
 *
 * @param targetKey 현재 대상 키(`analysisTargetKey`로 만든 값)
 * @param onStale   대상이 바뀌어 화면의 결과가 남의 것이 됐을 때 호출(결과·오류를 비운다)
 */
export function useAnalysisTargetGuard(targetKey: string, onStale: () => void) {
  /** 화면에 떠 있는(또는 요청 중인) 결과가 어느 대상의 것인지. null이면 붙은 결과 없음. */
  const shownForRef = useRef<string | null>(null);
  /** 현재 대상 키의 최신값 — 응답이 도착한 시점에 비교하려면 렌더와 무관하게 읽어야 한다. */
  const targetRef = useRef(targetKey);
  targetRef.current = targetKey;
  /** onStale은 매 렌더 새 함수일 수 있다. 이걸 effect deps에 넣으면 대상이 안 바뀌어도
   *  effect가 돌아 엉뚱하게 화면을 비운다 — 그래서 ref로 최신값만 들고 간다. */
  const onStaleRef = useRef(onStale);
  onStaleRef.current = onStale;

  useEffect(() => {
    // 붙은 결과가 없으면(첫 진입 포함) 지울 것도 없다.
    if (shownForRef.current === null) return;
    if (shownForRef.current === targetKey) return;
    shownForRef.current = null;
    onStaleRef.current();
  }, [targetKey]);

  /** 분석을 시작할 때 부른다 — 이 결과가 어느 대상의 것인지 표시하고 그 키를 돌려준다. */
  const begin = useCallback(() => {
    const key = targetRef.current;
    shownForRef.current = key;
    return key;
  }, []);

  /** 응답을 화면에 붙이기 전에 부른다 — 그 사이 대상이 바뀌었으면 false. */
  const isCurrent = useCallback((key: string) => targetRef.current === key, []);

  return { begin, isCurrent };
}
