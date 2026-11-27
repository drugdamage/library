"""Проверки сигналов форм без рабочего файла БД и без показа окон."""
import csv
from datetime import date, timedelta
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import Qt, QDate, QPoint
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtTest import QTest
import database as db
from main import apply_light_theme
from reports import BOOK_FORMULAR, DEBTORS, READER_FORMULAR
from ui.common import Table, RAW_ROLE
from ui.main_window import MainWindow
from ui.report_page import ReportSubjectDialog, ReportsPage
from ui.workflows import CatalogPage, ReaderCardDialog, ReaderRegistrationDialog, ReadersPage, ReturnPage, AdminPage


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'ui.db')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        db.init_db()
        self.user = db.check_login('lib', '1111')
        confirmation = patch('ui.common.Page.confirm', return_value=True)
        self.confirm = confirmation.start()
        self.addCleanup(confirmation.stop)

    def test_all_sections_and_role(self):
        window = MainWindow(db.check_login('admin', '1234'))
        for name in ('Выдача', 'Отдача', 'Отчёты', 'Поиск книг', 'Читатели', 'Администрирование'):
            window.open_named(name)
            self.assertTrue(window.pages.currentIndex() > 0)
            self.app.processEvents()
        window.open_section(0)
        self.assertEqual(window.home.cards['copies'].number.text(), '10')
        window.deleteLater()
        librarian = MainWindow(self.user)
        librarian.open_named('Администрирование')
        self.assertEqual(librarian.pages.currentIndex(), 0)
        librarian.deleteLater()

    def test_search_issue_return_signals(self):
        page = CatalogPage(self.user, issuing=True)
        page.search.setText('СТРУ')
        self.assertEqual(page.table.rowCount(), 2)
        page.genre.setCurrentText('Фантастика')
        self.assertEqual(page.table.rowCount(), 2)
        page.search.clear()
        page.genre.setCurrentIndex(0)
        page.table.selectRow(0)
        copy_id = page.table.selected_id()
        page.days.setValue(21)
        page.set_reader(1)
        page.issue()
        self.assertEqual(db.get_stats()['issued'], 4)
        self.assertEqual(db.get_history(1)[0]['copy_id'], copy_id)
        self.assertEqual(db.get_history(1)[0]['due_date'], (date.today() + timedelta(days=21)).isoformat())
        returned = ReturnPage(self.user)
        returned.search.setText(str(copy_id))
        index = next(i for i in range(returned.table.rowCount()) if int(returned.table.item(i, 0).text()) == copy_id)
        returned.table.selectRow(index)
        returned.accept_book()
        self.assertEqual(db.get_stats()['issued'], 3)
        page.deleteLater()
        returned.deleteLater()

    def test_reader_form_validation_and_registration(self):
        page = ReadersPage()
        dialog = ReaderRegistrationDialog()
        dialog.save()
        self.assertEqual(len(db.get_readers()), 3)
        for field, value in zip(dialog.fields, ('Новый читатель', '89001234567', 'Адрес')):
            field.setText(value)
        dialog.save()
        self.assertIn('дату рождения', dialog.error.text())
        dialog.birth.setDate(QDate(2000, 1, 1))
        dialog.save()
        self.assertEqual(len(db.get_readers()), 4)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        page.search.setText('несуществующий')
        with patch('ui.workflows.ReaderRegistrationDialog', return_value=dialog), patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Accepted):
            page.register()
        self.assertEqual(page.table.selected_id(), dialog.ticket)
        self.assertIn('Номер билета:', page.message.text())
        page.deleteLater()
        dialog.deleteLater()

    def test_reader_card_opens_correct_ticket_after_sort_and_filter(self):
        page = ReadersPage()
        self.assertFalse(page.card_button.isEnabled())
        page.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        page.table.selectRow(0)
        self.assertTrue(page.card_button.isEnabled())
        with patch('ui.workflows.ReaderCardDialog') as dialog:
            page.card_button.click()
            self.assertEqual(dialog.call_args.args[0]['reader']['id'], 3)
            dialog.return_value.exec.assert_called_once()
            page.search.setText('Смирнов')
            page.table.selectRow(0)
            page.table.cellDoubleClicked.emit(0, 0)
            self.assertEqual(dialog.call_args.args[0]['reader']['id'], 1)
        page.search.setText('несуществующий читатель')
        self.assertFalse(page.card_button.isEnabled())
        page.deleteLater()

    def test_reader_card_shows_active_overdue_but_not_historical_overdue(self):
        card = ReaderCardDialog(db.get_reader_card(3))
        self.assertEqual(card.summary.text(), 'Книг на руках: 1. Просрочено: 1.')
        self.assertEqual(card.loans.rowCount(), 1)
        self.assertEqual(card.history.rowCount(), 3)
        self.assertEqual(card.loans.item(0, 0).foreground().color(), QColor('#a32424'))
        db.return_book(9, 2)
        refreshed = ReaderCardDialog(db.get_reader_card(3))
        self.assertEqual(refreshed.summary.text(), 'Книг на руках: 0. Просрочено: 0.')
        self.assertEqual(refreshed.history.rowCount(), 4)
        for row in range(refreshed.history.rowCount()):
            self.assertNotEqual(refreshed.history.item(row, 0).foreground().color(), QColor('#a32424'))
        card.deleteLater()
        refreshed.deleteLater()

    def test_light_theme_keeps_controls_readable_with_dark_system_palette(self):
        original_palette = self.app.palette()
        original_style = self.app.style().objectName()
        original_sheet = self.app.styleSheet()

        def restore_theme():
            self.app.setStyleSheet('')
            self.app.setStyle(original_style)
            self.app.setPalette(original_palette)
            self.app.setStyleSheet(original_sheet)

        self.addCleanup(restore_theme)
        self.app.setStyleSheet('')
        dark = QPalette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base,
                     QPalette.ColorRole.AlternateBase, QPalette.ColorRole.Button):
            dark.setColor(role, QColor('#171717'))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                     QPalette.ColorRole.ButtonText):
            dark.setColor(role, QColor('#ffffff'))
        self.app.setPalette(dark)
        apply_light_theme(self.app)

        def luminance(color):
            def channel(value):
                return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            return sum(weight * channel(value) for weight, value in
                       zip((0.2126, 0.7152, 0.0722), (color.redF(), color.greenF(), color.blueF())))

        window = MainWindow(self.user)
        self.addCleanup(window.deleteLater)
        window.open_named('Выдача')
        page = window.pages.currentWidget()
        readers = ReaderRegistrationDialog()
        self.addCleanup(readers.deleteLater)
        for widget in (page.table, page.table.horizontalHeader(), page.reader,
                       page.reader.view(), page.days, readers.birth, window.statusBar()):
            widget.ensurePolished()
            palette = widget.palette()
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                for background, foreground in (
                    (QPalette.ColorRole.Base, QPalette.ColorRole.Text),
                    (QPalette.ColorRole.AlternateBase, QPalette.ColorRole.Text),
                    (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText),
                    (QPalette.ColorRole.Button, QPalette.ColorRole.ButtonText),
                    (QPalette.ColorRole.Highlight, QPalette.ColorRole.HighlightedText),
                ):
                    a = luminance(palette.color(group, background))
                    b = luminance(palette.color(group, foreground))
                    with self.subTest(widget=type(widget).__name__, group=group.name, role=background.name):
                        self.assertGreaterEqual((max(a, b) + 0.05) / (min(a, b) + 0.05), 4.5)
                self.assertGreater(luminance(palette.color(group, QPalette.ColorRole.Base)), 0.8)

    def test_issue_requires_explicit_reader_and_keeps_it_during_book_search(self):
        page = CatalogPage(self.user, issuing=True)
        self.assertIsNone(page.reader.currentData())
        page.table.selectRow(0)
        self.assertFalse(page.issue_button.isEnabled())
        page.set_reader(1)
        self.assertTrue(page.issue_button.isEnabled())
        page.search.setText('Пикник')
        self.assertEqual(page.reader.currentData(), 1)
        self.assertFalse(page.issue_button.isEnabled())
        page.table.selectRow(0)
        self.assertTrue(page.issue_button.isEnabled())
        page.reader_search.setText('Кузнецова')
        self.assertIsNone(page.reader.currentData())
        self.assertFalse(page.issue_button.isEnabled())
        page.reader.setCurrentIndex(1)
        self.assertEqual(page.reader.currentData(), 2)
        page.reader_search.clear()
        self.assertEqual(page.reader.currentData(), 2)
        page.table.clearSelection()
        self.assertIsNone(page.table.selected_id())
        self.assertFalse(page.issue_button.isEnabled())
        page.deleteLater()

    def test_cancelling_issue_and_return_keeps_database(self):
        self.confirm.return_value = False
        page = CatalogPage(self.user, issuing=True)
        page.set_reader(1)
        page.table.select_id(1)
        before = len(db.get_history(-1))
        page.issue()
        details = self.confirm.call_args.args[1]
        self.assertIn('Инвентарный №1', details)
        self.assertIn('Смирнов', details)
        returned = ReturnPage(self.user)
        returned.table.select_id(2)
        returned.accept_book()
        self.assertEqual(len(db.get_history(-1)), before)
        self.assertEqual(db.get_stats()['issued'], 3)
        page.deleteLater()
        returned.deleteLater()

    def test_navigation_returns_to_context_and_passes_reader_to_issue(self):
        window = MainWindow(self.user)
        window.open_named('Выдача')
        window.open_named('Читатели')
        self.assertIn('Выдача', window.back.text())
        window.go_back()
        self.assertIsInstance(window.pages.currentWidget(), CatalogPage)
        window.open_named('Читатели')
        readers = window.pages.currentWidget()
        readers.table.select_id(2)
        readers.choose_button.click()
        self.assertIsInstance(window.pages.currentWidget(), CatalogPage)
        self.assertEqual(window.pages.currentWidget().reader.currentData(), 2)
        window.go_back()
        self.assertEqual(window.pages.currentIndex(), 0)
        window.deleteLater()

    def test_stale_return_refreshes_list_without_returning_new_loan(self):
        page = ReturnPage(self.user)
        page.table.select_id(2)
        db.return_book(2, 2)
        db.issue_book(2, 2, 2)
        page.accept_book()
        self.assertIn('Выдача изменилась', page.message.text())
        self.assertFalse(page.accept_button.isEnabled())
        self.assertEqual(next(r for r in db.get_issued() if r['copy_id'] == 2)['ticket'], 2)
        page.deleteLater()

    def test_report_export_preserves_sorted_raw_dates_and_history_is_not_overdue(self):
        page = ReportsPage()
        page.table.sortItems(5, Qt.SortOrder.DescendingOrder)
        path = Path(self.temp.name) / 'sorted.csv'
        expected = [page.table.item(row, 5).data(RAW_ROLE) for row in range(page.table.rowCount())]
        with patch('ui.report_page.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV (*.csv)')):
            page.export()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream, delimiter=';'))
        self.assertEqual([row[5] for row in rows[1:]], expected)
        page.kind.setCurrentText('Журнал операций')
        for row in range(page.table.rowCount()):
            self.assertNotEqual(page.table.item(row, 0).foreground().color(), QColor('#a32424'))
        page.deleteLater()

    def test_report_filter_and_sort_control_exported_debtors(self):
        due = (date.today() - timedelta(days=4)).isoformat()
        with db.connect() as conn:
            conn.execute('UPDATE copies SET due_date = ? WHERE id = 5', (due,))
        page = ReportsPage()
        self.addCleanup(page.deleteLater)
        page.kind.setCurrentText(DEBTORS)
        page.days_filter.setText('>=')
        self.assertEqual(page.table.rowCount(), 0)
        self.assertFalse(page.export_button.isEnabled())
        self.assertIn('Введите целое число', page.message.text())

        page.days_filter.setText('>=4')
        page.sort_order.setCurrentIndex(0)
        self.assertEqual([page.table.item(row, 6).data(RAW_ROLE) for row in range(2)], [4, 5])
        page.kind.setCurrentText('Журнал операций')
        self.assertEqual(page.table.rowCount(), 5)
        page.kind.setCurrentText(DEBTORS)
        page.refresh()
        self.assertEqual(page.sort_field.currentData(), 'days_late')
        self.assertEqual(page.sort_order.currentIndex(), 0)

        path = Path(self.temp.name) / 'должники.csv'
        with patch('ui.report_page.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV')):
            page.export()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter=';'))
        self.assertEqual([row['Просрочка, дней'] for row in rows], ['4', '5'])

    def test_book_formular_choice_and_inventory_scope_apply_to_both_sections(self):
        page = ReportsPage()
        self.addCleanup(page.deleteLater)
        page.kind.setCurrentText(BOOK_FORMULAR)
        self.assertFalse(page.export_button.isEnabled())
        dialog = ReportSubjectDialog(BOOK_FORMULAR, None, page)
        dialog.book_mode.setCurrentIndex(1)
        self.assertFalse(dialog.choose_button.isEnabled())
        dialog.search.setText('№2')
        self.assertEqual(dialog.table.rowCount(), 1)
        dialog.table.selectRow(0)
        dialog.choose_button.click()
        with patch('ui.report_page.ReportSubjectDialog', return_value=dialog), \
                patch.object(dialog, 'exec', return_value=dialog.result()):
            page.choose_subject_button.click()
        self.assertEqual(page.table.rowCount(), 2)
        page.sort_order.setCurrentIndex(1)
        self.assertEqual([page.table.item(row, 0).data(RAW_ROLE) for row in range(2)], [2, 1])

        db.issue_book(1, 3, 2)
        page.refresh()
        page.part.setCurrentIndex(1)
        self.assertEqual(page.table.rowCount(), 2)
        page.copy_scope.setCurrentIndex(page.copy_scope.findData(2))
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 2).data(RAW_ROLE), 2)
        self.assertNotEqual(page.table.item(0, 0).foreground().color(), QColor('#a32424'))
        page.part.setCurrentIndex(0)
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 0).data(RAW_ROLE), 2)
        page.copy_scope.setCurrentIndex(0)
        page.table.cellDoubleClicked.emit(0, 0)
        self.assertEqual(page.copy_scope.currentData(), 2)
        self.assertEqual(page.part.currentIndex(), 1)
        self.assertEqual(page.table.rowCount(), 1)

    def test_select_copy_opens_history_and_exports_only_that_inventory_number(self):
        db.add_book('2', 1, [1], 2005, 1, 1)
        db.issue_book(1, 3, 2)
        db.return_book(2, 2)
        db.issue_book(2, 2, 2)

        page = ReportsPage()
        self.addCleanup(page.deleteLater)
        page.kind.setCurrentText(BOOK_FORMULAR)
        dialog = ReportSubjectDialog(BOOK_FORMULAR, None, page)
        dialog.search.setText('война и мир')
        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertFalse(dialog.choose_button.isEnabled())
        dialog.search.setText('2')
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.selected_id(), 2)
        dialog.search.setText('999')
        self.assertFalse(dialog.choose_button.isEnabled())
        self.assertIn('не найден', dialog.count.text())
        dialog.search.setText('Инв. №002')
        dialog.choose_button.click()
        with patch('ui.report_page.ReportSubjectDialog', return_value=dialog), \
                patch.object(dialog, 'exec', return_value=dialog.result()):
            page.choose_subject_button.click()

        self.assertEqual(page.part.currentIndex(), 1)
        self.assertEqual(page.copy_scope.currentData(), 2)
        self.assertIn('Инв. №2 · На руках', page.summary.text())
        self.assertIn('билет №2', page.summary.text())
        page.refresh()
        self.assertEqual(page.table.rowCount(), 3)

        path = Path(self.temp.name) / 'копия.csv'
        with patch('ui.report_page.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV')) as save:
            page.export_button.click()
        self.assertIn('Инв. №2', save.call_args.args[2])
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter=';'))
        self.assertEqual({row['Инв. №'] for row in rows}, {'2'})
        self.assertCountEqual(
            [(row['Билет'], row['Операция']) for row in rows],
            [('1', 'выдача'), ('1', 'возврат'), ('2', 'выдача')],
        )

    def test_reader_formular_refreshes_loans_and_exports_only_its_history(self):
        page = ReportsPage()
        self.addCleanup(page.deleteLater)
        page.kind.setCurrentText(READER_FORMULAR)
        dialog = ReportSubjectDialog(READER_FORMULAR, None, page)
        dialog.search.input.setText('№3')
        dialog.table.selectRow(0)
        dialog.choose_button.click()
        with patch('ui.report_page.ReportSubjectDialog', return_value=dialog), \
                patch.object(dialog, 'exec', return_value=dialog.result()):
            page.choose_subject_button.click()
        self.assertEqual(page.table.rowCount(), 1)
        db.return_book(9, 2)
        db.issue_book(9, 1, 2)
        page.refresh()
        self.assertEqual(page.table.rowCount(), 0)
        self.assertIn('нет книг на руках', page.count.text())

        page.part.setCurrentIndex(1)
        self.assertEqual(page.table.rowCount(), 4)
        page.table.sortItems(2, Qt.SortOrder.DescendingOrder)
        self.assertEqual(page.sort_field.currentData(), 'copy_id')
        self.assertEqual(page.sort_order.currentIndex(), 1)
        path = Path(self.temp.name) / 'формуляр читателя.csv'
        with patch('ui.report_page.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV')):
            page.export()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter=';'))
        self.assertEqual({row['Билет'] for row in rows}, {'3'})
        self.assertEqual([row['Инв. №'] for row in rows], ['9', '9', '3', '3'])

    def test_date_sort_and_selection_reset(self):
        table = Table()
        table.populate([('id', 'Билет'), ('birth_date', 'Дата рождения')],
                       [{'id': 1, 'birth_date': '2000-12-31'}, {'id': 10, 'birth_date': '2001-01-01'}], 'id')
        table.sortItems(1, Qt.SortOrder.AscendingOrder)
        self.assertEqual(table.item(0, 1).text(), '31.12.2000')
        table.select_id(10)
        self.assertEqual(table.selected_id(), 10)
        table.populate([('id', 'Билет')], [{'id': 1}], 'id')
        self.assertIsNone(table.selected_id())
        table.deleteLater()

    def test_birth_calendar_opens_near_current_year_without_prefilling_birth(self):
        dialog = ReaderRegistrationDialog()
        dialog.show()
        self.app.processEvents()
        QTest.mouseClick(dialog.birth, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(dialog.birth.width() - 8, dialog.birth.height() // 2))
        self.app.processEvents()
        self.assertEqual(dialog.birth.calendarWidget().yearShown(), QDate.currentDate().year() - 20)
        self.assertEqual(dialog.birth.date(), dialog.birth.minimumDate())
        dialog.birth.calendarWidget().window().hide()
        dialog.hide()
        dialog.deleteLater()

    def test_admin_add_requires_fields_and_confirmation_then_resets_form(self):
        page = AdminPage(db.check_login('admin', '1234'))
        before = db.get_stats()
        page.add()
        self.assertEqual(db.get_stats(), before)
        page.title.setText('Новый фонд')
        page.authors.item(0).setSelected(True)
        page.year.setValue(2020)
        page.copies.setValue(2)
        self.confirm.return_value = False
        page.add()
        self.assertEqual(db.get_stats(), before)
        self.confirm.return_value = True
        page.add()
        self.assertEqual(db.get_stats()['copies'], before['copies'] + 2)
        self.assertEqual(page.title.text(), '')
        self.assertEqual(page.authors.selectedItems(), [])
        self.assertEqual(page.year.value(), 0)
        page.deleteLater()


if __name__ == '__main__':
    unittest.main()
