"""Editable group defaults and durable, Beijing-date daily attempt counters."""
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
import math
import os
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
DEFAULTS = {'每日娶群友次数': 3, '每日透群友次数': 10, '离婚后等待分钟': 120}
KINDS = {'marry': '每日娶群友次数', 'touch': '每日透群友次数'}


class DailyLimits:
    def __init__(self, root, clock=time.time):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / '每日设置.json'
        self.database = self.root / 'daily_limits.sqlite3'
        self.clock = clock
        self.lock = threading.RLock()
        self._last = {'默认': DEFAULTS.copy(), '分群': {}}
        if not self.config_path.exists():
            self._write(self._last)
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS usage (
                  day TEXT, group_id TEXT, user_id TEXT, kind TEXT, count INTEGER NOT NULL,
                  PRIMARY KEY(day,group_id,user_id,kind));
                CREATE TABLE IF NOT EXISTS cooldown (
                  group_id TEXT, user_id TEXT, until REAL NOT NULL,
                  PRIMARY KEY(group_id,user_id));
            ''')

    def connect(self):
        return sqlite3.connect(self.database, timeout=8)

    def _write(self, value):
        temporary = self.config_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, self.config_path)

    def _read(self):
        try:
            document = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
            if not isinstance(document, dict) or set(document) - {'默认', '分群'}:
                raise ValueError('只能包含“默认”和“分群”')
            defaults = document.get('默认', {})
            groups = document.get('分群', {})
            if not isinstance(defaults, dict) or not isinstance(groups, dict):
                raise ValueError('设置必须是对象')
            for values in [defaults, *groups.values()]:
                if not isinstance(values, dict) or set(values) - set(DEFAULTS):
                    raise ValueError('存在未知的设置名称')
                for key, value in values.items():
                    maximum = 10080 if key == '离婚后等待分钟' else 1000
                    if type(value) is not int or not 0 <= value <= maximum:
                        raise ValueError('次数应为0～1000，等待分钟应为0～10080的整数')
            if any(not str(gid).isdigit() for gid in groups):
                raise ValueError('分群键必须为群号')
            self._last = {'默认': {**DEFAULTS, **defaults}, '分群': groups}
        except (OSError, ValueError, TypeError) as exc:
            logging.getLogger(__name__).warning('群友每日设置读取失败，沿用上次有效设置：%s', exc)
        return self._last

    def settings(self, group_id):
        with self.lock:
            cfg = self._read()
            return {**cfg['默认'], **cfg['分群'].get(str(group_id), {})}

    def set_group(self, group_id, key, value):
        maximum = 10080 if key == '离婚后等待分钟' else 1000
        if key not in DEFAULTS or type(value) is not int or not 0 <= value <= maximum:
            raise ValueError('设置超出范围')
        with self.lock:
            cfg = self._read()
            updated = json.loads(json.dumps(cfg))
            updated['分群'].setdefault(str(group_id), {})[key] = value
            self._write(updated)
            self._last = updated

    def day(self):
        return datetime.fromtimestamp(self.clock(), ZONE).date().isoformat()

    def remaining_wait(self, group_id, user_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT until FROM cooldown WHERE group_id=? AND user_id=?', (str(group_id), str(user_id))).fetchone()
        return max(0, math.ceil((row[0] if row else 0) - self.clock()))

    def cooling_users(self, group_id):
        with closing(self.connect()) as db:
            return {r[0] for r in db.execute('SELECT user_id FROM cooldown WHERE group_id=? AND until>?', (str(group_id), self.clock()))}

    def used(self, group_id, user_id, kind):
        with closing(self.connect()) as db:
            row = db.execute('SELECT count FROM usage WHERE day=? AND group_id=? AND user_id=? AND kind=?', (self.day(), str(group_id), str(user_id), kind)).fetchone()
        return row[0] if row else 0

    def reserve(self, group_id, user_id, kind):
        """Charge once before rolling/awaiting; failures cannot be retried for free."""
        config = self.settings(group_id)
        label = '娶群友' if kind == 'marry' else '透群友'
        with self.lock, closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if kind == 'marry':
                row = db.execute('SELECT until FROM cooldown WHERE group_id=? AND user_id=?', (str(group_id), str(user_id))).fetchone()
                wait = max(0, math.ceil((row[0] if row else 0) - self.clock()))
                if wait:
                    return f'刚解除配对，再等{math.ceil(wait / 60)}分钟吧。'
            args = (self.day(), str(group_id), str(user_id), kind)
            row = db.execute('SELECT count FROM usage WHERE day=? AND group_id=? AND user_id=? AND kind=?', args).fetchone()
            used = row[0] if row else 0
            limit = config[KINDS[kind]]
            if used >= limit:
                return ('别娶啦你这个大猪蹄子！' if kind=='marry' else '不可以涩涩！') if limit else f'本群暂时关掉{label}啦。'
            db.execute('INSERT INTO usage VALUES (?,?,?,?,1) ON CONFLICT(day,group_id,user_id,kind) DO UPDATE SET count=count+1', args)
        return None

    def divorce(self, data, group_id, user_id):
        """Persist cooldown and pair release together, with rollback on save errors."""
        group_id, user_id = str(group_id), str(user_id)
        group = data.group(group_id)
        partner = group.couple.get(user_id)
        if partner is None or partner == user_id:
            return False
        before = (dict(group.couple), dict(group.locked_couple))
        now = self.clock()
        local = datetime.fromtimestamp(now, ZONE)
        midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), ZONE).timestamp()
        until = min(now + self.settings(group_id)['离婚后等待分钟'] * 60, midnight)
        with self.lock, closing(self.connect()) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO cooldown VALUES (?,?,?) ON CONFLICT(group_id,user_id) DO UPDATE SET until=max(until,excluded.until)', (group_id, user_id, until))
                group.disband(user_id)
                data.save()
                db.commit()
            except Exception:
                db.rollback()
                group.couple, group.locked_couple = before
                data.save()
                raise
        return True
