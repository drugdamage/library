"""Отчёты доступны и интерфейсу, и автоматическим проверкам."""
import csv
from dataclasses import dataclass
import operator
from pathlib import Path
import re

import database as db

DEBTORS = "Должники"
BOOK_FORMULAR = "Формуляр книги"
READER_FORMULAR = "Формуляр читателя"


@dataclass(frozen=True)
class ReportLayout:
    columns: tuple[tuple[str, str], ...]
    sort_key: str
    descending: bool = False
    mark_overdue: bool = False


ISSUED_LAYOUT = ReportLayout(
    (("copy_id", "Инв. №"), ("title", "Название"), ("ticket", "Билет"),
     ("full_name", "Читатель"), ("phone", "Телефон"), ("due_date", "Срок возврата")),
    "due_date", mark_overdue=True,
)
JOURNAL_LAYOUT = ReportLayout(
    (("op_date", "Дата операции"), ("op_type", "Операция"), ("copy_id", "Инв. №"),
     ("title", "Название"), ("reader", "Читатель"), ("ticket", "Билет"),
     ("staff", "Сотрудник"), ("due_date", "Срок при выдаче")),
    "op_date", descending=True,
)

REPORTS = {
    "Выданные книги": (db.get_issued, ISSUED_LAYOUT),
    "Книги в наличии": (lambda: db.search_books(only_available=True), ReportLayout(
        (("copy_id", "Инв. №"), ("title", "Название"), ("authors", "Авторы"),
         ("genre", "Жанр"), ("year", "Год")),
        "title",
    )),
    DEBTORS: (db.get_debtors, ReportLayout(
        (("ticket", "Билет"), ("full_name", "Читатель"), ("phone", "Телефон"),
         ("copy_id", "Инв. №"), ("title", "Название"), ("due_date", "Срок возврата"),
         ("days_late", "Просрочка, дней")),
        "days_late", descending=True, mark_overdue=True,
    )),
    "Журнал операций": (lambda: db.get_history(-1), JOURNAL_LAYOUT),
}

FORMULARS = {
    BOOK_FORMULAR: (
        ("copies", "Экземпляры", ReportLayout(
            (("copy_id", "Инв. №"), ("state", "Состояние"), ("reader", "Читатель"),
             ("ticket", "Билет"), ("due_date", "Срок возврата"), ("days_late", "Просрочка, дней")),
            "copy_id", mark_overdue=True,
        )),
        ("history", "История операций", ReportLayout(
            tuple(col for col in JOURNAL_LAYOUT.columns if col[0] != "title"),
            "op_date", descending=True,
        )),
    ),
    READER_FORMULAR: (
        ("loans", "Книги на руках", ReportLayout(
            (("copy_id", "Инв. №"), ("title", "Название"), ("due_date", "Срок возврата"),
             ("days_late", "Просрочка, дней")),
            "due_date", mark_overdue=True,
        )),
        ("history", "История операций", ReportLayout(
            tuple(col for col in JOURNAL_LAYOUT.columns if col[0] not in ("ticket", "reader")),
            "op_date", descending=True,
        )),
    ),
}

OVERDUE_FILTER = re.compile(r"(<=|>=|<|>|=|≤|≥)?\s*([0-9]{1,9})(?:\s*(?:день|дня|дней|дн?\.?))?")
COMPARISONS = {
    None: operator.eq, "=": operator.eq,
    "<": operator.lt, ">": operator.gt,
    "<=": operator.le, "≤": operator.le,
    ">=": operator.ge, "≥": operator.ge,
}


def filter_debtors(rows, text):
    text = text.strip().lower()
    if not text:
        return rows
    match = OVERDUE_FILTER.fullmatch(text)
    if match is None:
        raise ValueError("Введите целое число дней. Поддерживаются условия <4, 4, >4, <=4 и >=4.")
    compare = COMPARISONS[match[1]]
    days = int(match[2])
    return [row for row in rows if compare(row["days_late"], days)]


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
