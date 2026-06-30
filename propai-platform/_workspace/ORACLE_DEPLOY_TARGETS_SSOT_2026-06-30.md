# Oracle 배포 대상 SSOT

## 절대 혼동 금지

프론트 화면(`4t8t.net/ko`, `/ko/precheck`, `/ko/design-studio` 등)의 UI 변경 배포는
**프론트 A1**에서 실행한다. 백엔드 A1은 API 서버이며, 프론트 화면 변경 배포 대상이 아니다.

## 확정된 접속/배포 대상

| 구분 | 용도 | SSH | 키 | Hostname | Repo |
| --- | --- | --- | --- | --- | --- |
| 프론트 A1 | `4t8t.net` 웹 UI, Next.js web 컨테이너 | `ubuntu@158.179.174.207` | `~/.oci.key` | `4t8t` | `/home/ubuntu/Development_AI` |
| 백엔드 A1 | `api.4t8t.net`, API/Caddy/블루그린 | `ubuntu@168.110.125.89` | 키 별도 확인 필요 | `4t8tpropai-backend-a1` | `/home/ubuntu/Development_AI` |

## 이번 실수의 원인

- 지도시스템 UI 변경은 프론트 배포 대상이다.
- 그런데 `168.110.125.89` 백엔드 A1에 `~/.ssh/propai_oracle_deploy` 키로 접속을 시도했다.
- 해당 키는 서버에서 거부됐고, 이를 "Oracle 배포가 막힘"으로 잘못 판단했다.
- 실제 프론트 A1은 `ssh -i ~/.oci.key ubuntu@158.179.174.207`로 접속 가능했다.

## 프론트 UI 변경 배포 명령

로컬에서 원격 실행:

```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207 \
  'cd ~/Development_AI && setsid bash /tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629 </dev/null >/dev/null 2>&1 &'
```

또는 프론트 A1에 접속한 뒤:

```bash
cd ~/Development_AI
setsid bash /tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629 \
  </dev/null >/dev/null 2>&1 &
watch -n5 cat /tmp/deploy_status.txt
```

## 배포 후 검증

```bash
cat /tmp/deploy_status.txt
tail -120 /tmp/deploy.log
curl -s -o /dev/null -w "%{http_code}\n" https://4t8t.net/ko
curl -s -o /dev/null -w "%{http_code}\n" https://4t8t.net/ko/precheck
curl -s -o /dev/null -w "%{http_code}\n" https://4t8t.net/ko/design-studio
curl -s https://api.4t8t.net/health
```

## 체크 규칙

1. 화면이 안 바뀌었다면 먼저 `4t8t.net` 프론트 A1 배포 여부를 확인한다.
2. 프론트 UI 배포에 `168.110.125.89`를 사용하지 않는다.
3. `Permission denied (publickey)`가 `168.110.125.89`에서 발생해도 프론트 배포 실패로 결론내지 않는다.
4. 프론트 UI 변경은 `web` target을 우선 사용한다. API 변경이 포함된 경우에만 API 배포 경로를 별도로 확인한다.
