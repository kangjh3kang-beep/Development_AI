/**
 * 선택 오염 **관측** — "고지는 하는데 빈도를 못 잰다"를 푼다.
 *
 * 왜 필요한가(쉬운 설명):
 * `lib/selection-integrity.ts` 가 "이 필지들은 하나의 개발 부지가 아닙니다"를 판정하고
 * 화면이 그것을 고지한다. 그런데 **그 일이 얼마나 자주 일어나는지는 아무도 몰랐다.**
 * 빈도를 모르면 "이미 오염된 프로젝트를 정리할 것인가"도, "선택 UI 를 바꿀 것인가"도
 * 근거 없이 결정하게 된다. 여기서 그 빈도를 재는 통로를 만든다.
 *
 * ★**주소를 보내지 않는다.** `regionGroups`·`malformedRows` 는 원문이 사람 이름·지번이다
 *   (실측: `◀ 전성결`). 빈도를 재는 데 필요한 것은 **개수**이지 원문이 아니므로 개수만
 *   보낸다. collector 의 PII 마스킹에 기대지 않는다 — 애초에 담지 않는 것이 확실하다.
 *
 * ★**정상 선택은 보내지 않는다.** `single_site` 는 관측 대상이 아니다. 전수를 보내면
 *   신호가 잡음에 묻히고 쿼터만 태운다.
 *
 * ★앞 세션의 실측 오류를 적어 둔다(같은 함정 재발 방지): 이 통로가 "없다"고 기록돼 있었다.
 *   실제로는 `lib/growth/event-collector.ts` 의 `trackEvent` 가 이미 있었고 `api-client`
 *   에 배선돼 있었다 — `recordEvent`/`captureEvent` 라는 **틀린 이름으로만** 찾았기 때문이다.
 *   "0건은 부재가 아니다."
 */
import type { SelectionIntegrity } from "@/lib/selection-integrity";

import { trackEvent, type GrowthEventType, type TrackEventProps } from "./event-collector";

/**
 * 이벤트 타입 상수 — 문자열 리터럴을 호출부에 흩뿌리지 않는다.
 * ★`GrowthEventType` 으로 좁혀 두면 백엔드 화이트리스트에 없는 이름을 쓰는 순간 `tsc` 가 막는다.
 */
export const SELECTION_CONTAMINATION_EVENT: GrowthEventType =
  "selection_contamination_observation";

/** 어느 서비스가 낸 관측인가 — 대시보드에서 이 값으로 묶인다. */
export const SELECTION_CONTAMINATION_SERVICE = "precheck.selection-integrity";

/**
 * 판정 → 전송할 속성. **순수 함수**로 분리해 두는 이유:
 * 서버·화면 사이의 변환 함수는 한 줄이 빠져도 백엔드 정상·테스트 초록·화면(여기선 적재)만
 * 비는 형태로 조용히 죽는다. 순수 함수로 `export` 해야 잠글 수 있다.
 *
 * @returns 관측 대상이 아니면 `null`(정상 선택은 보내지 않는다).
 */
export function buildSelectionContaminationProps(
  integrity: SelectionIntegrity,
  route: string | null,
): TrackEventProps | null {
  if (integrity.verdict === "single_site") return null;
  return {
    route,
    service: SELECTION_CONTAMINATION_SERVICE,
    // `malformed` 는 데이터가 깨진 것(복구 필요), `multi_region` 은 정당할 수 있다(§고지만).
    severity: integrity.verdict === "malformed" ? "error" : "warn",
    payload: {
      verdict: integrity.verdict,
      // 좌표가 2개 미만이면 **미상이지 0이 아니다** — null 을 그대로 보낸다.
      spread_km: integrity.spreadKm,
      region_groups: integrity.regionGroups.length,
      malformed_rows: integrity.malformedRows.length,
    },
  };
}

/**
 * 관측 1건 적재. 정상 선택이면 아무것도 하지 않는다.
 * @returns 실제로 보냈으면 true.
 */
export function trackSelectionContamination(
  integrity: SelectionIntegrity,
  route: string | null,
): boolean {
  const props = buildSelectionContaminationProps(integrity, route);
  if (!props) return false;
  trackEvent(SELECTION_CONTAMINATION_EVENT, props);
  return true;
}

/**
 * 같은 오염을 재렌더마다 다시 세지 않기 위한 **중복 제거 키**.
 * ★개수·판정이 바뀌면 다른 관측이다(필지를 지워 2지역→1지역이 되면 그건 새 사실이다).
 */
export function selectionContaminationKey(integrity: SelectionIntegrity): string {
  return [
    integrity.verdict,
    integrity.regionGroups.length,
    integrity.malformedRows.length,
    integrity.spreadKm ?? "unknown",
  ].join("|");
}
