"""保留原技能伤害计算；回合调度移至 duel_manager.py。"""
import json
import random

class calculate():

    def __init__(self,fighter_blood,fighted_blood ,fighter_attribute ,fighted_attribute ,fighter_atk,fighted_atk,fighter_accuracy,fighted_accuracy,fighter_state ,fighted_state,skill_hurt,skill_attribute,skill_function,skill_parameter,skill,used_num,skilljsonfile):
        self.rng = random
        # 调参
        self.restraint_coefficient = 1.2 #克制系数
        self.atk_corfficient = 1.22      #攻击乘数
        self.ran_corfficient = 0.08      #随机长度
        self.def_corfficient = 0.30      #防御系数
        self.fra_corfficient = 1.40      #易伤系数
        self.con_corfficient = 0.45      #混乱系数
        #
        self.fighter_blood = fighter_blood
        self.fighted_blood = fighted_blood
        self.fighter_attribute = fighter_attribute
        self.fighted_attribute = fighted_attribute
        self.fighter_atk = fighter_atk
        self.fighted_atk = fighted_atk
        self.fighter_accuracy = fighter_accuracy
        self.fighted_accuracy = fighted_accuracy
        self.fighter_state = fighter_state
        self.fighted_state = fighted_state
        self.fighter_state_all = fighter_state
        self.fighted_state_all = fighted_state
        self.skill_function = skill_function #列表,["skill_change_atk","skill_rand_state"]
        self.skill_parameter = skill_parameter #字典,{"skill_change_atk":{"if_to_myself":1,"change_num":-12~12},"skill_rand_state":{"if_to_myself":1自己0对方,"rand_choice":{0:100,1:10,2:10,7:50}}}
        self.skill_hurt = skill_hurt
        self.skill_attribute = skill_attribute
        self.skill = skill
        self.used_num = used_num
        self.skilljsonfile = skilljsonfile
        self.fighter_blood_last = fighter_blood
        self.fighted_blood_last = fighted_blood

        self.is_restraint = 1.0
        self.def_cor = 1
        self.jump = 0
        self.iszero = 0
        self.fighter_notchange = 0
        self.fighted_notchange = 0
        self.acc = 0
        self.ifacc = 0


    def cac(self):
        # 判断疲惫
        message = ""
        msg = ""
        return_msg = ""

        if self.fighter_state == 1:
            self.fighter_state = 0
            # print("疲惫中！",end="")
            return "疲惫中！"

        else:
            #判断克制
            restraint = [[0,0,0,0,0,0,0],
                         [0,0,1,-1,0,0,1],
                         [0,-1,0,1,0,0,1],
                         [0,1,-1,0,0,0,1],
                         [0,0,-1,0,0,1,0],
                         [0,0,0,-1,1,0,0],
                         [1,-1,-1,-1,0,0,1]]
            restraint_text = ["微弱！","","克制！"]
            self.is_restraint = self.restraint_coefficient ** restraint[self.skill_attribute][self.fighted_attribute]
            # print(restraint_text[(restraint[self.skill_attribute][self.fighted_attribute]+1)])

            if self.fighter_state == 9:
                self.fighter_state = 0
                self.skill = self.rng.randint(0,int(self.used_num))
                file = getattr(self, "skill_definitions", None)
                if file is None:
                    with open(self.skilljsonfile, 'r', encoding="utf-8-sig") as stream:
                        file = json.load(stream)
                    file = file.get("skills", file)
                self.skill = self.rng.choice([int(key) for key in file])
                file_skill = file[str(self.skill)]
                self.skill_hurt = file_skill["hurt"]
                self.skill_attribute = file_skill["attribute"]
                self.skill_function = file_skill["function"]
                self.skill_parameter = file_skill["parameter"]
                name = str(file_skill["name"])
                msg += f"在疑惑中使用了{name}！"


            self.acc = self.fighter_accuracy + getattr(self, "fighter_accuracy_bonus", 0)
            if self.fighter_state == 10:
                self.fighter_state = 0
                self.acc = self.acc - 0.4
            if self.acc <= 0:
                self.acc = 0
            if self.acc >= 1:
                self.acc = 1
            self.ifacc = getattr(self, "force_hit", False) or self.rng.random() < self.acc
            # if ifacc:
            #     pass
            # else:
            #     return f"未命中！"



            # 判断是否使用了防御
            if self.skill == 0 :
                self.fighter_state = 2
                self.jump = 1
                # print("你下一回合受到的伤害减弱{}%！".format(int(100*(1-def_corfficient))),end="")
                # return "你下一回合受到的伤害减弱{}%！".format(int(100*(1-self.def_corfficient)))
                msg += "你下一回合受到的伤害减弱{}%！".format(int(100*(1-self.def_corfficient)))
                self.iszero = 1

            #是否混乱
            if self.fighter_state == 7 and ("skill_random_damage" not in self.skill_function):
                self.fighter_state = 0
                if_confused = (self.rng.random() < self.con_corfficient)
                if if_confused:
                    fight = self.skill_hurt * (self.atk_corfficient ** (max(0, min(12, self.fighter_atk + getattr(self, "fighter_atk_bonus", 0))) - 6))
                    self_damage = int(self.rng.normalvariate(fight, fight * self.ran_corfficient))
                    if self.fighter_blood - self_damage <= 0:
                        self_damage = max(0, self.fighter_blood - 1)
                        self.fighter_blood = 1
                        return f"混乱了！对自己造成了{self_damage}点伤害！"
                    else:
                        self.fighter_blood -= self_damage
                        return f"混乱了！对自己造成了{self_damage}点伤害！"
                else:
                    pass

            # fighter_blood_last = 0
            # fighted_blood_last = 0


            if self.fighter_state == 8:#判断时滞
                self.fighter_notchange = 1
                msg += "完全感受不到时间的流逝……"
            if self.fighted_state == 8:
                self.fighted_notchange = 1
                msg += "完全感受不到对方身旁时间的流逝……"



            state_fun_name = f"self.state_judgement{self.fighted_state}"
            if self.fighted_state in [2,3,4,5,6]:
                msg1 = getattr(self, "state_judgement" + str(self.fighted_state))()
                msg += str(msg1)
                # print(msg)
                if self.iszero:
                    # fighter_blood_last = self.fighter_blood
                    # fighted_blood_last = self.fighted_blood
                    return msg


            #技能的效果
            for function in self.skill_function:
                if (str(function)) and (isinstance(self.skill_parameter,dict)):
                    fun_name = f"self.{function}"
                    parameter = self.skill_parameter[function]
                    returnmsg = self._dispatch_skill(function, parameter)
                    returnmsg = str(returnmsg)
                    if returnmsg:
                        return_msg += returnmsg



            msg_dam = ""
            #伤害结算
            if not self.jump:
                if self.ifacc:
                    damage = int(self.damage())
                    if damage > 0:
                        msg_dam = restraint_text[(
                                    restraint[self.skill_attribute][self.fighted_attribute] + 1)] + f"造成了{damage}点伤害！"
                else:
                    msg_dam = restraint_text[(
                            restraint[self.skill_attribute][self.fighted_attribute] + 1)] + f"未命中！"


            # 属性变化
            self.fighter_attribute = self.skill_attribute

            if self.fighter_notchange == 1:
                self.fighter_state = 8
            if self.fighted_notchange == 1:
                self.fighted_state = 8

            message = msg + msg_dam + return_msg
            return message



    def state_judgement2(self):
        #防御
        self.fighted_state = 0
        self.def_cor = self.def_corfficient
        return ""

    def state_judgement3(self):
        #毒
        blooding = int(self.rng.normalvariate(getattr(self, "bleed_damage", 95), getattr(self, "bleed_damage", 95) * self.ran_corfficient))
        self.fighted_blood -= blooding
        # print("对方因为流血损失了{}点血量！".format(blooding), end="")
        return "对方因为流血损失了{}点血量！".format(blooding)

    def state_judgement4(self):
        # 顽强
        self.fighted_state = 0
        self.iszero = 1
        return_msg = ""

        for function in self.skill_function:
            if (str(function)) and (isinstance(self.skill_parameter, dict)):
                fun_name = f"self.{function}"
                parameter = self.skill_parameter[function]
                returnmsg = self._dispatch_skill(function, parameter)
                returnmsg = str(returnmsg)
                if returnmsg:
                    return_msg += returnmsg
        # 伤害结算
        if not self.jump and not self.ifacc:
            return return_msg + "未命中！"
        if not self.jump:
            damage = int(self.damage())
        # 属性变化
        self.fighter_attribute = self.skill_attribute

        damage = self.fighted_blood_last - self.fighted_blood

        if self.fighted_blood <= 0:
            self.fighted_blood = 1
            damage = self.fighted_blood_last - 1
            return return_msg + "造成了{}点伤害，但对方挺住了！".format(damage)
        else:
            damage = damage if damage > 0 else 0
            return return_msg + "造成了{}点伤害！".format(damage)

    def state_judgement5(self):
        # 荆棘
        self.fighted_state = 0
        self.iszero = 1
        return_msg = ""

        for function in self.skill_function:
            if (str(function)) and (isinstance(self.skill_parameter, dict)):
                fun_name = f"self.{function}"
                parameter = self.skill_parameter[function]
                returnmsg = self._dispatch_skill(function, parameter)
                returnmsg = str(returnmsg)
                if returnmsg:
                    return_msg += returnmsg
        # 伤害结算
        if not self.jump and not self.ifacc:
            return return_msg + "未命中！"
        if not self.jump:
            damage = int(self.damage())
        # 属性变化
        self.fighter_attribute = self.skill_attribute

        damage = self.fighted_blood_last - self.fighted_blood
        damage = damage if damage > 0 else 0

        self_damage = int(getattr(self, "thorns_ratio", .3) * damage)
        if self.fighter_blood - self_damage <= 0:
            self_damage = max(0, self.fighter_blood - 1)
            self.fighter_blood = 1
            return f"造成了{damage}点伤害！同时由于对方的荆棘损失{self_damage}点血量！"+return_msg
        else:
            self.fighter_blood -= self_damage
            return f"造成了{damage}点伤害！同时由于对方的荆棘损失{self_damage}点血量！"+return_msg




    def state_judgement6(self):
        #易伤
        self.fighted_state = 0
        self.def_cor = self.fra_corfficient
        return ""


    def damage(self,ifuse = 0,only_retrn = False,scale = 1):
        fight = (ifuse if ifuse else self.skill_hurt) * (self.atk_corfficient ** (max(0, min(12, self.fighter_atk + getattr(self, "fighter_atk_bonus", 0))) - 6)) * self.is_restraint * self.def_cor * getattr(self, "damage_multiplier", 1)
        fight_rand = max(0, int(self.rng.normalvariate(fight,fight*self.ran_corfficient) * scale))
        # print("造成了{}点伤害！".format(fight_rand),end="")
        if not only_retrn:
            self.fighted_blood -= fight_rand
            self.attack_hit = getattr(self, "attack_hit", False) or fight_rand > 0
        return fight_rand


    def iter_method(self,data):
            total = sum(data.values())
            rad = self.rng.randint(1, total)
            cur_total = 0
            res = ""
            for k, v in data.items():
                cur_total += v
                if rad <= cur_total:
                    res = k
                    break
            return int(res)

    def skill_rand_state(self,kw):#随机状态，格式：{"if_to_myself":1自己0对方,"rand_choice":{0:100,1:10,2:10,7:50}}，0正常1疲惫2防御3流血4顽强5荆棘6易伤7混乱8时滞
        # print(kw)
        states = ["是正常状态！","疲惫了！","进入防御状态了！","进入流血状态了！","变得顽强了！","身边长出荆棘了！","容易受到伤害了！","混乱了！","时间暂停了！","变得迷惑了！","失明了！"]
        if_to_myself = kw.get("if_to_myself", None)
        rand_chioce = kw.get("rand_choice",None) #参数应是字典
        if if_to_myself == 1:
            if rand_chioce:
                self.fighter_state = int(self.iter_method(rand_chioce))
                return states[self.fighter_state]
        elif if_to_myself == 0:
            if rand_chioce:
                self.fighted_state = int(self.iter_method(rand_chioce))
                return "对方" + states[self.fighted_state]



    def skill_change_atk(self,kw):  #攻击改变，参数格式：{"if_to_myself":1,"change_num":-12~12}
        # print(kw)
        if_to_myself = kw.get("if_to_myself", None)
        change_num = kw.get("change_num", 0)
        # print(change_num)
        # print(self.skill_more_b,self.skill_more_c)
        if if_to_myself == 1:
            self.fighter_atk += change_num
            if change_num == 0 and self.fighter_atk < 6:
                self.fighter_atk = 6
            if self.fighter_atk < 0:
                self.fighter_atk = 0
            if self.fighter_atk > 12:
                self.fighter_atk = 12
            # print("攻击变化为{}！".format(self.fighter_atk - 6), end="")
            return "攻击变化为{}！".format(self.fighter_atk - 6)
        elif if_to_myself == 0:
            self.fighted_atk += change_num
            if change_num == 0 and self.fighted_atk > 6:
                self.fighted_atk = 6
            if self.fighted_atk < 0 :
                self.fighted_atk = 0
            if self.fighted_atk > 12:
                self.fighted_atk = 12
            # print("对方攻击变化为{}！".format(self.fighted_atk - 6), end="")
            return "对方攻击变化为{}！".format(self.fighted_atk - 6)
        # print(self.fighter_atk)

    def skill_treatment(self,kw):#治疗自己：{"if_to_myself":1,"damage":400}
        if_to_myself = kw.get("if_to_myself", None)
        damage = kw.get("damage", 0)
        ratio = kw.get("ratio",0)
        # state = kw.get("state",None)
        # print(self.skill_more_b,self.skill_more_c)
        if if_to_myself == 1:
            msg = ""
            self.jump = 1
            if getattr(self, "healing_cap", False):
                damage = min(damage, max(0, self.fighter_max_hp-self.fighter_blood))
            self.fighter_blood += int(damage)
            # if state:
            #     msg = self.rand_state(state)
            return msg + f"回复了{damage}点血量！"
        elif if_to_myself == 0:
            msg = ""
            self.jump = 1
            if self.ifacc:
                real_damage = int(self.damage(ifuse=damage))
                healed = int(real_damage * ratio)
                if getattr(self, "healing_cap", False):
                    healed = min(healed, max(0, self.fighter_max_hp-self.fighter_blood))
                self.fighter_blood += healed
                # if state:
                #     msg = self.rand_state(state)
                return msg + f"造成了{real_damage}点伤害！回复了{healed}点血量！"
            else:
                return msg + f"未命中！"
        # print(self.fighter_atk)

    def skill_addition(self,kw):#造成固伤
        if_to_myself = kw.get("if_to_myself", None)
        damage = kw.get("damage", 0)
        ratio = kw.get("ratio",100)
        rand = self.rng.random()
        if rand < ratio / 100:
            if if_to_myself == 1:
                # self.jump = 1
                if self.fighter_blood - damage > 0 :
                    self.fighter_blood -= damage
                    return  f"对自己造成了{damage}点固定伤害！"
                else:
                    damage = self.fighter_blood - 1
                    self.fighter_blood = 1
                    return f"对自己造成了{damage}点固定伤害！"
            elif if_to_myself == 0:
                if self.ifacc:
                # self.jump = 1
                    if damage == 0:
                        damage = self.fighted_blood-self.fighter_blood if (self.fighted_blood-self.fighter_blood > 0) else 0
                        self.fighted_blood -= damage
                        return f"造成了{damage}点固定伤害！"
                    else:
                        self.fighted_blood -= damage
                        return  f"造成了{damage}点固定伤害！"
                else:
                    return "未命中！"
        else:
            return ""

    def skill_change(self,kw):#交换属性
        # print(self.fighter_atk, self.fighted_atk, self.fighter_state, self.fighted_state)
        self.fighter_atk,self.fighted_atk = self.fighted_atk,self.fighter_atk
        self.fighter_state,self.fighted_state = self.fighted_state,self.fighter_state
        self.fighter_accuracy, self.fighted_accuracy = self.fighted_accuracy, self.fighter_accuracy
        # print(self.fighter_atk,self.fighted_atk,self.fighter_state,self.fighted_state)
        # print("交换了双方的属性！",end="")
        return "交换了双方的属性！"


    def skill_random_damage(self,kw):
        self.jump = 1
        down = kw.get("down",0)
        up = kw.get("up",0)
        ran = self.rng.randint(down,up)
        if self.fighter_state == 7:
            self.fighter_state = 0
            dmg_self = 0
            dmg = 0
            self_damage = int(self.acc * self.con_corfficient * self.damage(ifuse=self.skill_hurt*ran,only_retrn=True))
            dmg = int(self.acc * (1 - self.con_corfficient) * self.damage(ifuse=self.skill_hurt * ran,only_retrn=True))
            self.fighted_blood -= dmg
            self.attack_hit = getattr(self, "attack_hit", False) or dmg > 0
            if self.fighter_blood - self_damage <= 0:
                dmg_self = self.fighter_blood_last - 1
                self.fighter_blood = 1
            else:
                self.fighter_blood -= self_damage
                dmg_self = self_damage
            return f"由于混乱对自己造成了{dmg_self}点伤害！同时对对方造成了{dmg}点伤害！"
        else:
            # dmg = 0
            # for i in range(0, ran):
            #     dm = self.damage()
            #     dmg += dm
            dmg = self.damage(ifuse=self.skill_hurt*ran, scale=self.acc)
            return f"对对方造成了{dmg}点伤害！"




    def skill_if_positive(self,kw):
        msg = ""
        if_judge_myself = kw.get("if_judge_myself", None)
        if_is_positive = kw.get("if_is_positive", 0)
        if_to_myself = kw.get("if_to_myself", None)
        effect = str(kw.get("effect", None))
        ifispositive = 2
        if if_judge_myself:
            if self.fighter_state_all in [2,4,5]:
                ifispositive = 1
            if self.fighter_state_all in [1,3,6,7]:
                ifispositive = 0
        else:
            if self.fighted_state_all in [2,4,5]:
                ifispositive = 1
            if self.fighted_state_all in [1,3,6,7]:
                ifispositive = 0
        if if_is_positive == ifispositive:
            if if_to_myself and effect == "add":#延长
                self.fighter_state = self.fighter_state_all
                msg += "效果延长了！"
            if if_to_myself and effect == "atk":#增伤
                self.def_cor = self.def_cor* 1.7
                msg += "伤害增加了！"
            if if_to_myself and effect == "clean":#净化
                self.fighter_state = 0
                self.def_cor = self.def_cor * 1.4
                msg += "净化了不利状态并增加了伤害！"
            if not if_to_myself and effect == "add":#延长
                self.fighted_state = self.fighted_state_all
            if not if_to_myself and effect == "atk":  # 增伤
                self.def_cor = self.def_cor* 1.7
                msg += "伤害增加了！"
            if not if_to_myself and effect == "turn":  # 夺取
                self.fighter_state = self.fighted_state_all
                self.fighted_state = 0
                msg += "夺取了对方的效果！"
        return msg

    def skill_acc_damage(self, kw):
        self.jump = 1
        dmg = self.damage(ifuse=self.skill_hurt * (1 + min(.5, max(0, 1-self.acc))))
        return f"对对方造成了{dmg}点伤害！"

    def skill_acc_change(self, kw):
        if_to_myself = kw.get("if_to_myself", None)
        change_num = kw.get("change_num", 0)
        if if_to_myself == 1:
            self.fighter_accuracy += change_num
            return f"命中变化为{int(self.fighter_accuracy*100)}%！"
        elif if_to_myself == 0:
            self.fighted_accuracy += change_num
            return f"对方命中变化为{int(self.fighted_accuracy*100)}%！"

    def _dispatch_skill(self, function, parameter):
        allowed = {"skill_acc_change", "skill_acc_damage", "skill_addition",
                   "skill_change", "skill_change_atk", "skill_if_positive",
                   "skill_rand_state", "skill_random_damage", "skill_treatment"}
        if function not in allowed:
            raise ValueError("未知决斗技能函数：" + str(function))
        return getattr(self, function)(parameter)


def _create_manager():
    import asyncio
    from pathlib import Path
    import nonebot
    from nonebot import require
    from nonebot.adapters.onebot.v11 import Message, MessageSegment
    from ..database import dbcontrol, getcollection
    from .duel_manager import DuelManager, player_status_lines

    driver = nonebot.get_driver()
    config = driver.config
    scheduler = require("nonebot_plugin_apscheduler").scheduler
    data_dir = Path(getattr(config, "russian_path", Path())) / "data" / "fight"
    nickname = next(iter(config.nickname), "本裁判")

    from .battle_ui import render_battle
    from qqbot_media import render_scoped
    import copy
    from functools import partial
    ui_slots = asyncio.Semaphore(2)

    async def image_bytes(function, *args):
        async with ui_slots:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, partial(function, *args))

    async def send(bot, event, payload):
        # Only render() can create an image. All broadcasts/help/results stay text.
        await bot.send(event, Message(payload))

    async def render(bot, event, game, choices):
        snapshot = copy.deepcopy(game.data)
        snapshot['_command_prefix'] = manager.prefix_for(bot,event)
        snapshot['_combat_log'] = [manager.format_commands(line,bot,event) for line in snapshot.get('_combat_log',[])]
        image = await image_bytes(render_scoped,render_battle,bot.self_id,event.group_id,manager._rules(game),snapshot,game.first)
        return MessageSegment.text('现在轮到')+MessageSegment.at(game.data['next'])+MessageSegment.text('行动。\n')+MessageSegment.image(image)

    manager = DuelManager(calculate, data_dir, send, scheduler=scheduler,
        dbcontrol=dbcontrol, getcollection=getcollection, render=render,
        bot_name=nickname, command_prefix='#')
    async def shutdown():
        manager.shutdown()

    driver.on_shutdown(shutdown)
    return manager


russian_manager = _create_manager()
