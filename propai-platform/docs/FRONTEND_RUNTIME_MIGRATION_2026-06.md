# 프런트엔드 런타임 이전 검토안 (Cloudflare Workers → Node)

작성일: 2026-06-05 · 대상: PropAI(사통팔땅) 웹 프런트엔드(Next.js)

## 1. 배경 / 문제
- 현재 프런트엔드는 **Cloudflare Workers**(`@opennextjs/cloudflare`)에서 SSR.
- **오류 1102(Worker 리소스 초과)** 가 반복: Workers의 **요청당 CPU/메모리(128MB) 한도**를, 무거운 페이지의 SSR(대형 클라이언트 트리·framer-motion 51파일·3D)이 초과.
- 완화책(무거운 패널 `dynamic ssr:false`)을 적용했으나, 앱이 커질수록 재발 위험 상존 → 근본 해결로 런타임 이전 검토.

## 2. 후보 비교

| 항목 | (A) Cloudflare Workers(현행) | (B) Vercel (Node/Fluid) | (C) Oracle 자체 Node(Docker) |
|------|------------------------------|--------------------------|------------------------------|
| 런타임 | V8 isolate(제약 큼) | Node 서버리스(넉넉) | 풀 Node(제약 없음) |
| CPU/메모리 한도 | 엄격(1102 원인) | 함수당 넉넉(수 GB·수십초) | 컨테이너 자원 내 자유 |
| SSR 무게 허용 | 낮음 | 높음 | 매우 높음 |
| 국내 응답속도 | 엣지(빠름) | 엣지+함수(양호) | 단일 리전(국내 양호) |
| 운영 난이도 | 낮음(현행) | 낮음(Git 연동 자동) | 중(직접 운영·이미 백엔드 운영중) |
| 비용 | 저렴 | 트래픽 비례(중) | 고정(기존 인프라 재사용) |
| 공공데이터 국외IP 차단 | 무관(프런트) | 무관(프런트) | 무관(프런트) |
| 백엔드 근접성 | 분리 | 분리 | **백엔드와 동일 인프라(지연↓)** |

> 참고: 백엔드는 이미 Oracle(국내, 공공데이터 국외IP 차단 회피용)에서 Docker로 운영 중. 프런트를 같은 Oracle Node로 두면 운영 일원화 + 프런트→백엔드 호출 지연 감소 이점.

## 3. 권고
- **1순위: (C) Oracle 자체 Node(Docker)** — 이미 Oracle 운영 경험·인프라가 있어 추가 비용 0에 가깝고, Workers의 CPU 한도(1102)에서 완전히 자유. 백엔드와 동일 리전.
- **대안: (B) Vercel** — 운영 최소(Git push 자동배포), Next 네이티브 호환 최고. 단 트래픽 비용·또 다른 외부 종속.
- 현행(A)는 1102 완화책으로 단기 유지 가능하나, 트래픽·기능 증가 시 한계.

## 4. (C) Oracle Node 이전 절차(권고안)
1. **빌드 전환**: `@opennextjs/cloudflare` 제거 → 표준 `next build` + `next start`(Node) 또는 `output: "standalone"`.
2. **Dockerfile.web**: `node:20-slim` + standalone 산출물 복사 + `node server.js`(3000). (백엔드 Dockerfile.oracle 패턴 재사용)
3. **리버스 프록시**: 기존 Cloudflare(DNS/SSL)는 유지하되 오리진을 Oracle 프런트 컨테이너로. Nginx/Caddy로 `/`(프런트 3000)·`/api`(백엔드 8000) 라우팅, 또는 프런트가 api.4t8t.net 직접 호출(현행 유지).
4. **환경변수**: `NEXT_PUBLIC_*`(API base 등) 동일 이전. SSR 시크릿 없음 확인.
5. **배포 파이프라인**: 백엔드 deploy.sh에 프런트 빌드·컨테이너 교체 추가(또는 별도 web-deploy.sh). main 푸시 → SSH 빌드.
6. **검증**: 1102 재현 페이지(대시보드·프로젝트 상세·BIM)에서 콜드/웜 응답·메모리·동시접속 부하 테스트.
7. **롤백**: Cloudflare Pages 빌드 보존 → 문제 시 DNS 오리진만 원복.

## 5. 리스크 / 체크포인트
- **Edge 전용 코드 의존성**: 현재 코드가 Cloudflare 전용 API(KV/R2/Workers env)에 의존하는지 점검(대부분 미사용 추정) → Node에서 제거/대체.
- **이미지 최적화**: next/image 로더가 Cloudflare 기반이면 Node sharp로 전환.
- **콜드스타트**: Node 컨테이너는 상시 가동이라 콜드스타트 거의 없음(이점).
- **SSL/도메인**: Cloudflare proxy(주황 구름) 유지 시 SSL·CDN·WAF 이점 유지, 오리진만 Oracle.
- **무중단**: 블루-그린(새 컨테이너 띄우고 프록시 스위치).

## 6. 단기(이전 전) 병행 완화 — 이미 적용/예정
- 무거운 패널 `dynamic ssr:false`(대시보드·프로젝트 상세·BIM) ✅
- AI 해석 온디맨드+캐시(SSR 무블로킹) ✅
- (예정) framer-motion 사용 축소, 페이지별 SSR 데이터 페치 경량화.

## 7. ★실측 제약(2026-06-05) — Oracle VM은 "빌드" 불가
- Oracle VM 실측: **RAM 956MB(가용 ~385MB) + swap 4GB, 2 vCPU, node 미설치**.
- Next 프로덕션 빌드는 ~2~4GB RAM 필요 → **이 VM에서 직접 빌드 시 OOM/스왑 폭주로 실패**.
- 그러나 **런타임(빌드 산출물 실행)은 ~150~300MB** → 이 VM에서 충분히 구동 가능.
- 결론: "Oracle Node" 자체는 가능하나 **빌드를 VM에서 하면 안 됨**. 빌드는 외부에서, 산출물만 배포.

### 수정된 실행 옵션(빌드/런타임 분리)
- **(C-1) CI 빌드 → 이미지 배포(권장)**: GitHub Actions(또는 로컬)에서 `Dockerfile.web`로 이미지 빌드 → 레지스트리(ghcr/docker hub) push → Oracle은 `docker pull` 후 실행(블루-그린). VM은 빌드 부담 0. 무료 인프라 유지.
- **(C-2) 로컬 빌드 → 이미지 push**: 개발 PC(WSL2)에서 이미지 빌드 후 push, Oracle pull. CI 없이 즉시 가능하나 수동.
- **(C-3) Oracle VM 업그레이드**: RAM 4GB+로 올려 VM 자체 빌드. 비용 발생.
- **(B) Vercel**: Vercel이 빌드·런타임 모두 담당 → VM 자원 무관, 1102 해소, 운영 최소. 트래픽 비용·외부 종속.

### 권고(수정)
- VM 자체 빌드가 막혔으므로 **(C-1) CI 빌드→Oracle 런타임** 또는 **(B) Vercel** 이 현실적.
- 운영 최소·즉효 = **(B) Vercel**, 인프라 일원화·무료 유지 = **(C-1)**.

## 8. 결정 요청
- 타깃: (C-1) CI빌드→Oracle 런타임 / (B) Vercel / (C-3) VM 업그레이드 중 택1.
- (C-1) 선택 시: 레지스트리(ghcr 등)·GitHub Actions 시크릿 준비 필요.
- 무중단 전환 창(트래픽 적은 시간) 협의.
