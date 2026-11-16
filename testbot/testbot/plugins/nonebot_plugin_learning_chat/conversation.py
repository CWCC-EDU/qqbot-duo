"""Bounded local group context and batching, independently implemented."""
from collections import deque
from dataclasses import dataclass
import re,time
from testbot.plugins.persona_utils import attack

COMMAND=re.compile(r'^(?:问答概率|问答触发概率|设置问答|本群问答|当前群问答|本地问答|设置本群问答|设置当前群问答|设置本地问答|模型分工|模型配置|签到|当前好感|好感位次|排行$|求签$|改签$|今日小猪|藏品|查看藏品|新增藏品|授予藏品|增加好感|减少好感|赛马|发起决斗|接受$|拒绝$|决斗|娶群友|离婚|分手|扔瓶子|捡瓶子|公告|帮助|菜单$|功能$|禁言机器人|解除禁言机器人|机器人禁言状态|开启|关闭|智能|云聊|我的画像|群友画像|我的记忆|记住|忘记记忆|清空|学到的知识|知识详情|确认知识|删除知识|人格$|同步小猪)')
ACK=re.compile(r'^(?:[哈啊哦嗯额好6]+|谢谢(?:你)?[啦啊]?|多谢|谢啦|收到|好的|ok|晚安|早安)[!！。~～]*$',re.I)

def conversational(text):
    return bool(text.strip()) and len(text)<=180 and not attack(text) and not COMMAND.search(text) and not text.startswith(('#','\\','/','.','!','！')) and not re.search(r'https?://|\[CQ:|&#91;CQ:',text,re.I)

@dataclass
class Turn:
    uid:str
    speaker:str
    mid:str
    text:str
    at:float
    bot:bool=False
    reply_to:str=''

@dataclass
class RecentImage:
    uid:str
    speaker:str
    mid:str
    data:dict
    at:float
    description:str=''
    attempted:bool=False

class Conversation:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.turns=deque(maxlen=16);self.images=deque(maxlen=4)
    def clear(self):self.turns.clear();self.images.clear()
    def prune(self):
        while self.turns and self.clock()-self.turns[0].at>600:self.turns.popleft()
        while self.images and self.clock()-self.images[0].at>120:self.images.popleft()
    def add_image(self,uid,speaker,mid,data):
        self.prune()
        if any(p.uid==str(uid) and p.mid==str(mid) for p in self.images):return
        # Only OneBot references are kept, never bytes, paths in model prompts,
        # persistent image history, or unbounded segment dictionaries.
        clean={k:str(data[k])[:4096] for k in ('url','file') if data.get(k)}
        if not clean:return
        speaker=re.sub(r'[\r\n\t\[\]{}<>]','',str(speaker))[:12] or '群友'
        self.images.append(RecentImage(str(uid),speaker,str(mid),clean,self.clock()))
    def related_image(self,uid,reply_mid=''):
        self.prune()
        if reply_mid:
            return next((p for p in reversed(self.images) if p.mid==str(reply_mid)),None)
        return next((p for p in reversed(self.images) if p.uid==str(uid)),None)
    def image_context(self,picture):
        return {'发言者':picture.speaker,'账号':picture.uid,'消息编号':picture.mid,
                '来源':'近期图片识别，可能不准确' if picture.description else '近期图片，未能识别',
                '内容':picture.description[:150] if picture.description else '不知道图片具体内容，不能据此编造细节。'}
    def add(self,uid,speaker,mid,text,bot=False,reply_to=''):
        self.prune()
        if not conversational(text):return False
        if any(t.mid==str(mid) and t.uid==str(uid) for t in self.turns):return False
        speaker=re.sub(r'[\r\n\t\[\]{}<>]','',str(speaker))[:12] or '群友'
        self.turns.append(Turn(str(uid),speaker,str(mid),text[:180],self.clock(),bot,str(reply_to)));return True
    def context(self,uid,current):
        self.prune()
        # Display names and chat content remain data, never trusted instructions.
        return [{'发言者':t.speaker,'账号':t.uid,'回复账号':t.reply_to,'身份':'机器人' if t.bot else '群友','内容':t.text[:80]} for t in self.turns if not (t.uid==str(uid) and t.text==current)][-6:]
    def merge(self,uid,mid):
        self.prune();turns=list(self.turns)
        for i,turn in enumerate(turns):
            if turn.uid==str(uid) and turn.mid==str(mid):
                text=turn.text;last=turn.mid
                for next_turn in turns[i+1:i+4]:
                    if next_turn.bot or next_turn.uid!=turn.uid or next_turn.at-turn.at>3 or len(text)+len(next_turn.text)+1>180:break
                    text+='\n'+next_turn.text;last=next_turn.mid
                return text,last
        return None,None
    def signals(self):
        self.prune();now=self.clock();recent=[t for t in self.turns if now-t.at<90]
        return {'speakers':len({t.uid for t in recent if not t.bot}),'recent_bot':any(t.bot for t in recent),'messages':len(recent)}
