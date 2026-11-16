from testbot.plugins.persona_utils import load_persona,attack,identity_question
import re
import random
from pathlib import Path
from testbot.plugins.chat_storage import ChatFiles
from typing import Dict, List, Tuple
from asyncio import sleep

from nonebot import on_regex, on_command, on_message
from nonebot.internal.params import Arg, ArgPlainText, Depends
from nonebot.params import  CommandArg, RegexGroup
from nonebot.typing import T_State, T_Handler
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent
from nonebot.adapters.onebot.v11.permission import (
    GROUP_ADMIN,
    GROUP_OWNER,
    PRIVATE_FRIEND,
    GROUP_MEMBER
)

from .util import to_json, parse_msg, save_and_convert_img
from .models import MatchType, IncludeCQCodeError
from .data_source import word_bank as wb
from .data_source import dbcontrol_ans,dbcontrol_single
# from testbot.testbot.plugins.database import increaselike
from testbot.plugins.database import increaselike

reply_type = "random"


def get_session_id(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    else:
        return f"private_{event.user_id}"


def wb_match_rule(event: MessageEvent, state: T_State ) -> bool:
    if attack(event.get_plaintext()) or identity_question(event.get_plaintext()):
        return False
    command_text=event.get_plaintext().strip().lstrip('#\\')
    for alias in sorted(load_persona().aliases,key=len,reverse=True):
        if command_text.startswith(alias):
            command_text=command_text[len(alias):].lstrip(' ,，:：!！');break
    if re.match(r'^(?:设置)?(?:本群|当前群)?(?:本地)?问答(?:触发)?概率|^(?:模型分工|模型配置)$',command_text):
        return False
    msgs = wb.match(get_session_id(event), event.get_message(), to_me=event.is_tome())
    # result = dbcontrol_ans()
    msgs = [m for m in (msgs or []) if load_persona().output_ok(str(m))]
    if not msgs:
        return False
    if isinstance(event, GroupMessageEvent):
        try:
            files=ChatFiles(Path('data/learning_chat/local_intelligence'))
            key=f'{event.self_id}:{event.group_id}:{event.message_id}'
            # A matched word-bank entry owns this local-QA event, even on a miss.
            # The learning handler must not send a second reply or paid substitute.
            files.claim_qa(key)
            if not files.allow_qa(event.group_id,None,key):
                return False
        except (OSError,ValueError,TypeError):
            return False
    if reply_type == "random":
        msgs = [random.choice(msgs)]
    state["replies"] = msgs
    return True


wb_matcher = on_message(wb_match_rule, priority=2, block=False)


@wb_matcher.handle()
async def handle_wb(event: MessageEvent, state: T_State ):
    msgs: List[Message] = state["replies"]
    for msg in msgs:
        reply=Message.template(msg).format(
            nickname=event.sender.card or event.sender.nickname,
            sender_id=event.sender.user_id,
        )
        if load_persona().output_ok(str(reply)):
            await wb_matcher.finish(reply)


PERM_EDIT = GROUP_ADMIN | GROUP_OWNER | PRIVATE_FRIEND | SUPERUSER
PERM_GLOBAL = SUPERUSER
PERM_ALL = GROUP_ADMIN | GROUP_OWNER | PRIVATE_FRIEND | SUPERUSER | GROUP_MEMBER

wb_set_cmd = on_regex(
    r"^((?:模糊|正则|@)*)\s*问\s*(\S+.*?)\s*答\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=11,
    permission=PERM_ALL,
)

wb_set_cmd_gl = on_regex(
    r"^((?:全局|模糊|正则|@)*)\s*问\s*(\S+.*?)\s*答\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=10,
    permission=PERM_ALL,
)


@wb_set_cmd.handle()
@wb_set_cmd_gl.handle()
async def wb_set(
    bot: Bot,
    event: MessageEvent,
    matcher: Matcher,
    matched: Tuple[str, ...] = RegexGroup(),
):
    flag, key, value = matched
    if attack(key) or attack(value) or not load_persona().output_ok(value):
        await matcher.finish("这组词条含有人格改写指令或不合适的表达，未保存。")
    type_ = (
        MatchType.regex
        if "正则" in flag
        else MatchType.include
        if "模糊" in flag
        else MatchType.congruence
    )
    require_to_me: bool = False
    if "@" in flag:  # @问需要to_me才会触发
        require_to_me = True
    else:
        # 以昵称开头的词条视为需要to_me
        for name in bot.config.nickname:
            if key.startswith(name):
                key = key.replace(name, "", 1)
                require_to_me = True
                break

    value = Message(parse_msg(value))  # 替换/at, /self, /atself
    await save_and_convert_img(value, wb.img_dir)  # 保存回答中的图片
    value = str(value)
    value = value.replace('"', '”').replace("'", "‘")
    value = Message(value)
    key = str(key)
    key = key.replace('"', '“').replace("'", "‘")
    key = Message(key)

    index = get_session_id(event)
    index = "0" if "全局" in flag else index
    permission = await SUPERUSER(bot,event)
    try:
        # if permission:
        #     result = dbcontrol_ans("SELECT * FROM answer_ans WHERE answer_type='{}' AND answer_group = '{}' AND answer_key = '{}' AND answer_use = 2".format(type_.name,index,key))
        #     if result[-1]:
        #         await matcher.finish(message="当前词条未通过审核哦~")
        # wb.set(index, type_, Message(key), value, require_to_me)
        # print(index,type_.name)
        if (not permission) and index == "0":
            wb.set_exam(index, type_, Message(key), value, require_to_me)
            dbcontrol_ans('INSERT INTO answer_exam (answer_type,answer_group,answer_key,answer_answer,answer_uploader) values ("{}","{}","{}","{}","{}")'.format(type_.name, index,key,[str(value)],event.user_id))
            # dbcontrol_ans("UPDATE answer_exam SET answer_uploader = {} WHERE answer_type='{}' AND answer_group = '{}' AND answer_key = '{}'".format(event.user_id,type_.name,index,key))
            await matcher.finish(message="我记住了~请等待审核~")
        else:
            wb.set(index, type_, Message(key), value, require_to_me)
            # dbcontrol_ans("UPDATE answer_ans SET answer_uploader = {} WHERE answer_type='{}' AND answer_group = '{}' AND answer_key = '{}'".format(event.user_id, type_.name, index,key))
            await matcher.finish(message="我记住了~")
    except IncludeCQCodeError:
        await matcher.finish("正则匹配中不允许带有CQ码")


wb_del_cmd = on_regex(
    r"^删除\s*((?:模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=11,
    permission=PERM_EDIT,
)

wb_del_cmd_gl = on_regex(
    r"^删除\s*((?:全局|模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=10,
    permission=PERM_GLOBAL,
)


@wb_del_cmd.handle()
@wb_del_cmd_gl.handle()
async def _(
    bot: Bot,
    event: MessageEvent,
    matcher: Matcher,
    matched: Tuple[str, ...] = RegexGroup(),
):
    flag, key = matched
    type_ = (
        MatchType.regex
        if "正则" in flag
        else MatchType.include
        if "模糊" in flag
        else MatchType.congruence
    )
    require_to_me: bool = False
    if "@" in flag:
        require_to_me = True
    else:
        for name in bot.config.nickname:
            if key.startswith(name):
                key = key.replace(name, "", 1)
                require_to_me = True
                break

    index = get_session_id(event)
    index = "0" if "全局" in flag else index
    res = wb.delete(index, type_, Message(key), require_to_me)
    if res:
        await matcher.finish("删除成功~")


def wb_clear(type_: str = "") -> T_Handler:
    async def wb_clear_(
        event: MessageEvent, state: T_State, arg: Message = CommandArg()):
        msg = arg.extract_plain_text().strip()
        if msg:
            state["is_sure"] = msg

        if not type_:
            index = get_session_id(event)
            keyword = "群聊" if isinstance(event, GroupMessageEvent) else "个人"
        else:
            index = "0" if type_ == "全局" else None
            keyword = type_
        state["index"] = index  # 为 "0" 表示全局词库, 为 None 表示全部词库
        state["keyword"] = keyword  # 群聊/个人/全局/全部

    return wb_clear_


wb_clear_cmd = on_command(
    "删除词库",
    block=True,
    priority=10,
    permission=PERM_EDIT,
    handlers=[wb_clear()],
)
wb_clear_cmd_gl = on_command(
    "删除全局词库", block=True, priority=10, permission=PERM_GLOBAL, handlers=[wb_clear("全局")]
)
wb_clear_bank = on_command(
    "删除全部词库", block=True, priority=10, permission=PERM_GLOBAL, handlers=[wb_clear("全部")]
)


prompt_clear = Message.template("此命令将会清空您的{keyword}词库，确定请发送 yes")


@wb_clear_cmd.got("is_sure", prompt=prompt_clear)
@wb_clear_cmd_gl.got("is_sure", prompt=prompt_clear)
@wb_clear_bank.got("is_sure", prompt=prompt_clear)
async def _(matcher: Matcher, state: T_State ):
    is_sure = str(state["is_sure"]).strip()
    index = state["index"]
    if is_sure == "yes":
        res = wb.clear(index)
        if res:
            await matcher.finish(Message.template("删除{keyword}词库成功~"))
    else:
        await matcher.finish("命令取消")


wb_search_cmd = on_regex(
    r"^查询\s*((?:群|用户)*)\s*(\d*)\s*((?:全局)?(?:模糊|正则)?@?)\s*词库\s*(.*?)\s*$",
    flags=re.S,
    block=True,
    priority=10,
    permission=PERM_GLOBAL,
)
wb_search_cmd_user = on_regex(
    r"^查询\s*((?:模糊|正则)?@?)\s*词库\s*(.*?)\s*$",
    flags=re.S,
    block=True,
    priority=11,
    permission=PERM_EDIT,
)


@wb_search_cmd_user.handle()
@wb_search_cmd.handle()
async def wb_search(bot: Bot, event: MessageEvent, matcher: Matcher,
                    matched: Tuple[str, ...] = RegexGroup()):
    # wordbank_query_pages_v1; keep the original matcher permissions and rules.
    from .query_pages import run_search
    await run_search(bot,event,matcher,matched,wb,get_session_id,MatchType)



exam = on_command("审核",permission=PERM_GLOBAL,priority=12)
@exam.handle()
async def _():

    num = dbcontrol_single("SELECT COUNT(*) FROM answer_exam")
    num = int(num[0][0])
    if num:
        result = dbcontrol_ans("SELECT * FROM answer_exam ORDER BY _id LIMIT 1 OFFSET {}".format(0))
        ifenpty = result[-1]
        if ifenpty:
            result = result[0][0]
            answer_type = result[1]
            type_ = (
                MatchType.regex
                if answer_type == "regex"
                else MatchType.include
                if answer_type == "include"
                else MatchType.congruence
            )
            answer_id = result[0]
            answer_group = result[2]
            answer_key = result[3]
            answer_answer = result[4]
            answer_uploader = result[5]
            if answer_group == '0':
                answer_group = "全局"
            message = "词条：{}\n回答：{}\n匹配：{}\n群组：{}\n上传者：{}".format(answer_key,answer_answer,answer_type,answer_group,answer_uploader)
            message = Message(message)
            await exam.send(message)
    else:
        await exam.finish("没有待审核的词条~")

def depend():
    num = dbcontrol_single("SELECT COUNT(*) FROM answer_exam")
    num = int(num[0][0])
    return  num


@exam.got("key", prompt="")
async def handle_func(num: int = Depends(depend),key:Message = Arg(),name:str = ArgPlainText("key")):
    print(num)
    if num == 1:
        result = dbcontrol_ans("SELECT * FROM answer_exam ORDER BY _id LIMIT 1 OFFSET {}".format(0))
        result = result[0][0]
        answer_type = result[1]
        type_ = (
            MatchType.regex
            if answer_type == "regex"
            else MatchType.include
            if answer_type == "include"
            else MatchType.congruence
        )
        answer_id = result[0]
        answer_group = result[2]
        answer_key = result[3]
        answer_key_msg = Message(answer_key)
        answer_answer = result[4]
        answer_uploader = result[5]
        print(f"{answer_id,answer_key,answer_answer}")

        if name in ["退出"]:
            await exam.finish("finish")
        elif name in ["y", "Y", "ok", "yes", "1"]:
            answer_answer = eval(answer_answer)
            for answers in answer_answer:
                answers_msg = Message(answers)
                wb.set(answer_group, type_, answer_key_msg, answers_msg)
            wb.delete_exam(answer_group, type_, answer_key_msg,answer_id, ifdeletepicture=False)
            num = dbcontrol_ans("SELECT answer_num FROM answer_who WHERE answer_uploader = {}".format(answer_uploader))
            if num[-1]:
                num = num[0][0][0]
                dbcontrol_ans(
                    "UPDATE answer_who SET answer_num={} WHERE answer_uploader = {}".format(num + 1, answer_uploader))
            else:
                dbcontrol_ans(
                    "INSERT INTO answer_who (answer_num,answer_uploader) values ('{}','{}')".format(1, answer_uploader))
            await increaselike(answer_uploader, 3)
            await exam.finish("通过！为提供人增加3好感")
        elif name in ["n", "N", "no", "0"]:
            wb.delete_exam(answer_group, type_, answer_key_msg,answer_id, ifdeletepicture=False)
            await exam.finish("未通过！")
        else:
            await exam.reject("wrong!")
    else:
        result = dbcontrol_ans("SELECT * FROM answer_exam ORDER BY _id LIMIT 1 OFFSET {}".format(0))
        ifenpty = result[-1]
        if ifenpty:
            result = result[0][0]
            answer_type = result[1]
            type_ = (
                MatchType.regex
                if answer_type == "regex"
                else MatchType.include
                if answer_type == "include"
                else MatchType.congruence
            )
            answer_id = result[0]
            answer_group = result[2]
            answer_key = result[3]
            answer_key_msg = Message(answer_key)
            answer_answer = result[4]
            answer_uploader = result[5]
            if answer_group == '0':
                answer_group_say = "全局"
            else:
                answer_group_say = "错误"
            if name in ["退出"]:
                await exam.finish("finish")
            elif name in ["y","Y","ok","yes","1"]:
                await exam.send("通过！")
                answer_answer = eval(answer_answer)
                for answers in answer_answer:
                    answers_msg = Message(answers)
                    wb.set(answer_group,type_,answer_key_msg,answers_msg)
                print(f"{answer_id,answer_key,answer_answer}")
                wb.delete_exam(answer_group,type_,answer_key_msg,answer_id,ifdeletepicture=False)
                num = dbcontrol_ans("SELECT answer_num FROM answer_who WHERE answer_uploader = {}".format(answer_uploader))
                if num[-1]:
                    num = num[0][0][0]
                    dbcontrol_ans("UPDATE answer_who SET answer_num={} WHERE answer_uploader = {}".format(num + 1,answer_uploader))
                else:
                    dbcontrol_ans("INSERT INTO answer_who (answer_num,answer_uploader) values ('{}','{}')".format(1,answer_uploader))
                await increaselike(answer_uploader,3)
                await exam.send("为{}增加3好感".format(answer_uploader))

                result = dbcontrol_ans("SELECT * FROM answer_exam ORDER BY _id LIMIT 1 OFFSET {}".format(0))         
                ifenpty = result[-1]         
                if ifenpty:             
                    result = result[0][0]             
                    answer_type = result[1]             
                    type_ = (                 
                        MatchType.regex                 
                        if answer_type == "regex"                
                        else MatchType.include                 
                        if answer_type == "include"                 
                        else MatchType.congruence            
                        )             
                    answer_id = result[0]             
                    answer_group = result[2]             
                    answer_key = result[3]             
                    answer_key_msg = Message(answer_key)             
                    answer_answer = result[4]             
                    answer_uploader = result[5]             
                    if answer_group == '0':                 
                        answer_group_say = "全局"             
                    else:                 
                        answer_group_say = "错误"             
                    message = "词条：{}\n回答：{}\n匹配：{}\n群组：{}\n上传者：{}".format(
                        answer_key,answer_answer,answer_type,answer_group_say,answer_uploader)             
                    message = Message(message)

                await exam.reject(message)
            elif name in ["n", "N", "no","0"]:
                await exam.send("未通过！")
                print(f"{answer_id,answer_key,answer_answer}")
                wb.delete_exam(answer_group, type_, answer_key_msg,answer_id, ifdeletepicture=False)

                result = dbcontrol_ans("SELECT * FROM answer_exam ORDER BY _id LIMIT 1 OFFSET {}".format(0))                          
                ifenpty = result[-1]
                print(result)                          
                if ifenpty:                                  
                    result = result[0][0]                                  
                    answer_type = result[1]                                  
                    type_ = (                                          
                        MatchType.regex                                          
                        if answer_type == "regex"                                         
                        else MatchType.include                                          
                        if answer_type == "include"                                          
                        else MatchType.congruence                                     
                        )                                  
                    answer_id = result[0]                                  
                    answer_group = result[2]                                  
                    answer_key = result[3]                                  
                    answer_key_msg = Message(answer_key)                                  
                    answer_answer = result[4]                                  
                    answer_uploader = result[5]                                  
                    if answer_group == '0':                                         
                        answer_group_say = "全局"                                  
                    else:                                          
                        answer_group_say = "错误"                                  
                    message = "词条：{}\n回答：{}\n匹配：{}\n群组：{}\n上传者：{}".format(                         
                            answer_key,answer_answer,answer_type,answer_group_say,answer_uploader)                                  
                    message = Message(message)
                    # print(message)
                
                await exam.reject(message)
            else:
                await exam.reject("wrong!")
        else:
            await exam.finish("finish")


wb_clo_cmd = on_regex(
    r"^关闭\s*((?:模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=11,
    permission=PERM_ALL,
)

wb_clo_cmd_gl = on_regex(
    r"^关闭\s*((?:全局|模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=10,
    permission=PERM_GLOBAL,
)


@wb_clo_cmd.handle()
@wb_clo_cmd_gl.handle()
async def _(
    bot: Bot,
    event: MessageEvent,
    matcher: Matcher,
    matched: Tuple[str, ...] = RegexGroup(),
):
    flag, key = matched
    type_ = (
        MatchType.regex
        if "正则" in flag
        else MatchType.include
        if "模糊" in flag
        else MatchType.congruence
    )
    require_to_me: bool = False
    if "@" in flag:
        require_to_me = True
    else:
        for name in bot.config.nickname:
            if key.startswith(name):
                key = key.replace(name, "", 1)
                require_to_me = True
                break

    index = get_session_id(event)
    index = "0" if "全局" in flag else index
    res = wb.close(index, type_, Message(key), require_to_me)
    if res:
        await matcher.finish("关闭成功~")

wb_op_cmd = on_regex(
    r"^开启\s*((?:模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=11,
    permission=PERM_ALL,
)

wb_op_cmd_gl = on_regex(
    r"^开启\s*((?:全局|模糊|正则|@)*)\s*词条\s*(\S+.*?)\s*$",
    flags=re.S,
    block=True,
    priority=10,
    permission=PERM_GLOBAL,
)


@wb_op_cmd.handle()
@wb_op_cmd_gl.handle()
async def _(
    bot: Bot,
    event: MessageEvent,
    matcher: Matcher,
    matched: Tuple[str, ...] = RegexGroup(),
):
    flag, key = matched
    type_ = (
        MatchType.regex
        if "正则" in flag
        else MatchType.include
        if "模糊" in flag
        else MatchType.congruence
    )
    # print("hello")
    require_to_me: bool = False
    if "@" in flag:
        require_to_me = True
    else:
        for name in bot.config.nickname:
            if key.startswith(name):
                key = key.replace(name, "", 1)
                require_to_me = True
                break
    # print("hello2")
    index = get_session_id(event)
    index = "0" if "全局" in flag else index
    # print("helllo3")
    res = wb.open(index, type_, Message(key), require_to_me)
    if res:
        await matcher.finish("开启成功~")