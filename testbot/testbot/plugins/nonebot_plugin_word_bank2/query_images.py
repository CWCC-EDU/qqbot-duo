"""Render only a selected word-bank page; return bounded, lossless PNG panels."""
import asyncio
import base64
import io
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote,urlsplit
import httpx
from PIL import Image,ImageDraw,ImageFont,ImageOps

ROOT=Path(__file__).resolve().parents[3]
WIDTH=1080
HEIGHT=2400
MAX_PANELS=20
MAX_OUTPUT_BYTES=16_000_000
MAX_BATCH_PANELS=20
MAX_BATCH_BYTES=16_000_000

@lru_cache(maxsize=12)
def font(size,symbol=False):
    paths=('C:/Windows/Fonts/seguisym.ttf','C:/Windows/Fonts/seguiemj.ttf') if symbol else ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf','C:/Windows/Fonts/simsun.ttc')
    for path in paths:
        if Path(path).is_file():return ImageFont.truetype(path,size)
    if symbol:return font(size)
    raise OSError('未找到中文字体')

def draw_line(draw,pos,text,f,color):
    x,y=pos
    for chunk in re.split(r'([\u2600-\u27BF\U0001F000-\U0001FAFF])',text):
        if not chunk:continue
        chosen=font(f.size,True) if len(chunk)==1 and (0x2600<=ord(chunk)<=0x27BF or ord(chunk)>0xFFFF) else f
        draw.text((x,y),chunk,font=chosen,fill=color);x+=chosen.getlength(chunk)

def wrap(text,f,width):
    result=[]
    for source in text.split('\n'):
        line=''
        for char in source:
            if f.getlength(line+char)>width and line:result.append(line);line=char
            else:line+=char
        result.append(line)
    return result

def local_image(value):
    if value.startswith('base64://'):
        if len(value)>12_000_000:raise ValueError('图片过大')
        return base64.b64decode(value[9:])
    if value.startswith('file:'):
        parsed=urlsplit(value);value=unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in ('localhost','127.0.0.1'):value=parsed.netloc+value
        if len(value)>2 and value[0]=='/' and value[2]==':':value=value[1:]
    path=Path(value)
    if not path.is_absolute():path=ROOT/path
    if not path.is_file() or path.stat().st_size>8_000_000:return None
    return path.read_bytes()

async def media(nodes):
    from nonebot.adapters.onebot.v11 import Message
    found={};jobs=[]
    for i,node in enumerate(nodes):
        for j,segment in enumerate(Message(node['data']['content'])):
            if segment.type=='image':jobs.append((i,j,str(segment.data.get('file') or segment.data.get('url') or '')))
    async with httpx.AsyncClient(timeout=3,follow_redirects=True) as client:
        async def load(i,j,value):
            try:
                if value.startswith(('http://','https://')):
                    async with client.stream('GET',value) as response:
                        response.raise_for_status();buf=bytearray()
                        async for chunk in response.aiter_bytes():
                            buf.extend(chunk)
                            if len(buf)>8_000_000:raise ValueError('图片过大')
                        raw=bytes(buf)
                else:raw=await asyncio.to_thread(local_image,value)
                if raw:found[i,j]=raw
            except Exception:pass
        await asyncio.gather(*(load(*job) for job in jobs))
    return found

def render(nodes,pictures,page,total,count):
    from nonebot.adapters.onebot.v11 import Message
    normal=font(30);small=font(23);label=font(25)
    output=[];canvas=None;draw=None;y=0
    def start():
        nonlocal canvas,draw,y
        canvas=Image.new('RGB',(WIDTH,HEIGHT),'#F1F6FB');draw=ImageDraw.Draw(canvas)
        draw.text((36,22),'群词库',font=font(40),fill='#28577D')
        draw.text((36,80),f'第{page}/{total}页 · 共{count}个词条 · 本页图{len(output)+1}',font=small,fill='#648099')
        y=135
    def finish():
        image=canvas.crop((0,0,WIDTH,min(HEIGHT,y+35)))
        buf=io.BytesIO();image.save(buf,format='PNG',compress_level=6);output.append(buf.getvalue())
    def room(height):
        if y+height>HEIGHT-40:
            finish()
            if len(output)>=MAX_PANELS:raise ValueError('本页图片过长')
            start()
    start()
    for i,node in enumerate(nodes):
        content=Message(node['data']['content'])
        estimate=65
        for segment in content:
            if segment.type=='image':estimate+=440
            else:
                text=segment.data.get('text','') if segment.type=='text' else '〔表情〕'
                estimate+=len(wrap(text,normal,WIDTH-88))*43
        room(min(estimate,HEIGHT-200))
        draw.rounded_rectangle((28,y-2,WIDTH-28,y+31),radius=8,fill='#DFECF6')
        draw.text((44,y),f'本页记录 {i+1}',font=label,fill='#416784');y+=45
        for j,segment in enumerate(content):
            if segment.type=='image':
                try:
                    raw=pictures.get((i,j))
                    if not raw:raise ValueError('无图片')
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.width*source.height>20_000_000:raise ValueError('图片过大')
                        picture=ImageOps.exif_transpose(source).convert('RGBA')
                        picture.thumbnail((900,420),Image.Resampling.LANCZOS)
                        room(picture.height+20)
                        draw.rectangle((36,y,WIDTH-36,y+picture.height+4),fill='white')
                        canvas.paste(picture,((WIDTH-picture.width)//2,y),picture)
                        y+=picture.height+20
                except Exception:
                    room(44);draw.text((44,y),'〔这张图片暂时读不到，原词条未改动〕',font=small,fill='#7D7481');y+=44
                continue
            text=segment.data.get('text','') if segment.type=='text' else '@'+str(segment.data.get('qq','')) if segment.type=='at' else '〔表情〕' if segment.type=='face' else '〔'+segment.type+'〕'
            for line in wrap(text,normal,WIDTH-88):
                room(43);draw_line(draw,(44,y),line,normal,'#273B4A');y+=43
        y+=20
    finish()
    if sum(len(x) for x in output)>MAX_OUTPUT_BYTES:raise ValueError('本页图片体积过大')
    return output

async def build(nodes,page,total,count):
    pictures=await asyncio.wait_for(media(nodes),5)
    return await asyncio.wait_for(asyncio.to_thread(render,nodes,pictures,page,total,count),15)

def iter_panels(nodes):
    """Plan by rendered image height, independent of the old text-query pages."""
    from nonebot.adapters.onebot.v11 import Message
    normal=font(30);capacity=HEIGHT-175;panel=[];used=0
    for index,node in enumerate(nodes,1):
        ops=[('label',f'记录 {index}',45)]
        for segment in Message(node['data']['content']):
            if segment.type=='image':
                value=str(segment.data.get('file') or segment.data.get('url') or '')
                ops.append(('image',value,440))
            else:
                text=segment.data.get('text','') if segment.type=='text' else '@'+str(segment.data.get('qq','')) if segment.type=='at' else '〔表情〕'
                ops.extend(('text',line,43) for line in wrap(text,normal,WIDTH-88))
        ops.append(('gap','',20))
        if panel and sum(x[2] for x in ops)<=capacity and used+sum(x[2] for x in ops)>capacity:
            yield panel;panel=[];used=0
        for position,op in enumerate(ops):
            if panel and used+op[2]>capacity:
                yield panel;panel=[];used=0
                if position:
                    panel.append(('label',f'记录 {index}（续）',45));used=45
            panel.append(op);used+=op[2]
    if panel:yield panel

def choose_panels(nodes,start,limit=MAX_BATCH_PANELS):
    selected=[];total=0
    for total,ops in enumerate(iter_panels(nodes),1):
        if start<=total<start+limit:selected.append(ops)
    return selected,total

async def selected_media(plans):
    """Only the selected images are read; at most four downloads run together."""
    values=list(dict.fromkeys(op[1] for ops in plans for op in ops if op[0]=='image'))
    output={};semaphore=asyncio.Semaphore(4);used=0
    async with httpx.AsyncClient(timeout=3,follow_redirects=True) as client:
        async def load(value):
            nonlocal used
            async with semaphore:
                if used>=32_000_000:return
                try:
                    if value.startswith(('http://','https://')):
                        async with client.stream('GET',value) as response:
                            response.raise_for_status();buffer=bytearray()
                            async for chunk in response.aiter_bytes():
                                buffer.extend(chunk)
                                if len(buffer)>8_000_000:raise ValueError('原图片过大')
                            raw=bytes(buffer)
                    else:raw=await asyncio.to_thread(local_image,value)
                    if raw and used+len(raw)<=32_000_000:output[value]=raw;used+=len(raw)
                except Exception:pass
        tasks=[asyncio.create_task(load(value)) for value in values]
        if tasks:
            done,pending=await asyncio.wait(tasks,timeout=6)
            for task in pending:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    return output

def render_batch(plans,pictures,start,total,count):
    normal=font(30);small=font(23);label=font(25);result=[];size=0
    for offset,ops in enumerate(plans):
        canvas=Image.new('RGB',(WIDTH,HEIGHT),'#F1F6FB');draw=ImageDraw.Draw(canvas)
        draw.text((36,22),'群词库',font=font(40),fill='#28577D')
        draw.text((36,80),f'第{start+offset}/{total}张 · 共{count}个词条',font=small,fill='#648099');y=135
        for kind,value,height in ops:
            if kind=='label':
                draw.rounded_rectangle((28,y-2,WIDTH-28,y+31),radius=8,fill='#DFECF6')
                draw.text((44,y),value,font=label,fill='#416784')
            elif kind=='text':draw_line(draw,(44,y),value,normal,'#273B4A')
            elif kind=='image':
                try:
                    raw=pictures.get(value)
                    if not raw:raise ValueError('原图片不可用')
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.width*source.height>20_000_000:raise ValueError('原图片过大')
                        image=ImageOps.exif_transpose(source).convert('RGBA');image.thumbnail((900,420),Image.Resampling.LANCZOS)
                        draw.rectangle((36,y,WIDTH-36,y+420),fill='white')
                        canvas.paste(image,((WIDTH-image.width)//2,y),image)
                except Exception:draw.text((44,y),'〔原图片暂时读不到，文字和词条未改动〕',font=small,fill='#7D7481')
            y+=height
        buffer=io.BytesIO();canvas.crop((0,0,WIDTH,min(HEIGHT,y+35))).save(buffer,format='PNG',compress_level=6)
        raw=buffer.getvalue()
        if result and size+len(raw)>MAX_BATCH_BYTES:break
        result.append(raw);size+=len(raw)
    return result

async def build_batch(plans,start,total,count):
    pictures=await selected_media(plans)
    return await asyncio.wait_for(asyncio.to_thread(render_batch,plans,pictures,start,total,count),45)
