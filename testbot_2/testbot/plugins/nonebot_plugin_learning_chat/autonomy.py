"""Local attention gate before a single model decision/reply request."""
from dataclasses import dataclass,field
import random,re,time
from .conversation import ACK,conversational

QUESTION=re.compile(r'怎么|如何|为什么|为啥|咋办|怎么办|能不能|可不可以|有没有|谁知道|谁懂|求助|推荐|纠结|[?？]')
SHARE=re.compile(r'今天|刚刚|终于|居然|没想到|好像|我觉得|真的|笑死|好玩|好累|下班|开黑|通关|抽到|翻车|开心|难过|好无聊')

@dataclass
class LocalGate:
    last_attempt:float=-1e20
    recent:dict=field(default_factory=dict)
    waits:int=0
    until:float=0
    def result(self,silent,now=None):
        now=time.monotonic() if now is None else now
        self.waits=self.waits+1 if silent else 0
        self.until=now+min(300,30*2**min(self.waits-2,3)) if self.waits>=2 else 0
    def choose(self,text,*,quoted=False,segments=('text',),interval=45,probability=.45,now=None,roll=None,room=None):
        now=time.monotonic() if now is None else now;room=room or {}
        if quoted or any(kind!='text' for kind in segments) or not conversational(text) or ACK.fullmatch(text):return False
        if not 4<=len(text)<=160 or len(set(re.sub(r'\W','',text)))<3:return False
        question=bool(QUESTION.search(text));sharing=bool(SHARE.search(text));following=bool(room.get('recent_bot'))
        if not (question or sharing or following):return False
        key=re.sub(r'\s+','',text).lower();self.recent={k:v for k,v in self.recent.items() if now-v<600}
        if now<self.until or now-self.last_attempt<interval or key in self.recent:return False
        # Reply opportunities grow with genuine interaction, rather than every
        # message causing a paid planner invocation.
        chance=min(.85,probability*(1.2 if question else .8)*(1.15 if following else 1)*(1.1 if room.get('speakers',0)>=2 else 1))
        if (random.random() if roll is None else roll)>=chance:return False
        self.last_attempt=now;self.recent[key]=now
        if len(self.recent)>64:self.recent.pop(next(iter(self.recent)))
        return True
