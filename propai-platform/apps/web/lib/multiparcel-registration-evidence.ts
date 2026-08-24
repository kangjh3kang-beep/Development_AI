/**
 * 다필지 **등록 증거** — 활성 상태가 무너져도 살아남는 신호로 "몇 필지로 등록됐나"를 답한다.
 *
 * ## 왜 생겼나 (2026-08-24 · 라이브 수용시험 실패)
 *
 * `#773` 은 *"등록 N필지인데 화면은 단일 필지라고 단언한다"* 를 막으려고 만들었는데,
 * **라이브에서 한 번도 발화하지 않았다.** 실측(프로젝트 `49b59c62` 포항 호미곶 대보리 산 1-1):
 *
 * | 어디 | parcelCount | parcels |
 * |---|---|---|
 * | 서버 프로젝트 레코드 | (name=`"산 1-1 외 1필지"` · total_area_sqm=147,074) | — |
 * | 영속 스냅샷 `snapshots[pid].siteAnalysis` | **2** | **2개** |
 * | ★활성 슬라이스 `state.siteAnalysis`(화면이 읽는 것) | **0** | **[]** |
 *
 * `#773` 의 조건은 활성 슬라이스의 `parcelCount` 를 봤다. 그런데 **그 필드가 바로
 * 결함이 무너뜨리는 값**이다 — 즉 **탐지기가 결함이 파괴하는 신호를 입력으로 썼다.**
 * 그러면 **결함이 클수록 탐지기가 더 조용해진다**(0 이 되어 조건이 거짓).
 *
 * ★이 저장소가 반복해 데인 *"검증이 실제 대상을 태우지 않는다"* 의 **탐지기 버전**이다.
 *   `#773` 의 계약테스트 4케이스는 픽스처에 `parcelCount` 를 **손으로 넣어** 통과했으므로,
 *   **라이브가 실제로 주는 모양(0으로 붕괴)을 한 번도 안 태웠다.**
 *
 * ## 무엇을 하나
 *
 * 활성·스냅샷 **양쪽의 모든 신호 중 가장 큰 값**을 등록 증거로 삼는다.
 * 어느 한쪽이 0으로 무너져도 **다른 쪽이 살아 있으면 다필지였음을 안다.**
 * 근거가 어디서 왔는지(`source`)도 함께 돌려준다 — 화면이 **근거를 밝히고** 말하도록.
 *
 * ## 하지 않는 것
 *
 * · **고치지 않는다.** 활성 슬라이스가 스냅샷을 0 으로 덮는 **하이드레이션 근본**은
 *   스토어 쪽(`#779` 자가치유 · `#781` 단계 판정)의 영역이다. 여기서는 **읽기만** 한다.
 *   근본이 고쳐지면 활성 슬라이스가 정상값을 갖고 이 헬퍼는 같은 답을 낸다 — **전방호환.**
 * · **`lib/site-area.ts` 와 경쟁하지 않는다.** 그쪽(`#778`)은 *"몇 필지인가"* 판정을
 *   통일하는 축이고, 이 파일은 *"붕괴 이전의 증거가 남아 있는가"* 라는 **다른 질문**이다.
 *   ★`#778` 이 착지하면 **이 헬퍼를 그쪽으로 접는 것을 검토하라** — 말없이 갈라지면
 *   판정이 또 한 벌 늘어난다(그 파일 한 곳에만 이미 3벌이 있었다).
 */

/** 필지 신호를 가진 것이면 무엇이든(스토어 타입에 결속하지 않는다 — 테스트가 직접 태우도록). */
export interface ParcelSignals {
  parcelCount?: number | null;
  parcels?: readonly unknown[] | null;
}

/**
 * ★변이 검증 주석 — 이 인터페이스의 `source` 줄은 **vitest 변이에서 생존**한다(2건).
 *   타입 선언이라 런타임에 없기 때문이고, **잠금은 `tsc` 다** — 실측: 그 줄을 지우면
 *   `TS2339`/`TS2353` 로 EXIT=2 다. 구멍이 아니라 **다른 게이트가 잡는 것**이라 적어 둔다
 *   (설명 없는 생존만 진짜 구멍이다 — 변이 점수 부풀리기 방지).
 */
export interface RegistrationEvidence {
  /** 붕괴를 견딘 증거로 본 등록 필지 수. 증거가 없으면 `null`(0 이 아니다 — 0 은 거짓 사실이다). */
  registeredCount: number | null;
  /** 그 값의 출처. 화면이 근거를 밝히도록. 증거가 없으면 `null`. */
  source: "active" | "snapshot" | null;
}

/** 한 신호원에서 읽을 수 있는 최대 필지 수(못 읽으면 0). */
function countOf(s: ParcelSignals | null | undefined): number {
  if (!s) return 0;
  const n = typeof s.parcelCount === "number" && Number.isFinite(s.parcelCount) ? s.parcelCount : 0;
  const len = Array.isArray(s.parcels) ? s.parcels.length : 0;
  return Math.max(n > 0 ? n : 0, len);
}

/**
 * 활성 상태와 영속 스냅샷을 함께 보고 **등록 필지 수**를 정한다.
 *
 * ★활성이 스냅샷보다 크거나 같으면 활성을 쓴다(사용자가 방금 줄인 선택이 스냅샷보다 최신이다).
 *   스냅샷이 더 크면 **활성이 무너진 것**으로 보고 스냅샷을 쓴다 — 이게 이 함수의 존재 이유다.
 */
export function resolveRegistrationEvidence(
  active: ParcelSignals | null | undefined,
  snapshot: ParcelSignals | null | undefined,
): RegistrationEvidence {
  const a = countOf(active);
  const s = countOf(snapshot);
  if (a === 0 && s === 0) return { registeredCount: null, source: null };
  return a >= s ? { registeredCount: a, source: "active" } : { registeredCount: s, source: "snapshot" };
}

/**
 * **거짓 단언을 막아야 하는가** — 등록 증거는 다필지인데 화면이 그리는 필지가 2개 미만.
 *
 * ★`isMulti` 는 화면이 **실제로 그릴 수 있는** 필지 수에서 온다(주소 목록).
 *   등록 증거가 그보다 크면 *"단일 필지입니다"* 는 **거짓**이므로 단언 대신 사실을 말한다.
 */
export function shouldSuppressSingleParcelClaim(
  evidence: RegistrationEvidence,
  isMulti: boolean,
): boolean {
  return !isMulti && (evidence.registeredCount ?? 0) > 1;
}
