"""Bounded, shared QQ-avatar cache and pixel-preserving picture helpers."""
import asyncio,hashlib,json,os,sqlite3,threading,time,uuid,importlib.util,sys
from collections import OrderedDict
from contextlib import closing
from functools import wraps,lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urljoin
import httpx
from PIL import Image,ImageOps

DEFAULTS={'头像缓存上限MB':700,'发送临时图上限MB':96,'头像更新小时':24,'头像下载并发':4,'冷头像最长等待秒':6,'本机图片发送':False,'文字图无损优化':True}
HARD_AVATAR=700_000_000
HARD_OUT=96_000_000
ROOT=next((p/'media-cache' for p in Path(__file__).resolve().parents if p.name=='runtime'),Path.cwd().parent/'runtime/media-cache')

def avatar_id(url):
    try:
        p=urlsplit(str(url));host=(p.hostname or '').lower()
        if p.scheme not in ('http','https') or p.username or p.password or p.port not in (None,80,443):return None
        if not (host=='qlogo.cn' or host.endswith('.qlogo.cn')):return None
        query=parse_qs(p.query)
        uid=(query.get('nk') or query.get('dst_uin') or [''])[0]
        if uid.isdigit() and len(uid)<=20:return 'user-'+uid
        parts=p.path.strip('/').split('/')
        if len(parts)>=3 and parts[0]=='gh' and parts[1].isdigit() and parts[1]==parts[2] and len(parts[1])<=20:return 'group-'+parts[1]
    except (ValueError,TypeError):pass
    return None

def qq_url(url):
    p=urlsplit(str(url));host=(p.hostname or '').lower()
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not any(host==s or host.endswith('.'+s) for s in ('qlogo.cn','qq.com','qpic.cn')):
        raise ValueError('不支持的QQ图片地址')
    return str(url)

def normal_avatar(raw,size=320):
    if not raw or len(raw)>2_000_000:raise ValueError('头像文件过大或为空')
    with Image.open(BytesIO(raw)) as im:
        if im.width*im.height>8_000_000:raise ValueError('头像尺寸过大')
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((size,size))
        png=BytesIO();im.save(png,'PNG',compress_level=6)
        jpg=BytesIO();im.save(jpg,'JPEG',quality=92,subsampling=0)
        data=min((png.getvalue(),jpg.getvalue()),key=len)
        if len(data)>196608:
            jpg=BytesIO();im.save(jpg,'JPEG',quality=82,subsampling=0);data=jpg.getvalue()
        if len(data)>196608:raise ValueError('头像编码超出缓存单图上限')
        return data

class DiskCache:
    def __init__(self,root,avatar_limit=HARD_AVATAR,out_limit=HARD_OUT):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.limits={'avatar':min(HARD_AVATAR,max(0,int(avatar_limit))),'out':min(HARD_OUT,max(0,int(out_limit)))}
        self.database=self.root/'index.sqlite3'
        with closing(self.connect()) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS entries(kind TEXT,key TEXT,name TEXT,size INTEGER,expires REAL,used REAL,updated REAL,PRIMARY KEY(kind,key));
            CREATE INDEX IF NOT EXISTS cache_used ON entries(kind,used);
            CREATE TABLE IF NOT EXISTS leases(key TEXT PRIMARY KEY,owner TEXT,expires REAL);''');db.commit()
        self.sweep()
    def sweep(self):
        # Crash leftovers in this dedicated cache only; saved quote assets and
        # player data live elsewhere and must never be selected for eviction.
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            names={r[0] for r in db.execute('SELECT name FROM entries')}
            for path in self.root.iterdir():
                if not path.is_file() or not path.name.startswith(('avatar-','out-')):continue
                if path.name not in names and time.time()-path.stat().st_mtime>600:path.unlink(missing_ok=True)
    def connect(self):
        db=sqlite3.connect(self.database,timeout=2)
        db.execute('PRAGMA max_page_count=4096') # Index is capped at 16 MiB.
        return db
    def get(self,kind,key):
        with closing(self.connect()) as db:
            row=db.execute('SELECT name,size,expires,updated,used FROM entries WHERE kind=? AND key=?',(kind,key)).fetchone()
            if not row:return None
            if Path(row[0]).name!=row[0]:return None
            path=self.root/row[0]
            try:
                if path.stat().st_size!=row[1]:return None
                raw=path.read_bytes()
            except OSError:return None
            now=time.time()
            if now-row[4]>60:
                db.execute('UPDATE entries SET used=? WHERE kind=? AND key=?',(now,kind,key));db.commit()
            return raw,now<row[2],row[3],path
    def put(self,kind,key,raw,ttl,extension='.bin'):
        limit=self.limits[kind]
        if not raw or len(raw)>min(limit,196608 if kind=='avatar' else 8_000_000):return None
        digest=hashlib.sha256((kind+key).encode()).hexdigest()
        name=kind+'-'+digest+'-'+hashlib.sha256(raw).hexdigest()[:16]+extension;path=self.root/name
        temporary=self.root/(name+'.'+uuid.uuid4().hex+'.tmp');now=time.time()
        previous_name=None;created=False
        try:
          with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT name FROM entries WHERE kind=? AND key=?',(kind,key)).fetchone()
            previous_name=previous[0] if previous else None
            if not previous and db.execute('SELECT count(*) FROM entries').fetchone()[0]>=20000:
                victim=db.execute("SELECT kind,key,name FROM entries WHERE kind='avatar' OR used<? ORDER BY used LIMIT 1",(now-120,)).fetchone()
                if not victim:return None
                (self.root/victim[2]).unlink(missing_ok=True)
                db.execute('DELETE FROM entries WHERE kind=? AND key=?',victim[:2])
            # Only our managed filenames can be removed. Recent outgoing files
            # are pinned long enough for NapCat to finish opening/uploading them.
            total=db.execute('SELECT coalesce(sum(size),0) FROM entries WHERE kind=? AND key!=?',(kind,key)).fetchone()[0]
            rows=db.execute('SELECT key,name,size FROM entries WHERE kind=? AND key!=?'+(' AND used<?' if kind=='out' else '')+' ORDER BY used',(kind,key,now-120) if kind=='out' else (kind,key)).fetchall()
            for old_key,old_name,old_size in rows:
                if total+len(raw)<=limit:break
                if Path(old_name).name!=old_name:raise ValueError('缓存路径异常')
                (self.root/old_name).unlink(missing_ok=True)
                db.execute('DELETE FROM entries WHERE kind=? AND key=?',(kind,old_key));total-=old_size
            if total+len(raw)>limit:return None
            try:
                temporary.write_bytes(raw);os.replace(temporary,path);created=True
                db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?,?)',(kind,key,name,len(raw),now+ttl,now,now))
            finally:temporary.unlink(missing_ok=True)
        except BaseException:
            if created and previous_name!=name:path.unlink(missing_ok=True)
            raise
        if previous_name and previous_name!=name:(self.root/previous_name).unlink(missing_ok=True)
        return path
    def lease(self,key,owner):
        now=time.time()
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM leases WHERE expires<?',(now,))
            return db.execute('INSERT OR IGNORE INTO leases VALUES(?,?,?)',(key,owner,now+10)).rowcount==1
    def release(self,key,owner):
        with closing(self.connect()) as db,db:db.execute('DELETE FROM leases WHERE key=? AND owner=?',(key,owner))
    def status(self):
        with closing(self.connect()) as db:
            return {kind:{'bytes':size,'count':n,'limit':self.limits[kind]} for kind,size,n in db.execute('SELECT kind,sum(size),count(*) FROM entries GROUP BY kind')}

class MediaService:
    def __init__(self,root=ROOT,fetch=None,avatar_limit=HARD_AVATAR,out_limit=HARD_OUT):
        self.root=Path(root);self.disk=DiskCache(root,avatar_limit,out_limit)
        self.fetch_override=fetch;self.client=None;self.sem=asyncio.Semaphore(4)
        self.pending={};self.backoff={};self.closed=False;self.ttl=86400;self.deadline=6
        self.metrics={'disk_hits':0,'network_fetches':0,'stale_hits':0,'misses':0}
    async def fetch(self,url):
        if self.fetch_override:return await self.fetch_override(url)
        if self.client is None:
            self.client=httpx.AsyncClient(timeout=httpx.Timeout(2.5,connect=1.5),trust_env=False,follow_redirects=False,limits=httpx.Limits(max_connections=4,max_keepalive_connections=4))
        url=qq_url(url)
        for attempt in range(3):
            async with self.client.stream('GET',url) as response:
                if response.status_code in (301,302,303,307,308):
                    url=qq_url(urljoin(url,response.headers.get('location','')));continue
                response.raise_for_status();raw=bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw)>2_000_000:raise ValueError('头像超过2MB')
                return bytes(raw)
        raise ValueError('头像跳转过多')
    async def _refresh(self,key,identity,size):
        owner=uuid.uuid4().hex;owned=False
        try:
            # A second bot process waits for the shared first download instead
            # of downloading every popular user's avatar twice.
            owned=await asyncio.to_thread(self.disk.lease,key,owner)
            if not owned:
                for _ in range(20):
                    await asyncio.sleep(.15)
                    found=await asyncio.to_thread(self.disk.get,'avatar',key)
                    if found and found[1]:return found[0]
                return None
            async with self.sem:
                found=await asyncio.to_thread(self.disk.get,'avatar',key)
                if found and found[1]:return found[0]
                if identity.startswith('user-'):
                    uid=identity[5:]
                    urls=[f'https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640',f'https://q.qlogo.cn/headimg_dl?dst_uin={uid}&spec=640&img_type=jpg']
                else:
                    gid=identity[6:];urls=[f'https://p.qlogo.cn/gh/{gid}/{gid}/640']
                for url in urls:
                    try:
                        self.metrics['network_fetches']+=1
                        raw=await self.fetch(url)
                        raw=await asyncio.to_thread(normal_avatar,raw,size)
                        try:await asyncio.to_thread(self.disk.put,'avatar',key,raw,self.ttl)
                        except (OSError,sqlite3.Error):pass
                        return raw
                    except (OSError,ValueError,httpx.HTTPError,asyncio.TimeoutError):continue
                return None
        finally:
            if owned:
                try:await asyncio.to_thread(self.disk.release,key,owner)
                except (OSError,sqlite3.Error):pass
    def _schedule(self,key,identity,size):
        if key in self.pending:return self.pending[key]
        if len(self.pending)>=32 or self.backoff.get(key,0)>time.monotonic():return None
        async def run():
            try:
                result=await asyncio.wait_for(self._refresh(key,identity,size),self.deadline)
                if not result:self.backoff[key]=time.monotonic()+60
                if len(self.backoff)>8192:self.backoff.clear()
                return result
            except (OSError,ValueError,sqlite3.Error,asyncio.TimeoutError):
                self.backoff[key]=time.monotonic()+60;return None
            finally:self.pending.pop(key,None)
        task=asyncio.create_task(run());self.pending[key]=task;return task
    async def avatar(self,url,size=320):
        identity=avatar_id(url)
        if not identity or self.closed:return None
        size=640 if size>320 else 320;key=identity+'-'+str(size)
        try:found=await asyncio.to_thread(self.disk.get,'avatar',key)
        except (OSError,sqlite3.Error):found=None
        if found:
            self.metrics['disk_hits']+=1
            if not found[1]:
                self.metrics['stale_hits']+=1;self._schedule(key,identity,size)
            return found[0]
        self.metrics['misses']+=1
        task=self._schedule(key,identity,size)
        return await asyncio.shield(task) if task else None
    async def close(self):
        self.closed=True
        tasks=list(self.pending.values())
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        if self.client:await self.client.aclose()

_service=None
def service():
    global _service
    if _service is None:
        settings=DEFAULTS.copy();path=ROOT.parent/'图片加速.json'
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                try:
                    with path.open('x',encoding='utf-8') as file:json.dump(DEFAULTS,file,ensure_ascii=False,indent=2)
                except FileExistsError:pass
            settings.update(json.loads(path.read_text(encoding='utf-8-sig')))
            avatar_limit=min(HARD_AVATAR,max(1,int(settings['头像缓存上限MB']))*1_000_000)
            out_limit=min(HARD_OUT,max(1,int(settings['发送临时图上限MB']))*1_000_000)
            hours=min(168,max(1,int(settings['头像更新小时'])))
            concurrency=min(8,max(1,int(settings['头像下载并发'])))
            deadline=min(6,max(2,int(settings['冷头像最长等待秒'])))
        except (OSError,ValueError,TypeError):avatar_limit=HARD_AVATAR;out_limit=HARD_OUT;hours=24;concurrency=4;deadline=6
        _service=MediaService(ROOT,avatar_limit=avatar_limit,out_limit=out_limit)
        _service.ttl=hours*3600;_service.sem=asyncio.Semaphore(concurrency);_service.deadline=deadline
    return _service

from contextvars import ContextVar
from contextlib import contextmanager
_render_context=ContextVar('qqbot_group_image_scope',default=None)

@contextmanager
def render_scope(bot,gid):
    token=_render_context.set((bot,gid))
    try:yield
    finally:_render_context.reset(token)

def render_scoped(function,bot,gid,*args,**kwargs):
    with render_scope(bot,gid):return function(*args,**kwargs)

def render_mode(bot=None,gid=None):
    try:
        from .controls import controls
        if bot is None:
            scope=_render_context.get()
            if scope is not None:bot,gid=scope
            else:
                try:
                    from nonebot.matcher import current_bot,current_event
                    bot=current_bot.get().self_id
                    gid=getattr(current_event.get(),'group_id',None)
                except (ImportError,LookupError):return '快速'
        return controls().mode(bot,gid)
    except (ImportError,OSError,sqlite3.Error):return '快速'

def lossless_png(im):
    # No rescaling, lossy palette quantization, JPEG or subsampling for text.
    # Exact palettes are used only if every existing RGB colour fits in 256.
    candidate=im
    if im.mode=='RGB' and im.getcolors(256) is not None:
        candidate=im.convert('P',palette=Image.Palette.ADAPTIVE,colors=256,dither=Image.Dither.NONE)
        if candidate.convert('RGB').tobytes()!=im.tobytes():candidate=im
    out=BytesIO();candidate.save(out,'PNG',compress_level=6)
    raw=out.getvalue();optimizer=png_optimizer()
    if optimizer is not None and len(raw)>=16384:
        try:
            smaller=optimizer.optimize_from_memory(raw,level=0,optimize_alpha=False)
            if len(smaller)<len(raw):return smaller
        except Exception:pass
    # A missing optional Windows native optimizer must never stop picture sends.
    if optimizer is None:
        out=BytesIO();candidate.save(out,'PNG',optimize=True)
        if len(out.getvalue())<len(raw):raw=out.getvalue()
    return raw

@lru_cache(maxsize=1)
def png_optimizer():
    try:
        try:
            cfg=json.loads((ROOT.parent/'图片加速.json').read_text(encoding='utf-8-sig'))
            if cfg.get('文字图无损优化') is False:return None
        except (OSError,ValueError):pass
        package=Path(__file__).resolve().parent/'_vendor/oxipng'
        spec=importlib.util.spec_from_file_location('_qqbot_png_optimizer',package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        return module
    except (OSError,ImportError,AttributeError):return None

_renders=OrderedDict();_render_bytes=0;_render_lock=threading.RLock()
def cached_render(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        global _render_bytes
        # Duel state deliberately mixes integer player slots and string fields;
        # sorted JSON keys cannot represent that state. repr preserves key types.
        mode=render_mode()
        if mode=='旧版':return function(*args,**kwargs)
        try:key=hashlib.sha256((mode+function.__module__+function.__qualname__+repr((args,kwargs))).encode()).digest()
        except Exception:return function(*args,**kwargs)
        with _render_lock:
            hit=_renders.get(key)
            if hit and hit[0]>time.monotonic():_renders.move_to_end(key);return hit[1]
            if hit:_render_bytes-=len(hit[1]);del _renders[key]
        result=function(*args,**kwargs)
        if mode==render_mode() and isinstance(result,bytes) and len(result)<=8_000_000:
            with _render_lock:
                old=_renders.pop(key,None)
                if old:_render_bytes-=len(old[1])
                _renders[key]=(time.monotonic()+300,result);_render_bytes+=len(result)
                while _render_bytes>32_000_000:
                    _,(_,raw)=_renders.popitem(last=False);_render_bytes-=len(raw)
        return result
    return wrapped
