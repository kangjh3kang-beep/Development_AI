# 🔐 시크릿 키 로테이션 가이드 (2026-06-11 코드리뷰 후속)

코드 레벨 조치는 완료됐지만, 아래 **외부 서비스 키 교체는 대시보드에서 직접** 수행해야 합니다.
유출 이력이 있으므로 전부 교체를 권장합니다. 우선순위 순서대로 정리했습니다.

## 1. JWT 서명키 (최우선 — GitHub에 유출됨)
- 유출 경위: `.env.example`에 실제 운영 키가 커밋되어 원격 저장소에 푸시됨 (현재 플레이스홀더로 교체 완료. 단, **git 히스토리에는 남아 있음**)
- 교체 방법:
  1. 새 키 생성: `openssl rand -hex 32`
  2. 운영 환경(.env / Railway / Cloudflare 환경변수)의 `JWT_SECRET_KEY` 교체
  3. 교체 즉시 기존 발급 토큰 전부 무효화됨 → 사용자 재로그인 필요 (리프레시 토큰도 무효)
  4. `APP_SECRET_KEY`도 함께 교체 (sales_crypto 블라인드 인덱스·secret_store 마스터키로 재사용되므로 동일 등급)
- 히스토리 정리(선택): `git filter-repo --replace-text` 로 과거 커밋에서 키 문자열 치환 후 force push. 공개 저장소라면 필수.

## 2. Hasura Admin Secret
- `.env.example` 유출분. Hasura 콘솔/배포 환경에서 `HASURA_GRAPHQL_ADMIN_SECRET` 교체.

## 3. 블록체인 배포자 프라이빗키
- 위치: `contracts/.env` (git 미추적이나 평문 보관 중)
- 조치:
  1. 새 지갑 생성 (하드웨어 지갑 권장)
  2. 기존 주소 잔액(Amoy MATIC) 이전
  3. Amoy `PropAIEscrow`(0x961cba4A...82E6) owner를 새 주소로 `transferOwnership` (Ownable2Step 전환 후 권장)
  4. `contracts/.env`에서 구키 삭제 → `scripts/setup-contracts-env.sh` 재실행 (이제 키 입력이 화면에 표시되지 않음)
  5. **메인넷 배포 시 절대 이 키 재사용 금지**
- Alchemy RPC 키, Polygonscan API 키도 함께 재발급.

## 4. Supabase DB 비밀번호
- 위치: `apps/api/.env` (운영 풀러 호스트+비밀번호 평문)
- Supabase Dashboard → Settings → Database → Reset database password
- 로컬 `.env`에는 운영 자격증명 대신 로컬 DB 연결만 두세요.

## 5. ANTHROPIC_API_KEY 등 외부 API 키
- 위치: `propai-platform/.env`
- console.anthropic.com에서 기존 키 폐기·재발급. KAKAO_CLIENT_SECRET, MOLIT/VWORLD 키도 노출 의심 시 재발급.

## 6. 기본값 자격증명 (운영 전 필수 교체)
- `GRAFANA_PASSWORD=admin`, `AIRFLOW_PASSWORD=airflow`, `MINIO_SECRET_KEY=minioadmin*`, `EMQX_PASSWORD=emqx_pass`
- `docker-compose.prod.yml`은 이제 `POSTGRES_PASSWORD`/`JWT_SECRET_KEY` 환경변수 없이는 기동되지 않도록 수정됨 (`${VAR:?}` 가드).

## 향후 운영 원칙
1. `.env.example`에는 절대 실값 금지 — 플레이스홀더만
2. 운영 시크릿은 배포 플랫폼 환경변수(Railway/Cloudflare/K8s external-secrets)로만 주입
3. 커밋 전 시크릿 스캔: `gitleaks` pre-commit 훅 도입 권장
