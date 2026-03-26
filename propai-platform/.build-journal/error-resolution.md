# 오류 해결 및 변경 이력 공유 (Error Resolution Log)

## 1. Casbin_rule 권한 누락 (부분 해소 건) 처리 내역

- **발생 일시**: 2026-03-18T06:45 (Gemini Phase 2 중 검토)
- **이슈 설명**: Python 백엔드의 권한 제어 모듈(Casbin Adapter)이 초기 구동 시 `casbin_rule` 정책 테이블을 `public` 스키마에 자동 생성하려고 시도할 때, DB 접속 계정(`propai`)에 스키마 내 테이블 생성(`CREATE`) 권한이 명시적으로 존재하지 않으면 권한 부족 오류가 발생할 수 있는 잠재적 이슈가 발굴됨. (가이드라인 내 "1건 부분 해소(casbin_rule — 낮음 심각도)")
- **담당 파트**: Gemini (인프라 / DB 초기화)
- **영향 범위**: 다음 단계(Step 3) Claude Code가 구현할 FastAPI 애플리케이션 및 RBAC 초기화 과정에서의 컨테이너 재시작 및 오류 유발.
- **해결 방안**:
  `propai-platform/infra/docker/init.sql` 하단에 사용자 스키마 조작 및 테이블 관리를 허용하는 명시적 `GRANT` 스크립트를 추가하여 원천 차단.

```sql
-- Casbin 어댑터가 casbin_rule 테이블을 자동 생성할 수 있도록 스키마 권한 명시 부여
GRANT CREATE ON SCHEMA public TO propai;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO propai;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO propai;
```

- **상태**: 해결 완료 (**Claude Code 확인 요망**)
- **후속 조치**: 백엔드/API 구동 전, 최신 `init.sql` 스키마가 반영되도록 `propai-postgres` 컨테이너를 재시작 권장 (`docker compose restart postgres`).

---
> **To: Claude Code**
> 백엔드 초기화 및 Casbin Adapter 적용 시, 위 권한이 부여된 상태이므로 `init.sql` 권한 걱정 없이 진행하시면 됩니다.
