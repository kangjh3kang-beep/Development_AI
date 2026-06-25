"""reportlab Paragraph/Table 동적문자열 XML 이스케이프 공용 헬퍼(전역 전파방지).

[왜 필요한가 — 쉬운 설명]
reportlab 의 Paragraph 는 텍스트를 작은 HTML/XML 로 본다. 그래서 사용자·엔진이 만든
동적 문자열(주소·근거값·법령명 등)에 '<', '>', '&' 같은 글자나 '</para>' 같은 태그가
섞여 들어오면 reportlab 이 "태그가 깨졌다"며 ValueError 를 던지고, 그게 그대로
HTTP 500 으로 새어 나간다. PDF 빌더들은 docstring 에서 'graceful(크래시 없음)'을
약속하므로 이는 약속 위반이다.

[해결 — 한 곳을 고치면 전역이 따라온다]
모든 PDF 빌더(decision_brief·persona urban/developer/constructor/designer)가 이 공용
_esc 를 Paragraph/Table 셀에 주입하기 직전에 적용한다. _esc 는 try/except 로 오류를
은폐하지 않고, 원문을 XML 안전 문자열로 바꿔 '정상 렌더'시키는 것이 정답이다.

[의도적 마크업은 건드리지 않는다]
'<b>강조</b>' 같이 빌더가 의도적으로 넣는 인라인 태그는 _esc 로 감싸면 안 된다(글자가
그대로 보이게 되어 스타일 회귀). 그런 헤더/라벨은 호출부에서 _esc 를 적용하지 않거나,
정적 상수라 애초에 동적 입력이 아니므로 이스케이프 대상이 아니다.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape as _xml_escape


def esc(text: Any) -> str:
    """동적 텍스트를 reportlab Paragraph/Table 에 넣어도 안전한 XML 문자열로 바꾼다.

    '<' → '&lt;', '>' → '&gt;', '&' → '&amp;' 만 치환한다(원문 보존·은폐 없음).
    None 은 빈 문자열로(가짜값 생성 아님 — 호출부에서 이미 '미확보' 등을 결정한 뒤 들어온다).
    문자열이 아니면 str() 로 강제한 뒤 이스케이프한다(예: 숫자·bool 라벨).
    """
    if text is None:
        return ""
    return _xml_escape(str(text))
