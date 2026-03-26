"""PII 마스킹 단위 테스트.

이메일, 전화번호, 주민등록번호, 카드번호 마스킹 검증.
"""

from apps.api.logging_config import mask_pii


def _apply(event_dict: dict) -> dict:
    """mask_pii 호출 편의 래퍼."""
    return mask_pii(None, "info", event_dict)


class TestEmailMasking:
    """이메일 마스킹 검증."""

    def test_simple_email(self) -> None:
        """일반 이메일이 마스킹된다."""
        result = _apply({"email": "user@example.com"})
        assert result["email"] == "***@***.***"

    def test_email_with_plus(self) -> None:
        """+ 포함 이메일이 마스킹된다."""
        result = _apply({"msg": "연락처: user+tag@gmail.com 입니다"})
        assert "***@***.***" in result["msg"]
        assert "gmail.com" not in result["msg"]


class TestPhoneMasking:
    """전화번호 마스킹 검증."""

    def test_mobile_number(self) -> None:
        """휴대폰 번호가 마스킹된다."""
        result = _apply({"phone": "010-1234-5678"})
        assert result["phone"] == "***-****-****"

    def test_landline_number(self) -> None:
        """일반 전화번호가 마스킹된다."""
        result = _apply({"phone": "02-123-4567"})
        assert result["phone"] == "***-****-****"


class TestSSNMasking:
    """주민등록번호 마스킹 검증."""

    def test_resident_registration_number(self) -> None:
        """주민등록번호가 마스킹된다."""
        result = _apply({"ssn": "900101-1234567"})
        assert result["ssn"] == "******-*******"


class TestCardMasking:
    """카드번호 마스킹 검증."""

    def test_card_with_dashes(self) -> None:
        """대시로 구분된 카드번호가 마스킹된다."""
        result = _apply({"card": "1234-5678-9012-3456"})
        assert result["card"] == "****-****-****-****"

    def test_card_without_separator(self) -> None:
        """구분자 없는 카드번호가 마스킹된다."""
        result = _apply({"card": "1234567890123456"})
        assert result["card"] == "****-****-****-****"


class TestNonPIIPreserved:
    """PII가 아닌 값은 변경되지 않는다."""

    def test_plain_text_unchanged(self) -> None:
        """일반 텍스트는 변경되지 않는다."""
        result = _apply({"msg": "프로젝트가 생성되었습니다"})
        assert result["msg"] == "프로젝트가 생성되었습니다"

    def test_integer_unchanged(self) -> None:
        """정수 값은 변경되지 않는다."""
        result = _apply({"count": 42})
        assert result["count"] == 42

    def test_uuid_unchanged(self) -> None:
        """UUID는 마스킹되지 않는다."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = _apply({"id": uuid})
        assert result["id"] == uuid

    def test_multiple_fields(self) -> None:
        """여러 필드가 동시에 마스킹된다."""
        result = _apply({
            "email": "test@test.com",
            "phone": "010-9999-8888",
            "name": "홍길동",
        })
        assert result["email"] == "***@***.***"
        assert result["phone"] == "***-****-****"
        assert result["name"] == "홍길동"
