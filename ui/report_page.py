"""Просмотр, фильтрация и экспорт отчётов."""
import re
import sqlite3

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTabBar, QVBoxLayout, QWidget,
)

import database as db
from reports import (
    BOOK_FORMULAR, DEBTORS, FORMULARS, READER_FORMULAR, REPORTS,
    export_csv, filter_debtors,
)
from ui.common import Page, RAW_ROLE, ReaderSearch, Table, display_date


class ReportSubjectDialog(QDialog):
    def __init__(self, report, selected_id, parent, *, selected_copy_id=None):
        super().__init__(parent)
        self.is_book = report == BOOK_FORMULAR
        self.subject_id = None
        self.copy_id = None
        self.setWindowTitle('Выбор экземпляра или издания' if self.is_book else 'Выбор читателя')
        self.resize(780, 450)

        layout = QVBoxLayout(self)
        if self.is_book:
            self.book_mode = QTabBar()
            self.book_mode.setAccessibleName('Объект формуляра')
            self.book_mode.setExpanding(False)
            self.book_mode.addTab('Экземпляры')
            self.book_mode.addTab('Издания целиком')
            self.book_mode.currentChanged.connect(self.change_book_mode)
            layout.addWidget(self.book_mode)
            self.search = QLineEdit()
            self.search.setClearButtonEnabled(True)
            self.search.setMaxLength(200)
            self.search.setAccessibleName('Поиск книги')
            self.search.textChanged.connect(self.refresh)
            search_widget = self.search
        else:
            self.search = ReaderSearch()
            self.search.changed.connect(self.refresh)
            search_widget = self.search.input
        layout.addWidget(self.search)
        self.table = Table(sort_column=0 if self.is_book else 1)
        layout.addWidget(self.table, 1)
        self.count = QLabel()
        layout.addWidget(self.count)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton('Отмена')
        cancel.setObjectName('secondaryButton')
        cancel.clicked.connect(self.reject)
        self.choose_button = QPushButton('Открыть формуляр' if self.is_book else 'Выбрать')
        self.choose_button.setDefault(True)
        self.choose_button.clicked.connect(self.choose)
        actions.addWidget(cancel)
        actions.addWidget(self.choose_button)
        layout.addLayout(actions)
        self.table.itemSelectionChanged.connect(self.update_choice)
        self.table.cellDoubleClicked.connect(self.choose)

        if self.is_book:
            self.change_book_mode()
            if selected_copy_id is not None:
                self.table.select_id(selected_copy_id)
        else:
            self.refresh()
            if selected_id is not None:
                self.table.select_id(selected_id)
        search_widget.setFocus()

    @property
    def choosing_copy(self):
        return self.is_book and self.book_mode.currentIndex() == 0

    def change_book_mode(self):
        self.search.setPlaceholderText(
            'Инвентарный номер, название или автор' if self.choosing_copy
            else 'Название, автор или инвентарный номер'
        )
        self.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.refresh()

    def refresh(self):
        exact_number = False
        if self.choosing_copy:
            columns = (('copy_id', 'Инв. №'), ('title', 'Название'), ('authors', 'Авторы'),
                       ('year', 'Год'), ('state', 'Состояние'))
            key, stretch_column = 'copy_id', 1
            query = self.search.text().strip()
            number = db.py_lower(query).removeprefix('инв.').lstrip('№# ')
            exact_number = number.isdecimal()
            if exact_number:
                query = f'№{number}'
        elif self.is_book:
            columns = (('title', 'Название'), ('authors', 'Авторы'), ('genre', 'Жанр'),
                       ('year', 'Год'), ('copy_count', 'Экземпляров'))
            key, stretch_column = 'book_id', 0
        else:
            columns = (('id', 'Билет'), ('full_name', 'ФИО'), ('phone', 'Телефон'),
                       ('birth_date', 'Дата рождения'), ('loan_count', 'На руках'))
            key, stretch_column = 'id', 1
        try:
            if self.choosing_copy:
                rows = [
                    dict(row, state='В наличии' if row['available'] else 'На руках')
                    for row in db.search_books(query)
                ]
            elif self.is_book:
                rows = db.search_editions(self.search.text())
            else:
                rows = self.search.rows()
        except sqlite3.Error:
            rows = []
            message = 'Не удалось загрузить список. Повторите поиск.'
        else:
            message = f'Найдено: {len(rows)}' if rows else 'Ничего не найдено. Измените запрос.'
            if exact_number and not rows:
                message = 'Экземпляр с таким инвентарным номером не найден.'
        self.table.populate(columns, rows, key, mark_overdue=False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
        self.count.setText(message)
        if exact_number and len(rows) == 1:
            self.table.select_id(rows[0]['copy_id'])

    def update_choice(self):
        self.choose_button.setEnabled(self.table.selected_id() is not None)

    def choose(self):
        row = self.table.selected_record()
        if row is None:
            return
        self.subject_id = row['book_id'] if self.is_book else row['id']
        self.copy_id = row['copy_id'] if self.choosing_copy else None
        self.accept()


class ReportsPage(Page):
    def __init__(self):
        super().__init__('Отчёты')
        self.subjects = {BOOK_FORMULAR: None, READER_FORMULAR: None}
        self.book_copy_id = None
        self.sorting = {}
        self.view_key = None

        toolbar = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItems([*REPORTS, *FORMULARS])
        kind_label = QLabel('Отчёт')
        kind_label.setBuddy(self.kind)
        toolbar.addWidget(kind_label)
        toolbar.addWidget(self.kind)
        toolbar.addStretch(1)
        self.sort_field = QComboBox()
        self.sort_field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        sort_label = QLabel('Сортировка')
        sort_label.setBuddy(self.sort_field)
        toolbar.addWidget(sort_label)
        toolbar.addWidget(self.sort_field)
        self.sort_order = QComboBox()
        self.sort_order.setAccessibleName('Направление сортировки')
        self.sort_order.addItem('По возрастанию', Qt.SortOrder.AscendingOrder)
        self.sort_order.addItem('По убыванию', Qt.SortOrder.DescendingOrder)
        toolbar.addWidget(self.sort_order)
        self.layout.addLayout(toolbar)

        self.debtor_tools = QWidget()
        debtor_row = QHBoxLayout(self.debtor_tools)
        debtor_row.setContentsMargins(0, 0, 0, 0)
        self.days_filter = QLineEdit()
        self.days_filter.setClearButtonEnabled(True)
        self.days_filter.setPlaceholderText('Например, <4, 4 или >4')
        self.days_filter.setToolTip('Пустое поле показывает все просрочки. Также можно ввести <=4 или >=4.')
        days_label = QLabel('Просрочка, дней')
        days_label.setBuddy(self.days_filter)
        debtor_row.addWidget(days_label)
        debtor_row.addWidget(self.days_filter, 1)
        self.layout.addWidget(self.debtor_tools)

        self.formular_tools = QWidget()
        formular_layout = QVBoxLayout(self.formular_tools)
        formular_layout.setContentsMargins(0, 0, 0, 0)
        subject_row = QHBoxLayout()
        self.choose_subject_button = QPushButton()
        self.choose_subject_button.setObjectName('secondaryButton')
        subject_row.addWidget(self.choose_subject_button)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        subject_row.addWidget(self.summary, 1)
        self.copy_scope = QComboBox()
        self.copy_scope.setAccessibleName('Экземпляры в формуляре книги')
        subject_row.addWidget(self.copy_scope)
        formular_layout.addLayout(subject_row)
        self.part = QTabBar()
        self.part.setAccessibleName('Раздел формуляра')
        self.part.setExpanding(False)
        self.part.addTab('Экземпляры')
        self.part.addTab('История операций')
        formular_layout.addWidget(self.part)
        self.layout.addWidget(self.formular_tools)

        self.table = Table()
        self.layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.count = QLabel()
        self.count.setWordWrap(True)
        footer.addWidget(self.count, 1)
        self.export_button = QPushButton('Сохранить CSV…')
        footer.addWidget(self.export_button)
        self.layout.addLayout(footer)

        self.kind.currentIndexChanged.connect(self.change_report)
        self.part.currentChanged.connect(self.render)
        self.days_filter.textChanged.connect(self.render)
        self.copy_scope.currentIndexChanged.connect(self.change_copy_scope)
        self.choose_subject_button.clicked.connect(self.choose_subject)
        self.table.cellDoubleClicked.connect(self.open_copy_history)
        self.sort_field.currentIndexChanged.connect(self.apply_sort)
        self.sort_order.currentIndexChanged.connect(self.apply_sort)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self.remember_sort)
        self.export_button.clicked.connect(self.export)
        self.change_report()

    def change_report(self):
        report = self.kind.currentText()
        self.debtor_tools.setVisible(report == DEBTORS)
        self.formular_tools.setVisible(report in FORMULARS)
        self.copy_scope.setVisible(report == BOOK_FORMULAR)
        if report in FORMULARS:
            caption = 'Выбрать экземпляр или издание…' if report == BOOK_FORMULAR else 'Выбрать читателя…'
            self.choose_subject_button.setText(caption)
            with QSignalBlocker(self.part):
                self.part.setTabText(0, FORMULARS[report][0][1])
                self.part.setCurrentIndex(1 if report == BOOK_FORMULAR and self.book_copy_id is not None else 0)
        self.refresh()

    def choose_subject(self):
        report = self.kind.currentText()
        dialog = ReportSubjectDialog(
            report, self.subjects[report], self, selected_copy_id=self.book_copy_id
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.subjects[report] = dialog.subject_id
            if report == BOOK_FORMULAR:
                self.book_copy_id = dialog.copy_id
            with QSignalBlocker(self.part):
                self.part.setCurrentIndex(1 if dialog.copy_id is not None else 0)
            self.refresh()

    def change_copy_scope(self):
        self.book_copy_id = self.copy_scope.currentData()
        self.refresh()

    def open_copy_history(self, row, _column):
        if self.view_key == (BOOK_FORMULAR, 'copies'):
            self.book_copy_id = self.table.item(row, 0).data(RAW_ROLE)
            with QSignalBlocker(self.part):
                self.part.setCurrentIndex(1)
            self.refresh()

    def refresh(self):
        report = self.kind.currentText()
        self.formular = None
        self.rows = []
        self.load_error = ''
        try:
            if report in FORMULARS:
                subject_id = self.subjects[report]
                if subject_id is not None:
                    if report == BOOK_FORMULAR:
                        self.formular = db.get_book_formular(subject_id, self.book_copy_id)
                    else:
                        self.formular = db.get_reader_card(subject_id)
            else:
                self.rows = REPORTS[report][0]()
        except ValueError as error:
            self.load_error = str(error)
        except sqlite3.Error:
            self.load_error = 'Не удалось загрузить отчёт. Попробуйте обновить его.'

        if report == BOOK_FORMULAR:
            with QSignalBlocker(self.copy_scope):
                self.copy_scope.clear()
                self.copy_scope.addItem('Все экземпляры', None)
                if self.formular:
                    for copy in self.formular['copies']:
                        self.copy_scope.addItem(f"Инв. №{copy['copy_id']}", copy['copy_id'])
                elif self.book_copy_id is not None:
                    self.copy_scope.addItem(f'Инв. №{self.book_copy_id}', self.book_copy_id)
                self.copy_scope.setCurrentIndex(max(0, self.copy_scope.findData(self.book_copy_id)))
            self.copy_scope.setEnabled(self.copy_scope.count() > 1)
        self.render()

    def formular_rows(self, report, part):
        if self.formular is None:
            self.summary.clear()
            return []

        if report == READER_FORMULAR:
            reader, loans = self.formular['reader'], self.formular['loans']
            overdue = sum(row['days_late'] > 0 for row in loans)
            self.summary.setText(
                f"Билет №{reader['id']} · {reader['full_name']}\n"
                f"Книг на руках: {len(loans)} · Просрочено: {overdue}"
            )
            return self.formular[part]

        book = self.formular['book']
        details = [f"«{book['title']}»", book['authors'], book['genre'], book['year']]
        edition = ' · '.join(str(value) for value in details if value)
        copy = self.formular['copy']
        copies = self.formular['copies']
        if copy is not None:
            status = f"Инв. №{copy['copy_id']} · {copy['state']}"
            if copy['ticket'] is not None:
                status += f" · {copy['reader']} (билет №{copy['ticket']})"
                if copy['due_date']:
                    status += f" · вернуть до {display_date(copy['due_date'])}"
            rows = [copy] if part == 'copies' else self.formular['history']
        else:
            available = sum(row['state'] == 'В наличии' for row in copies)
            status = f'Экземпляров: {len(copies)} · В наличии: {available} · На руках: {len(copies) - available}'
            rows = self.formular[part]
        self.summary.setText(f'{edition}\n{status}')
        return rows

    def render(self):
        report = self.kind.currentText()
        error = self.load_error
        count_tag = ''
        if report in FORMULARS:
            part, _, layout = FORMULARS[report][self.part.currentIndex()]
            rows = self.formular_rows(report, part)
            if self.formular is None:
                count_tag = 'Выберите экземпляр или издание.' if report == BOOK_FORMULAR else 'Выберите читателя для отчёта.'
            elif not rows:
                count_tag = {
                    'copies': 'У этой книги пока нет экземпляров.',
                    'loans': 'У читателя сейчас нет книг на руках.',
                    'history': 'Выдач и возвратов пока нет.',
                }[part]
                if part == 'history' and report == BOOK_FORMULAR and self.book_copy_id is not None:
                    count_tag = f'У экземпляра №{self.book_copy_id} пока нет выдач и возвратов.'
        else:
            part = None
            layout, rows = REPORTS[report][1], self.rows
            if report == DEBTORS:
                try:
                    rows = filter_debtors(rows, self.days_filter.text())
                except ValueError as invalid_filter:
                    error = error or str(invalid_filter)
                    rows = []
                if self.days_filter.text().strip() and not error:
                    count_tag = f'Показано просрочек: {len(rows)} из {len(self.rows)}'
        self.show_message(error, error=True)
        self.count.setText(count_tag or (f'Записей: {len(rows)}' if rows else 'Записей нет.'))
        self.export_button.setEnabled(bool(rows))
        self.sort_field.setEnabled(bool(rows))
        self.sort_order.setEnabled(bool(rows))

        self.view_key = (report, part)
        self.columns = layout.columns
        default_order = Qt.SortOrder.DescendingOrder if layout.descending else Qt.SortOrder.AscendingOrder
        sort_key, order = self.sorting.get(self.view_key, (layout.sort_key, default_order))
        column = next(i for i, (key, _) in enumerate(self.columns) if key == sort_key)
        header = self.table.horizontalHeader()
        with QSignalBlocker(self.sort_field), QSignalBlocker(self.sort_order), QSignalBlocker(header):
            self.sort_field.clear()
            for key, caption in self.columns:
                self.sort_field.addItem(caption, key)
            self.sort_field.setCurrentIndex(column)
            self.sort_order.setCurrentIndex(self.sort_order.findData(order))
            self.table.populate(self.columns, rows, mark_overdue=layout.mark_overdue, sort=(column, order))
            self.fit_columns()

    def fit_columns(self):
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for index, (key, caption) in enumerate(self.columns):
            if key in ('ticket', 'copy_id', 'year', 'due_date', 'days_late'):
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(index, header.fontMetrics().horizontalAdvance(caption) + 28)
        keys = [key for key, _ in self.columns]
        stretch_key = next((key for key in ('title', 'reader', 'full_name') if key in keys), None)
        if stretch_key is not None:
            header.setSectionResizeMode(keys.index(stretch_key), QHeaderView.ResizeMode.Stretch)
        row_mode = QHeaderView.ResizeMode.Interactive
        if self.view_key == (BOOK_FORMULAR, 'history'):
            row_mode = QHeaderView.ResizeMode.ResizeToContents
        self.table.verticalHeader().setSectionResizeMode(row_mode)

    def apply_sort(self):
        column = self.sort_field.currentIndex()
        order = self.sort_order.currentData()
        if column >= 0:
            self.table.sortItems(column, Qt.SortOrder(order))

    def remember_sort(self, column, order):
        if self.view_key is not None and 0 <= column < len(self.columns):
            self.sorting[self.view_key] = (self.columns[column][0], order)
            with QSignalBlocker(self.sort_field), QSignalBlocker(self.sort_order):
                self.sort_field.setCurrentIndex(column)
                self.sort_order.setCurrentIndex(self.sort_order.findData(order))

    def export(self):
        if not self.table.rowCount():
            return
        report = self.kind.currentText()
        filename, context = report, {}
        if report == BOOK_FORMULAR:
            book = self.formular['book']
            context = {'Книга': book['title'], 'Авторы': book['authors'], 'Год издания': book['year']}
            scope = self.copy_scope.currentText()
            title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', book['title'])[:60].strip(' .')
            filename = f'{report} — {title or "Издание"} — {scope} — {self.part.tabText(self.part.currentIndex())}'
        elif report == READER_FORMULAR:
            reader = self.formular['reader']
            context = {'Билет': reader['id'], 'Читатель': reader['full_name']}
            filename = f"{report} — билет №{reader['id']} — {self.part.tabText(self.part.currentIndex())}"
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить отчёт', filename + '.csv', 'CSV (*.csv)')
        if not path:
            return
        columns = tuple((caption, caption) for caption in context) + self.columns
        rows = [
            {**context, **{key: self.table.item(row, col).data(RAW_ROLE)
                           for col, (key, _) in enumerate(self.columns)}}
            for row in range(self.table.rowCount())
        ]
        try:
            export_csv(path, columns, rows)
        except OSError:
            self.show_message('Не удалось сохранить отчёт. Выберите доступную папку.', error=True)
        else:
            self.show_message('Отчёт сохранён: ' + path)
