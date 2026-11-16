"""Operator settings and per-bot/per-group sliding-window admission."""
import copy,json,os,sqlite3,time,uuid
from contextlib import closing
from pathlib import Path

ROOT=next((parent for parent in Path(__file__).resolve().parents if parent.name=='runtime'),Path.cwd().parent/'runtime')
DEFAULTS={'图像模式':{},'每分钟上限':{}}

class ControlStore:
    def __init__(self,root=ROOT,clock=time.time):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.clock=clock
        self.path=self.root/'功能控制.json';self.database=self.root/'feature-controls.sqlite3';self.last=copy.deepcopy(DEFAULTS)
        with closing(self.connect()) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS triggers(bot TEXT,gid TEXT,uid TEXT,mid TEXT,stamp TEXT,at REAL,allowed INTEGER,PRIMARY KEY(bot,gid,uid,mid,stamp));
            CREATE INDEX IF NOT EXISTS triggers_window ON triggers(bot,gid,at);
            CREATE TABLE IF NOT EXISTS notices(bot TEXT,gid TEXT,at REAL,PRIMARY KEY(bot,gid));''');db.commit()
        if not self.path.exists():
            try:
                with self.path.open('x',encoding='utf-8') as file:json.dump(DEFAULTS,file,ensure_ascii=False,indent=2)
            except FileExistsError:pass
    def connect(self):
        db=sqlite3.connect(self.database,timeout=3);db.execute('PRAGMA max_page_count=2048');return db
    def read(self):
        try:
            if self.path.stat().st_size>262144:raise ValueError('功能控制文件过大')
            cfg=json.loads(self.path.read_text(encoding='utf-8-sig'))
            if not isinstance(cfg,dict) or not isinstance(cfg.get('图像模式'),dict) or not isinstance(cfg.get('每分钟上限'),dict):raise ValueError('功能控制格式不正确')
            for mode in cfg['图像模式'].values():
                if mode not in ('快速','旧版'):raise ValueError('图像模式不正确')
            for key,row in cfg['每分钟上限'].items():
                if len(key.split(':'))!=2 or not all(part.isdigit() for part in key.split(':')):raise ValueError('群限额键不正确')
                if not isinstance(row,dict) or type(row.get('开启')) is not bool or type(row.get('次数')) is not int or not 1<=row['次数']<=10000:raise ValueError('上限需要1～10000')
            self.last=copy.deepcopy(cfg)
        except (OSError,ValueError,TypeError):pass
        return copy.deepcopy(self.last)
    def write(self,cfg):
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temporary,self.path)
        finally:temporary.unlink(missing_ok=True)
        self.last=copy.deepcopy(cfg)
    def mode(self,bot=None,gid=None):
        if bot is None or gid is None:return '快速'
        return self.read()['图像模式'].get(str(bot)+':'+str(gid),'快速')
    def set_mode(self,value,bot,gid):
        if value not in ('快速','旧版'):raise ValueError('请选择快速或旧版')
        if not str(bot).isdigit() or not str(gid).isdigit() or int(gid)<=0:raise ValueError('请指定正确的机器人和群号')
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');cfg=self.read();cfg['图像模式'][str(bot)+':'+str(gid)]=value;self.write(cfg)
    def group(self,bot,gid):return self.read()['每分钟上限'].get(str(bot)+':'+str(gid),{'开启':False,'次数':30}).copy()
    def configure(self,bot,gid,enabled=None,limit=None):
        if enabled is not None and type(enabled) is not bool:raise ValueError('开启必须是布尔值')
        if limit is not None and (type(limit) is not int or not 1<=limit<=10000):raise ValueError('次数需要1～10000')
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');cfg=self.read();key=str(bot)+':'+str(gid)
            previous=cfg['每分钟上限'].get(key,{'开启':False,'次数':30}).copy();row=previous.copy()
            if enabled is not None:row['开启']=enabled
            if limit is not None:row['次数']=limit
            cfg['每分钟上限'][key]=row;self.write(cfg)
            if previous['开启']!=row['开启']:
                db.execute('DELETE FROM triggers WHERE bot=? AND gid=?',(str(bot),str(gid)))
                db.execute('DELETE FROM notices WHERE bot=? AND gid=?',(str(bot),str(gid)))
        return row
    def admit(self,bot,gid,uid,mid,stamp):
        row=self.group(bot,gid)
        if not row['开启']:return True
        now=self.clock();args=tuple(map(str,(bot,gid,uid,mid,stamp)))
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM triggers WHERE at<?',(now-600,))
            old=db.execute('SELECT allowed FROM triggers WHERE bot=? AND gid=? AND uid=? AND mid=? AND stamp=?',args).fetchone()
            if old is not None:return bool(old[0])
            count=db.execute('SELECT count(*) FROM triggers WHERE bot=? AND gid=? AND allowed=1 AND at>?',(str(bot),str(gid),now-60)).fetchone()[0]
            accepted=count<row['次数']
            db.execute('INSERT INTO triggers VALUES(?,?,?,?,?,?,?)',(*args,now,int(accepted)))
            return accepted
    def remaining(self,bot,gid):
        row=self.group(bot,gid)
        if not row['开启']:return None
        with closing(self.connect()) as db:
            used=db.execute('SELECT count(*) FROM triggers WHERE bot=? AND gid=? AND allowed=1 AND at>?',(str(bot),str(gid),self.clock()-60)).fetchone()[0]
        return max(0,row['次数']-used)
    def notice(self,bot,gid):
        now=self.clock()
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT at FROM notices WHERE bot=? AND gid=?',(str(bot),str(gid))).fetchone()
            if previous and now-previous[0]<60:return False
            db.execute('INSERT OR REPLACE INTO notices VALUES(?,?,?)',(str(bot),str(gid),now));return True

_store=None
def controls():
    global _store
    if _store is None:_store=ControlStore()
    return _store
