/**
 * 표본 셀렉터 골든 — **프로덕션 실응답**에 대해 선별 결과를 정수 리터럴로 못 박는다.
 *
 * ## 왜 라이브 픽스처인가
 *
 * 손으로 만든 픽스처는 동어반복이 되기 쉽다. 테스트가 `location_status` 를 직접 채우고
 * 셀렉터가 그걸 존중하는지만 보면, **생산 코드가 그 값을 잘못 채우는** 회귀를 못 잡는다
 * (#516 R2 에서 실제로 겪었다 — 버그 복원 변이 11건이 전건 통과했다).
 *
 * 그래서 2026-08-02 프로덕션(`https://4t8t.net`, main=7741b501)에서 실제로 받은 응답을 박제했다.
 *
 * ## 왜 기대값이 정수 리터럴인가
 *
 * `basis.locatedCount === groups.length` 같은 **항등식**은 항상 참이라 아무것도 잠그지 못한다.
 * 실측 시점의 숫자를 리터럴로 박아야 판별력이 생긴다. 응답에서 파생한 값과 비교하면
 * 양변이 함께 움직여 변이를 통과시킨다.
 *
 * ## 이 골든이 잠그는 것과 **잠그지 못하는 것**(정직 고지)
 *
 * - 잠근다: 셀렉터가 위치 미확인·개략 그룹을 집계에서 배제하는가, 라벨이 근거 없이 반경을
 *   주장하지 않는가, 표본 0일 때 값 대신 사유를 내는가.
 * - **못 잠근다**: 생산처(`nearby_map_service`)가 `location_status`/`coord_precision` 을
 *   **올바르게 채우는가**. 픽스처는 응답을 고정하므로 생산처 회귀는 여기서 안 잡힌다 —
 *   그건 백엔드 골든(`apps/api/tests/test_nearby_map_precision.py`)의 몫이다.
 * - **못 잠근다**: 지오코딩 성공률·캡·사전컷의 상호작용(픽스처 2개로 커버되지 않는다).
 *
 * ## 픽스처는 절단본이다
 *
 * 응답 전체는 수백 KB라 카테고리당 그룹을 3~4개로 잘라 담았다. 따라서 아래 기대값은
 * **이 픽스처 안에서의 실제값**이지 프로덕션 전체 합계가 아니다(예: 역삼 apt 의 프로덕션
 * `count_in_radius` 는 18이지만, 절단된 그룹만 합치면 12다). 둘을 구분해 단언한다.
 */

import { describe, it, expect } from "vitest";
import {
  exclusionNote,
  noSampleReason,
  sampleLabel,
  selectLocatedGroups,
  weightedAvgPrice10k,
} from "@/lib/market/comparable-sample";
import homigot from "./fixtures/nearby-map.homigot.live.json";
import yeoksam from "./fixtures/nearby-map.yeoksam.live.json";

type Payload = { categories?: Record<string, unknown> };

const cat = (p: unknown, key: string) =>
  ((p as Payload).categories as Record<string, never>)[key];

describe("골든 — 호미곶 대보리 산1-1 (위치 확인 0건인 극단 케이스)", () => {
  it("아파트 매매: 위치 확인 그룹이 하나도 선별되지 않는다", () => {
    const { groups } = selectLocatedGroups(cat(homigot, "apt_trade"));
    // 실측: 이 필지 주변 아파트 거래는 전부 지오코딩 실패(오천읍 20~30km 밖 물건들).
    expect(groups.length).toBe(0);
  });

  it("아파트 매매: 평균가를 만들지 않는다(0을 지어내지 않는다)", () => {
    const { groups } = selectLocatedGroups(cat(homigot, "apt_trade"));
    // ★종전 결함: 이 표본으로 1억 1,144만원을 만들어 "분석 반경 1km" 옆에 표시했다.
    expect(weightedAvgPrice10k(groups)).toBeNull();
  });

  it("토지 매매: 탁상감정 거래사례가 될 표본이 없다", () => {
    const { groups, basis } = selectLocatedGroups(cat(homigot, "land_trade"));
    expect(groups.length).toBe(0);
    // 프로덕션 실측 카운트(응답에 실려온 값) — 절단과 무관하게 보존된다.
    expect(basis.unlocatedCount).toBe(7);
  });

  it("표본 0이면 값 대신 사유를 낸다", () => {
    const { basis } = selectLocatedGroups(cat(homigot, "apt_trade"));
    const reason = noSampleReason(basis);
    expect(reason).toContain("찾지 못했습니다");
    expect(reason).toContain("32"); // 위치 미확인 32건 — 실측치
    // "거래가 아예 없다"와 혼동되면 안 된다.
    expect(reason).not.toBe("해당 조건에서 수집된 실거래가 없습니다.");
  });
});

describe("골든 — 강남 역삼동 736 (부분 좌표 케이스)", () => {
  it("아파트 매매: 좌표가 있는 그룹만 선별된다", () => {
    const { groups } = selectLocatedGroups(cat(yeoksam, "apt_trade"));
    // 픽스처 절단본 기준 실제값: 좌표 보유 2그룹.
    expect(groups.length).toBe(2);
  });

  it("아파트 매매: 선별 그룹의 거래 합이 픽스처 실측치와 일치한다", () => {
    const { groups } = selectLocatedGroups(cat(yeoksam, "apt_trade"));
    const sum = groups.reduce((a, g) => a + (g.count ?? 0), 0);
    // ★정수 리터럴 — 셀렉터가 위치 미확인 그룹까지 돌려주면 이 값이 커진다.
    expect(sum).toBe(12);
  });

  it("아파트 매매: 프로덕션 카운트는 별개로 보존된다(절단본과 구분)", () => {
    const { basis } = selectLocatedGroups(cat(yeoksam, "apt_trade"));
    // 응답에 실려온 프로덕션 실측: 반경 내 18건 / 위치 미확인 87건.
    expect(basis.locatedCount).toBe(18);
    expect(basis.unlocatedCount).toBe(87);
  });

  it("토지 매매: 위치 확인 0건 — 강남에서도 탁상감정 표본이 비어 있다", () => {
    const { groups, basis } = selectLocatedGroups(cat(yeoksam, "land_trade"));
    // ★"오염은 시골 한정"이라는 오해를 막는 골든. 강남 토지도 in_radius 0 이다.
    expect(groups.length).toBe(0);
    expect(basis.locatedCount).toBe(0);
    expect(basis.unlocatedCount).toBe(47);
  });

  it("전월세는 좌표 확보율이 높다(비대칭이 실재한다)", () => {
    const { basis } = selectLocatedGroups(cat(yeoksam, "apt_rent"));
    expect(basis.locatedCount).toBe(93);
    expect(basis.unlocatedCount).toBe(0);
  });
});

describe("골든 — 라벨은 근거 없이 반경을 주장하지 않는다", () => {
  it("구버전 페이로드(sample_basis 없음)는 반경 문구를 만들지 않는다", () => {
    // ★배포 스큐·캐시로 구버전 응답이 올 수 있다. 그때 요청 radius 를 에코해 "반경 1km"라고
    //   말하면 그게 바로 이 캠페인이 봉합한 거짓 라벨이다. 모르면 주장하지 않는다.
    const { basis } = selectLocatedGroups(cat(yeoksam, "apt_trade"));
    expect(basis.scope).toBe("sigungu");
    expect(sampleLabel(basis)).toBe("시군구 전체(반경 미적용)");
    expect(sampleLabel(basis)).not.toContain("반경 1");
  });

  it("반경이 실제 적용된 표본만 반경 문구를 얻는다", () => {
    const withRadius = {
      sample_basis: {
        scope: "radius" as const,
        radius_applied: true,
        radius_m: 1000,
        located_count: 18,
        approximate_count: 0,
        unlocated_count: 87,
        capped_count: 0,
      },
      groups: [],
    };
    const { basis } = selectLocatedGroups(withRadius);
    expect(sampleLabel(basis)).toBe("반경 1km 내 위치 확인 거래");
    // 제외분은 숨기지 않는다.
    expect(exclusionNote(basis)).toContain("위치 미확인 87건");
  });

  it("위치 개략(동 단위) 분도 제외 고지에 드러난다", () => {
    const mixed = {
      sample_basis: {
        scope: "radius" as const,
        radius_applied: true,
        radius_m: 1500,
        located_count: 3,
        approximate_count: 20,
        unlocated_count: 5,
        capped_count: 0,
      },
      groups: [],
    };
    const { basis } = selectLocatedGroups(mixed);
    // ★`lat != null` 로는 안 걸리는 분류 — 사용자에게 보여야 한다.
    expect(exclusionNote(basis)).toContain("위치 개략(동 단위) 20건");
    expect(sampleLabel(basis)).toBe("반경 1.5km 내 위치 확인 거래");
  });
});
