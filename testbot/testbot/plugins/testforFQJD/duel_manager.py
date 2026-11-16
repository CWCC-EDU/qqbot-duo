"""Duel lifecycle, independent of NoneBot so it can be tested without a QQ login.

The legacy calculator still owns damage/status effects. This module owns only
invitations, actor selection, turn boundaries, deadlines and finalization.
"""
import asyncio
import copy
import json
import logging
import os
import random
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from .skill_rules import RuleStore, SkillEngine
    from .group_settings import GroupSettings
    from .commands import format_commands
else:
    from skill_rules import RuleStore, SkillEngine
    from group_settings import GroupSettings
    from commands import format_commands


log = logging.getLogger(__name__)
ATTRIBUTES = ["普通", "水", "火", "草", "暗", "光", "？"]
STATES = ["无", "疲惫", "防御", "流血", "顽强", "荆棘", "易伤", "混乱", "时滞", "迷惑", "失明"]


class PlainText(str):
    """Transport marker: mode confirmations must stay readable without images."""


def player_status_lines(data, slot):
    """Shared text/image labels; show the stored accuracy, including >100%."""
    modifiers = data.get("_rule_modifiers", {}).get(slot, {})
    accuracy = f"{(data[f'accuracy{slot}'] + modifiers.get('accuracy', 0)) * 100:.1f}".rstrip("0").rstrip(".")
    attack = max(0, min(12, data[f'atk{slot}'] + modifiers.get('attack', 0))) - 6
    lines = [f"{data[f'player{slot}']}:",
            f"属性:{ATTRIBUTES[data[f'attribute{slot}']]}",
            f"攻击等级:{attack:+}",
            f"命中值:{accuracy}%",
            f"状态:{STATES[data[f'state{slot}']]}"]
    if modifiers.get("names"):
        lines.append("特性:" + "、".join(modifiers["names"]))
    return lines


@dataclass
class Duel:
    bot: object
    event: object
    data: dict
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    phase: str = "invited"
    first: int = 1
    revision: int = 0
    seen: set = field(default_factory=set)
    choices_turn: int = -1
    pending_result: str = ""
    prefer_text: bool = False
    rules: object = None
    rule_vars: dict = field(default_factory=lambda: {1: {}, 2: {}})


class DuelManager:
    invitation_timeout = 30
    claim_timeout = 30
    automatic_timeout = 90
    max_turns = 11
    send_timeout = 10

    def __init__(self, calculator, data_dir, send, scheduler=None,
                 dbcontrol=None, getcollection=None, render=None,
                 bot_name="本裁判", clock=time.monotonic, rng=None, command_prefix="#"):
        self.calculator = calculator
        self.data_dir = Path(data_dir).resolve()
        self.group_settings = GroupSettings(self.data_dir / 'duel_settings.json', command_prefix)
        self.command_prefix = self.group_settings.prefix
        self.skill_file = self.data_dir / "skill.json"
        self.record_file = self.data_dir / "fight_data.json"
        self.rule_store = RuleStore(self.skill_file)
        self.skills = self.rule_store.current.skills
        self.collections = json.loads(
            (self.data_dir / "collection.json").read_text(encoding="utf-8-sig")
        )["collection"]
        if "0" not in self.skills or len(self.skills) < 5:
            raise ValueError("决斗技能表必须包含防御技能 0 和至少四个其他技能")
        self.skill_ids = sorted(int(k) for k in self.skills if int(k) != 0)
        self.records = (json.loads(self.record_file.read_text(encoding="utf-8-sig"))
                        if self.record_file.exists() else {})
        self._transport = send
        self.render = render
        self.scheduler = scheduler
        self.dbcontrol = dbcontrol
        self.getcollection = getcollection
        self.bot_name = bot_name
        self.clock = clock
        self.rng = rng or random.Random()
        self.games = {}
        self.locks = {}
        self.undelivered = {}
        self.display_file = self.data_dir / "display_modes.json"
        self.display_modes = {}
        if self.display_file.exists():
            try:
                modes = json.loads(self.display_file.read_text(encoding="utf-8-sig"))
                if not isinstance(modes, dict) or any(not isinstance(k, str) or v not in ("text", "image") for k,v in modes.items()):
                    raise ValueError("显示设置格式错误")
                self.display_modes = modes
            except Exception:
                log.exception("读取决斗显示设置失败，使用默认显示")
        self._reported_rule_error = ""

    def reload_rules(self):
        valid = self.rule_store.reload()
        self.skills = self.rule_store.current.skills
        self.skill_ids = self.rule_store.current.skill_ids
        if not valid and self.rule_store.error != self._reported_rule_error:
            log.error("决斗配置校验失败，保留上一有效版本：%s", self.rule_store.error)
        self._reported_rule_error = self.rule_store.error
        return valid

    def _rules(self, game):
        return game.rules or self.rule_store.current

    def rich(self, game):
        # Integrated panels keep the action narration in both image and text mode.
        return self.render is not None

    def prefix_for(self,bot,event):
        return self.group_options(bot,event)['prefix']

    def format_commands(self,text,bot=None,event=None):
        prefix=self.prefix_for(bot,event) if bot is not None and event is not None else self.command_prefix
        formatted = format_commands(str(text), prefix)
        return PlainText(formatted) if isinstance(text, PlainText) else formatted

    def group_options(self,bot,event):
        return self.group_settings.for_group(self.key(bot,event))

    def group_status(self,bot,event):
        options=self.group_options(bot,event)
        status=(f"本群决斗：{'开启' if options['enabled'] else '关闭'}\n"
                f"藏品联动：{'开启' if options['collections'] else '关闭'}\n"
                f"本群前缀：{options['prefix']}\n"
                f"发起决斗需要前缀：{'是' if options['invite_prefix'] else '否'}\n"
                f"接受拒绝需要前缀：{'是' if options['reply_prefix'] else '否'}\n"
                "藏品联动只控制藏品和藏品称号，战绩及好感规则保留。")
        if self.group_settings.error:status+='\n群设置读取异常，请管理员检查配置。'
        return status

    async def set_group_option(self,bot,event,option,value,authorized=False):
        if authorized is not True:
            return await self.reply(bot,event,PlainText('仅机器人超管、群主或群管理员可修改本群决斗开关及藏品联动。'))
        key=self.key(bot,event)
        async with self._lock(key):
            try:self.group_settings.set(key,option,value)
            except Exception:
                log.exception('保存决斗群设置失败，保持原开关')
                return await self.reply(bot,event,PlainText('没保存上，决斗设置没改。'))
            cancelled=False
            if option=='enabled' and not value:
                cancelled=self._drop(key) is not None
                self.undelivered.pop(key,None)
            title={'enabled':'决斗','collections':'藏品联动','invite_prefix':'邀请前缀要求','reply_prefix':'应答前缀要求','prefix':'前缀'}[option]
            if option=='prefix':message=f'决斗前缀改成 {value} 了。'
            else:message=f"本群{title}已{'开启' if value else '关闭'}。"
            if cancelled:message+='这场也取消了，不计输赢。'

            await self.reply(bot,event,PlainText(message))
            if option=='prefix':
                game=self.games.get(key)
                if game and game.phase=='active':
                    game.bot,game.event=bot,event
                    await self._show_prompt(key,game,reset_deadline=False)

    def display_mode(self, bot, event, game=None):
        key = "{}:{}".format(*self.key(bot, event))
        return self.display_modes.get(key, (self._rules(game) if game else self.rule_store.current).ui["mode"])

    async def set_display_mode(self, bot, event, mode):
        if mode not in ("text", "image"):
            raise ValueError("未知显示模式")
        key = self.key(bot, event)
        resume = False
        async with self._lock(key):
            updated = dict(self.display_modes)
            updated["{}:{}".format(*key)] = mode
            temporary = None
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.data_dir,
                        prefix="display-", suffix=".tmp", delete=False) as file:
                    temporary = file.name
                    json.dump(updated, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self.display_file)
            except Exception:
                log.exception("保存决斗显示模式失败")
                return await self.reply(bot, event, PlainText("没保存上，显示方式没改。"))
            finally:
                if temporary and os.path.exists(temporary): os.unlink(temporary)
            self.display_modes = updated
            game = self.games.get(key)
            if game:
                game.prefer_text = mode == "text"
                game.bot, game.event = bot, event
            name = "文字" if mode == "text" else "图片"
            await self.reply(bot, event, PlainText(f"决斗换成{name}了。"))
            if game and game.phase == "active":
                await self._show_prompt(key, game, reset_deadline=False)
            elif game and game.phase == "paused":
                resume = int(event.user_id) in (game.data[1], game.data[2])
                if not resume:
                    await self.reply(bot, event, PlainText("参赛者发 #继续 就能接着打。"))
            elif not game and key in self.undelivered:
                resume = True
        # Resume uses the same lock; never acquire it recursively.
        if resume: await self.resume(bot, event)

    def add_log(self, game, text):
        log_lines = game.data.setdefault("_combat_log", [])
        log_lines.append(text)
        del log_lines[:-3]

    async def help(self, bot, event):
        try:
            from testbot.plugins.help_center import send_help
            await send_help(bot,event,'决斗',manager=self)
            return True
        except ImportError:
            pass
        if __package__:
            from .mechanics import help_text
        else:
            from mechanics import help_text
        game = self.games.get(self.key(bot, event))
        if not game: self.reload_rules()
        return await self.reply(bot, event, help_text(self._rules(game) if game else self.rule_store.current)
            +'\n【本群设置】\n'+self.group_status(bot,event))

    def rule_status(self):
        valid = self.reload_rules()
        return (f"当前规则：{self.rule_store.current.version}，{len(self.skills)}个技能\n"
                "新对局自动读取有效修改；进行中的对局保留原版本。"
                + ("\n配置校验失败，仍用上一有效版本：" + self.rule_store.error if not valid else ""))

    async def cancel_for_admin(self, bot, event):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self._drop(key)
            self.undelivered.pop(key, None)
            await self.reply(bot, event, "管理员已取消本群决斗，不计胜负及奖励。" if game else "本群没有进行中的决斗。")

    async def send(self, bot, event, text, remember=True):
        """A failed gateway must not retain a processing flag or a waiting job."""
        key = self.key(bot, event)
        if isinstance(text,str):text=self.format_commands(text,bot,event)
        try:
            delivered = await asyncio.wait_for(
                self._transport(bot, event, text), timeout=self.send_timeout)
            if delivered is False:
                raise RuntimeError("协议端报告发送失败")
            if remember:
                self.undelivered.pop(key, None)
            return True
        except Exception:
            log.exception("决斗发送失败，停止本局计时，可用 %s继续 恢复", self.prefix_for(bot,event))
            if remember:
                self.undelivered[key] = text
            game = self.games.get(key)
            if game and game.phase == "active":
                game.phase = "paused"
                game.prefer_text = True
                game.revision += 1
                self._cancel_timer(key)
            return False

    async def reply(self, bot, event, text):
        """Informational replies must not erase a failed result awaiting retry."""
        return await self.send(bot, event, text, remember=False)

    async def _announce(self, game, text):
        game.pending_result = text
        if await self.send(game.bot, game.event, text):
            game.pending_result = ""

    def key(self, bot, event):
        return str(bot.self_id), int(event.group_id)

    def _lock(self, key):
        return self.locks.setdefault(key, asyncio.Lock())

    @staticmethod
    def _name(event):
        return event.sender.card or event.sender.nickname

    def _user(self, event, user_id=None, name=None):
        uid = str(event.user_id if user_id is None else user_id)
        group = self.records.setdefault(str(event.group_id), {})
        user = group.setdefault(uid, {"user_id": uid,
            "group_id": str(event.group_id), "nickname": name or self._name(event),
            "win_count": 0, "lose_count": 0, "is_sign": None})
        if name is not None:
            user["nickname"] = name
        elif user_id is None:
            user["nickname"] = self._name(event)
        return user

    def _job_id(self, key):
        return "duel:{}:{}".format(*key)

    def _cancel_timer(self, key):
        if self.scheduler is not None and self.scheduler.get_job(self._job_id(key)):
            self.scheduler.remove_job(self._job_id(key))

    def _arm_timer(self, key, game, seconds):
        if self.scheduler is not None:
            self.scheduler.add_job(self.expire, "date",
                run_date=datetime.now(timezone.utc) + timedelta(seconds=seconds),
                id=self._job_id(key), args=[key, game.token, game.revision],
                replace_existing=True, max_instances=1, misfire_grace_time=60)

    def _drop(self, key):
        self._cancel_timer(key)
        return self.games.pop(key, None)

    async def invite(self, bot, event, target=0):
        key = self.key(bot, event)
        async with self._lock(key):
            if not self.group_options(bot,event)['enabled']:
                return await self.reply(bot,event,PlainText('本群决斗已关闭，请超管、群主或群管理员使用 #开启决斗。'))
            old = self.games.get(key)
            if old and old.phase == "invited" and self.clock() - old.data["time"] >= self.invitation_timeout:
                self._drop(key)
                old = None
            if old:
                return await self.reply(bot, event, "本群已有决斗，请先完成或取消当前邀请。")
            target = int(target)
            if target in (int(event.user_id), int(bot.self_id)):
                return await self.reply(bot, event, "请邀请其他群友，不能与自己或裁判机器人决斗。")
            self._user(event)
            self.undelivered.pop(key, None)
            data = {1: int(event.user_id), 2: 0, "player1": self._name(event),
                    "player2": "", "at": target, "next": int(event.user_id),
                    "index": 0, "time": self.clock(), "skill_choose": {}}
            for slot, hp in [(1, 600), (2, 700)]:
                data.update({f"blood{slot}": hp, f"attribute{slot}": 0,
                             f"atk{slot}": 6, f"accuracy{slot}": 0.95,
                             f"state{slot}": 0})
            self.reload_rules()
            game = Duel(bot, event, data, rules=self.rule_store.current)
            self.games[key] = game
            try:
                self._arm_timer(key, game, self.invitation_timeout)
                whom = f"[CQ:at,qq={target}]" if target else "群友"
                prefix=self.prefix_for(bot,event)
                require_prefix=self.group_options(bot,event)['reply_prefix']
                accept_word=prefix+'接受' if require_prefix else '接受'
                refuse_word=prefix+'拒绝' if require_prefix else '拒绝'
                delivered = await self.send(bot, event, f"{data['player1']} 向{whom}发起决斗！\n"
                    f"请在30秒内回复 {accept_word} 或 {refuse_word}；发起者也可回复 {refuse_word} 取消邀请。")
                if not delivered:
                    self._drop(key)
                    self.undelivered[key] = "上次决斗邀请未成功发送，已取消，请重新发起决斗。"
            except Exception:
                self._drop(key)
                raise

    async def accept(self, bot, event):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self.games.get(key)
            if game is None:
                return
            d = game.data
            if game.phase != "invited":
                return await self.reply(bot, event, "这场决斗已经开始了。")
            if self.clock() - d["time"] >= self.invitation_timeout:
                self._drop(key)
                return await self.reply(bot, event, "邀请已过期，请重新发起决斗。")
            if int(event.user_id) == d[1]:
                return await self.reply(bot, event, "不能接受自己发起的决斗。")
            if d["at"] and int(event.user_id) != d["at"]:
                return await self.reply(bot, event, f"这场决斗仅邀请了[CQ:at,qq={d['at']}]。")
            self._user(event)
            d[2], d["player2"] = int(event.user_id), self._name(event)
            game.bot, game.event = bot, event
            game.first = self.rng.choice([1, 2])
            settings = self._rules(game).battle
            d[f"blood{game.first}"] = settings["first_hp"]
            d[f"blood{3-game.first}"] = settings["second_hp"]
            for slot in (1, 2):
                d[f"max_blood{slot}"] = d[f"blood{slot}"]
            d["next"] = d[game.first]
            game.phase = "active"
            game.revision += 1
            d["time"] = self.clock()
            self._arm_timer(key, game, self.automatic_timeout)
            opening = (f"{d['player2']}接受了决斗！\n"
                f"[CQ:at,qq={d['next']}]取得先手。使用 #0～#4，#认输可立即认输。\n"
                "对手30秒未行动可 #结算，90秒未行动自动判负。")
            await self._announce(game, opening)
            await self._prepare_turn(key, game)

    async def refuse(self, bot, event):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self.games.get(key)
            if game is None:
                return
            if game.phase != "invited":
                return await self.reply(bot, event, "比赛已经开始，参赛者可使用 #认输。")
            d = game.data
            uid = int(event.user_id)
            if uid != d[1] and (not d["at"] or uid != d["at"]):
                return await self.reply(bot, event, "只有邀请者或指定对手可以取消这次邀请。")
            self._drop(key)
            await self.send(bot, event, "本次决斗邀请已取消。")

    async def shot(self, bot, event, count=None):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self.games.get(key)
            if game and game.phase == "paused":
                return await self.reply(bot, event, "发送故障后本局已暂停，参赛者请使用 #继续。")
            if not game or game.phase != "active":
                return await self.reply(bot, event, "当前没有已经开始的决斗。")
            d = game.data
            if int(event.user_id) != d["next"]:
                return await self.reply(bot, event, f"现在轮到[CQ:at,qq={d['next']}]行动。")
            game.bot, game.event = bot, event
            mid = getattr(event, "message_id", None)
            if mid is not None and mid in game.seen:
                return
            if count is not None and (type(count) is not int or not 0 <= count <= 4):
                return await self.reply(bot, event, "技能序号必须是0～4的整数。")
            if self.clock() - d["time"] >= self.automatic_timeout:
                return await self._finish(key, game, 3-self._actor(game), "行动超时")
            if mid is not None:
                game.seen.add(mid)
            choice = self.rng.randrange(5) if count is None else count
            await self._apply_skill(game, d["skill_choose"][choice])
            await self._prepare_turn(key, game)

    def _actor(self, game):
        return 1 if game.data["next"] == game.data[1] else 2

    async def _apply_skill(self, game, skill):
        d = game.data
        actor, defender = self._actor(game), 3-self._actor(game)
        rules = self._rules(game)
        spec = rules.skills[str(skill)]
        rng_state = self.rng.getstate()
        try:
            updated, variables, result = SkillEngine(self.calculator, self.rng, self.skill_file).execute(
                rules, d, game.rule_vars, actor, skill)
        except Exception:
            self.rng.setstate(rng_state)
            log.exception("决斗技能规则执行失败，本次状态变更已撤销")
            await self._announce(game, "技能规则执行失败，本次未扣血、未消耗行动，请改选技能并联系管理员检查配置。")
            return False
        # Commit the entire action before sending: resuming never executes twice.
        d.clear()
        d.update(updated)
        game.rule_vars = variables
        d["index"] += 1
        d["next"] = d[defender]
        d["time"] = self.clock()
        game.revision += 1
        # A failed send must not leave the next player's old deadline in place.
        self._cancel_timer(self.key(game.bot, game.event))
        narration = f"{d[f'player{actor}']}使用了{spec['name']}！\n{result}"
        self.add_log(game, narration)
        if not self.rich(game): await self._announce(game, narration)
        return True

    async def _prepare_turn(self, key, game):
        d = game.data
        if game.phase == "active":
            self._cancel_timer(key)
        while self.games.get(key) is game and game.phase == "active":
            maximum = self._rules(game).battle["max_actions"]
            if d["blood1"] <= 0 or d["blood2"] <= 0 or d["index"] >= maximum:
                if d["blood1"] <= 0 or d["blood2"] <= 0:
                    winner = 0 if d["blood1"] <= 0 and d["blood2"] <= 0 else 1 if d["blood2"] <= 0 else 2
                else:
                    left, right = d['blood1'], d['blood2']
                    if self._rules(game).battle['cap_compare'] == 'ratio':
                        left *= d['max_blood2']
                        right *= d['max_blood1']
                    elif self._rules(game).battle['cap_compare'] == 'loss':
                        left -= d['max_blood1']
                        right -= d['max_blood2']
                    winner = 0 if left == right else 1 if left > right else 2
                return await self._finish(key, game, winner, f"生命值耗尽或达到{maximum}次行动上限")
            actor, defender = self._actor(game), 3-self._actor(game)
            if d[f"state{actor}"] == 1:
                d[f"state{actor}"] = 0
                d["index"] += 1
                if d[f"state{defender}"] == 3:
                    constants = self._rules(game).constants
                    bleed = constants["bleed_damage"]
                    d[f"blood{defender}"] -= int(self.rng.normalvariate(bleed, bleed*constants["damage_variance"]))
                d["next"] = d[defender]
                game.revision += 1
                d["time"] = self.clock()
                narration = f"{d[f'player{actor}']}疲惫，跳过本回合。"
                self.add_log(game, narration)
                if not self.rich(game): await self._announce(game, narration)
                continue
            if d[f"state{actor}"] == 9:
                d[f"state{actor}"] = 0
                if not await self._apply_skill(game, self._rules(game).draw(self.rng, 1, include_defense=True)[0]):
                    return
                continue
            if game.choices_turn != d["index"]:
                d["skill_choose"] = dict(enumerate([0]+self._rules(game).draw(self.rng)))
                game.choices_turn = d["index"]
            await self._show_prompt(key, game)
            return

    async def _show_prompt(self, key, game, reset_deadline=True):
        """Resending a panel never redraws skills or runs the calculator."""
        d = game.data
        prefix=self.prefix_for(game.bot,game.event)
        d['_command_prefix']=prefix
        rules = self._rules(game)
        try:
            SkillEngine.update_display(rules, d, game.rule_vars)
        except Exception:
            log.exception("属性特性计算失败，本局暂停，保留现有状态")
            game.phase, game.prefer_text = "paused", True
            game.revision += 1
            self._cancel_timer(key)
            return await self.reply(game.bot, game.event, "属性配置计算失败，本局已暂停。请管理员修正配置并用“取消决斗”结束本局，再重新发起。")
        choices = [f"{prefix}{i} {rules.skills[str(s)]['name']}：{rules.skills[str(s)]['effect']}"
                   for i, s in d["skill_choose"].items()]
        text = (f"第{d['index']//2+1}回合 · 第{d['index']+1}次行动\n" + "\n".join(
            f"{d[f'player{i}']}：生命{d[f'blood{i}']}，"
            + "，".join(player_status_lines(d, i)[1:])
            for i in (1, 2)) + f"\n[CQ:at,qq={d['next']}]请选择：\n" + "\n".join(choices))
        if self.rich(game) and d.get("_combat_log"):
            text = "\n".join(d["_combat_log"][-2:]) + "\n" + text
        payload = text
        if self.rich(game) and self.display_mode(game.bot, game.event, game) == "image" and not game.prefer_text:
            try:
                # Rendering returns a payload; all network sends share send().
                payload = await asyncio.wait_for(
                    self.render(game.bot, game.event, game, choices), self.send_timeout)
                if payload is None or payload is False:
                    raise ValueError("图片生成器没有返回消息")
            except Exception:
                game.prefer_text = True
                log.exception("决斗图片生成失败，回退到文字")
                payload = text
        delivered = await self.send(game.bot, game.event, payload)
        if delivered and reset_deadline:
            d["time"] = self.clock()
            game.revision += 1
            self._arm_timer(key, game, self.automatic_timeout)
        return delivered

    async def settle(self, bot, event, surrender=False):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self.games.get(key)
            if not game or game.phase not in ("active", "paused"):
                return await self.reply(bot, event, "比赛尚未开始，无法结算。")
            d = game.data
            if int(event.user_id) not in (d[1], d[2]):
                return await self.reply(bot, event, "只有参赛者可以认输或申请结算。")
            actor = 1 if int(event.user_id) == d[1] else 2
            game.bot, game.event = bot, event
            if surrender:
                game.phase = "active"
                return await self._finish(key, game, 3-actor, "主动认输")
            if game.phase == "paused":
                return await self.reply(bot, event, "本局因发送故障暂停，不按超时判负；请使用 #继续。")
            if int(event.user_id) == d["next"]:
                return await self.reply(bot, event, "当前轮到你行动，不能申请对手超时；可使用 #认输。")
            elapsed = self.clock() - d["time"]
            if elapsed < self.claim_timeout:
                return await self.reply(bot, event,
                    f"对手尚未超时，还需等待{int(self.claim_timeout-elapsed)+1}秒。")
            await self._finish(key, game, actor, "对手30秒未行动，申请结算")

    async def resume(self, bot, event):
        key = self.key(bot, event)
        async with self._lock(key):
            game = self.games.get(key)
            if game is None:
                pending = self.undelivered.get(key)
                if pending:
                    return await self.send(bot, event, pending)
                return await self.reply(bot, event, "当前没有需要恢复的决斗。")
            if int(event.user_id) not in (game.data[1], game.data[2]):
                return await self.reply(bot, event, "只有参赛者可以恢复决斗。")
            # Reconnection may create a new Bot object for the same account.
            game.bot, game.event = bot, event
            if game.phase == "active":
                return await self._show_prompt(key, game, reset_deadline=False)
            if game.phase != "paused":
                return await self.reply(bot, event, "决斗正在结算，请稍候。")
            game.phase = "active"
            game.data["time"] = self.clock()
            game.revision += 1
            if game.pending_result:
                await self._announce(game, game.pending_result)
                if game.phase == "paused":
                    return
            await self._prepare_turn(key, game)

    async def expire(self, key, token, revision):
        key = tuple(key)
        async with self._lock(key):
            game = self.games.get(key)
            if not game or game.token != token or game.revision != revision:
                return
            limit = self.invitation_timeout if game.phase == "invited" else self.automatic_timeout
            remaining = limit - (self.clock()-game.data["time"])
            if remaining > 0:
                return self._arm_timer(key, game, remaining)
            if game.phase == "invited":
                self._drop(key)
                await self.send(game.bot, game.event, "30秒内无人接受，本次决斗邀请已过期。")
            elif game.phase == "active":
                await self._finish(key, game, 3-self._actor(game), "90秒未行动，自动判负")

    def _save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.data_dir,
                                             prefix="fight_data-", suffix=".tmp", delete=False) as f:
                temp = f.name
                json.dump(self.records, f, ensure_ascii=False, indent=4, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.record_file)
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)

    async def _finish(self, key, game, winner, reason):
        if self.games.get(key) is not game or game.phase != "active":
            return
        d = game.data
        game.phase = "settling"
        before = copy.deepcopy(self.records)
        try:
            if winner:
                group = self.records[str(game.event.group_id)]
                group[str(d[winner])]["win_count"] += 1
                group[str(d[3-winner])]["lose_count"] += 1
                self._save()
        except Exception:
            self.records = before
            game.phase = "active"
            self._arm_timer(key, game, 5)
            raise
        # Close before any network/database await: retries cannot award twice.
        game.phase = "finished"
        self._drop(key)
        health = (f"\n剩余生命：{d['player1']} {max(0,d['blood1']):g} / "
                  f"{d['player2']} {max(0,d['blood2']):g}")
        if (self._rules(game).battle['cap_compare'] == 'loss' and
                d['index'] >= self._rules(game).battle['max_actions'] and min(d['blood1'],d['blood2']) > 0):
            health += (f"\n上限比较净损血：{d['player1']} {d['max_blood1']-d['blood1']:g} / "
                       f"{d['player2']} {d['max_blood2']-d['blood2']:g}（较少者胜，相同为平局）")
        if not winner:
            return await self.send(game.bot, game.event, f"决斗结束：平局（{reason}），不计胜负及奖励。"+health)
        group = self.records[str(game.event.group_id)]
        won, lost = group[str(d[winner])], group[str(d[3-winner])]
        reward_messages = []
        try:
            reward_messages = await self._rewards(game, winner, won, lost)
        except Exception:
            log.exception("决斗战绩已保存，但奖励处理失败；不自动重复发奖")
            reward_messages.append("奖励处理失败，请管理员检查日志；战绩已保存。")
        await self.send(game.bot, game.event,
            f"结算：{reason}\n胜者：{d[f'player{winner}']}，累计胜场：{won['win_count']}\n"
            f"败者：{d[f'player{3-winner}']}，累计败场：{lost['lose_count']}"
            + health
            + ("\n【最后战况】\n"+"\n".join(d.get("_combat_log", [])[-2:]) if self.rich(game) else "")
            + ("\n"+"\n".join(reward_messages) if reward_messages else ""))

    async def _rewards(self, game, winner, won, lost):
        d = game.data
        winner_id, loser_id = int(d[winner]), int(d[3-winner])
        messages = []
        if self.dbcontrol is not None:
            rw = await self.dbcontrol(f"SELECT user_like FROM user_sign WHERE user_id={winner_id}")
            rl = await self.dbcontrol(f"SELECT user_like FROM user_sign WHERE user_id={loser_id}")
            if rl[-1] and rl[0][0][0] > 5:
                if rw[-1]:
                    await self.dbcontrol(f"UPDATE user_sign SET user_like=user_like+5 WHERE user_id={winner_id}")
                    messages.append(f"{self.bot_name}对胜者的好感增加了5。")
                penalty = self.rng.randint(3, 5)
                await self.dbcontrol(f"UPDATE user_sign SET user_like=user_like-{penalty} WHERE user_id={loser_id}")
        collections_enabled=self.group_options(game.bot,game.event)['collections']
        if not collections_enabled:messages.append('本群藏品联动已关闭，本局不发藏品及藏品称号。')
        if self.getcollection is not None and collections_enabled:
            awards = []
            if self.collections and self.rng.randint(1, 3) == 1:
                awards.append((winner_id, self.rng.choice(self.collections), True))
            for total, uid, thresholds in [
                (won["win_count"], winner_id, [(20, "金牌训练家"), (100, "决斗的王")]),
                (lost["lose_count"], loser_id, [(20, "慈善家"), (100, "决斗的神")])]:
                awards.extend((uid, name, False) for threshold, name in thresholds if total >= threshold)
            for uid, name, repeat in awards:
                message = await self.getcollection(uid, name, if_can_reget=repeat)
                if isinstance(message, str) and message:
                    messages.append(f"[CQ:at,qq={uid}]{message}")
        return messages

    def get_user_data(self, event):
        return self._user(event)

    async def rank(self, command, group_id):
        key = "lose_count" if command in ("败场排行", "失败排行") else "win_count"
        users = sorted(self.records.get(str(group_id), {}).values(),
                       key=lambda u: (-u[key], str(u["user_id"])))[:10]
        title = "败场排行" if key == "lose_count" else "胜场排行"
        return title+"\n"+("\n".join(f"{u['nickname']}：{u[key]}" for u in users) or "暂无战绩")

    def shutdown(self):
        for key in list(self.games):
            self._drop(key)
