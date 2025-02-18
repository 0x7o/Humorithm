import random
import logging
from functools import wraps

import requests
import json
import time
import os
from PIL import Image, ImageDraw
from flask import Flask, request, jsonify, send_from_directory
from image import to_base64, draw_text_in_box, FONTS
from rank import Rank
from video import process_video_ffmpeg
from stats import MemeStats

app = Flask(__name__)
rank = Rank()
rank.load_presets()
rank.init_embeddings(force_rebuild=True)
meme_stats = MemeStats()

API_KEY = "PLACE_YOUR_KEY_HERE"
SEMATIC_WEIGHT = 0.5
PERFORMANCE_WEIGHT = 0.5
images = ["16"]

# Папка для сохранения сгенерированных изображений
OUTPUT_FOLDER = "output"
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER

token_logger = logging.getLogger("token_usage")
token_logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("tokens.log")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
token_logger.addHandler(file_handler)
token_logger.propagate = False


def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        wrapper.last_execution_time = end_time - start_time
        return result

    wrapper.last_execution_time = 0
    return wrapper


def log_token_usage(result_id, usage):
    try:
        log_entry = {
            "result_id": result_id,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
        }
        token_logger.info(json.dumps(log_entry))
    except Exception as e:
        token_logger.error(f"Error logging token usage: {str(e)}")


# Глобальная переменная для отслеживания недоступности Google
google_down_until = 0  # время (в секундах), до которого Google считается недоступным
COOLDOWN_PERIOD = 60  # время «охлаждения» для Google в секундах


@timing_decorator
def generate(result_id, messages):
    """
    Функция отправляет запрос к openrouter с перебором провайдеров по приоритету.
    Если запрос через Google завершается ошибкой, то на период COOLDOWN_PERIOD
    Google пропускается и используются другие провайдеры. При успешном ответе от
    Google сбрасывается таймаут.
    """
    global google_down_until
    providers = ["Google", "Anthropic", "Amazon Bedrock"]

    for provider in providers:
        # Если пытаемся использовать Google, а период недоступности ещё не истёк, пропускаем
        if provider == "Google" and time.time() < google_down_until:
            print("Google временно недоступен, пропускаем его...")
            continue

        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": messages,
            "temperature": 1.0,
            "provider": {
                "order": [provider],
                "allow_fallbacks": False,
            },
        }

        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_KEY}",
                },
                data=json.dumps(payload),
            )
        except Exception as e:
            print(f"Ошибка запроса с провайдером {provider}: {str(e)}")
            if provider == "Google":
                google_down_until = time.time() + COOLDOWN_PERIOD
                print(f"Google отмечен как недоступный до {google_down_until}")
            continue

        if response.status_code != 200:
            print(f"Ошибка от {provider}: {response.status_code}, {response.text}")
            if provider == "Google":
                google_down_until = time.time() + COOLDOWN_PERIOD
                print(f"Google отмечен как недоступный до {google_down_until}")
            continue

        try:
            response_data = response.json()
            usage = response_data["usage"]
            log_token_usage(result_id, usage)

            if provider == "Google":
                google_down_until = 0

            return response_data["choices"][0]["message"]["content"]
        except (KeyError, ValueError) as e:
            print(f"Ошибка обработки ответа от {provider}: {str(e)}")
            if provider == "Google":
                google_down_until = time.time() + COOLDOWN_PERIOD
                print(f"Google отмечен как недоступный до {google_down_until}")
            continue

    return None


def build_system(messages):
    a = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": open("system.txt", "r", encoding="utf-8").read(),
                }
            ],
        }
    ]
    a.extend(messages)
    return a


@timing_decorator
def generate_caption(result_id, theme, data, image=None):
    parts = "\n".join(
        [
            f"- Подпись {idx + 1} - {part['title']}"
            for idx, part in enumerate(data["parts"])
        ]
    )
    title = data["title"]
    description = data["description"]
    data = f"Заголовок мема: {title}\n\nОписание мема: {description}\n\nПодписи (parts):\n{parts}"
    if image:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": open("caption.txt", "r", encoding="utf-8")
                        .read()
                        .replace("${theme}", theme)
                        .replace("${data}", data),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image,
                        },
                    },
                ],
            }
        ]
    else:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": open("caption.txt", "r", encoding="utf-8")
                        .read()
                        .replace("${theme}", theme)
                        .replace("${data}", data),
                    }
                ],
            }
        ]
    messages = build_system(messages)
    return generate(result_id, messages)


@timing_decorator
def parse_captions(captions):
    print(captions)
    captions = (
        captions.split("<final_response>\n")[1]
        .split("\n</final_response>")[0]
        .replace("- ", "")
    )
    captions = captions.split("\n")
    return captions


@app.route("/api/v1/predict", methods=["POST"])
def predict():
    start_time = time.time()
    data = request.json
    prompt = data.get("prompt")
    result_id = data.get("result_id")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    situations = rank.find_best_situations(prompt, top_n=5)

    weighted_situations = []
    for situation in situations:
        preset_id = situation["preset_id"]
        stats = meme_stats.get_template_performance(preset_id)

        combined_score = SEMATIC_WEIGHT * situation[
            "similarity"
        ] + PERFORMANCE_WEIGHT * (stats["win_rate"] / 100)
        print(f"combined_score = {combined_score}")
        print(f"stats = {stats}")

        weighted_situations.append({"preset_id": preset_id, "score": combined_score})

    weighted_situations.sort(key=lambda x: x["score"], reverse=True)
    meme_preset = weighted_situations[0]["preset_id"]

    print(f"meme_preset = {meme_preset}")

    if result_id:
        meme_stats.track_result(result_id, meme_preset)

    try:
        if meme_preset in images:
            image = Image.open(f"presets/images/{meme_preset}.jpg")
            data = json.loads(
                open(f"presets/images/{meme_preset}.json", "r", encoding="utf-8").read()
            )

            base64 = to_base64(image)
            captions = generate_caption(result_id, prompt, data, base64)

            if not captions:
                return jsonify(
                    {
                        "type": "image",
                        "url": f"https://humorithm.gamio.ru/output/error.png",
                        "error": "Failed to generate meme",
                    }
                )

            try:
                caption = parse_captions(captions)

                draw = ImageDraw.Draw(image)
                font_path = random.choice(FONTS)

                for idx, i in enumerate(data["parts"]):
                    draw_text_in_box(draw, caption[idx], i["box"], font_path, (0, 0, 0))

                filename = f"{int(time.time())}.jpg"
                output_path = os.path.join(app.config["OUTPUT_FOLDER"], filename)
                image.save(output_path)

                url = f"https://humorithm.gamio.ru/output/{filename}"
                if result_id:
                    meme_stats.update_result_data(result_id, url=url, prompt=prompt)

                return jsonify({"type": "image", "url": url})
            except Exception as e:
                return (
                    jsonify(
                        {
                            "type": "image",
                            "url": f"https://humorithm.gamio.ru/output/error.png",
                            "error": str(e),
                        }
                    ),
                    500,
                )
        else:
            data = json.loads(
                open(f"presets/videos/{meme_preset}.json", "r", encoding="utf-8").read()
            )
            captions = generate_caption(result_id, prompt, data, image=None)
            if not captions:
                return jsonify(
                    {
                        "type": "image",
                        "url": f"https://humorithm.gamio.ru/output/error.png",
                        "error": "Failed to generate meme",
                    },
                    500,
                )
            caption = parse_captions(captions)
            font_path = random.choice(FONTS)
            filename = f"{int(time.time())}.mp4"
            output_path = os.path.join(app.config["OUTPUT_FOLDER"], filename)
            process_video_ffmpeg(
                f"presets/videos/{meme_preset}.mp4",
                output_path,
                caption[0],
                data["parts"][0]["box"],
                font_path,
                compression="ultrafast",
                color=data.get("color", 255),
                border_color=data.get("border_color", 0),
                border_width=data.get("border_width", 2),
            )
            url = f"https://humorithm.gamio.ru/output/{filename}"
            if result_id:
                meme_stats.update_result_data(result_id, url=url, prompt=prompt)

            return jsonify({"type": "video", "url": url})
    except Exception as e:
        return jsonify(
            {
                "type": "image",
                "url": f"https://humorithm.gamio.ru/output/error.png",
                "error": str(e),
            },
            500,
        )


@app.route("/output/<filename>")
def serve_image(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename)


@app.route("/api/v1/stats/templates", methods=["GET"])
def get_template_stats():
    min_battles = request.args.get("min_battles", 10, type=int)
    stats = MemeStats()
    templates = stats.get_best_performing_templates(min_battles=min_battles)
    return jsonify({"templates": templates})


if __name__ == "__main__":
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False)
