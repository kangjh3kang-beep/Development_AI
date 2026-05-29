# Real IFC Fixtures

이 디렉터리는 실 IFC 정확도 벤치용 샘플 파일을 저장한다.

- 파일명은 `tests/fixtures/ifc/real_ifc_manifest.v1.json`의 `local_path`와 일치해야 한다.
- 민감정보 제거(익명화)된 IFC만 추가한다.
- 파일 추가 후 Stage 3 벤치 스크립트를 재실행해 `available_count`를 확인한다.
- 온보딩 시 기본 `--scrub-owner-data`를 유지해 owner/org/app 메타를 재익명화한다.

현재 포함된 `*.ifc` 3개는 Stage 3 파서/게이트 검증을 위한 generated 샘플이며
`scripts/perf/generate_real_ifc_samples.py`로 재생성할 수 있다.
