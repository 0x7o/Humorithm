import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random
from glob import glob
import os

FONTS = glob("fonts/*")
MIN_FONT_SIZE = 16
MAX_FONT_SIZE = 48


def get_font(font_path, size):
    return ImageFont.truetype(font_path, size)


def find_optimal_font_size(text, box_width, box_height, font_path):
    font_size = MAX_FONT_SIZE
    font = get_font(font_path, font_size)

    while font_size > MIN_FONT_SIZE:
        avg_char_width = sum(font.getlength(char) for char in text) / len(text)
        max_chars = int((box_width * 0.95) / avg_char_width)
        lines = textwrap.wrap(text, width=max_chars, break_long_words=True)

        line_height = font.getbbox("hg")[3]
        total_height = line_height * len(lines)
        max_line_width = max(font.getlength(line) for line in lines)

        if total_height <= box_height * 0.9 and max_line_width <= box_width * 0.95:
            break

        font_size -= 2
        font = get_font(font_path, font_size)

    return font, lines, line_height


def create_text_overlay(
    size, lines, font, line_height, box, color=0, border_color=255, border_width=2
):
    """Создает PNG с прозрачным фоном и текстом"""
    # Создаем прозрачное изображение
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    width = box[2] - box[0]
    height = box[3] - box[1]
    y = box[1] + (height - (line_height * len(lines))) // 2

    for line in lines:
        line_width = font.getlength(line)
        x = box[0] + (width - line_width) // 2
        # Рисуем обводку
        draw.text(
            (x, y),
            line,
            (border_color, border_color, border_color, 255),
            font=font,
            stroke_width=border_width,
        )
        # Рисуем текст
        draw.text((x, y), line, (color, color, color, 255), font=font)
        y += line_height

    return overlay


def process_video_ffmpeg(
    input_path,
    output_path,
    text,
    box,
    font_path,
    compression="medium",
    color=0,
    border_color=255,
    border_width=2,
):
    # Словарь с пресетами сжатия
    compression_presets = {
        "high": {
            "preset": "veryslow",  # Самое медленное кодирование, лучшее сжатие
            "crf": "28",  # Высокое сжатие (диапазон 0-51, чем больше тем сильнее сжатие)
            "maxrate": "1M",  # Максимальный битрейт
            "bufsize": "2M",  # Размер буфера
        },
        "medium": {"preset": "medium", "crf": "23", "maxrate": "2M", "bufsize": "4M"},
        "low": {
            "preset": "fast",  # Быстрое кодирование, меньшее сжатие
            "crf": "18",  # Низкое сжатие, высокое качество
            "maxrate": "4M",
            "bufsize": "8M",
        },
        "ultrafast": {
            "preset": "ultrafast",  # Максимально быстрое кодирование
            "crf": "28",
            "maxrate": "3M",
            "bufsize": "4M",
        },
    }

    # Выбираем пресет сжатия
    comp_settings = compression_presets[compression]
    probe = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_path]
    )
    import json

    info = json.loads(probe)
    width = int(info["streams"][0]["width"])
    height = int(info["streams"][0]["height"])

    # Подготавливаем текст
    font, lines, line_height = find_optimal_font_size(
        text, box[2] - box[0], box[3] - box[1], font_path
    )

    # Создаем оверлей с текстом
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        overlay_path = tmp.name
        overlay = create_text_overlay(
            (width, height),
            lines,
            font,
            line_height,
            box,
            color,
            border_color,
            border_width,
        )
        overlay.save(overlay_path, "PNG")

    # Накладываем текст с помощью FFmpeg
    command = [
        "ffmpeg",
        "-i",
        input_path,
        "-i",
        overlay_path,
        "-filter_complex",
        "[0:v][1:v]overlay=0:0",
        "-c:v",
        "libx264",
        "-preset",
        comp_settings["preset"],
        "-crf",
        comp_settings["crf"],
        "-maxrate",
        comp_settings["maxrate"],
        "-bufsize",
        comp_settings["bufsize"],
        "-movflags",
        "+faststart",  # Позволяет начать воспроизведение до полной загрузки
        "-c:a",
        "aac",  # Сжатие аудио
        "-b:a",
        "128k",  # Битрейт аудио
        "-y",
        output_path,
    ]

    try:
        subprocess.run(command, check=True)
    finally:
        # Удаляем временный файл
        os.unlink(overlay_path)
