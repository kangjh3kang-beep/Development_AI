"use client";

/**
 * Phase 1-E — 재사용 프로필(개인 + 회사) 작성·저장 패널.
 *
 * PUBLIC 컨텐츠: 현장 site 컨텍스트가 아니라 전역 로그인 토큰을 사용한다.
 * → 일반 apiClient(Authorization Bearer만)로 /market/profile/* 를 호출(salesApi 아님, X-Site-Token 불필요).
 *
 * 1회 작성 → 저장하면 구인구직 마켓에서 profile_id로 원클릭 불러오기에 재사용된다.
 * 공개범위(visibility)·연락처 마스킹(mask_contact) 토글, 사진/로고 업로드, "자기기재" 고지 포함.
 * 백엔드 계약(_workspace/54 §7)과 필드명 정합.
 */
import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ImageUpload } from "@/components/ui/ImageUpload";

type Visibility = "public" | "contacts" | "private";

const VISIBILITY_LABEL: Record<Visibility, string> = {
  public: "전체 공개",
  contacts: "연결된 사용자만",
  private: "비공개(본인만)",
};

interface PersonalProfile {
  id?: string;
  user_id?: string;
  full_name?: string;
  contact?: string;
  region?: string;
  specialties?: string[];
  experience_years?: number;
  achievement_summary?: string;
  certifications?: string[];
  desired_conditions?: string;
  photo_url?: string;
  visibility?: Visibility;
  mask_contact?: boolean;
}

interface CompanyProfile {
  id?: string;
  owner_user_id?: string;
  org_id?: string;
  company_name?: string;
  company_type?: "DEVELOPER" | "AGENCY";
  company_size?: string;
  intro?: string;
  active_sites?: string;
  reputation?: string;
  logo_url?: string;
  contact?: string;
  region?: string;
  visibility?: Visibility;
  mask_contact?: boolean;
}

/** 쉼표 구분 문자열 ↔ 배열 변환. */
function toList(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}
function fromList(v?: string[]): string {
  return (v ?? []).join(", ");
}

function VisibilityControls({
  visibility,
  maskContact,
  onVisibility,
  onMask,
}: {
  visibility: Visibility;
  maskContact: boolean;
  onVisibility: (v: Visibility) => void;
  onMask: (b: boolean) => void;
}) {
  return (
    <div className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <p className="text-xs font-bold text-[var(--text-secondary)]">공개 설정</p>
      <div className="flex flex-wrap gap-2">
        {(Object.keys(VISIBILITY_LABEL) as Visibility[]).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onVisibility(v)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              visibility === v
                ? "bg-[var(--accent-strong)] text-white"
                : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {VISIBILITY_LABEL[v]}
          </button>
        ))}
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--text-secondary)]">
        <input
          type="checkbox"
          checked={maskContact}
          onChange={(e) => onMask(e.target.checked)}
          className="h-4 w-4 accent-[var(--accent-strong)]"
        />
        연락처 마스킹(공개 시 뒤 4자리 숨김)
      </label>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  textarea,
  type = "text",
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
  type?: string;
  hint?: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold text-[var(--text-secondary)]">{label}</span>
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
      )}
      {hint && <span className="text-[10px] text-[var(--text-hint)]">{hint}</span>}
    </label>
  );
}

export default function MarketProfilePanel() {
  const [sub, setSub] = useState<"personal" | "company">("personal");

  // 개인 프로필 상태
  const [pLoading, setPLoading] = useState(true);
  const [pSaving, setPSaving] = useState(false);
  const [pMsg, setPMsg] = useState("");
  const [pErr, setPErr] = useState("");
  const [personal, setPersonal] = useState<PersonalProfile>({
    visibility: "public",
    mask_contact: true,
  });
  const [pSpecialties, setPSpecialties] = useState("");
  const [pCerts, setPCerts] = useState("");

  // 회사 프로필 상태
  const [cLoading, setCLoading] = useState(true);
  const [cSaving, setCSaving] = useState(false);
  const [cMsg, setCMsg] = useState("");
  const [cErr, setCErr] = useState("");
  const [company, setCompany] = useState<CompanyProfile>({
    company_type: "DEVELOPER",
    visibility: "public",
    mask_contact: true,
  });

  const loadPersonal = useCallback(() => {
    apiClient
      .get<{ exists: boolean; profile?: PersonalProfile }>("/market/profile/personal")
      .then((r) => {
        if (r?.exists && r.profile) {
          setPersonal({ visibility: "public", mask_contact: true, ...r.profile });
          setPSpecialties(fromList(r.profile.specialties));
          setPCerts(fromList(r.profile.certifications));
        }
        setPErr("");
      })
      .catch(() => setPErr("개인 프로필을 불러오지 못했습니다."))
      .finally(() => setPLoading(false));
  }, []);

  const loadCompany = useCallback(() => {
    apiClient
      .get<{ exists: boolean; profile?: CompanyProfile }>("/market/profile/company")
      .then((r) => {
        if (r?.exists && r.profile) {
          setCompany({ company_type: "DEVELOPER", visibility: "public", mask_contact: true, ...r.profile });
        }
        setCErr("");
      })
      .catch(() => setCErr("회사 프로필을 불러오지 못했습니다."))
      .finally(() => setCLoading(false));
  }, []);

  useEffect(() => {
    loadPersonal();
    loadCompany();
  }, [loadPersonal, loadCompany]);

  const savePersonal = () => {
    setPSaving(true);
    setPMsg("");
    setPErr("");
    apiClient
      .put<{ profile: PersonalProfile }>("/market/profile/personal", {
        body: {
          full_name: personal.full_name ?? "",
          contact: personal.contact ?? "",
          region: personal.region ?? "",
          specialties: toList(pSpecialties),
          experience_years: Number(personal.experience_years) || 0,
          achievement_summary: personal.achievement_summary ?? "",
          certifications: toList(pCerts),
          desired_conditions: personal.desired_conditions ?? "",
          photo_url: personal.photo_url ?? "",
          visibility: personal.visibility ?? "public",
          mask_contact: !!personal.mask_contact,
        },
      })
      .then((r) => {
        if (r?.profile) setPersonal({ visibility: "public", mask_contact: true, ...r.profile });
        setPMsg("개인 프로필이 저장되었습니다.");
      })
      .catch((e) => setPErr(e instanceof ApiClientError ? e.message : "저장에 실패했습니다."))
      .finally(() => setPSaving(false));
  };

  const saveCompany = () => {
    setCSaving(true);
    setCMsg("");
    setCErr("");
    apiClient
      .put<{ profile: CompanyProfile }>("/market/profile/company", {
        body: {
          company_name: company.company_name ?? "",
          company_type: company.company_type ?? "DEVELOPER",
          company_size: company.company_size ?? "",
          intro: company.intro ?? "",
          active_sites: company.active_sites ?? "",
          reputation: company.reputation ?? "",
          logo_url: company.logo_url ?? "",
          contact: company.contact ?? "",
          region: company.region ?? "",
          visibility: company.visibility ?? "public",
          mask_contact: !!company.mask_contact,
        },
      })
      .then((r) => {
        if (r?.profile) setCompany({ company_type: "DEVELOPER", visibility: "public", mask_contact: true, ...r.profile });
        setCMsg("회사 프로필이 저장되었습니다.");
      })
      .catch((e) => setCErr(e instanceof ApiClientError ? e.message : "저장에 실패했습니다."))
      .finally(() => setCSaving(false));
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-2.5 text-xs font-semibold text-amber-200">
        ⓘ 실적·자격 등 모든 항목은 <b>본인이 직접 기재</b>합니다. 타인에게 표시될 때 &quot;자기기재&quot;로 안내되며,
        허위 기재 시 불이익을 받을 수 있습니다.
      </div>

      <div className="flex gap-2 border-b border-[var(--line)] pb-3">
        {(["personal", "company"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setSub(k)}
            className={`rounded-lg px-3.5 py-1.5 text-sm font-bold transition ${
              sub === k
                ? "bg-[var(--accent-strong)] text-white"
                : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {k === "personal" ? "개인 프로필" : "회사 프로필"}
          </button>
        ))}
      </div>

      {sub === "personal" && (
        <div className="space-y-3">
          {pLoading ? (
            <div className="h-40 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ) : (
            <>
              <ImageUpload
                value={personal.photo_url}
                onChange={(url) => setPersonal((p) => ({ ...p, photo_url: url }))}
                label="프로필 사진을 업로드하세요"
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="이름" value={personal.full_name ?? ""} onChange={(v) => setPersonal((p) => ({ ...p, full_name: v }))} placeholder="홍길동" />
                <Field label="연락처" value={personal.contact ?? ""} onChange={(v) => setPersonal((p) => ({ ...p, contact: v }))} placeholder="010-1234-5678" />
                <Field label="활동 지역" value={personal.region ?? ""} onChange={(v) => setPersonal((p) => ({ ...p, region: v }))} placeholder="서울 강남구" />
                <Field label="경력(년)" type="number" value={String(personal.experience_years ?? "")} onChange={(v) => setPersonal((p) => ({ ...p, experience_years: Number(v) || 0 }))} placeholder="5" />
              </div>
              <Field label="전문 분야" value={pSpecialties} onChange={setPSpecialties} placeholder="분양영업, 상담, 모델하우스 운영" hint="쉼표(,)로 구분" />
              <Field label="자격증" value={pCerts} onChange={setPCerts} placeholder="공인중개사, 분양상담사" hint="쉼표(,)로 구분" />
              <Field label="실적 요약" textarea value={personal.achievement_summary ?? ""} onChange={(v) => setPersonal((p) => ({ ...p, achievement_summary: v }))} placeholder="주요 분양 현장 및 실적(자기기재)" />
              <Field label="희망 조건" textarea value={personal.desired_conditions ?? ""} onChange={(v) => setPersonal((p) => ({ ...p, desired_conditions: v }))} placeholder="희망 수수료율·근무 형태 등" />

              <VisibilityControls
                visibility={personal.visibility ?? "public"}
                maskContact={!!personal.mask_contact}
                onVisibility={(v) => setPersonal((p) => ({ ...p, visibility: v }))}
                onMask={(b) => setPersonal((p) => ({ ...p, mask_contact: b }))}
              />

              {pErr && <p className="text-sm font-semibold text-rose-300">{pErr}</p>}
              {pMsg && <p className="text-sm font-semibold text-emerald-300">{pMsg}</p>}

              <button
                onClick={savePersonal}
                disabled={pSaving}
                className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {pSaving ? "저장 중..." : "개인 프로필 저장"}
              </button>
            </>
          )}
        </div>
      )}

      {sub === "company" && (
        <div className="space-y-3">
          {cLoading ? (
            <div className="h-40 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ) : (
            <>
              <ImageUpload
                value={company.logo_url}
                onChange={(url) => setCompany((c) => ({ ...c, logo_url: url }))}
                label="회사 로고를 업로드하세요"
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="회사명" value={company.company_name ?? ""} onChange={(v) => setCompany((c) => ({ ...c, company_name: v }))} placeholder="(주)○○개발" />
                <label className="block space-y-1">
                  <span className="text-xs font-bold text-[var(--text-secondary)]">유형</span>
                  <select
                    value={company.company_type ?? "DEVELOPER"}
                    onChange={(e) => setCompany((c) => ({ ...c, company_type: e.target.value as "DEVELOPER" | "AGENCY" }))}
                    className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-strong)] focus:outline-none"
                  >
                    <option value="DEVELOPER">시행사</option>
                    <option value="AGENCY">대행사</option>
                  </select>
                </label>
                <Field label="규모" value={company.company_size ?? ""} onChange={(v) => setCompany((c) => ({ ...c, company_size: v }))} placeholder="예: 임직원 30명" />
                <Field label="지역" value={company.region ?? ""} onChange={(v) => setCompany((c) => ({ ...c, region: v }))} placeholder="서울" />
                <Field label="연락처" value={company.contact ?? ""} onChange={(v) => setCompany((c) => ({ ...c, contact: v }))} placeholder="02-000-0000" />
              </div>
              <Field label="회사 소개" textarea value={company.intro ?? ""} onChange={(v) => setCompany((c) => ({ ...c, intro: v }))} placeholder="회사 소개(자기기재)" />
              <Field label="진행 현장" textarea value={company.active_sites ?? ""} onChange={(v) => setCompany((c) => ({ ...c, active_sites: v }))} placeholder="현재 진행 중인 분양 현장" />
              <Field label="실적" textarea value={company.reputation ?? ""} onChange={(v) => setCompany((c) => ({ ...c, reputation: v }))} placeholder="주요 실적(자기기재)" />

              <VisibilityControls
                visibility={company.visibility ?? "public"}
                maskContact={!!company.mask_contact}
                onVisibility={(v) => setCompany((c) => ({ ...c, visibility: v }))}
                onMask={(b) => setCompany((c) => ({ ...c, mask_contact: b }))}
              />

              {cErr && <p className="text-sm font-semibold text-rose-300">{cErr}</p>}
              {cMsg && <p className="text-sm font-semibold text-emerald-300">{cMsg}</p>}

              <button
                onClick={saveCompany}
                disabled={cSaving}
                className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {cSaving ? "저장 중..." : "회사 프로필 저장"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
