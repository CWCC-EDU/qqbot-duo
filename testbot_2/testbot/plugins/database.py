# -*- coding = utf-8 -*-
# @Time : 2022/7/28 11:07
# @Author : CCW
# @File : database.py.py
# @Software : PyCharm
import datetime
import json
import sqlite3
from datetime import date

from nonebot import get_bot


async def dbcontrol(control, dir="user.db"):
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


async def givecollection(user_id, user_get,if_can_reget = False):
    # print("hello")
    date = datetime.date.today().strftime("%Y%m%d")
    noexist = 0
    user_collection = await dbcontrol('SELECT user_collection FROM user_collection WHERE user_id = {}'.format(user_id))
    # print(user_collection)
    if user_collection[-1]:
        # print(user_collection[0][0][0])
        collection_dict = eval(user_collection[0][0][0])
        collection_id = await dbcontrol(
            'SELECT collection_id FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(
                user_get, user_get), "collection.db")
        # print("collechion_id:{}".format(collection_id))
        if collection_id[-1]:
            collection_id = collection_id[0][0][0]
            collection_num = str(collection_id) + "number"
            collection_day = str(collection_id) + "day"
            collection_exist = collection_dict.get(collection_num)
            # print("collechion_exist:{}".format(collection_exist))
            if collection_exist and if_can_reget:
                collection_dict[collection_num] = collection_exist + 1
            else:
                if not collection_exist:
                    noexist = 1
                collection_dict[collection_num] = 1
                collection_dict[collection_day] = date
            # collection_dict = str(collection_dict)
            collection_dict = json.dumps(collection_dict)
            await dbcontrol(
                r"UPDATE user_collection SET user_collection = '{}' WHERE user_id={}".format(collection_dict, user_id))
            return noexist
        else:
            return -1
    else:
        collection_dict = dict()
        collection_id = await dbcontrol(
            'SELECT collection_id FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(
                user_get, user_get), "collection.db")
        if collection_id[-1]:
            collection_id = collection_id[0][0][0]
            # print(collection_id)
            collection_num = str(collection_id) + "number"
            collection_day = str(collection_id) + "day"
            collection_exist = collection_dict.get(collection_num)
            if collection_exist and if_can_reget:
                collection_dict[collection_num] = collection_exist + 1
            else:
                if not collection_exist:
                    noexist = 1
                collection_dict[collection_num] = 1
                collection_dict[collection_day] = date
            # print(collection_dict)
            collection_dict = json.dumps(collection_dict)
            # print(collection_dict)
            await dbcontrol(r"INSERT INTO user_collection (user_id,user_collection) values ({},'{}')".format(user_id,
                                                                                                             collection_dict))
            return noexist
        else:
            return -1


async def getcollection(user_id, user_get,if_can_reget = False):
    result = await  givecollection(user_id, user_get,if_can_reget)
    # print(result)
    print(result,if_can_reget)
    if result == 1 or if_can_reget:
        print("hello")
        try:
            collection_say = await dbcontrol(
                'SELECT collection_get FROM collection WHERE collection_name = "{}" OR collection_nickname = "{}"'.format(
                    user_get, user_get), "collection.db")
            collection_say = collection_say[0][0][0]
            return collection_say
        except:
            pass
    else:
        return False


async  def increaselike(user_id,user_increase):
    try:
        # print(user_id,user_increase)
        nickname = await  get_bot().get_stranger_info(user_id=user_id)
        nickname = nickname["nickname"]
        # print(nickname)
        if nickname:
            result = await dbcontrol(r"SELECT user_like FROM user_sign WHERE user_id = {}".format(user_id))
            # print(result)
            if result[-1]:
                user_like = result[0][0][0]
                await dbcontrol(r"UPDATE user_sign SET user_like={} WHERE user_id={}".format(user_like+user_increase,user_id))
                # await givelike.finish("为{}增加了{}好感！".format(nickname,user_increase))
            else:
                await dbcontrol(r"INSERT INTO user_sign (user_id,user_like) values ({},{})".format(user_id,user_increase))
                # await givelike.finish("为{}增加了{}好感！".format(nickname, user_increase))
        else:
            # await givelike.finish("您真的输对qq号了吗")
            pass
    except:
        pass