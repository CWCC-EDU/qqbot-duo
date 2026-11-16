"""Light result sheet; text remains lossless and readable at normal QQ preview size."""
import base64
import io
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .core import ZONE

@lru_cache(maxsize=16)
def font(size):
    for path in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf','C:/Windows/Fonts/simsun.ttc'):
        if Path(path).is_file(): return ImageFont.truetype(path,size)
    raise OSError('未找到中文字体')

@lru_cache(maxsize=16)
def symbol_font(size,emoji=False):
    for path in (('C:/Windows/Fonts/seguiemj.ttf','C:/Windows/Fonts/seguisym.ttf') if emoji else ('C:/Windows/Fonts/seguisym.ttf','C:/Windows/Fonts/seguiemj.ttf')):
        if Path(path).is_file():return ImageFont.truetype(path,size)
    return font(size)

def draw_text(draw,position,text,f,fill):
    x,y=position
    for part in re.split(r'([\u2600-\u27BF\U0001F000-\U0001FAFF])',str(text)):
        if not part:continue
        actual=symbol_font(f.size,ord(part[0])>0xFFFF) if len(part)==1 and (0x2600<=ord(part)<=0x27BF or ord(part)>0xFFFF) else f
        draw.text((x,y),part,font=actual,fill=fill)
        x+=actual.getlength(part)

def lines(text, f, width):
    result=[]
    for source in str(text).split('\n'):
        current=''
        for char in source:
            if f.getlength(current+char)>width and current:result.append(current);current=char
            else:current+=char
        result.append(current)
    return result

def read_local(value, root):
    if value.startswith('base64://'): return base64.b64decode(value[9:])
    if value.startswith(('http://','https://')): return None
    if value.startswith('file:'):
        value=unquote(urlsplit(value).path)
        if len(value)>2 and value[0]=='/' and value[2]==':':value=value[1:]
    path=Path(value)
    if not path.is_absolute():path=Path(root)/path
    if path.is_file() and path.stat().st_size<=12_000_000:return path.read_bytes()
    return None

def sheet(rows, images, title):
    import datetime,json
    regular,small,bold=font(27),font(22),font(31)
    cards=[]
    for row in rows:
        ops=[];height=98
        for index,part in enumerate(json.loads(row['payload'])):
            if part['type']=='text':
                wrapped=lines(part['text'],regular,486)
                if len(wrapped)>110:wrapped=wrapped[:110]+['（内容过长，请单独查看）']
                ops.append(('text',wrapped));height+=len(wrapped)*38+12
            elif part['type']=='image':
                raw=images.get((row['id'],index))
                try:
                    if raw is None:raise ValueError('无图片')
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.width*source.height>24_000_000:raise ValueError('图片过大')
                        image=ImageOps.exif_transpose(source).convert('RGBA')
                        image.thumbnail((486,390),Image.Resampling.LANCZOS)
                        # Add a light background without changing the source image on disk.
                        ops.append(('image',image.copy()));height+=image.height+18
                except Exception:
                    ops.append(('text',['〔图片暂不可用，文字结果已保留〕']));height+=50
        card=Image.new('RGB',(534,height+16),'white');d=ImageDraw.Draw(card)
        label=f"{row['name']}（{row['uid']}）"
        if bold.getlength(label)>486:
            while label and bold.getlength(label+'…')>486:label=label[:-1]
            label+='…'
        draw_text(d,(24,14),label,bold,'#255B84')
        d.text((24,58),row['kind'],font=small,fill='#698399');y=98
        for kind,value in ops:
            if kind=='image':card.paste(value,((534-value.width)//2,y),value);y+=value.height+18
            else:
                for line in value:draw_text(d,(24,y),line,regular,'#263444');y+=38
                y+=12
        cards.append(card)
    heights=[max(card.height for card in cards[i:i+2]) for i in range(0,len(cards),2)]
    canvas=Image.new('RGB',(1140,146+sum(heights)+24*len(heights)+58),'#EEF5FA');d=ImageDraw.Draw(canvas)
    d.text((36,22),title+' · 本群结果',font=font(38),fill='#294F70')
    d.text((36,80),f"{len(rows)}次操作 · 按发起顺序汇总 · "+datetime.datetime.now(ZONE).strftime('%H:%M'),font=small,fill='#627C91')
    y=140
    for i in range(0,len(cards),2):
        for j,card in enumerate(cards[i:i+2]):canvas.paste(card,(24+j*558,y))
        y+=heights[i//2]+24
    d.text((36,canvas.height-44),'结果已即时结算，本图仅合并展示。',font=small,fill='#627C91')
    out=io.BytesIO();canvas.save(out,format='PNG',compress_level=3)
    return out.getvalue()
