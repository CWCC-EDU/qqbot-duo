import ast
import json
import sqlite3
from typing import Dict, List, Iterator, Optional
from pathlib import Path

from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Message

from .util import compare_msg
from .models import MatchType, IncludeCQCodeError
from .word_entry import WordEntry

NULL_BANK = {t.name: {"0": []} for t in MatchType}

def dbcontrol_ans(control, dir="answer.db"):
    con = sqlite3.connect(r"database\{}".format(dir))
    cur = con.cursor()
    result = cur.execute(control)
    if result:
        counter = 0
        a = []
        for i in result:
            a.append(i)
            counter += 1
    else:
        a = []
        counter = 0
    cur.close()
    con.commit()
    con.close()
    return a, counter

def dbcontrol_single(control, dir="answer.db"):
    con = sqlite3.connect(r"database\{}".format(dir))
    cur = con.cursor()
    result = cur.execute(control)
    if result:
        counter = 0
        a = []
        for i in result:
            a.append(i[0])
            counter += 1
    else:
        a = []
        counter = 0
    cur.close()
    con.commit()
    con.close()
    return a, counter

def dbcontrol_tuple(control,dir="answer.db"):
    con = sqlite3.connect(r"database\{}".format(dir))
    cur=con.cursor()
    result = cur.execute(control)
    if result:
        counter = 0
        a = []
        for i in result:
            b = []
            b.append(i[0])
            # print(b)
            b.append(ast.literal_eval(i[1]))
            i = tuple(b)
            a.append(i)
            counter += 1
    else:
        a = []
        counter = 0
    cur.close()
    con.commit()
    con.close()
    return a,counter




class WordBank(object):
    def __init__(self):
        conn = sqlite3.connect(r"database\answer.db")
        print("数据库创建成功!")
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS answer(
        _id INTEGER PRIMARY KEY NOT NULL ,
        answer_type TEXT NOT NULL DEFAULT 'congruence',
        answer_group TEXT NOT NULL DEFAULT '0')
        """)
        print("问答表创建成功！")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS answer_ans(
        _id INTEGER PRIMARY KEY NOT NULL ,
        answer_type TEXT NOT NULL DEFAULT 'congruence',
        answer_group TEXT NOT NULL DEFAULT '0',
        answer_key TEXT NOT NULL DEFAULT 'question',
        answer_answer TEXT NOT NULL DEFAULT "['reply']",
        answer_use INTEGER NOT NULL DEFAULT 1)
        """)
        print("答案表创建成功！")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS answer_exam(
        _id INTEGER PRIMARY KEY NOT NULL ,
        answer_type TEXT NOT NULL DEFAULT 'congruence',
        answer_group TEXT NOT NULL DEFAULT '0',
        answer_key TEXT NOT NULL DEFAULT 'question',
        answer_answer TEXT NOT NULL DEFAULT "['reply']",
        answer_uploader INTEGER NOT NULL DEFAULT 0)
        """)
        print("答案表创建成功！")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS answer_who(
        _id INTEGER PRIMARY KEY NOT NULL ,
        answer_uploader INTEGER NOT NULL DEFAULT 0,
        answer_num INTEGER NOT NULL DEFAULT 0)
        """)
        print("答案表创建成功！")
        cur.close()
        conn.close()
        self.data_dir = Path("database").absolute()
        self.bank_path = self.data_dir / "answer.db"
        self.img_dir = self.data_dir / "img"

        # self.data_dir = Path("data/word_bank").absolute()
        # self.bank_path = self.data_dir / "bank.json"
        # self.img_dir = self.data_dir / "img"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.img_dir.mkdir(parents=True, exist_ok=True)
        self.__data: Dict[str, Dict[str, List[WordEntry]]] = {}
        self.__exam: Dict[str, Dict[str, List[WordEntry]]] = {}
        self.__load()

    def __load(self):
        if self.bank_path.exists():

            # with self.bank_path.open("r", encoding="utf-8") as f:
            #     data: Dict[str, Dict[str, Dict[str, List[str]]]] = json.load(f)
            #     print(data)
            #
            for t in MatchType:
                # print(t)
                self.__data[t.name] = {}
                self.__exam[t.name] = {}

                user_ids = dbcontrol_single("SELECT answer_group FROM answer WHERE answer_type = '{}'".format(t.name))
                # print(user_ids)
                user_ids = user_ids[0]

                # print("data.get:{}".format(data.get(t.name,{}).keys()))
                # for user_id in data.get(t.name, {}).keys():

                for user_id in user_ids:
                    # print("user_id:{}".format(user_id))
                    self.__data[t.name][user_id] = []
                    self.__exam[t.name][user_id] = []
                    # print("dataitmes:{}".format(data[t.name][user_id].items()))
                    dataitmes =dbcontrol_tuple("SELECT answer_key,answer_answer FROM answer_ans WHERE answer_type = '{}' AND answer_group = '{}' AND answer_use = 1 ".format(t.name,user_id))
                    dataitmes = dataitmes[0]
                    dataitmes_exam = dbcontrol_tuple("SELECT answer_key,answer_answer FROM answer_exam WHERE answer_type = '{}' AND answer_group = '{}' ".format(t.name,user_id))
                    dataitmes_exam = dataitmes_exam[0]
                    # print(dataitmes)
                    # for key, value in data[t.name][user_id].items():

                    for key, value in dataitmes:
                        # print("key:{},value:{}".format(key,value))
                        self.__data[t.name][user_id].append(WordEntry.load(key, value))
                        # print(self.__data[t.name][user_id][0].key)
                    for key, value in dataitmes_exam:
                        # print("key:{},value:{}".format(key,value))
                        self.__exam[t.name][user_id].append(WordEntry.load(key, value))
                        # print(self.__data[t.name][user_id][0].key)
            logger.success("读取词库位于 " + str(self.bank_path))
        else:
            self.__data = NULL_BANK
            self.__exam = NULL_BANK
            # self.__save()
            logger.success("创建词库位于 " + str(self.bank_path))

    def __save(self):
        data: Dict[str, Dict[str, Dict[str, List[str]]]] = {}
        print(data)
        for t in self.__data.keys():
            data[t] = {}
            for user_id in self.__data[t].keys():
                data[t][user_id] = {}
                for entry in self.__data[t][user_id]:
                    key, values = entry.dump()
                    data[t][user_id][key] = values
                    # print("answer,key:{},value:{}".format(key,values))
        # with self.bank_path.open("w", encoding="utf-8") as f:
        #     json.dump(data, f, ensure_ascii=False, indent=4)

    def match(
        self,
        index: str,
        msg: Message,
        match_type: Optional[MatchType] = None,
        to_me: bool = False,
    ) -> List[Message]:
        """
        :说明: `match`
        > 匹配词条

        :参数:
          * `index: str`: 为0时是全局词库
          * `msg: Message`: 需要匹配的消息

        :可选参数:
          * `match_type: Optional[MatchType] = None`: 为空表示依次尝试所有匹配方式\n
                MatchType.congruence: 全匹配(==)
                MatchType.include: 模糊匹配(in)
                MatchType.regex: 正则匹配(regex)
          * `to_me: bool = False`: 匹配 @bot

        :返回:
          - `List[Message]`: 首先匹配成功的消息列表
        """
        if match_type is None:
            for type_ in MatchType:
                res = self.__match(index, msg, type_, to_me)
                if res:
                    return res
            return []
        else:
            return self.__match(index, msg, match_type, to_me)

    def __get_entries(self, index: str, match_type: MatchType) -> Iterator[WordEntry]:
        for entry in self.__data[match_type.name].get(index, []):
            yield entry
        if index != "0":
            for entry in self.__data[match_type.name].get("0", []):  # 加入全局词库
                yield entry

    def __match(
        self, index: str, msg: Message, match_type: MatchType, to_me: bool = False
    ) -> List[Message]:
        for entry in self.__get_entries(index, match_type):
            # result1 = dbcontrol_single("SELECT answer_use FROM answer_ans WHERE answer_type='{}' AND answer_group = '{}' AND answer_key = '{}'".format(match_type.name,index,entry.key))
            # result2 = dbcontrol_single("SELECT answer_use FROM answer_ans WHERE answer_type='{}' AND answer_group = '0' AND answer_key = '{}'".format(match_type.name, entry.key))
            # if result1[-1]:
            #     result1 = result1[0][0]
            # if result2[-1]:
            #     result2 = result2[0][0]
            # # print(result2,result1)
            # if entry.match(msg, match_type, to_me) and (result2 == 1 or result1 == 1):
            if entry.match(msg, match_type, to_me):
                return entry.get_values()
        return []

    def set(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        value: Message,
        require_to_me: bool = False,
    ) -> bool:
        """
        :说明: `set`
        > 新增词条

        :参数:
          * `index: str`: 为0时是全局词库
          * `match_type: MatchType`: 匹配方式\n
                MatchType.congruence: 全匹配(==)
                MatchType.include: 模糊匹配(in)
                MatchType.regex: 正则匹配(regex)
          * `key: Message`: 需要匹配的消息
          * `value: Message`: 触发后发送的短语

        :可选参数:
          * `require_to_me: bool = False`: 匹配 @bot

        :返回:
          - `bool`: 是否新增成功
        """
        name = match_type.name
        add = False
        # print(key)
        # key = Message(str(value).replace('"','！'))
        # 如果为正则词条，检查是否为纯文本，否则抛出异常
        if match_type == MatchType.regex:
            for i in key:
                if i.type != "text":
                    raise IncludeCQCodeError("正则词条只能包含纯文本")

        if index in self.__data[name]:
            for entry in self.__data[name][index]:
                # print("entry:{}".format(entry))
                # print("name:{},index:{}".format(name,index))
                if entry.require_to_me != require_to_me:
                    continue
                if compare_msg(entry.key, key):
                    # print("key:{}".format(key))
                    entry.add_value(value)
                    key, value = entry.dump()
                    print("answer test,key:{},value:{}".format(key, value))
                    dbcontrol_ans('UPDATE answer_ans SET answer_key="{}",answer_answer = "{}" WHERE answer_type="{}" AND answer_group = "{}" AND answer_key="{}"'.format(key,value,name,index,key))
                    add = True
                    break
        else:
            self.__data[name][index] = []
            dbcontrol_ans("INSERT INTO answer (answer_type,answer_group) values ('{}','{}')".format(name,index))
        if not add:
            self.__data[name][index].append(WordEntry(key, [value], require_to_me))
            key,value = WordEntry(key, [value], require_to_me).dump()
            print("answer first,key:{},value:{}".format(key, value))
            dbcontrol_ans('INSERT INTO answer_ans (answer_type,answer_group,answer_key,answer_answer) values ("{}","{}","{}","{}")'.format(name, index,key,value))
        # self.__save()
        return True


    def set_nomessage(
        self,
        index: str,
        match_type: str,
        key: str,
        value: str,
        require_to_me: bool = False,
    ) -> bool:
        name = match_type
        add = False
        # print(key)
        # key = Message(str(value).replace('"','！'))
        # 如果为正则词条，检查是否为纯文本，否则抛出异常
        if match_type == "regex":
            for i in key:
                if i.type != "text":
                    raise IncludeCQCodeError("正则词条只能包含纯文本")

        if index in self.__data[name]:
            for entry in self.__data[name][index]:
                # print("entry:{}".format(entry))
                # print("name:{},index:{}".format(name,index))
                if entry.require_to_me != require_to_me:
                    continue

                if compare_msg(entry.key, key):
                    # print("key:{}".format(key))
                    entry.add_value(value)
                    key, value = entry.dump()
                    print("answer test,key:{},value:{}".format(key, value))
                    dbcontrol_ans('UPDATE answer_ans SET answer_key="{}",answer_answer = "{}" WHERE answer_type="{}" AND answer_group = "{}"'.format(key,value,name,index))
                    add = True
                    break
        else:
            self.__data[name][index] = []
            dbcontrol_ans("INSERT INTO answer (answer_type,answer_group) values ('{}','{}')".format(name,index))
        if not add:
            self.__data[name][index].append(WordEntry(key, [value], require_to_me))
            key,value = WordEntry(key, [value], require_to_me).dump()
            print("answer first,key:{},value:{}".format(key, value))
            dbcontrol_ans('INSERT INTO answer_ans (answer_type,answer_group,answer_key,answer_answer) values ("{}","{}","{}","{}")'.format(name, index,key,value))
        # self.__save()
        return True



    def set_exam(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        value: Message,
        require_to_me: bool = False,
    ) -> bool:
        name = match_type.name
        add = False
        # 如果为正则词条，检查是否为纯文本，否则抛出异常
        if match_type == MatchType.regex:
            for i in key:
                if i.type != "text":
                    raise IncludeCQCodeError("正则词条只能包含纯文本")

        if index in self.__exam[name]:
            for entry in self.__exam[name][index]:
                if entry.require_to_me != require_to_me:
                    continue
                if compare_msg(entry.key, key):
                    entry.add_value(value)
                    key, value = entry.dump()
                    add = True
                    break
        else:
            self.__exam[name][index] = []
            # dbcontrol_ans("INSERT INTO answer (answer_type,answer_group) values ('{}','{}')".format(name,index))
        if not add:
            self.__exam[name][index].append(WordEntry(key, [value], require_to_me))
            # key,value = WordEntry(key, [value], require_to_me).dump()
            # print("answer first,key:{},value:{}".format(key, value))
            # dbcontrol_ans('INSERT INTO answer_exam (answer_type,answer_group,answer_key,answer_answer) values ("{}","{}","{}","{}")'.format(name, index,key,value))
        # self.__save()
        return True


    def select(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        require_to_me: bool = False,
    ) -> List[WordEntry]:
        """
        :说明: `select`
        > 获取词条

        :参数:
          * `index: str`: 为0时是全局词库
          * `match_type: MatchType`: 匹配方式\n
                MatchType.congruence: 全匹配(==)
                MatchType.include: 模糊匹配(in)
                MatchType.regex: 正则匹配(regex)

        :可选参数:
          * `require_to_me: bool = False`: 匹配 @bot

        :返回:
          - `list`: 获取到的词条
        """
        return [
            entry
            for entry in list(self.__data[match_type.name].get(index, []))
            if entry.require_to_me == require_to_me
            and (not key or compare_msg(entry.key, key))
        ]

    def select_exam(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        require_to_me: bool = False,
    ) -> List[WordEntry]:
        return [
            entry
            for entry in list(self.__exam[match_type.name].get(index, []))
            if entry.require_to_me == require_to_me
            and (not key or compare_msg(entry.key, key))
        ]


    def delete(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        require_to_me: bool = False,
    ) -> bool:
        """
        :说明: `delete`
        > 删除词条

        :参数:
          * `index: str`: 为0时是全局词库
          * `match_type: MatchType`: 匹配方式\n
                MatchType.congruence: 全匹配(==)
                MatchType.include: 模糊匹配(in)
                MatchType.regex: 正则匹配(regex)
          * `key: Message`: 触发短语

        :可选参数:
          * `require_to_me: bool = False`: 匹配 @bot

        :返回:
          - `bool`: 是否删除成功
        """
        name = match_type.name
        for entry in list(self.__data[name].get(index, [])):
            if entry.require_to_me != require_to_me:
                continue
            if compare_msg(entry.key, key):
                text = entry.get_values()
                # text_str = str(text[0])
                for text_str in text:
                    text_str = str(text_str)
                    k = 0
                    n = text_str.count("file:///")
                    if n != 0:
                        for i in range(n):
                            path2 = text_str.find(".image", k)
                            if path2 != -1:
                                path1 = text_str.find("file:///", k)
                                img_path = Path(text_str[path1 + 8:path2 + 6])
                                if img_path.is_file():
                                    img_path.unlink()
                                    if not img_path.is_file():
                                        logger.info("成功删除对应图片文件")
                                k = path2 + 6
                            else:
                                logger.info("不存在对应图片文件")
                self.__data[name][index].remove(entry)
                # print(entry.key)
                dbcontrol_ans("DELETE FROM answer_ans WHERE answer_type = '{}' AND answer_group = '{}' AND answer_key = '{}'".format(name,index,entry.key))
                # self.__save()
                return True
        return False

    def delete_exam(
            self,
            index: str,
            match_type: MatchType,
            key: Message,
            id,
            require_to_me: bool = False,
            ifdeletepicture = True
    ) -> bool:
        name = match_type.name
        for entry in list(self.__exam[name].get(index, [])):
            if entry.require_to_me != require_to_me:
                continue
            if compare_msg(entry.key, key):
                text = entry.get_values()
                # text_str = str(text[0])
                if ifdeletepicture:
                    for text_str in text:
                        text_str = str(text_str)
                        k = 0
                        n = text_str.count("file:///")
                        if n != 0:
                            for i in range(n):
                                path2 = text_str.find(".image", k)
                                if path2 != -1:
                                    path1 = text_str.find("file:///", k)
                                    img_path = Path(text_str[path1 + 8:path2 + 6])
                                    if img_path.is_file():
                                        img_path.unlink()
                                        if not img_path.is_file():
                                            logger.info("成功删除对应图片文件")
                                    k = path2 + 6
                                else:
                                    logger.info("不存在对应图片文件")
                self.__exam[name][index].remove(entry)
                # print(entry.key)
                dbcontrol_ans("DELETE FROM answer_exam WHERE _id = {}".format(id))
                # self.__save()
                return True
        dbcontrol_ans("DELETE FROM answer_exam WHERE _id = {}".format(id))
        return False


    def close(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        require_to_me: bool = False,
    ) -> bool:
        name = match_type.name
        for entry in list(self.__data[name].get(index, [])):
            if entry.require_to_me != require_to_me:
                continue
            if compare_msg(entry.key, key):
                # text = entry.get_values()
                self.__data[name][index].remove(entry)
                # print(entry.key)
                dbcontrol_ans("UPDATE answer_ans SET answer_use=0 WHERE answer_type = '{}' AND answer_group = '{}' AND answer_key = '{}'".format(name,index,entry.key))
                # self.__save()
                return True
        return False


    def open(
        self,
        index: str,
        match_type: MatchType,
        key: Message,
        require_to_me: bool = False,
    ) -> bool:
        name = match_type.name
        key = str(key)
        # print("hello4")
        try:
            # print("hello5")
            dataitmes = dbcontrol_tuple("SELECT answer_key,answer_answer FROM answer_ans WHERE answer_type = '{}' AND answer_group = '{}' AND answer_use = 0 AND answer_key = '{}'".format(match_type.name,index,key))
            # print(dataitmes)
            dataitmes = dataitmes[0]
            for key, value in dataitmes:
                # print("key:{},value:{}".format(key,value))
                self.__data[match_type.name][index].append(WordEntry.load(key, value))
                # print(self.__data[t.name][user_id][0].key)
            dbcontrol_ans("UPDATE answer_ans SET answer_use=1 WHERE answer_type = '{}' AND answer_group = '{}' AND answer_key = '{}'".format(match_type.name,index,key))
            return True
        except:
            return False



    def clear(self, index: str) -> bool:
        """
        :说明: `clear`
        > 清空词库

        :参数:
          * `index: str`: 为0时是全局词库, 为空时清空所有词库

        :返回:
          - `bool`: 是否清空成功
        """
        if index is None:
            self.__data = NULL_BANK
            dbcontrol_ans("DELETE FROM answer_ans")
        else:
            for type_ in MatchType:
                name = type_.name
                if index in self.__data[name]:
                    del self.__data[name][index]
                    dbcontrol_ans("DELETE FROM answer_ans WHERE answer_type = '{}' AND answer_group = '{}'".format(name,index))
        # self.__save()
        return True

    def keys(self, index: str, match_type: MatchType) -> List[Message]:
        """
        :说明: `keys`
        > 获取词库的触发短语列表

        :参数:
          * `index: str`: 为0时是全局词库
          * `match_type: MatchType`: 匹配方式\n
                MatchType.congruence: 全匹配(==)
                MatchType.include: 模糊匹配(in)
                MatchType.regex: 正则匹配(regex)

        :返回:
          - `List[Message]`: 触发短语列表
        """
        name = match_type.name
        keys: List[Message] = []
        for entry in self.__data[name][index]:
            keys.append(entry.get_key())
        return keys


word_bank = WordBank()
