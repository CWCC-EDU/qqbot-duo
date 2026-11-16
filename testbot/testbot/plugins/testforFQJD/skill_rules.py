"""Validated JSON rules, per-duel snapshots and a bounded effect interpreter.

No Python expressions or external side effects are exposed to rule files.
Legacy skills and new step-based skills share one versioned JSON document.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re

ATTRIBUTES = ("普通", "水", "火", "草", "暗", "光", "？")
ATTRIBUTE_ALIASES = dict(zip(("normal", "water", "fire", "grass", "dark", "light", "unknown"), range(7)))
ATTRIBUTE_ALIASES.update({name: i for i, name in enumerate(ATTRIBUTES)})
FIELDS = {"hp": "blood", "attack": "atk", "accuracy": "accuracy", "state": "state", "attribute": "attribute"}
MODIFIERS = {"attack", "accuracy", "damage_multiplier", "damage_taken_multiplier"}
LEGACY_FUNCTIONS = {"skill_acc_change", "skill_acc_damage", "skill_addition", "skill_change", "skill_change_atk", "skill_if_positive", "skill_rand_state", "skill_random_damage", "skill_treatment"}
EXPR_OPS = {"add", "sub", "mul", "div", "min", "max", "clamp", "floor", "ceil", "abs", "eq", "ne", "gt", "gte", "lt", "lte", "and", "or", "not", "var"}
OPS = {"legacy", "damage", "heal", "stat_add", "stat_set", "set_attribute", "set_state", "set_var", "if", "repeat", "chance", "choose", "message"}
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
CONSTANTS = {
    "attack_per_stage": (1.22, 1, 2, "atk_corfficient"),
    "attribute_multiplier": (1.2, 1, 3, "restraint_coefficient"),
    "damage_variance": (.08, 0, .5, "ran_corfficient"),
    "defense_multiplier": (.3, 0, 1, "def_corfficient"),
    "vulnerability_multiplier": (1.4, 1, 5, "fra_corfficient"),
    "confusion_probability": (.45, 0, 1, "con_corfficient"),
    "bleed_damage": (95, 0, 1000, "bleed_damage"),
    "thorns_ratio": (.3, 0, 1, "thorns_ratio"),
}


class RuleError(ValueError):
    pass


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e12:
        raise RuleError("需要有限数值，绝对值不能超过1e12")
    return value


def attribute_id(value):
    if isinstance(value, str) and value in ATTRIBUTE_ALIASES:
        return ATTRIBUTE_ALIASES[value]
    if type(value) is int and 0 <= value <= 6:
        return value
    raise RuleError("属性必须为普通/水/火/草/暗/光/？或0～6")


def validate_modifier(stat, amount):
    number(amount)
    if stat == "attack" and (type(amount) is not int or not -12 <= amount <= 12):
        raise RuleError("被动attack需要-12～12的整数")
    if stat == "accuracy" and not -2 <= amount <= 2:
        raise RuleError("被动accuracy必须在-2～2之间")
    if stat.endswith("multiplier") and not 0 <= amount <= 10:
        raise RuleError("被动倍率必须在0～10之间")


def validate_legacy(function, parameters):
    allowed = {"skill_acc_change": {"if_to_myself", "change_num"}, "skill_acc_damage": set(),
               "skill_addition": {"if_to_myself", "damage", "ratio"}, "skill_change": {"0"},
               "skill_change_atk": {"if_to_myself", "change_num"},
               "skill_if_positive": {"if_judge_myself", "if_is_positive", "if_to_myself", "effect"},
               "skill_rand_state": {"if_to_myself", "rand_choice"}, "skill_random_damage": {"up", "down"},
               "skill_treatment": {"if_to_myself", "damage", "ratio"}}[function]
    if set(parameters) - allowed:
        raise RuleError("旧技能参数包含未知字段：" + function)
    for key, value in parameters.items():
        if key in ("if_to_myself", "if_judge_myself", "if_is_positive"):
            if type(value) is not int or value not in (0, 1): raise RuleError(key + "必须为0或1")
        elif key == "rand_choice":
            if not isinstance(value, dict) or not value or any(not re.fullmatch(r"[0-9]|10", k) or type(w) is not int or not 0 < w <= 1000000 for k, w in value.items()):
                raise RuleError("状态权重需要0～10的状态编号及正整数权重")
        elif key == "effect":
            if value not in ("add", "atk", "clean", "turn"): raise RuleError("未知条件技能效果")
        else:
            number(value)
            if key in ("up", "down") and (type(value) is not int or not 0 <= value <= 1000): raise RuleError("次数范围必须为0～1000整数")
            if key == "change_num" and function == "skill_change_atk" and (type(value) is not int or not -12 <= value <= 12): raise RuleError("攻击变化需要-12～12整数")
            if key == "change_num" and function == "skill_acc_change" and not -2 <= value <= 2: raise RuleError("命中变化超出范围")
            if key == "ratio" and not 0 <= value <= (1 if function == "skill_treatment" else 100): raise RuleError("概率或吸血比例超出范围")
            if key == "damage" and value < 0: raise RuleError("伤害/治疗数值不能为负")
    if function == "skill_random_damage" and parameters.get("down", 0) > parameters.get("up", 0):
        raise RuleError("多段次数下限不能大于上限")


def validate_expr(value, depth=0, aura=False):
    if depth > 16:
        raise RuleError("表达式嵌套过深")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 400:
            raise RuleError("字符串过长")
        return
    if isinstance(value, (int, float)):
        number(value)
        return
    if not isinstance(value, dict) or len(value) != 1:
        raise RuleError("表达式必须是值或单个运算符对象")
    op, args = next(iter(value.items()))
    if op not in EXPR_OPS:
        raise RuleError("未知表达式运算符：" + str(op))
    if op == "var":
        if not isinstance(args, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]{0,79}", args):
            raise RuleError("变量路径格式错误")
        parts = args.split(".")
        if parts[0] in ("self", "enemy"):
            if len(parts) == 3 and parts[1] == "vars" and IDENTIFIER.fullmatch(parts[2]):
                return
            if len(parts) != 2 or parts[1] not in set(FIELDS) | {"max_hp", "attack_effective", "accuracy_effective"}:
                raise RuleError("未知角色字段：" + args)
            if aura and parts[1] in ("attack_effective", "accuracy_effective"):
                raise RuleError("被动条件需读取基础属性，不能递归读取有效属性")
        elif args == "turn":
            pass
        elif args in ("skill.attribute", "skill.id") and not aura:
            pass
        elif len(parts) == 2 and IDENTIFIER.fullmatch(parts[0]) and parts[1] in ("hp_damage", "raw_damage", "hit", "healed") and not aura:
            pass
        else:
            raise RuleError("未知变量路径：" + args)
        return
    if not isinstance(args, list) or not 1 <= len(args) <= 16:
        raise RuleError("运算符参数必须是非空数组")
    expected = {"sub": 2, "div": 2, "eq": 2, "ne": 2, "gt": 2, "gte": 2, "lt": 2, "lte": 2, "not": 1, "clamp": 3, "floor": 1, "ceil": 1, "abs": 1}
    if op in expected and len(args) != expected[op]:
        raise RuleError("运算符参数个数错误：" + op)
    for arg in args:
        validate_expr(arg, depth+1, aura)


def validate_steps(steps, depth=0, allow_legacy=True):
    if depth > 8 or not isinstance(steps, list) or len(steps) > 64:
        raise RuleError("步骤必须是数组，且不能过多或嵌套过深")
    for step in steps:
        if not isinstance(step, dict) or step.get("op") not in OPS:
            raise RuleError("未知或缺失的技能操作")
        op = step["op"]
        required = {"legacy": set(), "damage": {"amount"}, "heal": {"amount"}, "stat_add": {"stat", "value"}, "stat_set": {"stat", "value"}, "set_attribute": {"value"}, "set_state": {"value"}, "set_var": {"name", "value"}, "if": {"condition", "then"}, "repeat": {"count", "steps"}, "chance": {"probability", "then"}, "choose": {"choices"}, "message": set()}[op]
        common = {"op", "when", "target", "save_as"}
        extras = {"legacy": set(), "damage": {"amount", "damage_type", "hit_check", "attribute"}, "heal": {"amount", "cap_to_max"}, "stat_add": {"stat", "value"}, "stat_set": {"stat", "value"}, "set_attribute": {"value"}, "set_state": {"value"}, "set_var": {"name", "value"}, "if": {"condition", "then", "else"}, "repeat": {"count", "steps"}, "chance": {"probability", "then", "else"}, "choose": {"choices"}, "message": {"text", "parts"}}[op]
        if not required <= set(step) or set(step) - common - extras:
            raise RuleError("操作缺少字段或包含未知字段：" + op)
        if step.get("target", "enemy" if op == "damage" else "self") not in ("self", "enemy"):
            raise RuleError("目标只能为self或enemy")
        if "save_as" in step and (not isinstance(step["save_as"], str) or not IDENTIFIER.fullmatch(step["save_as"]) or step["save_as"] in ("self", "enemy", "skill", "turn", "action")):
            raise RuleError("save_as变量名不合法")
        if "save_as" in step and op not in ("damage", "heal", "legacy"):
            raise RuleError("只有damage/heal/legacy能保存结果")
        if "when" in step:
            validate_expr(step["when"])
        if op == "legacy" and not allow_legacy:
            raise RuleError("触发器中不能再次执行整个旧技能")
        if op in ("stat_add", "stat_set") and step["stat"] not in ("hp", "attack", "accuracy"):
            raise RuleError("可修改属性为hp/attack/accuracy")
        if op == "set_var" and (not isinstance(step["name"], str) or not IDENTIFIER.fullmatch(step["name"])):
            raise RuleError("自定义变量名不合法")
        for field in ("amount", "value", "count", "probability", "condition"):
            if field in step:
                validate_expr(step[field])
        if op == "set_attribute" and not isinstance(step["value"], dict): attribute_id(step["value"])
        if op == "set_state" and not isinstance(step["value"], dict) and (type(step["value"]) is not int or not 0 <= step["value"] <= 10):
            raise RuleError("状态编号必须为0～10整数")
        if op in ("stat_add", "stat_set") and not isinstance(step["value"], dict):
            number(step["value"])
            if step["stat"] == "attack" and type(step["value"]) is not int: raise RuleError("攻击等级需要整数")
        if op == "damage":
            if step.get("damage_type", "normal") not in ("normal", "true"):
                raise RuleError("damage_type只能为normal或true")
            if "hit_check" in step and type(step["hit_check"]) is not bool:
                raise RuleError("hit_check必须为布尔值")
            if "attribute" in step:
                attribute_id(step["attribute"])
            if step.get("target", "enemy") == "self" and step.get("damage_type", "normal") != "true":
                raise RuleError("自伤请显式使用true伤害")
        if op == "heal" and "cap_to_max" in step and type(step["cap_to_max"]) is not bool:
            raise RuleError("cap_to_max必须为布尔值")
        if op == "repeat" and isinstance(step["count"], (int, float)) and (type(step["count"]) is not int or not 0 <= step["count"] <= 20):
            raise RuleError("重复次数必须为0～20的整数")
        if op == "chance" and isinstance(step["probability"], (int, float)) and not 0 <= step["probability"] <= 1:
            raise RuleError("概率必须在0～1之间")
        for branch in ("then", "else", "steps"):
            if branch in step:
                validate_steps(step[branch], depth+1, allow_legacy)
        if op == "choose":
            options = step["choices"]
            if not isinstance(options, list) or not 1 <= len(options) <= 20:
                raise RuleError("随机选项数量必须为1～20")
            total = 0
            for option in options:
                if not isinstance(option, dict) or set(option) != {"weight", "steps"} or number(option["weight"]) <= 0:
                    raise RuleError("随机选项需要正数weight和steps")
                total += option["weight"]
                validate_steps(option["steps"], depth+1, allow_legacy)
            number(total)
        if op == "message":
            if ("text" in step) == ("parts" in step): raise RuleError("消息需选择text或parts之一")
            if "text" in step and (not isinstance(step["text"], str) or len(step["text"]) > 300):
                raise RuleError("消息text必须是300字以内的文本")
            if "parts" in step:
                if not isinstance(step["parts"], list) or not 1 <= len(step["parts"]) <= 16: raise RuleError("消息parts需要1～16个片段")
                for part in step["parts"]: validate_expr(part)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuleError("JSON键重复：" + key)
        result[key] = value
    return result


@dataclass(frozen=True)
class RuleSet:
    version: str
    skills: dict
    passives: tuple
    triggers: tuple
    constants: dict
    battle: dict
    ui: dict

    @property
    def skill_ids(self):
        return sorted(int(key) for key in self.skills if key != "0")

    def draw(self, rng, count=4, include_defense=False):
        pool = [int(key) for key, skill in self.skills.items()
                if (key != "0" or include_defense) and skill.get("weight", 100) > 0]
        if len(pool) < count:
            raise RuleError("可抽取技能不足")
        # Exponential races implement weighted sampling without replacement.
        return sorted(pool, key=lambda key: -math.log(max(rng.random(), 1e-15)) /
                      self.skills[str(key)].get("weight", 100))[:count]


class RuleStore:
    max_file_bytes = 1024 * 1024

    def __init__(self, path):
        self.path = Path(path)
        self.current = None
        self.error = ""
        self.attempted_digest = ""
        self.reload()
        if self.current is None:
            raise RuleError("决斗配置无法加载：" + self.error)

    def reload(self):
        digest = None
        try:
            if self.path.stat().st_size > self.max_file_bytes:
                raise RuleError("配置文件超过1MB")
            raw = self.path.read_bytes()
            if len(raw) > self.max_file_bytes:
                raise RuleError("配置文件超过1MB")
            digest = hashlib.sha256(raw).hexdigest()
            if digest == self.attempted_digest:
                return not self.error
            self.attempted_digest = digest
            document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=no_duplicate_keys,
                                  parse_constant=lambda value: (_ for _ in ()).throw(RuleError("不允许NaN或Infinity")))
            if not isinstance(document, dict):
                raise RuleError("配置根节点必须是对象")
            if "skills" in document:
                if type(document.get("schema_version")) is not int or document["schema_version"] != 1 or set(document) - {"schema_version", "requires_engine", "description", "skills", "passives", "triggers", "constants", "battle", "ui"}:
                    raise RuleError("配置版本或顶层字段错误")
                if type(document.get("requires_engine", 1)) is not int or not 1 <= document.get("requires_engine", 1) <= 2:
                    raise RuleError("此配置需要更新的决斗规则引擎")
                skills = document["skills"]
                passives = document.get("passives", [])
                triggers = document.get("triggers", [])
                constants = document.get("constants", {})
                battle, ui = document.get("battle", {}), document.get("ui", {})
            else:
                skills, passives, triggers, constants, battle, ui = document, [], [], {}, {}, {}
            if not isinstance(battle, dict) or set(battle) - {"first_hp", "second_hp", "max_actions", "healing_cap", "cap_compare"}:
                raise RuleError("未知对局设置")
            battle = {"first_hp": 600, "second_hp": 700, "max_actions": 11, "healing_cap": False, "cap_compare": "absolute", **battle}
            if battle['cap_compare'] not in ('absolute', 'ratio', 'loss'): raise RuleError("行动上限比较方式错误")
            for key in ("first_hp", "second_hp", "max_actions"):
                if type(battle[key]) is not int or not (6 <= battle[key] <= 30 if key == "max_actions" else 300 <= battle[key] <= 2000):
                    raise RuleError("对局生命或行动上限不合法")
            if type(battle["healing_cap"]) is not bool: raise RuleError("healing_cap需要布尔值")
            if not isinstance(ui, dict) or set(ui) - {"mode"} or ui.get("mode", "text") not in ("image", "text"):
                raise RuleError("UI mode只能为image或text")
            ui = {"mode": "text", **ui}
            if not isinstance(constants, dict) or set(constants) - set(CONSTANTS):
                raise RuleError("未知底层常量字段")
            for key, value in constants.items():
                number(value)
                if not CONSTANTS[key][1] <= value <= CONSTANTS[key][2]:
                    raise RuleError("底层常量超出范围：" + key)
            constants = {key: constants.get(key, bounds[0]) for key, bounds in CONSTANTS.items()}
            if not isinstance(skills, dict) or "0" not in skills or not 5 <= len(skills) <= 1000:
                raise RuleError("技能表需要0号防御及至少4个其他技能，最多1000个")
            for key, skill in skills.items():
                if not re.fullmatch(r"0|[1-9][0-9]{0,5}", key) or not isinstance(skill, dict):
                    raise RuleError("技能编号必须是规范的非负整数")
                if set(skill) - {"name", "effect", "hurt", "attribute", "function", "parameter", "steps", "weight", "rarity"}:
                    raise RuleError("技能包含未知字段：" + key)
                weight = number(skill.get("weight", 100))
                if not 0 <= weight <= 1000: raise RuleError("技能权重必须为0～1000，0为停用")
                if skill.get("rarity", "common") not in ("common", "rare", "epic", "legendary"):
                    raise RuleError("未知技能稀有度")
                if not isinstance(skill.get("name"), str) or not 1 <= len(skill["name"]) <= 100 or not isinstance(skill.get("effect"), str) or len(skill["effect"]) > 500:
                    raise RuleError("技能需要name和effect文本")
                attribute_id(skill.get("attribute"))
                if "steps" in skill:
                    validate_steps(skill["steps"])
                needs_legacy = "steps" not in skill or self._contains_legacy(skill.get("steps", []))
                if needs_legacy:
                    number(skill.get("hurt"))
                    functions, parameters = skill.get("function"), skill.get("parameter")
                    if not isinstance(functions, list) or len(functions) > 16:
                        raise RuleError("旧技能function需要数组")
                    for function in functions:
                        if function == 0:
                            continue
                        if function not in LEGACY_FUNCTIONS or not isinstance(parameters, dict) or not isinstance(parameters.get(function), dict):
                            raise RuleError("旧技能函数或参数不合法：" + str(function))
                        validate_legacy(function, parameters[function])
                skill["attribute"] = attribute_id(skill["attribute"])
            if sum(1 for key, spec in skills.items() if key != "0" and spec.get("weight", 100) > 0) < 4:
                raise RuleError("至少四个非防御技能的权重必须大于0")
            if not isinstance(passives, list) or len(passives) > 32 or not isinstance(triggers, list) or len(triggers) > 32:
                raise RuleError("被动与触发器必须是数组，分别最多32个")
            identifiers = set()
            for passive in passives:
                if not isinstance(passive, dict) or set(passive) - {"id", "name", "when", "modifiers"} or not isinstance(passive.get("id"), str) or not IDENTIFIER.fullmatch(passive["id"]) or passive["id"] in identifiers:
                    raise RuleError("被动id、字段或唯一性错误")
                identifiers.add(passive["id"])
                if not isinstance(passive.get("name"), str) or not 1 <= len(passive["name"]) <= 40:
                    raise RuleError("被动需要40字以内名称")
                validate_expr(passive.get("when", True), aura=True)
                modifiers = passive.get("modifiers")
                if not isinstance(modifiers, dict) or not modifiers or set(modifiers) - MODIFIERS:
                    raise RuleError("未知被动加成字段")
                for stat, value in modifiers.items():
                    validate_expr(value, aura=True)
                    if not isinstance(value, dict): validate_modifier(stat, value)
            for trigger in triggers:
                if not isinstance(trigger, dict) or set(trigger) - {"id", "event", "when", "steps"} or not isinstance(trigger.get("id"), str) or not IDENTIFIER.fullmatch(trigger["id"]) or trigger["id"] in identifiers or trigger.get("event") not in ("before_skill", "after_skill"):
                    raise RuleError("触发器id、事件或字段错误")
                identifiers.add(trigger["id"])
                validate_expr(trigger.get("when", True))
                validate_steps(trigger.get("steps"), allow_legacy=False)
            candidate = RuleSet(digest[:12], skills, tuple(passives), tuple(triggers), constants, battle, ui)
            # Catch invalid conditional aura expressions before replacing a good
            # version. Runtime-dependent expressions are also checked atomically
            # at action commit, so a failed calculation never corrupts a duel.
            for own_attribute in range(7):
                for enemy_attribute in range(7):
                    probe = {"index": 0, "player1": "校验甲", "player2": "校验乙"}
                    for slot, attr in ((1, own_attribute), (2, enemy_attribute)):
                        probe.update({f"blood{slot}": 600, f"max_blood{slot}": 600,
                                      f"atk{slot}": 6, f"accuracy{slot}": .95,
                                      f"state{slot}": 0, f"attribute{slot}": attr})
                    SkillEngine.update_display(candidate, probe, {1: {}, 2: {}})
            self.current = candidate
            self.error = ""
            return True
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
            if digest is None:
                self.attempted_digest = ""
            self.error = str(error)[:400]
            return False

    @classmethod
    def _contains_legacy(cls, steps):
        for step in steps:
            if step["op"] == "legacy":
                return True
            if any(cls._contains_legacy(step.get(branch, [])) for branch in ("then", "else", "steps")):
                return True
            if any(cls._contains_legacy(option["steps"]) for option in step.get("choices", [])):
                return True
        return False


class Context:
    def __init__(self, rules, data, variables, actor, rng, calculator=None, skill=None, skill_file=None):
        self.rules, self.data, self.variables, self.actor = rules, data, variables, actor
        self.rng, self.calculator, self.skill, self.skill_file = rng, calculator, skill or {}, skill_file
        self.locals, self.messages = {"action": {"hit": False}}, []
        self.budget, self.legacy_calls, self.attribute_explicit = 256, 0, False

    def spend(self):
        self.budget -= 1
        if self.budget < 0:
            raise RuleError("本次行动超过256步执行预算")

    def expr(self, value):
        self.spend()
        if not isinstance(value, dict):
            return value
        op, args = next(iter(value.items()))
        if op == "var":
            if args == "turn":
                return self.data["index"] + 1
            parts = args.split(".")
            if parts[0] in ("self", "enemy"):
                slot = self.actor if parts[0] == "self" else 3-self.actor
                if parts[1] == "vars":
                    return self.variables.setdefault(slot, {}).get(parts[2], 0)
                if parts[1] == "max_hp":
                    return self.data.get(f"max_blood{slot}", 600 if slot == 1 else 700)
                if parts[1] == "attack_effective":
                    return max(0, min(12, self.data[f"atk{slot}"] + self.modifiers(slot)["attack"])) - 6
                if parts[1] == "accuracy_effective":
                    return self.data[f"accuracy{slot}"] + self.modifiers(slot)["accuracy"]
                result = self.data[FIELDS[parts[1]] + str(slot)]
                if parts[1] == "attribute":
                    return ATTRIBUTES[result]
                return result - 6 if parts[1] == "attack" else result
            if parts[0] == "skill":
                return ATTRIBUTES[self.skill["attribute"]] if parts[1] == "attribute" else self.skill["id"]
            if parts[0] not in self.locals or parts[1] not in self.locals[parts[0]]:
                raise RuleError("结果变量尚未定义：" + args)
            return self.locals[parts[0]][parts[1]]
        if op == "and":
            return all(self.expr(arg) for arg in args)
        if op == "or":
            return any(self.expr(arg) for arg in args)
        values = [self.expr(arg) for arg in args]
        if op in ("eq", "ne"):
            return values[0] == values[1] if op == "eq" else values[0] != values[1]
        if op == "not":
            return not values[0]
        values = [number(item) for item in values]
        if op == "add": result = sum(values)
        elif op == "sub": result = values[0]-values[1]
        elif op == "mul":
            result = 1
            for item in values:
                result = number(result*item)
        elif op == "div":
            if values[1] == 0: raise RuleError("表达式除数为0")
            result = values[0]/values[1]
        elif op == "min": result = min(values)
        elif op == "max": result = max(values)
        elif op == "floor": result = math.floor(values[0])
        elif op == "ceil": result = math.ceil(values[0])
        elif op == "abs": result = abs(values[0])
        elif op == "clamp":
            if values[1] > values[2]: raise RuleError("clamp下界不能大于上界")
            result = max(values[1], min(values[2], values[0]))
        elif op == "gt": return values[0] > values[1]
        elif op == "gte": return values[0] >= values[1]
        elif op == "lt": return values[0] < values[1]
        elif op == "lte": return values[0] <= values[1]
        else: raise RuleError("未知表达式")
        return number(result)

    def modifiers(self, slot):
        result = {"attack": 0, "accuracy": 0, "damage_multiplier": 1, "damage_taken_multiplier": 1, "names": []}
        context = Context(self.rules, self.data, self.variables, slot, self.rng)
        for passive in self.rules.passives:
            if context.expr(passive.get("when", True)):
                result["names"].append(passive["name"])
                for stat, value in passive["modifiers"].items():
                    amount = number(context.expr(value))
                    validate_modifier(stat, amount)
                    result[stat] = number(result[stat] * amount if stat.endswith("multiplier") else result[stat] + amount)
        return result

    def legacy(self, spec, force_hit=False):
        actor, defender, d = self.actor, 3-self.actor, self.data
        calc = self.calculator(*[d[f"{name}{slot}"] for name in ("blood", "attribute", "atk", "accuracy", "state") for slot in (actor, defender)],
            spec["hurt"], spec["attribute"], copy.deepcopy(spec["function"]), copy.deepcopy(spec["parameter"]),
            spec.get("id", self.skill.get("id", 0)), max(self.rules.skill_ids), self.skill_file)
        own, enemy = self.modifiers(actor), self.modifiers(defender)
        calc.fighter_atk_bonus, calc.fighter_accuracy_bonus = own["attack"], own["accuracy"]
        calc.damage_multiplier = own["damage_multiplier"] * enemy["damage_taken_multiplier"]
        calc.skill_definitions, calc.rng, calc.force_hit = self.rules.skills, self.rng, force_hit
        calc.healing_cap = self.rules.battle["healing_cap"]
        calc.fighter_max_hp = d.get(f"max_blood{actor}", self.rules.battle["first_hp"])
        for key, value in self.rules.constants.items():
            setattr(calc, CONSTANTS[key][3], value)
        before = d[f"blood{defender}"]
        message = calc.cac()
        self.locals["action"]["hit"] |= bool(getattr(calc, "attack_hit", False))
        for name in ("blood", "attribute", "atk", "accuracy", "state"):
            for slot, prefix in ((actor, "fighter_"), (defender, "fighted_")):
                value = number(getattr(calc, prefix + name))
                if name == "blood" and self.rules.battle["healing_cap"] and value > d[f"blood{slot}"]:
                    value = min(value, max(d[f"blood{slot}"], d.get(f"max_blood{slot}", 700)))
                d[f"{name}{slot}"] = value
        lost = max(0, before - d[f"blood{defender}"])
        self.messages.append(message)
        return {"hp_damage": min(max(0, before), lost), "raw_damage": lost, "hit": bool(getattr(calc, "ifacc", lost > 0))}

    def steps(self, steps):
        for step in steps:
            self.spend()
            if not self.expr(step.get("when", True)):
                continue
            op = step["op"]
            target = self.actor if step.get("target", "enemy" if op == "damage" else "self") == "self" else 3-self.actor
            result = None
            if op == "legacy":
                self.legacy_calls += 1
                if self.legacy_calls > 1:
                    raise RuleError("每次行动只能执行一次legacy技能")
                result = self.legacy(self.skill)
            elif op == "if":
                self.steps(step["then"] if self.expr(step["condition"]) else step.get("else", []))
            elif op == "chance":
                probability = number(self.expr(step["probability"]))
                if not 0 <= probability <= 1: raise RuleError("概率超出0～1")
                self.steps(step["then"] if self.rng.random() < probability else step.get("else", []))
            elif op == "repeat":
                count = self.expr(step["count"])
                if type(count) is not int or not 0 <= count <= 20: raise RuleError("重复次数必须是0～20整数")
                for _ in range(count): self.steps(step["steps"])
            elif op == "choose":
                roll = self.rng.random() * sum(option["weight"] for option in step["choices"])
                for option in step["choices"]:
                    roll -= option["weight"]
                    if roll < 0:
                        self.steps(option["steps"])
                        break
            elif op in ("stat_add", "stat_set"):
                stat, amount = step["stat"], number(self.expr(step["value"]))
                key = FIELDS[stat] + str(target)
                base = self.data[key] - (6 if stat == "attack" else 0)
                value = amount + base if op == "stat_add" else amount
                if stat == "attack":
                    if type(value) is not int: raise RuleError("攻击等级必须为整数")
                    value = max(-6, min(6, value)) + 6
                elif stat == "accuracy": value = max(-2, min(3, value))
                else: value = int(number(value))
                self.data[key] = value
                self.messages.append(f"{self.data[f'player{target}']}的{ {'hp':'生命','attack':'攻击等级','accuracy':'命中值'}[stat]}发生变化。")
            elif op in ("set_attribute", "set_state"):
                value = self.expr(step["value"])
                if op == "set_attribute":
                    self.data[f"attribute{target}"] = attribute_id(value)
                    if target == self.actor: self.attribute_explicit = True
                else:
                    if type(value) is not int or not 0 <= value <= 10: raise RuleError("状态编号必须为0～10整数")
                    self.data[f"state{target}"] = value
            elif op == "set_var":
                value = self.expr(step["value"])
                if isinstance(value, (int, float)) and not isinstance(value, bool): number(value)
                if not isinstance(value, (int, float, str, bool)): raise RuleError("变量只能保存数值、字符串或布尔值")
                variables = self.variables.setdefault(target, {})
                if step["name"] not in variables and len(variables) >= 32: raise RuleError("每人最多32个自定义变量")
                variables[step["name"]] = value
            elif op == "heal":
                amount = max(0, int(number(self.expr(step["amount"]))))
                key = f"blood{target}"
                before = self.data[key]
                after = number(before + amount)
                if step.get("cap_to_max", True): after = max(before, min(after, self.data.get(f"max_blood{target}", 700)))
                self.data[key] = after
                result = {"healed": after-before}
                self.messages.append(f"{self.data[f'player{target}']}回复了{after-before}点生命。")
            elif op == "damage":
                amount = max(0, number(self.expr(step["amount"])))
                if step.get("damage_type", "normal") == "normal":
                    spec = {"id": 1, "hurt": amount, "attribute": attribute_id(step.get("attribute", self.skill.get("attribute", 0))), "function": [0], "parameter": 0}
                    result = self.legacy(spec, force_hit=not step.get("hit_check", True))
                else:
                    own = self.modifiers(self.actor)
                    accuracy = self.data[f"accuracy{self.actor}"] + own["accuracy"] - (.4 if self.data[f"state{self.actor}"] == 10 else 0)
                    hit = not step.get("hit_check", True) or self.rng.random() < max(0, min(1, accuracy))
                    before = self.data[f"blood{target}"]
                    lost = int(amount) if hit else 0
                    self.data[f"blood{target}"] = number(before-lost)
                    if target != self.actor and hit and lost > 0:
                        self.locals["action"]["hit"] = True
                    result = {"hp_damage": min(max(0, before), lost), "raw_damage": lost, "hit": hit}
                    self.messages.append(f"{self.data[f'player{target}']}受到{lost}点固定伤害。" if hit else "未命中！")
            elif op == "message":
                text = step["text"] if "text" in step else "".join(str(self.expr(part)) for part in step["parts"])
                if len(text) > 300: raise RuleError("生成的消息超过300字")
                self.messages.append(text)
            if "save_as" in step:
                if result is None: raise RuleError("只有damage/heal/legacy能保存结果")
                self.locals[step["save_as"]] = result


class SkillEngine:
    def __init__(self, calculator, rng, skill_file):
        self.calculator, self.rng, self.skill_file = calculator, rng, skill_file

    def execute(self, rules, data, variables, actor, skill_id):
        data, variables = copy.deepcopy(data), copy.deepcopy(variables)
        spec = dict(rules.skills[str(skill_id)], id=skill_id)
        context = Context(rules, data, variables, actor, self.rng, self.calculator, spec, self.skill_file)
        for trigger in rules.triggers:
            if trigger["event"] == "before_skill" and context.expr(trigger.get("when", True)):
                context.steps(trigger["steps"])
        if data[f"blood{actor}"] > 0 and data[f"blood{3-actor}"] > 0:
            context.steps(spec.get("steps", [{"op": "legacy"}]))
            if not context.attribute_explicit:
                data[f"attribute{actor}"] = spec["attribute"]
            for trigger in rules.triggers:
                if trigger["event"] == "after_skill" and context.expr(trigger.get("when", True)):
                    context.steps(trigger["steps"])
        self.update_display(rules, data, variables)
        return data, variables, "\n".join(context.messages)

    @staticmethod
    def update_display(rules, data, variables):
        modifiers = {}
        for slot in (1, 2):
            context = Context(rules, data, variables, slot, None)
            modifiers[slot] = context.modifiers(slot)
        data["_rule_modifiers"] = modifiers
