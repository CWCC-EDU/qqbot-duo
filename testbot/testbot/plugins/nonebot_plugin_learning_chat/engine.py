"""Local retrieval and small tools. No network, model weights, eval or executable rules."""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import json
import math
import operator
from pathlib import Path
import re
import sqlite3
import unicodedata
from zoneinfo import ZoneInfo

import jieba

DEFAULTS = {
    "group_context_enabled": True, "enabled": True, "cloud_enabled": False, "autonomous_enabled": False, "profile_recording": True, "mode": "安静", "passive_probability": 0.08,
    "passive_interval": 45, "direct_interval": 2, "context_seconds": 180,
    "max_history_answers": 2000, "index_refresh_seconds": 90,
    "send_timeout": 12, "failure_cooldown": 30,
    "ignored_users": [],
}
STOP = set("的 了 呢 吗 啊 呀 吧 哦 嘛 我 你 他 她 它 是 在 有 就 都 也 和 与 请 帮 帮我 一下 一个 什么 怎么 如何 请问 这个 那个 这 那".split())
# Deliberately short, reviewable equivalences; negations are never removed.
ALIASES = {"咋": "怎么", "咋样": "怎么样", "为啥": "为什么", "哪儿": "哪里",
           "计算机": "电脑", "笔记本电脑": "电脑", "重启": "重新启动",
           "掉线": "断线", "卡死": "卡住", "高兴": "开心"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    for old in sorted(ALIASES, key=len, reverse=True):
        text = text.replace(old, ALIASES[old])
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text)


def tokens(text: str) -> list[str]:
    text = normalize(text)
    words = [w for w in jieba.lcut(text) if w not in STOP and w.strip()]
    # Character bigrams help with unseen names, typos and segmentation boundaries.
    return words + ["~" + text[i:i+2] for i in range(len(text)-1)]


def safe_text(text: str, maximum: int = 400) -> bool:
    return bool(text.strip()) and len(text) <= maximum and not any(
        part in text.lower() for part in ("[cq:", "&#91;cq:", "http://", "https://")
    )


@dataclass(frozen=True)
class Entry:
    question: str
    answer: str
    count: int = 1
    curated: bool = False
    source_id: int = 0


class Index:
    """Bounded BM25 shortlist + wording/keyword checks; scores are not probabilities."""
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self.docs = [Counter(tokens(e.question)) for e in entries]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(1, len(entries)) or 1
        self.postings = defaultdict(list)
        for i, doc in enumerate(self.docs):
            for word in doc:
                self.postings[word].append(i)

    def search(self, query: str, context: str = "", excluded=()) -> list[tuple[float, Entry]]:
        qnorm = normalize(query)
        if not qnorm:
            return []
        qwords = set(tokens(query))
        scores = defaultdict(float)
        n = len(self.entries)
        for word in qwords:
            indices = self.postings.get(word, ())
            idf = math.log(1 + (n - len(indices) + 0.5) / (len(indices) + 0.5))
            for i in indices:
                tf = self.docs[i][word]
                scores[i] += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * self.lengths[i] / self.avg))
        results = []
        for i in sorted(scores, key=scores.get, reverse=True)[:60]:
            entry = self.entries[i]
            if normalize(entry.answer) in excluded or normalize(entry.answer) == qnorm:
                continue
            en = normalize(entry.question)
            # "不能" versus "能", "喜欢" versus "不喜欢" must not become equivalent.
            if bool(re.search("不|没|别|禁止|勿", qnorm)) != bool(re.search("不|没|别|禁止|勿", en)):
                continue
            overlap = len(qwords & set(self.docs[i])) / max(1, len(qwords))
            ratio = SequenceMatcher(None, qnorm, en).ratio()
            if qnorm == en:
                score = 1.0
            else:
                score = 0.60 * ratio + 0.40 * overlap
                if len(qnorm) <= 3 and ratio < 0.8:
                    continue
                # Context can break a close tie, never rescue a weak current query.
                if score >= 0.55 and context:
                    score += min(0.04, len(set(tokens(context)) & set(self.docs[i])) * 0.005)
            results.append((min(1.0, score), entry))
        return sorted(results, key=lambda p: (p[0], p[1].curated, min(p[1].count, 8)), reverse=True)[:5]


def choose(results, direct: bool):
    if not results:
        return None, False
    score, first = results[0]
    threshold = (0.72 if first.curated else 0.80) if direct else 0.95
    if score < threshold or (not first.curated and first.count < (2 if direct else 4)):
        return None, False
    # Equal wording with conflicting learned answers should ask rather than guess.
    ambiguous = any(
        abs(score - s) < 0.045 and normalize(e.answer) != normalize(first.answer)
        and e.curated == first.curated for s, e in results[1:3]
    )
    return first, ambiguous


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "local_chat.db"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS qa (
              group_id INTEGER NOT NULL, key TEXT NOT NULL, question TEXT NOT NULL,
              answer TEXT NOT NULL, teacher INTEGER NOT NULL, updated REAL NOT NULL,
              PRIMARY KEY(group_id,key));
            CREATE TABLE IF NOT EXISTS memory (
              group_id INTEGER NOT NULL, user_id INTEGER NOT NULL, key TEXT NOT NULL,
              value TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(group_id,user_id,key));
            CREATE TABLE IF NOT EXISTS settings (group_id INTEGER PRIMARY KEY, content TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=3)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def settings(self, group: int) -> dict:
        path = self.root / "settings.json"
        # Global defaults hot reload. Bad edits retain defaults, never enable code execution.
        values = {}
        try:
            values = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(values, dict):
                values = {}
        except (OSError, ValueError):
            pass
        with self.connect() as db:
            row = db.execute("SELECT content FROM settings WHERE group_id=?", (group,)).fetchone()
        if row:
            values.update(json.loads(row[0]))
        result = DEFAULTS.copy()
        for k, v in values.items():
            if k in result and type(v) is type(result[k]):
                result[k] = v
        result["mode"] = result["mode"] if result["mode"] in {"安静", "自然"} else "安静"
        for k, lo, hi in [("passive_interval", 15, 3600), ("direct_interval", 1, 60),
                          ("context_seconds", 30, 600), ("max_history_answers", 100, 5000),
                          ("index_refresh_seconds", 30, 600), ("send_timeout", 3, 30),
                          ("failure_cooldown", 5, 300)]:
            result[k] = max(lo, min(hi, result[k]))
        result["passive_probability"] = max(0.0, min(0.2, result["passive_probability"]))
        return result

    def set_setting(self, group, **values):
        with self.connect() as db:
            row = db.execute("SELECT content FROM settings WHERE group_id=?", (group,)).fetchone()
            current = json.loads(row[0]) if row else {}
            current.update(values)
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (group, json.dumps(current, ensure_ascii=False)))

    def teach(self, group, user, question, answer, now):
        if not safe_text(question, 180) or not safe_text(answer) or not normalize(question):
            return "问题限180字、回答限400字，请使用不带链接或消息代码的纯文字。"
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM qa WHERE group_id=? AND key=?", (group, normalize(question))).fetchone()
            count = db.execute("SELECT count(*) FROM qa WHERE group_id=?", (group,)).fetchone()[0]
            if count >= 2000 and not exists:
                return "本群教学词库已达2000条，请先删除不需要的问答。"
            db.execute("INSERT OR REPLACE INTO qa VALUES (?,?,?,?,?,?)", (group, normalize(question), question, answer, user, now))
        return "记住这组问答了。"

    def forget_qa(self, group, question):
        with self.connect() as db:
            return db.execute("DELETE FROM qa WHERE group_id=? AND key=?", (group, normalize(question))).rowcount

    def entries(self, group):
        with self.connect() as db:
            rows = db.execute("SELECT question,answer FROM qa WHERE group_id=? ORDER BY updated DESC LIMIT 2000", (group,)).fetchall()
        return [Entry(q, a, 100, True) for q, a in rows]

    def remember(self, group, user, key, value, now):
        if not safe_text(key, 24) or not safe_text(value, 120) or not normalize(key):
            return "记忆名称限24字、内容限120字，请使用纯文字。"
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO memory VALUES (?,?,?,?,?)", (group, user, normalize(key), value, now))
            db.execute("DELETE FROM memory WHERE group_id=? AND user_id=? AND key NOT IN (SELECT key FROM memory WHERE group_id=? AND user_id=? ORDER BY updated DESC LIMIT 20)", (group, user, group, user))
        return "记住了。"

    def memories(self, group, user):
        with self.connect() as db:
            return dict(db.execute("SELECT key,value FROM memory WHERE group_id=? AND user_id=? ORDER BY updated DESC", (group, user)).fetchall())

    def forget_memory(self, group, user, key=None):
        with self.connect() as db:
            if key is None:
                return db.execute("DELETE FROM memory WHERE group_id=? AND user_id=?", (group, user)).rowcount
            return db.execute("DELETE FROM memory WHERE group_id=? AND user_id=? AND key=?", (group, user, normalize(key))).rowcount


def calculate(expression: str) -> str:
    if len(expression) > 120:
        raise ValueError("算式太长")
    expression = expression.replace("×", "*").replace("÷", "/").replace("^", "**").replace("（", "(").replace("）", ")")
    tree = ast.parse(expression.strip(), mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 50:
        raise ValueError("算式太复杂")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            val = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            val = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1e6 or (left < 0 and right != int(right))):
                raise ValueError("乘方超出范围")
            val = ops[type(node.op)](left, right)
        else:
            raise ValueError("只支持数字、括号和加减乘除、乘方、取余")
        if not math.isfinite(val) or abs(val) > 1e15:
            raise ValueError("数值超出范围")
        return val
    return format(visit(tree.body), ".12g")


def tool_reply(text: str, now=None):
    match = re.fullmatch(r"(?:计算|算一下|帮我算(?:一下)?)\s*[:：]?\s*(.+)", text.strip())
    if match:
        try:
            return "计算结果：" + calculate(match[1])
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
            return "这个算式无法计算：" + ("除数不能为零" if isinstance(exc, ZeroDivisionError) else "请检查算式，只支持有限范围内的四则运算、乘方和取余。")
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    if re.fullmatch(r"(?:现在)?(?:几点了?|几点钟|时间)[?？]?", text):
        return now.strftime("现在是北京时间 %H:%M:%S。")
    if re.fullmatch(r"(?:今天|明天|后天|昨天)(?:是)?(?:几号|日期|星期几|周几)[?？]?", text):
        delta = 2 if text.startswith("后天") else 1 if text.startswith("明天") else -1 if text.startswith("昨天") else 0
        day = now + timedelta(days=delta)
        return f"{text[:2]}是{day:%Y年%m月%d日}，星期{'一二三四五六日'[day.weekday()]}。"
    return None
