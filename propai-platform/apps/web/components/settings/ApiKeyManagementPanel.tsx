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

/**
 * **전용 연결 테스트**가 구현된 키들 — 이 목록에 없으면 「테스트」 버튼을 그리지 않는다.
 *
 * ★원천은 백엔드 `apps/api/app/routers/admin_secrets.py` 의 `_TESTABLE_SECRETS` 이고,
 * 그것은 **분기 셋에서 파생**된다(등기 · LLM · 이미지). 손 목록이 아니다.
 *   종전엔 양쪽이 **각각 인라인 손목록**을 들고 있었고 **대조 락이 0건**이었다.
 *   갈리면 이렇게 된다:
 *     · 백엔드만 추가 → 화면에 버튼이 **안 뜬다**(기능이 있는데 닿지 않는다)
 *     · 프론트만 추가 → 백엔드가 **「미지원」**을 돌려주고, 예전엔 그게 **`ok: true`** 였다
 *   → `apps/api/tests/test_secret_test_honesty.py` 가 `ast` 로 양쪽을 파싱해 대조한다.
 *
 * ★모듈 상수로 둔 이유: 컴포넌트 안 인라인 배열은 **기계가 파생시킬 수 없다**.
 */
const TESTABLE_SECRETS: readonly string[] = [
  // 등기(registry) — `RegistryService.live_status()` 실호출
  "HYPHEN_HKEY",
  "HYPHEN_USER_ID",
  "REGISTRY_PROVIDER",
  "TILKO_API_KEY",
  // ★LLM/이미지 — `#899` 가 **백엔드에 실호출 테스트를 넣었는데 여기에 안 더해서**
  //   그 테스트를 **사용자가 영영 쓸 수 없었다**(2026-09-02 실측: 백엔드 7키 ↔ 화면 4키).
  //   그것이 이 상수를 백엔드와 대조하는 락을 만든 이유다.
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "GOOGLE_API_KEY",
];

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
  // ★3상태다 — 「성공/실패」 2상태로 두면 **보류를 표현할 자리가 없어** 빨강으로 떨어진다.
  const [msg, setMsg] = useState<{ tone: "ok" | "fail" | "withheld"; text: string } | null>(null);

  const canTest = useMemo(() => TESTABLE_SECRETS.includes(item.name), [item.name]);

  const save = useCallback(async () => {
    const v = value.trim();
    if (!v) return;
    setBusy("save");
    setMsg(null);
    try {
      await apiClient.put(`/admin/secrets/${item.name}`, {
        body: { value: v },
      });
      setMsg({ tone: "ok", text: "저장됨 (즉시 반영)" });
      if (item.kind !== "select") setValue("");
      onSaved();
    } catch (e) {
      setMsg({ tone: "fail", text: errText(e, "저장 실패") });
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
      setMsg({ tone: "ok", text: "삭제됨" });
      onSaved();
    } catch (e) {
      setMsg({ tone: "fail", text: errText(e, "삭제 실패") });
    } finally {
      setBusy("");
    }
  }, [item.name, item.label, onSaved]);

  const test = useCallback(async () => {
    setBusy("test");
    setMsg(null);
    try {
      // ★`ok` 는 **`boolean | null`** 이다 — `null` 은 **보류**(전용 테스트가 없음)이지
      //   실패가 아니다. 종전엔 타입이 `boolean` 이라 `!!null === false` 로 **빨강**이 됐다:
      //   거짓 초록을 고치고 **거짓 빨강**을 얻는 자리였다(독립 리뷰 MEDIUM-2).
      //   ★타입을 정직하게 적어 두면 다음 사람이 `!!r.ok` 자리에서 **tsc 에 걸린다.**
      const r = await apiClient.post<{
        ok: boolean | null;
        message: string;
        ok_absent?: string;
      }>(`/admin/secrets/${item.name}/test`);
      setMsg(
        r.ok === null || r.ok === undefined
          ? { tone: "withheld", text: r.message || "확인할 수 없습니다" }
          : { tone: r.ok ? "ok" : "fail", text: r.message || (r.ok ? "연결 성공" : "연결 실패") },
      );
    } catch (e) {
      setMsg({ tone: "fail", text: errText(e, "테스트 실패") });
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
                /* ★**존재를 「정상」으로 그리지 않는다.**
                   `is_set` 은 `bool(cur) or in_db`(secret_store.py) — **값이 있다**는 뜻일 뿐
                   연결을 확인한 것이 아니다. 종전엔 이것을 `--status-success`(초록 점 포함)로
                   그려서 관리자가 **「정상 연결됨」으로 읽었다**.
                   ★이 화면에서 실제로 연결을 확인하는 키는 4개뿐이고(테스트 버튼이 그 넷에만
                   렌더된다) 나머지 55개에 대해 관리자가 보는 초록은 **바로 이 배지**였다.
                   → 중립색으로 내린다. 초록은 **확인된 것**에만 쓴다. */
                <span
                  className="flex items-center gap-1 rounded-full bg-[var(--text-secondary)]/10 px-2 py-0.5 text-[11px] font-bold text-[var(--text-secondary)]"
                  title="값이 저장돼 있다는 뜻입니다. 연결·인증을 확인한 것은 아닙니다."
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-secondary)]" />
                  설정됨{item.source === "env" ? " (.env)" : ""}
                </span>
              ) : (
                <span className="rounded-full bg-[var(--status-error)]/10 px-2 py-0.5 text-[11px] font-bold text-[var(--status-error)]">
                  미설정
                </span>
              )}
            </div>
            <p className="cc-num mt-0.5 text-[11px] text-[var(--text-tertiary)]">{item.name}</p>
            {item.desc && (
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.desc}</p>
            )}
            {item.is_set && item.masked && item.kind !== "select" && (
              <p className="cc-num mt-1 text-xs text-[var(--text-secondary)] break-all max-w-full">
                현재값: {item.masked}
              </p>
            )}
          </div>
          {item.guide_url && (
            <a
              href={item.guide_url}
              target="_blank"
              rel="noopener noreferrer"
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
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
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
              className="min-w-[260px] flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
            />
          ) : (
            <div className="relative flex-1 min-w-[220px]">
              <input
                type={show ? "text" : "password"}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={item.is_set ? "새 값 입력 시 교체" : "값 입력"}
                className="h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 pr-16 text-sm text-[var(--text-primary)]"
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
              className="h-9 whitespace-nowrap rounded-lg border border-[var(--line)] px-3 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50"
            >
              {busy === "test" ? "확인 중…" : "테스트"}
            </button>
          )}
          {item.is_set && (
            <button
              type="button"
              onClick={remove}
              disabled={busy !== ""}
              className="h-9 whitespace-nowrap rounded-lg border border-[var(--status-error)]/30 px-3 text-sm font-semibold text-[var(--status-error)] disabled:opacity-50"
            >
              {busy === "del" ? "삭제 중…" : "삭제"}
            </button>
          )}
        </div>

        {msg && (
          <p
            className={`mt-2 text-xs font-semibold ${
              msg.tone === "ok"
                ? "text-[var(--status-success)]"
                : msg.tone === "withheld"
                  ? "text-[var(--text-secondary)]"
                  : "text-[var(--status-error)]"
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
  // ★3상태다 — 「성공/실패」 2상태로 두면 **보류를 표현할 자리가 없어** 빨강으로 떨어진다.
  const [msg, setMsg] = useState<{ tone: "ok" | "fail" | "withheld"; text: string } | null>(null);

  const submit = useCallback(async () => {
    const n = name.trim().toUpperCase();
    if (!n || !value.trim()) {
      setMsg({ tone: "fail", text: "키 이름과 값을 입력하세요." });
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
      setMsg({ tone: "ok", text: `'${n}' 추가됨` });
      setName("");
      setLabel("");
      setGroup("");
      setValue("");
      onAdded();
    } catch (e) {
      setMsg({ tone: "fail", text: errText(e, "추가 실패") });
    } finally {
      setBusy(false);
    }
  }, [name, label, group, value, secret, onAdded]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-xl border border-dashed border-[var(--line)] py-3 text-sm font-semibold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]"
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
            className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 font-mono text-sm text-[var(--text-primary)]"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="표시 이름 (선택)"
            className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
          />
          <input
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            placeholder="분류 (선택, 기본 '사용자 추가')"
            className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
          />
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="키 값"
            type={secret ? "password" : "text"}
            className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]"
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
              msg.tone === "ok"
                ? "text-[var(--status-success)]"
                : msg.tone === "withheld"
                  ? "text-[var(--text-secondary)]"
                  : "text-[var(--status-error)]"
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
          <span className="cc-meta">CREDENTIALS · ENCRYPTED VAULT</span>
          <h2 className="text-lg font-bold text-[var(--text-primary)] mt-1">API 키 관리</h2>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            서버에 암호화 저장되며 즉시 반영됩니다(재배포 불필요).{" "}
            {data && (
              <span className="cc-num font-semibold text-[var(--text-primary)]">
                {setCount}/{data.items?.length ?? 0} 설정됨
              </span>
            )}
            {data && (
              /* ★「설정됨」이 무엇을 뜻하는지 화면이 스스로 말한다 —
                 색만 내리면 다음 사람이 다시 초록으로 올린다. */
              <span className="block text-[11px] text-[var(--text-tertiary)]">
                「설정됨」은 값이 저장돼 있다는 뜻이며, 연결·인증을 확인한 것이 아닙니다.
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="h-9 rounded-lg border border-[var(--line)] px-3 text-sm font-semibold text-[var(--text-primary)]"
        >
          새로고침
        </button>
      </div>

      {loading && <p className="text-sm text-[var(--text-secondary)]">불러오는 중…</p>}
      {error && (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm font-semibold text-[var(--status-error)]">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading &&
        !error &&
        (data?.groups || []).map((g) => (
          <section key={g} className="space-y-2">
            <h3 className="cc-label text-[var(--text-secondary)]">{g}</h3>
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
