# 21 — 디지털트윈 AI 협업 고도화 + 항공 오리진 수정 (프론트엔드)

기반 계약: 20_digitaltwin_ai_contract.md. MVP 프론트 5e94e6f 위 증분. 커밋 `101e049`.

## 1. 신규/변경 파일
| 파일 | 구분 | 내용 |
|------|------|------|
| `apps/web/lib/api-client.ts` | 변경(1줄) | `resolveApiOrigin()` export화(항공 절대화에서 재사용) |
| `apps/web/components/digital-twin/types.ts` | 변경 | `DigitalTwinBbox{size_m?}`, `terrain.bbox_m` 타입화, `DigitalTwinInterpretResponse`/`DigitalTwinInterpretSections` 추가 |
| `apps/web/components/digital-twin/DigitalTwinScene.tsx` | 변경 | 항공 URL 절대화·CORS·실패 폴백, 카메라 size_m, AI 카드 마운트 |
| `apps/web/components/digital-twin/DigitalTwinAiCard.tsx` | 신규 | 가상준공 AI 해설 카드(5섹션) |

페이지(`site-analysis/page.tsx`) 무수정 — 카드는 DigitalTwinScene 내부(씬 아래)에서 렌더하여 무파괴.

## 2. 항공 절대화 + size_m (WARN 수정)
- `absolutizeAerialUrl(url)`: 절대(`https?://`)면 그대로, 상대면 `resolveApiOrigin()` 결합(`/`접두 보정). TerrainMesh 항공 분기에서 적용 → Cloudflare 프론트 오리진에서 api.4t8t.net로 전달(WARN-1 404 해소).
- `AerialMaterial`를 `useLoader(TextureLoader)`(에러 폴백 없음, throw→ErrorBoundary 크래시) → 수동 `TextureLoader.load(...)` + `setCrossOrigin("anonymous")`로 교체. 로드 실패(404/CORS) onError에서 조용히 무시, 미로드 시 회색(`#1e293b`) 머티리얼 유지. cancel 가드 + 취소 시 dispose.
- 카메라: `camSpan = terrain.bbox_m.size_m ?? aerial.cover_m ?? 200`. 기존 inline 카메라가 `size_m ?? 200`만 보던 것을 cover_m 폴백 포함 전 체인으로 통일(SceneContent와 동일 규칙). `useLoader` import 제거.

## 3. AI 해설 카드 (5섹션·재사용)
- `DigitalTwinAiCard`: "AI 해설 생성" 버튼 → `apiClient.post("/digital-twin/interpret", {address|pnu, scene, context})` (timeoutMs 60000, useMock false).
- 5섹션 표시(라벨): design_rationale(설계 의도·적합성), context_fit(주변 맥락·스카이라인), view_sunlight(조망·일조), development_implication(개발 시사점), marketing_highlight(분양 하이라이트).
- 재사용: `AnalysisVerdict`(analysisType `digital_twin_interpret`, 섹션 레코드를 interpretation+검증 context로 전달, sectionLabels로 순서/라벨, defaultOpen, autoRunVerification) → 내부에서 `VerificationBadge` 자동 결합.
- 정직성: "AI 해석·참고용" 배지, `grounding.used_fields` 칩 표기, "실측·인허가 결론 아님" 안내문, `note` 표시, `cached` 배지.
- 상태: busy(30s+ 안내)·err·ok:false(message) 처리. 캐시면 백엔드가 cached:true 반환→배지.
- context: useProjectContextStore에서 가용 시에만 추출 — roi(feasibilityData.profitRatePct), esg(esgData.totalCarbonPerSqm), zone_type(siteAnalysis.zoneCode), design_summary(designData: building_type/total_gfa_sqm/floor_count/bcr/far). permit은 스토어에 없어 생략(과설계 금지). 비면 context 자체 생략.
- 다크/토큰색만 사용.

## 4. 로컬 검증
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(4파일) → EXIT 0.
- api-client.ts diff는 export 1줄만(apiClient import 회귀 없음). 스테이징 diff에서 `apiClient` import 보존 확인(`apiClient, resolveApiOrigin`).

## 5. 커밋
- 해시 `101e049036a7e1d578a601c57dede88f1bd68d7d`, 메시지 `feat(digital-twin): 가상준공 AI 해설 카드 + 항공 텍스처 오리진 수정`. footer Co-Authored-By: Claude Opus 4.8 (1M context). push 안 함.
- git add 명시경로 4개만(-A 미사용).

## 6. 백엔드 정합사항(확인 필요)
- 엔드포인트 `POST /api/v1/digital-twin/interpret` 필요. Req `{ address?, pnu?, scene?(DigitalTwinScenePayload), context?{roi?, esg?, zone_type?, design_summary?} }`.
- Res 계약(types.ts와 일치 필수): `{ ok, sections{design_rationale,context_fit,view_sunlight,development_implication,marketing_highlight}(string), cached?, grounding{used_fields:string[]}, note?, message? }`. ok:false 시 message로 사유.
- 항공 절대화는 프론트 방어가 들어갔으나, 계약대로 백엔드도 공개 API 베이스로 절대 URL 반환 권장. aerial-image 엔드포인트는 CORS(Access-Control-Allow-Origin) 허용 필요 — TextureLoader crossOrigin=anonymous 응답.
- terrain.bbox_m.size_m(=half_m*2) 백엔드 추가 시 카메라 거리 자동 사용(없으면 cover_m→200 폴백).
- context 키 네이밍: 프론트는 roi/esg/zone_type/design_summary로 전송. 백엔드 그라운딩 요약과 키 일치 확인.
