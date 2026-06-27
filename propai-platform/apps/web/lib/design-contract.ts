// 설계 C2R 계약(envelope_result·geometry_invariants·rule_trace) — 프론트 타입 + 안전 파서.
//
// 무엇인가(쉬운 설명): 백엔드 설계 엔진은 /design/{id}/mass·/bim 응답에 "이 건물 매스가
//   어떤 법규로·어떤 값으로 산출됐고, 기하가 정상인지(PASS/FAIL)"를 담은 표준 계약(compliance)을
//   같이 보낸다. 지금까지 프론트는 이 계약을 한 군데도 안 읽고 버렸다(감사 적발). 이 파일은
//   그 계약의 모양(타입)을 백엔드 실제 필드명과 1:1로 맞춰 정의하고, 응답 dict를 안전하게
//   읽어 들이는 순수 파서를 제공한다(추측·날조 금지 — 백엔드가 안 준 값은 null).
//
// 출처(백엔드 실제 정의):
//   - apps/api/app/services/cad/envelope_result.py — EnvelopeResult/EnvelopeGeometry/EnvelopeMetrics
//   - apps/api/app/services/cad/geometry_invariants.py — GeometryInvariantResult.to_dict()/InvariantCheck.to_dict()
//   - apps/api/app/services/cad/rule_trace.py — rule_trace entry {rule_code,rule_name,applied,basis,source,legal_link}
//   - apps/api/app/services/cad/design_contract.py — build_mass_contract → {envelope_result, geometry_invariants}
//
// 무회귀 원칙: 모든 필드 옵셔널/nullable. 어느 키가 없어도(구 백엔드·부분 응답) 파서가 깨지지 않고
//   "없으면 null"로 정직하게 둔다. 소비처(렌더)는 null을 "없음/미산출"로 표기한다.

// 기하 불변식 등급(백엔드 GeoStatus enum과 동일 문자열) — 최악 등급/개별 체크 status에 쓰임.
export type GeoStatus = "PASS" | "PASS_WITH_WARNINGS" | "FAIL";

// 개별 기하 불변식 한 건(InvariantCheck.to_dict()) — 무엇을 봤고 왜 이 등급인지.
export type GeometryInvariantCheck = {
  code: string;        // 예: "INV-GEO-001"
  name: string;        // 사람이 읽는 이름(쉬운 한국어)
  status: GeoStatus;   // 이 체크의 등급
  detail: string;      // 한 줄 설명
};

// 전체 기하 불변식 결과(GeometryInvariantResult.to_dict()) — 최악 등급 + 개별 체크 + 경고/오류.
export type GeometryInvariants = {
  status: GeoStatus;                    // 최악 등급(개별 체크 중 가장 나쁜 것)
  checks: GeometryInvariantCheck[];     // 개별 체크 목록
  warnings: string[];                   // 경고 문구(차단 아님)
  errors: string[];                     // 오류 문구(FAIL)
};

// 적용 법규 추적 한 줄(rule_trace entry) — "어떤 법규가 어떤 값으로 적용됐는지".
//   evidence와 별개 구조(kernel-trace). applied는 규칙마다 키가 다른 자유 dict.
export type ContractRuleTraceEntry = {
  rule_code: string;                          // 예: "건축법시행령_119/국토계획법시행령_84_85"
  rule_name: string;                          // 사람이 읽는 규칙 이름
  applied?: Record<string, unknown> | null;   // 적용 결과값(규칙별 키 상이)
  basis?: string | null;                      // 산식·근거 한 줄
  source?: string | null;                     // 법령 출처(예: "건축법 §61·시행령 §86")
  legal_link?: string | null;                 // 법령 원문 링크(없으면 null)
};

// 매스 기하(EnvelopeGeometry) — 건물 모양·크기. 미상은 null.
export type ContractEnvelopeGeometry = {
  building_width_m?: number | null;
  building_depth_m?: number | null;
  footprint_sqm?: number | null;
  num_floors?: number | null;
  floor_height_m?: number | null;
  building_height_m?: number | null;
  massing_profile?: string | null;
  podium?: Record<string, unknown> | null;
  tower?: Record<string, unknown> | null;
  floors_for_units?: number | null;
  residential_gfa_sqm?: number | null;
};

// 핵심 수치(EnvelopeMetrics) — 보고·검증에 바로 쓰는 숫자. 미상은 null.
export type ContractEnvelopeMetrics = {
  bcr_pct?: number | null;
  far_pct?: number | null;
  gfa_sqm?: number | null;
  canonical_floors?: number | null;       // ★정본 층수(권위 소스) — floors_for_units 우선, 없으면 num_floors
  total_units?: number | null;
  applied_max_bcr_pct?: number | null;
  applied_max_far_pct?: number | null;
};

// 표준 그릇(EnvelopeResult) — 매스 산출물의 단일 계약. 거의 모든 필드 옵셔널(무회귀).
export type ContractEnvelopeResult = {
  schema_version?: string | null;            // 예: "propai.envelope_result.v0.1"
  status?: GeoStatus | null;                 // 기하불변식 최악등급(없으면 PASS 의미)
  geometry?: ContractEnvelopeGeometry | null;
  metrics?: ContractEnvelopeMetrics | null;
  evidence?: Record<string, unknown>[] | null;
  geometry_invariants?: GeometryInvariants | null;
  warnings?: string[] | null;
  // provenance(재현·출처추적·변조탐지) — 입력이 없으면 백엔드가 null로 둔다(가짜 해시 없음).
  run_id?: string | null;
  input_hash?: string | null;
  geometry_hash?: string | null;
  source_version?: string | null;
  // 적용 규칙 묶음의 지문 + 추적표(site_input+legal이 둘 다 있을 때만 채워짐).
  rule_set_hash?: string | null;
  rule_trace?: ContractRuleTraceEntry[] | null;
};

// 매스에 동봉되는 계약 묶음(build_mass_contract 반환) — /mass·/bim 응답의 compliance 필드.
export type DesignCompliance = {
  envelope_result?: ContractEnvelopeResult | null;
  geometry_invariants?: GeometryInvariants | null;
};

// ── 안전 파서(추측·날조 금지) ──
//
// 응답 JSON은 unknown으로 들어온다. 아래 파서는 "있으면 그대로, 모양이 다르면 null"만 한다.
// 값을 만들어내지 않으며(무날조), 어떤 형태가 와도 예외 없이 동작한다(무회귀).

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// 응답의 compliance(또는 그 안의 키)를 표준 DesignCompliance로 정규화한다.
//   d는 /mass·/bim 응답의 compliance 값(또는 그 dict). 형태가 아니면 null(저장 안 함).
//   ★envelope_result/geometry_invariants는 백엔드가 model_dump(mode="json")/to_dict()로 직렬화한
//     평범한 dict라, 여기선 형태만 통과시키고 깊은 변환은 하지 않는다(필드명 그대로 유지).
export function parseDesignCompliance(d: unknown): DesignCompliance | null {
  if (!isObj(d)) return null;
  const env = d["envelope_result"];
  const geo = d["geometry_invariants"];
  const envelope_result = isObj(env) ? (env as ContractEnvelopeResult) : null;
  const geometry_invariants = isObj(geo) ? (geo as GeometryInvariants) : null;
  // 둘 다 없으면 저장 가치가 없으니 null(빈 객체 환류로 staleness 오염 방지).
  if (!envelope_result && !geometry_invariants) return null;
  return { envelope_result, geometry_invariants };
}

// 유한 '양수'만 통과(0·음수·NaN 거름) — 층수처럼 0이 정본으로 새면 안 되는 값에 쓴다(무날조).
function posInt(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.round(v) : null;
}

// 계약이 정한 '정본 층수'(envelope_result.metrics.canonical_floors)를 안전하게 꺼낸다.
//   ★이 값이 C2R 계약상 층수의 권위 소스다. 없거나 0/음수면 null(폴백은 호출부가 결정).
export function contractCanonicalFloors(compliance?: DesignCompliance | null): number | null {
  return posInt(compliance?.envelope_result?.metrics?.canonical_floors);
}

// ── 근거 렌더용 정규화(EvidencePanel/배지 입력) ──
//
// 아래 두 함수는 "계약을 사용자에게 보이는 근거로 끌어올리는" 표시용 정규화다. store의 실제
// 계약 값만 읽어 모양만 다듬으며(무날조 — 없는 값은 만들지 않음), 깨지지 않게 전부 방어한다.

// EvidencePanel의 EvidenceItem과 구조 호환(컴포넌트 직접 의존 회피 — 순수 lib 유지).
export type ContractEvidenceItem = {
  label: string;
  value: string | number;
  basis?: string | null;
  legalRef?: { lawName: string; article?: string | null; title?: string | null; url?: string | null } | null;
};

// 계약을 한눈에 보는 헤드라인(배지·요약용) — 없으면 null 필드(화면은 "없음/미산출").
export type ContractSummary = {
  status: GeoStatus | null;        // 기하 검증 최악 등급(PASS/WARN/FAIL)
  canonicalFloors: number | null;  // 계약 정본 층수
  runId: string | null;            // 산출 식별자(재현·추적)
  ruleSetHashShort: string | null; // 적용 규칙묶음 지문(짧게 표시)
  schemaVersion: string | null;    // 계약 스키마 버전
  ruleCount: number;               // 적용 법규 추적 항목 수
  warningCount: number;            // 기하 경고 수
  errorCount: number;              // 기하 오류(FAIL) 수
};

function shortHash(h?: string | null): string | null {
  return typeof h === "string" && h.trim() ? h.trim().slice(0, 12) : null;
}

// 계약 → 헤드라인 요약(배지·칩). 전부 방어적으로 읽어 미상은 null(무날조).
export function summarizeCompliance(compliance?: DesignCompliance | null): ContractSummary | null {
  const env = compliance?.envelope_result ?? null;
  const geo = compliance?.geometry_invariants ?? null;
  if (!env && !geo) return null;
  // 최악 등급은 envelope_result.status(있으면) 우선, 없으면 geometry_invariants.status.
  const status: GeoStatus | null =
    (env?.status as GeoStatus | undefined) ?? (geo?.status as GeoStatus | undefined) ?? null;
  const ruleTrace = Array.isArray(env?.rule_trace) ? env!.rule_trace! : [];
  const warnings = Array.isArray(geo?.warnings) ? geo!.warnings : (Array.isArray(env?.warnings) ? env!.warnings! : []);
  const errors = Array.isArray(geo?.errors) ? geo!.errors : [];
  return {
    status: status ?? null,
    canonicalFloors: contractCanonicalFloors(compliance),
    runId: typeof env?.run_id === "string" && env.run_id.trim() ? env.run_id.trim() : null,
    ruleSetHashShort: shortHash(env?.rule_set_hash),
    schemaVersion: typeof env?.schema_version === "string" && env.schema_version.trim() ? env.schema_version.trim() : null,
    ruleCount: ruleTrace.length,
    warningCount: warnings.length,
    errorCount: errors.length,
  };
}

// 적용 법규 추적(rule_trace) → EvidenceItem[]. "어떤 법규가 어떤 값으로 적용됐는지"를 근거 행으로.
//   rule_name=label, basis=basis, source/legal_link→법령칩. rule_name 없는 항목은 제외(빈 행 방지).
//   ★rule_trace가 비었으면 빈 배열을 돌려준다 — 호출부가 '근거 없음'을 정직 표기(가짜 entry 금지).
export function ruleTraceToEvidence(compliance?: DesignCompliance | null): ContractEvidenceItem[] {
  const ruleTrace = compliance?.envelope_result?.rule_trace;
  if (!Array.isArray(ruleTrace)) return [];
  return ruleTrace
    .filter((r): r is ContractRuleTraceEntry => isObj(r))
    .filter((r) => typeof r.rule_name === "string" && r.rule_name.trim())
    .map((r) => {
      // 적용값(applied dict)을 "키=값" 한 줄로 압축(있으면) — 어떤 수치로 적용됐는지 표시.
      const appliedStr = isObj(r.applied)
        ? Object.entries(r.applied)
            .filter(([, v]) => v !== null && v !== undefined)
            .map(([k, v]) => `${k}=${typeof v === "number" ? v : String(v)}`)
            .join(", ")
        : "";
      const source = typeof r.source === "string" && r.source.trim() ? r.source.trim() : null;
      const link = typeof r.legal_link === "string" && r.legal_link.trim() ? r.legal_link.trim() : null;
      return {
        label: String(r.rule_name).trim(),
        // value는 적용값 요약(있으면), 없으면 규칙코드(추적용).
        value: appliedStr || (typeof r.rule_code === "string" ? r.rule_code : "적용"),
        basis: typeof r.basis === "string" && r.basis.trim() ? r.basis.trim() : null,
        // 법령 출처가 있으면 칩(원문 링크는 legal_link 있을 때만 — 없으면 텍스트만, 정직성).
        legalRef: source || link ? { lawName: source || "법령 근거", url: link } : null,
      };
    });
}
