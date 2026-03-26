#!/usr/bin/env bash
# OpenAPI JSON → TypeScript 타입 생성 스크립트
#
# 사용법:
#   cd propai-platform
#   bash scripts/generate-types.sh
#
# 필수 의존성:
#   - Python + FastAPI 앱이 import 가능해야 함
#   - npx openapi-typescript (Node.js)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "1/3: OpenAPI JSON 스키마 추출 중..."
PYTHONPATH="$ROOT_DIR:$PYTHONPATH" python -c "
from apps.api.main import app
import json

schema = app.openapi()
output = 'packages/schemas/openapi.json'
with open(output, 'w', encoding='utf-8') as f:
    json.dump(schema, f, indent=2, ensure_ascii=False)
print(f'   → {output} 생성 완료 ({len(schema.get(\"paths\", {}))} 엔드포인트)')
"

echo "2/3: TypeScript 타입 생성 중..."
npx openapi-typescript packages/schemas/openapi.json \
  -o packages/schemas/generated-types.ts

echo "3/3: 완료!"
echo "   → packages/schemas/openapi.json"
echo "   → packages/schemas/generated-types.ts"
