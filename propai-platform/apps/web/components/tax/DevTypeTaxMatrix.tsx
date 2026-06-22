"use client";

import { Fragment, useEffect, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { PROGRESSIVE_BRACKETS, ACQ_TAX_BRACKETS } from "@/lib/kr-tax-calculator";

type MatrixEntry = {
  development_type: string;
  applicable_codes: string[];
  count: number;
};

const MODULE_LABELS: Record<string, string> = {
  M01: "재개발", M02: "재건축", M03: "역세권", M04: "주택조합",
  M05: "임대협동", M06: "일반분양", M07: "주상복합", M08: "오피스텔",
  M09: "지산센터", M10: "단독주택", M11: "전원주택", M12: "타운하우스",
  M13: "도시형", M14: "공공임대", M15: "민간리츠",
};

// ── 세금코드 한글명 (배지·헤더 표기용) ──
const TAX_CODE_LABELS: Record<string, string> = {
  ACQ: "취득세",
  REG: "등록면허세",
  VAT: "부가가치세",
  PROP: "재산세",
  CGT: "양도소득세",
  COMP: "종합부동산세",
};

// ── 세금코드별 근거(산식·법령·세율) 정의 ──
// 가짜값 금지: 세율구간은 kr-tax-calculator의 export 상수(PROGRESSIVE_BRACKETS·ACQ_TAX_BRACKETS)에서만 인용.
//             법령명은 검증된 텍스트만 표기하고 URL은 조립하지 않는다(LegalRefChip이 url 없으면 텍스트 폴백).
type TaxCodeEvidence = {
  /** 산출 산식 한 줄 (예: "과세표준 × 세율 − 누진공제"). */
  formula: string;
  /** 적용 세율구간 요약 — 실제 상수에서 파생(가짜값 0). */
  rateNote: string;
  /** 검증된 법령명(텍스트). 미검증·해당없음이면 null로 정직 미표시. */
  lawName: string | null;
  /** 조문(있으면). 없으면 법령명만 칩에 표기. */
  article?: string | null;
  /** 조문 제목(부연). */
  lawTitle?: string | null;
  /** 다주택 중과 적용 여부(배지 표시 트리거). */
  multiHome?: boolean;
};

// 양도소득세 누진세율 구간을 사람이 읽는 한 줄로 — PROGRESSIVE_BRACKETS 실값에서 생성.
// (예: "6%~45% 8단계 누진 (1,400만 이하 6% … 10억 초과 45%)")
function buildProgressiveRateNote(): string {
  const first = PROGRESSIVE_BRACKETS[0];
  const last = PROGRESSIVE_BRACKETS[PROGRESSIVE_BRACKETS.length - 1];
  const minPct = Math.round(first.rate * 100);
  const maxPct = Math.round(last.rate * 100);
  const firstLimitMan = Math.round(first.limit / 10_000); // 원→만원
  return `${minPct}%~${maxPct}% ${PROGRESSIVE_BRACKETS.length}단계 누진 (과표 ${firstLimitMan.toLocaleString()}만원 이하 ${minPct}% … 최고 ${maxPct}%)`;
}

// 취득세(주택) 세율구간을 한 줄로 — ACQ_TAX_BRACKETS 실값에서 생성.
// (예: "6억 이하 1% / 9억 이하 2% / 초과 3%")
function buildAcqRateNote(): string {
  return ACQ_TAX_BRACKETS
    .map((b) => {
      const pct = Math.round(b.rate * 100);
      if (b.limit === Infinity) return `초과 ${pct}%`;
      const eokLimit = Math.round(b.limit / 100_000_000); // 원→억원
      return `${eokLimit}억 이하 ${pct}%`;
    })
    .join(" / ");
}

// 세금코드 → 근거 매핑. 세율 텍스트는 위 빌더(실상수 파생)로 채워 가짜값을 차단.
const TAX_CODE_EVIDENCE: Record<string, TaxCodeEvidence> = {
  ACQ: {
    formula: "취득세 = 취득가 × 세율 (+ 농특세 10% + 교육세 10%)",
    rateNote: buildAcqRateNote(),
    lawName: "지방세법",
    article: "제11조",
    lawTitle: "부동산 취득의 세율",
    multiHome: true, // 2주택 8% / 3주택+ 12% 중과 (calculateAcquisitionTax 로직)
  },
  REG: {
    formula: "등록면허세 = 등기·등록 대상금액 × 세율",
    rateNote: "등기 유형별 세율 (소유권보존 등 행위별)",
    lawName: "지방세법",
    article: "제28조",
    lawTitle: "등록면허세 세율",
  },
  VAT: {
    formula: "부가가치세 = 공급가액(건물분) × 10% (토지분 면세)",
    rateNote: "10% (건물 공급가액분, 토지·국민주택규모 이하는 면세)",
    lawName: "부가가치세법",
    article: "제30조",
    lawTitle: "세율",
  },
  PROP: {
    formula: "재산세 = 과세표준(공시가 × 공정시장가액비율 60%) × 누진세율",
    rateNote: "0.1%~0.4% 누진 (과표 6천만 이하 0.1% … 3억 초과 0.4%)",
    lawName: "지방세법",
    article: "제111조",
    lawTitle: "재산세 세율",
  },
  CGT: {
    formula: "양도소득세 = 과세표준 × 세율 − 누진공제 (다주택 시 +중과세율)",
    rateNote: buildProgressiveRateNote(),
    lawName: "소득세법",
    article: "제104조",
    lawTitle: "양도소득세의 세율",
    multiHome: true, // 2주택 +20%p / 3주택+ +30%p 중과 (calculateCapitalGainsTax 로직)
  },
  COMP: {
    formula: "종합부동산세 = (공시가 − 공제기준) × 공정시장가액비율 60% × 누진세율",
    rateNote: "0.6%~2.2% 누진 (1주택 공제 11억 / 다주택 6억 초과분)",
    lawName: "종합부동산세법",
    article: "제9조",
    lawTitle: "세율 및 세액",
  },
};

// 다주택 중과세율 추가분 — calculateCapitalGainsTax/계산기 로직과 동일한 정책상수.
// (가짜값 아님: 코드의 if(houseCount===2)→20% / >=3→30% 분기와 일치)
const CGT_SURCHARGE_2HOME = 20; // %p
const CGT_SURCHARGE_3HOME = 30; // %p

export function DevTypeTaxMatrix() {
  const [matrix, setMatrix] = useState<MatrixEntry[]>([]);
  // 행별 '근거 보기' 펼침 토글 (개발유형 코드 → 열림 여부).
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const localMatrix: MatrixEntry[] = [
      { development_type: "M01", applicable_codes: ["ACQ", "REG", "VAT"], count: 3 },
      { development_type: "M02", applicable_codes: ["ACQ", "REG", "PROP", "CGT"], count: 4 },
      { development_type: "M03", applicable_codes: ["ACQ", "REG"], count: 2 },
      { development_type: "M06", applicable_codes: ["ACQ", "REG", "PROP", "CGT", "COMP"], count: 5 },
      { development_type: "M07", applicable_codes: ["ACQ", "REG", "PROP", "CGT"], count: 4 },
      { development_type: "M08", applicable_codes: ["ACQ", "REG", "PROP"], count: 3 },
    ];
    setMatrix(localMatrix);
  }, []);

  const toggleRow = (code: string) =>
    setExpanded((prev) => ({ ...prev, [code]: !prev[code] }));

  // 한 개발유형의 적용 세금코드들 → EvidencePanel 항목으로 변환.
  // 미정의 코드(근거 없음)는 정직하게 건너뛴다(가짜 근거 금지).
  const buildEvidenceItems = (codes: string[]): EvidenceItem[] =>
    codes
      .map((code) => {
        const ev = TAX_CODE_EVIDENCE[code];
        if (!ev) return null;
        const label = `${TAX_CODE_LABELS[code] ?? code} (${code})`;
        return {
          label,
          value: ev.formula,
          basis: ev.rateNote,
          // 법령 검증 텍스트만 — url 미전달 → LegalRefChip이 텍스트 칩으로 폴백(가짜 링크 0).
          legalRef: ev.lawName
            ? { lawName: ev.lawName, article: ev.article, title: ev.lawTitle }
            : null,
        } as EvidenceItem;
      })
      .filter((x): x is EvidenceItem => x !== null);

  if (matrix.length === 0) {
    return (
      <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <CardContent className="p-6 text-center text-sm text-slate-500">
          매트릭스 데이터를 불러오는 중...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-6">
        <h4 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
          개발유형별 세금 매트릭스
        </h4>
        <p className="mb-4 text-[11px] text-slate-400">
          각 행의 &lsquo;근거 보기&rsquo;에서 세금코드별 산식·세율구간·근거 법령을 확인하세요.
          세율은 계산기 상수(지방세법·소득세법 기준)에서 인용합니다.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700">
                <th className="px-3 py-2 text-left font-medium text-slate-500">유형</th>
                <th className="px-3 py-2 text-left font-medium text-slate-500">명칭</th>
                <th className="px-3 py-2 text-center font-medium text-slate-500">세금 수</th>
                <th className="px-3 py-2 text-left font-medium text-slate-500">적용 코드</th>
                <th className="px-3 py-2 text-center font-medium text-slate-500">근거</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((entry) => {
                // 이 개발유형에 다주택 중과 대상 세금(취득세·양도세)이 포함되는지.
                const hasMultiHome = entry.applicable_codes.some(
                  (c) => TAX_CODE_EVIDENCE[c]?.multiHome,
                );
                const isOpen = expanded[entry.development_type] ?? false;
                const evidenceItems = buildEvidenceItems(entry.applicable_codes);
                return (
                  <Fragment key={entry.development_type}>
                    <tr className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">
                        {entry.development_type}
                      </td>
                      <td className="px-3 py-2 text-slate-900 dark:text-slate-100">
                        <span className="inline-flex items-center gap-1.5">
                          {MODULE_LABELS[entry.development_type] ?? entry.development_type}
                          {/* 다주택 중과 배지 — 취득세/양도세 중과가 걸리는 유형에 표시 */}
                          {hasMultiHome && (
                            <span
                              title={`다주택 중과: 취득세 2주택 8%/3주택+ 12%, 양도세 2주택 +${CGT_SURCHARGE_2HOME}%p/3주택+ +${CGT_SURCHARGE_3HOME}%p`}
                              className="inline-flex items-center rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300"
                            >
                              다주택 중과
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center font-medium">{entry.count}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {entry.applicable_codes.slice(0, 10).map((code) => (
                            <span
                              key={code}
                              title={TAX_CODE_LABELS[code] ?? code}
                              className="inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                            >
                              {code}
                            </span>
                          ))}
                          {entry.applicable_codes?.length > 10 && (
                            <span className="text-xs text-slate-400">
                              +{entry.applicable_codes.length - 10}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-center">
                        {evidenceItems.length > 0 ? (
                          <button
                            type="button"
                            onClick={() => toggleRow(entry.development_type)}
                            aria-expanded={isOpen}
                            className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline"
                          >
                            {isOpen ? "접기" : "근거 보기"}
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                    {isOpen && evidenceItems.length > 0 && (
                      <tr className="border-b border-slate-100 dark:border-slate-800">
                        <td colSpan={5} className="px-3 pb-3">
                          <EvidencePanel
                            title={`${MODULE_LABELS[entry.development_type] ?? entry.development_type} 세금 산출 근거`}
                            items={evidenceItems}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
