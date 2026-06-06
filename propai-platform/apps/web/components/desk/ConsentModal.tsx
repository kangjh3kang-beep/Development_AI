"use client";

/**
 * F-2 — 모델하우스 방문객 개인정보 수집·이용 동의 팝업.
 *
 * 개인정보보호법 제15·22조: ① 수집항목 ② 이용목적 ③ 보유기간을 명확히 고지하고,
 * 필수동의(개인정보)와 선택동의(마케팅·제3자)를 분리해 받는다. 필수 미동의 시 등록 비활성.
 * 백엔드 GET /mh/consent-template 의 고지문을 렌더하며, 미연결/오류 시 기본 고지문으로 폴백한다.
 */

import { useMemo, useState } from "react";

export interface ConsentItem {
  type: string;
  required: boolean;
  title: string;
  items: string[];
  purpose: string;
  retention: string;
  deny_notice?: string;
}

export interface ConsentTemplate {
  version: string;
  consents: ConsentItem[];
}

export interface ConsentResult {
  type: string;
  agreed: boolean;
  items: string[];
  purpose: string;
  retention: string;
  version: string;
  agreed_at: string;
}

// 백엔드 미연결/오류 시 폴백 고지문(백엔드 consent.py 와 동일 골격).
const FALLBACK_TEMPLATE: ConsentTemplate = {
  version: "2026-06-v1",
  consents: [
    {
      type: "REQUIRED",
      required: true,
      title: "[필수] 방문·상담 관리 목적 개인정보 수집·이용",
      items: ["성명", "연락처(휴대전화)", "방문목적", "방문인원", "방문일시"],
      purpose: "모델하우스 방문 응대·상담 배정 및 분양 상담 진행, 재방문 관리",
      retention: "상담종료(또는 청약 미진행 확정) 후 1년 보관 후 파기",
      deny_notice: "필수 항목에 동의하지 않으시면 방문 등록 및 상담 배정이 불가합니다.",
    },
    {
      type: "MARKETING",
      required: false,
      title: "[선택] 분양 정보 마케팅 활용",
      items: ["성명", "연락처(휴대전화)"],
      purpose: "신규 분양·이벤트·할인 정보 등 마케팅 정보의 문자·전화 발송",
      retention: "동의 철회 시 또는 수집일로부터 2년 중 먼저 도래하는 시점까지",
      deny_notice: "미동의 시에도 방문 등록은 가능하며, 마케팅 정보만 발송되지 않습니다.",
    },
    {
      type: "THIRD_PARTY",
      required: false,
      title: "[선택] 시행사/분양대행사 제3자 제공",
      items: ["성명", "연락처(휴대전화)", "방문목적"],
      purpose: "분양 계약 진행을 위한 시행사·분양대행사의 상담 연락",
      retention: "제공 목적 달성 후 또는 동의 철회 시까지",
      deny_notice: "미동의 시에도 방문 등록은 가능합니다.",
    },
  ],
};

interface Props {
  /** 동의 고지문(부모가 GET /mh/consent-template 로 받아 주입). 없으면 폴백 사용. */
  template?: ConsentTemplate | null;
  onConfirm: (consents: ConsentResult[]) => void;
  onCancel: () => void;
}

export default function ConsentModal({ template, onConfirm, onCancel }: Props) {
  const tpl = template ?? FALLBACK_TEMPLATE;
  // 동의상태는 모든 항목 false에서 시작(필수도 사용자가 명시 동의해야 함).
  // 모달은 열릴 때마다 새로 마운트되므로 초기화 effect 없이 lazy 초기값으로 충분하다.
  const [agree, setAgree] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(tpl.consents.map((c) => [c.type, false])),
  );

  // 필수 type 모두 동의해야 확인 활성(개인정보보호법 제15조 — 미동의 시 수집 불가).
  const requiredOk = useMemo(
    () => tpl.consents.filter((c) => c.required).every((c) => agree[c.type]),
    [tpl, agree],
  );

  const confirm = () => {
    if (!requiredOk) return;
    const now = new Date().toISOString();
    const out: ConsentResult[] = tpl.consents.map((c) => ({
      type: c.type,
      agreed: !!agree[c.type],
      items: c.items,
      purpose: c.purpose,
      retention: c.retention,
      version: tpl.version,
      agreed_at: now,
    }));
    onConfirm(out);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-xl">
        <h2 className="mb-1 text-lg font-black text-[var(--text-primary)]">개인정보 수집·이용 동의</h2>
        <p className="mb-4 text-xs text-[var(--text-tertiary)]">
          개인정보보호법 제15·22조에 따라 수집항목·이용목적·보유기간을 고지합니다. (동의서 버전 {tpl.version})
        </p>

        <div className="space-y-4">
          {tpl.consents.map((c) => (
            <div key={c.type} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3">
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={!!agree[c.type]}
                  onChange={(e) => setAgree((prev) => ({ ...prev, [c.type]: e.target.checked }))}
                  className="mt-1"
                  aria-label={c.title}
                />
                <span className="text-sm font-bold text-[var(--text-primary)]">{c.title}</span>
              </label>
              <dl className="mt-2 space-y-1 pl-6 text-xs text-[var(--text-secondary)]">
                <div className="flex gap-2">
                  <dt className="shrink-0 font-semibold text-[var(--text-tertiary)]">수집항목</dt>
                  <dd>{c.items.join(", ")}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="shrink-0 font-semibold text-[var(--text-tertiary)]">이용목적</dt>
                  <dd>{c.purpose}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="shrink-0 font-semibold text-[var(--text-tertiary)]">보유기간</dt>
                  <dd>{c.retention}</dd>
                </div>
              </dl>
              {c.deny_notice && (
                <p className={`mt-2 pl-6 text-xs ${c.required ? "text-amber-500" : "text-[var(--text-tertiary)]"}`}>
                  {c.deny_notice}
                </p>
              )}
            </div>
          ))}
        </div>

        {!requiredOk && (
          <p className="mt-3 text-xs font-semibold text-amber-500">
            필수 동의에 체크해야 방문 등록이 가능합니다. 동의하지 않으면 개인정보를 수집하지 않습니다.
          </p>
        )}

        <div className="mt-5 flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border border-[var(--line)] py-2.5 text-sm font-bold text-[var(--text-secondary)]"
          >
            취소
          </button>
          <button
            onClick={confirm}
            disabled={!requiredOk}
            className="flex-1 rounded-lg bg-[var(--accent-strong)] py-2.5 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            동의하고 등록
          </button>
        </div>
      </div>
    </div>
  );
}
