"""Durable quote assets. No expiry, eviction, or source/index deletion."""
import argparse,hashlib,json,os,sqlite3,time,uuid
from contextlib import closing
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote,urlsplit
from PIL import Image

MAXIMUM=8_000_000
quote_transport=ContextVar('qqbot_permanent_quote_transport',default=False)

def filename(ref):return str(ref).replace('\\','/').rstrip('/').rsplit('/',1)[-1]

def checked(raw):
    if not raw or len(raw)>MAXIMUM:raise ValueError('图片为空或超过8MB')
    with Image.open(BytesIO(raw)) as image:
        if image.width*image.height>30_000_000:raise ValueError('图片尺寸超过限制')
        fmt=image.format
        image.verify()
    if fmt not in ('PNG','JPEG','GIF','WEBP','BMP'):raise ValueError('图片格式不支持')
    return {'PNG':'.png','JPEG':'.jpg','GIF':'.gif','WEBP':'.webp','BMP':'.bmp'}[fmt]

class Archive:
    def __init__(self,bot_root,quote_root=None):
        self.bot_root=Path(bot_root).resolve()
        self.quote_root=Path(quote_root or self.bot_root/'data')
        if not self.quote_root.is_absolute():self.quote_root=self.bot_root/self.quote_root
        self.folder=self.bot_root/'data/语录存档'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.db=self.folder/'旧路径映射.sqlite3'
        with closing(self.connect()) as db:
            db.execute('CREATE TABLE IF NOT EXISTS assets(ref TEXT PRIMARY KEY,name TEXT NOT NULL,sha TEXT NOT NULL)');db.commit()
    def connect(self):return sqlite3.connect(self.db,timeout=2)
    def mapped(self,ref):
        with closing(self.connect()) as db:
            row=db.execute('SELECT name,sha FROM assets WHERE ref=?',(str(ref),)).fetchone()
        if row and Path(row[0]).name==row[0]:
            path=self.folder/row[0]
            if path.is_file():
                raw=self.read(path)
                if hashlib.sha256(raw).hexdigest()==row[1]:return path,raw
        return None
    @staticmethod
    def read(path):
        with Path(path).open('rb') as stream:raw=stream.read(MAXIMUM+1)
        checked(raw);return raw
    def candidates(self,ref):
        ref=str(ref)
        if ref.startswith('file:'):
            parsed=urlsplit(ref)
            if parsed.netloc not in ('','localhost'):return
            ref=unquote(parsed.path)
            if os.name=='nt' and len(ref)>2 and ref[0]=='/' and ref[2]==':':ref=ref[1:]
        elif '://' in ref:return
        path=Path(ref.replace('\\','/'));name=filename(ref)
        roots=[self.bot_root,self.bot_root.parent,self.bot_root.parent.parent]
        possibilities=[path] if path.is_absolute() else [base/path for base in roots]
        # Old Windows absolute paths can survive a move to another server.
        parts=ref.replace('\\','/').split('/')
        for pos,part in enumerate(parts):
            if part==self.bot_root.name:possibilities.append(self.bot_root/Path(*parts[pos+1:]))
        possibilities += [self.folder/name,self.quote_root/name,self.bot_root/'data'/name]
        for base in roots:
            possibilities += [base/'cache'/name,base/'data/cache'/name]
        seen=set()
        for candidate in possibilities:
            key=os.path.normcase(str(candidate))
            if key not in seen:
                seen.add(key);yield candidate
    def store(self,ref,raw):
        suffix=checked(raw);digest=hashlib.sha256(raw).hexdigest()
        destination=self.folder/(digest+suffix)
        if destination.is_file():
            if hashlib.sha256(self.read(destination)).hexdigest()!=digest:raise ValueError('已有存档校验失败')
        else:
            temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,destination)
            finally:temporary.unlink(missing_ok=True)
        with closing(self.connect()) as db,db:
            db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?)',(str(ref),destination.name,digest))
        return destination,raw
    def load(self,ref):
        mapped=self.mapped(ref)
        if mapped:return mapped
        for path in self.candidates(ref):
            try:
                if not path.is_file():continue
                raw=self.read(path)
                # New snapshots already live in the permanent directory.
                if path.resolve().parent==self.folder.resolve():return path,raw
                return self.store(ref,raw)
            except (FileNotFoundError,IsADirectoryError):continue
        raise FileNotFoundError(str(ref))

def references(record,index):
    result=set()
    for bucket in record.values():
        if isinstance(bucket,list):result.update(ref for ref in bucket if isinstance(ref,str))
    for group in index.values():
        if isinstance(group,dict):
            for bucket in group.values():
                if isinstance(bucket,list):result.update(ref for ref in bucket if isinstance(ref,str))
    return result

def settings(bot):
    values={}
    # Only parse these three path settings, never load a bot or execute config.
    for name in ('.env','.env.prod'):
        path=bot/name
        if not path.is_file():continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key,separator,value=line.partition('=');key=key.strip().lower()
            if separator and key in ('record_path','inverted_index_path','quote_path'):
                value=value.strip()
                try:value=json.loads(value)
                except ValueError:value=value.strip("\"'")
                if isinstance(value,str):values[key]=value
    return values

def scan(root,wanted):
    matches={};visited=0;limited=False
    ignored={'runtime','backups','.git','.venv','venv','node_modules','__pycache__','logs','语录存档'}
    for current,dirs,files in os.walk(root,followlinks=False):
        parent=Path(current)
        dirs[:]=[name for name in dirs if name.lower() not in ignored and not (parent/name).is_symlink() and not (hasattr((parent/name),'is_junction') and (parent/name).is_junction()) and len((parent/name).relative_to(root).parts)<=14]
        for name in files:
            visited+=1
            if name in wanted:matches.setdefault(name,[]).append(parent/name)
            if visited>=300000:limited=True;break
        if limited:break
    return matches,visited,limited

def repair(root):
    root=Path(root).resolve();upgrade=root/'upgrade-20261018'
    if not upgrade.is_dir():raise ValueError('请选择包含upgrade-20261018的QQbot目录')
    work=[];wanted=set();reports={}
    for botname in ('testbot','testbot_2'):
        bot=upgrade/botname
        if not bot.is_dir():continue
        cfg=settings(bot);files=[];objects=[]
        for key,default in (('record_path','record.json'),('inverted_index_path','inverted_index.json')):
            path=Path(cfg.get(key,default));path=path if path.is_absolute() else bot/path
            files.append(path)
            if path.exists():objects.append(json.loads(path.read_text(encoding='utf-8-sig')))
            else:objects.append({})
        if not all(isinstance(obj,dict) for obj in objects):raise ValueError(botname+'索引不是字典，未修改原文件')
        refs=references(*objects);archive=Archive(bot,cfg.get('quote_path','data'))
        work.append((botname,archive,refs));wanted.update(filename(ref) for ref in refs if '://' not in ref or ref.startswith('file:'))
        reports[botname]={'索引文件':[str(p) for p in files],'索引原样保留':True,'总引用':len(refs),'已归档':0,'待处理':[]}
    print('正在QQbot目录内查找旧语录图片，不扫描其他磁盘。',flush=True)
    matches,visited,limited=scan(root,wanted)
    for botname,archive,refs in work:
        report=reports[botname]
        for ref in sorted(refs):
            try:
                try:archive.load(ref)
                except FileNotFoundError:
                    choices=matches.get(filename(ref),[])
                    if not choices:raise
                    versions={}
                    for path in choices:
                        raw=archive.read(path);versions[hashlib.sha256(raw).hexdigest()]=raw
                    if len(versions)!=1:raise ValueError('同名图片内容不同，未擅自选取')
                    archive.store(ref,next(iter(versions.values())))
                report['已归档']+=1
            except (OSError,ValueError,sqlite3.Error) as exc:report['待处理'].append({'引用':ref,'原因':type(exc).__name__+': '+str(exc)})
    result={'时间':time.strftime('%Y-%m-%d %H:%M:%S'),'扫描文件数':visited,'达到扫描上限':limited,'联网下载':False,'删除原文件':False,'机器人':reports}
    path=upgrade/'语录归档检查结果.json';temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temporary,path)
    for name,item in reports.items():print(f"{name}：共{item['总引用']}条引用，已归档{item['已归档']}条，待处理{len(item['待处理'])}条。",flush=True)
    print('报告：'+str(path),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repair-root',required=True)
    try:repair(parser.parse_args().repair_root)
    except Exception as exc:print('整理未完成，原索引保留：'+type(exc).__name__+': '+str(exc),flush=True);raise SystemExit(1)
