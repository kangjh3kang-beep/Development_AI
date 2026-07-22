"""렌더 디스패치 — 정본 ReportModel + 포맷 → (bytes, MIME, 확장자).

지연 임포트: 포맷별 렌더러가 무거운 라이브러리를 쓰므로 요청 포맷만 로드.
알 수 없는 포맷은 PDF 로 정직 폴백(에러 대신 안전).
"""

from __future__ import annotations

from .model import ReportModel

_MIME = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

SUPPORTED_FORMATS = tuple(_MIME.keys())


def render_report(model: ReportModel, fmt: str = "pdf") -> tuple[bytes, str, str]:
    """정본 모델을 원하는 포맷으로 렌더. 반환=(파일 bytes, MIME, 확장자).

    ★W1-C 발행 게이트(R2=R1 리뷰 반영 — 이원화): publish_gate.check_publishable 의
    violations(hard)가 있으면 예외로 차단한다 — approved_by 누락(APPROVED 라벨 사칭)은 항상
    hard, 결정론 금지어·ASSUMPTION 결합은 approval_state가 EXPERT_REVIEWED 이상("승인 트랙")
    일 때만 hard(그 외 DRAFT/MACHINE_VALIDATED는 warnings로만 수집 — 절대 차단하지 않는다).
    warnings 는 render_pdf 로 그대로 전달해 표지에 "⚠ 미검증 단정 표현 N건" 문구로 노출한다.
    위반이 없으면(대다수 기존 DRAFT 보고서) 기존과 동일하게 통과한다(무회귀).

    ★스코프 결정(JSON 직렬화 경로): 이 hard-block은 **바이너리 포맷 렌더(PDF/PPTX/DOCX)에만**
    적용된다. rough_scenario_report._model_to_json 처럼 render_report 를 거치지 않고 JSON을
    직접 만드는 경로는 이 함수를 호출하지 않는다 — 그런 경로는 check_publishable 을 별도로
    호출해 violations/warnings 를 결과 dict 에 정보성으로만 동봉하고 절대 차단하지 않는다
    (JSON은 프리뷰/구조화 소비 채널로 간주 — '발행' 관문은 바이너리 포맷으로 한정).
    """
    from .publish_gate import ReportPublishGateError, check_publishable

    gate = check_publishable(model)
    if not gate.ok:
        raise ReportPublishGateError(gate)

    f = (fmt or "pdf").strip().lower()
    if f not in _MIME:
        f = "pdf"  # 미지원 포맷은 PDF 폴백

    if f == "pdf":
        from .pdf_renderer import render_pdf

        data = render_pdf(model, gate_warnings=gate.warnings)
    elif f == "pptx":
        from .pptx_renderer import render_pptx

        data = render_pptx(model)
    else:  # docx
        from .docx_renderer import render_docx

        data = render_docx(model)

    return data, _MIME[f], f
