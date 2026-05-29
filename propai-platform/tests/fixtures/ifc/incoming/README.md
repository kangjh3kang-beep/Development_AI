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
