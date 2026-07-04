"""Доменная онтология R&D графа знаний горно-металлургической отрасли.

Небольшая, но настоящая схема: типы узлов, типы связей и числовые параметры,
которые поддерживают фильтрацию по диапазонам.
"""

# Типы узлов и цвет для визуализации
NODE_TYPES = {
    "Publication": {"color": "#4C78A8", "label": "Публикация/Отчёт"},
    "Experiment": {"color": "#F58518", "label": "Эксперимент"},
    "Material":    {"color": "#54A24B", "label": "Материал/Вещество"},
    "Process":     {"color": "#B279A2", "label": "Процесс/Технология"},
    "Equipment":   {"color": "#E45756", "label": "Оборудование"},
    "Person":      {"color": "#72B7B2", "label": "Эксперт/Команда"},
    "Conclusion":  {"color": "#EECA3B", "label": "Вывод/Рекомендация"},
}

# Типы связей: (тип, откуда, куда)
EDGE_TYPES = [
    ("AUTHORED_BY",   "Publication", "Person"),
    ("DESCRIBES",     "Publication", "Experiment"),
    ("USES_MATERIAL", "Experiment",  "Material"),
    ("APPLIES_PROCESS","Experiment", "Process"),
    ("USES_EQUIPMENT","Experiment",  "Equipment"),
    ("PRODUCES",      "Experiment",  "Material"),
    ("CONCLUDES",     "Experiment",  "Conclusion"),
    ("CITES",         "Publication", "Publication"),
    ("CONTRADICTS",   "Conclusion",  "Conclusion"),
]

# Числовые параметры эксперимента -> (человекочитаемое имя, единица)
# Именно они дают семантику числовых диапазонов в запросах.
NUMERIC_PARAMS = {
    "temperature":  ("Температура", "°C"),
    "recovery":     ("Извлечение", "%"),
    "ph":           ("pH", ""),
    "grade":        ("Содержание в концентрате", "%"),
    "pressure":     ("Давление", "атм"),
    "duration":     ("Длительность", "мин"),
}

ORIGINS = ["Отечественная", "Зарубежная"]
