"""Place an end suffix inside sentence punctuation, without breaking kaomoji."""
import re

END = re.compile(r'''[。！？!?，,、；;：:…⋯.～~“”‘’"'「」『』]+$''')
# Parentheses/CJK brackets are common kaomoji boundaries, not sentence terminators.
CLOSING = re.compile(r'[)）\]】]$')


def append_tail(text,word='喵'):
    text=str(text)
    body=text.rstrip();spaces=text[len(body):]
    if not body:return text
    if re.search(r'[（(][^()（）\n\u4e00-\u9fff]{1,32}[）)]\s*[ぁ-んァ-ン]{0,3}[?？!！~～]*$',body):return body+word+spaces
    if CLOSING.search(body):return body+word+spaces
    match=END.search(body)
    if not match:return body+word+spaces
    # Preserve standalone/emotive ASCII faces such as >_<!, ^_^~ and T_T...
    left=body[:match.start()]
    if re.search(r'(?:[>＾^TQA;；=][^\s\u4e00-\u9fff]{0,4}[_ω口▽﹏ДДvVд][^\s\u4e00-\u9fff]{0,4}[<＾^TQA;；=]|QAQ|TAT|qwq|QwQ)$',left,re.I):
        return body+word+spaces
    return left+word+match.group()+spaces
