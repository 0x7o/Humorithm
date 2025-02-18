import requests
import json
import os
from collections import defaultdict


class MemeStats:
    def __init__(self):
        self.stats_file = "meme_stats.json"
        self.our_results_file = "our_results.json"
        self.processed_battles_file = "processed_battles.json"
        self.template_stats = self.load_stats()
        self.our_results = self.load_our_results()
        self.processed_battles = self.load_processed_battles()

    def get_default_stats():
        return {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "same_shit": 0,
            "total_battles": 0,
            "win_rate": 100.0,
        }

    def load_stats(self):
        if os.path.exists(self.stats_file):
            with open(self.stats_file, "r") as f:
                data = json.load(f)
                # Преобразуем обычный dict в defaultdict
                templates = defaultdict(MemeStats.get_default_stats)
                templates.update(data["templates"])
                return {"templates": templates}
        return {"templates": defaultdict(MemeStats.get_default_stats)}

    def load_our_results(self):
        if os.path.exists(self.our_results_file):
            with open(self.our_results_file, "r") as f:
                return json.load(f)
        return {}

    def load_processed_battles(self):
        if os.path.exists(self.processed_battles_file):
            with open(self.processed_battles_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_processed_battles(self):
        with open(self.processed_battles_file, "w") as f:
            json.dump(list(self.processed_battles), f, indent=2)

    def save_our_results(self):
        with open(self.our_results_file, "w") as f:
            json.dump(self.our_results, f, indent=2)

    def track_result(self, result_id, template_id):
        self.our_results[str(result_id)] = {
            "template_id": str(template_id),
            "url": None,
            "prompt": None,
        }
        self.save_our_results()

    def update_result_data(self, result_id, url=None, prompt=None):
        if str(result_id) in self.our_results:
            if url is not None:
                self.our_results[str(result_id)]["url"] = url
            if prompt is not None:
                self.our_results[str(result_id)]["prompt"] = prompt
            self.save_our_results()

    def save_stats(self):
        stats_to_save = {
            "templates": {
                k: dict(v) for k, v in self.template_stats["templates"].items()
            }
        }
        with open(self.stats_file, "w") as f:
            json.dump(stats_to_save, f, indent=2)

    def fetch_battles(self, to_date=None):
        url = "https://aimemearena-676a343606c3.herokuapp.com/api/battles"
        if to_date:
            url += f"?to={to_date}"

        response = requests.get(url)
        if response.status_code == 200:
            # Фильтруем только баттлы с нашими результатами и не обработанные ранее
            battles = response.json()["items"]
            our_battles = [
                battle
                for battle in battles
                if (
                    str(battle["result_1_id"]) in self.our_results
                    or str(battle["result_2_id"]) in self.our_results
                )
                and str(battle["battle_id"]) not in self.processed_battles
            ]
            return our_battles
        return []

    def update_template_stats(self, result_id, battle_result, battle_id):
        # Получаем ID шаблона по result_id
        result_data = self.our_results.get(str(result_id))
        if not result_data:
            return  # Пропускаем, если это не наш результат

        template_id = result_data.get("template_id")
        if not template_id:
            return

        stats = self.template_stats["templates"][template_id]
        stats["total_battles"] += 1

        if battle_result == "FIRST":
            stats["wins"] += 1
        elif battle_result == "SECOND":
            stats["losses"] += 1
        elif battle_result == "SAME":
            stats["draws"] += 1
        elif battle_result == "SAME_SHIT":
            stats["same_shit"] += 1

        total_decisive_battles = stats["wins"] + stats["losses"]
        stats["win_rate"] = (
            (stats["wins"] / total_decisive_battles * 100)
            if total_decisive_battles > 0
            else 0
        )

        # Отмечаем баттл как обработанный
        self.processed_battles.add(str(battle_id))

    def get_template_performance(self, template_id):
        return dict(self.template_stats["templates"][template_id])

    def get_best_performing_templates(self, min_battles=10):
        self.load_stats()
        templates = []
        for template_id, stats in self.template_stats["templates"].items():
            if stats["total_battles"] >= min_battles:
                templates.append(
                    {
                        "template_id": template_id,
                        "win_rate": stats["win_rate"],
                        "total_battles": stats["total_battles"],
                    }
                )
        return sorted(templates, key=lambda x: x["win_rate"], reverse=True)
