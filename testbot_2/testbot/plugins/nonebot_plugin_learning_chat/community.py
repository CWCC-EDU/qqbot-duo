"""Group-visible knowledge management and self-controlled conversation profiles."""
import re
from testbot.plugins.persona_utils import load_persona,attack

async def extra_commands(a,event,body,admin):
    gid,uid=event.group_id,event.user_id
    p=load_persona(a.root)
    if body in {'人格','查看人格'}:
        return True,f'我是{p.name}。{p.summary}'
    if body=='画像帮助':
        return True,'本地记录可观察的说话习惯，不鉴定真实性格。\n我的画像 / 我的性格 你的自述\n关闭画像记录 / 开启画像记录 / 清空我的画像\n管理员：群友画像 @群友 / 关闭本群画像记录 / 开启本群画像记录\n学到的知识 / 知识详情 编号\n管理员：确认知识 编号 / 删除知识 编号'
    if body in {'关闭本群画像记录','开启本群画像记录'}:
        if not admin:return True,'只有群主、群管或超管能改本群的记录开关哦。'
        await a.db('set_setting',gid,profile_recording=body.startswith('开启'))
        return True,'这群的聊天习惯'+('开始记录了。' if body.startswith('开启') else '不再记录了。')
    if body in {'关闭画像记录','开启画像记录','清空我的画像'}:
        enabled=body=='开启画像记录'
        await a.record_db('switch',gid,uid,enabled,clear=body=='清空我的画像')
        if body=='清空我的画像':await a.files_call('clear',gid,uid)
        await a.files_call('switch_recording',gid,uid,enabled)
        await a.update_profile(gid,uid)
        return True,('清掉了，也不再继续记录。' if body=='清空我的画像' else ('好，开始记你的聊天习惯。' if enabled else '好，不再记录你的聊天习惯了。'))
    if body.startswith('我的性格'):
        description=body.removeprefix('我的性格').strip()
        if description:
            response=await a.record_db('describe',gid,uid,description)
            await a.update_profile(gid,uid)
            return True,response
        profile=await a.record_db('profile',gid,uid)
        return True,'你的性格/交流偏好自述：'+(profile['description'] or '暂未填写；用 我的性格 喜欢轻松聊天、不喜欢被调侃 设置。')
    if body=='我的画像' or body=='群友画像':
        target=uid
        if body=='群友画像':
            if not admin:return True,'只有群主、群管或超管能看其他群友的互动记录。'
            targets=[int(s.data['qq']) for s in event.message if s.type=='at' and str(s.data.get('qq','')).isdigit() and int(s.data['qq'])!=event.self_id]
            if len(targets)!=1:return True,'用法：群友画像 @一位群友'
            target=targets[0]
        profile=await a.record_db('profile',gid,target)
        habits='、'.join(profile['observations']) or '还没聊够，暂时看不出来'
        topics='、'.join(profile['topics']) or '暂时没记到'
        return True,f"{'你' if target==uid else '该群友'}在本群的互动记录\n记录：{'开启' if profile['enabled'] else '关闭'}；聊天记录{profile['samples']}条\n本人说过的：{profile['description'] or '未填写'}\n说话习惯：{habits}\n常聊主题：{topics}\n只是平时聊天留下的印象。"
    if body=='学到的知识':
        rows=await a.record_db('list_knowledge',gid)
        if not rows:return True,'还没有新的知识记录。'
        lines=[f"{r[0]}｜{r[3]}｜{r[1][:45]}（记录{r[4]}次）" for r in rows]
        return True,'本群最近20条知识记录：\n'+'\n'.join(lines)+'\n详情：知识详情 编号'
    match=re.fullmatch(r'(知识详情|确认知识|删除知识)\s+(\d+)',body)
    if match:
        command,kid=match[1],int(match[2])
        row=await a.record_db('detail',gid,kid)
        if not row:return True,'没找到这条记录，确认一下编号？'
        _,question,answer,status,seen,sources=row
        if command=='知识详情':
            return True,f'知识{kid}｜{status}\n问题：{question}\n回答/资料：{answer}\n观察次数：{seen}\n来源记录：{sources}'
        if not admin:return True,'只有群主、群管或超管能确认或删除本群问答。'
        if command=='确认知识':
            if attack(question) or attack(answer) or not p.output_ok(answer):return True,'这条内容不适合收进问答，先不记了。'
            from .config import config_manager
            words=config_manager.config.ban_words+config_manager.get_group_config(gid).ban_words
            if any(word and word in question+answer for word in words):return True,'里面有本群屏蔽的词，这条先不记了。'
            result=await a.db('teach',gid,uid,question,answer,event.time)
            if not result.startswith('记住'):return True,result
            await a.record_db('learn',gid,uid,event.message_id,question,answer,True,'管理员确认');a.group(gid).index=None
            return True,'这条记下了。'
        await a.record_db('change',gid,kid,'已删除')
        entries=await a.db('entries',gid)
        if any(e.question==question and e.answer==answer for e in entries):await a.db('forget_qa',gid,question)
        a.group(gid).index=None
        return True,'这条知识和对应问答都停用了。'
    return False,None
