"""Генерация синтетического корпуса R&D-отчётов горно-металлургической отрасли.

Выдаёт связный русскоязычный текст (прозу), который потом честно перепарсивается
экстрактором. Заложены пары экспериментов с противоречивыми выводами и числами —
для демонстрации поиска противоречий.

Реальный датасет с Яндекс.Диска подключается заменой data/corpus.json.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(42)

MATERIALS = [
    "пентландит", "халькопирит", "пирротин", "медно-никелевая руда",
    "никелевый концентрат", "медный концентрат", "файнштейн", "штейн",
    "серная кислота", "ксантогенат калия", "известь", "магнетит",
    "элементная сера", "кобальтовый кек",
]
PRODUCTS = [
    "никелевый концентрат", "медный концентрат", "катодный никель",
    "катодная медь", "файнштейн", "серная кислота", "шлам МПГ",
]
PROCESSES = [
    "флотация", "автоклавное окислительное выщелачивание", "плавка в печи Ванюкова",
    "конвертирование штейна", "электроэкстракция", "сгущение пульпы",
    "магнитная сепарация", "окислительный обжиг", "цианирование",
]
EQUIPMENT = [
    "флотомашина РИФ-25", "автоклав горизонтальный", "печь Ванюкова",
    "конвертер Пирса-Смита", "сгуститель Ø18 м", "гидроциклон ГЦ-500",
    "электролизёр", "шаровая мельница МШЦ-3600",
]
TEAMS = [
    "Лаборатория гидрометаллургии ГМОИЦ", "Иванов А. П.", "Петрова С. М.",
    "Отдел обогащения НИИ", "Сидоренко В. Н.", "Группа пирометаллургии",
    "Козлова Е. А.", "Лаборатория аналитической химии",
]

POSITIVE = [
    "показал устойчивый рост извлечения целевого металла",
    "позволяет повысить качество концентрата без потерь по извлечению",
    "рекомендуется к внедрению на обогатительной фабрике",
    "обеспечивает стабильные показатели при промышленном масштабировании",
]
NEGATIVE = [
    "не обеспечил проектных показателей извлечения",
    "приводит к росту потерь металла с хвостами",
    "не рекомендуется без дополнительной доводки режима",
    "показал нестабильные результаты и требует доработки",
]

ORIGINS = ["Отечественная", "Зарубежная"]


def _num(lo, hi, step=1):
    n = random.randint(int(lo / step), int(hi / step)) * step
    return round(n, 2)


def make_doc(i: int, contradiction_pair: tuple | None = None):
    """Собирает один отчёт. Если задан contradiction_pair — фиксирует материал/процесс
    и полярность вывода, чтобы получить противоречащую пару."""
    if contradiction_pair:
        material, process, positive = contradiction_pair
    else:
        material = random.choice(MATERIALS)
        process = random.choice(PROCESSES)
        positive = random.random() > 0.4

    product = random.choice(PRODUCTS)
    equip = random.choice(EQUIPMENT)
    team = random.choice(TEAMS)
    origin = random.choice(ORIGINS)
    year = random.randint(2016, 2024)

    temperature = _num(60, 1300, 5)
    recovery = _num(55, 96, 1)
    ph = round(random.uniform(1.5, 11.0), 1)
    grade = _num(8, 45, 1)
    pressure = _num(1, 40, 1)
    duration = _num(15, 240, 5)

    verdict = random.choice(POSITIVE if positive else NEGATIVE)

    title = f"Исследование процесса «{process}» для переработки материала «{material}»"
    text = (
        f"Отчёт № R-{1000 + i}. {title}. "
        f"Работа выполнена коллективом: {team}. Происхождение практики: {origin.lower()}. Год: {year}. "
        f"В ходе эксперимента материал «{material}» подвергался процессу «{process}» "
        f"с использованием оборудования «{equip}». "
        f"Режимные параметры: температура {temperature} °C, извлечение {recovery} %, "
        f"pH {ph}, содержание в концентрате {grade} %, давление {pressure} атм, "
        f"длительность {duration} мин. "
        f"Целевой продукт — «{product}». "
        f"Вывод: применение процесса «{process}» к материалу «{material}» {verdict}. "
    )
    return {
        "id": f"R-{1000 + i}",
        "title": title,
        "origin": origin,
        "year": year,
        "text": text,
    }


def main():
    docs = []
    idx = 0

    # 6 заложенных противоречивых пар: один материал+процесс, противоположные выводы
    contradiction_specs = [
        ("пентландит", "флотация"),
        ("файнштейн", "конвертирование штейна"),
        ("медно-никелевая руда", "автоклавное окислительное выщелачивание"),
    ]
    for material, process in contradiction_specs:
        docs.append(make_doc(idx, (material, process, True))); idx += 1
        docs.append(make_doc(idx, (material, process, False))); idx += 1

    # остальной корпус
    while idx < 40:
        docs.append(make_doc(idx)); idx += 1

    out = Path(__file__).resolve().parent.parent / "data" / "corpus.json"
    out.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сгенерировано {len(docs)} отчётов -> {out}")


if __name__ == "__main__":
    main()
