"""Small parameterized transactions shared by manual collection/affinity controls."""
import ast
import datetime
import json
from pathlib import Path
import sqlite3
from contextlib import closing

def connect(path):
    con=sqlite3.connect(str(path),timeout=5)
    con.row_factory=sqlite3.Row
    return con

def decode_owned(raw):
    try:value=json.loads(raw)
    except (ValueError,TypeError):
        try:value=ast.literal_eval(raw)
        except (ValueError,SyntaxError,TypeError):raise ValueError('藏品记录无法读取，请让超管检查原数据。')
    if not isinstance(value,dict):raise ValueError('藏品记录格式有误，请让超管检查原数据。')
    return value

def catalog(path=Path('database/collection.db')):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('SELECT collection_id,collection_name,collection_nickname,collection_introduction,collection_get FROM collection ORDER BY collection_id')]

def owned(user_id,path=Path('database/user.db')):
    with closing(connect(path)) as con:
        row=con.execute('SELECT user_collection FROM user_collection WHERE user_id=? ORDER BY _id LIMIT 1',(user_id,)).fetchone()
        return decode_owned(row[0]) if row else {}

def find_collection(name,items):
    matches=[r for r in items if name in (r['collection_name'],r['collection_nickname'],str(r['collection_id']))]
    if len(matches)!=1:raise ValueError('没找到唯一对应的藏品，请使用完整名称或编号。')
    return matches[0]

def create_collection(name,alias,introduction,reward,path=Path('database/collection.db')):
    if not name.strip() or len(name)>60 or len(alias)>60 or len(introduction)>600 or len(reward)>300:
        raise ValueError('名称和别名最多60字，介绍最多600字，获得文案最多300字。')
    con=connect(path)
    try:
        con.execute('BEGIN IMMEDIATE')
        keys={r[0] for r in con.execute('SELECT collection_name FROM collection UNION SELECT collection_nickname FROM collection')} - {''}
        if name in keys or (alias and alias in keys):raise ValueError('这个名称或别名已经有藏品在用，未覆盖原藏品。')
        ident=con.execute('SELECT COALESCE(MAX(collection_id),0)+1 FROM collection').fetchone()[0]
        con.execute('INSERT INTO collection(collection_id,collection_name,collection_nickname,collection_introduction,collection_get) VALUES(?,?,?,?,?)',(ident,name,alias,introduction,reward))
        con.commit();return ident
    finally:con.close()

def grant_collection(user_id,name,quantity=1,user_path=Path('database/user.db'),catalog_path=Path('database/collection.db')):
    if not 1<=quantity<=999:raise ValueError('每次发放数量请填1～999。')
    item=find_collection(name,catalog(catalog_path));key=str(item['collection_id'])
    con=connect(user_path)
    try:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT user_collection FROM user_collection WHERE user_id=? ORDER BY _id LIMIT 1',(user_id,)).fetchone()
        data=decode_owned(row[0]) if row else {}
        count=int(data.get(key+'number',0))+quantity
        data[key+'number']=count
        data.setdefault(key+'day',datetime.date.today().strftime('%Y%m%d'))
        raw=json.dumps(data,ensure_ascii=False)
        if row:con.execute('UPDATE user_collection SET user_collection=? WHERE user_id=?',(raw,user_id))
        else:con.execute('INSERT INTO user_collection(user_id,user_collection) VALUES(?,?)',(user_id,raw))
        con.commit();return item,count
    finally:con.close()

def adjust_affinity(user_id,delta,group_id=0,path=Path('database/user.db')):
    if not 1<=user_id<=999999999999 or not -1000000000<=delta<=1000000000 or delta==0:
        raise ValueError('请填写有效账号和1～1000000000之间的整数。')
    con=connect(path)
    try:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT user_like FROM user_sign WHERE user_id=? ORDER BY _id LIMIT 1',(user_id,)).fetchone()
        before=int(row[0] or 0) if row else 0;after=before+delta
        if row:con.execute('UPDATE user_sign SET user_like=? WHERE user_id=?',(after,user_id))
        else:con.execute('INSERT INTO user_sign(user_id,user_like,user_sign_group) VALUES(?,?,?)',(user_id,after,group_id))
        con.commit();return before,after
    finally:con.close()
