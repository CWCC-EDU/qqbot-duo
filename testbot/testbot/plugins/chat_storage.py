"""Hot-reloaded local controls; manual profile fields are never model-written."""
from contextlib import contextmanager
import copy
import json
import math
import os
from pathlib import Path
import random
import re
import threading
import time
import uuid

_locks = {}
_last_good = {}
_qa_rolls = {}
_qa_claims = set()


@contextmanager
def locked(path):
    key = str(Path(path).resolve())
    with _locks.setdefault(key, threading.RLock()):
        yield


def read_json(path, default, strict=False):
    path = Path(path)
    key = str(path.resolve())
    if not path.exists():
        return copy.deepcopy(default)
    try:
        if path.stat().st_size > 4_000_000:
            raise ValueError('配置文件过大')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('配置必须是对象')
        _last_good[key] = copy.deepcopy(value)
        return value
    except (OSError, ValueError):
        if not strict and key in _last_good:
            return copy.deepcopy(_last_good[key])
        raise ValueError('配置暂时读不出来，请检查JSON格式') from None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if len(encoded.encode('utf-8')) > 4_000_000:
            raise ValueError('配置文件超过4MB，请归档较旧的群友记录')
        temp.write_text(encoded, encoding='utf-8')
        os.replace(temp, path)
        _last_good[str(path.resolve())] = copy.deepcopy(value)
    finally:
        temp.unlink(missing_ok=True)


def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('概率需要在0%～100%之间')
    return float(value)


class ChatFiles:
    def __init__(self, root):
        self.root = Path(root)
        self.probability_path = self.root / '本地问答.json'
        self.profile_path = self.root / '群友人设.json'
        self.initialized = False

    def initialize(self):
        for path, default in [
            (self.probability_path, {'默认概率': 100, '分群': {}}),
            (self.profile_path, {'机器人补充设定': '', '分群': {}}),
        ]:
            with locked(path):
                if not path.exists():
                    write_json(path, default)
        self.initialized = True

    def probability(self, gid):
        if not self.initialized:
            self.initialize()
        with locked(self.probability_path):
            cfg = read_json(self.probability_path, {'默认概率': 100, '分群': {}}, strict=True)
            groups = cfg.get('分群', {})
            if not isinstance(groups, dict):
                raise ValueError('分群必须是对象')
            return percent(groups.get(str(gid), cfg.get('默认概率', 100)))

    def set_probability(self, gid, value):
        value = percent(value)
        self.initialize()
        with locked(self.probability_path):
            cfg = read_json(self.probability_path, {'默认概率': 100, '分群': {}}, strict=True)
            cfg.setdefault('分群', {})[str(gid)] = value
            write_json(self.probability_path, cfg)

    def allow_qa(self, gid, roll=None, message_key=None):
        probability = self.probability(gid)
        if message_key is not None:
            # The word-bank and learning handlers may match the same event. They
            # share one roll instead of increasing the chance with two attempts.
            key = (str(self.root.resolve()), str(message_key))
            with locked(self.probability_path):
                if len(_qa_rolls) > 2048:
                    _qa_rolls.clear()
                if key not in _qa_rolls:
                    _qa_rolls[key] = random.random() if roll is None else roll
                roll = _qa_rolls[key]
        return (random.random() if roll is None else roll) < probability / 100

    def profiles(self, for_write=False):
        if not self.initialized:
            self.initialize()
        value = read_json(self.profile_path, {'机器人补充设定': '', '分群': {}}, strict=for_write)
        if not isinstance(value.get('分群', {}), dict):
            raise ValueError('分群必须是对象')
        return value

    def claim_qa(self, message_key):
        with locked(self.probability_path):
            if len(_qa_claims) > 2048:
                _qa_claims.clear()
            _qa_claims.add((str(self.root.resolve()), str(message_key)))

    def claimed_qa(self, message_key):
        with locked(self.probability_path):
            return (str(self.root.resolve()), str(message_key)) in _qa_claims

    def import_profiles(self, profiles):
        with locked(self.profile_path):
            value = self.profiles(for_write=True)
            groups = value.setdefault('分群', {})
            for gid, uid, profile in profiles:
                member = groups.setdefault(str(gid), {'群说明': '', '成员': {}}).setdefault('成员', {}).setdefault(str(uid), {'管理员设定': '', '备注': ''})
                member.setdefault('记录', profile['enabled'])
                member['数据库允许记录'] = profile['enabled']
                if profile['enabled'] and member.get('记录', True):
                    member['本人口述'] = profile['description']
                    member['本地观察'] = {'样本数': profile['samples'], '说话习惯': profile['observations'], '常聊主题': profile['topics']}
                elif not profile['enabled']:
                    for key in ('本人口述', '本地观察', '最近发言', '模型印象_非事实'):
                        member.pop(key, None)
            write_json(self.profile_path, value)

    def observe(self, gid, uid, profile, text=None, mid=None):
        with locked(self.profile_path):
            value = self.profiles(for_write=True)
            group = value.setdefault('分群', {}).setdefault(str(gid), {'群说明': '', '成员': {}})
            member = group.setdefault('成员', {}).setdefault(str(uid), {'管理员设定': '', '备注': ''})
            # Administrators may disable a profile directly in the JSON file.
            member.setdefault('记录', profile['enabled'])
            member['数据库允许记录'] = profile['enabled']
            if not profile['enabled']:
                for key in ('本人口述', '本地观察', '最近发言', '模型印象_非事实'):
                    member.pop(key, None)
            elif member.get('记录', True):
                member['本人口述'] = profile['description']
                member['本地观察'] = {'样本数': profile['samples'], '说话习惯': profile['observations'], '常聊主题': profile['topics']}
                if text:
                    recent = member.setdefault('最近发言', [])
                    if not recent or recent[-1].get('消息号') != str(mid):
                        recent.append({'消息号': str(mid), '内容': text[:160]})
                    member['最近发言'] = recent[-8:]
            write_json(self.profile_path, value)

    def clear(self, gid, uid):
        with locked(self.profile_path):
            data = self.profiles(for_write=True)
            members = data.get('分群', {}).get(str(gid), {}).get('成员', {})
            members.pop(str(uid), None)
            write_json(self.profile_path, data)

    def member(self, gid, uid):
        with locked(self.profile_path):
            return copy.deepcopy(self.profiles().get('分群', {}).get(str(gid), {}).get('成员', {}).get(str(uid), {}))

    def recording(self, gid, uid):
        member = self.member(gid, uid)
        return member.get('记录', True) and member.get('数据库允许记录', True)

    def switch_recording(self, gid, uid, enabled):
        with locked(self.profile_path):
            data = self.profiles(for_write=True)
            member = data.setdefault('分群', {}).setdefault(str(gid), {'群说明': '', '成员': {}}).setdefault('成员', {}).setdefault(str(uid), {'管理员设定': '', '备注': ''})
            member['记录'] = bool(enabled)
            write_json(self.profile_path, data)

    def context(self, gid, uid):
        data = self.profiles()
        group = data.get('分群', {}).get(str(gid), {})
        member = group.get('成员', {}).get(str(uid), {})
        if not member.get('记录', True) or not member.get('数据库允许记录', True):
            return {}
        # Even administrator descriptions of group members are descriptive data,
        # not a channel to replace the bot's system instructions.
        return {'本群说明': str(group.get('群说明', ''))[:160],
                '管理员记下的群友设定_资料': str(member.get('管理员设定', ''))[:300],
                '本人说过的_未核实': str(member.get('本人口述', ''))[:100],
                '模型印象_非事实': member.get('模型印象_非事实', {})}

    def bot_prompt(self):
        return str(self.profiles().get('机器人补充设定', ''))[:1200]

    def memory_due(self, gid, uid):
        member = self.member(gid, uid)
        if not member.get('记录', True) or not member.get('数据库允许记录', True):
            return None
        recent = member.get('最近发言', [])
        if len(recent) < 6 or time.time() - member.get('模型整理时间', 0) < 1800:
            return None
        if recent[-1]['消息号'] == member.get('模型整理至消息号'):
            return None
        return recent

    def save_impression(self, gid, uid, impression, recent):
        if not isinstance(impression, dict):
            return
        cleaned = {}
        for key in ('说话习惯', '常聊主题', '交流偏好'):
            if isinstance(impression.get(key), list):
                cleaned[key] = [str(s)[:60] for s in impression[key][:3] if isinstance(s, str)]
        with locked(self.profile_path):
            data = self.profiles(for_write=True)
            member = data.get('分群', {}).get(str(gid), {}).get('成员', {}).get(str(uid))
            if not member or not member.get('记录', True) or not member.get('数据库允许记录', True):
                return
            member['模型印象_非事实'] = cleaned
            member['模型整理时间'] = time.time()
            member['模型整理至消息号'] = recent[-1]['消息号']
            write_json(self.profile_path, data)


async def file_commands(assistant, event, body, admin):
    match = re.fullmatch(r'(?:设置)?(?:(?:本群|当前群))?(?:本地)?问答(?:触发)?概率(?:\s*(?:为|是|=|：|:)\s*|\s*)?(.*)', body)
    if match:
        if not admin:
            return True, '只有群主、群管或超管能改本群问答概率。'
        value = match[1].strip().rstrip('%％').strip()
        try:
            if not value:
                current = await assistant.files_call('probability', event.group_id)
                return True, f'本群本地问答概率：{current:g}%。'
            number = float(value)
            await assistant.files_call('set_probability', event.group_id, number)
            return True, f'本群本地问答概率改为{number:g}%。'
        except (ValueError, TypeError, OSError):
            return True, '用法：问答概率 10%，范围是0%～100%。'
    if body in {'模型分工', '模型配置'}:
        if not admin:
            return True, '这个配置让群管或超管看一下吧。'
        try:
            from testbot.plugins.nonebot_plugin_learning_chat.model_router import Router
            return True, Router(assistant.cloud).summary()
        except (ValueError, OSError, TypeError):
            return True, '模型配置没读出来，请检查文件格式。'
    return False, None
