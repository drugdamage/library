"""Проверки работают только с временной БД, не затрагивая library.db."""
import csv
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database as db
from reports import REPORTS, export_csv


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        db.init_db()

    def test_seed_and_login(self):
        before = db.get_stats()
        db.init_db()
        self.assertEqual(before, db.get_stats())
        self.assertEqual(before['copies'], 10)
        self.assertEqual(db.check_login('admin', '1234')['role'], 'администратор')
        self.assertIsNone(db.check_login('admin', 'wrong'))

    def test_unicode_search_and_availability(self):
        self.assertEqual(len(db.search_books('СТРУ')), 3)
        self.assertEqual(len(db.search_books('стру', True)), 2)
        self.assertEqual(len(db.search_books("' OR 1=1 --")), 0)

    def test_issue_return_and_history(self):
        before = len(db.get_history(-1))
        due = db.issue_book(1, 1, 2, 7)
        self.assertEqual(due, (date.today() + timedelta(days=7)).isoformat())
        with self.assertRaises(ValueError):
            db.issue_book(1, 2, 2)
        db.return_book(1, 2)
        with self.assertRaises(ValueError):
            db.return_book(1, 2)
        self.assertEqual(len(db.get_history(-1)), before + 2)
        self.assertEqual(db.get_stats()['issued'], 3)

    def test_invalid_foreign_keys_leave_no_changes(self):
        before = db.get_stats()
        for args in ((1, 999, 2), (1, 1, 999), (999, 1, 2)):
            with self.assertRaises(ValueError):
                db.issue_book(*args)
        self.assertEqual(db.get_stats(), before)

    def test_journal_failure_rolls_back_issue(self):
        with db.connect() as conn:
            conn.execute("CREATE TRIGGER fail_log BEFORE INSERT ON operations BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        before = db.get_stats()
        with self.assertRaises(sqlite3.IntegrityError):
            db.issue_book(1, 1, 2)
        self.assertEqual(db.get_stats(), before)

    def test_journal_failure_preserves_loan_on_return(self):
        with db.connect() as conn:
            conn.execute("CREATE TRIGGER fail_log BEFORE INSERT ON operations BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        before = db.get_stats()
        with self.assertRaises(sqlite3.IntegrityError):
            db.return_book(2, 2)
        self.assertEqual(db.get_stats(), before)

    def test_reader_validation(self):
        for args in (('', '1', 'address', '2000-01-01'), ('Name', '1', 'address', 'bad'), ('Name', '1', 'address', '2999-01-01')):
            with self.assertRaises(ValueError):
                db.add_reader(*args)
        ticket = db.add_reader(' Новый читатель ', '123', 'Адрес', '2000-01-01')
        self.assertEqual(next(r for r in db.get_readers() if r['id'] == ticket)['full_name'], 'Новый читатель')

    def test_reports_csv_and_formula_escaping(self):
        for name, (load, columns) in REPORTS.items():
            rows = load()
            path = Path(self.temp.name) / (name + '.csv')
            export_csv(path, columns, rows)
            with path.open(encoding='utf-8-sig', newline='') as stream:
                saved = list(csv.reader(stream, delimiter=';'))
            self.assertEqual(len(saved), len(rows) + 1)
            self.assertEqual(saved[0], [caption for _, caption in columns])
        path = Path(self.temp.name) / 'escape.csv'
        export_csv(path, [('name', 'Название')], [{'name': '=1+1'}, {'name': 'Текст; с "кавычками"\nстрока'}])
        with path.open(encoding='utf-8-sig', newline='') as stream:
            saved = list(csv.reader(stream, delimiter=';'))
        self.assertEqual(saved[1][0], "'=1+1")
        self.assertEqual(saved[2][0], 'Текст; с "кавычками"\nстрока')

    def test_multi_author_book_permissions_and_rollback(self):
        before = db.get_stats()
        with self.assertRaises(ValueError):
            db.add_book('Новая книга', 1, [1, 2], 2020, 3, 2)
        self.assertEqual(db.get_stats(), before)
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_book('Ошибка автора', 1, [999], 2020, 3, 1)
        self.assertEqual(db.get_stats(), before)
        db.add_book('Новая книга', 1, [1, 2], 2020, 3, 1)
        self.assertEqual(db.get_stats()['copies'], before['copies'] + 3)
        rows = db.search_books('новая книга')
        self.assertEqual(len(rows), 3)
        self.assertIn('Толстой', rows[0]['authors'])
        self.assertIn('Достоевский', rows[0]['authors'])

    def test_backup_is_complete_and_does_not_overwrite(self):
        target = Path(self.temp.name) / 'backup.db'
        with self.assertRaises(ValueError):
            db.backup_database(target, 2)
        self.assertFalse(target.exists())
        db.backup_database(target, 1)
        conn = sqlite3.connect(target)
        try:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('SELECT count(*) FROM copies').fetchone()[0], 10)
        finally:
            conn.close()
        with self.assertRaises(ValueError):
            db.backup_database(target, 1)
        with self.assertRaises(ValueError):
            db.backup_database(db.DB_PATH, 1)


if __name__ == '__main__':
    unittest.main()
