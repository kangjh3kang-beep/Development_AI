"use client";

/**
 * Phase 1-A — 현장 워크스페이스(역할 기반 메뉴 게이팅).
 * 진입 토큰(site_token) 검증 → 없으면 진입 모달. GET /sales/sites/{id}/role 의 features[]/role로
 * 탭(메뉴)을 차등 노출. can_manage면 "현장 비밀번호 설정" 노출.
 *
 * Phase 1-A 범위: 진입·게이팅·관리 UI 골격. 각 탭의 상세 패널은 후속 단계에서 연결한다.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { getStoredSiteToken, clearSiteToken } from "@/lib/salesApi";
import SiteEnterModal from "@/components/sales-app/SiteEnterModal";
import SitePasswordModal from "@/components/sales-app/SitePasswordModal";
import { ROLE_LABEL, MANAGE_ROLES, visibleTabs } from "@/components/sales-app/roleConfig";
import type { Locale } from "@/i18n/config";

interface RoleResponse {
  site_id?: string;
  role: string;
  role_label?: string;
  org_path?: string;
  can_manage?: boolean;
  password_set?: boolean;
  features: string[];
}

export default function SiteWorkspaceClient({ locale, siteId }: { locale: Locale; siteId: string }) {
  const [role, setRole] = useState<RoleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [needEnter, setNeedEnter] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [tab, setTab] = useState<string>("dashboard");
  const [err, setErr] = useState("");

  const loadRole = useCallback(() => {
    // 진입 토큰이 없으면 역할 조회 없이 재진입 모달만(동기 setState는 fetch 콜백 외에선 회피).
    if (!getStoredSiteToken(siteId)) {
      Promise.resolve().then(() => {
        setNeedEnter(true);
        setLoading(false);
      });
      return;
    }
    apiClient
      .get<RoleResponse>(`/sales/sites/${siteId}/role`)
      .then((r) => {
        setRole(r);
        setErr("");
        setNeedEnter(false);
        const tabs = visibleTabs(r.features);
        if (tabs[0]) setTab(tabs[0].key);
      })
      .catch((e) => {
        // 토큰 만료/없음 → 재진입 유도. 그 외는 에러 표시.
        if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
          clearSiteToken(siteId);
          setNeedEnter(true);
        } else {
          setErr("현장 정보를 불러오지 못했습니다.");
        }
      })
      .finally(() => setLoading(false));
  }, [siteId]);

  useEffect(() => {
    loadRole();
  }, [loadRole]);

  const tabs = role ? visibleTabs(role.features) : [];
  const canManage = role ? (role.can_manage ?? MANAGE_ROLES.has(role.role)) : false;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={`/${locale}/sales/sites`}
          className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
        >
          ← 내 현장
        </Link>
        <h1 className="text-lg font-black text-[var(--text-primary)]">분양 현장</h1>
        {role && (
          <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
            {role.role_label ?? ROLE_LABEL[role.role] ?? role.role}
          </span>
        )}
        {canManage && (
          <button
            onClick={() => setPwOpen(true)}
            className="ml-auto rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]"
          >
            🛠 현장 비밀번호 설정
          </button>
        )}
      </div>

      {err && (
        <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-300">
          {err}
        </div>
      )}

      {loading && <div className="h-20 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />}

      {!loading && role && (
        <>
          {/* 역할 기반 탭 — features[]에 포함된 메뉴만 노출 */}
          <div className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-3">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-3.5 py-1.5 text-sm font-bold transition ${
                  tab === t.key
                    ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-sm)]"
                    : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6">
            <p className="text-sm font-bold text-[var(--text-primary)]">
              {tabs.find((t) => t.key === tab)?.label ?? "현장"}
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              내 권한으로 접근 가능한 메뉴 {tabs.length}개가 노출됩니다. 상세 기능은 단계적으로 연결됩니다.
            </p>
            <p className="mt-3 text-[11px] text-[var(--text-tertiary)]">
              기능키: {role.features.length ? role.features.join(", ") : "(없음)"}
            </p>
          </div>
        </>
      )}

      {/* 진입 토큰 없음/만료 → 재진입 모달 */}
      {needEnter && (
        <SiteEnterModal
          locale={locale}
          siteId={siteId}
          siteName="이 현장"
          open={needEnter}
          onClose={() => setNeedEnter(false)}
          onEntered={() => {
            setNeedEnter(false);
            loadRole();
          }}
        />
      )}

      <SitePasswordModal siteId={siteId} open={pwOpen} onClose={() => setPwOpen(false)} />
    </div>
  );
}
