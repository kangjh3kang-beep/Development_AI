"use client";

/**
 * 관리자 — 편집 가능 목록 관리.
 * 화면의 고정 드롭다운(현장유형 등)을 관리자가 추가/삭제/수정한다.
 * 백엔드: GET/PUT /api/v1/admin/option-lists/{key}
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { Card, CardContent } from "@propai/ui";

type Item = { value: string; label: string };

// 편집 대상 목록 정의(확장 가능)
const EDITABLE_LISTS: { key: string; title: string; desc: string }[] = [
  { key: "sales_site_types", title: "분양 현장유형", desc: "분양 현장 생성 시 선택하는 유형(아파트·오피스텔·상가 등)" },
];

function ListEditor({ def }: { def: { key: string; title: string; desc: string } }) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    apiClient
      .get<{ items?: Item[] }>(`/admin/option-lists/${def.key}`, { useMock: false })
      .then((r) => setItems(r.items ?? []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [def.key]);

  const update = (i: number, patch: Partial<Item>) =>
    setItems((arr) => arr.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  const remove = (i: number) => setItems((arr) => arr.filter((_, idx) => idx !== i));
  const add = () => setItems((arr) => [...arr, { value: "", label: "" }]);

  const save = useCallback(async () => {
    setSaving(true);
    setMsg("");
    try {
      const clean = items
        .map((it) => ({ value: it.value.trim(), label: it.label.trim() }))
        .filter((it) => it.value && it.label);
      const r = await apiClient.put<{ items: Item[] }>(`/admin/option-lists/${def.key}`, {
        body: { items: clean },
        useMock: false,
      });
      setItems(r.items ?? clean);
      setMsg("저장되었습니다.");
    } catch (e) {
      setMsg(e instanceof ApiClientError ? `저장 실패 (${e.status})` : "저장 실패");
    } finally {
      setSaving(false);
      setTimeout(() => setMsg(""), 2500);
    }
  }, [items, def.key]);

  return (
    <Card className="rounded-2xl">
      <CardContent className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-black text-[var(--text-primary)]">{def.title}</h2>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{def.desc}</p>
          </div>
          <button
            onClick={save}
            disabled={saving || loading}
            className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-[var(--text-hint)]">불러오는 중…</p>
        ) : (
          <div className="mt-4 space-y-2">
            <div className="flex gap-2 px-1 text-[11px] font-bold text-[var(--text-tertiary)]">
              <span className="w-40">코드(value)</span>
              <span className="flex-1">표시명(label)</span>
              <span className="w-8" />
            </div>
            {items.map((it, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={it.value}
                  onChange={(e) => update(i, { value: e.target.value })}
                  placeholder="예: APT"
                  className="w-40 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <input
                  value={it.label}
                  onChange={(e) => update(i, { label: e.target.value })}
                  placeholder="예: 아파트"
                  className="flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <button
                  onClick={() => remove(i)}
                  title="삭제"
                  className="h-9 w-9 shrink-0 rounded-lg border border-rose-500/30 text-rose-500 hover:bg-rose-500/10"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              onClick={add}
              className="mt-1 rounded-xl border border-dashed border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]"
            >
              ＋ 항목 추가
            </button>
          </div>
        )}
        {msg && <p className="mt-3 text-xs font-semibold text-[var(--accent-strong)]">{msg}</p>}
      </CardContent>
    </Card>
  );
}

export default function OptionListsAdminPage() {
  return (
    <div className="space-y-6 p-4 sm:p-8">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">편집 목록 관리</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          화면의 고정 선택목록(드롭다운)을 추가/삭제/수정합니다 (관리자 전용). 저장 즉시 전 사용자에게 반영됩니다.
        </p>
      </div>
      {EDITABLE_LISTS.map((def) => (
        <ListEditor key={def.key} def={def} />
      ))}
    </div>
  );
}
