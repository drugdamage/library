"""Рабочие формы с общими таблицами и сообщениями об ошибках."""
from datetime import date, datetime, timedelta
import sqlite3

from PyQt6.QtCore import QDate, QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
)
import database as db
from reports import ISSUED_LAYOUT
from ui.common import Page, Table, ReaderSearch, display_date


BOOK_COLUMNS = [('copy_id', 'Инв. №'), ('title', 'Название'), ('authors', 'Авторы'), ('genre', 'Жанр'), ('year', 'Год'), ('state', 'Состояние')]


class CatalogPage(Page):
    def __init__(self, user, issuing=False):
        super().__init__('Выдача' if issuing else 'Поиск книг')
        self.user, self.issuing = user, issuing
        self.search = QLineEdit()
        self.search.setMaxLength(200)
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText('Название, автор, жанр или инвентарный номер')
        self.available = QCheckBox('Только доступные')
        self.available.setChecked(issuing)
        self.genre = QComboBox()
        self.genre.addItem('Все жанры', None)
        for genre in db.get_genres():
            self.genre.addItem(genre['name'], genre['id'])
        bar = QHBoxLayout()
        for widget in (self.search, self.available, self.genre):
            bar.addWidget(widget)
        self.layout.addLayout(bar)
        if issuing:
            self.reader_filter = ReaderSearch()
            self.reader_search = self.reader_filter.input
            self.reader = QComboBox()
            self.reader_hint = QLabel()
            self.reader_hint.setWordWrap(True)
            self.days = QSpinBox()
            self.days.setRange(1, 365)
            self.days.setValue(db.LOAN_DAYS)
            form = QFormLayout()
            form.addRow('Найти читателя:', self.reader_filter)
            form.addRow('Выбрать читателя:', self.reader)
            form.addRow('', self.reader_hint)
            form.addRow('Срок выдачи, дней:', self.days)
            self.layout.addLayout(form)
        self.table = Table(sort_column=1)
        self.layout.addWidget(self.table)
        self.count = QLabel()
        self.layout.addWidget(self.count)
        if issuing:
            self.review = QLabel('Выберите читателя и доступный экземпляр.')
            self.review.setTextFormat(Qt.TextFormat.PlainText)
            self.review.setWordWrap(True)
            self.layout.addWidget(self.review)
            self.issue_button = QPushButton('Выдать книгу')
            self.issue_button.setEnabled(False)
            self.issue_button.clicked.connect(self.issue)
            self.layout.addWidget(self.issue_button)
            self.reader_filter.changed.connect(self.refresh_readers)
            self.reader.currentIndexChanged.connect(self.update_issue_state)
            self.table.itemSelectionChanged.connect(self.update_issue_state)
            self.days.valueChanged.connect(self.update_issue_state)
        self.search.textChanged.connect(self.refresh_books)
        self.available.toggled.connect(self.refresh_books)
        self.genre.currentIndexChanged.connect(self.refresh_books)
        self.refresh()

    def refresh_readers(self):
        previous = self.reader.currentData()
        rows = self.reader_filter.rows()
        self.reader.blockSignals(True)
        self.reader.clear()
        self.reader.addItem('Выберите читателя из результатов поиска', None)
        for row in rows:
            self.reader.addItem(f"№{row['id']} — {row['full_name']} · {row['phone']}", row['id'])
        self.reader.setCurrentIndex(max(0, self.reader.findData(previous)))
        self.reader.blockSignals(False)
        self.reader.setEnabled(bool(rows))
        self.reader_hint.setText(f'Найдено читателей: {len(rows)}. Выбор выполняется в списке ниже поиска.' if rows else 'Читатели не найдены. Проверьте запрос или зарегистрируйте читателя.')
        self.update_issue_state()

    def set_reader(self, ticket):
        self.reader_filter.field.setCurrentIndex(0)
        self.reader_search.clear()
        self.refresh_readers()
        index = self.reader.findData(ticket)
        if index > 0:
            self.reader.setCurrentIndex(index)

    def refresh(self):
        if self.issuing:
            self.refresh_readers()
        self.refresh_books()

    def refresh_books(self):
        rows = []
        for source in db.search_books(self.search.text(), self.available.isChecked(), self.genre.currentData()):
            row = dict(source)
            row['state'] = 'В наличии' if row['available'] else 'Выдана до ' + display_date(row['due_date'])
            rows.append(row)
        self.table.populate(BOOK_COLUMNS, rows, 'copy_id')
        self.count.setText(f'Найдено экземпляров: {len(rows)}' if rows else 'Книги не найдены. Измените поиск или фильтры.')

    def update_issue_state(self):
        row = self.table.selected_record()
        ready = bool(row and row['available'] and self.reader.currentData() is not None)
        self.issue_button.setEnabled(ready)
        if row and not row['available']:
            self.review.setText('Экземпляр уже выдан. Выберите книгу в наличии.')
        elif ready:
            due = date.today() + timedelta(days=self.days.value())
            self.review.setText(f"К выдаче: «{row['title']}», инв. №{row['copy_id']}.\n{self.reader.currentText()}. Вернуть до {display_date(due.isoformat())}.")
        else:
            self.review.setText('Выберите читателя и доступный экземпляр.')

    def issue(self):
        row, reader_id = self.table.selected_record(), self.reader.currentData()
        if not row or not row['available'] or reader_id is None:
            self.show_message('Выберите читателя и доступный экземпляр.', error=True)
            return
        reader_text = self.reader.currentText()
        due = (date.today() + timedelta(days=self.days.value())).isoformat()
        if not self.confirm('Подтверждение выдачи', f"Выдать «{row['title']}»?\nИнвентарный №{row['copy_id']}\nЧитатель: {reader_text}\nСрок возврата: {display_date(due)}"):
            return
        def action():
            saved_due = db.issue_book(row['copy_id'], reader_id, self.user['id'], self.days.value())
            return f"Выдано: «{row['title']}», инв. №{row['copy_id']}. Читатель: {reader_text}. Вернуть до {display_date(saved_due)}."
        self.run_action(action)


class ReturnPage(Page):
    def __init__(self, user):
        super().__init__('Отдача — возврат книг')
        self.user = user
        self.search = QLineEdit()
        self.search.setMaxLength(200)
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText('Точный инвентарный номер, название или ФИО читателя')
        self.overdue = QCheckBox('Только просроченные')
        bar = QHBoxLayout()
        bar.addWidget(self.search, 1)
        bar.addWidget(self.overdue)
        self.layout.addLayout(bar)
        self.table = Table(sort_column=5)
        self.layout.addWidget(self.table)
        self.count = QLabel()
        self.layout.addWidget(self.count)
        self.accept_button = QPushButton('Принять книгу')
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.accept_book)
        self.layout.addWidget(self.accept_button)
        self.table.itemSelectionChanged.connect(lambda: self.accept_button.setEnabled(self.table.selected_id() is not None))
        self.search.textChanged.connect(self.refresh)
        self.overdue.toggled.connect(self.refresh)
        self.refresh()

    def refresh(self):
        text = db.py_lower(self.search.text())
        number = text.lstrip('№# ')
        rows = []
        for row in db.get_issued():
            if self.overdue.isChecked() and row['due_date'] >= date.today().isoformat():
                continue
            if number.isdecimal():
                match = row['copy_id'] == db.number_value(number)
            else:
                combined = db.py_lower(row['title'] + ' ' + row['full_name'])
                match = all(token in combined for token in text.split())
            if match:
                rows.append(row)
        self.table.populate(ISSUED_LAYOUT.columns, rows, 'copy_id')
        self.count.setText(f'Выданных экземпляров: {len(rows)}' if rows else 'Выданные книги не найдены. Проверьте поиск и фильтры.')

    def accept_book(self):
        row = self.table.selected_record()
        if not row:
            self.show_message('Выберите выданный экземпляр в таблице.', error=True)
            return
        if not self.confirm('Подтверждение возврата', f"Принять «{row['title']}»?\nИнвентарный №{row['copy_id']}\nЧитатель: {row['full_name']}, билет №{row['ticket']}\nСрок возврата: {display_date(row['due_date'])}"):
            return
        def action():
            db.return_book(row['copy_id'], self.user['id'], expected_loan_id=row['loan_id'])
            return f"Принято: «{row['title']}», инв. №{row['copy_id']}, от {row['full_name']}. Возврат записан в журнал."
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
            value = QLabel(display_date(reader[key]) if key.endswith('_date') else str(reader[key]))
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details.addRow(caption, value)
        layout.addLayout(details)
        overdue = sum(loan['days_late'] > 0 for loan in loans)
        self.summary = QLabel(f'Книг на руках: {len(loans)}. Просрочено: {overdue}.')
        layout.addWidget(self.summary)
        tabs = QTabWidget()
        self.loans = Table(sort_column=2)
        self.loans.populate([('copy_id', 'Инв. №'), ('title', 'Название'),
                             ('due_date', 'Срок возврата'), ('days_late', 'Просрочка, дней')], loans)
        self.history = Table(sort_column=0, descending=True)
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


class ReaderRegistrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ticket = None
        self.setWindowTitle('Регистрация читателя')
        self.setMinimumWidth(520)
        self.fields = [QLineEdit() for _ in range(3)]
        for field in self.fields:
            field.setClearButtonEnabled(True)
        self.fields[0].setPlaceholderText('Фамилия, имя, отчество')
        self.fields[1].setPlaceholderText('+7 (900) 123-45-67')
        self.fields[2].setPlaceholderText('Адрес проживания')
        self.birth = QDateEdit()
        self.birth.setCalendarPopup(True)
        self.birth.setDisplayFormat('dd.MM.yyyy')
        self.birth.setMinimumDate(QDate(1, 1, 1))
        self.birth.setMaximumDate(QDate.currentDate())
        self.birth.setSpecialValueText('Укажите дату рождения')
        self.birth.setDate(self.birth.minimumDate())
        self.birth.calendarWidget().installEventFilter(self)
        form = QFormLayout()
        for caption, field in zip(('ФИО:', 'Телефон:', 'Адрес:'), self.fields):
            form.addRow(caption, field)
        form.addRow('Дата рождения:', self.birth)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Заполните все поля. Номер билета будет присвоен после сохранения.'))
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setObjectName('error')
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        cancel = QPushButton('Отмена')
        cancel.setObjectName('secondaryButton')
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton('Зарегистрировать')
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.fields[0].setFocus()

    def eventFilter(self, watched, event):
        if watched is self.birth.calendarWidget() and event.type() == QEvent.Type.Show and self.birth.date() == self.birth.minimumDate():
            today = QDate.currentDate()
            QTimer.singleShot(0, lambda: self.birth.calendarWidget().setCurrentPage(today.year() - 20, today.month()))
        return super().eventFilter(watched, event)

    def save(self):
        for field in self.fields:
            if not field.text().strip():
                self.error.setText('Заполните ФИО, телефон и адрес.')
                field.setFocus()
                return
        if self.birth.date() == self.birth.minimumDate():
            self.error.setText('Укажите дату рождения.')
            self.birth.setFocus()
            return
        self.save_button.setEnabled(False)
        try:
            self.ticket = db.add_reader(*(f.text() for f in self.fields), self.birth.date().toString('yyyy-MM-dd'))
        except (ValueError, sqlite3.Error) as error:
            self.error.setText(str(error) if isinstance(error, ValueError) else 'Не удалось зарегистрировать читателя. Повторите сохранение.')
            self.save_button.setEnabled(True)
            return
        self.accept()


class ReadersPage(Page):
    reader_selected = pyqtSignal(int)

    def __init__(self):
        super().__init__('Читатели')
        self.reader_filter = ReaderSearch()
        self.search = self.reader_filter.input
        self.layout.addWidget(self.reader_filter)
        self.table = Table(sort_column=1)
        self.layout.addWidget(self.table)
        self.count = QLabel()
        self.layout.addWidget(self.count)
        bar = QHBoxLayout()
        self.card_button = QPushButton('Карточка читателя')
        self.card_button.clicked.connect(self.open_card)
        self.choose_button = QPushButton('Выбрать для выдачи')
        self.choose_button.clicked.connect(self.choose_reader)
        register = QPushButton('Зарегистрировать читателя')
        register.clicked.connect(self.register)
        for button in (register, self.card_button, self.choose_button):
            bar.addWidget(button)
        self.layout.addLayout(bar)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        self.table.cellDoubleClicked.connect(self.open_card)
        self.reader_filter.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        rows = self.reader_filter.rows()
        self.table.populate([('id', 'Билет'), ('full_name', 'ФИО'), ('phone', 'Телефон'),
                             ('address', 'Адрес'), ('birth_date', 'Дата рождения'), ('loan_count', 'На руках')], rows, 'id')
        self.count.setText(f'Найдено читателей: {len(rows)}' if rows else 'Читатели не найдены. Измените поиск или зарегистрируйте нового читателя.')

    def update_buttons(self):
        selected = self.table.selected_id() is not None
        self.card_button.setEnabled(selected)
        self.choose_button.setEnabled(selected)

    def choose_reader(self):
        ticket = self.table.selected_id()
        if ticket is not None:
            self.reader_selected.emit(ticket)

    def open_card(self, *_):
        reader_id = self.table.selected_id()
        if reader_id is None:
            self.show_message('Выберите читателя в таблице.', error=True)
            return
        try:
            card = db.get_reader_card(reader_id)
        except (ValueError, sqlite3.Error) as error:
            self.show_message(str(error) if isinstance(error, ValueError) else 'Не удалось открыть карточку читателя.', error=True)
            return
        ReaderCardDialog(card, self).exec()

    def register(self):
        dialog = ReaderRegistrationDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reader_filter.field.setCurrentIndex(0)
            self.search.clear()
            self.refresh()
            self.table.select_id(dialog.ticket)
            self.show_message(f'Читатель зарегистрирован. Номер билета: {dialog.ticket}. Можно открыть карточку или выбрать его для выдачи.')


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
        self.year.setRange(0, date.today().year)
        self.year.setSpecialValueText('Укажите год')
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
        if not self.title.text().strip() or not self.authors.selectedItems() or not self.year.value():
            self.show_message('Укажите название, авторов и год издания.', error=True)
            return
        if not self.confirm('Пополнение фонда', f'Добавить «{self.title.text().strip()}»?\nГод: {self.year.value()}\nЭкземпляров: {self.copies.value()}'):
            return
        def action():
            db.add_book(self.title.text(), self.genre.currentData(), [item.data(Qt.ItemDataRole.UserRole) for item in self.authors.selectedItems()], self.year.value(), self.copies.value(), self.user['id'])
            caption, count = self.title.text().strip(), self.copies.value()
            self.title.clear()
            self.authors.clearSelection()
            self.year.setValue(0)
            self.copies.setValue(1)
            return f'Добавлена книга «{caption}». Экземпляров: {count}. Они доступны в поиске и выдаче.'
        self.run_action(action)

    def backup(self):
        filename = datetime.now().strftime('library-backup-%Y%m%d-%H%M%S.db')
        path, _ = QFileDialog.getSaveFileName(self, 'Резервная копия', filename, 'SQLite (*.db)')
        if path:
            def action():
                try:
                    db.backup_database(path, self.user['id'])
                except OSError:
                    raise ValueError('Не удалось записать копию. Выберите доступную папку.') from None
                return 'Резервная копия создана: ' + path
            self.run_action(action)
