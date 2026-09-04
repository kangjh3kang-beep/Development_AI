"""보안 콘텐츠 검증·자산권리 레지스트리 (P0 최소형).

- content_inspection: 업로드 바이트의 매직바이트 검증·아카이브 한도(zip bomb)·경로순회·
  MIME 위장 탐지를 하나의 구조화 결과(InspectionResult)로 반환한다(fail-closed).
- asset_rights: 자산의 학습/내보내기 권리를 표현하는 최소 모델(권리 불명=금지 기본값).
"""

from app.services.security.asset_rights import (
    AssetRight,
    is_export_allowed,
    is_train_allowed,
    keep_train_allowed,
    resolve_asset_right,
)
from app.services.security.content_inspection import (
    ArchiveLimits,
    ExtractResult,
    InspectionResult,
    av_scan,
    http_status_for,
    inspect_upload,
    safe_extract_archive,
    sniff_type,
)

__all__ = [
    "ArchiveLimits",
    "AssetRight",
    "ExtractResult",
    "InspectionResult",
    "av_scan",
    "http_status_for",
    "inspect_upload",
    "is_export_allowed",
    "is_train_allowed",
    "keep_train_allowed",
    "resolve_asset_right",
    "safe_extract_archive",
    "sniff_type",
]
