"""Reply-image/text upload. Shared indexes remain compatible with old commands."""
import asyncio,copy,json,os,uuid
from pathlib import Path
from nonebot.adapters.onebot.v11 import Message
from .chat_card import render_chat
from qqbot_media.quote_archive import Archive
from qqbot_media import render_scoped
from .quote_identity import download,AvatarStore,quoted_identity

LOCK=asyncio.Lock()


def persist(group,path,text,cfg,record,index,forward,offer):
    # Build copies first; callers keep the same dictionary objects, required by
    # legacy tag/query handlers. If saving fails, their in-memory data is intact.
    new_record=copy.deepcopy(record);new_index=copy.deepcopy(index);new_forward=copy.deepcopy(forward)
    new_index,new_forward=offer(group,str(path),text,new_index,new_forward)
    bucket=new_record.setdefault(group,[])
    if str(path) not in bucket:bucket.append(str(path))
    targets=[(Path(cfg.record_path),new_record),(Path(cfg.inverted_index_path),new_index)]
    staged=[];original={}
    try:
        for file,value in targets:
            file.parent.mkdir(parents=True,exist_ok=True)
            original[file]=file.read_bytes() if file.exists() else None
            temporary=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp')
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            staged.append((temporary,file))
        replaced=[]
        try:
            for temporary,file in staged:os.replace(temporary,file);replaced.append(file)
        except BaseException:
            for file in replaced:
                old=original[file]
                if old is not None:file.write_bytes(old)
                else:file.unlink(missing_ok=True)
            raise
        record.clear();record.update(new_record)
        index.clear();index.update(new_index)
        forward.clear();forward.update(new_forward)
    finally:
        for temporary,_ in staged:temporary.unlink(missing_ok=True)


async def add_record(group,path,text,cfg,record,index,forward,offer):
    async with LOCK:
        await asyncio.to_thread(persist,group,path,text,cfg,record,index,forward,offer)


async def save_upload(bot,event,root,cfg,record,index,forward,offer):
    reply=event.reply
    if not reply:raise ValueError('回复图片或纯文字消息，再@我发送“上传”。')
    # Permanent assets are isolated from every disposable image cache.
    root=Archive(Path(__file__).resolve().parents[3],root).folder
    message=Message(reply.message)
    images=[s for s in message if s.type=='image']
    plain=''
    if images:
        if len(images)!=1:raise ValueError('一次选一张图片上传吧。')
        segment=images[0];file=segment.data.get('file');raw=None
        if file:
            try:
                info=await asyncio.wait_for(bot.get_image(file=file),8)
                local=Path(info.get('file',''))
                if local.is_file() and local.stat().st_size<=8_000_000:raw=await asyncio.to_thread(local.read_bytes)
                elif info.get('url'):raw=await download(info['url'])
            except Exception:pass
        if raw is None:
            url=segment.data.get('url') or file
            raw=await download(url)
        # Verify content and normalise extension, without trusting CQ filenames.
        from PIL import Image,ImageOps
        from io import BytesIO
        def normalize():
            with Image.open(BytesIO(raw)) as image:
                if image.width*image.height>30_000_000:raise ValueError('这张图片尺寸太大了。')
                image=ImageOps.exif_transpose(image)
                output=BytesIO();image.save(output,'PNG');return output.getvalue()
        raw=await asyncio.to_thread(normalize)
    else:
        if any(s.type!='text' for s in message):raise ValueError('请回复图片或纯文字消息，其他类型暂时不能存成语录。')
        plain=message.extract_plain_text()
        if not plain.strip():raise ValueError('回复的文字是空的，换一条吧。')
        if len(plain)>3000:raise ValueError('这条文字太长了，选一条3000字以内的消息吧。')
        root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
        metadata,preferred=await quoted_identity(bot,event)
        avatar,provenance=await AvatarStore(root).obtain(reply.sender.user_id,preferred)
        raw=await asyncio.to_thread(render_scoped,render_chat,bot.self_id,event.group_id,plain,metadata['显示名'],avatar,metadata)
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    path=root/('quote-'+uuid.uuid4().hex+'.png')
    assets={path:raw}
    if plain:
        avatar_path=path.with_suffix('.avatar.png')
        metadata.update({'格式版本':1,'文字':plain,'图片文件':path.name,'头像文件':avatar_path.name,'头像来源':provenance})
        assets[avatar_path]=avatar
        assets[path.with_suffix('.json')]=json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf-8')
    # The worker owns rollback, so cancellation cannot remove an indexed image
    # while the disk transaction continues in the background.
    async with LOCK:
        worker=asyncio.create_task(asyncio.to_thread(commit_assets,assets,str(event.group_id),path,plain,cfg,record,index,forward,offer))
        try:await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:await worker
            finally:raise
    return str(path),plain


def commit_assets(assets,group,path,text,cfg,record,index,forward,offer):
    staged=[];written=[]
    try:
        for destination,raw in assets.items():
            temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
            staged.append(temporary)
            temporary.write_bytes(raw)
            os.replace(temporary,destination);written.append(destination)
        persist(group,path,text,cfg,record,index,forward,offer)
    except BaseException:
        for destination in written:destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:temporary.unlink(missing_ok=True)
