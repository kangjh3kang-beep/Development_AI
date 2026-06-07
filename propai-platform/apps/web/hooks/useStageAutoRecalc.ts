"use client";

/**
 * useStageAutoRecalc — 모세혈관(단계 간 데이터 전파) 공통 자동재계산 훅.
 *
 * 배경: InvestmentFeasibilityClient가 가지고 있던 "업스트림(공사비 등)이 갱신되면
 * 다운스트림(수지)을 1회 자동 재계산하고, 재계산이 끝나면 stamp로 stale을 해소하며,
 * 무한루프를 막는" 패턴을 단일 훅으로 추출해 design/cost/esg 등에서 재사용한다.
 *
 * 동작:
 *  - store.isStale(moduleKey)가 true이고, enabled이며, busy(중복호출 가드)가 아니고,
 *    이미 한 번 산출된 결과가 있을 때(hasResult) 1회 recalcFn()을 호출한다.
 *  - recalcFn은 성공 시 store의 update*Data(또는 stamp) 액션을 호출해 moduleKey의
 *    updatedAt을 갱신해야 한다 → 이로써 isStale이 false가 되어 무한루프가 끊긴다.
 *  - ESG·cost처럼 백엔드 호출이 있는 경우 과도호출 방지를 위해 enabled/busy/hasResult
 *    게이트를 모두 충족할 때만 호출한다(사용자 최초 산출·수정값은 보존).
 *
 * 회귀안전: 기존 isStale 소비처(CadCompliancePanel·InvestmentFeasibilityClient)의
 * 로직은 그대로 두고, 신규 적용처만 이 훅을 사용한다(additive).
 */

import { useEffect, useRef } from "react";
import {
  useProjectContextStore,
  type ModuleKey,
} from "@/store/useProjectContextStore";

export interface UseStageAutoRecalcOptions {
  /** 자동재계산 활성화 여부(기본 true). 로딩 중·미인증 등에서 false로 게이트. */
  enabled?: boolean;
  /**
   * 이미 한 번 산출된 결과가 있는지. 무목업·과도호출 방지를 위해 최초 산출은
   * 사용자/자동로드에 맡기고, 결과가 있을 때(=재계산 대상)만 자동재계산한다.
   * 기본 true(InvestmentFeasibilityClient는 호출측에서 costStale로 result 가드).
   */
  hasResult?: boolean;
  /**
   * (additive) 업스트림이 늦게 채워져 다운스트림이 아직 미산출일 때 최초 1회 자동
   * 산출을 허용한다. 기본 false(기존 소비처 동작 보존). true면 store의
   * isReadyForFirstCompute(업스트림 준비 && 자체 미산출)도 트리거로 삼는다.
   */
  allowFirstCompute?: boolean;
  /**
   * 무한루프·과도호출(과금) 방지용 입력 시그니처. 백엔드 호출 다운스트림(cost/esg)은
   * 동일 시그니처면 재호출하지 않는다(값 변경 시에만 1회). 미지정 시 시그니처 가드 없음.
   */
  inputSignature?: string | number | null;
}

/**
 * @param moduleKey  다운스트림 모듈 키(store의 MODULE_UPSTREAM에 정의된 키).
 * @param recalcFn   stale 감지 시 1회 호출할 재계산 함수(동기/비동기 모두 허용).
 *                   성공 시 반드시 store update*Data로 moduleKey updatedAt을 갱신해야
 *                   stale이 해소된다.
 */
export function useStageAutoRecalc(
  moduleKey: ModuleKey,
  recalcFn: () => void | Promise<void>,
  options: UseStageAutoRecalcOptions = {},
): void {
  const {
    enabled = true,
    hasResult = true,
    allowFirstCompute = false,
    inputSignature = null,
  } = options;
  const isStale = useProjectContextStore((s) => s.isStale);
  const isReadyForFirstCompute = useProjectContextStore(
    (s) => s.isReadyForFirstCompute,
  );
  // 진행 중 중복호출 가드(비동기 recalc이 끝나기 전 재진입 방지).
  const busyRef = useRef(false);
  // 마지막으로 자동산출을 트리거한 입력 시그니처(동일하면 재호출 skip — 과금/폭주 방지).
  const lastSigRef = useRef<string | number | null | undefined>(undefined);

  // 기존(재계산) 경로: 결과가 있고 업스트림이 더 최신일 때.
  const stale = enabled && hasResult && isStale(moduleKey);
  // 신규(최초산출) 경로: 결과가 없고 업스트림이 준비됐을 때 1회.
  const firstCompute =
    enabled && allowFirstCompute && isReadyForFirstCompute(moduleKey);
  const shouldRun = stale || firstCompute;

  useEffect(() => {
    if (!shouldRun || busyRef.current) return;
    // 시그니처 가드: 동일 입력으로 이미 트리거했으면 skip(무한루프/과도호출 방지).
    if (inputSignature != null && lastSigRef.current === inputSignature) return;
    busyRef.current = true;
    lastSigRef.current = inputSignature;
    void Promise.resolve(recalcFn()).finally(() => {
      busyRef.current = false;
    });
    // recalcFn 참조는 매 렌더 변경될 수 있으므로 의존성에서 제외(트리거 신호 변화로만).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldRun, inputSignature]);
}
