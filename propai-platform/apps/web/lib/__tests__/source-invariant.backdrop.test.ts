/**
 * `collectBackdrops` 파서 단위 잠금.
 *
 * ★왜 픽스처로 잠그나(정직): 이 파서를 만든 이유인 **비리터럴 className 백드롭**은
 *   2026-08-07 실측 기준 지도 공존 폐포에 **0건**, 저장소 전체에 1건(그마저 계약 준수)이다.
 *   즉 저장소를 스캔하는 계약 테스트만으로는 "삼항·cn()·템플릿을 본다"는 이 파서의 능력이
 *   **아무것도 증명되지 않는다**(대상이 없으니 늘 초록 = 공허 진리). 그래서 능력 자체는
 *   여기서 **입력을 만들어** 검증한다 — 미래에 그런 백드롭이 생겼을 때 감시망이 실제로
 *   작동함을 지금 보장하는 유일한 방법이다.
 * ★대칭으로 **위양성**도 잠근다 — 배경 장식(`pointer-events-none … -z-10`)을 위반으로
 *   신고하면 정상 코드를 막는다(이 저장소가 두 번 데인 가드 위양성).
 */
import { describe, expect, it } from "vitest";

import { collectBackdrops, resolveModuleSpec } from "@/lib/source-invariant";

describe("collectBackdrops — 백드롭 className 파서", () => {
  it("★리터럴 백드롭에서 z 를 읽는다", () => {
    const hits = collectBackdrops(`<div className="fixed inset-0 z-[800] bg-black/60" />`);
    expect(hits).toHaveLength(1);
    expect(hits[0].literal).toBe(true);
    expect(hits[0].zs).toEqual([800]);
  });

  it("★`z-50`(대괄호 없는 표기)도 같은 값으로 읽는다", () => {
    expect(collectBackdrops(`<div className="fixed inset-0 z-50 p-4" />`)[0].zs).toEqual([50]);
  });

  it("★cn() 로 조립한 백드롭을 본다 — 종전 정규식이 통째로 놓치던 형태", () => {
    const hits = collectBackdrops(
      `<div className={cn("fixed inset-0", "z-[800]", open && "opacity-100")} />`,
    );
    expect(hits, "cn() 백드롭을 수집하지 못했다").toHaveLength(1);
    expect(hits[0].literal).toBe(false);
    expect(hits[0].zs).toEqual([800]);
  });

  it("★삼항으로 z 가 갈리면 **양쪽 다** 읽는다 — 한쪽만 보면 낮은 갈래가 숨는다", () => {
    const hits = collectBackdrops(
      `<div className={\`fixed inset-0 \${big ? "z-[800]" : "z-50"}\`} />`,
    );
    expect(hits).toHaveLength(1);
    expect(hits[0].zs.sort((a, b) => a - b)).toEqual([50, 800]);
  });

  it("★클래스가 표현식 안에서 쪼개져 있어도(fixed 와 inset-0 이 다른 인자) 백드롭으로 본다", () => {
    const hits = collectBackdrops(`<div className={cn("fixed", "inset-0", "z-[800]")} />`);
    expect(hits).toHaveLength(1);
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

  it("★중괄호 균형으로 끝을 찾는다 — 표현식 뒤 다른 속성을 삼키지 않는다", () => {
    const hits = collectBackdrops(
      `<div className={cn({ "fixed inset-0 z-[800]": open })} data-x="z-50 fixed inset-0" />`,
    );
    // className 표현식 1건만 수집되고, data-x 는 className 이 아니므로 대상 밖이다.
    expect(hits).toHaveLength(1);
    expect(hits[0].zs).toEqual([800]);
  });

  it("★문자열 안의 중괄호를 세지 않는다 — 안 그러면 표현식이 **일찍 끊겨** 뒤쪽 z 를 잃는다", () => {
    // ★이 케이스가 없으면 중괄호 균형의 **따옴표 추적**이 무잠금이다(변이검증이 적발:
    //   `if (quote)` 무력화·그 안의 `continue` 삭제가 **둘 다 생존**했다). 문자열 안에 `}` 가
    //   있으면 추적 없이는 거기서 depth 가 0 이 되어 표현식이 잘리고, 뒤에 오는 낮은 z 갈래가
    //   통째로 안 보인다 — 즉 "삼항으로 낮은 z 를 숨기는" 형태와 정확히 같은 결과가 된다.
    const hits = collectBackdrops(
      `<div className={cn("fixed inset-0 after:content-['}']", big ? "z-[800]" : "z-50")} />`,
    );
    expect(hits).toHaveLength(1);
    expect(hits[0].zs.sort((a, b) => a - b)).toEqual([50, 800]);
  });

  it("★위양성 금지 — 삼항의 **비백드롭 갈래** z 를 위반으로 신고하지 않는다", () => {
    // ★독립 검증 H4 실증: 갈래를 합치면 `hidden z-10`(백드롭 아님)의 z-10 이 백드롭 위반이 된다.
    //   실물 근접 사례가 CadBimIntegrationPanel 의 전체화면 삼항이다 — 비전체화면 갈래에
    //   평범한 z-10 하나만 붙어도 정상 코드가 CI 를 깨뜨린다.
    const hits = collectBackdrops(
      `<div className={cn(open ? "fixed inset-0 z-[800]" : "hidden z-10")} />`,
    );
    expect(hits).toHaveLength(1);
    expect(hits[0].zs, "백드롭이 아닌 갈래의 z 까지 끌어왔다").toEqual([800]);
  });

  it("★변이 prefix 가 붙은 z 도 읽는다 — `md:z-50` 으로 계약을 빠져나가지 못하게", () => {
    // 종전 정규식은 `md:`·`dark:`·`group-hover:` 앞에서 끊겨, "준수처럼 보이면서 특정
    // 브레이크포인트에서만 z-50 으로 떨어지는" 백드롭이 통과했다(독립 검증 M1).
    const hits = collectBackdrops(`<div className="fixed inset-0 z-[800] md:z-50" />`);
    expect(hits[0].zs.sort((a, b) => a - b)).toEqual([50, 800]);
  });

  it("★판정불가 — 변수로 조립한 z 는 위반이 아니다(resolvable=false)", () => {
    const [hit] = collectBackdrops(`<div className={\`fixed inset-0 \${Z_BACKDROP}\`} />`);
    expect(hit.zs).toEqual([]);
    expect(hit.resolvable, "변수 z 를 '위반'으로 신고하면 정상 코드를 막는다").toBe(false);
  });

  it("★판정불가 — 같은 요소의 인라인 style zIndex(이 저장소의 실제 관용)", () => {
    // SATONG_UI_Z 는 `style={{ zIndex: … }}` 로 흘리는 것이 이 저장소의 SSOT 규칙이다.
    const [hit] = collectBackdrops(
      `<div className="fixed inset-0" style={{ zIndex: SATONG_CONTENT_Z.appModal }} />`,
    );
    expect(hit.zs).toEqual([]);
    expect(hit.resolvable).toBe(false);
  });

  it("★그래도 리터럴이고 z 도 style 도 없으면 판정 가능 — 위반으로 남는다", () => {
    const [hit] = collectBackdrops(`<div className="fixed inset-0 bg-black/60" />`);
    expect(hit.resolvable, "판정불가를 남발하면 진짜 누락이 숨는다").toBe(true);
  });

  it("★최상위 블록 주석 안의 백드롭도 세지 않는다", () => {
    // 독립 검증 L1: JSX 주석·줄 주석만 벗기고 `/* … */` 는 그대로 집계했다(위양성 방향).
    expect(collectBackdrops(`/* <div className="fixed inset-0 z-50" /> */`)).toHaveLength(0);
  });

  it("★파일당 여러 백드롭을 전부 수집한다(첫 건에서 멈추지 않는다)", () => {
    const hits = collectBackdrops(
      `<div className="fixed inset-0 z-[800]" /><div className="fixed inset-0 z-50" />`,
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
