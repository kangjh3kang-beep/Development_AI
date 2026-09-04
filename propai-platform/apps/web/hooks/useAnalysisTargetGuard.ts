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
/** 실행 토큰 구분자 — 키에 들어갈 수 없는 제어문자(키는 JSON 직렬화라 raw NUL이 없다). */
const TOKEN_SEP = "\u0000";

export function useAnalysisTargetGuard(
  targetKey: string,
  onStale: () => void,
  /**
   * 지금 화면에 결과가 붙어 있는가.
   *
   * ★이걸 받는 이유(2026-08-05 R3 M-3): 종전에는 "붙은 결과"를 `begin()` 호출로만 추적해서,
   *   분석 실행이 아닌 경로(히스토리 복원 등)로 결과가 붙으면 가드가 **조용히 죽었다**
   *   — 대상을 바꿔도 그 결과가 안 지워진다. 실제 상태를 함께 보게 해 추적이 어긋날 수
   *   없게 한다(현재 패널은 실행 경로 하나뿐이라 잠재였지만, 경로가 하나만 늘면 발현한다).
   *
   * ★기본값을 두지 않는다 — 선택형이면 소비처가 안 넘겨도 조용히 통과해(변이 생존 실측)
   *   가드가 반쪽으로 돌아간다. **필수로 두어 컴파일러가 배선 누락을 잡게** 한다
   *   (소스 grep 불변식보다 강하다 — 우회할 방법이 없다).
   */
  hasResult: boolean,
) {
  /** 화면에 떠 있는(또는 요청 중인) 결과가 어느 대상의 것인지. null이면 붙은 결과 없음. */
  const shownForRef = useRef<string | null>(null);
  /** 실행 일련번호·최신 실행 토큰 — 같은 대상 재실행 경합을 가른다. */
  const seqRef = useRef(0);
  const latestRunRef = useRef<string | null>(null);
  /** 현재 대상 키의 최신값 — 응답이 도착한 시점에 비교하려면 렌더와 무관하게 읽어야 한다. */
  const targetRef = useRef(targetKey);
  targetRef.current = targetKey;
  /** onStale은 매 렌더 새 함수일 수 있다. 이걸 effect deps에 넣으면 대상이 안 바뀌어도
   *  effect가 돌아 엉뚱하게 화면을 비운다 — 그래서 ref로 최신값만 들고 간다. */
  const onStaleRef = useRef(onStale);
  onStaleRef.current = onStale;

  useEffect(() => {
    // 실행 경로를 안 거치고 결과가 붙었으면(히스토리 복원 등) 현재 대상의 것으로 입양한다 —
    // 그래야 다음 대상 전환에서 정상적으로 무효화된다.
    if (hasResult && shownForRef.current === null) shownForRef.current = targetKey;
    // 결과가 사라졌으면 추적도 비운다(다음 진입에서 헛 무효화 방지).
    if (!hasResult && shownForRef.current !== null && shownForRef.current === targetKey) {
      shownForRef.current = null;
    }
    // 붙은 결과가 없으면(첫 진입 포함) 지울 것도 없다.
    if (shownForRef.current === null) return;
    if (shownForRef.current === targetKey) return;
    shownForRef.current = null;
    onStaleRef.current();
  }, [targetKey, hasResult]);

  /** 분석을 시작할 때 부른다 — 이 실행을 식별하는 토큰을 돌려준다.
   *
   * ★키가 아니라 **실행 토큰**을 돌려준다(2026-08-05 R3 M-3): 키만 비교하면 같은 대상에서
   *   분석을 두 번 시작했을 때 두 실행의 토큰이 같아져, **먼저 시작한 느린 응답**이 나중
   *   실행의 결과를 덮어쓴다(같은 대상이므로 대상 전환 가드에도 안 걸린다).
   */
  const begin = useCallback(() => {
    const key = targetRef.current;
    seqRef.current += 1;
    const token = `${seqRef.current}${TOKEN_SEP}${key}`;
    shownForRef.current = key;
    latestRunRef.current = token;
    return token;
  }, []);

  /** 응답을 화면에 붙이기 전에 부른다 — 대상이 바뀌었거나 **더 나중 실행이 있으면** false. */
  const isCurrent = useCallback((token: string) => {
    if (token !== latestRunRef.current) return false; // 재실행 경합 — 나는 이미 낡았다
    const key = token.slice(token.indexOf(TOKEN_SEP) + TOKEN_SEP.length);
    return key === targetRef.current;
  }, []);

  return { begin, isCurrent };
}
