# -*- coding = utf-8 -*-
# @Time : 2024/5/29 20:09
# @Author : CCW
# @File : img_maker.py
# @Software : PyCharm
import string
import os

from PIL import Image, ImageDraw, ImageFont


def img_maker(player1_msg,player2_msg,player1_blood,player2_blood,index,choice_msg,font_path = r"C:\Windows\Fonts\msyh.ttc",save_path = None,group = 0 ):

    image = Image.new("RGB", (800, 750), "white")
    draw = ImageDraw.Draw(image)

    # 加载字体
    font_path = font_path   # Windows系统字体路径
    font_size = 20
    font = ImageFont.truetype(font_path, font_size)

    # player1_info = player1_msg.strip().split("\n")
    # player2_info = player2_msg.strip().split("\n")
    # choice_info = choice_msg.strip().split("\n")
    player1_info = player1_msg
    player2_info = player2_msg
    choice_info = choice_msg
    # print(choice_info)

    # 颜色映射字典
    color_map = {
        "普通": "black",
        "水": "blue",
        "火": "red",
        "草": "green",
        "暗": "purple",
        "光": "gold",
        "？": "pink",
        "无": "black",
        "疲惫": "gray",
        "防御": "yellow",
        "流血": "darkred",
        "顽强": "darkgreen",
        "荆棘": "darkolivegreen",
        "易伤": "orange",
        "混乱": "darkorchid",
        "时滞": "dodgerblue",
        "迷惑": "lightcoral",
        "失明": "darkslategray"
    }

    # 上半部分：双方状态
    # 玩家1信息
    # player1_info = [
    #     "孜然刺猬鸽:",
    #     "剩余血量:525",
    #     "当前属性:暗",
    #     "攻击等级:-1",
    #     "命中值:105.0%",
    #     "当前状态:无"
    # ]
    player1_box = [50, 100, 400, 300]
    draw.rectangle(player1_box, outline="black")  # 玩家1方框
    y_offset = player1_box[1] + 10
    for line in player1_info:
        # 检查是否超出边界
        line_bbox = draw.textbbox((player1_box[0] + 10, y_offset), line, font=font)
        if line_bbox[2] > player1_box[2] - 10:  # 超出边界
            line = line[:max(0, (player1_box[2] - player1_box[0] - 60) // font_size)]
            draw.text((player1_box[0] + 10, y_offset), line, fill="black", font=font)
        else:
            draw.text((player1_box[0] + 10, y_offset), line, fill="black", font=font)
        for word, color in color_map.items():
            if word in line and not line.startswith(tuple(["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."])):  # 数字开头的行不替换颜色
                x = line.find(word)
                char_offset = 0
                if x != -1:
                    for char in line[1:x+1]:
                        char_width = font.getbbox(char)[-2]
                        if char.encode().isalpha() or char.isdigit() or char in string.punctuation:  # 判断是否是英文字符
                            char_offset += char_width  # 半角字符增加10像素
                        else:
                            char_offset += char_width
                    draw.text((player1_box[0] + 10 + char_offset, y_offset), word, fill=color, font=font)
        y_offset += (font_size+10)

    # 玩家2信息
    # player2_info = [
    #     "西风漂流:",
    #     "剩余血量:448",
    #     "当前属性:光",
    #     "攻击等级:0",
    #     "命中值:75.0%",
    #     "当前状态:无"
    # ]
    player2_box = [400, 100, 750, 300]
    draw.rectangle(player2_box, outline="black")  # 玩家2方框
    y_offset = player2_box[1] + 10
    for line in player2_info:
        # 检查是否超出边界
        line_bbox = draw.textbbox((player2_box[0] + 10, y_offset), line, font=font)
        if line_bbox[2] > player2_box[2] - 10:  # 超出边界
            line = line[:max(0, (player2_box[2] - player2_box[0] - 60) // font_size)]
            draw.text((player2_box[0] + 10, y_offset), line, fill="black", font=font)
        else:
            draw.text((player2_box[0] + 10, y_offset), line, fill="black", font=font)
        for word, color in color_map.items():
            if word in line and not line.startswith(tuple(["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."])):  # 数字开头的行不替换颜色
                x = line.find(word)
                if x != -1:
                    char_offset = 0
                    for char in line[1:x+1]:
                        char_width = font.getbbox(char)[-2]
                        if char.encode().isalpha() or char.isdigit() or char in string.punctuation:  # 判断是否是英文字符
                            char_offset += char_width  # 半角字符增加10像素
                        else:
                            char_offset += char_width
                    draw.text((player2_box[0] + 10 + char_offset, y_offset), word, fill=color, font=font)
        y_offset += (font_size+10)


    index = index
    ind = f"回合数：{index}"
    draw.text((350, 300), ind, fill="black", font=font)

    # 绘制玩家1的血量条
    player1_health = player1_blood  # 玩家1剩余血量
    player1_bar_width = (player1_health / 600) * 350
    draw.rectangle([50, 50, 50 + player1_bar_width, 100], fill=(139, 0, 0))  # 玩家1血条，颜色为暗红色
    draw.rectangle([50, 50, 400, 100], outline="black")  # 玩家1血条外框
    # 绘制玩家1血量文字
    health_text = f"{player1_health}/600"
    text_bbox = draw.textbbox((50, 50), health_text, font=font)
    text_x = (400 - text_bbox[2]) // 2 + 50  # 居中计算血量文字的x坐标
    text_y = (50 + 150 - text_bbox[3]) // 2
    draw.text((text_x, text_y), health_text, fill="black", font=font)
    # 绘制玩家2的血量条
    player2_health = player2_blood  # 玩家2剩余血量
    player2_bar_width = (player2_health / 700) * 350
    draw.rectangle([400 + (350 - player2_bar_width), 50, 750, 100], fill=(139, 0, 0))  # 玩家2血条，颜色为暗红色
    draw.rectangle([400, 50, 750, 100], outline="black")  # 玩家2血条外框
    # 绘制玩家2血量文字
    health_text = f"{player2_health}/700"
    text_bbox = draw.textbbox((400, 50), health_text, font=font)
    text_x = (750 - text_bbox[2]) // 2 + 400  # 居中计算血量文字的x坐标
    text_y = (50 + 150 - text_bbox[3]) // 2
    draw.text((text_x, text_y), f"{player2_health}/700", fill="black", font=font)

    # 下半部分：选择列表
    # choice_info = [
    #     "0.防御:",
    #     "下回合减伤70%",
    #     "1.赢！:",
    #     "属性：光，伤害：180，效果：提高自己10%命中值",
    #     "2.雪豹闭嘴:",
    #     "属性：暗，伤害：150，效果：降低对手20%命中率，但是降低自己1级攻击",
    #     "3.以此蝶火，斩无不断！！:",
    #     "属性：？，伤害：200，效果：180伤害的大招并给自己添加防御，但有70%的概率对自己造成100伤害，来吧。",
    #     "4.「你的愿望，我收到了」:",
    #     "属性：水，伤害：200，效果：无"
    # ]
    choice_box = [50, 300, 750, 700]
    draw.rectangle(choice_box, outline="black")  # 选择列表外框
    y_offset = choice_box[1] + 10
    for line in choice_info:
        # 检查是否超出边界
        line_bbox = draw.textbbox((choice_box[0] + 10, y_offset), line, font=font)
        if line_bbox[2] > choice_box[2] - 10:  # 超出边界
            index = choice_info.index(line)
            choice_info.insert(index + 1, line[max(0, (choice_box[2] - choice_box[0] - 60) // font_size):])
            line = line[:max(0, (choice_box[2] - choice_box[0] - 60) // font_size)]
        draw.text((choice_box[0] + 10, y_offset), line, fill="black", font=font)
        for word, color in color_map.items():
            if word in line and not line.startswith(tuple(["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."])):  # 数字开头的行不替换颜色
                x = line.find(word)
                if x != -1:
                    char_offset = 0
                    for char in line[1:x+1]:
                        char_width = font.getbbox(char)[-2]
                        if char.encode().isalpha() or char.isdigit() or char in string.punctuation:  # 判断是否是英文字符
                            char_offset += char_width  # 半角字符增加10像素
                        else:
                            char_offset += char_width
                    draw.text((choice_box[0] + 10 + char_offset, y_offset), word, fill=color, font=font)
        y_offset += (font_size+10)



    # 获取当前文件的路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    if not save_path:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_name = f"{group}game.png"
        file_path = os.path.join(current_dir,"pic", file_name)
        image.save(file_path)
    else:
        file_name = f"{group}game.png"
        file_path = os.path.join(save_path, file_name)
        image.save(file_path)
    print(file_path)
    return file_path


