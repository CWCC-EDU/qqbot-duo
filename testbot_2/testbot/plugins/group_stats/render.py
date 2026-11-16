from pathlib import Path
from io import BytesIO
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from wordcloud import WordCloud

def font_path():
    for p in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf','C:/Windows/Fonts/simsun.ttc'):
        if Path(p).is_file():return p
    raise RuntimeError('缺少中文字体，请安装微软雅黑或黑体')
def font(size):return ImageFont.truetype(font_path(),size)
def output(image):
    buf=BytesIO();image.save(buf,'PNG',compress_level=3);return buf.getvalue()
def render(data,cloud=True):
    image=Image.new('RGB',(1080,1150 if cloud else 240+58*max(1,len(data['ranking']))),'white');draw=ImageDraw.Draw(image)
    title='群聊词云' if cloud else '群聊发言排行'
    draw.text((540,28),title+' · '+data['label'],fill='#223044',font=font(42),anchor='mt')
    draw.text((540,90),data['start']+' ～ '+data['end'],fill='#657285',font=font(23),anchor='mt')
    draw.text((540,130),f"{data['messages']} 条发言 · {data['members']} 位群友",fill='#657285',font=font(23),anchor='mt')
    if cloud:
        y,x=np.ogrid[:900,:1000];mask=np.where(((x-500)/490)**2+((y-450)/440)**2>1,255,0).astype('uint8')
        cloud=WordCloud(font_path=font_path(),width=1000,height=900,mask=mask,background_color='white',max_words=300,min_font_size=14,max_font_size=180,
            prefer_horizontal=.82,collocations=False,relative_scaling=.45,colormap='viridis',random_state=31,margin=4).generate_from_frequencies(data['words'])
        image.paste(cloud.to_image(),(40,180))
    else:
        maximum=max((n for _,n,_ in data['ranking']),default=1)
        for i,(uid,n,chars) in enumerate(data['ranking'],1):
            y=190+(i-1)*58
            draw.rounded_rectangle((32,y,1048,y+50),radius=9,fill='#f1f6fb')
            draw.rounded_rectangle((32,y,32+max(12,int(1016*n/maximum)),y+50),radius=9,fill='#d4eaf4')
            draw.text((46,y+7),str(i),font=font(27),fill='#24627c')
            draw.text((100,y+7),data['names'][uid][:18],font=font(27),fill='#233442')
            draw.text((1025,y+9),f'{n}条 · {chars}字',font=font(24),fill='#344459',anchor='rt')
    note='记录起始：'+str(data['began'] or '暂无')+'；仅含机器人收到的消息'
    draw.text((25,image.height-42),note,font=font(19),fill='#667385')
    return output(image)
