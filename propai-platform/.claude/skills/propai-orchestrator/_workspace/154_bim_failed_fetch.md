# BIM 페이지 "Failed to fetch" 진단 (154)

조사일: 2026-06-07 / 대상: projects/[id]/bim · api.4t8t.net

## 결론 요약

- **근본원인**: 배포된 Oracle API 컨테이너에 `minio` 파이썬 패키지가 설치되어 있지 않음 → `POST /bim/generate-ifc` 호출 시 `ModuleNotFoundError: No module named 'minio'` 로 즉시 500.
- **수정위치**: `propai-platform/apps/api/requirements.oracle.txt` 에 `minio>=7.2.0` 추가 + Oracle SSH 재배포. (코드 수정 불필요)
- `ifcopenshell`(0.8.4)는 컨테이너에 정상 설치됨 — OOM/메모리/타임아웃 아님. 빠른 500(0.45s).

## BIM 호출 엔드포인트 (3개)

`components/projects/ProjectBimWorkspaceClient.tsx` 가 호출:

| 단계 | 메서드/경로 | 코드 위치 |
|------|------------|----------|
| 메타데이터 | `GET /api/v1/projects/{id}` | ProjectBimWorkspaceClient.tsx:217 |
| BIM 물량산출 | `POST /api/v1/bim/generate-ifc` | ProjectBimWorkspaceClient.tsx:287 |
| 3D 형상 | `GET /api/v1/bim/threejs/{id}` | ProjectBimWorkspaceClient.tsx:319 |

베이스 URL: `lib/api-client.ts` resolveApiOrigin() → 브라우저에서 `https://api.4t8t.net` (www.4t8t.net은 localhost가 아니므로 PROD 폴백).

백엔드 라우터: `apps/api/routers/bim.py` — 엔드포인트 모두 존재, prefix `/api/v1` 정상.

## 라이브 상태코드 검증

```
GET  /health                       → 200 (0.48s)
POST /api/v1/bim/generate-ifc      → 403 "Not authenticated" (무인증, 0.35s) — 라우팅 정상
OPTIONS (preflight, www→api)       → 200, access-control-allow-origin: https://www.4t8t.net ✅ (CORS 정상)
POST login test@4t8t.net           → 200 (role=viewer)
POST /api/v1/bim/generate-ifc      → 500 (인증 후, 0.45s)  ← 버그
  body: {"success":false,"error_code":"INTERNAL_SERVER_ERROR",...}
```

CORS·인증·라우팅 모두 정상. 빠른 500 = 무거운 작업(IFC/MinIO 업로드) 도달 전 조기 실패.

## 트레이스백 (컨테이너 propai-api-8001 로그)

```
File "/app/apps/api/routers/bim.py", line 128, in generate_ifc
  return await service.generate_ifc_from_design(...)
File "/app/apps/api/services/bim_ifc_service.py", line 200, in generate_ifc_from_design
  from minio import Minio
ModuleNotFoundError: No module named 'minio'
```

컨테이너 직접 확인:
```
import ifcopenshell → OK (0.8.4)
import minio        → ModuleNotFoundError
```

`bim_ifc_service.py:199` 의 `import ifcopenshell` 는 성공, 바로 다음 줄 `:200` 의 `from minio import Minio` 에서 throw. IFC 생성 루프·MinIO 업로드·DB insert 도달 전이라 0.45s 즉시 실패.

## 근본원인 상세

- `minio>=7.2.0` 은 `apps/api/pyproject.toml:69` 에만 선언됨.
- Docker 빌드(`Dockerfile.oracle:16-17`)는 `pyproject.toml`이 아니라 **`requirements.oracle.txt`** 로 설치.
- `minio` 가 `requirements.oracle.txt` 에도 `requirements.txt` 에도 **누락**(grep exit=1, 둘 다 없음).
- 따라서 배포 컨테이너에 minio 모듈 부재 → generate-ifc 가 항상 500.
- `MEMORY` 의 "현장이미지 업로드는 Supabase Storage(httpx, 신규의존성0)"로 전환되면서 MinIO 의존을 줄였으나, **BIM IFC 저장 경로는 여전히 MinIO에 의존**(bim_ifc_service.py:307-322 put_object). 이 경로만 minio 미설치로 누락 노출.

## "Failed to fetch" vs 500 관계

- ProjectBimWorkspaceClient는 500을 `ApiClientError`(status 500)로 잡아 "API request failed with status 500" 메시지를 표시(extractErrorMessage, :174). 순수 500이면 화면에 "Failed to fetch"가 아니라 status 500 문구가 떠야 정상.
- 사용자가 본 정확한 "Failed to fetch" 문구는 fetch 자체 실패(네트워크 레벨)를 의미 → 동일 generate-ifc 호출이 (a) 이전 배포에서 502/연결리셋, 또는 (b) 일시적 워커 재기동/엣지 타임아웃 시점에 발생했을 가능성. 현재 시점 라이브는 깔끔한 500으로 재현됨.
- 어느 경우든 **BIM 물량산출이 막혀 있는 단일 실효 버그는 minio 모듈 부재**다. 이를 해소하면 generate-ifc 가 정상 200을 반환하고 threejs 후속 호출까지 이어진다.

## 수정안 (코드 수정 금지 범위 내 — 의존성/배포)

1) **(권장·최소)** `apps/api/requirements.oracle.txt` 에 한 줄 추가:
   ```
   minio>=7.2.0
   ```
   그리고 `requirements.txt`(Railway/기타 빌드 경로 사용 시)에도 동일 추가 권장.

2) Oracle SSH 재배포 필수(푸시만으론 미반영):
   ```
   ssh -i ~/.oci.key ubuntu@134.185.104.167
   git pull && docker build -f Dockerfile.oracle -t propai-api . \
     && docker rm -f propai-api-8001 \
     && docker run -d --name propai-api-8001 -p 8001:8000 ... propai-api
   ```
   (포트 매핑 기존 규칙 유지)

3) 검증:
   ```
   TOKEN=$(curl -s -X POST https://api.4t8t.net/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"test@4t8t.net","password":"test1234"}' | jq -r .access_token)
   curl -s -X POST https://api.4t8t.net/api/v1/bim/generate-ifc \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"project_id":"<실제 UUID>","total_area_sqm":2405,"floors":17,"structure_type":"RC"}' \
     -w '\nHTTP %{http_code}\n'
   # 기대: 200 + BIMQuantityResponse(total_volume_m3/element_count/ifc_version=IFC4)
   ```

## 후속 점검 포인트 (선택)

- **MinIO 인프라 자체 가용성**: minio 설치 후에도 `settings.minio_url` 대상 MinIO 서버가 미가동/네트워크 단절이면 `put_object`/`bucket_exists`(:314-322)에서 connection 에러로 다시 500/타임아웃 가능. 재배포 후 검증 시 200 확인 필수.
- generate-ifc 성공 후 `GET /bim/threejs/{id}`(routers/bim.py:78)는 `designs` 테이블 `design_type='bim_ifc'` 최신행의 file_url로 MinIO 재다운로드(_download_ifc, service:33) → 동일 MinIO 의존. minio 설치+MinIO 가동 둘 다 필요.
- 큰 floors/면적 입력 시 ifcopenshell 생성 루프가 1GB Micro에서 메모리 압박 가능하나, 현재 차단요인은 아님(import 단계에서 선행 실패).
```

## 참조 파일

- `apps/web/components/projects/ProjectBimWorkspaceClient.tsx:217,287,319` — 3개 엔드포인트 호출
- `apps/web/lib/api-client.ts:31-44` — 베이스 URL 해석
- `apps/api/routers/bim.py:120-134` — generate-ifc 라우터
- `apps/api/services/bim_ifc_service.py:200` — `from minio import Minio` (실패 지점)
- `apps/api/services/bim_ifc_service.py:307-322` — MinIO 업로드
- `apps/api/requirements.oracle.txt` — minio 누락(수정 대상)
- `apps/api/requirements.txt` — minio 누락(수정 대상)
- `apps/api/pyproject.toml:69` — minio 선언(빌드에 미사용)
- `Dockerfile.oracle:16-17` — requirements.oracle.txt로 설치
