"""One-picture directory. Detailed prose remains available through text help."""
def compact_sections(name,level,topic,prefix,loaded,owner=False,quote=None,horse=None):
    loaded=set(loaded);quote=quote or {};horse=horse or {};cards=[]
    if topic in ('全部','日常'):
        cards.extend([
            ('签到与运势',['签到 · 当前好感 · 好感位次 · 排行','求签 · 改签 · 赛博硬币','发病 名字 · @我 我爱你']),
            ('群友与词库',['娶群友 · 透群友 · 本群cp · 群友卡池','离婚 · 分手 · 群友设置 · NTR状态','问 问题 答 回答 · 开启/关闭词条 问题']),
            ('表情与瓶子',['表情包制作 · 表情详情 名字','扔瓶子 内容 · 捡瓶子 · 我的瓶子','查看/评论/点赞/举报瓶子 编号']),
        ])
        if 'testforcollection' in loaded:cards.append(('藏品',['藏品列表 · 查看藏品 名称 · 藏品图鉴']))
        if 'nonebot_plugin_morning' in loaded:cards.append(('作息',['早安 · 晚安 · 我的作息 · 群友作息']))
        if 'testforseraphim' in loaded:cards.append(('和菲姆酱玩',['捕捉菲姆酱 · 刷礼物']))
        if 'russian' in loaded:cards.append(('快速决斗',['快速决斗 @群友 → 接受 / 拒绝（随机剧情）']))
    if topic in ('全部','决斗'):
        cards.append(('技能决斗',[
            '发起决斗 @群友 → 接受 / 拒绝',
            f'{prefix}0～{prefix}4 选招 · {prefix}随机 · {prefix}认输',
            f'{prefix}继续 恢复 · {prefix}决斗文字 / {prefix}决斗图片',
            '发起决斗帮助 · 我的战绩 · 胜场排行',
        ]))
        if topic=='决斗':cards.append(('对战要点',['双方轮流行动，选招后更新面板。','伤害、命中、属性特性和状态都会影响战局。','生命归零判负；达到行动上限时比较最终血量。','完整规则：文字帮助 决斗']))
    if topic in ('全部','赛马'):
        if 'nonebot_plugin_horserace' in loaded:cards.append(('赛马',[
            '赛马创建 → 赛马加入 小白 → 赛马开始',
            f"{horse.get('min_player',2)}～{horse.get('max_player',8)}人 · 随机事件 · 赛马帮助",
            f"赛马重置（超时{horse.get('setting_over_time',120)}秒）",
        ]))
        elif topic=='赛马':cards.append(('赛马',['这台没有启用赛马，请找千鸟酱。']))
    if topic in ('全部','小猪'):cards.append(('今日小猪',[
        '今日小猪 · 我的猪圈 · 小猪图鉴',
        '今日烤猪 · 烤群友 @群友 · 随机烤猪',
        '烤箱续火 · 加急生火 @群友',
        '小猪帮助：日报、昨日/明日小猪、找猪等',
    ]))
    if topic=='聊天':cards.append(('三个开关',['智能：聊天总开关','云聊：允许用 DeepSeek 回答','主动接话：没被点名也会参与','开启主动接话会顺带开云聊、切自然模式；智能仍需开启。']))
    if topic in ('全部','聊天'):cards.append(('聊天与记忆',[
        f'@{name} / 叫名字 / 回复我的消息',
        '智能状态 · 云聊状态 · 人格',
        '记住 昵称=小明 · 我的记忆 · 我的画像',
        '学到的知识 · 文字帮助 聊天',
    ]))
    if topic in ('全部','语录'):
        if 'nonebot_plugin_quote' in loaded:
            q=quote.get('prefix','');rows=[('@我后发送：' if quote.get('needat',True) else '')+f'{q}上传（回复图片或文字） · {q}语录 · {q}语录 关键词',f'回复语录图片：{q}标签 / {q}addtag 标签 / {q}deltag 标签']
            if quote.get('can_delete'):rows.append(f'回复图片：{q}删除（你有语录删除权限）')
            if quote.get('fonts_ready'):rows.append(f'回复文字：{q}记录 / {q}生成')
            cards.append(('群聊语录',rows))
        elif topic=='语录':cards.append(('语录',['这台没有启用语录库。']))
    if topic in ('全部','其他'):
        rows=[]
        for plugin,text in [
            ('nonebot_plugin_bread_shop','面包帮助（买/吃/抢/送、猜拳、排行）'),
            ('nonebot_plugin_batarot','塔罗牌 · 占卜 · 塔罗牌解读'),
            ('nonebot_plugin_what2eat','今天吃什么 · 今天喝什么 · 群菜单'),
            ('nonebot_plugin_homo_mathematician','找规律 数字 · 臭数字 数字'),
            ('nonebot_plugin_animalVoice','兽音加密/解密 内容 · 切噜一下 内容'),
            ('nonebot_plugin_person','随个人 · 疯狂星期四'),
            ('nonebot_plugin_crazy_thursday','疯狂星期四' if 'nonebot_plugin_person' not in loaded else ''),
            ('nonebot_plugin_poke','戳一戳 · 抓图 + 图片'),
            ('echo','@我 echo 内容'),
            ('nonebot_plugin_send','.send 内容（向超管反馈）'),
        ]:
            if plugin in loaded and text:rows.append(text)
        if rows:cards.append(('更多玩法',rows))
        automatic=[]
        for plugin,label in [('nonebot_plugin_antiinsult','反嘴臭'),('nonebot_plugin_antirecall','防撤回'),('nonebot_plugin_miao','回复口癖')]:
            if plugin in loaded:automatic.append(label)
        if automatic:cards.append(('自动触发',[' · '.join(automatic)]))
    if topic in ('全部','管理','聊天','小猪','决斗') and level>=1:
        cards.append(('群内管理',[
            '禁言机器人 [时长] · 解除禁言机器人',
            '默认30分钟 · 机器人禁言状态',
            '开启/关闭云聊 · 开启/关闭主动接话',
            '问答概率 10% · 模型分工',
            '开启/关闭群聊上下文 · 清空群聊上下文',
            '开启/关闭NTR · 小猪日报 开启/关闭',
            '设置娶群友上限 次数 · 设置透群友上限 次数',
            f'{prefix}开启/关闭决斗 · {prefix}设置前缀 !',
            '帮助 管理（更多设置：文字帮助 管理）',
        ]))
        if topic=='管理':cards.append(('更多本群设置',['设置离婚等待 分钟（默认120，遇零点刷新）','智能开启/关闭 · 智能模式 安静/自然','智能教学 问题 => 回答 · 智能删除 问题','确认知识 编号 · 群友画像 @群友','查询词库 关键词 · 删除词条 问题',f'{prefix}开启/关闭藏品 · {prefix}邀请前缀 开/关 · {prefix}应答前缀 开/关']))
    if (owner or level>=2) and topic in ('全部','管理') and 'nonebot_plugin_antirecall' in loaded:
        cards.append(('仅群主与超管',['开启/关闭本群防撤回 · 开启/关闭绕过管理层']))
    if level>=2 and topic in ('全部','管理'):
        cards.append(('仅超管',[
            '增加好感 @群友 10 · 减少好感 @群友 10',
            '公告 群号1,群号2 正文 · 公告群列表',
            '云聊用量 · 同步小猪资源',
            '图像模式 快速/旧版 · 每分钟上限 查看',
            '每分钟上限 开/关 · 每分钟上限 次数',
            '全局维护与完整参数：文字帮助 管理',
        ]))
        if 'testforcollection' in loaded:cards.append(('藏品管理 · 仅超管',[
            '授予藏品 @群友 名称 [数量]',
            '新增藏品 名称 | 别名 | 介绍 | 获得文案',
        ]))
        if topic=='管理' and 'nonebot_plugin_horserace' in loaded:cards.append(('赛马维护 · 仅超管',['赛马暂停 · 赛马清空 · 赛马事件重载']))
    if topic=='管理' and level==0:return [('群内管理',['这页留给群主、群管和超管。'])]
    return cards
