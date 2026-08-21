"use client";

/**
 * 종상향 잠재 용적률 범위 표기 — 세 화면(종합분석·부지분석·자동추천)의 **공용 표면**.
 *
 * ★왜 공용인가(실측 결함):
 *   대표 목표 용도지역 선정이 보수적이라 여러 종상향 경로가 같은 목표를 가리키면
 *   `min_pct`와 `max_pct`가 **같은 값**이 된다(자연녹지 서울 실측: 150·150).
 *   그때 화면이 `예상 상한 150.0~150.0%`라고 적으면 개발사는 "그 위는 안 된다"로 읽는다.
 *   실제 의미는 "우리가 한 경로만 봤다"인데 그 한정이 화면 어디에도 없었다.
 *   세 화면이 각자 문자열을 만들면 한 화면만 고치고 형제를 놓친다(이 저장소의 반복 결함) —
 *   그래서 값 표기와 정직 고지를 여기 한 곳에 둔다.
 *
 * ★숫자는 바꾸지 않는다. 없는 상향 여지를 만들어내는 것이 아니라, 있는 한정을 말할 뿐이다.
 * ★고지 문구는 백엔드(potential_far_range.honest_disclosure)만 만든다 — 근거를 아는 쪽이
 *   쓰고 화면은 나른다. 프론트가 문구를 지어내면 근거 없는 단정이 된다.
 */

import { formatUpzoningFarRange, type UpzoningFarRange } from "@/lib/formatters";

/** 값 표기 — 붕괴 시 범위 기호(~)를 쓰지 않고 "단일 값(범위 미산출)"을 함께 적는다. */
export function UpzoningFarRangeValue({
  range, className,
}: { range: UpzoningFarRange; className?: string }) {
  return <span className={className}>{formatUpzoningFarRange(range).text}</span>;
}

/**
 * 정직 고지 — 붕괴했을 때만 렌더한다(백엔드가 사유를 실어 보낸 경우).
 * 붕괴하지 않았거나 고지가 없으면 아무것도 그리지 않는다(빈 껍데기 금지).
 */
export function UpzoningFarRangeNotice({
  range, className,
}: { range: UpzoningFarRange; className?: string }) {
  const disclosure = formatUpzoningFarRange(range).disclosure;
  if (!disclosure) return null;
  return <p className={className}>{disclosure}</p>;
}
