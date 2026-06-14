# 멀티세션 협업 프로토콜

> 여러 Claude 세션이 같은 저장소를 동시에 개발할 때의 **충돌 방지 + 조율** 규약.
> 자율 실시간 오케스트레이션이 아니라 **git 강제 + 공유 보드 + 명시적 핸드오프**의 하이브리드.

## 왜 (배경)
독립 Claude 세션들은 서로를 런타임에 제어할 수 없다. `send_message`는 사용자 확인 게이트라 자동 루프가 안 된다. 따라서 신뢰할 협업의 척추는 **git(구조 강제)** 와 **공유 파일(조율 상태)** 이고, 메시징은 보조다.

## 계층
### L0 — 구조 격리 (git이 강제)
- **브랜치당 전용 워크트리.** `scripts/new-worktree.sh <branch>`로 만든다. 공유 메인(`Development_AI/`)에서 feature 브랜치 checkout 금지. 상세: `WORKTREES.md`.
- git은 한 브랜치를 두 워크트리에서 동시 checkout하는 것을 거부 → **충돌이 구조적으로 불가능**해진다.

### L1 — 공유 조율 보드 (항상 가용·게이트 0)
- 위치: `~/My_Projects/.coordination/BOARD.md` (git 밖 공유 — 모든 워크트리가 같은 한 부를 본다. 브랜치별 사본 충돌 없음).
- **세션 시작 시 보드를 읽는다**(누가 무슨 브랜치·영역을 작업 중인지 파악).
- **공유영역(여러 워크스트림이 건드릴 파일/모듈) 편집 전 claim**을 남긴다. 완료 시 release.
- 진행/완료/블로커를 핸드오프 로그에 갱신한다.
- 헬퍼: `scripts/coord.sh status|claim|release|note`.

### L2 — 소유권 분할 (충돌 최소화)
- 워크스트림별로 디렉토리/모듈 오너십을 보드에 명시. 남의 오너 영역은 claim+핸드오프 없이 편집하지 않는다.
- 불가피한 공유 파일(예: `main.py` include_router, 라우터 등록)은 **additive 1줄**로만, claim 후 즉시 커밋·release.

### L3 — 명시적 핸드오프 (능동·사용자 확인)
- 다른 세션에 인계/요청 시 `mcp__ccd_session_mgmt__send_message`(사용자 확인 필요). 예: "X 끝남, Y 픽업 가능" / "공유파일 Z 건드림, fetch·rebase 요망".
- 같은 CCD 인스턴스 세션만 도달. 다른 인스턴스는 보드 + git으로만 조율.

### L4 — 통합 수렴
- 각 브랜치는 독립 진행 후 **공유 integration 브랜치 / main으로 주기 머지**로 수렴. 머지 전 `git fetch && git log --all --oneline`로 타 브랜치 변경 확인.

## 불변 안전장치
- 커밋 전 `git branch --show-current`로 자기 브랜치 확인(엉뚱한 브랜치 착지 방지).
- main 직접 푸시 금지(이 저장소 규약). 자기 feature 브랜치로만.

## 빠른 시작
```bash
scripts/coord.sh status                      # 워크트리·브랜치·보드 한눈에
scripts/new-worktree.sh feature/<branch>     # 전용 워크트리 생성(없으면)
scripts/coord.sh claim apps/api/main.py      # 공유 파일 편집 전 클레임
scripts/coord.sh release apps/api/main.py    # 완료 후 해제
scripts/coord.sh note "SP2-2 마이그레이션 시작"  # 핸드오프 로그
```
