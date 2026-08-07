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
  kmText,
  noSampleReason,
  sampleLabel,
  selectLocatedGroups,
  selectMappableGroups,
  weightedAvgPrice10k,
} from "@/lib/market/comparable-sample";
import homigot from "./fixtures/nearby-map.homigot.live.json";
import yeoksam from "./fixtures/nearby-map.yeoksam.live.json";
import newContract from "./fixtures/nearby-map.newcontract.generated.json";
// ★백엔드와 **공유하는 값 골든**. 백엔드 pytest 가 자기 출력이 이 파일과 같은지 보고,
//   아래 테스트가 TS 출력이 같은 파일과 같은지 본다 — 어느 쪽 문구를 바꾸든 깨진다.
import sharedCases from "./fixtures/no-sample-reason.cases.json";

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
    // ★R1 리뷰(m-4) flip — `sampleLabel()` 은 명사구라 "~가 없습니다"를 붙이면
    //   "시군구 전체(반경 미적용)가 없습니다" 같은 비문이 된다. 범위별 완성 문장으로 바꿨다.
    expect(reason).toContain("위치가 확인된 거래가 없습니다");
    expect(reason).toContain("32"); // 위치 미확인 32건 — 실측치
    // "거래가 아예 없다"와 혼동되면 안 된다.
    expect(reason).not.toContain("수집된 거래가 없습니다");
  });

  it("★★백엔드와 값이 정확히 같다(공유 골든 전건 대조)", () => {
    // R2 리뷰(M-3) — 종전 "문구 일치"는 소스 조각 grep 이라 값이 갈려도 통과했다.
    expect(sharedCases.length).toBeGreaterThan(0);
    for (const c of sharedCases) {
      const basis = {
        scope: c.scope as "radius" | "sigungu" | "unknown",
        radiusApplied: c.scope === "radius",
        radiusM: c.radius_m,
        locatedCount: c.located ?? 0,
        approximateCount: c.approximate,
        unlocatedCount: c.unlocated,
        cappedCount: c.capped ?? 0,
        maskedJibunCount: c.masked,
        maskedJibunGroupCount: c.masked_groups,
      };
      // ★R5(F-5) — 문구 3종을 **전부** 백엔드와 대조한다(종전엔 사유 하나뿐이었다).
      expect(sampleLabel(basis)).toBe(c.expected_label);
      expect(exclusionNote(basis)).toBe(c.expected_exclusion);
      if (c.expected !== null) expect(noSampleReason(basis)).toBe(c.expected);
    }
  });

  it("★마스킹 지번이 원인이면 그 사실을 말한다(백엔드와 같은 문구)", () => {
    // 원천이 지번을 가려 준 상태 — "거래가 없다"와 전혀 다른 상태다.
    const basis = {
      scope: "radius" as const, radiusApplied: true, radiusM: 1500,
      locatedCount: 0, approximateCount: 0, unlocatedCount: 5, cappedCount: 0,
      maskedJibunCount: 5, maskedJibunGroupCount: 2,
    };
    const reason = noSampleReason(basis);
    expect(reason).toContain("지번을 가려서");
    expect(reason).toContain("5*");
    // ★마스킹은 위치 미확인의 부분집합이다 — 같은 거래를 두 번 세면 안 된다.
    expect(reason).toContain("위치 미확인 중 5건");
  });

  it("★★구버전 폴백이 그룹에서 마스킹을 센다(프론트 변이 감사 적발)", () => {
    // 백엔드는 이 폴백을 잠갔는데 **프론트 미러는 구멍**이었다 — `maskedJibunCount:
    // fromGroups.deals` 를 지워도 통과했다(변이 감사). 미러 계약의 절반만 잠근 셈이다.
    // ★두 모집단을 가른다 — 마스킹 그룹과 정상 그룹이 서로 다른 수를 내야 한다.
    const { basis } = selectLocatedGroups({
      // sample_basis 없음 = 구버전 페이로드(배포 스큐·캐시)
      groups: [
        { jibun: "5*", count: 3 },
        { jibun: "1**", count: 2 },
        { jibun: "736", count: 9 },
      ],
    });
    expect(basis.maskedJibunCount).toBe(5);
    expect(basis.maskedJibunGroupCount).toBe(2);
  });

  it("★신형 페이로드의 마스킹 카운트가 도메인 객체에 배선된다(R2 M-4)", () => {
    // 백엔드 `test_sample_basis_reads_masked_count_from_modern_payload` 의 미러.
    // ★두 축이 서로 다른 값이어야 단위 배선이 판별된다.
    const { basis } = selectLocatedGroups({
      sample_basis: {
        scope: "radius", radius_applied: true, radius_m: 1500,
        located_count: 0, approximate_count: 5, unlocated_count: 8,
        masked_jibun_count: 13, masked_jibun_group_count: 4, capped_count: 0,
      },
      // 그룹엔 마스킹이 없다 — 폴백이 아니라 sample_basis 경로를 태웠는지 구분한다.
      groups: [{ jibun: "736", count: 99 }],
    });
    expect(basis.maskedJibunCount).toBe(13);
    expect(basis.maskedJibunGroupCount).toBe(4);
  });

  it("★마스킹 키 부재를 0 으로 단정하지 않는다(R2 M-4 · 배포 스큐)", () => {
    // 실제 스큐는 "sample_basis 는 있고 마스킹 키만 없는" 형태다.
    const { basis } = selectLocatedGroups({
      sample_basis: {
        scope: "radius", radius_applied: true, radius_m: 1500,
        located_count: 0, approximate_count: 0, unlocated_count: 5, capped_count: 0,
      },
      groups: [
        { jibun: "5*", count: 3 },
        { jibun: "1**", count: 2 },
      ],
    });
    expect(basis.maskedJibunCount).toBe(5);
    expect(basis.maskedJibunGroupCount).toBe(2);
  });

  it("★반경 표기가 백엔드와 같다(비라운드 값 포함 — R2 M-3)", () => {
    expect(kmText(1000)).toBe("1");
    expect(kmText(1500)).toBe("1.5");
    // ★여기가 갈렸던 지점 — 종전 미러는 1250 → "1.3", 백엔드는 "1.25".
    expect(kmText(1250)).toBe("1.25");
    expect(kmText(1234)).toBe("1.234");
    expect(kmText(300)).toBe("0.3");
    // 같은 파일 안 두 소비처가 같은 표기를 쓴다(종전엔 세 표기가 공존했다).
    const b = {
      scope: "radius" as const, radiusApplied: true, radiusM: 1250,
      locatedCount: 1, approximateCount: 0, unlocatedCount: 0, cappedCount: 0,
      maskedJibunCount: 0, maskedJibunGroupCount: 0,
    };
    expect(sampleLabel(b)).toContain("1.25km");
    expect(noSampleReason({ ...b, locatedCount: 0 })).toContain("1.25km");
  });

  it("★마스킹 1건이 위치 미확인 80건을 가리지 않는다(누적 서술)", () => {
    // R1 리뷰(M-3): 배타 분기였을 때 마스킹이 크기와 무관하게 선점해 80건이 사라졌다.
    const basis = {
      scope: "radius" as const, radiusApplied: true, radiusM: 1000,
      locatedCount: 0, approximateCount: 30, unlocatedCount: 50, cappedCount: 0,
      maskedJibunCount: 1, maskedJibunGroupCount: 1,
    };
    const reason = noSampleReason(basis);
    expect(reason).toContain("50"); // 위치 미확인이 사라지지 않는다
    expect(reason).toContain("30"); // 동 단위 확인분도
    expect(reason).toContain("지번을 가려서");
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
    // ★M-1 봉합 — 구버전 페이로드는 반경 적용 여부를 **모른다**. "미적용"이라 단정하면
    //   그것도 거짓이다(이 픽스처의 최상위는 실제로 radius_applied=true 다).
    expect(basis.scope).toBe("unknown");
    expect(sampleLabel(basis)).toBe("표본 범위 확인 불가");
    expect(sampleLabel(basis)).not.toContain("반경 1");
    expect(sampleLabel(basis)).not.toContain("미적용");
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

describe("골든 — 신 계약(location_status · coord_precision) 실행 경로", () => {
  /**
   * ★리뷰(H-2 부속) 봉합 — 위 두 라이브 픽스처는 **구버전 백엔드 응답**이라
   * `sample_basis`·`location_status`·`coord_precision` 이 하나도 없다. 그래서 셀렉터의
   * 신 계약 경로가 **한 줄도 실행되지 않았고**, 그 분기를 삭제해도 골든이 전건 통과했다.
   *
   * 이 픽스처는 **생산처(`NearbyMapService.build`)를 실제로 실행해** 만들었다 — 손으로
   * 채우면 "테스트가 값을 넣고 셀렉터가 그걸 존중하는지"만 보는 동어반복이 된다(#516 R2).
   */
  it("세 상태가 모두 담긴 픽스처다(판별력 확인)", () => {
    const c = cat(newContract, "apt_trade") as { groups: Array<{ location_status: string }> };
    const statuses = c.groups.map((g) => g.location_status).sort();
    expect(statuses).toEqual(["approximate", "located", "unlocated"]);
  });

  it("집계는 located 만 — 개략(동 단위)도 배제한다", () => {
    const { groups, basis } = selectLocatedGroups(cat(newContract, "apt_trade"));
    expect(groups.length).toBe(1);
    expect(basis.locatedCount).toBe(2);
    expect(basis.approximateCount).toBe(1);
    expect(basis.unlocatedCount).toBe(1);
  });

  it("반경이 실제 적용됐으므로 반경 문구를 만든다", () => {
    const { basis } = selectLocatedGroups(cat(newContract, "apt_trade"));
    expect(basis.scope).toBe("radius");
    expect(sampleLabel(basis)).toBe("반경 1km 내 위치 확인 거래");
    expect(exclusionNote(basis)).toContain("위치 개략(동 단위) 1건");
  });

  it("마커 셀렉터는 개략 좌표도 포함한다(집계와 기준이 다르다)", () => {
    const mappable = selectMappableGroups(cat(newContract, "apt_trade"));
    // located 1 + approximate 1 = 2 (unlocated 는 좌표가 없어 못 찍는다)
    expect(mappable.length).toBe(2);
  });
});
