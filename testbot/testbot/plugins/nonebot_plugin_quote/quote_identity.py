"""QQ-only bounded media fetching and durable per-quote avatar snapshots."""
import asyncio,hashlib,os,time
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import httpx
from PIL import Image,ImageOps

HOSTS=('qpic.cn','qq.com','qlogo.cn')


def validate_url(url):
    parsed=urlsplit(str(url));host=(parsed.hostname or '').lower()
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not any(host==d or host.endswith('.'+d) for d in HOSTS):
        raise ValueError('不支持的QQ图片地址')
    return str(url)


async def download(url,transport=None,maximum=8_000_000):
    url=validate_url(url)
    async with httpx.AsyncClient(timeout=4,trust_env=False,follow_redirects=False,transport=transport) as client:
        for attempt in range(4):
            async with client.stream('GET',url) as response:
                if response.status_code in (301,302,303,307,308):
                    if attempt==3:raise ValueError('QQ图片跳转次数过多')
                    url=validate_url(urljoin(url,response.headers.get('location','')))
                    continue
                response.raise_for_status()
                if int(response.headers.get('content-length','0'))>maximum:raise ValueError('图片超过8MB')
                data=bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data)>maximum:raise ValueError('图片超过8MB')
                return bytes(data)
    raise ValueError('QQ图片没有返回内容')


def normalize_avatar(raw):
    if not raw or len(raw)>8_000_000:raise ValueError('头像内容为空或过大')
    with Image.open(BytesIO(raw)) as image:
        if image.width*image.height>16_000_000:raise ValueError('头像尺寸过大')
        image=ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((640,640))
        output=BytesIO();image.save(output,'PNG');return output.getvalue()


class AvatarStore:
    def __init__(self,root,fetch=None):
        self.root=Path(root);self.fetch=fetch or download
    async def obtain(self,uid,preferred=None):
        from qqbot_media import service
        uid=str(int(uid));url='https://q1.qlogo.cn/g?b=qq&nk='+uid+'&s=640'
        raw=await service().avatar(url,size=320)
        if not raw:raise ValueError('头像暂时没取到，这条还没保存，稍后再试。')
        # A quote keeps its own immutable PNG snapshot; shared thumbnails are
        # disposable cache entries and may be refreshed/evicted independently.
        raw=await asyncio.to_thread(normalize_avatar,raw)
        return raw,{'来源':'共享头像缓存（过期时后台刷新）','sha256':hashlib.sha256(raw).hexdigest()}


def short(value,limit):
    return str(value or '').replace('\r',' ').replace('\n',' ').replace('\x00','')[:limit]


async def quoted_identity(bot,event):
    sender=event.reply.sender;uid=int(sender.user_id);gid=int(event.group_id)
    async def fetch(method,**kwargs):
        try:
            result=await asyncio.wait_for(getattr(bot,method)(**kwargs),3)
            return result if isinstance(result,dict) else {}
        except Exception:return {}
    member,group=await asyncio.gather(
        fetch('get_group_member_info',group_id=gid,user_id=uid,no_cache=True),
        fetch('get_group_info',group_id=gid,no_cache=True))
    role=member.get('role') or getattr(sender,'role',None)
    if role not in ('owner','admin','member'):role=''
    card=short(member.get('card') or getattr(sender,'card',None),120)
    nickname=short(member.get('nickname') or getattr(sender,'nickname',None),120)
    size=group.get('member_count')
    metadata={
        '群号':str(gid),'群名':short(group.get('group_name'),120),'群人数':size if type(size) is int and size>=0 else None,
        '作者QQ':str(uid),'群名片':card,'昵称':nickname,'显示名':card or nickname or str(uid),
        '身份':{'owner':'群主','admin':'管理员','member':'成员','':''}[role],
        '专属头衔':short(member.get('title') or getattr(sender,'title',None),120),
        '群等级':short(member.get('level') or getattr(sender,'level',None),32),
        '原消息编号':str(event.reply.message_id),'原消息时间':int(event.reply.time),
        '保存时间':int(time.time()),'卡片信息时点':'保存时可取得的信息，不保证与发言时完全一致',
        '身份来源':'保存时群成员接口' if member.get('role') in ('owner','admin','member') else ('引用消息' if role else '未知，不绘制身份标签'),
    }
    preferred=member.get('avatar') or member.get('avatar_url')
    return metadata,preferred
