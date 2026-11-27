"""Проверки работают только с временной БД, не затрагивая library.db."""
import csv
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database as db
from reports import REPORTS, export_csv, filter_debtors


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
        ticket = db.add_reader(' Новый читатель ', '89001234567', 'Адрес', '2000-01-01')
        self.assertEqual(next(r for r in db.get_readers() if r['id'] == ticket)['full_name'], 'Новый читатель')

    def test_reader_card_separates_current_loans_and_history(self):
        card = db.get_reader_card(3)
        self.assertEqual(card['reader']['id'], 3)
        self.assertEqual([r['copy_id'] for r in card['loans']], [9])
        self.assertEqual(card['loans'][0]['days_late'], 2)
        self.assertEqual([r['op_type'] for r in card['history']], ['возврат', 'выдача', 'выдача'])
        self.assertEqual({r['copy_id'] for r in card['history']}, {3, 9})

    def test_reader_card_tracks_return_and_next_borrower(self):
        db.return_book(2, 2)
        db.issue_book(2, 2, 2)
        old_reader = db.get_reader_card(1)
        new_reader = db.get_reader_card(2)
        self.assertEqual(old_reader['loans'], [])
        self.assertEqual([r['op_type'] for r in old_reader['history']], ['возврат', 'выдача'])
        self.assertEqual({r['copy_id'] for r in new_reader['loans']}, {2, 5})
        self.assertTrue(all(r['days_late'] == 0 for r in new_reader['loans']))
        self.assertEqual([r['op_type'] for r in new_reader['history']], ['выдача', 'выдача'])

    def test_reader_card_empty_missing_and_full_history(self):
        ticket = db.add_reader('Без выдач', '89001234567', 'Адрес', '2000-01-01')
        card = db.get_reader_card(ticket)
        self.assertEqual(card['loans'], [])
        self.assertEqual(card['history'], [])
        for reader_id in (999, "1 OR 1=1"):
            with self.assertRaisesRegex(ValueError, 'Читатель не найден'):
                db.get_reader_card(reader_id)
        with db.connect() as conn:
            conn.executemany(
                "INSERT INTO operations (op_type, copy_id, reader_id, staff_id) VALUES ('возврат', 1, ?, 2)",
                [(ticket,)] * 101,
            )
        self.assertEqual(len(db.get_reader_card(ticket)['history']), 101)

    def test_reports_csv_and_formula_escaping(self):
        for name, (load, layout) in REPORTS.items():
            columns = layout.columns
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

    def test_reader_search_words_tickets_and_phone(self):
        with db.connect() as conn:
            conn.execute("INSERT INTO readers(id, full_name, phone, address, birth_date) VALUES (10, 'Фёдоров Пётр Сергеевич', '89001234567', 'Адрес', '1990-01-01')")
            conn.execute("INSERT INTO readers(id, full_name, phone, address, birth_date) VALUES (11, 'Смирнов Пётр Иванович', '89007654321', 'Адрес', '1991-01-01')")
        self.assertEqual([r['id'] for r in db.search_readers('1')], [1])
        self.assertEqual([r['id'] for r in db.search_readers('№ 0010')], [10])
        self.assertEqual([r['id'] for r in db.search_readers('  пЕТР   федоров ')], [10])
        self.assertEqual([r['id'] for r in db.search_readers('+7 (900) 123-45-67', 'phone')], [10])
        self.assertEqual([r['id'] for r in db.search_readers('8 (900) 123', 'phone')], [10])
        self.assertEqual([r['id'] for r in db.search_readers('765-43', 'phone')], [11])
        self.assertEqual(len(db.search_readers('Пётр', 'name')), 2)
        for query in ('%', '_', "' OR 1=1 --", '9' * 200):
            self.assertEqual(db.search_readers(query), [])
        with self.assertRaises(ValueError):
            db.search_readers('', 'unknown')

    def test_book_search_words_inventory_and_literal_symbols(self):
        self.assertEqual(len(db.search_books('  ПИКНИК аркадий ')), 2)
        self.assertEqual(len(db.search_books('достоЕВСКИЙ федор')), 2)
        self.assertEqual([r['copy_id'] for r in db.search_books('№ 10')], [10])
        self.assertEqual(len(db.search_books('', genre_id=2)), 3)
        for query in ('%', '_', '9' * 200):
            self.assertEqual(db.search_books(query), [])
        db.add_book('1984', 1, [1], 1949, 1, 1)
        self.assertEqual(db.search_books('1984')[0]['title'], '1984')

    def test_registration_normalizes_and_rejects_duplicate(self):
        ticket = db.add_reader('  Фёдоров   Пётр ', '8 (900) 123-45-67', ' ул. Мира,  5 ', '1990-01-01')
        reader = db.get_reader_card(ticket)['reader']
        self.assertEqual(reader['full_name'], 'Фёдоров Пётр')
        self.assertEqual(reader['address'], 'ул. Мира, 5')
        with self.assertRaisesRegex(ValueError, f'Номер билета: {ticket}'):
            db.add_reader('ФЕДОРОВ ПЕТР', '+7 900 1234567', 'Другой адрес', '1990-01-01')
        self.assertEqual(len(db.get_readers()), 4)

    def test_registration_phone_and_birth_validation(self):
        before = len(db.get_readers())
        for phone in ('123', 'телефон', '+7 abc 9001234567', '1' * 16):
            with self.assertRaisesRegex(ValueError, 'Телефон'):
                db.add_reader('Новый читатель', phone, 'Адрес', '1990-01-01')
        for born in ('bad', '2999-01-01'):
            with self.assertRaises(ValueError):
                db.add_reader('Новый читатель', '89001234567', 'Адрес', born)
        self.assertEqual(len(db.get_readers()), before)

    def test_issue_rejects_invalid_days_without_changes(self):
        before = len(db.get_history(-1))
        for days in (0, -1, 366, True, 1.5, '14'):
            with self.assertRaisesRegex(ValueError, 'Срок выдачи'):
                db.issue_book(1, 1, 2, days)
        self.assertEqual(len(db.get_history(-1)), before)
        self.assertTrue(db.search_books('№1')[0]['available'])

    def test_stale_return_does_not_close_new_loan(self):
        previous_loan = next(r for r in db.get_issued() if r['copy_id'] == 2)['loan_id']
        db.return_book(2, 2)
        db.issue_book(2, 2, 2)
        before = len(db.get_history(-1))
        with self.assertRaisesRegex(ValueError, 'Выдача изменилась'):
            db.return_book(2, 2, expected_loan_id=previous_loan)
        self.assertEqual(len(db.get_history(-1)), before)
        self.assertEqual(next(r for r in db.get_issued() if r['copy_id'] == 2)['ticket'], 2)

    def test_book_formular_keeps_editions_and_copy_history_separate(self):
        copy = db.search_books('№2')[0]
        other_edition = db.add_book(copy['title'], 1, [1], 1990, 1, 1)
        matching = db.search_editions('война толстой')
        self.assertEqual({row['book_id'] for row in matching}, {copy['book_id'], other_edition})
        self.assertEqual([row['book_id'] for row in db.search_editions('№2')], [copy['book_id']])

        db.return_book(2, 2)
        db.issue_book(1, 3, 2)
        report = db.get_book_formular(copy['book_id'])
        stock = {row['copy_id']: row for row in report['copies']}
        self.assertEqual(set(stock), {1, 2})
        self.assertEqual(stock[1]['ticket'], 3)
        self.assertEqual(stock[1]['state'], 'На руках')
        self.assertEqual(stock[2]['state'], 'В наличии')
        self.assertIsNone(stock[2]['days_late'])
        self.assertEqual(
            [(row['copy_id'], row['ticket'], row['op_type']) for row in report['history']],
            [(1, 3, 'выдача'), (2, 1, 'возврат'), (2, 1, 'выдача')],
        )
        scoped = db.get_book_formular(copy['book_id'], copy_id=2)
        self.assertEqual(scoped['copy']['state'], 'В наличии')
        self.assertEqual(
            [(row['copy_id'], row['ticket'], row['op_type']) for row in scoped['history']],
            [(2, 1, 'возврат'), (2, 1, 'выдача')],
        )
        with self.assertRaisesRegex(ValueError, 'Экземпляр №2 не найден'):
            db.get_book_formular(other_edition, copy_id=2)
        self.assertEqual(db.get_book_formular(other_edition)['history'], [])

    def test_overdue_filter_compares_integer_days_at_boundary(self):
        today = date.today()
        due = (today - timedelta(days=4)).isoformat()
        with db.connect() as conn:
            conn.execute('UPDATE copies SET due_date = ? WHERE id = 5', (due,))
        rows = db.get_debtors()
        for expression, expected in (
            ('', [5, 4, 2]), ('<4 дней', [2]), ('4', [4]), ('= 4', [4]),
            ('>4', [5]), ('<= 4', [4, 2]), ('≥4', [5, 4]), ('0', []),
        ):
            with self.subTest(expression=expression):
                self.assertEqual([row['days_late'] for row in filter_debtors(rows, expression)], expected)
        for invalid in ('<', '-4', '4,5', '4 OR 1=1', '>>4'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                filter_debtors(rows, invalid)


if __name__ == '__main__':
    unittest.main()
