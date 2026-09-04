/**
 * 프로젝트 생성 멱등키 SSOT — **하나의 생성 시도 = 하나의 키.**
 *
 * ## 무엇을 막는가
 *
 * 같은 프로젝트를 두 번 POST 하는 경로가 실측으로 둘 있었다:
 *
 *  - `#815` — 생성 `await` 창에 동기화가 끼어들어 "고아"로 오판(같은 탭 안에서만 막았다)
 *  - `#822` — 목록이 20건에서 잘려 **이미 있는 프로젝트를 "백엔드에 없다"고 오판**
 *
 * 둘 다 클라이언트 처방이라 **다른 탭·다른 기기·재설치**에는 닿지 않는다.
 * 서버가 키를 기억하면 그 경로가 전부 닫힌다(`POST /projects` 가 `Idempotency-Key` 를 읽는다).
 *
 * ## ★키를 무엇으로 만드나 — 내용이 아니라 **시도**로 만든다
 *
 * 주소·이름 같은 **내용**으로 키를 만들면 안 된다. 그러면 *"같은 부지로 두 번째 프로젝트를
 * 만들 수 없다"* 가 되는데, 그건 정당한 사용이다(이 저장소 프로덕션에도 같은 주소로 의도적으로
 * 만든 프로젝트가 있다 — 검증용 2건).
 *
 * 그래서 **로컬 프로젝트 id**(`addProject` 가 한 번 만들고 그 뒤로 재사용하는 값)를 쓴다:
 *  · 같은 시도의 재전송 → **같은 키** → 서버가 처음 응답을 재생(중복 없음)
 *  · 사용자가 새로 만든 것 → **새 로컬 id** → 새 키 → 정상 생성
 *
 * 로컬 id 는 `localStorage`(`propai-project-storage`)에 있어 **같은 브라우저의 다른 탭**도
 * 같은 값을 본다. 다른 기기는 다른 id 를 만들므로 여기까지는 닿지 않는다(정직 표기).
 */

/** 다른 엔드포인트의 키 공간과 섞이지 않게 하는 접두. */
export const PROJECT_CREATE_KEY_PREFIX = "project-create:";

/** 로컬 프로젝트 id 로 생성 멱등키를 만든다. id 가 비면 `undefined`(키 없이 = 종전 동작). */
export function projectCreateIdempotencyKey(localId: string | null | undefined): string | undefined {
  const id = (localId ?? "").trim();
  return id ? `${PROJECT_CREATE_KEY_PREFIX}${id}` : undefined;
}

/** 요청 옵션에 실을 헤더 조각. 키가 없으면 빈 객체(헤더를 붙이지 않는다). */
export function projectCreateHeaders(
  localId: string | null | undefined,
): Record<string, string> {
  const key = projectCreateIdempotencyKey(localId);
  return key ? { "Idempotency-Key": key } : {};
}
