#!/usr/bin/env python3
"""OpenAPI JSON 스키마 내보내기 스크립트.

FastAPI 앱에서 OpenAPI 스키마를 추출하여 JSON 파일로 내보낸다.
Codex는 이 파일을 기반으로 openapi-typescript를 실행해 TypeScript 타입을 생성한다.

사용법:
    python scripts/export-openapi.py
    python scripts/export-openapi.py --output packages/types/openapi.json
"""

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def export_openapi(output_path: str) -> None:
    """FastAPI 앱에서 OpenAPI JSON을 내보낸다."""
    from apps.api.main import app

    schema = app.openapi()

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2, default=str)

    # 통계 출력
    paths = schema.get("paths", {})
    components = schema.get("components", {}).get("schemas", {})
    print(f"OpenAPI 스키마 내보내기 완료: {output_file}")
    print(f"  - 경로: {len(paths)}개")
    print(f"  - 스키마 컴포넌트: {len(components)}개")
    print(f"  - 버전: {schema.get('info', {}).get('version', 'unknown')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PropAI OpenAPI JSON 내보내기")
    parser.add_argument(
        "--output", "-o",
        default="packages/types/openapi.json",
        help="출력 파일 경로 (기본: packages/types/openapi.json)",
    )
    args = parser.parse_args()
    export_openapi(args.output)


if __name__ == "__main__":
    main()
