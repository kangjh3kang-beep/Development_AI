# Cloudflare R2 원본 도면 저장 — 활성화 가이드

설계생성(design-gen) 인제스트가 업로드한 **원본 도면 파일**을 Cloudflare R2(S3 호환,
**egress 무료**)에 보관한다. 코드는 이미 배선되어 있고(`app/services/design_ingest/object_store.py`),
**아래 4개 시크릿만 입력하면 즉시 라이브로 동작**한다(미입력 시 색인·검색은 정상, 원본 저장만 `stored=false`로 정직 강등).

> 왜 R2인가: 수십 TB 도면을 쌓아도 **전송(egress) 비용 0**. 저장만 약 $0.015/GB·월
> (10TB≈$150, 50TB≈$750/월). 중복제거(content_hash)+압축+티어링으로 실저장 GB를 더 줄인다.

---

## 1) Cloudflare에서 R2 버킷 + S3 자격증명 발급

1. Cloudflare 대시보드 → **R2** → **Create bucket**
   - 이름 예: `propai-design-originals` (비공개 유지 — 퍼블릭 액세스 켜지 말 것)
   - 위치: 자동(글로벌). 한국 사용자 지연이 중요하면 Jurisdiction/Location hint 검토.
2. **R2 → Manage R2 API Tokens → Create API Token**
   - 권한: **Object Read & Write** (해당 버킷으로 스코프 권장)
   - 발급 후 표시되는 **Access Key ID / Secret Access Key**를 안전히 복사(시크릿은 1회만 표시).
3. **Account ID** 확인: R2 개요 페이지 또는 S3 엔드포인트
   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` 에서 확인.

---

## 2) PropAI에 시크릿 입력 (4개)

| 키 | 값 | 필수 |
|----|----|------|
| `R2_ACCOUNT_ID` | Cloudflare 계정 ID | ✅ |
| `R2_ACCESS_KEY_ID` | R2 API 토큰의 Access Key ID | ✅ |
| `R2_SECRET_ACCESS_KEY` | R2 API 토큰의 Secret Access Key | ✅ |
| `R2_BUCKET` | 버킷 이름(예: `propai-design-originals`) | ✅ |
| `R2_ENDPOINT` | 엔드포인트 오버라이드(보통 불필요 — 미입력 시 계정ID로 자동조립) | ⛔ 선택 |

입력 방법(둘 중 하나):

- **관리자 화면(권장)**: 관리자 → **API 키 관리**(`/api/v1/admin/secrets`)에서 위 키를 추가.
  `platform_secrets`에 Fernet 암호화 저장되고 env로 오버레이되어 **재배포 없이** 적용된다.
- **서버 env**: 백엔드 서버의 `.env`(또는 시크릿 매니저)에 4개 키를 설정 후 재기동.

> 코드는 `get_clean_env_key`로 읽으므로 두 방식 모두 동작한다. 4개가 모두 있어야 활성화되며,
> 하나라도 비면 `is_configured()=False`로 **원본 저장만 비활성**(색인·검색·생성은 정상).

---

## 3) 보안·동작 요점 (이미 코드에 반영)

- **테넌트 격리 + 중복제거**: 키 = `design/{tenant_id}/{content_hash}{ext}`.
  동일 내용은 1회만 저장(멱등), 테넌트별 네임스페이스 분리. `tenant_id`는 인증 컨텍스트에서만
  주입(클라이언트 입력 금지), 경로 조작 문자는 화이트리스트로 정화.
- **원본 비공개**: 버킷은 비공개로 두고, 조회는 **단기(600초) presigned URL**로만.
  발급 시 `design/{요청자테넌트}/` 프리픽스 가드로 **교차테넌트 접근(IDOR) 차단**.
- **자격증명 비노출**: secret/access key는 로그·응답·URL 어디에도 평문 노출하지 않음
  (presigned에는 서명만 포함). 엔드포인트는 시크릿 기반이라 SSRF 표면 없음.
- **무의존 구현**: boto3 없이 httpx + AWS SigV4(stdlib). SigV4는 AWS 공식 예제 서명과 일치 검증됨.

---

## 4) 검증 (입력 후)

1. 설계 스튜디오 → **AI 설계생성** 패널에서 도면 파일(dxf/pdf/이미지 등) 업로드·색인.
   결과에 **`원본 보관`** + **`원본 보기`** 링크가 보이면 R2 저장 성공.
2. **원본 보기** 클릭 → 새 탭에서 presigned URL로 원본 열림(600초 유효).
3. 동일 파일 재업로드 시 `store_skip_reason=deduplicated`(중복제거 동작 확인).
4. (선택) R2 대시보드에서 `design/{tenant}/...` 객체 적재 확인.

---

## 5) 수십 TB 운영 — 비용 절감 단계 (후속 최적화)

원본 보관이 동작한 뒤, 실저장 GB를 더 줄이는 후속 작업(별도 증분):

1. **압축**: 텍스트성 도면(DXF/IFC)은 zstd/IFC-ZIP로 60~80%↓ 후 저장.
2. **썸네일/프록시**: 뷰어용 저해상 프록시(원본의 1/100~1/1000)만 Hot, 원본은 Cold.
3. **라이프사이클/티어링**: R2 Standard(Hot) → Infrequent Access(Warm) 수명주기 정책,
   장기 보존(법정 보관)은 더 저렴한 아카이브 티어로.
4. **CDN**: Cloudflare CDN 엣지 캐시로 반복 조회 트래픽 비용 0(R2 egress 무료와 결합).
5. **벡터 스케일**: Qdrant는 1억+ 벡터에서 스칼라/이진 양자화 + `on_disk` 적용(메모리 4~32x↓).

> 인프라 전환(티어링 정책·CDN·벡터 분산)은 인프라 트랙과 조율해 진행한다.
> 본 가이드 범위는 "원본을 R2에 안전하게 보관·조회"까지이며, 그 토대 위에서 단계적으로 최적화한다.
