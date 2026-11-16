"""本机绘制的亮色大字决斗面板。"""
from functools import lru_cache
from qqbot_media import cached_render,lossless_png,render_mode
from io import BytesIO
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

WIDTH=900
BG=(241,248,255)
TEXT=(38,68,105)
MUTED=(73,102,133)
ACCENT=(24,119,164)
COLORS=[(83,116,148),(23,121,184),(195,80,62),(37,131,88),(122,87,174),(163,116,29),(171,70,133)]
ATTRIBUTES=['普通','水','火','草','暗','光','？']
STATES=['正常','疲惫','防御','流血','顽强','荆棘','易伤','混乱','时滞','迷惑','失明']

@lru_cache(maxsize=24)
def font(size,bold=False):
    for path in (Path(r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc'),Path(r'C:\Windows\Fonts\simhei.ttf')):
        if path.exists():return ImageFont.truetype(str(path),size)
    return ImageFont.truetype('DejaVuSans.ttf',size)

def clean(value):
    text=re.sub(r'\[CQ:at,qq=(\d+)\]',r'@\1',str(value))
    return re.sub(r'\[CQ:[^\]]+\]','',text).replace('\r','')

def wrap(text,size,width,limit=None):
    f=font(size)
    lines=[]
    for paragraph in clean(text).split('\n'):
        current,length=[],0
        tokens=[]
        for token in re.findall(r'[0-9]+(?:\.[0-9]+)?%?|.',paragraph):
            tokens.extend(list(token) if f.getlength(token)>width else [token])
        for char in tokens:
            measure=f.getlength(char)
            if current and length+measure>width:
                if char in '，。！？；：、）》】”’…' and len(current)>1:
                    tail=current.pop()
                    lines.append(''.join(current))
                    current,length=[tail],f.getlength(tail)
                else:
                    lines.append(''.join(current))
                    current,length=[],0
            current.append(char)
            length+=measure
        lines.append(''.join(current))
    if limit and len(lines)>limit:
        lines=lines[:limit]
        lines[-1]=lines[-1][:-1]+'…'
    return lines

def background(height):
    image=Image.new('RGB',(WIDTH,height),BG)
    draw=ImageDraw.Draw(image)
    for y in range(min(240,height)):
        t=y/240
        draw.line((0,y,WIDTH,y),fill=(int(220+21*t),int(240+8*t),255))
    draw.rectangle((0,0,WIDTH,8),fill=(91,183,207))
    return image

def encode(image):
    return lossless_png(image)

def card(draw,box,color=ACCENT,active=False):
    x,y,right,bottom=box
    draw.rounded_rectangle((x,y+4,right,bottom+4),radius=20,fill=(222,233,243))
    draw.rounded_rectangle(box,radius=20,fill=(255,255,255),outline=color if active else (198,216,232),width=3 if active else 2)

def attribute_details(rules,data,slot):
    mods=data.get('_rule_modifiers',{}).get(slot,{})
    details=[]
    if mods.get('attack',0):details.append(f"临时攻击{mods['attack']:+}级")
    if mods.get('accuracy',0):details.append(f"命中{mods['accuracy']*100:+g}个百分点")
    if mods.get('damage_multiplier',1)!=1:details.append(f"技能伤害{(mods['damage_multiplier']-1)*100:+g}%")
    if mods.get('damage_taken_multiplier',1)!=1:details.append(f"承受技能伤害{(mods['damage_taken_multiplier']-1)*100:+g}%")
    if data[f'attribute{slot}']==3:
        amount=next((t['steps'][0]['amount'] for t in rules.triggers if t['id']=='grass_recovery'),0)
        details.append(f'出招前回复{amount:g}生命，不超过初始上限')
    if data[f'attribute{slot}']==6:details.append('命运骰：15%伤害150%；70%正常；15%伤害50%')
    if data[f'attribute{slot}']==5:details.append('被命中且双方存活：40%使攻击者下次出招命中-15个百分点，不叠加')
    return '特性：'+('；'.join(details) or '无额外加成')

def status_details(rules,status):
    c=rules.constants
    return [
        '状态：当前没有异常或防护状态。',
        '疲惫：下次行动跳过一次，随后解除。',
        f"防御：对手下次技能结算，常规伤害保留{c['defense_multiplier']*100:g}%；随后消耗。固定伤害不统一减免。",
        f"流血：对手行动时受到约{c['bleed_damage']:g}伤害，持续至清除或覆盖。",
        '顽强：对手下次技能结算保留至少1生命，随后消耗。',
        f"荆棘：反弹下次实际伤害的{c['thorns_ratio']*100:g}%；不会把攻击者降至1生命以下。",
        f"易伤：对手下次技能的常规伤害乘{c['vulnerability_multiplier']:g}，随后消耗。",
        f"混乱：下次行动有{c['confusion_probability']*100:g}%概率自伤；常规自伤保留1生命。",
        '时滞：锁住常规状态变化，主动防御可以退出。',
        '迷惑：下次行动自动随机出招，随后解除。',
        '失明：下次行动命中降低40个百分点，随后解除。'
    ][status]

STATE_COLORS=[MUTED,(173,105,31),(29,126,163),(191,62,69),(130,106,29),(40,133,86),
              (194,74,43),(144,79,172),(75,104,175),(150,75,160),(111,97,155)]

def effect_color(token):
    if token.startswith('属性：'):
        label=token[3:]
        return COLORS[ATTRIBUTES.index(label)] if label in ATTRIBUTES else MUTED
    if token in STATES:return STATE_COLORS[STATES.index(token)]
    return MUTED

def draw_effect(draw,xy,text,size=36):
    x,y=xy
    expression='(属性：[普通水火草暗光？]+|'+'|'.join(map(re.escape,sorted(STATES[1:],key=len,reverse=True)))+')'
    for part in re.split(expression,text):
        if part:
            draw.text((x,y),part,font=font(size),fill=effect_color(part))
            x+=font(size).getlength(part)

@cached_render
def render_battle(rules,data,first=1):
    if render_mode()=='旧版':
        from .._legacy_media.battle_ui import render_battle as original
        return original(rules,data,first)
    prefix=data.get('_command_prefix','#')
    label_width=max(font(42,True).getlength(prefix+str(i)) for i in data['skill_choose'])+24
    name_x=47+label_width
    cards=[]
    for index,skill_id in data['skill_choose'].items():
        skill=rules.skills[str(skill_id)]
        names=wrap(skill['name'],38,850-name_x)
        effects=wrap(skill['effect'],36,794)
        cards.append((index,names,effects,24+48*len(names)+46*len(effects)+22))
    players=[]
    for slot in (first,3-first):
        trait=wrap(attribute_details(rules,data,slot),26,370)
        status=wrap(status_details(rules,data[f'state{slot}']),26,370)
        players.append((slot,trait,status,306+34*len(trait)+34*len(status)+24))
    player_height=max(p[-1] for p in players)
    log=[]
    for entry in data.get('_combat_log',[])[-2:]:log.extend(wrap(entry,32,800,8))
    if not log:log=['观察双方属性与状态，选择你的技能。']
    log_height=30+41*len(log)
    footer=wrap(f'{prefix}认输 · {prefix}结算 · {prefix}继续 · {prefix}帮助',30,820)
    height=100+player_height+70+log_height+22+sum(c[-1]+16 for c in cards)+40*len(footer)+76
    image=background(height)
    draw=ImageDraw.Draw(image)
    draw.text((30,25),f"第{data['index']//2+1}回合 · 第{data['index']+1}次行动，共{rules.battle['max_actions']}次",font=font(32,True),fill=TEXT)
    for position,(slot,trait,status,_) in enumerate(players):
        x,y,w=28+position*430,100,414
        color=COLORS[data[f'attribute{slot}']]
        active=data['next']==data[slot]
        card(draw,(x,y,x+w,y+player_height),color,active)
        draw.text((x+20,y+13),wrap(data[f'player{slot}'],36,370,1)[0],font=font(36,True),fill=TEXT)
        role=('先手' if slot==first else '后手')+' · '+('正在行动' if active else '等待对手')
        draw.text((x+20,y+63),role,font=font(28),fill=color if active else MUTED)
        hp=max(0,data[f'blood{slot}'])
        maximum=data[f'max_blood{slot}']
        draw.text((x+20,y+106),f'生命 {hp:g}／{maximum:g}',font=font(36,True),fill=TEXT)
        draw.rounded_rectangle((x+20,y+155,x+w-20,y+174),radius=8,fill=(223,234,242))
        length=(w-40)*max(0,min(1,hp/maximum))
        if length:draw.rounded_rectangle((x+20,y+155,x+20+length,y+174),radius=8,fill=color)
        mods=data.get('_rule_modifiers',{}).get(slot,{})
        attack=max(0,min(12,data[f'atk{slot}']+mods.get('attack',0)))-6
        accuracy=(data[f'accuracy{slot}']+mods.get('accuracy',0))*100
        draw.text((x+20,y+190),f'攻击 {attack:+}  命中 {accuracy:g}%',font=font(32,True),fill=TEXT)
        attr=ATTRIBUTES[data[f'attribute{slot}']]+'系'
        draw.text((x+20,y+237),attr,font=font(30,True),fill=color)
        draw.text((x+130,y+237),STATES[data[f'state{slot}']],font=font(30,True),fill=STATE_COLORS[data[f'state{slot}']])
        ty=y+283
        for line in trait:
            draw.text((x+20,ty),line,font=font(26),fill=color)
            ty+=34
        ty+=16
        for line in status:
            draw.text((x+20,ty),line,font=font(26),fill=STATE_COLORS[data[f'state{slot}']])
            ty+=34
    y=100+player_height+22
    draw.text((32,y),'最近战况',font=font(34,True),fill=TEXT)
    y+=48
    card(draw,(28,y,872,y+log_height))
    for i,line in enumerate(log):draw.text((48,y+15+41*i),line,font=font(32),fill=MUTED)
    y+=log_height+22
    for index,names,effects,card_height in cards:
        card(draw,(28,y,872,y+card_height))
        draw.text((47,y+17),f'{prefix}{index}',font=font(42,True),fill=ACCENT)
        ty=y+17
        for name in names:
            draw.text((name_x,ty),name,font=font(38,True),fill=TEXT)
            ty+=48
        ty+=8
        for effect in effects:
            draw_effect(draw,(48,ty),effect)
            ty+=46
        y+=card_height+16
    for line in footer:
        draw.text((32,y+8),line,font=font(30,True),fill=ACCENT)
        y+=40
    draw.text((32,y+14),'切换文字：'+prefix+'文字',font=font(32),fill=MUTED)
    return encode(image)


def title_for(text):
    text=str(text)
    if text.startswith('结算：') or '决斗结束：' in text:return '决斗结算'
    if text.startswith('【决斗手册】'):return '决斗机制介绍'
    if '发起决斗' in text:return '决斗邀请'
    return '对局播报'

def document_lines(text):
    rows=[]
    for paragraph in clean(text).split('\n'):
        heading=paragraph.startswith('【')
        for line in wrap(paragraph,38 if heading else 34,800):rows.append((line,heading))
    return rows

def draw_document(title,rows,page=None):
    height=160+sum(54 if heading else 46 for _,heading in rows)+36
    image=background(height)
    draw=ImageDraw.Draw(image)
    draw.text((32,27),title,font=font(44,True),fill=TEXT)
    label='群友决斗 · 规则与战况' if page is None else f'第{page[0]}页，共{page[1]}页'
    draw.text((34,87),label,font=font(30),fill=ACCENT)
    draw.line((30,137,870,137),fill=(175,211,231),width=2)
    y=157
    for line,heading in rows:
        draw.text((39,y),line,font=font(38 if heading else 34,heading),fill=ACCENT if heading else TEXT)
        y+=54 if heading else 46
    return encode(image)

def render_document(title,text):return draw_document(title,document_lines(text))
def render_notice(text):return render_document(title_for(text),text)

def render_pages(text):
    rows=document_lines(text)
    groups=[]
    group=[]
    used=0
    for row in rows:
        cost=54 if row[1] else 46
        if used+cost+(46 if row[1] else 0)>1320 and group:
            groups.append(group)
            group,used=[],0
        group.append(row)
        used+=cost
    if group:groups.append(group)
    return [draw_document(title_for(text),rows,(index+1,len(groups)) if len(groups)>1 else None) for index,rows in enumerate(groups)]
