"""独立指令前缀及用户提示，不保留会使双机器人同时响应的公共入口。"""
import re

ALIASES={'发起决斗帮助':'帮助','发起决斗':'决斗','决斗文字':'文字','决斗图片':'图片',
         '文字模式':'文字','图片模式':'图片','我的战绩':'战绩','胜场排行':'胜榜','胜利排行':'胜榜',
         '败场排行':'败榜','失败排行':'败榜','重载决斗':'重载','决斗配置':'状态','取消决斗':'取消'}
COMMANDS=('帮助','接受','拒绝','认输','结算','继续','文字','图片','随机','战绩','胜榜','败榜',
          '开启决斗','关闭决斗','开启藏品','关闭藏品','状态','重载','取消','决斗')
COMMANDS=COMMANDS+('设置前缀','邀请前缀','应答前缀')

def format_commands(text,prefix):
    tokens=sorted(set(ALIASES)|set(COMMANDS)|set('01234'),key=len,reverse=True)
    expression=r'#('+'|'.join(map(re.escape,tokens))+r')(?![A-Za-z0-9])'
    if prefix!='#':
        text=re.sub(expression,lambda match:prefix+('发起决斗' if match[1] in ('发起决斗','决斗') else ALIASES.get(match[1],match[1])),text)
        text=re.sub(r'#(?=\s*(?:则|会))',lambda match:prefix+'随机',text)
    for word in ('发起决斗','接受','拒绝','重载决斗','决斗配置','取消决斗'):
        text=text.replace('“'+word+'”','“'+prefix+('发起决斗' if word=='发起决斗' else ALIASES.get(word,word))+'”')
    text=text.replace('我的战绩 / 胜场排行 / 败场排行',prefix+'战绩 / '+prefix+'胜榜 / '+prefix+'败榜')
    text=text.replace('使用 #0～#4', '使用 '+prefix+'0～'+prefix+'4')
    text=text.replace(prefix+'帮助 / '+prefix+'帮助',prefix+'帮助')
    return text
