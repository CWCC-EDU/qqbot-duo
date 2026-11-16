"""Word-bank image batches: up to 20 rendered images in one merged forward."""
import asyncio
import json
import re
import time
from nonebot import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

MAX_NODES=20                 # Includes the page header.
MAX_BYTES=24000              # Conservative local budget, not a claimed QQ limit.
MAX_IMAGES=4
MAX_PLAIN=2200
TEXT_CHUNK=800
SEND_TIMEOUT=15
MAX_BATCH_IMAGES=20
_busy=set()
_last={}

def options(value):
    text=value.strip();plain=False;page=1;start=None
    if re.search(r'(?:^|\s)(?:文字|图片)$',text):
        plain=bool(re.search(r'(?:^|\s)文字$',text))
        text=re.sub(r'(?:^|\s)(?:文字|图片)$','',text).rstrip()
    cursor=re.search(r'(?:^|\s)从第([0-9]+)张$',text)
    if cursor:
        if len(cursor[1])>8 or int(cursor[1])<1:raise ValueError('图片序号请从第1张开始。')
        start=int(cursor[1]);text=text[:cursor.start()].rstrip()
    found=re.search(r'(?:^|\s)第([0-9]+)页$',text)
    if found:
        digits=found[1]
        if len(digits)>8 or int(digits)<1:raise ValueError('页码请从第1页开始。')
        page=int(digits);text=text[:found.start()].rstrip()
    return text,page,plain,start

def plain(message):
    result=[]
    for segment in Message(message):
        kind=segment.type
        if kind=='text':result.append(segment.data.get('text',''))
        elif kind=='at':result.append('@'+str(segment.data.get('qq','')))
        else:result.append({'image':'〔图片〕','face':'〔表情〕','record':'〔语音〕','video':'〔视频〕'}.get(kind,'〔'+kind+'〕'))
    return ''.join(result)

def fragments(message):
    for segment in Message(message):
        if segment.type=='text':
            text=segment.data.get('text','')
            for start in range(0,len(text),TEXT_CHUNK):yield Message(MessageSegment.text(text[start:start+TEXT_CHUNK]))
        elif segment.type in ('image','face'):
            candidate=Message(segment)
            if len(json.dumps(candidate,ensure_ascii=False,default=str).encode('utf-8'))>8000:
                yield Message(MessageSegment.text('〔图片内容过大，查询中仅显示占位，原回复不变〕'))
            else:yield candidate
        elif segment.type=='reply':continue
        else:yield Message(MessageSegment.text(plain(Message(segment))))

def node(content,sid):
    return {'type':'node','data':{'name':'词库查询','uin':str(sid),'content':content}}

def iter_nodes(entries,sid):
    for number,entry in enumerate(entries,1):
        # Snapshot a value list so a concurrent edit cannot extend this iterator.
        for part in (list(fragments(entry.key)) or [Message('')]):
            yield node(MessageSegment.text(f'〔词条{number}〕问：\n')+part,sid)
        question=plain(entry.key).replace('\n',' ')[:80]
        for answer,value in enumerate(list(entry.values),1):
            for part in fragments(value):
                heading=f'〔词条{number} · 回答{answer}〕{question}\n答：'
                yield node(MessageSegment.text(heading)+part,sid)

def choose_page(entries,sid,wanted):
    page=1;current=[];cost=1400;images=0;characters=0;selected=None
    for item in iter_nodes(entries,sid):
        raw=len(json.dumps(item,ensure_ascii=False,default=str).encode('utf-8'))
        picture_count=len(Message(item['data']['content'])['image'])
        text_size=len(plain(item['data']['content']))+2
        if current and (len(current)>=MAX_NODES-1 or cost+raw>MAX_BYTES or
                        images+picture_count>MAX_IMAGES or characters+text_size>MAX_PLAIN):
            if page==wanted:selected=current
            page+=1;current=[];cost=1400;images=0;characters=0
        current.append(item);cost+=raw;images+=picture_count;characters+=text_size
    if current and page==wanted:selected=current
    return selected,page

def query_base(event,typed):
    source=event.get_plaintext().strip()
    heading=source.split('词库',1)[0]+'词库'
    return (heading+' '+typed).rstrip()

def status_text(base,page,total,entries,failed=False):
    prefix='合并转发没发出，先用文字显示这一页。\n' if failed else ''
    # Avoid a huge command itself becoming a huge forward header.
    next_command=f'{base} 第{page+1}页' if len(base)<=350 else f'原查询末尾加“第{page+1}页”'
    text=f'{prefix}词库：共{entries}个词条，第{page}/{total}页。'
    if page<total:text+='\n下一页：'+next_command
    text+='\n文字查看：'+(f'{base} 第{page}页 文字' if len(base)<=350 else f'原查询末尾加“第{page}页 文字”')
    return text

def image_status(base,start,amount,total,entries):
    end=start+amount-1
    text=f'词库：共{entries}个词条、{total}张图片。\n本次第{start}～{end}张，共{amount}张。'
    if end<total:
        text+='\n继续查看：'+(f'{base} 从第{end+1}张' if len(base)<=350 else f'原查询末尾加“从第{end+1}张”')
    text+='\n文字模式独立分页：'+(f'{base} 第1页 文字' if len(base)<=350 else '原查询末尾加“第1页 文字”')
    return text

async def run_search(bot,event,matcher,matched,wb,get_session_id,MatchType):
    scope_id=(str(bot.self_id),get_session_id(event))
    now=time.monotonic()
    if scope_id in _busy or now-_last.get(scope_id,-1000)<3:return
    _busy.add(scope_id)
    try:
        if len(matched)==2:
            scope='群' if isinstance(event,GroupMessageEvent) else '用户'
            identifier=event.group_id if isinstance(event,GroupMessageEvent) else event.user_id
            flag,raw_key=matched
        else:scope,identifier,flag,raw_key=matched
        if scope not in ('','群','用户'):
            await matcher.send('请使用“查询词库”或“查询群 群号 词库”。');return
        if scope and not identifier:
            await matcher.send(f'请填写{scope}ID');return
        try:typed,page,text_only,start=options(raw_key)
        except ValueError as exc:await matcher.send(str(exc));return
        base=query_base(event,typed);keyword=typed
        index='0' if '全局' in flag else get_session_id(event) if not scope else {'群':'group','用户':'private'}[scope]+f'_{identifier}'
        mode=MatchType.regex if '正则' in flag else MatchType.include if '模糊' in flag else MatchType.congruence
        require_to_me='@' in flag
        if not require_to_me:
            for name in sorted(bot.config.nickname,key=len,reverse=True):
                if name and keyword.startswith(name):keyword=keyword[len(name):];require_to_me=True;break
        entries=await asyncio.to_thread(wb.select,index,mode,Message(keyword),require_to_me)
        if not entries:await matcher.send('词库中未找到词条~');return
        if text_only:
            nodes,total=await asyncio.to_thread(choose_page,entries,bot.self_id,page)
            if not nodes:
                await matcher.send(f'文字共{total}页，没有第{page}页。');return
            header='文字模式 · '+status_text(base,page,total,len(entries))
            text=header+'\n\n'+'\n\n'.join(plain(x['data']['content']) for x in nodes)
            await asyncio.wait_for(matcher.send(Message(MessageSegment.text(text))),8);return
        fallback=f'{base} 第1页 文字' if len(base)<=350 else '原查询末尾加“第1页 文字”'
        try:
            from .query_images import choose_panels,build_batch
            start=start or (page-1)*MAX_BATCH_IMAGES+1
            plans,total=await asyncio.to_thread(choose_panels,iter_nodes(entries,bot.self_id),start,MAX_BATCH_IMAGES)
            if not plans:
                await matcher.send(f'共{total}张词库图片，没有第{start}张。');return
            panels=await build_batch(plans,start,total,len(entries))
            header=image_status(base,start,len(panels),total,len(entries))
            messages=[node(Message(MessageSegment.text(header)),bot.self_id)]
            messages.extend(node(Message(MessageSegment.image(raw)),bot.self_id) for raw in panels)
        except Exception as exc:
            logger.warning('词库图片排版失败：'+type(exc).__name__)
            await asyncio.wait_for(matcher.send(Message(MessageSegment.text('图片没排出来，可以先用文字查看：\n'+fallback))),8)
            return
        api='send_group_forward_msg' if isinstance(event,GroupMessageEvent) else 'send_private_forward_msg'
        target={'group_id':event.group_id} if isinstance(event,GroupMessageEvent) else {'user_id':event.user_id}
        try:
            await asyncio.wait_for(bot.call_api(api,**target,messages=messages),SEND_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning('词库分页转发超时，未自动重发：'+str(scope_id))
            # An uncertain timeout can still arrive later; do not duplicate the page automatically.
            notice='这页转发没及时返回，先看看有没有收到。没收到可发：\n'
            notice+=fallback
            await asyncio.wait_for(matcher.send(Message(MessageSegment.text(notice))),8)
        except Exception as exc:
            logger.warning('词库图片批次转发失败：'+type(exc).__name__)
            await asyncio.wait_for(matcher.send(Message(MessageSegment.text('图片合并记录没发出，可以用文字查看：\n'+fallback))),8)
    except asyncio.TimeoutError:
        logger.warning('词库查询发送超时，未继续补发：'+str(scope_id))
    except Exception as exc:
        logger.warning('词库分页查询未完成：'+type(exc).__name__)
        try:await asyncio.wait_for(matcher.send('这次词库没查出来，稍后再试一下。'),5)
        except Exception:pass
    finally:
        _busy.discard(scope_id);_last[scope_id]=time.monotonic()
        if len(_last)>2000:
            for key,stamp in list(_last.items()):
                if time.monotonic()-stamp>600:_last.pop(key,None)
