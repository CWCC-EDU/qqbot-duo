"""User-facing switch summaries; diagnostics remain in the ledger and logs."""
from .config import config_manager

async def switch_status(a,event,kind='智能'):
    cfg=await a.db('settings',event.group_id)
    cloud,configured,_=await a.cloud.status()
    learning=config_manager.config.total_enable and config_manager.get_group_config(event.group_id).enable
    smart=cfg['enabled'] and learning
    why=('聊天还关着' if not cfg['enabled'] else '本群学说话还关着' if not learning else
         '云聊还关着' if not cfg['cloud_enabled'] else '还没连好' if not configured or not cloud or not cloud['enabled'] else
         '现在是安静模式' if cfg['mode']=='安静' else '')
    auto='开' if cfg['autonomous_enabled'] else '关'
    if cfg['autonomous_enabled'] and why:auto+='（'+why+'）'
    lines=['聊天：'+('开' if cfg['enabled'] else '关'),'云聊：'+('开' if cfg['cloud_enabled'] else '关'),'主动接话：'+auto]
    if kind=='云聊' and cfg['cloud_enabled']:
        if not smart:lines.append('聊天这边还没开。')
        elif not configured or not cloud or not cloud['enabled']:lines.append('还没连好，让超管看看吧。')
        else:
            last=await a.cloud.db('latest',event.self_id,event.group_id)
            if last and last[0] in ('timeout','network','unavailable','http_429'):lines.append('刚才没连上，稍后再试。')
            elif last and last[0] in ('http_401','http_402','http_403','config'):lines.append('暂时用不了，让超管看看吧。')
            elif last and last[0] in ('budget','quota','auto_quota'):lines.append('这会儿先歇一歇。')
    return '\n'.join(lines)
