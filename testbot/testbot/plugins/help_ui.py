"""Single-image cards shared by help and the collection album."""
from pathlib import Path
from io import BytesIO
from functools import lru_cache
from qqbot_media import cached_render,lossless_png,render_mode
from PIL import Image,ImageDraw,ImageFont

@lru_cache(maxsize=24)
def font(size):
    from nonebot_plugin_rollpig_plus import __file__ as package_file
    return ImageFont.truetype(str(Path(package_file).parent/'resource/fonts/SourceHanSansSC-Medium.otf'),size)

def wrap(text,draw,f,width):
    lines=[]
    for paragraph in str(text).split('\n'):
        line=''
        for char in paragraph:
            if line and draw.textlength(line+char,font=f)>width:lines.append(line);line=char
            else:line+=char
        lines.append(line)
    return lines

@cached_render
def render_sheet(name,title,subtitle,sections,columns=2,footer='指令中的 / 表示任选一种；文字帮助可查看完整说明'):
    if render_mode()=='旧版':
        from ._legacy_media.help_ui import render_sheet as original
        return original(name,title,subtitle,sections,columns,footer)
    width=1440 if columns>1 else 1080
    gap=20;margin=28;card_width=(width-margin*2-gap*(columns-1))//columns
    body=font(32);heading=font(35);small=font(26);large=font(48)
    accent='#bd6654' if name=='千鸟酱' else '#6082b3'
    bg='#fff7f0' if name=='千鸟酱' else '#f1f7ff'
    tint='#ffebe0' if name=='千鸟酱' else '#e5efff'
    probe=Image.new('RGB',(10,10));draw=ImageDraw.Draw(probe)
    heights=[204]*columns;placements=[]
    for label,rows in sections:
        lines=[]
        for row in rows:lines.extend(wrap(row,draw,body,card_width-42))
        h=72+len(lines)*43+18
        column=min(range(columns),key=lambda c:heights[c])
        placements.append((margin+column*(card_width+gap),heights[column],label,lines,h))
        heights[column]+=h+gap
    height=max(heights)+74
    im=Image.new('RGB',(width,height),bg);d=ImageDraw.Draw(im)
    d.rounded_rectangle((margin,24,width-margin,180),radius=24,fill=tint)
    d.text((margin+26,42),name+' · '+title,font=large,fill=accent)
    for i,line in enumerate(wrap(subtitle,d,small,width-110)):
        d.text((margin+28,112+i*31),line,font=small,fill='#526477')
    for x,y,label,lines,h in placements:
        d.rounded_rectangle((x,y,x+card_width,y+h),radius=18,fill='white',outline='#e3e7ec',width=2)
        d.text((x+20,y+14),label,font=heading,fill=accent)
        for i,line in enumerate(lines):d.text((x+20,y+66+i*43),line,font=body,fill='#34465a')
    for i,line in enumerate(wrap(footer,d,small,width-80)):
        d.text((40,height-60+i*30),line,font=small,fill='#627283')
    return lossless_png(im)

def render_help(name,level,topic,sections):
    role=('大家都能用','群内管理可见','机器人超管可见')[level]
    return [render_sheet(name,'功能目录' if topic=='全部' else topic+'帮助',role+' · 直接发指令；详细用法：文字帮助 '+('管理' if topic=='管理' else topic if topic!='全部' else '日常'),sections)]

def render_collection(name,title,rows):
    if not rows:rows=['还没有藏品。签到和决斗都可能留下新的纪念。']
    columns=3 if len(rows)>20 else 2 if len(rows)>8 else 1
    size=(len(rows)+columns-1)//columns
    sections=[('藏品' if columns==1 else f'藏品 {i+1}～{min(i+size,len(rows))}',rows[i:i+size]) for i in range(0,len(rows),size)]
    return render_sheet(name,title,'藏品列表 看自己的收藏 · 藏品图鉴 看全部 · 查看藏品 名称 看详情',sections,columns,footer='图片发不出来时：文字藏品列表 / 文字藏品图鉴 / 文字查看藏品 名称')
