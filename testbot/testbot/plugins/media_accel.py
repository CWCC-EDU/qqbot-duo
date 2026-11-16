"""OneBot image transport acceleration; never retries an uncertain send."""
import asyncio,base64,hashlib,json
from pathlib import Path
from urllib.parse import urlsplit
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot,Message
from qqbot_media import service,avatar_id,lossless_png,render_mode
from io import BytesIO
from PIL import Image
from qqbot_media.quote_archive import quote_transport

def local_files_enabled():
    # Explicit opt-in because a loopback reverse-WS listener does not prove the
    # NapCat client shares this filesystem. Base64 remains portable by default.
    try:
        cfg=json.loads((service().root.parent/'图片加速.json').read_text(encoding='utf-8-sig'))
        return cfg.get('本机图片发送') is True
    except (OSError,ValueError):return False

def outgoing(raw):
    if len(raw)>8_000_000:return raw,None
    # Renderers already encode the text panel losslessly. Re-encoding it again
    # in a send hook would add CPU latency and could alter third-party artwork.
    ext='.png' if raw.startswith(b'\x89PNG') else '.jpg' if raw.startswith(b'\xff\xd8') else '.gif' if raw.startswith(b'GIF8') else '.webp' if raw[:4]==b'RIFF' else '.bin'
    key=hashlib.sha256(raw).hexdigest()
    found=service().disk.get('out',key)
    path=found[3] if found else service().disk.put('out',key,raw,1800,ext)
    return raw,path

_prepared={}
@Bot.on_calling_api
async def accelerate(bot:Bot,api:str,data:dict):
    if quote_transport.get():return
    if render_mode(bot.self_id,data.get('group_id'))=='旧版':return
    if api not in ('send_msg','send_group_msg','send_private_msg'):return
    original=data.get('message')
    if original is None:return
    message=Message(original)
    changed=False
    for segment in message:
        if segment.type!='image':continue
        file=segment.data.get('file')
        if not isinstance(file,str):continue
        try:
            raw=None
            if avatar_id(file):raw=await service().avatar(file)
            elif file.startswith('base64://') and len(file)<=11_000_000:
                key=hashlib.sha256(file.encode()).hexdigest()
                if key in _prepared:
                    raw,path=_prepared[key]
                    found=await asyncio.to_thread(service().disk.get,'out',hashlib.sha256(raw).hexdigest())
                    path=found[3] if found else None
                    if path is None:raw,path=await asyncio.to_thread(outgoing,raw)
                else:
                    raw=await asyncio.to_thread(base64.b64decode,file[9:],validate=True)
                    raw,path=await asyncio.to_thread(outgoing,raw)
                    # Bound by bytes rather than indefinitely caching every duel.
                    if sum(len(r) for r,_ in _prepared.values())+len(raw)>8_000_000:_prepared.clear()
                    _prepared[key]=(raw,path)
                segment.data['file']=path.as_uri() if path and local_files_enabled() else 'base64://'+base64.b64encode(raw).decode()
                changed=True;continue
            if raw:
                raw,path=await asyncio.to_thread(outgoing,raw)
                segment.data['file']=path.as_uri() if path and local_files_enabled() else 'base64://'+base64.b64encode(raw).decode()
                changed=True
        except Exception:
            # Keep the original segment on cache/encoding failure. No resend.
            continue
    if changed:data['message']=message

@get_driver().on_shutdown
async def close_cache():await service().close()
