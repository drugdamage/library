"""Проверки сигналов форм без рабочего файла БД и без показа окон."""
from datetime import date, timedelta
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
import database as db
from ui.main_window import MainWindow
from ui.workflows import CatalogPage, ReadersPage, ReturnPage


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


if __name__ == '__main__':
    unittest.main()
