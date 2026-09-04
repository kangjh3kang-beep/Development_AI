/**
 * 과금 경로 재전송 안전 키 — **호출부마다 따로 만들지 않는다.**
 *
 * ## 왜 공용인가
 *
 * 백엔드는 `charge_once` 가드로 과금 경로 전부를 감쌌지만, **프론트가 키를 보내야 보호가 켜진다.**
 * 처음엔 `RegistryBulkButton` 하나만 `useRef` 로 직접 키를 관리했는데, 그 방식을 호출부마다
 * 복사하면 규칙이 갈라진다 — 어떤 곳은 목록이 바뀌어도 키를 안 갈고(→ 백엔드가 **422**),
 * 어떤 곳은 매번 새 키를 만든다(→ 보호 **0**). 둘 다 조용히 잘못된다.
 *
 * ## 계약 (백엔드 `app/core/charge_idempotency.py` 와 짝)
 *
 * - **같은 요청이면 같은 키** → 재전송해도 두 번 청구되지 않는다(정산 상태에서 과금만 스킵).
 * - **다른 요청이면 다른 키** → 같은 키를 다른 바디에 쓰면 백엔드가 **422** 로 거절한다.
 * - 처리 중 같은 키가 또 오면 **409** — 동시 이중청구를 선점으로 막는다.
 *
 * 그래서 키를 **(스코프 + 요청 내용의 지문)** 에서 파생한다. 같은 화면에서 같은 값으로 다시
 * 누르면 같은 키가 나오고, 값이 바뀌면 자동으로 새 키가 나온다 — 호출부가 신경 쓸 게 없다.
 *
 * ★세션(탭) 범위 메모리다. 새로고침하면 키가 새로 나는데, 그건 **의도**다:
 *   백엔드 정산 기록에 TTL(24h)이 있어 무한 무료가 되지 않아야 하고, 새로고침은 사용자가
 *   "다시 하겠다"는 신호로 보는 것이 안전한 쪽(과소청구보다 과대청구 위험이 낮은 쪽)이다.
 */

/** 스코프+지문 → 키. 같은 입력이면 같은 키가 나온다. */
const _keys = new Map<string, string>();

/** 무한 증식 방지 — 한 탭에서 이만큼 넘게 서로 다른 요청을 만들 일은 없다. */
const _MAX_KEYS = 500;

function _uuid(): string {
  // crypto.randomUUID 는 보안 컨텍스트에서만 보장된다 — 없으면 충분히 흩어지는 폴백.
  const c = typeof crypto !== "undefined" ? crypto : undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/**
 * 요청 내용의 안정적인 지문.
 * ★키 순서에 흔들리지 않게 정렬한다 — 같은 논리 요청이 다른 지문을 내면 새 키가 나고
 *   보호가 조용히 꺼진다(백엔드 `compute_request_hash` 도 키 순서를 정규화한다).
 */
function _fingerprint(payload: unknown): string {
  const norm = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(norm);
    if (v && typeof v === "object") {
      return Object.keys(v as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, k) => {
          acc[k] = norm((v as Record<string, unknown>)[k]);
          return acc;
        }, {});
    }
    return v;
  };
  try {
    return JSON.stringify(norm(payload));
  } catch {
    // 순환참조 등 — 지문을 못 만들면 **키를 재사용하지 않는다**(422 를 내느니 보호를 포기).
    return `__unstable__${_uuid()}`;
  }
}

/**
 * 과금 요청에 붙일 헤더. `apiClient.post(..., { headers: idempotencyHeaders(scope, body) })`
 *
 * @param scope 엔드포인트 논리명(예: `"registry.bulk"`). **경로마다 달라야** 키 공간이 안 섞인다.
 * @param payload 실제로 보낼 바디. 이 값이 바뀌면 키도 바뀐다.
 */
export function idempotencyHeaders(scope: string, payload: unknown): Record<string, string> {
  const sig = `${scope}|${_fingerprint(payload)}`;
  let key = _keys.get(sig);
  if (!key) {
    if (_keys.size >= _MAX_KEYS) _keys.clear();
    key = _uuid();
    _keys.set(sig, key);
  }
  return { "Idempotency-Key": key };
}

/** 테스트·명시적 재시도용 — 그 스코프의 키를 버려 다음 호출이 새 키를 쓰게 한다. */
export function resetIdempotencyScope(scope: string): void {
  for (const k of Array.from(_keys.keys())) {
    if (k.startsWith(`${scope}|`)) _keys.delete(k);
  }
}
