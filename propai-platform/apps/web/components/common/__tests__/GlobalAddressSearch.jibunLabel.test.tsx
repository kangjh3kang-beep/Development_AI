/**
 * 인테이크 목록이 **지번을 보여준다** — 사용자 재신고(2026-08-21) 회귀망.
 *
 * 증상: `/ko/permits` 좌측 "검색·등록 주소" 77행이 전부 `"경기도 오산시 내삼미동"` 이었다.
 * 같은 데이터가 메인 대시보드에서는 `"내삼미동 467-1"` 로 정상 표시됐다.
 *
 * ★이 테스트는 **그 화면이 실제로 데이터를 받는 경로**를 태운다 —
 *   프로젝트 하이드레이션(`siteAnalysis.parcels` → `fullAddress: p.address` + `pnu`).
 *   순수 함수만 잠그면 소비처가 원시 필드로 되돌아가도 초록이다(정의만 하고 소비처 0).
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { __stripCommentsForScan } from "@/lib/source-invariant";
import { useProjectContextStore } from "@/store/useProjectContextStore";

vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  dynamicMap: () => function S() { return <div />; },
}));
vi.mock("@/components/ui/KakaoAddressSearch", () => ({
  KakaoAddressSearch: () => <div />,
}));
vi.mock("next/dynamic", () => ({
  default: () => function S() { return <div data-testid="satong-multi-map" />; },
}));

const 동 = "경기도 오산시 내삼미동";

beforeEach(() => {
  useProjectContextStore.setState({
    siteAnalysis: {
      address: 동,
      parcels: [
        // 사용자 데이터 모양 그대로 — 주소는 **동 단위**, 지번은 **PNU 안에만** 있다.
        { address: 동, pnu: "4137010900100380000", areaSqm: 53 },
        { address: 동, pnu: "4137010900104670001", areaSqm: 684 },
      ],
    },
  } as never);
});

describe("인테이크 목록 지번 표시", () => {
  it("★동 단위 주소 + PNU 인 필지가 목록에서 **지번과 함께** 보인다", async () => {
    render(<GlobalAddressSearch single={false} writeToContext />);

    // 공허한 참 방지 — 목록이 실제로 두 행을 그렸는지 먼저 확인한다.
    expect(await screen.findAllByText(new RegExp(`${동} \\d`))).toHaveLength(2);
    // 지번이 실제로 붙었다(38 · 467-1).
    expect(screen.getAllByText(`${동} 38`).length).toBeGreaterThan(0);
    expect(screen.getAllByText(`${동} 467-1`).length).toBeGreaterThan(0);
  });

  it("★대조군 — 두 행이 **서로 다른** 라벨이다(같은 값이면 배선을 끊어도 통과한다)", async () => {
    render(<GlobalAddressSearch single={false} writeToContext />);
    const rows = await screen.findAllByText(new RegExp(`${동} \\d`));
    const labels = new Set(rows.map((n) => n.textContent?.trim()));
    expect(labels.size).toBe(2);
    // 동 단위 주소만 있는 행(=지번 소실)이 **하나도 없어야** 한다.
    expect(screen.queryAllByText(동)).toHaveLength(0);
  });

  // ────────────────────────────────────────────────────────────────────────
  // ★부채 상환(2026-08-22) — 종전 `it.todo` 5건을 **실제 잠금**으로 바꿨다.
  //
  // 종전 주석은 "각 화면의 렌더 경로를 세우는 비용이 커서 다음으로 미룬다"였다.
  // 상환하면서 **무엇을 잠갔는지 정직하게 적는다**:
  //   · 신고 표면(인테이크 목록)은 **위의 실제 렌더**로 잠겨 있다(변경 없음).
  //   · 아래 5곳은 **소스 불변식**이다 — 런타임 증명이 아니라 *"이 표면이 공용 함수를
  //     계속 쓰는가"* 를 본다. 그게 이 부채가 막으려던 회귀(원시 필드로 되돌아감)의 실체다.
  //   · 주석·문자열 변이에는 뚫리지 않는다(`__stripCommentsForScan` 경유).
  //
  // ★왜 파생(전수) 가드로 만들지 않았나 — 실측했고 **기각**했다.
  //   `X.jibunAddress || X.fullAddress` 형태를 전면 금지하면 정당한 용례가 걸린다:
  //   `GlobalAddressSearch:530`(parse-parcels 원본 전달 — 백엔드가 소재지·지번을 나눠 받는다)
  //   `:656`(지번 해석 로직) · `lib/parcel-rows.ts:48`(SSOT 자신).
  //   **가드의 위양성도 결함**이라 목록형을 택했다 — 대신 아래 대조군이 목록의 공허함을 막는다.
  // ────────────────────────────────────────────────────────────────────────
  const scanned = (file: string) =>
    __stripCommentsForScan(readFileSync(resolve(process.cwd(), file), "utf-8"), file);

  /**
   * ★**import 줄을 뺀** 소스 — 이 가드가 실제로 뚫린 자리다.
   *
   * 처음엔 `expect(src).toContain("preferredEntryAddress")` 였는데, 변이검증에서
   * **호출을 전부 원시 필드로 되돌려도 초록**이었다. `import { preferredEntryAddress }` 줄이
   * 남아 있어 문자열이 계속 매치됐기 때문이다 — CLAUDE.md 가 *"이 저장소를 두 번 관통했다"* 고
   * 적은 **"주석처리 + 임포트 유지"** 변이를 내 가드에서 그대로 재현한 것이다.
   * → import 줄을 걷어내고 **호출 형태**(`이름(`)를 본다.
   */
  const scannedWithoutImports = (file: string) =>
    scanned(file)
      .split("\n")
      .filter((l) => !/^\s*import\b/.test(l))
      .join("\n");

  const HELPER_SURFACES: ReadonlyArray<[file: string, what: string]> = [
    ["components/common/BulkParcelBatchPanel.tsx", "반경검색 중심 주소"],
    ["components/pipeline/ProjectPipelinePanel.tsx", "파이프라인 payload·선택 필지 표시"],
    ["components/precheck/PreCheckWorkspace.tsx", "사전검토 주소 수집"],
    ["components/feasibility/AutoRecommendPanel.tsx", "자동추천 필지 목록"],
    ["components/projects/ProjectSiteAnalysisWorkspaceClient.tsx", "부지분석 주소 자동채움"],
    ["components/projects/SiteInitiator.tsx", "프로젝트 착수 주소"],
    ["app/[locale]/(dashboard)/projects/new/page.tsx", "신규 프로젝트 위치"],
  ];

  it.each(HELPER_SURFACES)("%s — %s 가 공용 표시함수를 **호출**한다", (file) => {
    // ★임포트만 남은 상태를 통과시키지 않는다(위 주석의 그 변이).
    expect(scannedWithoutImports(file)).toContain("preferredEntryAddress(");
  });

  it("GlobalAddressSearch — 지도 feature·대지지분 모달이 원시 필드로 되돌아가지 않았다", () => {
    const src = scannedWithoutImports("components/common/GlobalAddressSearch.tsx");
    // ①양성 — 두 자리 모두 공용 함수를 쓴다.
    expect(src).toContain('address: preferredEntryAddress(a) || "필지"');
    expect(src).toContain("jibun={preferredEntryAddress(shareParcel)}");
    // ②음성 — 되돌아간 형태가 없다(부재 단언은 위 양성과 **같은 실행**에서만 의미가 있다).
    expect(src).not.toContain("a.fullAddress || a.jibunAddress || a.roadAddress");
    expect(src).not.toContain("shareParcel.jibunAddress || shareParcel.fullAddress");
  });

  it("★대조군 — 목록이 실제 파일을 가리킨다(오타·이동으로 공허해지지 않는다)", () => {
    // 사람이 센 목록의 최대 위험은 **파일이 사라졌는데 검사만 남는 것**이다.
    for (const [file] of HELPER_SURFACES) {
      expect(existsSync(resolve(process.cwd(), file)), `${file} 가 없다 — 목록이 낡았다`).toBe(true);
    }
    // 그리고 그 파일들이 실제로 AddressEntry 소비처여야 이 검사가 의미를 가진다.
    expect(HELPER_SURFACES.length).toBeGreaterThanOrEqual(7);
  });
});
