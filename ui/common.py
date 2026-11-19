"""Общие элементы рабочих форм."""
from datetime import date, datetime
import sqlite3

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
import database as db

RAW_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_ROLE = Qt.ItemDataRole.UserRole + 2


def display_date(value):
    if not value:
        return '—'
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime('%d.%m.%Y %H:%M') if len(str(value)) > 10 else parsed.strftime('%d.%m.%Y')
    except ValueError:
        return str(value)


class TableItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(RAW_ROLE), other.data(RAW_ROLE)
        if isinstance(a, str) and isinstance(b, str):
            a, b = db.py_lower(a), db.py_lower(b)
        return (a is not None, a) < (b is not None, b)


class Table(QTableWidget):
    def __init__(self, sort_column=0, descending=False):
        super().__init__()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSortIndicator(sort_column, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)

    def populate(self, columns, rows, id_key=None, mark_overdue=True):
        self.blockSignals(True)
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([caption for key, caption in columns])
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            row = dict(row)
            overdue = mark_overdue and row.get('due_date') and row['due_date'] < date.today().isoformat()
            for j, (key, caption) in enumerate(columns):
                value = row[key]
                shown = display_date(value) if key in ('due_date', 'birth_date', 'reg_date', 'op_date') else ('' if value is None else str(value))
                item = TableItem(shown)
                item.setData(RAW_ROLE, value)
                item.setData(ROW_ROLE, row)
                if id_key:
                    item.setData(Qt.ItemDataRole.UserRole, row[id_key])
                item.setToolTip(shown)
                if overdue:
                    item.setForeground(QColor('#a32424'))
                self.setItem(i, j, item)
        self.setSortingEnabled(True)
        self.clearSelection()
        self.setCurrentCell(-1, -1)
        self.blockSignals(False)
        self.itemSelectionChanged.emit()

    def selected_row(self):
        rows = self.selectionModel().selectedRows()
        return self.item(rows[0].row(), 0) if len(rows) == 1 else None

    def selected_id(self):
        item = self.selected_row()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_record(self):
        item = self.selected_row()
        return item.data(ROW_ROLE) if item else None

    def select_id(self, value):
        for row in range(self.rowCount()):
            if self.item(row, 0).data(Qt.ItemDataRole.UserRole) == value:
                self.selectRow(row)
                self.scrollToItem(self.item(row, 0))
                return True
        return False


class ReaderSearch(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.field = QComboBox()
        for caption, key in [('ФИО или № билета', 'all'), ('Только ФИО', 'name'), ('Точный № билета', 'ticket'), ('Телефон', 'phone')]:
            self.field.addItem(caption, key)
        self.input = QLineEdit()
        self.input.setClearButtonEnabled(True)
        self.input.setMaxLength(200)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.field)
        layout.addWidget(self.input, 1)
        self.field.currentIndexChanged.connect(self.change_field)
        self.input.textChanged.connect(self.changed)
        self.change_field()

    def change_field(self):
        self.input.setPlaceholderText({
            'all': 'Фамилия, имя, отчество или точный номер билета',
            'name': 'Любые слова из ФИО, например: Мария Кузнецова',
            'ticket': 'Номер билета целиком, например: 12',
            'phone': 'Номер телефона или его часть',
        }[self.field.currentData()])
        self.changed.emit()

    def rows(self):
        return db.search_readers(self.input.text(), self.field.currentData())


class Page(QWidget):
    def __init__(self, title):
        super().__init__()
        self.layout = QVBoxLayout(self)
        header = QLabel(title)
        header.setObjectName('pageTitle')
        bar = QHBoxLayout()
        bar.addWidget(header, 1)
        refresh = QPushButton('Обновить')
        refresh.setObjectName('secondaryButton')
        refresh.setShortcut('F5')
        refresh.clicked.connect(lambda: self.refresh())
        bar.addWidget(refresh)
        self.layout.addLayout(bar)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.hide()
        self.layout.addWidget(self.message)

    def show_message(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet('color: #a32424; padding: 6px;' if error else 'color: #236b36; padding: 6px;')
        self.message.setVisible(bool(text))

    def confirm(self, title, text):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        confirm = dialog.addButton('Подтвердить', QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton('Отмена', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        return dialog.clickedButton() == confirm

    def run_action(self, action):
        try:
            result = action()
        except (ValueError, sqlite3.Error) as error:
            self.refresh()
            self.show_message(str(error) if isinstance(error, ValueError) else 'Не удалось сохранить изменения. Обновите список и повторите операцию.', error=True)
            return False
        self.refresh()
        self.show_message(result or 'Готово.')
        return True
