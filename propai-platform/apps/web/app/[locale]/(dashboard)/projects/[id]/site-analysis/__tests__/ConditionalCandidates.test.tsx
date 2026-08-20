/**
 * 실효용적률 카드 — **조건부 완화 후보를 보이되 적용값으로 읽히지 않게**.
 *
 * 【배경】조례는 `용도지역 → 값 하나`가 아니라 **`용도지역 × 조건 → 값들`**이다
 * (오산시 자연녹지 = 6개 조). 백엔드가 `ordinance_conditional`(조례 조건부 매칭)과
 * `conditional_ceiling`(법 §75의3 조건부 법정상한)을 내지만, **화면이 읽지 않으면
 * 고친 것이 아니다** — 이 캠페인이 내내 고쳐 온 "정의만 하고 소비처 0"이 된다.
 *
 * 【이 파일이 잠그는 것 — 양쪽 다】
 * · 값이 **보인다**(숨기면 사용자가 완화 여지를 영영 모른다)
 * · 그런데 **적용값으로 읽히지 않는다**(적용값처럼 보이면 근거 없는 단정이 된다)
 * · 조건이 안 맞으면 **뜨지 않는다**(가드의 위양성 방지)
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { L3EnhancedCards } from "@/app/[locale]/(dashboard)/projects/[id]/site-analysis/page";

const BASE_EFF = {
  effective_far_pct: 100,
  effective_bcr_pct: 20,
  ordinance_confirmed: true,
  legal_min_far_pct: 50,
  legal_max_far_pct: 100,
};

function renderWith(effective_far: Record<string, unknown>) {
  render(
    <L3EnhancedCards
      l3Data={{ effective_far } as never}
      siteAnalysis={null}
    />
  );
}

describe("조건부 완화 후보 표시", () => {
  it("★조례 조건부 매칭이 조문·수치와 함께 보인다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 30, article: "제50조", article_title: "성장관리방안 수립지역에서의 건폐율 완화", condition_key: "growth_management_plan" }],
        undecidable: [],
      },
    });
    const line = screen.getByText(/제50조/);
    expect(line.textContent).toContain("건폐율");
    expect(line.textContent).toContain("30%");
  });

  it("★★적용값으로 읽히지 않는다 — '적용값이 아닙니다'가 함께 나온다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 30, article: "제50조", article_title: "성장관리방안" }],
        undecidable: [],
      },
    });
    expect(screen.getByText(/적용값이 아닙니다/)).toBeTruthy();
    // 그리고 최종 실효값은 여전히 조례·법정 기준값이다(후보가 승격되지 않았다).
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
  });

  it("법 §75의3 조건부 법정상한 고지도 보인다", () => {
    renderWith({
      ...BASE_EFF,
      conditional_ceiling: {
        applied: false,
        bcr_ceiling_pct: 30,
        note: "성장관리계획구역이라 자연녹지지역의 법정 건폐율 상한이 30% 까지 열릴 수 있습니다",
      },
    });
    expect(screen.getByText(/열릴 수 있습니다/)).toBeTruthy();
  });

  it("판정 보류 건수를 정직하게 말한다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [],
        undecidable: [{ article: "제49조", why: "설계가 정해져야 판정 가능" }],
      },
    });
    const note = screen.getByText(/판정 보류/);
    expect(note.textContent).toContain("제49조");
  });

  it("★대조군(음성) — 조건부가 없으면 블록이 뜨지 않는다(가드 위양성 방지)", () => {
    renderWith(BASE_EFF);
    // 공허 진리 가드 — 카드 자체는 렌더됐는가.
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
    expect(screen.queryByText(/적용값이 아닙니다/)).toBeNull();
  });
});

/**
 * ★조례 수치 미확보의 **사유** — 값이 아니라 사유를 낸다(#718 프론트 착지).
 *
 * 【배경】울산·창원 도시계획 조례는 건폐율·용적률 별표를 **HWP 첨부로만** 제공한다.
 * 백엔드는 그 사유·원문 링크를 만들었지만 **화면 계약에 키가 없어 소비처가 0**이었다
 * (2026-08-21 라이브 실측: 두 지자체 응답에 사유는 있고 화면엔 없다).
 * 그래서 화면은 "조례 확인 필요"라고만 말했고, 사용자는 *조례가 없거나 용도지역이 틀렸다*고
 * 의심하게 된다 — **틀린 사유는 틀린 처방을 부른다**.
 */
/* ★변이감사 잔존 생존군의 정체(2026-08-21 · 17건 중 13→12건) — 점수 부풀리기 방지를 위해 적는다.
 *  전부 **`className` 문자열과 주석**이다. 변이도구는 *따옴표 문자열*을 바꾸는데, JSX 텍스트는
 *  문자열 리터럴이 아니라 이 줄들에서 실제로 바뀌는 건 Tailwind 클래스뿐이다
 *  (반증: 그 줄들의 JSX 텍스트는 아래 단언들이 이미 잠그고 있어, 텍스트가 바뀌었다면 죽었어야 한다).
 *  스타일 회귀는 이 스위트의 사정거리 밖이다 — **동작을 바꾸는 생존은 남기지 않았다**
 *  (`target="_blank"` 1건이 그 부류였고, 위에서 락을 추가해 죽였다). */
describe("조례 수치 미확보 사유(별표 HWP 첨부)", () => {
  const ATTACH = {
    reason:
      "울산광역시 도시계획 조례는 건폐율·용적률 표를 **별표 첨부파일(HWP)** 로만 제공해 " +
      "본문에서 수치를 읽을 수 없습니다(조례가 없거나 용도지역이 빠진 것이 아닙니다).",
    attachment_url: "http://www.law.go.kr/flDownload.do?gubun=ELIS&flSeq=163373187",
    ordinance_name: "울산광역시 도시계획 조례",
    requires: ["별표 원문(HWP) 열람으로 해당 용도지역 건폐율·용적률 확인"],
  };

  it("★사유가 보인다 — 백엔드가 만든 것이 화면에 닿는다", () => {
    renderWith({ ...BASE_EFF, ordinance_confirmed: false, ordinance_attachment_only: ATTACH });
    const box = screen.getByTestId("ordinance-attachment-only");
    expect(box.textContent).toContain("별표가 첨부파일(HWP)입니다");
    // ★사유의 후반절 — 무엇을 의심하면 **안 되는지**가 이 고지의 핵심이다.
    expect(box.textContent).toContain("조례가 없거나 용도지역이 빠진 것이 아닙니다");
  });

  it("★마크다운 별표(**)가 날것으로 노출되지 않는다", () => {
    renderWith({ ...BASE_EFF, ordinance_confirmed: false, ordinance_attachment_only: ATTACH });
    const box = screen.getByTestId("ordinance-attachment-only");
    // 공허 진리 가드 — 원문에 정말 `**` 가 있었는가(없으면 이 단언은 무의미).
    expect(ATTACH.reason).toContain("**");
    expect(box.textContent).not.toContain("**");
  });

  it("★다음 행동을 준다 — 별표 원문 링크가 실제 href 로 걸린다", () => {
    renderWith({ ...BASE_EFF, ordinance_confirmed: false, ordinance_attachment_only: ATTACH });
    const link = screen.getByRole("link", { name: /별표 원문 열기/ });
    expect(link.getAttribute("href")).toBe(ATTACH.attachment_url);
    // ★변이감사(2026-08-21)가 잡았다: `rel` 만 잠갔더니 `target="_blank"` 삭제가 **생존**했다.
    //   target 이 빠지면 원문이 **같은 탭에서 열려 분석 화면이 날아간다** — 스타일이 아니라
    //   동작이다. `rel` 은 그 target 의 보안 짝이라 **한 쌍으로** 잠근다.
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("★무엇을 의심하면 안 되는지 말한다 — 이 고지의 존재 이유", () => {
    renderWith({ ...BASE_EFF, ordinance_confirmed: false, ordinance_attachment_only: ATTACH });
    const box = screen.getByTestId("ordinance-attachment-only");
    // 최종값이 법정상한인 **이유**를 화면이 직접 잇는다. 이 문장이 없으면 사용자는
    // "조례가 없다"·"용도지역이 틀렸다"로 오진한다(#718 이 백엔드에서 고친 바로 그 결함).
    expect(box.textContent).toContain("최종값이 법정상한인 것은");
    expect(box.textContent).toContain("조례가 없거나 용도지역이 틀린 것이 아닙니다");
  });

  it("★★후보값으로 읽히지 않는다 — '적용값이 아닙니다' 박스와 분리된다", () => {
    renderWith({ ...BASE_EFF, ordinance_confirmed: false, ordinance_attachment_only: ATTACH });
    // 조건부 후보가 **없는데도** 사유는 떠야 한다(두 블록이 서로 다른 게이트다).
    expect(screen.queryByText(/적용값이 아닙니다/)).toBeNull();
    expect(screen.getByTestId("ordinance-attachment-only")).toBeTruthy();
  });

  it("★대조군(음성) — 정상 조례에서는 뜨지 않는다(위양성 방지)", () => {
    renderWith(BASE_EFF);
    // 공허 진리 가드 — 카드 자체는 렌더됐는가(0건이 '조회 실패'가 아님을 보인다).
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
    // ★양성 짝 — **같은 실행에서** 반대 결과가 나올 수 있음을 함께 단언한다.
    //   이게 없으면 렌더가 통째로 고장 나도 이 부재 단언은 초록이다.
    expect(screen.queryByTestId("ordinance-attachment-only")).toBeNull();
    renderWith({ ...BASE_EFF, ordinance_attachment_only: ATTACH });
    expect(screen.getAllByTestId("ordinance-attachment-only").length).toBe(1);
  });
});

/**
 * ★나열형 조문(제46조 '그 밖에 용도지구·구역 등')은 **항목마다 값이 다르다**
 * (오산 실측: 취락 40 · 개발진흥 30 · 수산자원 30 · 자연공원 60 · 산업단지 80).
 * 그래서 화면은 **어느 지정으로 매칭됐는지** 밝혀야 한다 — 안 밝히면 사용자가
 * 왜 이 수치인지 확인할 길이 없다.
 */
describe("나열형 조건 — 매칭 근거 지구 표시", () => {
  const base = (extra: Record<string, unknown>) => ({
    ...BASE_EFF,
    ordinance_conditional: {
      applied: false,
      matched: [{
        kind: "bcr", value: 40, article: "제46조",
        article_title: "그 밖에 용도지구·구역 등의 건폐율", ...extra,
      }],
      undecidable: [],
    },
  });

  it("★근거가 된 부지 지정명이 보인다", () => {
    renderWith(base({ matched_district: "자연취락지구", matched_option: "취락지구" }));
    const line = screen.getByText(/제46조/);
    expect(line.textContent).toContain("자연취락지구");
    expect(line.textContent).toContain("40%");
  });

  it("★조례 항목명이 부지 지정명과 다르면 함께 밝힌다(상위 범주 ↔ 하위 유형)", () => {
    renderWith(base({ matched_district: "자연취락지구", matched_option: "취락지구" }));
    // 조례는 '취락지구'라 적었고 부지는 '자연취락지구'다 — 둘 다 보여야 대조가 된다.
    expect(screen.getByText(/제46조/).textContent).toContain("취락지구' 항목");
  });

  it("이름이 같으면 괄호를 중복해 붙이지 않는다", () => {
    renderWith(base({ matched_district: "자연공원", matched_option: "자연공원", value: 60 }));
    const t = screen.getByText(/제46조/).textContent ?? "";
    expect(t).toContain("자연공원");
    expect(t).not.toContain("'자연공원' 항목");
  });

  it("★대조군(음성) — 근거 지구가 없으면 그 문구를 만들지 않는다", () => {
    renderWith(base({}));
    const t = screen.getByText(/제46조/).textContent ?? "";
    // ★양성 짝 — 같은 실행에서 근거가 있으면 실제로 나온다(렌더가 죽은 게 아니다).
    expect(t).not.toContain("근거: 이 부지가");
    renderWith(base({ matched_district: "자연공원" }));
    expect(screen.getAllByText(/제46조/).some((e) => (e.textContent ?? "").includes("근거: 이 부지가"))).toBe(true);
  });
});
