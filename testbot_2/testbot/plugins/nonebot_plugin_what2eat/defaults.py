"""Initialize missing menus locally, preserving existing group menus and usage."""
from pathlib import Path
import json,os

FOODS=['炒饭','番茄鸡蛋面','牛肉面','饺子','馄饨','煎饼','鸡腿饭','咖喱饭','麻辣烫','螺蛳粉','米线','盖浇饭','肠粉','三明治','汉堡','披萨','烤鱼','火锅','寿司','凉皮','粥','包子','蒸蛋','蔬菜沙拉']
DRINKS={'家里':['温水','牛奶','豆浆','绿茶','红茶','柠檬水','酸奶','气泡水']}


def write(path,value):
    temporary=path.with_name(path.name+'.defaults-tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)


def initialize_defaults(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    path=root/'eating.json'
    if path.exists():
        try:data=json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):return  # Do not overwrite a hand-edited bad file.
        if not isinstance(data,dict):return
    else:data={}
    changed=False
    if not data.get('basic_food'):
        data['basic_food']=list(FOODS);changed=True
    for key in ('group_food','count'):
        if key not in data:data[key]={};changed=True
    if changed:write(path,data)
    path=root/'drinks.json'
    try:drinks=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):drinks=None
    if not isinstance(drinks,dict) or not any(isinstance(v,list) and v for v in drinks.values()):
        if path.exists() and not path.with_name('drinks.json.before-defaults').exists():
            path.with_name('drinks.json.before-defaults').write_bytes(path.read_bytes())
        write(path,DRINKS)
    path=root/'greetings.json'
    if not path.exists():write(path,{'breakfast':[],'lunch':[],'snack':[],'dinner':[],'midnight':[],'groups_id':{}})
