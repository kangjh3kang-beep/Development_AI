"""불변 감사 추적 서비스."""
import hashlib
import time
import uuid
from typing import Optional


class AuditEntry:
    """감사 로그 엔트리."""

    __slots__ = (
        "id",
        "timestamp",
        "action",
        "user_id",
        "resource_type",
        "resource_id",
        "changes",
        "prev_hash",
        "entry_hash",
        "metadata",
    )

    def __init__(
        self,
        action: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        changes: Optional[dict] = None,
        prev_hash: str = "",
        metadata: Optional[dict] = None,
    ):
        self.id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.action = action
        self.user_id = user_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.changes = changes or {}
        self.prev_hash = prev_hash
        self.metadata = metadata or {}
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = (
            f"{self.id}{self.timestamp}{self.action}"
            f"{self.user_id}{self.resource_type}"
            f"{self.resource_id}{self.prev_hash}"
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "changes": self.changes,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "metadata": self.metadata,
        }


class AuditTrailService:
    """불변 감사 추적 (append-only, SHA-256 해시 체인)."""

    ACTIONS = [
        "CREATE", "READ", "UPDATE", "DELETE",
        "LOGIN", "LOGOUT", "EXPORT", "APPROVE",
    ]

    def __init__(self):
        self._entries: list[AuditEntry] = []
        self._last_hash: str = ""

    def log(
        self,
        action: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        changes: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> AuditEntry:
        """감사 로그 추가."""
        entry = AuditEntry(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            prev_hash=self._last_hash,
            metadata=metadata,
        )
        self._entries.append(entry)
        self._last_hash = entry.entry_hash
        return entry

    def get_entries(
        self,
        resource_type: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """필터 조건으로 감사 로그 조회."""
        result = self._entries
        if resource_type:
            result = [e for e in result if e.resource_type == resource_type]
        if user_id:
            result = [e for e in result if e.user_id == user_id]
        if action:
            result = [e for e in result if e.action == action]
        return result[-limit:]

    def verify_chain(self) -> bool:
        """해시 체인 무결성 검증."""
        if not self._entries:
            return True
        prev = ""
        for entry in self._entries:
            if entry.prev_hash != prev:
                return False
            prev = entry.entry_hash
        return True

    def get_entry_by_id(self, entry_id: str) -> Optional[AuditEntry]:
        """ID로 감사 로그 조회."""
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    @property
    def total_entries(self) -> int:
        """총 엔트리 수."""
        return len(self._entries)

    @property
    def last_hash(self) -> str:
        """마지막 해시 값."""
        return self._last_hash
