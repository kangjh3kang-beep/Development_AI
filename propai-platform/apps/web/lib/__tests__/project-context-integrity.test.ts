/**
 * 프로젝트 컨텍스트 정합 — **레코드와 스냅샷을 묶는 불변식이 없어서** 화면이 두 프로젝트를
 * 섞어 말하던 것(2026-08-24 사용자 스크린샷).
 *
 * ## 사용자가 본 것
 *
 *     헤더:  프로젝트 "모산동 123-1 외 6필지"   ← 프로젝트 A
 *            주소     "제천시 금성면 성내리 산 7-1" ← 프로젝트 B
 *            대지면적  5,781㎡ (레코드) ↔ 5,881㎡ (스냅샷 필지합)  ← 화면마다 다름
 *
 * ## 이 파일이 잠그는 것
 *
 * ① `setProject` **전환 분기**의 오염 가드 — 같은 함수의 *같은 id 재바인딩* 분기에는 이 검사가
 *    있었는데 **실제 전환에는 없었다**(형제 비대칭). `snapshots[id]` 를 무검사 복원하면
 *    다른 지역의 분석이 전환하는 순간 그대로 화면에 올라온다.
 * ② `buildSiteMetaPatch` 의 면적 보강이 **자가치유를 되돌리지 않는다** — 치유기가 유령 면적을
 *    치운 직후(같은 useEffect, 세 줄 뒤) 레코드 값으로 되살리고 있었고, 치유기는 자기가 비운
 *    필드 때문에 **재검출조차 못 했다**.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { buildSiteMetaPatch } from "@/lib/project-site-meta";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";

function seedProjectWithAnalysis(id: string, address: string) {
  useProjectContextStore.getState().setProject(id, `프로젝트 ${id.slice(0, 4)}`, "draft", address);
  useProjectContextStore.setState({
    siteAnalysis: { address, landAreaSqm: 1000, zoneCode: null, pnu: null, estimatedValue: null },
  } as never);
}

describe("① setProject 전환 분기 — 스냅샷 무검사 복원 차단", () => {
  beforeEach(() => {
    useProjectContextStore.setState({
      projectId: null, projectName: "", siteAnalysis: null, snapshots: {},
    } as never);
  });

  it("★다른 지역 분석이 캐시된 프로젝트로 전환하면 그 분석을 복원하지 않는다", () => {
    // A 에서 제천 분석을 해 두고 → B 로 갔다가 → 다시 A 로 돌아온다.
    // 단, A 의 프로젝트 레코드 주소는 **서울**이다(= 캐시가 A 것이 아니다).
    seedProjectWithAnalysis(A, "충청북도 제천시 금성면 성내리 산 7-1");
    useProjectContextStore.getState().setProject(B, "B", "draft", "서울특별시 동작구 상도동 211-204");

    // A 로 복귀 — 레코드 주소는 서울인데 캐시된 분석은 제천이다.
    useProjectContextStore.getState().setProject(A, "A", "draft", "서울특별시 동작구 상도동 210-453");

    const site = useProjectContextStore.getState().siteAnalysis;
    expect(
      site?.address ?? "",
      "다른 지역 캐시가 전환과 함께 그대로 복원됐다 — 헤더가 두 프로젝트를 섞어 말하게 된다",
    ).not.toContain("제천");
  });

  it("[양성 대조군] 같은 지역이면 캐시를 정상 복원한다 — 사용자가 한 분석을 잃지 않는다", () => {
    seedProjectWithAnalysis(A, "서울특별시 동작구 상도동 210-453");
    useProjectContextStore.getState().setProject(B, "B", "draft", "충청북도 제천시 모산동 123-1");
    useProjectContextStore.getState().setProject(A, "A", "draft", "서울특별시 동작구 상도동 210-453");

    const site = useProjectContextStore.getState().siteAnalysis;
    expect(site?.address, "정상 캐시까지 날렸다 — 과차단").toContain("상도동");
    expect(site?.landAreaSqm, "정상 복원인데 면적을 잃었다").toBe(1000);
  });
});

describe("② 면적 보강이 자가치유를 되돌리지 않는다", () => {
  const META = { address: "충청북도 제천시 모산동 123-1", total_area_sqm: 164823 };

  it("★저장된 분석이 있는데 면적이 비어 있으면 = 치워진 것 → 레코드 값으로 되살리지 않는다", () => {
    const site = { address: META.address, landAreaSqm: null } as never;
    const patch = buildSiteMetaPatch(site, META, { hasStoredAnalysis: true });
    expect(
      "landAreaSqm" in patch,
      "치유기가 치운 유령 면적을 세 줄 뒤에서 되살렸다",
    ).toBe(false);
  });

  it("[양성 대조군] 저장된 분석이 없으면(갓 만든 프로젝트) 종전대로 보강한다", () => {
    const site = { address: META.address, landAreaSqm: null } as never;
    const patch = buildSiteMetaPatch(site, META, { hasStoredAnalysis: false });
    expect(patch.landAreaSqm, "신규 프로젝트가 면적을 잃었다 — 이 처방의 첫 설계가 만든 회귀").toBe(164823);
  });

  it("[양성 대조군] 옵션 미지정(구 호출부)은 동작이 바뀌지 않는다", () => {
    const site = { address: META.address, landAreaSqm: null } as never;
    expect(buildSiteMetaPatch(site, META).landAreaSqm).toBe(164823);
  });

  it("★주소·용도지역 보강은 그대로다 — 부지 게이트(U1) 계약 불변", () => {
    const patch = buildSiteMetaPatch(
      { address: null, landAreaSqm: null } as never,
      { ...META, zone_type: "보전관리지역" },
      { hasStoredAnalysis: true },
    );
    expect(patch.address, "면적 가드가 주소 보강까지 막았다 — 통합분석이 '부지 필요'로 막힌다").toBe(META.address);
    expect(patch.zoneCode).toBe("보전관리지역");
  });
});
