# Incoming IFC Dropzone

실제 익명화 IFC 원본을 이 폴더에 넣은 뒤 아래 명령으로 온보딩한다.

```bash
python scripts/perf/onboard_real_ifc_fixtures.py --mode copy --source-label internal-anonymized
```

기본값으로 `--scrub-owner-data`가 활성화되며, 소유자/조직/애플리케이션 식별정보를 비식별화한다.
필요 시 `--no-scrub-owner-data`로 비활성화할 수 있다(운영 사용 비권장).

실행 후 결과:
- `tests/fixtures/ifc/real_samples/*.ifc` 업데이트
- `tests/fixtures/ifc/real_ifc_manifest.v1.json` 자동 갱신

사전 검증(권장):

```bash
python scripts/perf/validate_real_ifc_incoming.py \
  --incoming tests/fixtures/ifc/incoming \
  --min-ifc-files 3
```

기본 품질게이트:
- IFC 파싱 성공
- 면적/체적 양수
- 동일 SHA-256 파일 중복 없음
- 파일 크기 상한(기본 512MB) 이내

원클릭(온보딩 + strict 벤치) 실행:

```bash
python scripts/perf/refresh_real_ifc_pipeline.py \
  --incoming tests/fixtures/ifc/incoming \
  --output-dir tests/fixtures/ifc/real_samples \
  --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json \
  --source-label internal-anonymized \
  --require-real-ifc-min 3
```

`refresh_real_ifc_pipeline.py`는 기본적으로 incoming 품질게이트를 선행 실행한다.
또한 `--mode move`일 때 기본값으로 실행 후 incoming에 IFC가 남아있으면 실패한다.
