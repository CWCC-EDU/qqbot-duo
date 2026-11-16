"""按机器人账号和群保存决斗开关，不接触战绩和奖励数据。"""
import copy
import json
import logging
import os
from pathlib import Path
import re
import tempfile

log=logging.getLogger(__name__)

def valid_prefix(value):
    return (isinstance(value,str) and len(value)==1 and value.isprintable()
            and not value.isspace() and not value.isalnum() and value not in '[]')

class GroupSettings:
    def __init__(self,path,prefix='#'):
        self.path=Path(path)
        self.prefix=prefix
        self.defaults={'enabled':True,'collections':True,'invite_prefix':False,'reply_prefix':False}
        self.groups={}
        self.error=''
        if self.path.exists():
            try:
                document=json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(document,dict) or set(document)-{'command_prefix','default_enabled','default_collections','default_invite_prefix','default_reply_prefix','groups'}:
                    raise ValueError('群设置包含未知字段')
                command_prefix=document.get('command_prefix',prefix)
                if not valid_prefix(command_prefix):
                    raise ValueError('指令前缀须为一个可见符号，例如#或反斜杠')
                defaults={'enabled':document.get('default_enabled',True),'collections':document.get('default_collections',True),
                          'invite_prefix':document.get('default_invite_prefix',False),'reply_prefix':document.get('default_reply_prefix',False)}
                groups=document.get('groups',{})
                if any(type(v) is not bool for v in defaults.values()) or not isinstance(groups,dict):
                    raise ValueError('默认开关须为布尔值')
                for key,settings in groups.items():
                    if not isinstance(key,str) or not re.fullmatch(r'\d+:\d+',key) or not isinstance(settings,dict):
                        raise ValueError('群设置键须为机器人账号:群号')
                    if (set(settings)-{'enabled','collections','prefix','invite_prefix','reply_prefix'} or
                        any(type(value) is not bool for option,value in settings.items() if option!='prefix') or
                        ('prefix' in settings and not valid_prefix(settings['prefix']))):
                        raise ValueError('群开关须为布尔值')
                self.prefix,self.defaults,self.groups=command_prefix,defaults,groups
            except Exception as error:
                # A corrupt disabled-group setting must never silently reopen rewards.
                self.defaults={'enabled':False,'collections':False,'invite_prefix':False,'reply_prefix':False}
                self.error=str(error)
                log.exception('决斗群设置损坏，暂时关闭决斗及藏品联动，请管理员检查配置')

    def for_group(self,key):
        return {'prefix':self.prefix,**self.defaults,**self.groups.get('{}:{}'.format(*key),{})}

    def set(self,key,option,value):
        if (option not in ('enabled','collections','prefix','invite_prefix','reply_prefix') or
            (not valid_prefix(value) if option=='prefix' else type(value) is not bool)):
            raise ValueError('无效群设置')
        groups=copy.deepcopy(self.groups)
        groups.setdefault('{}:{}'.format(*key),{})[option]=value
        document={'command_prefix':self.prefix,'default_enabled':self.defaults['enabled'],
                  'default_collections':self.defaults['collections'],
                  'default_invite_prefix':self.defaults['invite_prefix'],'default_reply_prefix':self.defaults['reply_prefix'],'groups':groups}
        temporary=None
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,prefix='duel-settings-',suffix='.tmp',delete=False) as file:
                temporary=file.name
                json.dump(document,file,ensure_ascii=False,indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary,self.path)
        finally:
            if temporary and os.path.exists(temporary):os.unlink(temporary)
        self.groups=groups
        self.error=''
