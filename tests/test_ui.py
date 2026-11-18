"""Проверки сигналов форм без рабочего файла БД и без показа окон."""
from datetime import date, timedelta
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
import database as db
from main import apply_light_theme
from ui.main_window import MainWindow
from ui.workflows import CatalogPage, ReaderCardDialog, ReadersPage, ReturnPage


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
        page.register()
        self.assertEqual(len(db.get_readers()), 3)
        for field, value in zip(page.fields, ('Новый читатель', '12345', 'Адрес')):
            field.setText(value)
        page.register()
        self.assertEqual(len(db.get_readers()), 4)
        self.assertIn('Номер билета:', page.message.text())
        page.deleteLater()

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
        readers = ReadersPage()
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


if __name__ == '__main__':
    unittest.main()
