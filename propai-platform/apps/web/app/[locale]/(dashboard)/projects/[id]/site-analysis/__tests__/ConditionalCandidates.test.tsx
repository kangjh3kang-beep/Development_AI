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

import { ABSENT_SHORT } from "@/lib/withheld/absent-reasons";
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
    // ★2026-09-05 — 사유를 **항목마다** 내면서 건수(p)와 조문(li)이 형제가 됐다.
    //   계약("건수와 조문이 함께 보인다")은 그대로이므로 **블록 전체**를 본다.
    //   ★계약이 그대로인데 리팩토링이 락을 깨면 깨진 쪽은 락이다 — 락을 고친다.
    const block = screen.getByText(/판정 보류/).closest("div")!;
    expect(block.textContent).toContain("제49조");
    expect(block.textContent).toContain("판정 보류 1건");
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
 *  (`target="_blank"` 1건이 그 부류였고, 위에서 락을 추가해 죽였다).
 *
 *  ★2026-08-22 갱신 — 이 파일이 커버하는 모든 블록에 같은 정체가 적용된다(계획 한도 미확보
 *  고지 12건 중 8건 생존도 전부 `className` 과 React `key` 다). `key` 는 렌더 결과를 바꾸지
 *  않고 개발 경고만 내므로 이 스위트의 사정거리 밖이다 — **동작을 바꾸는 생존은 없다**. */
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

/**
 * ★고시 결손 고지 — 화면이 "지구단위계획 없음"을 **사실처럼** 말하던 자리.
 * 실제 사고: 오산 내삼미동은 지구단위계획구역 신규 결정고시(2025-12-23 제2025-274호)가
 * 우리 데이터에 없어 자연녹지 법정 80%가 지배 한도인 양 표시됐다.
 */
describe("고시 결손 고지", () => {
  const NOTICE = {
    reason:
      "오산시 최근 지구단위계획구역 결정고시 중 **우리 데이터에서 확인되지 않는 것**이 있습니다: " +
      "2025-12-23 경기도 오산시 고시 제2025-274호.",
    items: [{ date: "2025-12-23", gosino: "경기도 오산시 고시 제2025-274호", title: "[신규] 오산(내삼미3구역) …" }],
    window_start: "20240821",
    list_url: "https://www.eum.go.kr/web/gs/gv/gvGosiList.jsp?selSggCd=41370",
    applied: false,
  };
  const withGosi = (g: unknown) =>
    render(
      <L3EnhancedCards l3Data={{ effective_far: BASE_EFF } as never} siteAnalysis={null} gosiCoverage={g as never} />
    );

  it("★결손 고시를 지목한다", () => {
    withGosi(NOTICE);
    const box = screen.getByTestId("gosi-coverage-notice");
    expect(box.textContent).toContain("제2025-274호");
    expect(box.textContent).toContain("2025-12-23");
  });

  it("★★'틀렸다'가 아니라 '확인되지 않는다'라고 말한다 — 대조는 휴리스틱이다", () => {
    withGosi(NOTICE);
    const t = screen.getByTestId("gosi-coverage-notice").textContent ?? "";
    expect(t).toContain("확인되지 않는");
    expect(t).not.toContain("틀렸");
    expect(t).not.toContain("오류");
  });

  it("★확인 범위를 밝힌다 — 범위 밖은 확인하지 않았다고 말한다", () => {
    withGosi(NOTICE);
    const t = screen.getByTestId("gosi-coverage-notice").textContent ?? "";
    expect(t).toContain("2024-08-21 이후");
    expect(t).toContain("범위 밖은 확인하지 않았습니다");
  });

  it("★다음 행동 — 토지이음 원문 링크가 새 탭으로 열린다", () => {
    withGosi(NOTICE);
    const link = screen.getByRole("link", { name: /토지이음에서 고시 원문 확인/ });
    expect(link.getAttribute("href")).toBe(NOTICE.list_url);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("★마크다운 별표가 날것으로 노출되지 않는다", () => {
    withGosi(NOTICE);
    expect(NOTICE.reason).toContain("**");
    expect(screen.getByTestId("gosi-coverage-notice").textContent).not.toContain("**");
  });

  it("★대조군(음성) — 결손이 없으면(null) 뜨지 않는다", () => {
    withGosi(null);
    // 공허 진리 가드 — 카드 자체는 렌더됐는가.
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
    expect(screen.queryByTestId("gosi-coverage-notice")).toBeNull();
    // ★양성 짝 — 같은 실행에서 고지가 있으면 실제로 뜬다.
    withGosi(NOTICE);
    expect(screen.getAllByTestId("gosi-coverage-notice").length).toBe(1);
  });
});

/**
 * ★다중 구역(P4) — 필지는 흔히 여러 지구에 걸친다(실측: designation 8~20건).
 * 백엔드가 맞는 것을 전부 내므로 화면도 전부 보이고, **어느 것이 우선하는지 모른다**는
 * 사실을 밝혀야 한다(용도지구 경합 우선순위는 법·조례 소관이다).
 */
describe("다중 구역 겹침 표시", () => {
  const two = {
    ...BASE_EFF,
    ordinance_conditional: {
      applied: false,
      matched: [
        { kind: "bcr", value: 40, article: "제46조", matched_district: "자연취락지구", matched_option: "취락지구", overlap_count: 2 },
        { kind: "bcr", value: 60, article: "제46조", matched_district: "자연공원", matched_option: "자연공원", overlap_count: 2 },
      ],
      undecidable: [],
    },
  };

  it("★겹친 지구를 **둘 다** 각자의 값으로 보여준다", () => {
    renderWith(two);
    const lines = screen.getAllByText(/제46조/);
    const all = lines.map((l) => l.textContent ?? "").join(" | ");
    expect(all).toContain("40%");
    expect(all).toContain("60%");
    expect(all).toContain("자연취락지구");
    expect(all).toContain("자연공원");
    // ★값이 서로 달라야 이 검사가 의미 있다(같으면 하나가 없어도 통과한다).
    expect(lines.length).toBe(2);
  });

  it("★★어느 것이 우선하는지 **모른다**고 말한다", () => {
    renderWith(two);
    const all = screen.getAllByText(/제46조/).map((l) => l.textContent ?? "").join(" ");
    expect(all).toContain("2개 지구에 걸칩니다");
    expect(all).toContain("확인이 필요합니다");
    // 그리고 여전히 적용값이 아니다.
    expect(screen.getByText(/적용값이 아닙니다/)).toBeTruthy();
  });

  it("★대조군(음성) — 하나만 맞으면 겹침 문구를 만들지 않는다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 40, article: "제46조", matched_district: "자연취락지구", matched_option: "취락지구", overlap_count: 1 }],
        undecidable: [],
      },
    });
    expect(screen.getByText(/제46조/).textContent).not.toContain("걸칩니다");
    // ★양성 짝 — 같은 실행에서 겹치면 실제로 뜬다.
    renderWith(two);
    expect(screen.getAllByText(/제46조/).some((l) => (l.textContent ?? "").includes("걸칩니다"))).toBe(true);
  });

  it("overlap_count 가 없어도(구 백엔드) 깨지지 않는다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 40, article: "제46조", matched_district: "자연취락지구" }],
        undecidable: [],
      },
    });
    expect(screen.getByText(/제46조/).textContent).not.toContain("걸칩니다");
  });
});

/** ★고시 원문 수치(P5) — 후보로만 보이고, 없으면 아예 안 나온다. */
describe("고시 원문에서 읽은 수치", () => {
  const base = {
    reason: "오산시 최근 지구단위계획구역 결정고시 중 확인되지 않는 것이 있습니다.",
    items: [{ date: "2025-12-23", gosino: "제2025-274호" }],
    window_start: "20240821",
    list_url: "https://www.eum.go.kr/x",
  };
  const withG = (g: unknown) =>
    render(<L3EnhancedCards l3Data={{ effective_far: BASE_EFF } as never} siteAnalysis={null} gosiCoverage={g as never} />);

  it("★수치를 '후보'로 보여준다", () => {
    withG({ ...base, limits_note: "고시 원문에서 읽은 값(후보): 용적률 200% · 180% — 한 구역 안에서도 획지마다 값이 다릅니다. 이 부지에 어느 값이 걸리는지는 조서·도면으로 확인하십시오." });
    const t = screen.getByTestId("gosi-limits-note").textContent ?? "";
    expect(t).toContain("후보");
    expect(t).toContain("200%");
    expect(t).toContain("획지마다");
    expect(t).toContain("확인하십시오");
  });

  it("★★대조군(음성) — 수치를 못 읽었으면 그 줄이 아예 없다", () => {
    withG(base);
    // 공허 진리 가드 — 고지 자체는 떴는가.
    expect(screen.getByTestId("gosi-coverage-notice")).toBeTruthy();
    expect(screen.queryByTestId("gosi-limits-note")).toBeNull();
    // ★양성 짝 — 같은 실행에서 수치가 있으면 실제로 뜬다.
    withG({ ...base, limits_note: "고시 원문에서 읽은 값(후보): 용적률 200%" });
    expect(screen.getAllByTestId("gosi-limits-note").length).toBe(1);
  });
});

/**
 * ★★계획 한도 미확보(#705) — 세 계층 중 **가장 비싼 경고**인데 화면 소비처가 **0**이었다.
 *
 * 백엔드 주석이 직접 적어 두었다: *"수치에만 경고를 붙이면 정작 더 비싼 오답
 * (불허 용도 추천)이 그대로 나간다."* 그래서 `governs`(건폐율·용적률·**건축물 용도제한**·높이)를
 * 함께 보이고, 용도 제안까지 미검증이라고 말해야 한다.
 *
 * ★게다가 생산자(`special_districts`)가 주소 문자열 휴리스틱이라 **발화 자체가 불가능**했다
 *   (#742 에서 VWorld 실측 designation 배선으로 수정). 그래서 이 렌더는 이제야 의미가 있다.
 */
describe("계획 한도 미확보 고지", () => {
  const PLU = {
    districts: ["지구단위계획구역"],
    applied: false,
    reason: "이 필지는 계획이 건폐율·용적률**과 건축물 용도**를 직접 정하는 구역에 속하지만, 그 계획이 정한 내용을 확보하지 못했습니다.",
    governs: ["건폐율", "용적률", "건축물 용도제한", "높이"],
    requires: ["결정고시(지구단위계획 등) 본문·조서에서 상한용적률·건폐율 확인"],
  };

  it("★구역명과 '우선한다'는 사실을 말한다", () => {
    renderWith({ ...BASE_EFF, plan_limit_unknown: PLU });
    const box = screen.getByTestId("plan-limit-unknown");
    expect(box.textContent).toContain("지구단위계획구역");
    expect(box.textContent).toContain("이 계획이 아래 값보다 우선합니다");
  });

  it("★★용도까지 미검증이라고 말한다 — 이 고지의 존재 이유", () => {
    renderWith({ ...BASE_EFF, plan_limit_unknown: PLU });
    const box = screen.getByTestId("plan-limit-unknown");
    // 수치만이 아니라 **용도**가 핵심이다.
    expect(box.textContent).toContain("건축물 용도제한");
    expect(box.textContent).toContain("용도 제안은 이 계획을 반영하지 못했습니다");
    expect(box.textContent).toContain("허용용도로도 단정하지 마십시오");
  });

  it("★마크다운 별표가 날것으로 노출되지 않는다", () => {
    renderWith({ ...BASE_EFF, plan_limit_unknown: PLU });
    expect(PLU.reason).toContain("**");
    expect(screen.getByTestId("plan-limit-unknown").textContent).not.toContain("**");
  });

  it("★적용값이 아니다 — 실효값 표시는 그대로 남는다", () => {
    renderWith({ ...BASE_EFF, plan_limit_unknown: PLU });
    expect(screen.getByTestId("plan-limit-unknown")).toBeTruthy();
    // 경고가 붙어도 아래 수치는 계속 보인다(숨기면 사용자가 아무 값도 못 본다).
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
  });

  it("★대조군(음성) — 계약이 없거나 구역이 비면 뜨지 않는다", () => {
    renderWith(BASE_EFF);
    // 공허 진리 가드 — 카드 자체는 렌더됐는가.
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
    expect(screen.queryByTestId("plan-limit-unknown")).toBeNull();
    // districts 가 빈 배열이면 발화하지 않는다(백엔드가 그런 모양을 낼 수 있다).
    renderWith({ ...BASE_EFF, plan_limit_unknown: { ...PLU, districts: [] } });
    expect(screen.queryByTestId("plan-limit-unknown")).toBeNull();
    // ★양성 짝 — 같은 실행에서 구역이 있으면 실제로 뜬다.
    renderWith({ ...BASE_EFF, plan_limit_unknown: PLU });
    expect(screen.getAllByTestId("plan-limit-unknown").length).toBe(1);
  });
});

/**
 * ★★판정 보류 **사유가 항목마다 다르다** — 한 문장으로 덮으면 오역이 된다.
 *
 * 【실측 2026-09-05 · origin/main c5e7fc718】
 * `ordinance_conditional.py` 의 `undecidable[]` 은 **세 갈래**의 `why` 를 낸다:
 *   :198 강화 조항 — 상향 여지가 아님
 *   :203 건축물 용도·연혁 조건 — 설계가 정해져야 판정 가능
 *   :246 조문 나열 항목을 읽지 못함  (+ `decision_absent: SOURCE_UNAVAILABLE`)
 * 그런데 화면은 `.why` 를 **렌더 0건**(대조군: 같은 파일 `.article` 3건 · `undecidable` 5건)
 * 이었고, :203 의 축어 환언 한 문장을 **하드코딩**해 세 갈래를 전부 덮었다.
 * ⇒ :246(**우리 자료가 깨졌다**)까지 "설계가 정해져야 판정됩니다"로 번역돼,
 *    사용자는 설계를 아무리 확정해도 판정이 안 나오는 상태에서 공이 자기 쪽에 있다고 읽었다.
 *    #983(「용도지역을 모른다」→「요건 미해당」)과 **같은 클래스**다.
 *
 * 【두 모집단으로 잠근다】한쪽만 걸면 «전부 지움»도 통과한다(§D19 양방향).
 *   · SOURCE_UNAVAILABLE 갈래에 「설계」가 **없어야** 하고
 *   · 설계 갈래에는 그 문구가 **있어야** 한다 — **같은 실행에서** 대조한다.
 */
describe("판정 보류 사유는 항목마다 다르다", () => {
  const SRC_UNAVAIL = {
    kind: "far",
    article: "제52조",
    why: "조문 나열 항목을 읽지 못함 — 어느 지구·구역인지 가릴 수 없어 판정 보류",
    decision_absent: "source_unavailable",
  };
  const NEEDS_DESIGN = {
    kind: "bcr",
    article: "제53조",
    why: "건축물 용도·연혁 조건 — 설계가 정해져야 판정 가능",
  };

  function renderUndecidable(undecidable: Record<string, unknown>[]) {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: { applied: false, matched: [], undecidable },
    });
  }

  it("★★두 갈래가 **서로 다른 문구**를 낸다 — 두 모집단을 같은 실행에서 대조", () => {
    renderUndecidable([SRC_UNAVAIL, NEEDS_DESIGN]);

    // 공허 진리 가드 — 단언 **앞에** 대상 존재를 먼저 확정한다.
    expect(screen.getByText(/판정 보류 2건/)).toBeTruthy();

    const srcLine = screen.getByText(/조문 나열 항목을 읽지 못함/).closest("li");
    const designLine = screen.getByText(/설계가 정해져야 판정 가능/).closest("li");
    expect(srcLine).toBeTruthy();
    expect(designLine).toBeTruthy();
    // ★핵심 — 두 줄의 텍스트가 실제로 다르다(하드코딩 한 문장이면 같아진다).
    expect(srcLine!.textContent).not.toBe(designLine!.textContent);
  });

  it("★★자료 결함 갈래를 「설계」로 번역하지 않는다 (음성 · 블록 전수)", () => {
    renderUndecidable([SRC_UNAVAIL]);
    // 공허 진리 가드 — 단언 앞에 대상 존재를 먼저 확정한다.
    expect(screen.getByText(/조문 나열 항목을 읽지 못함/)).toBeTruthy();
    // ★★음성은 **블록 전체**를 본다 — `li` 만 보면 머리글에 옛 하드코딩 문장을 되살려도
    //   통과한다. 변이 실측 2026-09-05: `li` 판정판은 그 변이에 **SURVIVED** 였다.
    //   이 모집단에는 정당한 「설계」 갈래가 없으므로 블록 전수 단언에 위양성이 없다.
    // ★머리글을 **건수까지** 포함해 앵커한다 — `/판정 보류/` 만 쓰면 백엔드 `why` 문구가
    //   "…판정 보류" 로 끝나서 `li` 까지 매치한다(실측: 이 락이 그 위양성에 걸렸다).
    //   ★가장 자주 틀리는 상대는 코드가 아니라 **자기가 방금 쓴 픽스처**다.
    const block = screen.getByText(/판정 보류 \d+건/).closest("div")!;
    expect(block.textContent).not.toContain("설계가 정해져야");
  });

  it("★양성 짝 — 설계 갈래는 그 문구를 그대로 낸다 (없으면 «전부 지움»이 만점)", () => {
    renderUndecidable([NEEDS_DESIGN]);
    expect(screen.getByText(/판정 보류 1건/)).toBeTruthy();
    expect(screen.getByText(/설계가 정해져야 판정 가능/)).toBeTruthy();
  });

  it("★사유 **코드**도 함께 실린다 — 산문의 대체가 아니라 합성", () => {
    renderUndecidable([SRC_UNAVAIL]);
    const li = screen.getByText(/조문 나열 항목을 읽지 못함/).closest("li")!;
    // ★기대값을 **지어내지 않는다** — 거울 상수에서 파생시킨다.
    //   초판에 "자료 없음"이라고 손으로 적었다가 실제 값 "조회실패"에 걸렸다.
    //   상수에서 파생하면 문구가 바뀌어도 이 락은 계속 옳다.
    expect(li.textContent).toContain(ABSENT_SHORT.source_unavailable);
    // 그리고 산문이 사라지지 않았다(대체가 아니라 합성이다).
    expect(li.textContent).toContain("조문 나열 항목을 읽지 못함");
  });

  it("★어휘 밖 코드는 조용히 무시한다 — 그리고 산문은 남는다", () => {
    renderUndecidable([{ ...SRC_UNAVAIL, decision_absent: "존재하지_않는_코드" }]);
    const li = screen.getByText(/조문 나열 항목을 읽지 못함/).closest("li")!;
    expect(li.textContent).not.toContain("존재하지_않는_코드");
    expect(li.textContent).toContain("조문 나열 항목을 읽지 못함");
  });

  it("★대조군(음성) — undecidable 이 비면 블록이 뜨지 않는다", () => {
    renderWith({ ...BASE_EFF, ordinance_conditional: { applied: false, matched: [], undecidable: [] } });
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();   // 카드 자체는 렌더됐다
    expect(screen.queryByText(/판정 보류/)).toBeNull();
    // ★양성 짝 — 같은 실행에서 항목이 있으면 실제로 뜬다.
    renderUndecidable([NEEDS_DESIGN]);
    expect(screen.getByText(/판정 보류 1건/)).toBeTruthy();
  });

  // ★★부채 — 이 락은 **두 표본만** 태운다. 백엔드가 네 번째 `why` 갈래를 추가해도
  //   빨개지지 않는다(갈래 목록을 파생하지 않는다). 파생형으로 올리려면 파이썬 소스에서
  //   `undecidable` 버킷의 `why` 리터럴을 뽑아 각각을 렌더해야 한다.
  it.todo("★부채: why 갈래를 백엔드 소스에서 파생해 전수로 태운다");

  // ★★부채 — `ABSENT_SHORT.ambiguous` 도 문구가 **"판정보류"** 다. 이 블록의 머리글도
  //   "판정 보류 N건" 이라, 그 코드가 오면 한 화면에 **뜻이 다른 「판정보류」가 둘** 뜬다.
  //   실측(2026-09-05): 이 갈래의 생산자는 `SOURCE_UNAVAILABLE` 만 달아서 지금은 안 겹친다.
  it.todo("★부채: ambiguous 코드가 오면 「판정보류」가 두 뜻으로 겹친다 — 축 접두 필요");
});
