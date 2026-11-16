"""Serialize pair changes and bind every real roll to durable daily usage."""
import asyncio
from functools import wraps
import logging
import time
from collections import OrderedDict

locks = {}

# Some OneBot reconnects can deliver the same event again. A group lock only
# serializes them; it does not prevent the second roll/usage charge. Claim by
# original message identity before waiting for that lock, never by text/user.
_seen = OrderedDict()
DEDUP_SECONDS = 600
DEDUP_CAPACITY = 8192


def claim_event(event,kind):
    extra=getattr(event,'_extra',None)
    original=extra.get('event') if isinstance(extra,dict) else None
    if original is None:return True  # Non-NoneBot adapters retain their behavior.
    mid=getattr(original,'message_id',None)
    own=getattr(original,'self_id',None)
    if mid is None or str(mid)=='0' or own is None:return True
    key=(str(own),str(event.group_id),str(event.user_id),str(mid),str(getattr(original,'time','')),kind)
    now=time.monotonic()
    while _seen and next(iter(_seen.values()))<=now:
        _seen.popitem(last=False)
    if key in _seen:return False
    _seen[key]=now+DEDUP_SECONDS
    while len(_seen)>DEDUP_CAPACITY:_seen.popitem(last=False)
    return True



def group_lock(group_id):
    return locks.setdefault(str(group_id), asyncio.Lock())


def serialized(function):
    @wraps(function)
    async def wrapped(event, *args, **kwargs):
        async with group_lock(event.group_id):
            return await function(event, *args, **kwargs)
    return wrapped


def limited(kind, data, limits, at_result):
    def decorate(function):
        @wraps(function)
        async def wrapped(event):
            if not claim_event(event,kind):return None
            async with group_lock(event.group_id):
                group = data.group(event.group_id)
                uid = event.user_id
                partner = group.couple.get(uid)
                target = event.at[0] if event.at else None
                charge = True
                if kind == 'marry':
                    # Viewing an existing pair or locked single status does not roll.
                    charge = partner != uid and not (partner and (not target or target in (uid, partner)))
                    if target and target != uid:
                        other = group.couple.get(target)
                        if not group.ntr_enabled and other not in (None, target, uid):
                            charge = False  # The original handler explains the prohibition.
                        elif charge and limits.remaining_wait(event.group_id, target):
                            return at_result(uid, '对方刚解除配对，还要再等一会儿。')
                try:
                    if charge:
                        reason = limits.reserve(event.group_id, uid, kind)
                        if reason:
                            return at_result(uid, reason)
                except Exception:
                    logging.getLogger(__name__).exception('群友次数记录失败，未进行抽取')
                    return at_result(uid, '次数没记上，这次先不抽，等一下再试吧。')
                snapshot = group.model_copy(deep=True)
                try:
                    return await asyncio.wait_for(function(event), timeout=25)
                except Exception:
                    logging.getLogger(__name__).exception('群友玩法执行失败')
                    snapshot.ntr_enabled = data.group(event.group_id).ntr_enabled
                    data.groups[str(event.group_id)] = snapshot
                    try:
                        data.save()
                    except Exception:
                        logging.getLogger(__name__).exception('群友存档回退保存失败')
                    return at_result(uid, '这次没办成，配对没有改变，等一下再试吧。')
        return wrapped
    return decorate
