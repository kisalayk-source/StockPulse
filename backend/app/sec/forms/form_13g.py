from __future__ import annotations

from app.sec.forms.form_13d import parse_13d


def parse_13g(xml_text: str, form_type: str = "SC 13G", is_amendment: bool = False):
    result = parse_13d(xml_text, form_type=form_type, is_amendment=is_amendment)
    if result is not None:
        result.passive_flag = True
    return result
