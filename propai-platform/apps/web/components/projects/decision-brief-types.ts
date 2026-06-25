/**
 * Stage1 통합 의사결정 브리프(Decision Brief) — 백엔드 표준 요약 계약의 TypeScript 타입.
 *
 * ★Pydantic↔TS 1:1 정합: 이 타입은 백엔드 DecisionBriefService.build()가 반환하는 dict
 *   (apps/api/app/services/land_intelligence/decision_brief_service.py)와 키가 정확히 일치한다.
 *   (POST /api/v1/projects/{id}/decision-brief 응답 본문 — 배포 환경에서 동작, 샌드박스는 deploy-pending.)
 *
 * 한 곳(이 파일)에만 계약을 두고 패널·카드·테스트가 공유해 키 드리프트를 막는다.
 */

/** part 식별자 — 백엔드 PART_* 상수와 1:1(부지/시장·법규·인허가Top3). */
export type DecisionBriefPartId = "site_market" | "regulation" | "permit_design";

/** 신뢰도 라벨 — 백엔드 confidence(high/medium/low)와 1:1. */
export type DecisionConfidence = "high" | "medium" | "low";

/** part 상태 — 'ok'면 실데이터, 'unavailable'이면 정직 미확보(사유 동반). */
export type DecisionPartStatus = "ok" | "unavailable";

/** 종합 판정 결정 — 백엔드 verdict.decision과 1:1. */
export type DecisionVerdictDecision = "GO" | "CONDITIONAL" | "HOLD";

/**
 * key_metric의 안정 식별자 — 라벨(표시 전용)이 바뀌어도 소비처(findMetric)가 silent-null
 * 나지 않게 하는 SSOT 키. 백엔드 decision_brief_service.py의 key_metrics 'key'와 1:1.
 * 옵셔널(하위호환) — 구 응답(key 없음)은 label 폴백으로 동작(무회귀).
 */
export type DecisionMetricKey =
  // 부지·시장 part
  | "zone"
  | "land_area"
  | "effective_far"
  | "effective_bcr"
  | "gfa"
  | "presale_price"
  | "parcel_count"
  // 법규 part
  | "far_trio"
  | "bcr_trio"
  | "district_count"
  | "high_impact"
  // 인허가·Top3 part
  | "top1_model"
  | "roi"
  | "net_profit"
  | "grade"
  | "types_analyzed"
  | "effective_far_top3";

/** key_metrics 한 항목 — {key?, label, value, unit}. value는 문자열/숫자/null 모두 허용(미확보=null). */
export interface DecisionKeyMetric {
  /** 안정 식별자(라벨 변경 silent-null 차단). 백엔드 key_metrics 'key'와 1:1. 구 응답은 미정의. */
  key?: DecisionMetricKey | string;
  label: string;
  value: string | number | null;
  unit?: string;
}

/** 근거 한 항목 — 백엔드 evidence[{label, value, basis?}]. */
export interface DecisionEvidenceItem {
  label: string;
  value?: string | number | null;
  basis?: string | null;
}

/** 법령 링크 한 항목 — 백엔드 legal_links[{label, url}]. url 없으면 텍스트만(죽은링크 금지). */
export interface DecisionLegalLink {
  label: string;
  url?: string | null;
}

/** 도메인 part(표준 요약 계약) — 3개 통합 도메인(부지·시장 통합/법규/인허가·Top3) 동일 형태. */
export interface DecisionBriefPart {
  part: DecisionBriefPartId | string;
  title: string;
  summary_oneliner: string;
  key_metrics: DecisionKeyMetric[];
  evidence: DecisionEvidenceItem[];
  legal_links: DecisionLegalLink[];
  confidence: DecisionConfidence;
  detail_route: string;
  status: DecisionPartStatus;
  /** unavailable일 때 정직 사유(가짜 금지). */
  reason?: string;
  /** 인허가 part 전용 — 잠정 시나리오 신호(선행절차 전제). */
  scenario_status?: "actual" | "tentative" | string | null;
  /** 인허가 part 전용 — 정직 고지(예: site_id 미확보). */
  honest_disclosure?: string | null;
}

/** 디벨로퍼 Go/No-Go 패스스루 — 백엔드 verdict.go_nogo(inner value dict + status). */
export interface DecisionGoNoGo {
  decision?: string | null;
  top1?: string | null;
  grade?: string | null;
  roi_pct?: number | null;
  /** 최종 verdict와 정합한 배지용 상태(go/conditional/hold). */
  status?: "go" | "conditional" | "hold" | string | null;
}

/** 종합 판정 — 백엔드 verdict와 1:1. */
export interface DecisionVerdict {
  decision: DecisionVerdictDecision | string;
  confidence: DecisionConfidence;
  reasons: string[];
  blockers: string[];
  go_nogo: DecisionGoNoGo | null;
  gate: "PASS" | "TENTATIVE" | "BLOCK" | string;
}

/**
 * 면적 override 괴리 메타 — 백엔드 meta.area_override(_area_override_meta)와 1:1.
 *
 * 프론트가 보낸 통합면적(override)이 엔진 대표면적과 얼마나 다른지(ratio)를 가시화한다.
 * 5배(또는 1/5배) 초과 괴리면 warning 이 붙어 '잘못된 면적'(다른 부지·단위오류·악의 입력)이
 * 권위 KPI(대지면적·GFA·사업성)를 왜곡하기 전에 경고한다(라우터 422 상한을 통과한 값이라도).
 * override 미적용이거나 엔진 대표면적 미확보면 meta.area_override 자체가 없다(옵셔널).
 */
export interface DecisionAreaOverrideMeta {
  override_area_sqm: number;
  engine_area_sqm: number;
  ratio: number;
  /** 5배 초과 괴리 시에만 부착(잘못된 면적 가시화). 없으면 정상 범위. */
  warning?: string | null;
}

/** 메타 — 과금·배포 상태·면적 override 괴리. deploy_pending이면 라이브 실호출은 배포 환경에서만 동작. */
export interface DecisionBriefMeta {
  use_llm?: boolean;
  deploy_pending?: boolean;
  deploy_pending_note?: string;
  reason?: string;
  /** 면적 override 괴리 메타(통합면적이 엔진 대표면적과 과도하게 다르면 warning 동반). */
  area_override?: DecisionAreaOverrideMeta;
}

/**
 * 캐시 메타 — 백엔드 analysis_cache.cache_get 이 응답 본문 최상위에 부착하는 _cache 와 1:1.
 * 캐시 적중(영속 재사용) 시에만 존재한다(신규 분석 응답에는 없음·옵셔널).
 */
export interface DecisionBriefCacheMeta {
  cached?: boolean;
  created_at?: string | null;
}

export interface DecisionBriefBilling {
  use_llm?: boolean;
  billing_key?: string;
  estimated_fee_krw?: number;
  note?: string;
}

/** 의사결정 브리프 응답 본문(POST /api/v1/projects/{id}/decision-brief). */
export interface DecisionBrief {
  address?: string | null;
  project_id?: string | null;
  parcel_count: number;
  parts: DecisionBriefPart[];
  verdict: DecisionVerdict;
  billing?: DecisionBriefBilling;
  meta?: DecisionBriefMeta;
  /** 캐시 적중 시 백엔드(analysis_cache)가 최상위에 부착하는 메타(신규 분석엔 없음·옵셔널). */
  _cache?: DecisionBriefCacheMeta;
}

/**
 * 브리프 parts에서 특정 도메인 part를 안전하게 조회(SSOT 단일 출처).
 *
 * Tier2 드릴다운 패널(인허가·사업성 등)이 Stage1 통합분석 결과를 재사용할 때, 매번
 * `parts.find(...)`를 복붙하지 않고 이 헬퍼로 일원화한다(키 드리프트·silent-null 방지).
 * brief나 part가 없으면 null을 반환한다(폴백=기존 동작·무회귀).
 */
export function findDecisionPart(
  brief: DecisionBrief | null | undefined,
  partId: DecisionBriefPartId,
): DecisionBriefPart | null {
  if (!brief?.parts) return null;
  return brief.parts.find((p) => p.part === partId) ?? null;
}
