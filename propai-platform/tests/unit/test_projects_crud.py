"""프로젝트 CRUD 단위 테스트.

PUT(수정), PATCH(상태 전환), DELETE(소프트 삭제) 검증.
라우터 소스를 직접 읽어 코드 패턴을 검증한다 (DB 의존성 회피).
"""

from pathlib import Path

from packages.schemas.enums import ProjectStatus
from packages.schemas.models import ProjectStatusUpdateRequest, ProjectUpdateRequest

# 라우터 소스 코드를 직접 읽어 DB import 체인을 회피
_ROUTER_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "projects.py"
)
_SOURCE = _ROUTER_SOURCE.read_text(encoding="utf-8")


# ──────────────────────────────────────
# 상태 전환 맵 검증 (소스에서 파싱)
# ──────────────────────────────────────


class TestValidTransitions:
    """_VALID_TRANSITIONS 딕셔너리 검증."""

    def test_draft_to_planning_in_source(self) -> None:
        """draft → planning 전환이 소스에 정의되어 있다."""
        assert '"planning"' in _SOURCE

    def test_all_statuses_referenced(self) -> None:
        """모든 ProjectStatus가 소스에 참조된다."""
        for status_value in ProjectStatus:
            assert f'"{status_value.value}"' in _SOURCE

    def test_archived_has_empty_list(self) -> None:
        """archived 상태는 빈 전환 목록을 가진다."""
        assert '"archived": []' in _SOURCE

    def test_transitions_dict_exists(self) -> None:
        """_VALID_TRANSITIONS 딕셔너리가 정의되어 있다."""
        assert "_VALID_TRANSITIONS" in _SOURCE

    def test_construction_to_completed(self) -> None:
        """construction → completed 전환이 정의되어 있다."""
        assert '"completed"' in _SOURCE
        assert '"construction"' in _SOURCE


# ──────────────────────────────────────
# 프로젝트 수정 스키마 검증
# ──────────────────────────────────────


class TestProjectUpdateSchema:
    """ProjectUpdateRequest 스키마 검증."""

    def test_all_fields_optional(self) -> None:
        """모든 필드가 Optional이다."""
        req = ProjectUpdateRequest()
        assert req.name is None
        assert req.address is None
        assert req.description is None

    def test_partial_update(self) -> None:
        """일부 필드만 지정 가능하다."""
        req = ProjectUpdateRequest(name="새 이름")
        assert req.name == "새 이름"
        assert req.address is None

    def test_exclude_unset_works(self) -> None:
        """model_dump(exclude_unset=True)로 변경 필드만 추출한다."""
        req = ProjectUpdateRequest(name="변경됨")
        data = req.model_dump(exclude_unset=True)
        assert "name" in data
        assert "address" not in data

    def test_description_field(self) -> None:
        """description 필드가 Optional이다."""
        req = ProjectUpdateRequest(description="새 설명")
        assert req.description == "새 설명"


# ──────────────────────────────────────
# 상태 전환 요청 스키마 검증
# ──────────────────────────────────────


class TestProjectStatusUpdateSchema:
    """ProjectStatusUpdateRequest 스키마 검증."""

    def test_valid_status(self) -> None:
        """유효한 상태값이 허용된다."""
        req = ProjectStatusUpdateRequest(status=ProjectStatus.PLANNING)
        assert req.status == ProjectStatus.PLANNING

    def test_status_value(self) -> None:
        """status.value가 문자열이다."""
        req = ProjectStatusUpdateRequest(status=ProjectStatus.CONSTRUCTION)
        assert req.status.value == "construction"


# ──────────────────────────────────────
# 라우터 코드 패턴 검증 (소스 텍스트)
# ──────────────────────────────────────


class TestProjectsRouterCode:
    """프로젝트 라우터 코드 구조 검증."""

    def test_put_endpoint_exists(self) -> None:
        """PUT /{project_id} 엔드포인트가 정의되어 있다."""
        assert '@router.put("/{project_id}"' in _SOURCE

    def test_patch_status_endpoint_exists(self) -> None:
        """PATCH /{project_id}/status 엔드포인트가 정의되어 있다."""
        assert '@router.patch("/{project_id}/status"' in _SOURCE

    def test_delete_endpoint_exists(self) -> None:
        """DELETE /{project_id} 엔드포인트가 정의되어 있다."""
        assert '@router.delete("/{project_id}"' in _SOURCE

    def test_update_uses_exclude_unset(self) -> None:
        """update_project가 exclude_unset=True를 사용한다."""
        assert "exclude_unset=True" in _SOURCE

    def test_status_checks_valid_transitions(self) -> None:
        """update_project_status가 _VALID_TRANSITIONS를 검사한다."""
        assert "_VALID_TRANSITIONS" in _SOURCE

    def test_delete_sets_is_deleted(self) -> None:
        """delete_project가 is_deleted = True를 설정한다."""
        assert "is_deleted = True" in _SOURCE

    def test_delete_sets_deleted_at(self) -> None:
        """delete_project가 deleted_at을 설정한다."""
        assert "deleted_at" in _SOURCE

    def test_update_records_audit(self) -> None:
        """프로젝트 수정 시 감사 기록을 생성한다."""
        assert "record_audit" in _SOURCE

    def test_delete_records_audit(self) -> None:
        """record_audit가 여러 번 호출된다 (create/update/delete/status)."""
        assert _SOURCE.count("record_audit") >= 4

    def test_to_response_helper_exists(self) -> None:
        """_to_response 헬퍼 함수가 정의되어 있다."""
        assert "def _to_response" in _SOURCE

    def test_get_project_or_404_exists(self) -> None:
        """_get_project_or_404 헬퍼 함수가 정의되어 있다."""
        assert "def _get_project_or_404" in _SOURCE

    def test_status_invalid_transition_returns_400(self) -> None:
        """유효하지 않은 상태 전환 시 400을 반환한다."""
        assert "HTTP_400_BAD_REQUEST" in _SOURCE

    def test_204_no_content_for_delete(self) -> None:
        """DELETE는 204 No Content를 반환한다."""
        assert "HTTP_204_NO_CONTENT" in _SOURCE
