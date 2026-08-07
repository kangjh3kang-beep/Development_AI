/**
 * `collectBackdrops` / `resolveModuleSpec` 파서 단위 잠금.
 *
 * ★수집기는 **통짜 문자열 리터럴 className 만** 본다(2026-08-07 R3 판정으로 범위를 줄였다).
 *   비리터럴(삼항·`cn()`·템플릿·상수 조립) 파서를 만들었다가 3라운드 연속 위양성을 생산했고,
 *   실측상 그 코드가 지키는 대상은 전 저장소 1건(그마저 준수)이었다. 폐포 백드롭 8건은
 *   전부 리터럴이라 축소해도 **감시 8/8 유지**다.
 * ★그래서 여기 픽스처는 두 가지를 잠근다: ①리터럴 수집이 정확한가 ②**위양성을 만들지 않는가**.
 *   그리고 해석기(`resolveModuleSpec`)는 폐포 단언으로 원리적으로 잠기지 않는 분기가 있어
 *   여기서 분기별로 잠근다.
 */
import { describe, expect, it } from "vitest";

import { collectBackdrops, importClosure, resolveModuleSpec } from "@/lib/source-invariant";

describe("collectBackdrops — 백드롭 className 파서", () => {
  it("★리터럴 백드롭에서 z 를 읽는다", () => {
    const hits = collectBackdrops(`<div className="fixed inset-0 z-[800] bg-black/60" />`);
    expect(hits).toHaveLength(1);
    expect(hits[0].zs).toEqual([800]);
  });

  it("★`className={\"…\"}`(중괄호 안 통짜 리터럴)도 같은 리터럴로 본다", () => {
    // 이 저장소에 실사용 1건이 있다(SatongMultiMap:2945 — 백드롭은 아니다).
    // 변이검증이 이 지원을 무잠금으로 적발해 추가했다.
    const hits = collectBackdrops(`<div className={"fixed inset-0 z-[800]"} />`);
    expect(hits).toHaveLength(1);
    expect(hits[0].zs).toEqual([800]);
  });

  it("★반대로 **표현식**은 보지 않는다 — 축소된 범위를 단언으로 못 박는다", () => {
    // `cn(...)`·삼항·템플릿·상수는 수집 대상이 아니다(it.todo 로 부채를 드러낸 그 경계).
    expect(collectBackdrops(`<div className={cn("fixed inset-0 z-50")} />`)).toHaveLength(0);
    expect(collectBackdrops(`<div className={\`fixed inset-0 z-50\`} />`)).toHaveLength(0);
    expect(collectBackdrops(`<div className={BACKDROP_CLS} />`)).toHaveLength(0);
  });

  it("★`z-50`(대괄호 없는 표기)도 같은 값으로 읽는다", () => {
    expect(collectBackdrops(`<div className="fixed inset-0 z-50 p-4" />`)[0].zs).toEqual([50]);
  });

  it("★z 유틸이 없으면 빈 배열로 보고한다(소비처가 위반으로 판정할 수 있게)", () => {
    expect(collectBackdrops(`<div className="fixed inset-0 bg-black/60" />`)[0].zs).toEqual([]);
  });

  it("★위양성 금지 — `pointer-events-none` 배경 장식은 백드롭이 아니다", () => {
    // 실측 2건(AuthWorkspaceClient·PasswordRecoveryClient)이 이 형태다. 위반으로 신고하면
    // 정상 코드가 막힌다.
    expect(
      collectBackdrops(`<div className="pointer-events-none fixed inset-0 -z-10 bg-[var(--x)]" />`),
    ).toHaveLength(0);
  });

  it("★위양성 금지 — `inset-0` 없이 fixed 만 있는 요소는 백드롭이 아니다", () => {
    expect(collectBackdrops(`<div className="fixed bottom-4 right-4 z-50" />`)).toHaveLength(0);
  });

  it("★부분일치로 오인하지 않는다 — `inset-0.5`·`not-fixed` 는 다른 클래스다", () => {
    expect(collectBackdrops(`<div className="fixed inset-0.5 z-50" />`)).toHaveLength(0);
  });

  it("★주석 처리된 백드롭은 세지 않는다 — JSX 주석·줄 주석 둘 다", () => {
    expect(collectBackdrops(`{/* <div className="fixed inset-0 z-50" /> */}`)).toHaveLength(0);
    expect(collectBackdrops(`// <div className="fixed inset-0 z-50" />`)).toHaveLength(0);
  });

  it("★변이 prefix 가 붙은 z 도 읽는다 — `md:z-50` 으로 계약을 빠져나가지 못하게", () => {
    // 종전 정규식은 `md:`·`dark:`·`group-hover:` 앞에서 끊겨, "준수처럼 보이면서 특정
    // 브레이크포인트에서만 z-50 으로 떨어지는" 백드롭이 통과했다(독립 검증 M1).
    const hits = collectBackdrops(`<div className="fixed inset-0 z-[800] md:z-50" />`);
    expect(hits[0].zs.sort((a, b) => a - b)).toEqual([50, 800]);
  });

  it("★★블록 주석을 벗기려다 만든 맹점의 회귀락 — 줄주석·문자열 안의 `/*` 뒤 코드가 살아 있어야 한다", () => {
    // R1 에서 `/* … */` 스트립을 넣었다가 **474파일·9,882줄의 실코드를 삼켰다**(R2 실측).
    // 이 저장소엔 줄주석 안의 `/*`(`// /auction/* 는 …`)와 문자열 안의 `/*`(`image/*`)가 흔한데,
    // 그게 블록 주석 시작으로 잡혀 다음 `*/` 까지 통째로 공백이 됐다 — 지도 시드인
    // AuctionMonitorPanel 에 z-50 을 주입해도 계약이 초록이었다.
    const src = [
      `// 경로 규칙: /auction/* 는 RBAC 게이트를 탄다`,
      `<input accept=".dxf,image/*" />`,
      `const x = 1; /* 진짜 블록 주석 */`,
      `<div className="fixed inset-0 z-50" />`,
    ].join("\n");
    const hits = collectBackdrops(src);
    expect(hits, "줄주석·문자열 안의 `/*` 뒤 백드롭이 삼켜졌다 — 맹점 재발").toHaveLength(1);
    expect(hits[0].zs).toEqual([50]);
  });

  it("★최상위 블록 주석 안의 백드롭은 세지 않는다 — TS 파서가 지운다", () => {
    // ★내력: 2026-08-07 에 이 경계를 손수 정규식으로 닫으려다 **수백 파일의 실코드를 삼켰고**,
    //   되돌리면서 "안 고쳤다"를 단언으로 박제했다. 그 뒤 다른 세션(#584)이 같은 문제를
    //   **TS 파서(간극 주사)** 로 제대로 풀었고 여기서 그쪽에 합류해 경계가 닫혔다.
    //   손수 정규식으로 되돌리면 이 단언이 죽는다.
    expect(collectBackdrops(`const A = /* <div className="fixed inset-0 z-50" /> */ 1;`)).toHaveLength(0);
  });

  it("★파일당 여러 백드롭을 전부 수집한다(첫 건에서 멈추지 않는다)", () => {
    const hits = collectBackdrops(
      // ★스니펫도 **파스 가능해야** 한다 — 수집기가 TS 파서를 경유하므로(파스 실패는
      //   조용한 미탐 대신 시끄럽게 던진다). 실파일은 당연히 유효하다.
      `const A = <div className="fixed inset-0 z-[800]" />; const B = <div className="fixed inset-0 z-50" />;`,
    );
    expect(hits.map((h) => h.zs.flat())).toEqual([[800], [50]]);
  });
});

describe("resolveModuleSpec — 임포트 경로 해석기", () => {
  // ★왜 해석기를 따로 잠그나(독립 검증 M2): 폐포 단언은 "그 경로 형태로만 닿는 파일"이
  //   있어야 잠근다. 실측 결과 `../` 와 index 배럴로만 닿는 파일은 폐포에 **없어서**,
  //   그 두 분기는 폐포 단언으로는 원리적으로 잠기지 않는다(변이 실증: 각각 SURVIVED).
  //   목록형 1건에 기대지 말고 **분기마다** 여기서 잠근다.
  const OP = "components/orchestration/OrchestratorPanel.tsx";

  it("★`./` + .tsx — 이 PR 이 고친 바로 그 형태", () => {
    expect(resolveModuleSpec(OP, "./InputResolveModal")).toBe(
      "components/orchestration/InputResolveModal.tsx",
    );
  });

  it("★`../` — 폐포에 이 형태로만 닿는 파일이 없어 폐포 단언으로는 못 잡는다", () => {
    expect(resolveModuleSpec(OP, "../precheck/types")).toBe("components/precheck/types.ts");
  });

  it("★`.ts` 확장자 — .tsx 만 시도하면 lib/* 가 통째로 폐포에서 빠진다", () => {
    expect(resolveModuleSpec(OP, "@/lib/parcel-rows")).toBe("lib/parcel-rows.ts");
  });

  it("★index 배럴 — 실사용 1건(lib/stores)", () => {
    expect(resolveModuleSpec(OP, "@/lib/stores")).toBe("lib/stores/index.ts");
  });

  it("★저장소 밖(패키지)은 따라가지 않는다 — node_modules 로 새면 폐포가 폭발한다", () => {
    expect(resolveModuleSpec(OP, "react")).toBeNull();
    expect(resolveModuleSpec(OP, "framer-motion")).toBeNull();
  });

  it("★존재하지 않는 경로는 null — 있는 척하지 않는다", () => {
    expect(resolveModuleSpec(OP, "./NoSuchModule")).toBeNull();
  });
});

describe("importClosure — 공허진리 강제가 실제로 무는가", () => {
  // ★R2 H-C: `minFiles`·`minDepth`·`mustInclude` 세 가드를 `if (false && …)` 로 무력화해도
  //   계약 테스트가 **전부 초록**이었다. "구조적으로 강제한다"고 선언한 코드 자체가
  //   공허진리 검증을 안 받은 것이다(규율 9·16). 여기서 각각을 직접 문다.
  const SEEDS = ["components/orchestration/OrchestratorPanel.tsx"];
  const OK = { minFiles: 1, minDepth: 0, mustInclude: [] as string[] };

  it("★기준선 — 느슨한 기대값이면 통과한다(아래 세 단언이 공허하지 않음을 보인다)", () => {
    expect(importClosure(SEEDS, OK).length).toBeGreaterThan(1);
  });

  it("★minFiles 미달이면 던진다", () => {
    expect(() => importClosure(SEEDS, { ...OK, minFiles: 99999 })).toThrow(/폐포/);
  });

  it("★minDepth 미달이면 던진다", () => {
    expect(() => importClosure(SEEDS, { ...OK, minDepth: 99 })).toThrow(/최대깊이/);
  });

  it("★mustInclude 가 폐포에 없으면 던진다", () => {
    expect(() =>
      importClosure(SEEDS, { ...OK, mustInclude: ["components/does/not/Exist.tsx"] }),
    ).toThrow(/폐포에 없다/);
  });
});
