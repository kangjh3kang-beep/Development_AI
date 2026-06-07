"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";

/** ApiClientError → 사람이 읽는 메시지(백엔드 detail 우선, 상태코드 포함). */
function errText(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    if (e.status === 403) return "관리자만 접근할 수 있습니다.";
    const detail = (e.payload as { detail?: string } | null)?.detail;
    return detail || `${fallback} (${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}

/* ------------------------------------------------------------------ */
/*  서버 연동 — 관리자 API 키 관리(분류별·항목별 + 사용자 임의추가)        */
/*  값은 서버(DB)에 Fernet 암호화 저장, 평문은 절대 내려오지 않음.         */
/* ------------------------------------------------------------------ */

type SecretItem = {
  name: string;
  label: string;
  group: string;
  secret: boolean;
  kind: "text" | "textarea" | "select";
  options?: string[] | null;
  desc?: string | null;
  guide_url?: string | null;
  custom?: boolean;
  is_set: boolean;
  source: "db" | "env" | "none";
  masked: string;
  updated_at?: string | null;
  updated_by?: string | null;
};

type ListResponse = { groups: string[]; items: SecretItem[] };

/* ------------------------------------------------------------------ */
/*  단일 키 카드                                                       */
/* ------------------------------------------------------------------ */

function SecretCard({
  item,
  onSaved,
}: {
  item: SecretItem;
  onSaved: () => void;
}) {
  const [value, setValue] = useState(item.kind === "select" ? (item.masked || "") : "");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<"" | "save" | "del" | "test">("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const canTest = useMemo(
    () =>
      [
        "APICK_CL_AUTH_KEY",
        "REGISTRY_PROVIDER",
        "CODEF_CLIENT_ID",
        "CODEF_CLIENT_SECRET",
        "TILKO_API_KEY",
      ].includes(item.name),
    [item.name],
  );

  const save = useCallback(async () => {
    const v = value.trim();
    if (!v) return;
    setBusy("save");
    setMsg(null);
    try {
      await apiClient.put(`/admin/secrets/${item.name}`, {
        body: { value: v },
      });
      setMsg({ ok: true, text: "저장됨 (즉시 반영)" });
      if (item.kind !== "select") setValue("");
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "저장 실패") });
    } finally {
      setBusy("");
    }
  }, [value, item.name, item.kind, onSaved]);

  const remove = useCallback(async () => {
    if (!confirm(`'${item.label}' 키를 삭제할까요? (.env 원본값이 있으면 복원됩니다)`)) return;
    setBusy("del");
    setMsg(null);
    try {
      await apiClient.delete(`/admin/secrets/${item.name}`);
      setMsg({ ok: true, text: "삭제됨" });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "삭제 실패") });
    } finally {
      setBusy("");
    }
  }, [item.name, item.label, onSaved]);

  const test = useCallback(async () => {
    setBusy("test");
    setMsg(null);
    try {
      const r = await apiClient.post<{ ok: boolean; message: string }>(
        `/admin/secrets/${item.name}/test`,
      );
      setMsg({ ok: !!r.ok, text: r.message || (r.ok ? "연결 성공" : "연결 실패") });
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "테스트 실패") });
    } finally {
      setBusy("");
    }
  }, [item.name]);

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-bold text-[var(--text-primary)]">{item.label}</h4>
              {item.custom && (
                <span className="rounded-md bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                  사용자 추가
                </span>
              )}
              {item.is_set ? (
                <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-bold text-emerald-600">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  설정됨{item.source === "env" ? " (.env)" : ""}
                </span>
              ) : (
                <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-bold text-red-500">
                  미설정
                </span>
              )}
            </div>
            <p className="mt-0.5 font-mono text-[11px] text-[var(--text-tertiary)]">{item.name}</p>
            {item.desc && (
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.desc}</p>
            )}
            {item.is_set && item.masked && item.kind !== "select" && (
              <p className="mt-1 font-mono text-xs text-[var(--text-secondary)]">
                현재값: {item.masked}
              </p>
            )}
          </div>
          {item.guide_url && (
            <a
              href={item.guide_url}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 whitespace-nowrap text-xs font-semibold text-[var(--accent-strong)] hover:underline"
            >
              발급 사이트 ↗
            </a>
          )}
        </div>

        {/* 입력 영역 */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {item.kind === "select" ? (
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
            >
              <option value="">선택…</option>
              {(item.options || []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : item.kind === "textarea" ? (
            <textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={item.is_set ? "새 값 입력 시 교체" : "값 입력"}
              rows={2}
              className="min-w-[260px] flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
            />
          ) : (
            <div className="relative flex-1 min-w-[220px]">
              <input
                type={show ? "text" : "password"}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={item.is_set ? "새 값 입력 시 교체" : "값 입력"}
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 pr-16 text-sm text-[var(--text-primary)]"
              />
              {item.secret && (
                <button
                  type="button"
                  onClick={() => setShow((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] font-semibold text-[var(--text-tertiary)]"
                >
                  {show ? "숨김" : "표시"}
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={save}
            disabled={!value.trim() || busy !== ""}
            className="h-9 whitespace-nowrap rounded-lg bg-[var(--accent-strong)] px-3 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy === "save" ? "저장 중…" : "저장"}
          </button>
          {canTest && (
            <button
              type="button"
              onClick={test}
              disabled={busy !== ""}
              className="h-9 whitespace-nowrap rounded-lg border border-[var(--border)] px-3 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50"
            >
              {busy === "test" ? "확인 중…" : "테스트"}
            </button>
          )}
          {item.is_set && (
            <button
              type="button"
              onClick={remove}
              disabled={busy !== ""}
              className="h-9 whitespace-nowrap rounded-lg border border-red-500/30 px-3 text-sm font-semibold text-red-500 disabled:opacity-50"
            >
              {busy === "del" ? "삭제 중…" : "삭제"}
            </button>
          )}
        </div>

        {msg && (
          <p
            className={`mt-2 text-xs font-semibold ${
              msg.ok ? "text-emerald-600" : "text-red-500"
            }`}
          >
            {msg.text}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  사용자 임의추가 폼                                                 */
/* ------------------------------------------------------------------ */

function AddCustomKey({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [group, setGroup] = useState("");
  const [value, setValue] = useState("");
  const [secret, setSecret] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = useCallback(async () => {
    const n = name.trim().toUpperCase();
    if (!n || !value.trim()) {
      setMsg({ ok: false, text: "키 이름과 값을 입력하세요." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await apiClient.post(`/admin/secrets`, {
        body: {
          name: n,
          value: value.trim(),
          label: label.trim() || undefined,
          group: group.trim() || undefined,
          secret,
        },
      });
      setMsg({ ok: true, text: `'${n}' 추가됨` });
      setName("");
      setLabel("");
      setGroup("");
      setValue("");
      onAdded();
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "추가 실패") });
    } finally {
      setBusy(false);
    }
  }, [name, label, group, value, secret, onAdded]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-xl border border-dashed border-[var(--border)] py-3 text-sm font-semibold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]"
      >
        + 새 API 키 추가 (네임·값 직접 입력)
      </button>
    );
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-[var(--text-primary)]">새 API 키 추가</h4>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-xs text-[var(--text-tertiary)]"
          >
            닫기
          </button>
        </div>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          향후 새 연동에 필요한 키를 코드 수정 없이 추가합니다. 이름은 영대문자·숫자·_ (예:{" "}
          <span className="font-mono">NAVER_MAP_API_KEY</span>). 위험 인프라 키(DB·시크릿키)는
          차단됩니다.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="키 이름 (NAVER_MAP_API_KEY)"
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 font-mono text-sm text-[var(--text-primary)]"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="표시 이름 (선택)"
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
          />
          <input
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            placeholder="분류 (선택, 기본 '사용자 추가')"
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
          />
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="키 값"
            type={secret ? "password" : "text"}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
          />
        </div>
        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={secret}
              onChange={(e) => setSecret(e.target.checked)}
            />
            비밀값(마스킹)
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy ? "추가 중…" : "추가"}
          </button>
        </div>
        {msg && (
          <p
            className={`mt-2 text-xs font-semibold ${
              msg.ok ? "text-emerald-600" : "text-red-500"
            }`}
          >
            {msg.text}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  메인 패널                                                          */
/* ------------------------------------------------------------------ */

export function ApiKeyManagementPanel() {
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiClient.get<ListResponse>(`/admin/secrets`);
      setData(r);
    } catch (e) {
      setError(errText(e, "불러오기 실패"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byGroup = useMemo(() => {
    const m = new Map<string, SecretItem[]>();
    (data?.items || []).forEach((it) => {
      const arr = m.get(it.group) || [];
      arr.push(it);
      m.set(it.group, arr);
    });
    return m;
  }, [data]);

  const setCount = (data?.items || []).filter((i) => i.is_set).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-[var(--text-primary)]">API 키 관리</h2>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            서버에 암호화 저장되며 즉시 반영됩니다(재배포 불필요).{" "}
            {data && (
              <span className="font-semibold text-[var(--text-primary)]">
                {setCount}/{data.items?.length ?? 0} 설정됨
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="h-9 rounded-lg border border-[var(--border)] px-3 text-sm font-semibold text-[var(--text-primary)]"
        >
          새로고침
        </button>
      </div>

      {loading && <p className="text-sm text-[var(--text-secondary)]">불러오는 중…</p>}
      {error && (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm font-semibold text-red-500">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading &&
        !error &&
        (data?.groups || []).map((g) => (
          <section key={g} className="space-y-2">
            <h3 className="text-sm font-bold text-[var(--text-secondary)]">{g}</h3>
            <div className="space-y-2">
              {(byGroup.get(g) || []).map((it) => (
                <SecretCard key={it.name} item={it} onSaved={load} />
              ))}
            </div>
          </section>
        ))}

      {!loading && !error && <AddCustomKey onAdded={load} />}
    </div>
  );
}
