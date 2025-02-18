import base64
from io import BytesIO

from PIL import Image, ImageFont, ImageDraw
from glob import glob
import random
import textwrap

FONTS = glob("fonts/*")
MIN_FONT_SIZE = 16
MAX_FONT_SIZE = 48
DATA = glob("presets/images/*.json")


def get_font(font_path, size):
    return ImageFont.truetype(font_path, size)


def to_base64(image):
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"


def find_optimal_font_size(text, box_width, box_height, font_path):
    font_size = MAX_FONT_SIZE
    font = get_font(font_path, font_size)

    while font_size > MIN_FONT_SIZE:
        # Подбираем количество символов для переноса
        avg_char_width = sum(font.getlength(char) for char in text) / len(text)
        max_chars = int((box_width * 0.95) / avg_char_width)

        # Разбиваем текст на строки
        lines = textwrap.wrap(text, width=max_chars, break_long_words=True)

        # Проверяем, помещается ли текст
        line_height = font.getbbox("hg")[3]
        total_height = line_height * len(lines)
        max_line_width = max(font.getlength(line) for line in lines)

        if total_height <= box_height * 0.9 and max_line_width <= box_width * 0.95:
            break

        font_size -= 2
        font = get_font(font_path, font_size)

    return font


def draw_text_in_box(draw, text, box, font_path, color):
    # box = (x1, y1, x2, y2)
    width = box[2] - box[0]
    height = box[3] - box[1]

    # Находим оптимальный размер шрифта
    font = find_optimal_font_size(text, width, height, font_path)

    # Подбираем количество символов для переноса
    avg_char_width = sum(font.getlength(char) for char in text) / len(text)
    max_chars = int((width * 0.95) / avg_char_width)

    # Разбиваем текст на строки
    lines = textwrap.wrap(text, width=max_chars, break_long_words=True)

    # Вычисляем общую высоту текста
    line_height = font.getbbox("hg")[3]
    total_height = line_height * len(lines)

    # Вычисляем начальную y-координату для центрирования по вертикали
    y = box[1] + (height - total_height) // 2

    # Рисуем каждую строку
    for line in lines:
        # Получаем ширину линии для центрирования по горизонтали
        line_width = font.getlength(line)
        x = box[0] + (width - line_width) // 2

        draw.text(
            (x, y), line, color, font=font, stroke_width=2, stroke_fill=(255, 255, 255)
        )
        y += line_height
