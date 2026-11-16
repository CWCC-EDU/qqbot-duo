"""Daily aggregate storage only: no raw messages or image downloads."""
import json,re,sqlite3,time
from collections import Counter
from contextlib import closing
from datetime import datetime,timedelta,date
from pathlib import Path
from zoneinfo import ZoneInfo
import jieba

ZONE=ZoneInfo('Asia/Shanghai')
DEFAULT={'默认开启':True,'保留天数':800,'数据库上限MB':256,'停用词':['这个','那个','什么','怎么','就是','还是','没有','不是','可以','一个','我们','你们','他们','自己','这样','时候','已经','真的','然后','但是','所以','因为','知道','现在','感觉','哈哈','哈哈哈'],'排除账号':[],'分群':{}}
PERIODS=('今日','昨日','本周','上周','本月','上月','今年','去年')

def period(label,now=None):
    now=now or datetime.now(ZONE);day=now.astimezone(ZONE).date()
    if label=='今日':start=end=day
    elif label=='昨日':start=end=day-timedelta(days=1)
    elif label=='本周':start=day-timedelta(days=day.weekday());end=day
    elif label=='上周':end=day-timedelta(days=day.weekday()+1);start=end-timedelta(days=6)
    elif label=='本月':start=day.replace(day=1);end=day
    elif label=='上月':end=day.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif label=='今年':start=day.replace(month=1,day=1);end=day
    elif label=='去年':start=date(day.year-1,1,1);end=date(day.year-1,12,31)
    else:raise ValueError('时间范围无效')
    return start.isoformat(),end.isoformat()

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.config=self.root/'设置.json';self.db=self.root/'群统计.sqlite3';self.last=DEFAULT.copy();self._maintenance=''
        if not self.config.exists():
            try:
                with self.config.open('x',encoding='utf-8') as f:json.dump(DEFAULT,f,ensure_ascii=False,indent=2)
            except FileExistsError:pass
        with closing(self.connect()) as db,db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(gid TEXT,day TEXT,uid TEXT,name TEXT,n INTEGER,chars INTEGER,PRIMARY KEY(gid,day,uid));
            CREATE TABLE IF NOT EXISTS words(gid TEXT,day TEXT,word TEXT,n INTEGER,PRIMARY KEY(gid,day,word));
            CREATE TABLE IF NOT EXISTS seen(gid TEXT,uid TEXT,mid TEXT,stamp INTEGER,at REAL,PRIMARY KEY(gid,uid,mid,stamp));
            CREATE TABLE IF NOT EXISTS groups(gid TEXT PRIMARY KEY,started TEXT);
            CREATE INDEX IF NOT EXISTS seen_at ON seen(at);''')
    def connect(self):
        db=sqlite3.connect(self.db,timeout=4);db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA journal_size_limit=4194304')
        db.execute('PRAGMA max_page_count='+str(max(8,min(1024,int(self.cfg()['数据库上限MB'])))*256));return db
    def cfg(self):
        try:
            if self.config.stat().st_size>262144:raise ValueError('配置过大')
            cfg={**DEFAULT,**json.loads(self.config.read_text(encoding='utf-8-sig'))}
            assert type(cfg['默认开启']) is bool and type(cfg['保留天数']) is int and 366<=cfg['保留天数']<=3660
            assert type(cfg['数据库上限MB']) is int and 8<=cfg['数据库上限MB']<=1024
            assert isinstance(cfg['停用词'],list) and all(isinstance(v,str) for v in cfg['停用词'])
            assert isinstance(cfg['排除账号'],list) and isinstance(cfg['分群'],dict)
            assert all(str(g).isdigit() and type(v) is bool for g,v in cfg['分群'].items())
            self.last=cfg
        except (OSError,ValueError,TypeError,AssertionError):pass
        return self.last
    def enabled(self,gid):
        cfg=self.cfg();return cfg['分群'].get(str(gid),cfg['默认开启'])
    def configure(self,gid,enabled):
        cfg=self.cfg();cfg={**cfg,'分群':{**cfg['分群'],str(gid):bool(enabled)}}
        temp=self.config.with_suffix('.tmp');temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.config);self.last=cfg
    def add(self,events):
        cfg=self.cfg();stop=set(cfg['停用词']);today=datetime.now(ZONE).date().isoformat()
        with closing(self.connect()) as db,db:
            vocab={}
            for e in events:
                gid,uid,mid,stamp,name,text=e
                if not cfg['分群'].get(gid,cfg['默认开启']) or uid in set(map(str,cfg['排除账号'])):continue
                if not db.execute('INSERT OR IGNORE INTO seen VALUES(?,?,?,?,?)',(gid,uid,mid,stamp,time.time())).rowcount:continue
                day=datetime.fromtimestamp(stamp,ZONE).date().isoformat()
                db.execute('INSERT OR IGNORE INTO groups VALUES(?,?)',(gid,today))
                chars=len(re.sub(r'\s','',text))
                db.execute('INSERT INTO users VALUES(?,?,?,?,1,?) ON CONFLICT(gid,day,uid) DO UPDATE SET n=n+1,chars=chars+excluded.chars,name=excluded.name',(gid,day,uid,name[:60],chars))
                clean=re.sub(r'https?://\S+|\b\d+\b',' ',text[:2500])
                tokens=Counter(w.lower() for w in jieba.cut(clean,HMM=False) if re.fullmatch(r'[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_]{1,19}',w) and w.lower() not in stop)
                if (gid,day) not in vocab:vocab[gid,day]={r[0] for r in db.execute('SELECT word FROM words WHERE gid=? AND day=?',(gid,day))}
                existing=vocab[gid,day]
                for word,count in tokens.most_common(60):
                    if word not in existing:
                        if len(existing)>=2000:continue
                        existing.add(word)
                    db.execute('INSERT INTO words VALUES(?,?,?,?) ON CONFLICT(gid,day,word) DO UPDATE SET n=n+excluded.n',(gid,day,word,count))
            db.execute('DELETE FROM seen WHERE at<?',(time.time()-600,))
            if self._maintenance!=today:
                cutoff=(date.fromisoformat(today)-timedelta(days=cfg['保留天数'])).isoformat()
                db.execute('DELETE FROM words WHERE day<?',(cutoff,));db.execute('DELETE FROM users WHERE day<?',(cutoff,));self._maintenance=today
    def query(self,gid,label):
        start,end=period(label);gid=str(gid)
        with closing(self.connect()) as db:
            words=dict(db.execute('SELECT word,sum(n) FROM words WHERE gid=? AND day BETWEEN ? AND ? GROUP BY word ORDER BY sum(n) DESC LIMIT 500',(gid,start,end)))
            ranking=list(db.execute('SELECT uid,sum(n),sum(chars) FROM users WHERE gid=? AND day BETWEEN ? AND ? GROUP BY uid ORDER BY sum(n) DESC,uid LIMIT 20',(gid,start,end)))
            names={}
            for uid,_,_ in ranking:
                row=db.execute('SELECT name FROM users WHERE gid=? AND uid=? ORDER BY day DESC LIMIT 1',(gid,uid)).fetchone();names[uid]=row[0] if row else uid
            total=db.execute('SELECT coalesce(sum(n),0),count(DISTINCT uid) FROM users WHERE gid=? AND day BETWEEN ? AND ?',(gid,start,end)).fetchone()
            began=db.execute('SELECT started FROM groups WHERE gid=?',(gid,)).fetchone()
        return {'start':start,'end':end,'words':words,'ranking':ranking,'names':names,'messages':total[0],'members':total[1],'began':began[0] if began else None,'label':label}
