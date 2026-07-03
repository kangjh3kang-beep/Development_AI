/**
 * [MAP-007 P1] 기반 타일 로드 실패 시 명시 오버레이·재시도 회귀 테스트.
 *
 * 결함: tileerror 시 setTileStatus('error')로 상태만 기록하고 하단에 작은 경고 배지만 표시
 * → 지도는 회색 배경 + 초기 줌으로 정지해 사용자가 '로딩 중'과 '실패'를 구분 불가,
 *   복구 수단(재시도)도 없었다.
 *
 * 수선: 실패 상태를 지도 중앙 반투명 오버레이(메시지+재시도 버튼)로 승격.
 * Leaflet은 jsdom에서 구동 불가 → 오버레이 표시 판정을 순수 함수로 분리해 검증한다.
 */
import { describe, expect, it } from "vitest";

import { buildTileFailureNotice } from "@/components/map/SatongMultiMap";

describe("MAP-007 buildTileFailureNotice — 타일 실패 명시 오버레이 판정", () => {
  it("error 상태면 실패 메시지 + 재시도 라벨을 반환한다", () => {
    const notice = buildTileFailureNotice("error");
    expect(notice).not.toBeNull();
    // 실패임이 명시돼야 한다('로딩 중'과 구분) — 정직 라벨
    expect(notice!.message).toContain("실패");
    expect(notice!.retryLabel).toBe("재시도");
  });

  it("idle(로딩 전/중) 상태면 오버레이를 띄우지 않는다 — 로딩과 실패의 구분", () => {
    expect(buildTileFailureNotice("idle")).toBeNull();
  });

  it("ready(정상) 상태면 오버레이를 띄우지 않는다", () => {
    expect(buildTileFailureNotice("ready")).toBeNull();
  });
});
