/**
 * 전제 감사(`premise_audit`) 고지 — **공용 렌더러**.
 *
 * ## 왜 생겼나 (2026-09-04)
 *
 * 백엔드에 **변형관계 레지스트리**(`app/services/zoning/premise_audit.py`)가 있고 **두 표면**이
 * 그 결과를 응답에 싣는다:
 *
 *     services/development/scenario_simulator.py   개발방식 시뮬레이터  (#963 이 배선)
 *     routers/auto_zoning.py                        통합분석
 *
 * ★그런데 **프론트 소비처가 0** 이었다(실측 2026-09-04 · 대조군: 카드가 최상위에서 읽는 키 12종).
 *   `#963` 커밋 본문이 *"`#940` 에서 «백엔드 계약만 서고 화면 소비처 0» 으로 데였으므로 여기
 *   싣는 것만으로 끝내지 않는다 — **소비처는 별도 좌표로 남긴다**"* 라고 적었고, 여기가 그 좌표다.
 *
 * ## ★왜 형제 `IntegrityWarnings` 를 재사용하지 않는가
 *
 * 정신은 같다(공용 · 무날조 · 백엔드 문구 그대로). 그러나 **계약이 다르고**, 결정적으로
 * 그 컴포넌트의 독스트링은 이렇게 **명시적으로 한 축을 포기**한다:
 *
 *   > *"배열이 비면 아무것도 그리지 않는다 — «이상 없음»이라고 단언하지도 않는다
 *   >   (가드가 돌지 않았을 수도 있으므로 **침묵과 무결을 구분해 주장하지 않는다**)."*
 *
 * ★**`premise_audit` 은 그 정보를 가진다** — `checked`(실제로 판정한 관계 수)와
 *   `registered`(등록 수)를 함께 낸다. 그래서 **침묵과 무결을 구분할 수 있다.**
 *   같은 컴포넌트에 밀어 넣으면 **그 축이 사라진다.** 그래서 형제로 따로 둔다.
 *
 * ★감사 모듈 자신이 그것을 명문으로 요구한다:
 *   > *"`checked == 0` 이면 «위반 없음»이 **공허**하다 — 호출부가 그 사실을 알 수 있어야 한다."*
 *
 * ## 그리는 상태 — **네 갈래**(뭉치면 정보가 0이 된다)
 *
 *     위반      violations.length > 0        → 관계별 title + detail (백엔드 원문)
 *     판정불가  reason === "audit_failed"    → **왜** 못 했는지. 침묵하지 않는다
 *     공허      판정력 === 0                 → «검사를 돌리지 못했습니다». «위반 없음» 이라 하지 않는다
 *     부분      0 < 판정력 < registered      → «N/M 만 판정» + 왜 나머지가 빠졌는지
 *
 * ★**전부 판정 + 위반 0 이면 아무것도 그리지 않는다** — 정상 화면에 배지를 늘리지 않는다.
 *
 * ## ★★적대 리뷰가 잡은 것 — **내가 모듈 독스트링을 믿고 그 위에 축을 세웠다**
 *
 * 첫 판은 `checked` 를 **「판정한 관계 수」** 로 읽었다. 모듈 독스트링이 그렇게 적었기 때문이다:
 *   > *"`checked` : 실제로 판정한 관계 수(**전제 부족으로 건너뛴 것은 제외**)"*
 *
 * ★**구현이 그렇지 않다.** `audit()` 의 `checked += 1` 은 **무조건** 실행된다(예외가 난
 *   관계만 빠진다). 직접 태워서 확인했다(`origin/main` 참조 트리):
 *
 *       audit(정상ctx) → checked 6 / registered 6
 *       audit({})      → checked 6 / registered 6      ← 빈 입력에도 6
 *       audit(쓰레기)   → checked 6 / registered 6
 *
 *   그리고 관계들은 **「전제 부족」과 「위반 없음」을 같은 `None`** 으로 반환한다
 *   (`if got is None or want is None or got == want: return None` — 한 분기에 뭉쳐 있다).
 *   즉 **「건너뜀」이라는 정보가 원리적으로 존재하지 않는다.**
 *
 * ★★**그런데 저장소의 기존 락이 진짜 계약을 적어 뒀다** —
 *   `tests/test_premise_audit_registry.py:85·88`:
 *   > `assert empty["checked"] == empty["registered"], "빈 입력도 **판정은 시도**해야 한다"`
 *
 *   즉 `checked` 는 **「시도한 수」**다. 그러므로 `checked < registered` 의 뜻은
 *   **「관계가 실행 중 예외로 죽었다」**이지 「입력이 부족했다」가 아니다.
 *
 * ★**내가 치른 값**: 첫 판이 `effective = checked - vacuous` 를 `registered` 와 비교해
 *   **모든 정상 부지**가 *"부분 판정 5/6 — 나머지는 **입력이 부족해** 건너뛰었습니다"* 를 받았다.
 *   **숫자도 사유도 거짓**이었고, `clean`(무렌더)은 **도달 불가**였다 — *"정상 화면에 배지를
 *   늘리지 않는다"* 를 설계 중심에 놓고 **정상 화면에만 배지를 띄우고 있었다.**
 *
 * ★교훈: ***선언(독스트링)과 잠금(테스트)이 갈리면 **잠금이 사실**이다.***
 *   잘 쓰인 설계 문서일수록 그 문장이 결론처럼 읽혀 아무도 다시 재지 않는다.
 *
 * ## ★`structurally_vacuous` — **별개 축**이다(비율에 섞지 않는다)
 *
 * `#963` 이 시뮬레이터 경로에서 `path_invariance_zone` 을 `structurally_vacuous` 로 표시한다
 * (집계와 시나리오가 **같은 `primary_zone`** 에서 나와 자기 자신과 비교 → 판별력 0).
 *
 * ★**그것을 `checked/registered` 비율에 섞지 않는다.** 두 축이 다르기 때문이다:
 *   · `checked / registered` — **감사기가 살아서 돌았는가**(시도율)
 *   · `structurally_vacuous` — **그중 판별력이 없는 관계가 무엇인가**
 *   섞으면 «감사기가 죽었다» 와 «관계 하나가 이 경로에선 무의미하다» 가 같은 숫자가 된다.
 *
 * ★그래서 **경보를 만들지 않는다** — 이미 상자를 띄운 상태에서 **맥락**으로만 밝힌다.
 *   정상 부지에 «판별력 1건 없음» 배지를 상시로 띄우면 그것 자체가 소음이고,
 *   이 저장소가 기록한 *"위양성 피로"* 가 정확한 보고까지 죽인다.
 *
 * ## 무날조
 *
 * 백엔드가 준 `title`·`detail`·`reason` 을 **그대로** 싣는다. 프론트가 문구를 지어내지 않고,
 * 값을 보정하지도 않는다(모듈 설계가 *"자동 교정은 어느 쪽이 옳은지 단정하는 것이고, 그 단정이
 * 틀리면 **더 조용한 결함**이 된다"* 로 기각한 접근이다).
 */
"use client";

export type PremiseViolation = {
  /** 관계 키(예: `dominant_argmax`). 기계축 — 화면은 `title` 을 쓴다. */
  relation?: string | null;
  /** 사람이 읽는 관계 이름 — 백엔드 원문. */
  title?: string | null;
  /** 무엇이 어긋났는지 — 백엔드 원문. */
  detail?: string | null;
  /** 기계가 읽는 근거(값 쌍). 화면은 지금 안 쓴다(오독 위험 > 이득). */
  evidence?: Record<string, unknown> | null;
};

export type PremiseAudit = {
  violations?: PremiseViolation[] | null;
  /** 실제로 판정한 관계 수. ★`0` 이면 「위반 없음」이 **공허**하다. */
  checked?: number | null;
  /** 등록된 관계 수. 실패 경로에서는 `null` 이다. */
  registered?: number | null;
  /** 이 경로에서 **원리적으로 아무것도 못 가르는** 관계 키들. */
  structurally_vacuous?: string[] | null;
  /** 감사기 자체가 죽었을 때만 채워진다(성공 경로에는 없다). */
  reason?: string | null;
  detail?: string | null;
};

/** 화면이 판정할 상태. ★`"clean"` 은 **아무것도 안 그린다**(정상에 배지를 늘리지 않는다). */
export type PremiseAuditState = "violations" | "failed" | "vacuous" | "partial" | "clean";

/**
 * ★상태 판정을 **렌더에서 분리**한다 — 락이 문구가 아니라 **상태**를 태울 수 있어야 한다.
 *
 * 순서가 계약이다: 실패 → 위반 → 공허 → 부분 → 깨끗.
 * ★「실패」를 먼저 보는 이유: 실패 경로는 `violations: []`·`checked: 0` 이라, 뒤로 미루면
 *   **「공허」로 오분류**되어 *"검사를 못 돌렸다"* 는 **왜 못 돌렸는지를 잃는다.**
 */
export function premiseAuditState(a: PremiseAudit | null | undefined): PremiseAuditState {
  if (!a || typeof a !== "object" || Array.isArray(a)) return "clean";
  // ★위반은 **형태 해석보다 먼저** 본다. 첫 판은 형태 가드를 앞에 뒀는데, 그러면
  //   `checked` 가 빠진 페이로드에서 **진짜 위반이 조용히 사라진다**(적대 리뷰 MEDIUM-4).
  //   위반은 그 자체로 자기를 증명한다 — 세는 축이 없어도 「어긋났다」는 사실은 유효하다.
  const violations = Array.isArray(a.violations) ? a.violations.filter(Boolean) : [];
  if (violations.length > 0) return "violations";
  if (a.reason) return "failed";
  // ★여기부터는 **수를 해석**한다 — 그러니 수가 없으면 아무 주장도 하지 않는다.
  //   백엔드는 성공·실패 **양쪽 모두** `checked` 를 싣는다(실패 경로도 `checked: 0`).
  if (!Number.isFinite(a.checked)) return "clean";
  const checked = Number(a.checked);
  // ★`checked` 는 **「시도한 수」**다(기존 락: *"빈 입력도 판정은 시도해야 한다"*).
  //   그러므로 0 은 «감사기를 한 건도 실행하지 못했다», 미달은 «관계가 실행 중 죽었다» 다.
  //   ★「입력이 부족해 건너뛰었다」가 **아니다** — 그 정보는 생산자에 존재하지 않는다.
  if (checked === 0) return "vacuous";
  const registered = Number.isFinite(a.registered) ? Number(a.registered) : null;
  if (registered != null && checked < registered) return "partial";
  return "clean";
}

/**
 * 감사 수행 상태를 **두 축으로 분리**해 돌려준다.
 *
 * ★첫 판은 `effective = checked - vacuous` 라는 **한 수**로 뭉갰고, 그것을 `registered` 와
 *   비교했다 — **기준이 다른 두 수의 비교**였고 정상 부지가 전부 경고를 받았다.
 *   두 축은 서로 다른 질문에 답한다:
 *     · `attempted / registered` — **감사기가 살아서 돌았는가**
 *     · `vacuous`                 — 그중 **이 경로에서 판별력이 없는** 관계 수
 */
export function premiseAuditPower(a: PremiseAudit | null | undefined): {
  attempted: number;
  registered: number | null;
  vacuous: number;
  vacuousKeys: string[];
} {
  const attempted = Number.isFinite(a?.checked) ? Number(a?.checked) : 0;
  const vacuousKeys = Array.isArray(a?.structurally_vacuous)
    ? a!.structurally_vacuous!.filter((k): k is string => typeof k === "string" && k.length > 0)
    : [];
  const registered = Number.isFinite(a?.registered) ? Number(a?.registered) : null;
  return { attempted, registered, vacuous: vacuousKeys.length, vacuousKeys };
}

export function PremiseAuditNotice({
  audit,
  className = "",
}: {
  audit: PremiseAudit | null | undefined;
  className?: string;
}) {
  const state = premiseAuditState(audit);
  if (state === "clean") return null;

  const { attempted, registered, vacuous, vacuousKeys } = premiseAuditPower(audit);
  const violations = Array.isArray(audit?.violations) ? audit!.violations!.filter(Boolean) : [];
  const isError = state === "violations";

  // ★네 상태가 **서로 다른 말**을 한다. 두 갈래가 같은 문구를 쓰면 사용자가 얻는 정보가 0이다.
  const heading =
    state === "violations" ? `전제 불일치 검출 · ${violations.length}건`
    : state === "failed" ? "전제 감사를 수행하지 못했습니다"
    : state === "vacuous" ? "전제 감사를 한 건도 실행하지 못했습니다"
    // ★「부분 판정」이 아니라 **「부분 실행」**이다 — 미달의 뜻은 «관계가 실행 중 죽었다» 이지
    //   «입력이 부족했다» 가 아니다(그 정보는 생산자에 없다).
    : `전제 감사 부분 실행 · ${attempted}/${registered ?? "?"}`;

  // ★Tailwind 클래스를 **문자열 보간으로 만들지 않는다.** JIT 는 소스를 정적으로 훑어
  //   클래스를 생성하므로 `text-[${tone}]` 같은 런타임 조합은 **CSS 가 아예 생성되지 않는다**
  //   (형제 `IntegrityWarnings` 도 정적 문자열만 쓴다 — 그 이유다).
  //   두 톤을 **완성된 리터럴 두 벌**로 둔다.
  const shell = isError
    ? "border-[color-mix(in_srgb,var(--status-error)_35%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_8%,transparent)]"
    : "border-[color-mix(in_srgb,var(--status-warning)_35%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)]";
  const headTone = isError ? "text-[var(--status-error)]" : "text-[var(--status-warning)]";

  return (
    <div
      data-testid="premise-audit-notice"
      data-state={state}
      className={`rounded-lg border p-2.5 ${shell} ${className}`}
    >
      <p className={`mb-1 text-[10px] font-black uppercase tracking-widest ${headTone}`}>
        {heading}
      </p>

      {state === "violations" && (
        <ul className="space-y-1">
          {violations.map((v, i) => (
            <li key={`premise-${v.relation ?? i}`} className="text-[10px] leading-relaxed text-[var(--text-secondary)]">
              {/* ★백엔드 원문 그대로 — 화면이 문구를 지어내지 않는다. */}
              <span className="font-bold text-[var(--status-error)]">{v.title || v.relation || "전제 불일치"}</span>
              {v.detail ? <span> — {v.detail}</span> : null}
            </li>
          ))}
        </ul>
      )}

      {state === "failed" && (
        /* ★**왜** 못 했는지를 싣는다 — 무언 실패 금지(진단 불가는 그 자체로 장애다). */
        <p className="text-[10px] leading-relaxed text-[var(--text-secondary)]">
          {/* ★기계 키(`audit_failed`)를 사용자에게 그대로 내보내지 않는다. 백엔드는
              `detail: str(e)[:200]` 인데 `str(e)` 는 **빈 문자열일 수 있다**(`raise ValueError()`).
              그때 첫 판은 «audit_failed» 를 화면에 찍었다 — *"왜 못 했는지를 싣는다"* 는
              목적이 그 순간 무너진다(적대 리뷰 MINOR-6). */}
          {(audit?.detail || "").trim() || "원인을 기록하지 못했습니다 — 서버 로그를 확인하십시오."}
        </p>
      )}

      {state === "vacuous" && (
        /* ★**「위반 없음」이라고 말하지 않는다.** 감사 모듈이 명문으로 요구한 축이다. */
        <p className="text-[10px] leading-relaxed text-[var(--text-secondary)]">
          아래 판정을 교차검증할 전제 검사가 하나도 실행되지 않았습니다 — 「이상 없음」이 아니라
          「확인하지 못함」입니다.
        </p>
      )}

      {state === "partial" && (
        /* ★실효 판정력과 원래 `checked` 를 **둘 다** 싣는다 — 한 수로 뭉개면 오독된다. */
        <p className="text-[10px] leading-relaxed text-[var(--text-secondary)]">
          등록된 {registered}개 전제 검사 중 {attempted}개만 실행됐습니다 — 나머지는 실행 중
          오류로 중단됐습니다. 위반 0이 전체를 보증하지 않습니다.
        </p>
      )}

      {/* ★판별력 없는 관계는 **경보가 아니라 맥락**이다 — 상자가 이미 떠 있을 때만 밝힌다.
          정상 부지에 상시로 띄우면 그것 자체가 소음이고, 위양성 피로가 정확한 보고까지 죽인다.
          ★그리고 이것을 `checked/registered` 비율에 **섞지 않는다** — 두 축이 다른 질문에 답한다. */}
      {vacuous > 0 && (
        <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
          참고 — 이 경로에서 판별력이 없는 검사 {vacuous}건({vacuousKeys.join(", ")})은 위 수에
          포함돼 있으나 결과를 가르지 못합니다.
        </p>
      )}
      {/* ★값을 몰래 고치지 않는다 — 설계가 자동 교정을 기각했다(틀린 단정은 더 조용한 결함이 된다). */}
      <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
        위 판정값은 보정하지 않고 그대로 표시합니다.
      </p>
    </div>
  );
}
