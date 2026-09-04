"use client";

import { useEffect, useRef } from "react";

/**
 * 부모가 던진 토큰이 **바뀔 때만** 조회를 자동 실행한다 — 파이프라인 편입용 공용 훅.
 *
 * ## 왜 필요한가 (쉬운 설명)
 *
 * 입지 인프라(POI)·개발방식 시뮬레이션은 종합분석과 같은 필지를 보면서도 사용자가 **버튼을
 * 따로 눌러야** 했다. 종합분석을 돌려도 이 둘은 비어 있어서, 사용자는 "분석이 덜 됐나?"
 * 하고 버튼을 찾아 눌러야 했다. 종합분석 시작 시 부모가 토큰을 올리면 이 훅이 각 카드의
 * 조회를 자동으로 태워 한 번의 실행으로 모두 채워진다.
 *
 * ## 왜 훅으로 공용화했나
 *
 * 두 카드가 각자 useEffect를 쓰면 "언제 실행하는가"의 규칙이 조용히 갈라진다(한쪽만 마운트
 * 자동실행, 한쪽만 주소 가드 등). 트리거 의미론을 여기 한 곳에 고정한다.
 *
 * ## 계약(세 가지 가드)
 *
 * 1. **마운트 자동실행 안 함** — 최초 토큰값은 기준선으로만 기록한다. 화면에 카드가 뜨자마자
 *    조회가 나가면 사용자가 요청하지 않은 API 호출·과금이 발생한다.
 * 2. **토큰 변화 1회당 1실행** — 같은 값으로 리렌더돼도 재실행하지 않는다.
 * 3. **enabled=false면 실행하지 않고 토큰도 소비하지 않는다** — 주소 미선택 등 전제 미충족
 *    상태에서 토큰이 지나가버리면, 조건이 갖춰져도 그 회차는 영영 실행되지 않는다.
 */
export function useAutoRun(
  token: number | undefined,
  run: () => void,
  { enabled = true }: { enabled?: boolean } = {},
): void {
  // 최초 토큰을 기준선으로 기록 — 마운트 시점에는 실행하지 않는다.
  const lastRunToken = useRef<number | undefined>(token);
  // run은 매 렌더 새 함수일 수 있으므로 ref로 최신값만 참조한다(불필요한 재실행 방지).
  // ★렌더 중 ref 갱신 금지 — effect에서 갱신한다(React 규칙: refs는 렌더 외부에서만 접근).
  const runRef = useRef(run);
  useEffect(() => {
    runRef.current = run;
  });

  useEffect(() => {
    if (token === undefined) return;
    if (token === lastRunToken.current) return;
    // ★전제 미충족이면 토큰을 소비하지 않는다 — 조건이 갖춰진 뒤 같은 토큰으로 실행돼야 한다.
    if (!enabled) return;
    lastRunToken.current = token;
    runRef.current();
  }, [token, enabled]);
}
