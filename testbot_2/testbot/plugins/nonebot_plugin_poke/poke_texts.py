"""Reviewed default poke replies; custom text is filtered without rewriting files."""
import re

DEFAULT_TEXTS = [
    '你再戳！',
    '别戳了别戳了再戳就坏了 555',
    '我爪巴爪巴，球球别再戳了',
    '请不要戳我 >_<',
    '放手啦，不给戳 QAQ',
    '喂 (#`O′) 戳我干嘛！',
    '戳坏了，赔钱！',
    '戳坏了',
    '(。´・ω・) ん?',
    '再戳一下试试？',
    '啊呜，太舒服刚刚竟然睡着了。什么事？',
    '{bot}在呢，怎么啦？',
]

OFFENSIVE = re.compile(r'肥宅|l\s*s\s*p|老色批|死宅|真恶心|你.{0,2}[🐎妈馬]|戳[🔨锤]|真实地址|轰炸机|关闭.{0,8}所有服务|傻[逼比]|啥比|操你|草你|滚[开蛋]|废物|弱智|智障',re.I)
SUGGESTIVE = re.compile(r'那里.{0,8}不能戳|不可以.{0,10}不要乱戳')


def clean_text(text):
    text=str(text).strip()
    if not text or OFFENSIVE.search(text) or SUGGESTIVE.search(text):return ''
    # Old nickname overrides and custom resource files must not leak another name.
    return text.replace('宁宁','{bot}').replace('{nickname}','{bot}')
