"""NoneBot bridge. Retains the original ORM data and learning administration."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
import random
import hashlib,json,sys
import re
import time

from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from .engine import Entry, Index, Store, choose, normalize, safe_text, tool_reply
from .cloud import Cloud, reason_text
from .autonomy import LocalGate
from .conversation import Conversation,conversational
from .records import RecordBook
from .community import extra_commands
from .chat_feedback import switch_status
from testbot.plugins.chat_storage import ChatFiles, file_commands
from .chat_media import prepare_media, previous_image_context
from .understanding import contextual_candidates
from .model_router import summarize_profile, retrieve_memories
from testbot.plugins.persona_utils import load_persona,attack,identity_question,read_affinity
from .config import config_manager, NICKNAME, COMMAND_START
from .handler import LearningChat, Result
from .models import ChatMessage, ChatAnswer, ChatContext

HELP = '智能聊天（本地优先，可选省钱云聊）\n@我 或叫我的昵称后说话；引用我的消息也能继续聊。\n检索本群学过的问答，支持相近说法与短时上下文；没把握会追问。\n管理员：智能教学 问题 => 回答\n管理员：问答概率 10%（默认100%）\n管理员：模型分工\n管理员：智能删除 问题 / 智能词库\n管理员：智能模式 安静 / 智能模式 自然\n管理员：智能开启 / 智能关闭\n管理员：智能重建索引 / 智能恢复\n所有人：智能状态 / 智能帮助\n管理员：开启云聊 / 关闭云聊（默认关闭）\n所有人：云聊状态 / 云聊帮助 / 清空智能上下文\n管理员：开启主动接话 / 关闭主动接话\n所有人：主动接话状态\n超管：云聊用量\n人格与记录：人格 / 学到的知识 / 画像帮助 / 我的画像\n自己的记忆：记住 昵称=小明 / 我的记忆\n忘记记忆 昵称 / 清空我的记忆\n也可以@我说：记住我的昵称是小明、我叫什么？\n工具：@我 计算 (12+8)*3 / 今天星期几 / 现在几点\n安静模式只应答点名；自然模式低频插话。\n个人记忆会在群内回复。'


@dataclass
class Session:
    updated: float = 0
    turns: deque = field(default_factory=lambda: deque(maxlen=3))
    pending: list = field(default_factory=list)
    cloud_turns: deque = field(default_factory=lambda: deque(maxlen=2))
    context_signature: str = ""


@dataclass
class GroupState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    index: Index | None = None
    indexed_at: float = 0
    last_send: float = 0
    retry_after: float = 0
    recent: deque = field(default_factory=lambda: deque(maxlen=8))
    sent: int = 0
    failures: int = 0
    updated: float = 0
    cloud_pending: tuple | None = None
    cloud_reason: str = ""
    auto_gate: LocalGate = field(default_factory=LocalGate)
    conversation: Conversation = field(default_factory=Conversation)


class Assistant:
    def __init__(self, root=Path("data/learning_chat/local_intelligence")):
        self.root = root
        self._store = None
        self.records = RecordBook(root)
        self.files = ChatFiles(root)
        self.profile_tasks = set()
        self.exported_profiles = False
        self.groups = OrderedDict()
        self.sessions = OrderedDict()
        self.cloud = Cloud(root)
        self.peer_ids = set()
        self.peer_checked = -1e20
        self.registered_ids = set()

    def store(self):
        if self._store is None:
            self._store = Store(self.root)
        return self._store

    async def db(self, method, *args, **kwargs):
        return await asyncio.to_thread(lambda: getattr(self.store(), method)(*args, **kwargs))

    async def record_db(self,method,*args,**kwargs):
        return await asyncio.to_thread(lambda:getattr(self.records,method)(*args,**kwargs))

    async def files_call(self, method, *args):
        return await asyncio.to_thread(lambda: getattr(self.files, method)(*args))

    async def local_probability(self, event):
        try:
            return await self.files_call('allow_qa', event.group_id, None, f'{event.self_id}:{event.group_id}:{event.message_id}')
        except (OSError, ValueError, TypeError):
            logger.warning('本地问答概率配置有误，本轮不回复。')
            return False

    async def update_profile(self, gid, uid, text=None, mid=None):
        try:
            profile = await self.record_db('profile', gid, uid)
            await self.files_call('observe', gid, uid, profile, text, mid)
        except (OSError, ValueError, TypeError):
            logger.warning('群友人设文件暂时无法更新，原记录保留。')

    async def summarize_profile(self, event):
        try:
            cfg = await self.db('settings', event.group_id)
            if cfg['enabled'] and cfg['cloud_enabled'] and cfg['profile_recording']:
                await asyncio.wait_for(summarize_profile(self.cloud, event.self_id, event.group_id, event.user_id), 15)
        except Exception:
            logger.warning('群友印象整理跳过，本次聊天不受影响。')

    def group(self, gid):
        if gid not in self.groups:
            if len(self.groups) >= 128:
                for old, state in list(self.groups.items()):
                    if not state.lock.locked():
                        del self.groups[old]
                        break
            self.groups[gid] = GroupState()
        self.groups.move_to_end(gid)
        state = self.groups[gid]
        state.updated = time.monotonic()
        return state

    def session(self, gid, uid, ttl):
        key = gid, uid
        now = time.monotonic()
        current = self.sessions.get(key)
        if not current or now - current.updated > ttl:
            current = self.sessions[key] = Session()
        self.sessions.move_to_end(key)
        current.updated = now
        while len(self.sessions) > 1024:
            self.sessions.popitem(last=False)
        return current

    def addressed(self,event):
        text = event.get_plaintext().strip()
        direct = event.to_me or bool(event.reply and event.reply.sender.user_id == event.self_id)
        p=load_persona(self.root)
        others={"千鸟酱","千鸟","小千鸟","菲姆酱","菲姆","塞拉菲姆"}-set(p.aliases)
        nicknames = sorted((set(get_driver().config.nickname)-others)|set(p.aliases), key=len, reverse=True)
        for name in nicknames:
            if text.startswith(name) and (len(text) == len(name) or not (name[-1:].isascii() and text[len(name):len(name)+1].isalnum())):
                text = text[len(name):].lstrip(" ,，:：!！")
                direct = True
                break
        return direct, text

    @staticmethod
    def admin(event):
        return str(event.user_id) in get_driver().config.superusers or event.sender.role in {"admin", "owner"}

    async def command(self, event, text, direct, state):
        # Known commands also work without a prefix; permissions are checked below.
        is_command = text.startswith(("#", "\\"))
        body = text[1:].strip() if is_command else text
        admin = self.admin(event)
        gid, uid = event.group_id, event.user_id
        if body in {'开启群聊上下文','关闭群聊上下文','清空群聊上下文','群聊上下文状态'}:
            if body=='群聊上下文状态':
                cfg=await self.db('settings',gid)
                return True,'群聊上下文：'+('开' if cfg['group_context_enabled'] else '关')
            if not admin:return True,'只有群主、群管或超管能修改本群上下文。'
            if body=='清空群聊上下文':
                state.conversation.clear();return True,'这段群聊已经清掉了。'
            enabled=body=='开启群聊上下文'
            await self.db('set_setting',gid,group_context_enabled=enabled)
            if not enabled:state.conversation.clear()
            return True,'群聊上下文'+('开好了。' if enabled else '关好了。')
        handled,response=await file_commands(self,event,body,admin)
        if handled:return handled,response
        handled,response=await extra_commands(self,event,body,admin)
        if handled:
            return handled,response
        if body in {"开启主动接话", "关闭主动接话"}:
            if not admin:
                return True,'只有群主、群管或超管能改这个开关哦。'
            enable=body=="开启主动接话"
            if enable:
                await self.db("set_setting",gid,autonomous_enabled=True,cloud_enabled=True,mode="自然")
                return True,"主动接话开好了。"
            await self.db("set_setting",gid,autonomous_enabled=False)
            return True,"好，不主动接话了。"
        if body=='主动接话状态':return True,await switch_status(self,event,'主动')
        if body == "云聊帮助":
            return True, '群聊云聊：本地优先，按任务选模型，结合本群上下文、人设和本人记忆。\n管理员 开启云聊 / 关闭云聊；默认关闭。主动接话用 开启主动接话 / 关闭主动接话。\n所有人 云聊状态 / 清空智能上下文；超管 云聊用量。\n每台每人每天60次、每群120次；两台最多每天300次模型请求，主动最多120次模型请求（一条云聊可能用到多个请求）；还受每天1元、每月20元共享估算预算限制。\n近期群聊按预算选最多6条，本人最近两轮云聊、少量个人记忆及人工参考；不上传整个词库。管理员可 开启/关闭群聊上下文。'
        if body in {"开启云聊", "关闭云聊", "云聊开启", "云聊关闭"}:
            if not admin:
                return True, '只有群主、群管或超管能开关本群云聊哦。'
            enable = body in {"开启云聊", "云聊开启"}
            await self.db("set_setting", gid, cloud_enabled=enable)
            if enable:
                return True, '云聊开好了。'
            return True, '云聊关好了。'
        if body == "清空智能上下文":
            self.sessions.pop((gid,uid),None)
            await self.cloud.db("clear_cache",event.self_id,gid,uid)
            return True, '这段对话清掉了。'
        if body=='云聊状态':return True,await switch_status(self,event,'云聊')
        if body == "云聊用量":
            if str(uid) not in get_driver().config.superusers:
                return True, '只有超管能看两台机器人的云聊用量。'
            cloud_cfg,configured,stats = await self.cloud.status()
            if not cloud_cfg or stats is None:
                return True, "云聊配置或用量账本暂不可用，本地聊天不受影响。"
            return True, f"两台机器人共享云聊用量（北京时间）\n今日请求：{stats['calls']}/{cloud_cfg['daily_calls']}\n其中主动接话：{stats['auto_calls']}/{cloud_cfg['auto_daily_calls']}\n今日保守估算：{stats['spent']:.4f}元，阈值{cloud_cfg['daily_budget_yuan']}元\n本月保守估算：{stats['monthly']:.4f}元，阈值{cloud_cfg['monthly_budget_yuan']}元\n结果不明请求：{stats['unknown']}次，保留预占额度。\n按配置的模型单价估算，以平台实际账单为准。"
        if body == "智能帮助":
            return True, HELP
        if body=='智能状态':return True,await switch_status(self,event)
        managed = body in {"智能开启", "智能关闭", "智能恢复", "智能重建索引", "智能词库"} or body.startswith(("智能模式", "智能教学", "智能删除"))
        if managed:
            if not admin:
                return True, "只有超管、群主或群管理员可以修改本群智能设置与公共问答。"
            if body in {"智能开启", "智能关闭"}:
                await self.db("set_setting", gid, enabled=body == "智能开启")
                return True, "聊天" + ("开好了。" if body == "智能开启" else "这边先关掉了。")
            if body.startswith("智能模式"):
                mode = body.removeprefix("智能模式").strip()
                if mode not in {"安静", "自然"}:
                    return True, '用法：智能模式 安静 或 智能模式 自然'
                await self.db("set_setting", gid, mode=mode)
                return True, f"已切换为{mode}模式。"
            if body == "智能恢复":
                state.retry_after = 0
                state.last_send = 0
                return True, "好，可以再试着跟我说话了。"
            if body == "智能重建索引":
                state.index = None
                return True, "好，问答索引会重新整理。"
            if body == "智能词库":
                entries = await self.db("entries", gid)
                return True, "本群人工问答：\n" + ("\n".join(e.question for e in entries[:20]) or '还没有，用 智能教学 问题 => 回答 添加。') + (f"\n共{len(entries)}条，显示最近20条。" if len(entries) > 20 else "")
            if body.startswith("智能删除"):
                question = body.removeprefix("智能删除").strip()
                if not question:
                    return True, '用法：智能删除 问题'
                deleted = await self.db("forget_qa", gid, question)
                if deleted:await self.record_db("deactivate_question",gid,question)
                state.index = None
                return True, "这组问答删掉了。" if deleted else "没有找到这组人工问答。"
            teaching = body.removeprefix("智能教学").strip()
            if "=>" not in teaching:
                return True, '用法：智能教学 问题 => 回答'
            question, answer = map(str.strip, teaching.split("=>", 1))
            ban_words = config_manager.config.ban_words + config_manager.get_group_config(gid).ban_words
            if any(word and word in question + answer for word in ban_words):
                return True, "包含已配置的屏蔽词，未保存。"
            if attack(question) or attack(answer) or not load_persona(self.root).output_ok(answer):
                return True,'这条内容不适合收进问答，没有保存。'
            result = await self.db("teach", gid, uid, question, answer, time.time())
            if result.startswith("记住"):
                await self.record_db("learn",gid,uid,event.message_id,question,answer,True,"管理员教学")
            state.index = None
            return True, result
        if body == "我的记忆":
            data = await self.db("memories", gid, uid)
            return True, "你在本群让我记住的内容：\n" + ("\n".join(f"{k}：{v}" for k, v in data.items()) or "暂无")
        if body == "清空我的记忆":
            await self.db("forget_memory", gid, uid)
            return True, "你让我记住的那些事，已经清空了。"
        if body.startswith("忘记记忆"):
            key = body.removeprefix("忘记记忆").strip()
            if not key:
                return True, '用法：忘记记忆 昵称'
            deleted = await self.db("forget_memory", gid, uid, key)
            return True, "已忘记。" if deleted else "没找到这件事。"
        if body.startswith("记住"):
            content = body.removeprefix("记住").removeprefix("我的").strip()
            parts = re.split(r"\s*[=＝]\s*|是", content, maxsplit=1)
            if len(parts) != 2:
                return True, '用法：记住 昵称=小明，或@我说“记住我的昵称是小明”。'
            if attack(content):
                return True,'这个不算个人记忆，我的名字和性格还是原来的。'
            return True, await self.db("remember", gid, uid, parts[0].strip(), parts[1].strip(), time.time())
        return False, None

    async def build_index(self, legacy, cfg, state):
        gid = legacy.data.group_id
        curated = await self.db("entries", gid)
        # Load bounded, local-group records only. Never fetch the whole global history.
        answers = await ChatAnswer.filter(group_id=gid).select_related("context").order_by("-time", "-id").limit(cfg["max_history_answers"])
        messages = await ChatMessage.filter(group_id=gid).order_by("-time", "-id").limit(4000)
        entries = list(curated)
        # Batch blacklist checks instead of one DB roundtrip per candidate.
        from .models import ChatBlackList
        blacklist = await ChatBlackList.all()
        forbidden = {b.keywords for b in blacklist if b.global_ban or gid in b.ban_group_id}
        def assemble():
            forms = {}
            for msg in messages:
                if msg.user_id != legacy.bot_id and msg.is_plain_text and safe_text(msg.message, 180):
                    forms.setdefault(msg.keywords, msg.message)
            for answer in answers:
                if not answer.context or answer.keywords in forbidden or answer.context.keywords in forbidden:
                    continue
                question = forms.get(answer.context.keywords, answer.context.keywords)
                for text in answer.messages[:3]:
                    if safe_text(text) and safe_text(question, 180) and not any(w and w in text + question for w in legacy.ban_words):
                        entries.append(Entry(question, text, answer.count, False, answer.id))
            seen = set()
            unique = []
            for entry in entries:
                key = normalize(entry.question), normalize(entry.answer)
                if key not in seen:
                    seen.add(key)
                    unique.append(entry)
            return Index(unique[:cfg["max_history_answers"] + 2000])
        index = await asyncio.to_thread(assemble)
        # Keep at most four indexes resident; cooldowns remain intact for other groups.
        cached = [(gid, other) for gid, other in self.groups.items()
                  if other is not state and other.index is not None]
        while len(cached) >= 4:
            _, other = cached.pop(0)
            other.index = None
        state.index = index
        state.indexed_at = time.monotonic()

    async def respond(self, event, state):
        direct, text = self.addressed(event)
        handled, response = await self.command(event, text, direct, state)
        if handled:
            return response, True, None
        if await self.files_call('claimed_qa',f'{event.self_id}:{event.group_id}:{event.message_id}'):return None,direct,None
        if attack(text):
            return (load_persona(self.root).boundary if direct else None),direct,None
        cfg = await self.db("settings", event.group_id)
        legacy = LearningChat(event)
        legacy.to_me = direct
        # Keep original learning switches and reply-to-ban management working.
        if direct and any(w in text for w in {"学说话", "快学", "开启学习", "闭嘴", "别学", "关闭学习", "不可以", "达咩", "不能说这"}) and len(text) <= 20:
            answers = await legacy.answer()
            state.index = None
            return (str(answers[0]) if answers else None), True, None
        if not cfg["enabled"] or not config_manager.config.total_enable or not legacy.config.enable:
            return None, direct, None
        if event.user_id in legacy.ban_users or event.user_id in cfg["ignored_users"]:
            return None, direct, None
        if direct and identity_question(text):
            p=load_persona(self.root)
            return f"我是{p.name}。{p.summary}",True,None
        if not safe_text(text, 300) or any(w and w in text for w in legacy.ban_words):
            return None, direct, None
        if text.startswith(tuple({"#", "\\", "/", "."} | set(COMMAND_START))):
            return None, direct, None
        if any(s.type == "at" and str(s.data.get("qq")) != str(event.self_id) for s in event.message) and not direct:
            return None, direct, None
        if not await legacy._check_allow(legacy.data):
            return None, direct, None
        # Learn only after validation. The historical routine is patched to require a
        # real reply or a short, related exchange between different human speakers.
        if cfg["profile_recording"] and not getattr(event,"chat_media_input",False) and await self.files_call("recording",event.group_id,event.user_id):
            await self.record_db("observe",event.group_id,event.user_id,event.message_id,text,event.time)
            await self.update_profile(event.group_id,event.user_id,text,event.message_id)
        if not getattr(event,"chat_media_input",False):
            await legacy._learn()
            await legacy.data.save()
        autonomous=False
        if not direct:
            if cfg["mode"]=="安静":
                return None,False,None
            if cfg["autonomous_enabled"] and cfg["cloud_enabled"]:
                try:
                    policy=await asyncio.to_thread(self.cloud.configuration)
                    autonomous=state.auto_gate.choose(text,quoted=bool(event.reply),segments=tuple(s.type for s in event.message),interval=policy["auto_interval_seconds"],probability=policy["auto_probability"],room=state.conversation.signals())
                except (OSError,ValueError,TypeError):
                    autonomous=False
            if not autonomous and random.random()>=cfg["passive_probability"]:
                return None,False,None
        now = time.monotonic()
        if now - state.last_send < (cfg["direct_interval"] if direct else cfg["passive_interval"]):
            return None, direct, None
        session = self.session(event.group_id, event.user_id, cfg["context_seconds"])
        if direct:
            if answer := tool_reply(text):
                return answer, True, None
            memory_question = re.fullmatch(r"(?:我的(.{1,24}?)(?:是(?:什么|多少)|是什么|是多少)|我叫什么(?:名字)?|你还记得我(?:的(.{1,24}))?吗)[?？]?", text)
            if memory_question:
                data = await self.db("memories", event.group_id, event.user_id)
                key = memory_question[1] or memory_question[2] or "昵称"
                value = data.get(normalize(key)) or (data.get("名字") if key == "昵称" else None)
                return (f"你让我记住的{key}是：{value}" if value else f"你还没让我记住{key}，可以说：#记住 {key}=内容"), True, None
            selection = re.fullmatch(r"(?:第)?([1-3一二三])(?:个|条)?", text)
            if selection and session.pending:
                number = "一二三".index(selection[1]) if selection[1] in "一二三" else int(selection[1])-1
                if number < len(session.pending):
                    candidate = session.pending[number]
                    # Revalidate below, in case an administrator banned it meanwhile.
                    if await self.allowed(candidate, legacy):
                        if not await self.local_probability(event):return None,True,None
                        session.pending.clear()
                        return candidate.answer, True, candidate.question
        if state.index is None or now - state.indexed_at >= cfg["index_refresh_seconds"]:
            await self.build_index(legacy, cfg, state)
        context = " ".join(q for q, _ in session.turns)
        query = text
        if direct and session.turns and re.match(r"^(那|那么|这个|它|然后|还有)", text):
            query = re.sub(r"^(那么|那|这个|它|然后|还有)[呢吗，, ]*", "", text).strip("？? ")
            if len(normalize(query)) <= 2:
                query = session.turns[-1][0]
            else:
                query = session.turns[-1][0] + " " + query
        recent = set(state.recent) if not direct else set()
        results = await asyncio.to_thread(state.index.search, query, context, recent)
        if direct:
            # The bounded fuzzy cache must not erase years of older learning.
            # Original keyword indexes permit exact lookup across the full history.
            probe = ChatMessage(group_id=event.group_id, user_id=event.user_id,
                                message_id=0, message=text, raw_message=text,
                                plain_text=text, time=event.time)
            keys = {legacy.data.keywords, probe.keywords}
            contexts = await ChatContext.filter(keywords__in=keys).limit(20)
            negative = bool(re.search("不|没|别|禁止|勿", normalize(text)))
            context_ids = [c.id for c in contexts if bool(re.search("不|没|别|禁止|勿", normalize(c.keywords))) == negative]
            if context_ids:
                rows = await ChatAnswer.filter(group_id=event.group_id, context_id__in=context_ids, count__gte=2).order_by("-count", "-time").limit(30)
                known = {(e.source_id, e.answer) for _, e in results}
                for row in rows:
                    for answer in row.messages[:2]:
                        if safe_text(answer) and (row.id, answer) not in known:
                            results.append((0.88, Entry(text, answer, row.count, False, row.id)))
                results.sort(key=lambda pair: (pair[0], pair[1].curated, pair[1].count), reverse=True)
        # Check current blacklists on every returned candidate, including cached QA.
        validated = []
        for score, entry in results:
            if await self.allowed(entry, legacy):
                validated.append((score, entry))
                if len(validated) >= 5:
                    break
        results = contextual_candidates(text, validated, normalize)
        candidate, ambiguous = choose(results, direct)
        if candidate:
            if not await self.local_probability(event):return None,direct,None
            if ambiguous:
                if not direct:
                    return None, False, None
                session.pending = [e for _, e in results[:3]]
                lines = [f"{i+1}. {e.question} → {e.answer[:45]}" for i, e in enumerate(session.pending)]
                return "我学到的说法有冲突，你指哪一种？@我回复序号。\n" + "\n".join(lines), True, None
            return candidate.answer, direct, candidate.question
        if direct:
            if re.fullmatch(r"你好[呀啊]?|嗨|在吗|在不在", text):
                return load_persona(self.root).greeting, True, None
            if re.fullmatch(r"谢谢(?:你)?[啦啊]?|多谢|谢啦", text):
                return "不客气。", True, None
            # Never spend cloud tokens on ambiguous local answers or ordinary chatter.
            state.cloud_reason = ""
            if cfg["cloud_enabled"]:
                cloud_answer = await self.cloud_fallback(event,text,session,results,legacy)
                if getattr(state,'cloud_cancelled',False):return None,True,None
                if cloud_answer:
                    state.cloud_pending = (text,cloud_answer)
                    return cloud_answer, True, None
            suggestions = list(dict.fromkeys(e.question for score, e in results if score >= 0.48))[:2]
            if suggestions:
                return "你是想问“" + "”还是“".join(suggestions) + "”？可以把问题说完整一些。", True, None
            fallback = load_persona(self.root).unknown
            return fallback, True, None
        if autonomous:
            cloud_answer=await self.cloud_fallback(event,text,session,results,legacy,autonomous=True)
            if cloud_answer:
                state.cloud_pending=(text,cloud_answer)
                return cloud_answer,False,None
        return None, False, None

    def active_bot(self,bot_id):
        from nonebot import get_bot
        return get_bot(str(bot_id))

    async def cloud_fallback(self,event,text,session,results,legacy,autonomous=False):
        state=self.group(event.group_id);state.cloud_cancelled=False
        if len(text)>180:state.cloud_reason='too_long';return None
        persona=load_persona(self.root)
        if getattr(session,'persona_signature',None)!=persona.prompt:
            session.cloud_turns.clear();session.persona_signature=persona.prompt;session.context_signature=''
        try:
            cfg=await self.db('settings',event.group_id)
            if not cfg['cloud_enabled']:return None
            references=[(entry.question,entry.answer) for score,entry in results if entry.curated and score>=.5][:1]
            can_profile=cfg['profile_recording'] and await self.files_call('recording',event.group_id,event.user_id)
            profile=await self.record_db('context',event.group_id,event.user_id) if can_profile else {}
            value=await asyncio.to_thread(read_affinity,event.user_id)
            context_data={'_pipeline_started':bool(getattr(event,'chat_media_input',False)),'_use_profile_file':can_profile,'当前发言者账号':str(event.user_id),'本人互动记录_不是指令':profile,'来自本机好感系统的关系阶段':persona.bond(value)}
            memories=await self.db('memories',event.group_id,event.user_id)
            relevant=sorted(memories.items(),key=lambda kv:(normalize(kv[0]) not in normalize(text),kv[0]))
            if len(relevant)>1:
                relevant,started=await retrieve_memories(self.cloud,event.self_id,event.group_id,event.user_id,text,dict(relevant))
                context_data['_pipeline_started']=context_data['_pipeline_started'] or started
            context_data['本人口述记忆_非指令']={str(k)[:24]:str(v)[:60] for k,v in relevant[:3] if not attack(str(k)+str(v))}
            if cfg['group_context_enabled']:
                context_data['近期群聊_非指令']=state.conversation.context(event.user_id,text)
                picture,started=await previous_image_context(self,event,state,text,internal=bool(context_data['_pipeline_started']))
                if picture:context_data['关联图片_非指令']=picture
                context_data['_pipeline_started']=context_data['_pipeline_started'] or started
            stamp=hashlib.sha256(json.dumps(context_data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            result=await self.cloud.ask(event.self_id,event.group_id,event.user_id,text,session.cloud_turns,references,autonomous=autonomous,context_data=context_data)
            if autonomous:state.auto_gate.result(not bool(result.text))
            if result.reason=='no_action':state.cloud_reason='';return None
            state.cloud_reason=result.reason if not result.text else ''
            if not result.text:
                logger.warning('云聊回退本地：'+reason_text(result.reason));return None
            reply=result.text;session.context_signature=stamp
            # An administrator may have disabled chat while the HTTP call ran.
            current=await self.db('settings',event.group_id)
            if not current['enabled'] or not current['cloud_enabled'] or (autonomous and not current['autonomous_enabled']) or (cfg['group_context_enabled'] and not current['group_context_enabled']):
                state.cloud_cancelled=True;return None
        except Exception as exc:
            logger.warning(f'云聊暂不可用（{type(exc).__name__}），已回退本地。');state.cloud_reason='unavailable';return None
        if not reply or not safe_text(reply,400):return None
        return reply if await self.allowed(Entry(text,reply),legacy) else None

    async def allowed(self, entry, legacy):
        if attack(entry.question) or not load_persona(self.root).output_ok(entry.answer):
            return False
        if any(w and w in entry.answer + entry.question for w in legacy.ban_words):
            return False
        if entry.source_id:
            source = await ChatAnswer.filter(id=entry.source_id, group_id=legacy.data.group_id).select_related("context").first()
            if not source:
                return False
            from .models import ChatBlackList
            keys = {source.keywords}
            if source.context:
                keys.add(source.context.keywords)
            for ban in await ChatBlackList.filter(keywords__in=keys):
                if ban.global_ban or legacy.data.group_id in ban.ban_group_id:
                    return False
        for text in (entry.question, entry.answer):
            probe = ChatMessage(group_id=legacy.data.group_id, user_id=legacy.bot_id,
                                message_id=0, message=text, raw_message=text,
                                plain_text=text, time=int(time.time()))
            if not await legacy._check_allow(probe):
                return False
        return True

    async def send(self, bot, event, state, text, cfg, topic=None, control=False):
        now = time.monotonic()
        if now < state.retry_after and not control:
            return False
        if not control:
            from testbot.plugins.feature_controls import permitted
            if not await permitted(bot,event):
                state.cloud_pending=None
                return False
        # Plain text segment prevents learned content from turning into CQ actions.
        try:
            result = await asyncio.wait_for(bot.send_group_msg(group_id=event.group_id, message=Message(MessageSegment.text(text))), cfg["send_timeout"])
        except Exception as exc:
            state.failures += 1
            state.retry_after = time.monotonic() + cfg["failure_cooldown"]
            logger.warning(f"本地智能发送失败（{type(exc).__name__}），冷却后自动恢复；不重发本条，避免重复消息。")
            return False
        if isinstance(result,dict) and result.get('muted'):
            state.cloud_pending=None;return False
        if not control:state.conversation.add(event.self_id,load_persona(self.root).name,'bot-'+str(result.get('message_id',0)),text,bot=True)
        state.last_send = time.monotonic()
        state.retry_after = 0
        state.sent += 1
        state.recent.append(normalize(text))
        if topic:
            session = self.session(event.group_id, event.user_id, cfg["context_seconds"])
            session.turns.append((topic, text))
        if state.cloud_pending and state.cloud_pending[1] == text:
            session = self.session(event.group_id,event.user_id,cfg["context_seconds"])
            session.cloud_turns.append(state.cloud_pending)
            state.cloud_pending = None
            # Optional summaries run after sending; they cannot delay the reply.
            if cfg.get('profile_recording') and len(self.profile_tasks)<4:
                task=asyncio.create_task(self.summarize_profile(event))
                self.profile_tasks.add(task);task.add_done_callback(self.profile_tasks.discard)
            # Generated replies are not training examples for the old learning database.
            return True
        # DB failure must not cause retry of an already delivered QQ message.
        try:
            await ChatMessage.create(group_id=event.group_id, user_id=event.self_id,
                                     message_id=result["message_id"], message=text, raw_message=text,
                                     plain_text=text, time=int(time.time()))
        except Exception as exc:
            logger.warning(f"本地智能消息已发出，但学习日志写入失败（{type(exc).__name__}）。")
        return True

    async def remember_bot(self,bot_id):
        if str(bot_id) not in self.registered_ids:
            await self.cloud.db("register_bot",bot_id)
            self.registered_ids.add(str(bot_id))
        if time.monotonic()-self.peer_checked>=10:
            self.peer_ids=await self.cloud.db("peer_ids")
            self.peer_checked=time.monotonic()

    async def handle(self, bot: Bot, event: GroupMessageEvent):
        if event.user_id == event.self_id:
            return
        try:
            await self.remember_bot(event.self_id)
            if str(event.user_id) in self.peer_ids:
                return
        except Exception:
            # Shared ledger failure must not prevent ordinary local functions.
            pass
        if not self.exported_profiles:
            try:
                await self.files_call('initialize')
                profiles=await self.record_db('export_profiles')
                await self.files_call('import_profiles',profiles)
                self.exported_profiles=True
            except (OSError,ValueError,TypeError):
                logger.warning('旧画像暂时未导出，请检查人设文件。')
        state = self.group(event.group_id)
        cfg=await self.db('settings',event.group_id)
        direct,stripped=self.addressed(event)
        control = (stripped.lstrip("#\\").startswith(("问答概率", "问答触发概率", "设置问答", "本群问答", "当前群问答", "本地问答", "设置本群问答", "设置当前群问答", "设置本地问答", "模型分工", "模型配置", "开启群聊上下文", "关闭群聊上下文", "清空群聊上下文", "群聊上下文状态", "人格", "查看人格", "画像", "我的画像", "我的性格", "学到的知识", "知识详情", "确认知识", "删除知识", "开启画像记录", "关闭画像记录", "清空我的画像", "开启本群画像记录", "关闭本群画像记录", "群友画像", "智能", "云聊", "开启云聊", "关闭云聊", "开启主动接话", "关闭主动接话", "主动接话状态", "清空智能上下文", "我的记忆", "记住", "忘记记忆", "清空我的记忆")))
        group_cfg=config_manager.get_group_config(event.group_id)
        if cfg['enabled'] and cfg['cloud_enabled'] and cfg['group_context_enabled'] and config_manager.config.total_enable and group_cfg.enable and not control:
            words=config_manager.config.ban_words+group_cfg.ban_words
            users=set(config_manager.config.ban_users+group_cfg.ban_users+cfg['ignored_users'])
            segments=event.message
            safe_segments=all(s.type in ('text','reply','image') or (s.type=='at' and str(s.data.get('qq'))==str(event.self_id)) for s in segments)
            allowed=event.user_id not in users and not attack(stripped) and not any(w and w in stripped for w in words)
            images=[s for s in segments if s.type=='image']
            if allowed and safe_segments:
                if len(images)==1 and (not stripped or conversational(stripped)):
                    state.conversation.add_image(event.user_id,event.sender.card or event.sender.nickname,event.message_id,images[0].data)
                if conversational(stripped) and not images:
                    state.conversation.add(event.user_id,event.sender.card or event.sender.nickname,event.message_id,stripped,reply_to=event.reply.sender.user_id if event.reply else '')
            # Unaddressed images are retained as short-lived references only.
            # They must not hold the lock and discard the following text message.
            if images and not direct:
                from .model_router import Router
                try:
                    if Router(self.cloud).config['media'].get('only_addressed',True):return
                except (OSError,ValueError,TypeError):return
        if state.lock.locked():
            # Admin switches must remain responsive during an HTTP call.
            if control:
                handled,response=await self.command(event,stripped,direct,state)
                if handled and response:await self.send(bot,event,state,response,cfg,control=True)
            return
        async with state.lock:
            try:
                cfg = await self.db("settings", event.group_id)
                text = event.get_plaintext().strip()
                direct, stripped = self.addressed(event)
                control = (stripped.lstrip("#\\").startswith(("问答概率", "问答触发概率", "设置问答", "本群问答", "当前群问答", "本地问答", "设置本群问答", "设置当前群问答", "设置本地问答", "模型分工", "模型配置", "开启群聊上下文", "关闭群聊上下文", "清空群聊上下文", "群聊上下文状态", "人格", "查看人格", "画像", "我的画像", "我的性格", "学到的知识", "知识详情", "确认知识", "删除知识", "开启画像记录", "关闭画像记录", "清空我的画像", "开启本群画像记录", "关闭本群画像记录", "群友画像", "智能", "云聊", "开启云聊", "关闭云聊", "开启主动接话", "关闭主动接话", "主动接话状态", "清空智能上下文", "我的记忆", "记住", "忘记记忆", "清空我的记忆")))
                if not control and cfg['cloud_enabled']:
                    await asyncio.sleep(.8 if direct else 1.6)
                    quiet=sys.modules.get('testbot.plugins.bot_admin.quiet')
                    if quiet and quiet.is_muted(bot,event.group_id):return
                    cfg=await self.db('settings',event.group_id)
                    if not cfg['cloud_enabled'] or not cfg['enabled']:return
                    if cfg['group_context_enabled'] and all(s.type in ('text','at','reply') for s in event.message):
                        merged,mid=state.conversation.merge(event.user_id,event.message_id)
                        if merged:
                            event=event.copy(deep=True,update={'message':Message(MessageSegment.text(merged)),'raw_message':merged,'message_id':int(mid),'to_me':direct})
                if time.monotonic() < state.retry_after and not control:
                    return
                state.cloud_pending = None
                if not control:
                    try:
                        event=await asyncio.wait_for(prepare_media(self,bot,event,cfg,direct),30)
                    except Exception as exc:
                        logger.warning(f'媒体识别跳过（{type(exc).__name__}），后续消息可继续处理。')
                        return
                    if event is None:return
                answer, _, topic = await asyncio.wait_for(self.respond(event, state), 65)
                if answer:
                    await self.send(bot, event, state, answer, cfg, topic, control)
            except Exception as exc:
                logger.opt(exception=True).warning(f"本地智能处理异常（{type(exc).__name__}），已释放本群锁，后续消息可继续处理。")


assistant = Assistant()
