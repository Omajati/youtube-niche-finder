"""Запуск анализа из командной строки.

Примеры:
  python cli.py "unsolved mysteries" --langs en
  python cli.py "misterios sin resolver" --langs es --expand 3
  python cli.py --langs en,de --expand 2 --max 8      # автопоиск от стартовых тем
"""
import argparse

from niche_finder import pipeline


def main():
    p = argparse.ArgumentParser(description="Поиск ниш на YouTube")
    p.add_argument("queries", nargs="*", help="темы для анализа (на языке рынка); пусто = стартовые темы")
    p.add_argument("--langs", default="en", help="языки через запятую: en,es,de,fr")
    p.add_argument("--expand", type=int, default=0, help="сколько подсказок YouTube добавить к каждой теме")
    p.add_argument("--max", type=int, default=10, help="максимум ниш за запуск (≈204 единицы квоты на нишу)")
    args = p.parse_args()

    def progress(s):
        if s.get("current"):
            print(f"[{s['done'] + 1}/{s['total']}] {s['current']}")

    status = pipeline.run(args.queries, args.langs.split(","), args.expand, args.max, progress=progress)
    print(f"Готово: {status['done']} ниш, потрачено {status['units']} единиц квоты.")
    for err in status["errors"]:
        print("Ошибка:", err)
    for r in sorted(pipeline.load_results(), key=lambda r: r["score"], reverse=True)[:15]:
        print(f"{r['score']:>3}  [{r['lang']}] {r['query']}")


if __name__ == "__main__":
    main()
