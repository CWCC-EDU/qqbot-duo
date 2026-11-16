"""Explicit operator reset: today's marriage state only, never history."""
from contextlib import closing
import asyncio
from .guards import locks,group_lock,claim_event
reset_lock=asyncio.Lock()

def clear_today(data,limits):
    snapshot={gid:group.model_copy(deep=True) for gid,group in data.groups.items()}
    with limits.lock,closing(limits.connect()) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute("DELETE FROM usage WHERE day=? AND kind='marry'",(limits.day(),))
            db.execute('DELETE FROM cooldown')
            for group in data.groups.values():
                group.couple.clear();group.locked_couple.clear()
                for member in group.members.values():member.today_at_count.clear()
            data.save();db.commit()
        except BaseException:
            db.rollback()
            data.groups.clear();data.groups.update(snapshot)
            data.save()
            raise

async def reset_today(event,data,limits):
    if event.permission!=3:return None
    if not claim_event(event,'operator-reset'):return None
    async with reset_lock:return await _reset(data,limits)

async def _reset(data,limits):
    held=[];taken=set()
    try:
        # Include groups created while waiting for an in-flight marriage. The
        # final snapshot/reset contains no await, so no new roll can interleave.
        while True:
            keys=set(locks)|set(data.groups)
            pending=sorted(str(gid) for gid in keys if str(gid) not in taken)
            if not pending:break
            for gid in pending:
                lock=group_lock(gid);await lock.acquire();held.append(lock);taken.add(gid)
        clear_today(data,limits)
        return '今天的娶群友记录清空啦，可以重新娶了。'
    finally:
        for lock in reversed(held):lock.release()
