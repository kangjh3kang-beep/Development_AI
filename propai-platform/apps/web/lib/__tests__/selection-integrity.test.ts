/**
 * 선택 무결성 판정 — **라이브 오염 3건을 그대로 픽스처로 쓴다**.
 *
 * 픽스처를 지어내지 않는 이유: 오늘 같은 세션에서 내가 지어낸 픽스처가 두 모집단을 못 갈라
 * 변이가 생존했다(`#779` 의 `zoneMixed`). 실측이 이미 갈라 보여 준 값을 그대로 옮긴다.
 *
 * 실측 출처: 프로덕션 `projects.analysis_snapshot` 전수 54건 (2026-08-23 · 168 DB)
 */
import { describe, expect, it } from "vitest";

import {
  classifySelection,
  looksLikeAddress,
  selectionIntegrityNotice,
  type IntegrityParcel,
} from "@/lib/selection-integrity";

/** `4f8a6db5` — 제천 성내리 3 + 제천 모산동 3. **같은 시(제천)인데 15.86km**. */
const MIXED_SAME_CITY: IntegrityParcel[] = [
  { address: "충청북도 제천시 금성면 성내리 산 7-1", areaSqm: 326, lat: 37.036774796729205, lon: 128.17091456609188 },
  { address: "충청북도 제천시 금성면 성내리 산 7-2", areaSqm: 423, lat: 37.03679040853061, lon: 128.1712281568772 },
  { address: "충청북도 제천시 금성면 성내리 산 7-3", areaSqm: 456, lat: 37.036831606395424, lon: 128.17239949810647 },
  { address: "충청북도 제천시 모산동 123-1", areaSqm: 3836, lat: 37.1766866945329, lon: 128.20540025944734 },
  { address: "충청북도 제천시 모산동 123-2", areaSqm: 740, lat: 37.17597027129945, lon: 128.20520471066692 },
  { address: "충청북도 제천시 모산동 123-3", areaSqm: 100, lat: 37.17776273418395, lon: 128.20346119817145 },
];

/** `458d7c86` — 역삼동 + 포항 호미곶 + 의정부. 290km. */
const MIXED_FAR: IntegrityParcel[] = [
  { address: "서울특별시 강남구 역삼동 736", areaSqm: 629.8 },
  { address: "포항시 호미곶면 대보리 산1-1", areaSqm: 147074 },
  { address: "경기도 의정부시 의정부동 224", areaSqm: 14958.7 },
];

/** `ad66982a` — 소유자명이 주소 칸에. ★13필지 **전부 좌표 없음**(거리로는 못 잡는다). */
const MALFORMED: IntegrityParcel[] = [
  { address: "◀ 전성결", areaSqm: 0 },
  { address: "경기도 용인시 수지구 고기동 689", areaSqm: 372 },
  { address: "경기도 용인시 수지구 고기동 696-1", areaSqm: 628 },
  { address: "◀ 전성결외 4인", areaSqm: 0 },
  { address: "◀ 김영효", areaSqm: 0 },
  { address: "◀ 더윙홀딩스", areaSqm: 0 },
];

/** ★위양성 대조군 — 표기가 달라도 같은 지역(`경기도 용인시` vs `용인시`). */
const NORMAL_SAME_AREA: IntegrityParcel[] = [
  { address: "경기도 용인시 수지구 고기동 689", areaSqm: 372, lat: 37.32, lon: 127.05 },
  { address: "용인시 수지구 고기동 696-1", areaSqm: 628, lat: 37.321, lon: 127.051 },
  { address: "경기도 용인시 수지구 고기동 703-1", areaSqm: 1577, lat: 37.322, lon: 127.052 },
];

describe("주소 형태 검증 — addressRegionMismatch 의 사각을 메운다", () => {
  it("소유자명·법인명은 주소가 아니다", () => {
    for (const v of ["◀ 전성결", "◀ 전성결외 4인", "◀ 김영효", "◀ 더윙홀딩스"]) {
      expect(looksLikeAddress(v), v).toBe(false);
    }
  });

  it("★위양성 방지 — 실제 주소는 전부 통과한다(표기 차이 포함)", () => {
    for (const v of [
      "충청북도 제천시 금성면 성내리 산 7-1",
      "용인시 수지구 고기동 696-1",
      "포항시 호미곶면 대보리 산1-1",
      "상도동 210-453",
      "서울특별시 강남구 역삼동 736",
      "경기도 용인시 수지구 고기동 산 84",
    ]) {
      expect(looksLikeAddress(v), v).toBe(true);
    }
  });
});

describe("classifySelection — 라이브 오염 3건", () => {
  it("A) 같은 시(제천) 안 15.86km 혼합을 잡는다 — ★시군구만 보면 놓치는 케이스", () => {
    const r = classifySelection(MIXED_SAME_CITY);
    expect(r.verdict).toBe("multi_region");
    expect(r.regionGroups).toHaveLength(2); // 성내리 · 모산동
    expect(r.malformedRows).toEqual([]);
    // 좌표 확산이 실측치(15.86km) 근방이어야 한다 — 고지 문구가 이 숫자를 쓴다.
    expect(r.spreadKm).toBeGreaterThan(15);
    expect(r.spreadKm).toBeLessThan(17);
  });

  it("B) 290km 혼합을 잡는다 — ★좌표가 하나도 없어도(거리 미상) 판정된다", () => {
    const r = classifySelection(MIXED_FAR);
    expect(r.verdict).toBe("multi_region");
    expect(r.regionGroups).toHaveLength(3);
    // 좌표가 없으면 거리는 **미상(null)** — 0 이 아니다(무목업).
    expect(r.spreadKm).toBeNull();
  });

  it("C) 소유자명이 섞이면 malformed 가 우선한다 — ★좌표 전무해도 잡힌다", () => {
    const r = classifySelection(MALFORMED);
    expect(r.verdict).toBe("malformed");
    expect(r.malformedRows).toEqual(["◀ 전성결", "◀ 전성결외 4인", "◀ 김영효", "◀ 더윙홀딩스"]);
    expect(r.spreadKm).toBeNull();
  });

  it("★D) 위양성 방지 — 같은 지역(표기 차이 포함)은 single_site", () => {
    const r = classifySelection(NORMAL_SAME_AREA);
    expect(r.verdict).toBe("single_site");
    expect(r.regionGroups).toHaveLength(1);
    expect(r.malformedRows).toEqual([]);
    // 대조군이 실제로 가까운지도 확인 — 픽스처가 공허하지 않게.
    expect(r.spreadKm).not.toBeNull();
    expect(r.spreadKm!).toBeLessThan(1);
  });

  it("E) 단일 필지·빈 목록은 single_site(비교 대상 없음)", () => {
    expect(classifySelection([{ address: "서울특별시 강남구 역삼동 736" }]).verdict).toBe("single_site");
    expect(classifySelection([]).verdict).toBe("single_site");
    expect(classifySelection(null).verdict).toBe("single_site");
  });

  it("★F) 단일 필지라도 그 값이 주소가 아니면 malformed — 지역 비교가 없는 경로", () => {
    // ★변이가 잡아낸 구멍: 종전 스위트는 malformed 를 **2필지 이상**으로만 태웠다.
    //   `list.length >= 2` 분기 밖의 단일 필지 경로가 무잠금이라 그 줄을 지워도 초록이었다.
    //   실측 `ad66982a` 는 `siteAnalysis.address` **자체**가 `◀ 전성결` 이다 — 이 경로가 실재한다.
    const r = classifySelection([{ address: "◀ 전성결", areaSqm: 0 }]);
    expect(r.verdict).toBe("malformed");
    expect(r.malformedRows).toEqual(["◀ 전성결"]);
  });
});

describe("고지 문구 — 사실 + 무엇이 무효인가 + 복구 방법", () => {
  it("multi_region 은 '통합 대지면적이 아니다'를 말하고 거리를 싣는다", () => {
    const n = selectionIntegrityNotice(classifySelection(MIXED_SAME_CITY))!;
    expect(n).not.toBeNull();
    expect(n.tone).toBe("warn");
    expect(n.title).toContain("하나의 개발 부지가 아닙니다");
    expect(n.detail).toContain("합계 면적은 보여 주지만 통합 대지면적이 아니며");
    expect(n.detail).toMatch(/최대 15\.\d+km/); // 실측 거리가 문구에 실려야 한다
    // ★복구 방법 문장 전체를 잠근다 — "후보지 비교면 그대로 둬도 된다"가 이 고지의 핵심이다
    //   (차단이 아니라 고지라는 정책이 문구에 실려 있다). 변이 생존분.
    expect(n.detail).toContain("후보지 비교라면 그대로 두어도 되고");
    expect(n.detail).toContain("필지 선택/변경"); // 복구 방법
  });

  it("malformed 는 원문 샘플과 원인 가설을 함께 낸다", () => {
    const n = selectionIntegrityNotice(classifySelection(MALFORMED))!;
    expect(n.tone).toBe("bad");
    expect(n.detail).toContain("◀ 전성결");
    expect(n.detail).toContain("소유자");
    // ★복구 방법 문장도 잠근다 — 이것이 없으면 사용자는 무엇을 해야 할지 모른다(변이 생존분).
    expect(n.detail).toContain("해당 행을 지우고 지번을 다시 지정하세요");
  });

  it("★고지 문구에 **마크다운 잔재가 없다** — 화면은 평문을 그대로 그린다", () => {
    // ★라이브에서 발견한 내 결함: `**통합 대지면적이 아니며**` 로 써서 화면에 **별표가 글자로**
    //   나갔다. 종전 단언은 `toContain("통합 대지면적이 아니며")` 라 **별표를 피해서** 통과했다
    //   — 부분 문자열 단언은 그 앞뒤 마크업 잔재를 못 본다.
    //   그래서 부분이 아니라 **문구 전체**를 마크다운 문자로 훑는다(파생형 — 새 문구가 생겨도 걸린다).
    for (const sample of [MIXED_SAME_CITY, MIXED_FAR, MALFORMED]) {
      const n2 = selectionIntegrityNotice(classifySelection(sample));
      expect(n2, "고지가 있어야 이 검사가 공허하지 않다").not.toBeNull();
      for (const text of [n2!.title, n2!.detail]) {
        expect(text, `마크다운 강조가 평문으로 새어나갔다: ${text}`).not.toMatch(/\*\*/);
        expect(text, `마크다운 기울임/코드가 새어나갔다: ${text}`).not.toMatch(/[_`~]{2}|<\/?[a-z]/i);
      }
    }
  });

  it("★정상이면 고지하지 않는다 — 남발은 무시로 이어진다", () => {
    expect(selectionIntegrityNotice(classifySelection(NORMAL_SAME_AREA))).toBeNull();
    expect(selectionIntegrityNotice(classifySelection([{ address: "서울특별시 강남구 역삼동 736" }]))).toBeNull();
  });
});
