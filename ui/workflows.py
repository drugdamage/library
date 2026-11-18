"""Рабочие формы с общими таблицами и сообщениями об ошибках."""
from datetime import date
import sqlite3

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
import database as db
from reports import REPORTS, export_csv


class Table(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)

    def populate(self, columns, rows, id_key=None, mark_overdue=True):
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([caption for key, caption in columns])
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            overdue = mark_overdue and 'due_date' in row.keys() and row['due_date'] and row['due_date'] < date.today().isoformat()
            for j, (key, caption) in enumerate(columns):
                value = row[key]
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "" if value is None else value)
                if id_key:
                    item.setData(Qt.ItemDataRole.UserRole, row[id_key])
                if overdue:
                    item.setForeground(QColor('#a32424'))
                self.setItem(i, j, item)
        self.setSortingEnabled(True)

    def selected_id(self):
        row = self.currentRow()
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.item(row, 0) else None


class Page(QWidget):
    def __init__(self, title):
        super().__init__()
        self.layout = QVBoxLayout(self)
        header = QLabel(title)
        header.setObjectName('pageTitle')
        self.layout.addWidget(header)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.layout.addWidget(self.message)

    def run_action(self, action):
        try:
            result = action()
        except (ValueError, sqlite3.Error) as error:
            self.message.setText(str(error) if isinstance(error, ValueError) else 'Не удалось сохранить изменения в базе. Повторите операцию.')
            self.message.setStyleSheet('color: #a32424')
            return False
        self.message.setText(result or 'Готово.')
        self.message.setStyleSheet('color: #236b36')
        self.refresh()
        return True


BOOK_COLUMNS = [('copy_id', 'Инв. №'), ('title', 'Название'), ('authors', 'Авторы'), ('genre', 'Жанр'), ('year', 'Год'), ('state', 'Состояние')]


class CatalogPage(Page):
    def __init__(self, user, issuing=False):
        super().__init__('Выдача' if issuing else 'Поиск книг')
        self.user, self.issuing = user, issuing
        self.search = QLineEdit()
        self.search.setPlaceholderText('Название, автор или жанр')
        self.available = QCheckBox('Только доступные')
        self.available.setChecked(issuing)
        self.genre = QComboBox()
        self.genre.addItem('Все жанры')
        for genre in db.get_genres():
            self.genre.addItem(genre['name'])
        bar = QHBoxLayout()
        for widget in (self.search, self.available, self.genre):
            bar.addWidget(widget)
        self.layout.addLayout(bar)
        if issuing:
            self.reader_search = QLineEdit()
            self.reader_search.setPlaceholderText('Поиск читателя по ФИО или номеру билета')
            self.reader = QComboBox()
            self.days = QSpinBox()
            self.days.setRange(1, 365)
            self.days.setValue(db.LOAN_DAYS)
            form = QFormLayout()
            form.addRow('Найти читателя:', self.reader_search)
            form.addRow('Читатель:', self.reader)
            form.addRow('Срок, дней:', self.days)
            self.layout.addLayout(form)
            self.reader_search.textChanged.connect(self.refresh_readers)
            self.refresh_readers()
        self.table = Table()
        self.layout.addWidget(self.table)
        self.count = QLabel()
        self.layout.addWidget(self.count)
        if issuing:
            button = QPushButton('Выдать выбранный экземпляр')
            button.clicked.connect(self.issue)
            self.layout.addWidget(button)
        self.search.textChanged.connect(self.refresh)
        self.available.toggled.connect(self.refresh)
        self.genre.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh_readers(self):
        previous = self.reader.currentData()
        self.reader.clear()
        text = self.reader_search.text().strip().lower()
        for row in db.get_readers():
            if text in row['full_name'].lower() or text in str(row['id']):
                self.reader.addItem(f"№{row['id']} — {row['full_name']}", row['id'])
        index = self.reader.findData(previous)
        if index >= 0:
            self.reader.setCurrentIndex(index)

    def refresh(self):
        if self.issuing:
            self.refresh_readers()
        rows = []
        for source in db.search_books(self.search.text(), self.available.isChecked()):
            row = dict(source)
            if self.genre.currentIndex() and row['genre'] != self.genre.currentText():
                continue
            row['state'] = 'В наличии' if row['available'] else 'Выдана до ' + row['due_date']
            rows.append(row)
        self.table.populate(BOOK_COLUMNS, rows, 'copy_id')
        self.count.setText(f'Найдено экземпляров: {len(rows)}')

    def issue(self):
        copy_id, reader_id = self.table.selected_id(), self.reader.currentData()
        if copy_id is None or reader_id is None:
            self.message.setText('Выберите читателя и экземпляр в таблице.')
            return
        def action():
            due = db.issue_book(copy_id, reader_id, self.user['id'], self.days.value())
            return f'Экземпляр №{copy_id} выдан. Вернуть до {due}.'
        self.run_action(action)


class ReturnPage(Page):
    def __init__(self, user):
        super().__init__('Отдача — возврат книг')
        self.user = user
        self.search = QLineEdit()
        self.search.setPlaceholderText('Инвентарный номер, название или ФИО читателя')
        self.layout.addWidget(self.search)
        self.table = Table()
        self.layout.addWidget(self.table)
        button = QPushButton('Принять выбранный экземпляр')
        button.clicked.connect(self.accept_book)
        self.layout.addWidget(button)
        self.search.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        text = self.search.text().strip().lower()
        rows = [r for r in db.get_issued() if not text or text in str(r['copy_id']) or text in r['title'].lower() or text in r['full_name'].lower()]
        self.table.populate(REPORTS['Выданные книги'][1], rows, 'copy_id')

    def accept_book(self):
        copy_id = self.table.selected_id()
        if copy_id is None:
            self.message.setText('Выберите выданный экземпляр в таблице.')
            return
        def action():
            db.return_book(copy_id, self.user['id'])
            return f'Возврат экземпляра №{copy_id} записан в журнал.'
        self.run_action(action)


class ReaderCardDialog(QDialog):
    def __init__(self, card, parent=None):
        super().__init__(parent)
        reader, loans, history = card['reader'], card['loans'], card['history']
        self.setWindowTitle(f"Карточка читателя — билет №{reader['id']}")
        self.resize(1000, 560)
        layout = QVBoxLayout(self)
        heading = QLabel(f"Читательский билет №{reader['id']}")
        heading.setObjectName('pageTitle')
        layout.addWidget(heading)
        details = QFormLayout()
        for key, caption in [('full_name', 'ФИО:'), ('phone', 'Телефон:'),
                             ('address', 'Адрес:'), ('birth_date', 'Дата рождения:'),
                             ('reg_date', 'Дата регистрации:')]:
            value = QLabel(str(reader[key]))
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details.addRow(caption, value)
        layout.addLayout(details)
        overdue = sum(loan['days_late'] > 0 for loan in loans)
        self.summary = QLabel(f'Книг на руках: {len(loans)}. Просрочено: {overdue}.')
        layout.addWidget(self.summary)
        tabs = QTabWidget()
        self.loans = Table()
        self.loans.populate([('copy_id', 'Инв. №'), ('title', 'Название'),
                             ('due_date', 'Срок возврата'), ('days_late', 'Просрочка, дней')], loans)
        self.history = Table()
        # Старый срок в журнале не означает, что книга всё ещё просрочена.
        self.history.populate([('op_date', 'Дата операции'), ('op_type', 'Операция'),
                               ('copy_id', 'Инв. №'), ('title', 'Название'),
                               ('staff', 'Сотрудник'), ('due_date', 'Срок при выдаче')],
                              history, mark_overdue=False)
        self.history.horizontalHeader().setStretchLastSection(False)
        tabs.addTab(self.loans, f'Книги на руках ({len(loans)})')
        tabs.addTab(self.history, f'История операций ({len(history)})')
        layout.addWidget(tabs, 1)
        hint = QLabel('Просроченные книги выделены красным.' if loans else 'Сейчас у читателя нет книг на руках.')
        layout.addWidget(hint)
        close = QPushButton('Закрыть')
        close.clicked.connect(self.accept)
        layout.addWidget(close)


class ReadersPage(Page):
    def __init__(self):
        super().__init__('Читатели')
        self.search = QLineEdit()
        self.search.setPlaceholderText('ФИО или номер билета')
        self.layout.addWidget(self.search)
        self.table = Table()
        self.layout.addWidget(self.table)
        self.card_button = QPushButton('Карточка выбранного читателя')
        self.card_button.setEnabled(False)
        self.card_button.clicked.connect(self.open_card)
        self.layout.addWidget(self.card_button)
        self.table.itemSelectionChanged.connect(self.update_card_button)
        self.table.cellDoubleClicked.connect(self.open_card)
        self.fields = [QLineEdit() for _ in range(3)]
        self.birth = QDateEdit(QDate(2000, 1, 1))
        self.birth.setCalendarPopup(True)
        self.birth.setDisplayFormat('dd.MM.yyyy')
        self.birth.setMaximumDate(QDate.currentDate())
        form = QFormLayout()
        for caption, field in zip(('ФИО:', 'Телефон:', 'Адрес:'), self.fields):
            form.addRow(caption, field)
        form.addRow('Дата рождения:', self.birth)
        self.layout.addLayout(form)
        button = QPushButton('Зарегистрировать читателя')
        button.clicked.connect(self.register)
        self.layout.addWidget(button)
        self.search.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        text = self.search.text().strip().lower()
        rows = [r for r in db.get_readers() if text in r['full_name'].lower() or text in str(r['id'])]
        self.table.populate([('id', 'Билет'), ('full_name', 'ФИО'), ('phone', 'Телефон'), ('address', 'Адрес'), ('birth_date', 'Дата рождения')], rows, 'id')
        self.update_card_button()

    def update_card_button(self):
        self.card_button.setEnabled(self.table.selected_id() is not None)

    def open_card(self, *_):
        reader_id = self.table.selected_id()
        if reader_id is None:
            self.message.setText('Выберите читателя в таблице.')
            return
        try:
            card = db.get_reader_card(reader_id)
        except (ValueError, sqlite3.Error) as error:
            self.message.setText(str(error) if isinstance(error, ValueError) else 'Не удалось открыть карточку читателя.')
            return
        ReaderCardDialog(card, self).exec()

    def register(self):
        def action():
            ticket = db.add_reader(*(f.text() for f in self.fields), self.birth.date().toString('yyyy-MM-dd'))
            for field in self.fields:
                field.clear()
            return f'Читатель зарегистрирован. Номер билета: {ticket}.'
        self.run_action(action)


class ReportsPage(Page):
    def __init__(self):
        super().__init__('Отчёты')
        self.kind = QComboBox()
        self.kind.addItems(REPORTS)
        self.layout.addWidget(self.kind)
        self.table = Table()
        self.layout.addWidget(self.table)
        self.count = QLabel()
        self.layout.addWidget(self.count)
        button = QPushButton('Сохранить отчёт в CSV')
        button.clicked.connect(self.export)
        self.layout.addWidget(button)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        load, self.columns = REPORTS[self.kind.currentText()]
        self.rows = load()
        self.table.populate(self.columns, self.rows)
        self.count.setText(f'Записей: {len(self.rows)}')

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить отчёт', self.kind.currentText() + '.csv', 'CSV (*.csv)')
        if path:
            try:
                # Сохраняем именно видимый порядок, включая сортировку пользователем.
                rows = [{key: self.table.item(i, j).text() for j, (key, _) in enumerate(self.columns)} for i in range(self.table.rowCount())]
                export_csv(path, self.columns, rows)
            except OSError:
                QMessageBox.warning(self, 'Отчёт', 'Не удалось записать файл. Выберите доступную папку.')
            else:
                self.message.setText('Отчёт сохранён: ' + path)


class AdminPage(Page):
    def __init__(self, user):
        super().__init__('Администрирование — пополнение фонда')
        from PyQt6.QtWidgets import QListWidget
        self.user = user
        self.title = QLineEdit()
        self.genre = QComboBox()
        for row in db.get_genres():
            self.genre.addItem(row['name'], row['id'])
        self.authors = QListWidget()
        self.authors.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for row in db.get_authors():
            self.authors.addItem(row['name'])
            self.authors.item(self.authors.count() - 1).setData(Qt.ItemDataRole.UserRole, row['id'])
        self.year = QSpinBox()
        self.year.setRange(1, date.today().year)
        self.year.setValue(date.today().year)
        self.copies = QSpinBox()
        self.copies.setRange(1, 100)
        form = QFormLayout()
        for caption, field in [('Название:', self.title), ('Жанр:', self.genre), ('Авторы (можно несколько):', self.authors), ('Год издания:', self.year), ('Экземпляров:', self.copies)]:
            form.addRow(caption, field)
        self.layout.addLayout(form)
        add = QPushButton('Добавить книгу и экземпляры')
        add.clicked.connect(self.add)
        self.layout.addWidget(add)
        backup = QPushButton('Создать резервную копию базы')
        backup.clicked.connect(self.backup)
        self.layout.addWidget(backup)
        self.layout.addStretch()

    def refresh(self):
        pass

    def add(self):
        def action():
            db.add_book(self.title.text(), self.genre.currentData(), [item.data(Qt.ItemDataRole.UserRole) for item in self.authors.selectedItems()], self.year.value(), self.copies.value(), self.user['id'])
            self.title.clear()
            return 'Книга и экземпляры добавлены. Они доступны в поиске и выдаче.'
        self.run_action(action)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Резервная копия', 'library-backup.db', 'SQLite (*.db)')
        if path:
            def action():
                try:
                    db.backup_database(path, self.user['id'])
                except OSError:
                    raise ValueError('Не удалось записать копию. Выберите доступную папку.') from None
                return 'Резервная копия создана: ' + path
            self.run_action(action)
