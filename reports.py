"""Отчёты доступны и интерфейсу, и автоматическим проверкам."""
import csv
from pathlib import Path

import database as db

REPORTS = {
    "Выданные книги": (db.get_issued, [("copy_id", "Инв. №"), ("title", "Название"), ("ticket", "Билет"), ("full_name", "Читатель"), ("phone", "Телефон"), ("due_date", "Срок возврата")]),
    "Книги в наличии": (lambda: db.search_books(only_available=True), [("copy_id", "Инв. №"), ("title", "Название"), ("authors", "Авторы"), ("genre", "Жанр"), ("year", "Год")]),
    "Должники": (db.get_debtors, [("ticket", "Билет"), ("full_name", "Читатель"), ("phone", "Телефон"), ("copy_id", "Инв. №"), ("title", "Название"), ("due_date", "Срок возврата"), ("days_late", "Просрочка, дней")]),
    "Журнал операций": (lambda: db.get_history(-1), [("op_date", "Дата операции"), ("op_type", "Операция"), ("copy_id", "Инв. №"), ("title", "Название"), ("reader", "Читатель"), ("staff", "Сотрудник"), ("due_date", "Срок возврата")]),
}


def export_csv(path, columns, rows):
    # BOM и ; позволяют открыть русский отчёт в Excel без выбора кодировки.
    # Текстовые значения экранируются от интерпретации как формулы.
    def cell(value):
        value = "" if value is None else str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow([caption for key, caption in columns])
        writer.writerows([cell(row[key]) for key, caption in columns] for row in rows)
