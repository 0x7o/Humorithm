from celery import Celery
from celery.schedules import crontab
import os
import requests
from stats import MemeStats

# Создаем экземпляр Celery
celery = Celery("tasks")

# Конфигурация Celery из переменных окружения
celery.conf.update(
    broker_url=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    timezone="UTC",
    beat_schedule={
        "update-meme-stats": {
            "task": "tasks.update_meme_statistics",
            "schedule": 300.0,  # Каждые 5 минут
        }
    },
)

# Бот для логирования в телеграм
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
TELEGRAM_CHANNEL_ID = ""


def post_to_telegram(meme_url):
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    try:
        is_video = meme_url.lower().endswith((".mp4", ".mov", ".avi"))

        if is_video:
            endpoint = f"{base_url}/sendVideo"
            files = {"video": requests.get(meme_url).content}
        else:
            endpoint = f"{base_url}/sendPhoto"
            files = {"photo": requests.get(meme_url).content}

        response = requests.post(
            endpoint, data={"chat_id": TELEGRAM_CHANNEL_ID}, files=files
        )

        if response.status_code != 200:
            raise Exception(f"Failed to post meme to Telegram: {response.text}")

    except Exception as e:
        print(f"Failed to post meme to Telegram: {e}")


def send_to_telegram(message, media_url=None):
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    try:
        if media_url:
            is_video = media_url.lower().endswith((".mp4", ".mov", ".avi"))

            if is_video:
                endpoint = f"{base_url}/sendVideo"
                files = {"video": requests.get(media_url).content}
            else:
                endpoint = f"{base_url}/sendPhoto"
                files = {"photo": requests.get(media_url).content}

            response = requests.post(
                endpoint,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": message},
                files=files,
            )
        else:
            response = requests.post(
                f"{base_url}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            )

        return response.json()
    except Exception as e:
        print(f"Error sending to Telegram: {str(e)}")
        return None


@celery.task
def update_meme_statistics():
    """
    Задача Celery для обновления статистики мемов.
    """
    try:
        meme_stats = MemeStats()
        battles = meme_stats.fetch_battles()

        for battle in battles:
            result_1_id = str(battle["result_1_id"])
            result_2_id = str(battle["result_2_id"])
            battle_id = str(battle["battle_id"])
            vote = battle["vote"]

            # Определяем, какой result_id принадлежит нашему агенту
            our_result_id = None
            our_position = None

            if result_1_id in meme_stats.our_results:
                our_result_id = result_1_id
                our_position = "FIRST"
            elif result_2_id in meme_stats.our_results:
                our_result_id = result_2_id
                our_position = "SECOND"

            if our_result_id:
                # Определяем результат для нашего мема
                if vote == "SAME":
                    result = "SAME"
                elif vote == "SAME_SHIT":
                    result = "SAME_SHIT"
                elif vote == our_position:
                    result = "FIRST"  # победа
                else:
                    result = "SECOND"  # поражение

                meme_stats.update_template_stats(our_result_id, result, battle_id)

                if result in ["FIRST", "SECOND"]:
                    result_data = meme_stats.our_results.get(our_result_id, {})
                    meme_url = result_data.get("url")
                    prompt = result_data.get("prompt")

                    if meme_url:
                        message = (
                            f"🎭 Meme Battle Result 🎭\n"
                            f"Battle ID: {battle_id}\n"
                            f"Result: {'🏆 Victory!' if result == 'FIRST' else '❌ Defeat'}\n"
                            f"Our Position: {our_position}\n"
                            f"Vote: {vote}\n"
                            f"Prompt: {prompt if prompt else 'N/A'}"
                        )
                        send_to_telegram(message, meme_url)

                        if result == "FIRST":
                            post_to_telegram(meme_url)

        meme_stats.save_stats()
        meme_stats.save_processed_battles()
        return f"Successfully processed {len(battles)} battles"
    except Exception as e:
        return f"Error updating statistics: {str(e)}"
