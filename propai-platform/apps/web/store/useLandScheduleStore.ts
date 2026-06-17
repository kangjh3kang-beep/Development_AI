import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * 토지조서(편입토지 관리) 스토어 — 프로젝트별 영속.
 *
 * 지번·소유자·소유지분·면적·소유구분(사유/국공유)·매입예정가·매입가·계약확정·
 * 동의(토지사용/지구단위)를 관리하고, 등기정보분석과 상호 연동한다.
 * 서버 동기화는 projectSync가 함께 처리(기기 무관).
 */

export type LandRow = {
  id: string;
  jibun: string; // 지번(주소)
  pnu?: string | null; // PNU(19자리) — 있으면 대지지분 등 분석에서 재지오코딩 생략(빠른 경로)
  owner: string; // 소유자
  share: string; // 소유지분(집합건물 세대행은 대지권 비율 %)
  area_sqm: number | null; // 면적(집합건물 세대행은 '대지지분 면적'=실토지 기여분)
  exclusive_area_sqm?: number | null; // 세대 전유면적(집합건물 세대행만) — 대지지분 산정근거
  unit_label?: string; // 동·호(집합건물 세대행만, 예: "101동 1502호")
  parent_id?: string | null; // 집합건물 호실 행이면 부모 필지 행 id(토지조서에 필지 하단 중첩 배열)
  // ── 확장 동의(추가/삭제 가능한 커스텀 동의 유형) — key=consentTypes의 id ──
  consents?: Record<string, boolean>;
  // ── S3 케이스 분기: 필지 유형 자동감지(토지만/단일필지건물/집합건물) ──
  parcel_case?: "land" | "building" | "aggregate";
  zone_code?: string; // 용도지역(자동보강)
  is_aggregate?: boolean; // 집합건물(공동주택·다세대·집합상가) 여부
  building_name?: string; // 건물명
  unit_count?: number | null; // 세대/호수(집합건물)
  owner_type: "사유지" | "국공유지" | ""; // 소유구분
  expected_price: number | null; // 매입예정가(원)
  purchase_price: number | null; // 매입가(원)
  contracted: boolean; // 매입계약 확정여부
  land_use_consent: boolean; // 토지사용동의서
  district_consent: boolean; // 지구단위(정비) 동의서
  operator_consent: boolean; // 시행자지정동의서(사업시행자 지정 동의)
  pdf_url?: string | null; // 발급 등기부등본 PDF(서버 저장, TTL)
  note?: string;
};

// ── 사업방식별 동의서 프리셋 ──
// 토지사용동의(land_use)는 토지 사용권원 확보 = 모든 사업의 기본 전제이므로 공통 필수(fixed, 삭제불가).
export type ConsentType = { id: string; label: string; fixed?: boolean };
const LAND_USE: ConsentType = { id: "land_use", label: "토지사용", fixed: true };

export const BIZ_METHODS = [
  "일반(매입·시행자)", "지구단위계획", "도시개발사업",
  "재개발(정비)", "재건축", "가로주택·소규모재건축", "역세권 개발",
] as const;
export type BizMethod = (typeof BIZ_METHODS)[number];

export const BIZ_METHOD_PRESETS: Record<string, ConsentType[]> = {
  "일반(매입·시행자)": [LAND_USE, { id: "contract", label: "매매계약" }, { id: "operator", label: "시행자지정" }],
  "지구단위계획": [LAND_USE, { id: "district_unit", label: "지구단위(구역지정)" }, { id: "operator", label: "시행자지정" }],
  "도시개발사업": [LAND_USE, { id: "dev_zone", label: "도시개발구역지정" }, { id: "owner_consent", label: "토지소유자(면적/인원)" }, { id: "reparcel", label: "환지·수용방식" }, { id: "operator", label: "시행자지정" }],
  "재개발(정비)": [LAND_USE, { id: "redev_zone", label: "정비구역지정" }, { id: "assoc", label: "조합설립(3/4)" }, { id: "impl_plan", label: "사업시행계획" }],
  "재건축": [LAND_USE, { id: "assoc", label: "조합설립(3/4·동2/3)" }, { id: "safety", label: "안전진단" }, { id: "impl_plan", label: "사업시행계획" }],
  "가로주택·소규모재건축": [LAND_USE, { id: "assoc", label: "조합설립(8/10)" }, { id: "impl_plan", label: "사업시행" }],
  "역세권 개발": [LAND_USE, { id: "district_unit", label: "구역지정" }, { id: "operator", label: "시행자지정" }],
};
export const DEFAULT_BIZ_METHOD: BizMethod = "일반(매입·시행자)";

type State = {
  byProject: Record<string, LandRow[]>;
  bizMethodByProject: Record<string, string>;       // 프로젝트별 선택 사업방식
  consentTypesByProject: Record<string, ConsentType[]>; // 프로젝트별 활성 동의 항목(프리셋+커스텀)
  getRows: (projectId: string | null) => LandRow[];
  setRows: (projectId: string | null, rows: LandRow[]) => void;
  addRow: (projectId: string | null, row: Partial<LandRow>) => void;
  updateRow: (projectId: string | null, id: string, patch: Partial<LandRow>) => void;
  removeRow: (projectId: string | null, id: string) => void;
  getBizMethod: (projectId: string | null) => string;
  getConsentTypes: (projectId: string | null) => ConsentType[];
  setBizMethod: (projectId: string | null, method: string) => void; // 프리셋 동의항목 일괄 적용
  addConsentType: (projectId: string | null, label: string) => void;
  removeConsentType: (projectId: string | null, id: string) => void; // fixed는 삭제 불가
};

const KEY = (id: string | null) => id || "_default";
// 결정적 id(라벨 기반) — 삭제 후 재추가 시 기존 행의 consents 체크값이 복원되도록 무작위 접미사 미사용.
const slug = (s: string) => "c_" + s.replace(/[^a-zA-Z0-9가-힣]/g, "").slice(0, 16);

export const useLandScheduleStore = create<State>()(
  persist(
    (set, get) => ({
      byProject: {},
      bizMethodByProject: {},
      consentTypesByProject: {},
      getRows: (pid) => get().byProject[KEY(pid)] || [],
      getBizMethod: (pid) => get().bizMethodByProject[KEY(pid)] || DEFAULT_BIZ_METHOD,
      getConsentTypes: (pid) => {
        const ct = get().consentTypesByProject[KEY(pid)];
        if (ct && ct.length) return ct;
        // 미설정 시 현재(또는 기본) 사업방식의 프리셋.
        return BIZ_METHOD_PRESETS[get().getBizMethod(pid)] || BIZ_METHOD_PRESETS[DEFAULT_BIZ_METHOD];
      },
      setBizMethod: (pid, method) =>
        set((s) => {
          const k = KEY(pid);
          const preset = BIZ_METHOD_PRESETS[method] || BIZ_METHOD_PRESETS[DEFAULT_BIZ_METHOD];
          return {
            bizMethodByProject: { ...s.bizMethodByProject, [k]: method },
            consentTypesByProject: { ...s.consentTypesByProject, [k]: preset.map((c) => ({ ...c })) },
          };
        }),
      addConsentType: (pid, label) =>
        set((s) => {
          const k = KEY(pid);
          const cur = s.consentTypesByProject[k] || get().getConsentTypes(pid);
          const lbl = (label || "").trim();
          if (!lbl || cur.some((c) => c.label === lbl || c.id === slug(lbl))) return {}; // 라벨·id 중복 모두 차단
          return { consentTypesByProject: { ...s.consentTypesByProject, [k]: [...cur, { id: slug(lbl), label: lbl }] } };
        }),
      removeConsentType: (pid, id) =>
        set((s) => {
          const k = KEY(pid);
          const cur = s.consentTypesByProject[k] || get().getConsentTypes(pid);
          return { consentTypesByProject: { ...s.consentTypesByProject, [k]: cur.filter((c) => c.id !== id || c.fixed) } };
        }),
      setRows: (pid, rows) =>
        set((s) => ({ byProject: { ...s.byProject, [KEY(pid)]: rows } })),
      addRow: (pid, row) =>
        set((s) => {
          const k = KEY(pid);
          const cur = s.byProject[k] || [];
          const newRow: LandRow = {
            id: Math.random().toString(36).slice(2, 9),
            jibun: "", owner: "", share: "", area_sqm: null, owner_type: "",
            expected_price: null, purchase_price: null, contracted: false,
            land_use_consent: false, district_consent: false, operator_consent: false,
            ...row,
          };
          return { byProject: { ...s.byProject, [k]: [...cur, newRow] } };
        }),
      updateRow: (pid, id, patch) =>
        set((s) => {
          const k = KEY(pid);
          return { byProject: { ...s.byProject, [k]: (s.byProject[k] || []).map((r) => (r.id === id ? { ...r, ...patch } : r)) } };
        }),
      removeRow: (pid, id) =>
        set((s) => {
          const k = KEY(pid);
          return { byProject: { ...s.byProject, [k]: (s.byProject[k] || []).filter((r) => r.id !== id) } };
        }),
    }),
    { name: "propai-land-schedule" },
  ),
);
