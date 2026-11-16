"""Local, auditable knowledge candidates and observable conversation preferences."""
from contextlib import contextmanager
import hashlib,json,re,sqlite3,time
from pathlib import Path
from testbot.plugins.persona_utils import attack,normalized

TOPICS={
    '游戏':r'游戏|开黑|决斗|七日之都|原神|崩坏|塞拉菲姆',
    '编程':r'python|代码|编程|编译|程序|机器人|算法',
    '音乐':r'音乐|唱歌|歌曲|乐队|听歌',
    '动漫':r'动画|番剧|追番|漫画',
    '美食':r'好吃|吃什么|做饭|食谱|晚饭|午饭|早餐',
    '学习':r'作业|学习|考试|复习|上课',
    '运动':r'跑步|运动|打球|健身',
}


class RecordBook:
    def __init__(self,root=Path('data/learning_chat/local_intelligence')):
        self.root=Path(root);self.path=self.root/'knowledge_profiles.db'
        self.ready=False

    @contextmanager
    def connect(self):
        self.root.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:
                if not self.ready:
                    db.executescript('''
                    CREATE TABLE IF NOT EXISTS knowledge(
                      id INTEGER PRIMARY KEY, gid INTEGER NOT NULL, fingerprint TEXT NOT NULL,
                      question TEXT NOT NULL, answer TEXT NOT NULL, status TEXT NOT NULL,
                      sources TEXT NOT NULL, seen INTEGER NOT NULL, last_mid TEXT NOT NULL,
                      updated REAL NOT NULL, UNIQUE(gid,fingerprint));
                    CREATE INDEX IF NOT EXISTS knowledge_group ON knowledge(gid,status,updated);
                    CREATE TABLE IF NOT EXISTS profiles(
                      gid INTEGER NOT NULL, uid INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                      description TEXT NOT NULL DEFAULT '', metrics TEXT NOT NULL DEFAULT '{}',
                      updated REAL NOT NULL DEFAULT 0, last_mid TEXT NOT NULL DEFAULT '',PRIMARY KEY(gid,uid));
                    ''')
                    self.ready=True
                yield db
        finally:db.close()

    def learn(self,gid,uid,mid,question,answer,verified=False,source_kind='群聊引用'):
        if not question.strip() or not answer.strip() or len(question)>180 or len(answer)>400 or attack(question) or attack(answer) or '[CQ:' in question+answer:
            return False
        key=hashlib.sha256((normalized(question)+'\0'+normalized(answer)).encode()).hexdigest()
        with self.connect() as db:
            row=db.execute('SELECT id,status,sources,seen,last_mid FROM knowledge WHERE gid=? AND fingerprint=?',(gid,key)).fetchone()
            if row:
                kid,status,sources,seen,last=row
                if status=='已删除' and not verified:return False
                if last==str(mid) and not verified:return False
                sources=json.loads(sources);sources[str(uid)]=source_kind
                db.execute('UPDATE knowledge SET status=?,sources=?,seen=?,last_mid=?,updated=? WHERE id=?',('已确认' if verified else status,json.dumps(sources,ensure_ascii=False),min(seen+1,9999),str(mid),time.time(),kid))
            else:
                if db.execute('SELECT count(*) FROM knowledge WHERE gid=?',(gid,)).fetchone()[0]>=1000:return False
                db.execute('INSERT INTO knowledge(gid,fingerprint,question,answer,status,sources,seen,last_mid,updated) VALUES(?,?,?,?,?,?,?,?,?)',(gid,key,question,answer,'已确认' if verified else '待确认',json.dumps({str(uid):source_kind},ensure_ascii=False),1,str(mid),time.time()))
        return True

    def list_knowledge(self,gid):
        with self.connect() as db:
            return db.execute("SELECT id,question,answer,status,seen,updated FROM knowledge WHERE gid=? AND status!='已删除' ORDER BY updated DESC LIMIT 20",(gid,)).fetchall()

    def detail(self,gid,kid):
        with self.connect() as db:
            row=db.execute("SELECT id,question,answer,status,seen,sources FROM knowledge WHERE gid=? AND id=? AND status!='已删除'",(gid,kid)).fetchone()
            return row

    def change(self,gid,kid,status):
        with self.connect() as db:
            return db.execute('UPDATE knowledge SET status=?,updated=? WHERE gid=? AND id=?',(status,time.time(),gid,kid)).rowcount

    def deactivate_question(self,gid,question):
        with self.connect() as db:
            db.execute("UPDATE knowledge SET status='已删除',updated=? WHERE gid=? AND question=?",(time.time(),gid,question))

    def describe(self,gid,uid,text):
        if len(text)>100 or attack(text) or '[CQ:' in text:return '这段没法记，换成100字以内的普通描述吧。'
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO profiles(gid,uid) VALUES(?,?)',(gid,uid))
            db.execute('UPDATE profiles SET description=? WHERE gid=? AND uid=?',(text,gid,uid))
        return '好，记下你的习惯了。'

    def switch(self,gid,uid,enabled,clear=False):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO profiles(gid,uid) VALUES(?,?)',(gid,uid))
            if clear:db.execute("UPDATE profiles SET description='',metrics='{}',last_mid='',updated=0 WHERE gid=? AND uid=?",(gid,uid))
            db.execute('UPDATE profiles SET enabled=? WHERE gid=? AND uid=?',(int(enabled),gid,uid))

    def observe(self,gid,uid,mid,text,now=None):
        now=time.time() if now is None else now
        if not 3<=len(text)<=160 or attack(text) or text.startswith(('#','\\','/','.')) or '[CQ:' in text or 'http' in text.lower():return
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO profiles(gid,uid) VALUES(?,?)',(gid,uid))
            enabled,metrics,updated,last=db.execute('SELECT enabled,metrics,updated,last_mid FROM profiles WHERE gid=? AND uid=?',(gid,uid)).fetchone()
            if not enabled or now-updated<5 or str(mid)==last:return
            m=json.loads(metrics)
            n=m.get('samples',0)
            if n>=10000:return
            m['samples']=n+1;m['characters']=m.get('characters',0)+len(text)
            for name,condition in {
                'short':len(text)<=15,'questions':bool(re.search(r'[?？]|怎么|为什么|如何',text)),
                'polite':bool(re.search(r'谢谢|多谢|辛苦|麻烦你|感谢',text)),
                'playful':bool(re.search(r'哈哈|嘿嘿|笑死|好耶|233|hhh',text,re.I)),
                'emotes':bool(re.search(r'[\U0001F300-\U0001FAFF]|[~～]|[!！]{2,}',text)),
            }.items():m[name]=m.get(name,0)+int(condition)
            topics=m.setdefault('topics',{})
            for name,pattern in TOPICS.items():
                if re.search(pattern,text,re.I):topics[name]=topics.get(name,0)+1
            db.execute('UPDATE profiles SET metrics=?,updated=?,last_mid=? WHERE gid=? AND uid=?',(json.dumps(m,ensure_ascii=False),now,str(mid),gid,uid))

    def profile(self,gid,uid):
        with self.connect() as db:
            row=db.execute('SELECT enabled,description,metrics FROM profiles WHERE gid=? AND uid=?',(gid,uid)).fetchone()
        if not row:return dict(enabled=True,description='',samples=0,observations=[],topics=[])
        enabled,description,raw=row;m=json.loads(raw);n=m.get('samples',0)
        observations=[]
        if n>=20:
            if m.get('short',0)/n>=0.65:observations.append('常用短句')
            if m.get('questions',0)/n>=0.25:observations.append('常用提问式表达')
            if m.get('polite',0)>=3 and m['polite']/n>=0.1:observations.append('常表达感谢或礼貌请求')
            if m.get('playful',0)>=3 and m['playful']/n>=0.15:observations.append('常用轻松玩笑语气')
            if m.get('emotes',0)/n>=0.25:observations.append('常用表情或语气符号')
        topics=[k for k,v in sorted(m.get('topics',{}).items(),key=lambda p:p[1],reverse=True) if v>=3][:3]
        return dict(enabled=bool(enabled),description=description,samples=n,observations=observations,topics=topics)

    def profile_ids(self):
        with self.connect() as db:
            return db.execute('SELECT gid,uid FROM profiles ORDER BY gid,uid LIMIT 20000').fetchall()

    def export_profiles(self):
        return [(gid,uid,self.profile(gid,uid)) for gid,uid in self.profile_ids()]

    def context(self,gid,uid):
        p=self.profile(gid,uid)
        if not p['enabled']:return {}
        return {'本人自述_未核实':p['description'][:60], '可观察表达习惯':p['observations'][:2], '常聊主题_不是性格结论':p['topics'][:2]}


records=RecordBook()
