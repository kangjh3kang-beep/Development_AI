/**
 * adaptEvidence — 백엔드 근거 계약(evidence[] + legal_refs[])을 EvidencePanel 소비형으로 합성.
 *
 * 전역정책 Phase0(공용화)의 프론트 어댑터. 백엔드 build_evidence_block 출력
 * (evidence[{label,value,basis,legal_ref_key}] + legal_refs[{key,law_name,article,title,url,url_status}])을
 * EvidencePanel의 EvidenceItem{label,value,basis,legalRef{lawName,article,title,url}}로 변환한다.
 *
 * 정직성 가드(가짜 링크 0 — [[project_fair_price_basis]]·LegalRefChip safeHref 계약):
 *  - legal_ref_key → legal_refs 조인(키 일치). 미존재 키는 legalRef 미부착(텍스트만).
 *  - url_status === 'pending'(또는 url 빈값)이면 **url을 전달하지 않는다** → LegalRefChip이
 *    텍스트 칩으로 폴백(법령명만 표기, 죽은 링크 금지).
 *  - URL은 백엔드 레지스트리가 만든 값만 통과시킨다(프론트에서 URL 조립 절대 금지).
 *
 * 순수 함수 — 네트워크/스토어 접근 없음.
 */
import type { EvidenceItem, EvidenceLegalRef } from "@/components/common/EvidencePanel";

/** 백엔드 evidence[] 한 줄(근거 트레이스). */
export type BackendEvidence = {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  legal_ref_key?: string | null;
};

/** 백엔드 legal_refs[] 한 줄(레지스트리 get_legal_refs 출력). */
export type BackendLegalRef = {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string | null; // 'verified' | 'pending'
};

/** url_status가 verified이고 url이 있을 때만 url 전달(pending/빈값은 텍스트 폴백). */
function resolveUrl(ref: BackendLegalRef): string | null {
  const status = (ref.url_status || "").trim();
  const url = (ref.url || "").trim();
  if (!url) return null;
  // 명시적 pending이면 링크 금지. status 미지정이어도 url이 있으면 통과(verified 가정은
  // 하지 않되, 빈 url만 거른다 — 백엔드가 pending 시 url을 비워 보내기 때문).
  if (status === "pending") return null;
  return url;
}

/** legal_refs[]를 key→ref 맵으로(조인용). key 없는 항목은 제외. */
export function indexLegalRefs(
  legalRefs?: BackendLegalRef[] | null,
): Record<string, BackendLegalRef> {
  const out: Record<string, BackendLegalRef> = {};
  for (const r of legalRefs || []) {
    const k = (r?.key || "").trim();
    if (k) out[k] = r;
  }
  return out;
}

/** 단일 legal_ref → EvidenceLegalRef(LegalRefChip 호환). url은 pending 시 미전달. */
function toLegalRef(ref: BackendLegalRef | undefined): EvidenceLegalRef | null {
  if (!ref) return null;
  const lawName = (ref.law_name || "").trim();
  if (!lawName) return null; // 법령명 없으면 칩 미표시(정직성)
  return {
    lawName,
    article: (ref.article || "").trim() || null,
    title: (ref.title || "").trim() || null,
    url: resolveUrl(ref), // pending/빈값 → null → LegalRefChip 텍스트 폴백
  };
}

/**
 * 백엔드 evidence[] + legal_refs[] → EvidencePanel EvidenceItem[].
 *
 * @param evidence  백엔드 evidence 트레이스(없으면 빈 결과).
 * @param legalRefs 백엔드 legal_refs(legal_ref_key 조인용; 없어도 동작).
 */
export function adaptEvidence(
  evidence?: BackendEvidence[] | null,
  legalRefs?: BackendLegalRef[] | null,
): EvidenceItem[] {
  const refIndex = indexLegalRefs(legalRefs);
  const out: EvidenceItem[] = [];
  for (const e of evidence || []) {
    if (!e) continue;
    const label = (e.label || "").trim();
    if (!label) continue; // label 없으면 제외(EvidencePanel 빈행 방지)
    const key = (e.legal_ref_key || "").trim();
    const legalRef = key ? toLegalRef(refIndex[key]) : null;
    out.push({
      label,
      value: e.value ?? "",
      basis: (e.basis || "").trim() || null,
      legalRef,
    });
  }
  return out;
}
