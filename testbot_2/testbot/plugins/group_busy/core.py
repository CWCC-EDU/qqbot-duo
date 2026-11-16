"""Per-account/group settings, heat state, and durable result spool."""
import datetime as dt
import json
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
DEFAULT = {'模式': '关闭', '统计秒': 60, '消息条数': 20, '最少人数': 4,
           '恢复秒': 120, '汇总秒': 60, '汇总次数': 10, '时段': [],
           '限流开启': True, '限流秒': 60, '限流次数': 10}
MODES = ('关闭', '自动', '常开', '定时', '自动定时')

def peer_ids(root, sid=None):
    """Both independent bot processes advertise their QQ account locally."""
    path=Path(root).parent/'data/group_busy_peers.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=3) as db:
        db.execute('CREATE TABLE IF NOT EXISTS peers(sid TEXT PRIMARY KEY)')
        if sid is not None:db.execute('INSERT OR IGNORE INTO peers VALUES(?)',(str(sid),))
        return {row[0] for row in db.execute('SELECT sid FROM peers')}

def slots(value):
    result = []
    for part in value.split():
        ends = part.split('-')
        if len(ends) != 2: raise ValueError('时段格式：12:00-14:00 18:00-23:00')
        for end in ends:
            if len(end) != 5 or end[2] != ':': raise ValueError('时间使用两位小时和分钟')
            dt.datetime.strptime(end, '%H:%M')
        if ends[0] == ends[1]: raise ValueError('开始和结束不能相同；全天使用常开模式')
        result.append(part)
    if len(result) > 12: raise ValueError('最多设置12个时段')
    return result

def scheduled(row, now=None):
    moment = (now or dt.datetime.now(ZONE)).astimezone(ZONE).strftime('%H:%M')
    for part in row['时段']:
        start, end = part.split('-')
        if (start <= moment < end) if start < end else (moment >= start or moment < end):
            return True
    return False

class Settings:
    def __init__(self, root):
        self.path = Path(root) / '设置.json'
        self.lock = threading.RLock()
        self.last = {'排除账号': [], '分群': {}}
        self.error = ''
        if not self.path.exists(): self.save(self.last)

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)
        self.last = data

    def read(self):
        with self.lock:
            try:
                value = json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(value, dict) or not isinstance(value.get('分群'), dict):
                    raise ValueError('分群必须是对象')
                excluded = value.get('排除账号', [])
                if not isinstance(excluded, list): raise ValueError('排除账号必须是列表')
                for row in value['分群'].values(): self.validate(row)
                self.last = value
                self.error = ''
            except (OSError, ValueError, TypeError) as exc:
                self.error = str(exc)
            return self.last

    @staticmethod
    def validate(row):
        if not isinstance(row, dict): raise ValueError('群设置必须是对象')
        row = dict(row)
        # Read v1 settings without overwriting the user's file or pending data.
        old_messages = row.pop('每分钟消息', 20)
        old_batch = row.pop('每图人数', 10)
        row.pop('持续秒', None)
        row.setdefault('消息条数', old_messages)
        row.setdefault('汇总次数', 10 if old_batch == 8 else old_batch)
        out = dict(DEFAULT, **row)
        if out['模式'] not in MODES: raise ValueError('模式应为：' + '、'.join(MODES))
        bounds = {'统计秒': (1, 3600), '消息条数': (1, 10000), '最少人数': (1, 1000),
                  '恢复秒': (30, 1800), '汇总秒': (1, 3600), '汇总次数': (1, 32),
                  '限流秒': (1, 3600), '限流次数': (1, 10000)}
        for key, (lo, hi) in bounds.items():
            if type(out[key]) is not int or not lo <= out[key] <= hi:
                raise ValueError(f'{key}应为{lo}～{hi}的整数')
        if not isinstance(out['时段'], list): raise ValueError('时段必须是列表')
        if type(out['限流开启']) is not bool:raise ValueError('限流开启应为true或false')
        slots(' '.join(out['时段']))
        return out

    def get(self, sid, gid):
        return self.validate(self.read()['分群'].get(f'{sid}:{gid}', {}))

    def set(self, sid, gid, **changes):
        with self.lock:
            data = self.read()
            if self.error: raise ValueError('设置文件有错误，请先修正：' + self.error)
            # Do not modify the last valid snapshot unless saving succeeds.
            data = json.loads(json.dumps(data))
            row = dict(data['分群'].get(f'{sid}:{gid}', {}), **changes)
            row = self.validate(row)
            data['分群'][f'{sid}:{gid}'] = row
            self.save(data)
            return row

class Heat:
    def __init__(self):
        self.events = defaultdict(deque)
        self.states = {}
        self.seen = {}

    def add(self, key, mid, uid, now=None):
        now = time.monotonic() if now is None else now
        identity = (key, str(mid))
        if identity in self.seen: return
        self.seen[identity] = now
        self.events[key].append((now, str(uid)))
        while self.events[key] and now-self.events[key][0][0]>=3600:self.events[key].popleft()
        if len(self.events[key]) > 20000: self.events[key].popleft()
        if len(self.seen) > 4000:
            self.seen = {k: v for k, v in self.seen.items() if now-v < 3600}

    def status(self, key, row, now=None):
        now = time.monotonic() if now is None else now
        events = self.events[key]
        while events and now-events[0][0] >= 3600: events.popleft()
        recent=[x for x in events if now-x[0]<row['统计秒']]
        n, users = len(recent), len({x[1] for x in recent})
        hot, cool = self.states.get(key, (False, None))
        high = n >= row['消息条数'] and users >= row['最少人数']
        low = n < max(1, row['消息条数']/2) or users < row['最少人数']
        if high:
            hot = True
            cool = None
        else:
            if hot and low:
                cool = now if cool is None else cool
                if now-cool >= row['恢复秒']: hot = False; cool = None
            else: cool = None
        self.states[key] = (hot, cool)
        return hot, n, users

    def active(self, key, row, now=None, date=None):
        hot, n, users = self.status(key, row, now)
        mode = row['模式']
        active = mode == '常开' or (mode in ('自动', '自动定时') and hot) or (
            mode in ('定时', '自动定时') and scheduled(row, date))
        return active, hot, n, users

class RollingLimit:
    """An input operation costs one token; output messages never cost tokens."""
    def __init__(self):
        self.events=defaultdict(deque)
        self.decisions={}

    def admit(self,key,event,seconds,limit,now=None):
        now=time.monotonic() if now is None else now
        ident=(key,event)
        decision=self.decisions.get(ident)
        if decision is not None and now-decision[0]<7200:return decision[1]
        queue=self.events[key]
        while queue and now-queue[0][0]>=3600:queue.popleft()
        accepted=sum(now-stamp<seconds for stamp,_ in queue)<limit
        if accepted:queue.append((now,event))
        self.decisions[ident]=(now,accepted)
        if len(self.decisions)>10000:
            self.decisions={k:v for k,v in self.decisions.items() if now-v[0]<7200}
        return accepted

    def release(self,key,event):
        self.events[key]=deque((stamp,ident) for stamp,ident in self.events[key] if ident!=event)
        self.decisions[(key,event)]=(time.monotonic(),False)

    def used(self,key,seconds,now=None):
        now=time.monotonic() if now is None else now
        return sum(now-stamp<seconds for stamp,_ in self.events[key])

class Spool:
    """Commit before suppressing original API; pending survives process restarts."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / '待发结果.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS results (
              id INTEGER PRIMARY KEY, sid TEXT, gid TEXT, event TEXT, uid TEXT,
              name TEXT, kind TEXT, created REAL, updated REAL, ready INTEGER,
              state TEXT, batch TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS pending ON results(sid,gid,state,id);
            CREATE UNIQUE INDEX IF NOT EXISTS event_key ON results(sid,gid,event);
            ''')
            # Records were captured durably; even an interrupted handler has useful output.
            db.execute("UPDATE results SET ready=1 WHERE state='pending'")
            db.execute("UPDATE results SET state='uncertain' WHERE state='sending'")

    def connect(self):
        db = sqlite3.connect(self.db, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    def append(self, sid, gid, event, uid, name, kind, fragments):
        with self.lock, self.connect() as db:
            used = (db.execute('PRAGMA page_count').fetchone()[0] - db.execute('PRAGMA freelist_count').fetchone()[0]) * db.execute('PRAGMA page_size').fetchone()[0]
            if used > 64*1024*1024: raise OSError('待发结果达到64MB，请先处理待发内容')
            found = db.execute('SELECT * FROM results WHERE sid=? AND gid=? AND event=?',
                               (sid, gid, event)).fetchone()
            now = time.time()
            if found:
                if found['state'] != 'pending': raise ValueError('同一事件已汇总，不再捕获后续消息')
                parts = json.loads(found['payload'])
                parts.extend(fragments)
                if len(json.dumps(parts)) > 16_000_000: raise ValueError('单次结果过大，保留原发送方式')
                db.execute('UPDATE results SET payload=?,updated=?,ready=0 WHERE id=?',
                           (json.dumps(parts, ensure_ascii=False), now, found['id']))
                return found['id']
            if db.execute("SELECT count(*) FROM results WHERE state='pending' AND sid=? AND gid=?", (sid,gid)).fetchone()[0] >= 200:
                raise OSError('本群待发结果过多，保留原发送方式')
            cur = db.execute('INSERT INTO results(sid,gid,event,uid,name,kind,created,updated,ready,state,payload) VALUES(?,?,?,?,?,?,?,?,0,?,?)',
                 (sid,gid,event,uid,name[:80],kind,now,now,'pending',json.dumps(fragments,ensure_ascii=False)))
            return cur.lastrowid

    def ready(self, sid, gid, event):
        with self.lock, self.connect() as db:
            db.execute('UPDATE results SET ready=1 WHERE sid=? AND gid=? AND event=? AND state=?',
                       (sid,gid,event,'pending'))

    def contains(self,sid,gid,event):
        with self.lock,self.connect() as db:
            return db.execute('SELECT 1 FROM results WHERE sid=? AND gid=? AND event=?',(sid,gid,event)).fetchone() is not None

    def pending(self):
        with self.lock, self.connect() as db:
            return [dict(x) for x in db.execute("SELECT sid,gid,count(*) n,min(created) first FROM results WHERE state='pending' GROUP BY sid,gid")]

    def take(self, sid, gid, limit):
        import uuid
        with self.lock, self.connect() as db:
            rows = [dict(x) for x in db.execute("SELECT * FROM results WHERE sid=? AND gid=? AND state='pending' AND ready=1 ORDER BY id LIMIT ?", (sid,gid,limit))]
            if not rows: return None, []
            batch = uuid.uuid4().hex
            db.executemany("UPDATE results SET state='sending',batch=? WHERE id=?", [(batch,x['id']) for x in rows])
            return batch, rows

    def finish(self, batch, state):
        with self.lock, self.connect() as db:
            db.execute('UPDATE results SET state=? WHERE batch=?', (state,batch))
            if state == 'sent':
                db.execute('DELETE FROM results WHERE batch=?', (batch,))

    def failed(self, sid, gid):
        with self.lock, self.connect() as db:
            return [dict(x) for x in db.execute("SELECT * FROM results WHERE sid=? AND gid=? AND state='uncertain' ORDER BY id", (sid,gid))]

    def retry(self, sid, gid):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT batch FROM results WHERE sid=? AND gid=? AND state='uncertain' ORDER BY id LIMIT 1", (sid,gid)).fetchone()
            if not row: return 0
            cur = db.execute("UPDATE results SET state='pending',ready=1,batch=NULL,created=? WHERE batch=? AND state='uncertain'", (time.time(),row['batch']))
            return cur.rowcount

    def cleanup(self):
        with self.lock, self.connect() as db:
            # Keep uncertain records until an administrator explicitly handles them.
            db.execute("DELETE FROM results WHERE state='sent'")
            db.execute('PRAGMA incremental_vacuum')
