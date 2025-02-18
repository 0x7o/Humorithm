from sentence_transformers import SentenceTransformer
import pickle as pkl
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


import os

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"


class Rank:
    def __init__(self, model_name="deepvk/USER-bge-m3"):
        self.model = SentenceTransformer(model_name)
        self.situations = []  # список кортежей (preset_id, situation)
        self.embeddings = None

    def load_presets(self, preset_dir="presets"):
        for subdir in ["images", "videos"]:
            path = os.path.join(preset_dir, subdir)
            for file in os.listdir(path):
                if file.endswith(".json"):
                    with open(os.path.join(path, file), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        preset_id = os.path.splitext(file)[0]

                        # Добавляем каждую ситуацию отдельно
                        for situation in data.get("situations", []):
                            self.situations.append((preset_id, situation))

    def embed(self, sentences):
        embeddings = self.model.encode(
            sentences, normalize_embeddings=True, show_progress_bar=False
        )
        return embeddings

    def save_embeddings(self, embeddings, filename):
        with open(filename, "wb") as f:
            pkl.dump(embeddings, f)

    def load_embeddings(self, filename):
        with open(filename, "rb") as f:
            return pkl.load(f)

    def init_embeddings(self, force_rebuild=False):
        embedding_file = "situation_embeddings.pkl"

        if not force_rebuild and os.path.exists(embedding_file):
            self.embeddings = self.load_embeddings(embedding_file)
        else:
            # Создаем эмбеддинги для каждой ситуации
            situations = [s[1] for s in self.situations]  # берем только тексты ситуаций
            self.embeddings = self.embed(situations)
            self.save_embeddings(self.embeddings, embedding_file)

    def find_best_situations(self, query, top_n=5):
        query_embedding = self.embed([query])[0]
        similarities = cosine_similarity([query_embedding], self.embeddings)[0]

        # Получаем топ N результатов
        top_indices = np.argsort(similarities)[-top_n:][::-1]

        results = []
        for idx in top_indices:
            preset_id, situation = self.situations[idx]
            similarity = similarities[idx]
            results.append(
                {
                    "preset_id": preset_id,
                    "situation": situation,
                    "similarity": similarity,
                }
            )

        return results


if __name__ == "__main__":
    rank = Rank()
    rank.load_presets()
    rank.init_embeddings(force_rebuild=True)

    while True:
        query = input("Введите запрос: ")
        if not query:
            break

        results = rank.find_best_situations(query)

        print("\nПодходящие ситуации:")
        for i, result in enumerate(results, 1):
            print(
                f"\n{i}. Мем: {result['preset_id']} (сходство: {result['similarity']:.2f})"
            )
            print(f"Ситуация: {result['situation']}")
