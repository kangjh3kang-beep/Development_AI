"""SP6-2: 의견교환 순수 규칙 — 본문검증·앵커/해결 루트제약·부모검증·삭제본문 은닉(결정론)."""

import pytest

from app.services.collaboration.review_comment_rules import (
    MAX_COMMENT_BODY,
    anchor_allowed,
    is_root,
    parent_is_valid,
    resolve_allowed,
    validate_comment_body,
    visible_body,
)


class TestValidateBody:
    def test_trims_and_returns(self):
        assert validate_comment_body("  hi  ") == "hi"

    def test_empty_or_whitespace_raises(self):
        for bad in ("", "   ", None):
            with pytest.raises(ValueError):
                validate_comment_body(bad)

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_comment_body("x" * (MAX_COMMENT_BODY + 1))


class TestRootConstraints:
    def test_is_root(self):
        assert is_root(None) is True
        assert is_root("some-id") is False

    def test_anchor_only_on_root(self):
        assert anchor_allowed(None) is True
        assert anchor_allowed("parent") is False

    def test_resolve_only_on_root(self):
        assert resolve_allowed(None) is True
        assert resolve_allowed("parent") is False


class TestParentValidation:
    def test_valid_when_active_and_same_document(self):
        assert parent_is_valid("active", "doc-1", "doc-1") is True

    def test_invalid_when_deleted_or_other_document(self):
        assert parent_is_valid("deleted", "doc-1", "doc-1") is False
        assert parent_is_valid("active", "doc-2", "doc-1") is False

    def test_invalid_when_parent_not_found(self):
        assert parent_is_valid(None, "doc-1", "doc-1") is False

    def test_invalid_when_deleted_and_other_document(self):
        assert parent_is_valid("deleted", "doc-2", "doc-1") is False


class TestVisibleBody:
    def test_active_shows_body(self):
        assert visible_body("active", "hello") == "hello"

    def test_deleted_hides_body(self):
        assert visible_body("deleted", "hello") is None

    def test_active_with_none_body(self):
        assert visible_body("active", None) is None
