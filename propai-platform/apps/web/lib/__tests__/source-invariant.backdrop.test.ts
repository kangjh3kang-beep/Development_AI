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

import { collectBackdrops } from "@/lib/source-invariant";

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

  it("★파일당 여러 백드롭을 전부 수집한다(첫 건에서 멈추지 않는다)", () => {
    const hits = collectBackdrops(
      `<div className="fixed inset-0 z-[800]" /><div className="fixed inset-0 z-50" />`,
    );
    expect(hits.map((h) => h.zs.flat())).toEqual([[800], [50]]);
  });
});
