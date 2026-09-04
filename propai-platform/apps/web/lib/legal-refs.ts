// 법령 원문 링크(legalRefs) 정규화 공용 유틸.
//
// 배경(리뷰 MEDIUM — DRY 위반): DesignWorkspace.tsx(우측 근거·한도 패널)와 MetricBar.tsx(근거
//   인스펙터)가 legalRefs(unknown[]) → LegalRefChip 입력 매핑 로직을 문자 그대로 중복 보유했다
//   (같은 계약을 두 곳에서 각자 유지 = 한쪽만 고치면 갈라지는 구조). CLAUDE.md 공용화 정책에 따라
//   이 파일로 단일화해 두 소비처가 동일 함수를 호출하게 한다(한 곳을 고치면 전역이 따라옴).
//
// 무목업: 법령명 없는 항목은 제외(빈 칩 방지·정직성). 순수 함수.

/** 법령 원문 링크 한 줄(레지스트리 legalRefs 출력) — store엔 unknown[]로 들어온다. */
export type LegalRefLike = {
  lawName?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
};

/** LegalRefChip이 바로 소비할 수 있는 정규화된 형태. */
export type LegalRefChipInput = {
  lawName: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
};

/**
 * legalRefs(unknown[]) → LegalRefChip 입력 배열. 법령명 없는 항목은 제외(빈 칩 방지·정직성).
 *   백엔드 키가 camel(lawName) 또는 snake(law_name) 둘 다 올 수 있어 양쪽 폴백.
 */
export function toLegalChips(refs?: unknown[] | null): LegalRefChipInput[] {
  if (!Array.isArray(refs)) return [];
  return refs
    .filter((r): r is LegalRefLike => !!r && typeof r === "object")
    .map((r) => ({
      lawName: (r.lawName || r.law_name || "").trim(),
      article: r.article ?? null,
      title: r.title ?? null,
      url: r.url ?? null,
    }))
    .filter((r) => !!r.lawName);
}
