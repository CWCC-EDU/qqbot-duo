from qqbot_media import render_scoped
"""Collection pictures and superuser-only definition/grant commands."""
import asyncio
from pathlib import Path
import re
import sqlite3
from contextlib import closing
from nonebot import get_driver,on_message,logger
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot,GroupMessageEvent,MessageSegment
from testbot.plugins.persona_utils import load_persona
from .. import local_game_store as store
from ..help_ui import render_collection

@get_driver().on_startup
async def init_collection():
    Path('database').mkdir(exist_ok=True)
    with closing(sqlite3.connect('database/collection.db')) as con:
        con.execute("CREATE TABLE IF NOT EXISTS collection(_id INTEGER PRIMARY KEY NOT NULL,collection_id INTEGER NOT NULL DEFAULT 0,collection_name TEXT NOT NULL DEFAULT '',collection_nickname TEXT NOT NULL DEFAULT '',collection_introduction TEXT NOT NULL DEFAULT '',collection_get TEXT NOT NULL DEFAULT '')")
        con.commit()

def parse_view(text):
    plain=text.startswith('文字');text=text[2:] if plain else text
    if text in ('藏品列表','我的藏品','藏品图鉴'):return text,plain
    match=re.fullmatch(r'查看藏品\s*(\S.*?)',text)
    return (match[1],plain) if match else None

async def view_rule(event:GroupMessageEvent):return parse_view(event.get_plaintext().strip()) is not None
view=on_message(rule=Rule(view_rule),priority=5,block=True)

@view.handle()
async def show_collection(bot:Bot,event:GroupMessageEvent):
    query,plain=parse_view(event.get_plaintext().strip())
    try:
        items=await asyncio.to_thread(store.catalog)
        data=await asyncio.to_thread(store.owned,event.user_id)
        if query in ('藏品列表','我的藏品','藏品图鉴'):
            all_items=query=='藏品图鉴'
            selected=items if all_items else [r for r in items if int(data.get(str(r['collection_id'])+'number',0))>0]
            rows=[f"{r['collection_id']}. {r['collection_name']} ×{int(data.get(str(r['collection_id'])+'number',0))}" for r in selected]
            title='藏品图鉴' if all_items else '我的藏品'
            if not rows:rows=['还没有藏品，先从每天签到开始吧。']
        else:
            item=store.find_collection(query,items);key=str(item['collection_id'])
            title='藏品详情'
            rows=[f"「{item['collection_name']}」",item['collection_introduction'] or '这件纪念暂时还没有介绍。',f"拥有 {int(data.get(key+'number',0))} 个",'首次获得 '+str(data.get(key+'day','尚未获得'))]
    except (ValueError,sqlite3.Error) as error:
        logger.warning('藏品读取失败：'+str(error));await view.finish(str(error) if isinstance(error,ValueError) else '藏品册暂时没翻开，稍后再试。');return
    text=title+'\n'+'\n'.join(rows)
    if not plain:
        try:
            image=await asyncio.wait_for(asyncio.to_thread(render_scoped,render_collection,bot.self_id,event.group_id,load_persona().name,title,rows),20)
            await asyncio.wait_for(bot.send(event,MessageSegment.image(image)),15);return
        except Exception as error:logger.warning('藏品图片发送失败，改用文字：'+type(error).__name__)
    for offset in range(0,len(text),1600):await asyncio.wait_for(bot.send(event,MessageSegment.text(text[offset:offset+1600])),15)

def parse_grant(text):
    at=r'(?:\[CQ:at,qq=(\d+)(?:,[^\]]*)?\]|@(\d+)|(\d+))'
    match=re.fullmatch(r'授予藏品\s*'+at+r'\s+(.+?)(?:\s+(\d+))?',text)
    if not match:match=re.fullmatch(at+r'\s*授予藏品\s*(.+?)(?:\s+(\d+))?',text)
    if not match:return None
    return int(next(g for g in match.groups()[:3] if g)),match[4].strip(),int(match[5] or 1)

async def manage_rule(event:GroupMessageEvent):
    text=str(event.message).strip()
    return text.startswith(('新增藏品','授予藏品')) or parse_grant(text) is not None
manage=on_message(rule=Rule(manage_rule),permission=SUPERUSER,priority=4,block=True)

@manage.handle()
async def manage_collection(bot:Bot,event:GroupMessageEvent):
    text=str(event.message).strip()
    try:
        if text.startswith('新增藏品'):
            parts=[part.strip() for part in text[len('新增藏品'):].strip().split('|')]
            if len(parts)!=4:
                await manage.finish('格式：新增藏品 名称 | 别名（可空） | 介绍 | 获得文案');return
            ident=await asyncio.to_thread(store.create_collection,*parts)
            reply=f'已收进图鉴：{parts[0]}（编号{ident}）。'
        else:
            parsed=parse_grant(text)
            if not parsed:
                await manage.finish('格式：授予藏品 @群友 名称 [数量]');return
            user,name,quantity=parsed
            item,total=await asyncio.to_thread(store.grant_collection,user,name,quantity)
            reply=MessageSegment.at(user)+f" 收到「{item['collection_name']}」×{quantity}，现有{total}个。"
    except (ValueError,sqlite3.Error) as error:
        logger.warning('藏品管理失败：'+str(error));await manage.finish(str(error) if isinstance(error,ValueError) else '藏品没有修改成功，请稍后再试。');return
    await manage.finish(reply)
