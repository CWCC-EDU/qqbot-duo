"""Light QQ-style chat capture using regular Windows UI fonts."""
from io import BytesIO
from functools import lru_cache
from qqbot_media import lossless_png,render_mode
from pathlib import Path
import re
from PIL import Image,ImageDraw,ImageFont,ImageOps


@lru_cache(maxsize=16)
def font(size):
    candidates=[Path('C:/Windows/Fonts/msyh.ttc'),Path('C:/Windows/Fonts/msyh.ttf'),Path('C:/Windows/Fonts/simsun.ttc')]
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent/'runtime/rollpig-addons/nonebot_plugin_rollpig_plus/resource/fonts/SourceHanSansSC-Medium.otf')
    for path in candidates:
        if path.is_file():return ImageFont.truetype(str(path),size)
    raise ValueError('没有找到默认中文字体，请检查Windows字体或运行环境。')


def clip(draw,text,chosen,width):
    text=re.sub(r'[\r\n\t]',' ',str(text or ''))
    if draw.textlength(text,font=chosen)<=width:return text
    while text and draw.textlength(text+'…',font=chosen)>width:text=text[:-1]
    return text+'…'


def render_chat(text,author,avatar=None,metadata=None):
    if render_mode()=='旧版':
        from .._legacy_media.chat_card import render_chat as original
        return original(text,author,avatar,metadata)
    text=str(text).replace('\r\n','\n').replace('\r','\n')
    if not text.strip():raise ValueError('回复的文字是空的，换一条吧。')
    if len(text)>3000:raise ValueError('这条文字太长了，选一条3000字以内的消息吧。')
    if not avatar:raise ValueError('头像尚未取得，这条没有保存。')
    metadata=metadata or {};body=font(43);namefont=font(31);titlefont=font(42);badgefont=font(26)
    measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
    lines=[]
    for paragraph in text.split('\n'):
        current=''
        for char in paragraph:
            if current and measure.textlength(current+char,font=body)>750:lines.append(current);current=''
            current+=char
        lines.append(current)
    bubble_width=max(215,int(max((measure.textlength(line,font=body) for line in lines),default=0))+62)
    message_bottom=235+len(lines)*60+25
    footer_top=max(370,message_bottom+40);height=footer_top+150
    if height>8500:raise ValueError('这条消息换行太多了，选一条短一点的吧。')
    canvas=Image.new('RGB',(1080,height),(239,239,239));draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,0,1080,140),fill='white')
    draw.line([(71,44),(45,69),(71,94)],fill=(28,28,28),width=5)
    group_name=metadata.get('群名') or ('群聊 '+str(metadata.get('群号',''))).strip()
    members=metadata.get('群人数')
    if type(members) is int:group_name+='('+str(members)+')'
    draw.text((108,34),clip(draw,group_name,titlefont,790),font=titlefont,fill=(28,28,28))
    for y in (49,68,87):draw.line((978,y,1023,y),fill=(32,32,32),width=5)
    # Actual snapshot avatar, no letter-placeholder success branch.
    with Image.open(BytesIO(avatar)) as photo:
        photo=ImageOps.fit(ImageOps.exif_transpose(photo).convert('RGB'),(112,112))
        mask=Image.new('L',(112,112));ImageDraw.Draw(mask).ellipse((0,0,111,111),fill=255)
        canvas.paste(photo,(32,166),mask)
    x=170
    role=metadata.get('身份')
    badges=[]
    if role=='群主':badges.append(('群主',(241,177,63)))
    elif role=='管理员':badges.append(('管理员',(72,205,185)))
    special=metadata.get('专属头衔')
    if special:badges.append((clip(draw,special,badgefont,156),(145,174,214)))
    level=metadata.get('群等级')
    if level and str(level).isdigit():badges.append((str(level)+'级',(143,184,220)))
    for label,color in badges:
        width=int(draw.textlength(label,font=badgefont))+22
        if x+width>670:break
        draw.rounded_rectangle((x,165,x+width,207),radius=8,fill=color)
        draw.text((x+11,167),label,font=badgefont,fill='white');x+=width+12
    draw.text((x,165),clip(draw,author,namefont,1030-x),font=namefont,fill=(134,134,134))
    right=min(1033,170+bubble_width)
    draw.rounded_rectangle((170,235,right,message_bottom),radius=29,fill='white')
    draw.polygon([(175,254),(156,269),(175,283)],fill='white')
    for i,line in enumerate(lines):draw.text((200,246+i*60),line,font=body,fill=(24,24,24))
    # Familiar chat controls are visual decoration, never an interactive input.
    draw.rectangle((0,footer_top,1080,height),fill=(249,249,249))
    top=footer_top+28;bottom=height-24
    draw.rounded_rectangle((137,top,871,bottom),radius=31,fill='white')
    cy=footer_top+76
    draw.rounded_rectangle((65,cy-34,86,cy+13),radius=10,outline=(35,35,35),width=4)
    draw.arc((52,cy-5,99,cy+30),0,180,fill=(35,35,35),width=4)
    draw.line((75,cy+30,75,cy+45),fill=(35,35,35),width=4)
    draw.ellipse((901,cy-28,957,cy+28),outline=(35,35,35),width=4)
    for eye in (918,939):draw.line((eye,cy-13,eye,cy-4),fill=(35,35,35),width=4)
    draw.arc((917,cy-9,942,cy+15),0,180,fill=(35,35,35),width=3)
    draw.ellipse((987,cy-28,1043,cy+28),outline=(35,35,35),width=4)
    draw.line((1015,cy-16,1015,cy+16),fill=(35,35,35),width=4)
    draw.line((999,cy,1031,cy),fill=(35,35,35),width=4)
    return lossless_png(canvas)
