import sqlite3
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path

# база лежит в той же папке что и этот файл
DB_PATH = Path(__file__).with_name("library.db")
LOAN_DAYS = 14  # на сколько дней выдаём книгу


# lower() в sqlite не работает с русскими буквами, поэтому делаем свою функцию на python
def py_lower(text):
    return " ".join(str(text or "").casefold().replace("ё", "е").split())


def phone_digits(text):
    digits = "".join(c for c in str(text or "") if c.isdecimal())
    return "7" + digits[1:] if len(digits) == 11 and digits.startswith("8") else digits


def number_value(text):
    text = text.lstrip("№# ").lstrip("0") or "0"
    return int(text) if text.isdecimal() and len(text) <= 19 and int(text) < 2**63 else -1


class LibraryConnection(sqlite3.Connection):
    """Контекст завершает транзакцию и обязательно закрывает соединение."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    conn = sqlite3.connect(DB_PATH, factory=LibraryConnection)
    conn.row_factory = sqlite3.Row  # чтобы обращаться к столбцам по имени, например row["title"]
    conn.execute("PRAGMA foreign_keys = ON")  # без этого sqlite не проверяет связи между таблицами
    conn.create_function("py_lower", 1, py_lower)  # теперь py_lower можно писать прямо в запросе
    conn.create_function("phone_digits", 1, phone_digits)
    return conn


def hash_password(password):
    # в базе храним не пароль а его хеш
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_tables():
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS genres (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS authors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                last_name   TEXT NOT NULL,
                first_name  TEXT,
                middle_name TEXT
            );
            CREATE TABLE IF NOT EXISTS books (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT NOT NULL,
                genre_id INTEGER NOT NULL REFERENCES genres(id),
                year     INTEGER
            );
            -- связь многие ко многим: у книги может быть несколько авторов и наоборот
            CREATE TABLE IF NOT EXISTS book_authors (
                book_id   INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                author_id INTEGER NOT NULL REFERENCES authors(id),
                PRIMARY KEY (book_id, author_id)
            );
            -- id читателя это и есть номер читательского билета
            CREATE TABLE IF NOT EXISTS readers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name  TEXT NOT NULL,
                phone      TEXT NOT NULL,
                address    TEXT NOT NULL,
                birth_date TEXT NOT NULL,  -- гггг-мм-дд
                reg_date   TEXT NOT NULL DEFAULT (date('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS staff (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name     TEXT NOT NULL,
                position      TEXT,
                role          TEXT NOT NULL CHECK (role IN ('администратор', 'библиотекарь')),
                login         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            -- id экземпляра это инвентарный номер
            -- если reader_id пустой значит книга в библиотеке
            CREATE TABLE IF NOT EXISTS copies (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id   INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                reader_id INTEGER REFERENCES readers(id),
                due_date  TEXT
            );
            -- журнал: кто, что, когда и какая операция
            CREATE TABLE IF NOT EXISTS operations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                op_type   TEXT NOT NULL CHECK (op_type IN ('выдача', 'возврат')),
                op_date   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                copy_id   INTEGER NOT NULL REFERENCES copies(id) ON DELETE CASCADE,
                reader_id INTEGER NOT NULL REFERENCES readers(id),
                staff_id  INTEGER NOT NULL REFERENCES staff(id),
                due_date  TEXT  -- заполняется только при выдаче
            );
        """)


def fill_test_data():
    with connect() as conn:
        # если книги уже есть, значит база заполнена и второй раз не надо
        if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] > 0:
            return

        genres = ["Роман", "Фантастика", "Детектив", "Поэзия"]
        conn.executemany("INSERT INTO genres (name) VALUES (?)", [(g,) for g in genres])

        authors = [
            ("Толстой", "Лев", "Николаевич"),
            ("Достоевский", "Фёдор", "Михайлович"),
            ("Стругацкий", "Аркадий", "Натанович"),
            ("Стругацкий", "Борис", "Натанович"),
            ("Кристи", "Агата", None),
            ("Пушкин", "Александр", "Сергеевич"),
        ]
        conn.executemany(
            "INSERT INTO authors (last_name, first_name, middle_name) VALUES (?, ?, ?)", authors
        )

        # название, номер жанра, год, номера авторов
        books = [
            ("Война и мир", 1, 1869, [1]),
            ("Преступление и наказание", 1, 1866, [2]),
            ("Пикник на обочине", 2, 1972, [3, 4]),
            ("Трудно быть богом", 2, 1964, [3, 4]),
            ("Убийство в Восточном экспрессе", 3, 1934, [5]),
            ("Евгений Онегин", 4, 1833, [6]),
        ]
        for title, genre_id, year, author_ids in books:
            cur = conn.execute(
                "INSERT INTO books (title, genre_id, year) VALUES (?, ?, ?)", (title, genre_id, year)
            )
            for author_id in author_ids:
                conn.execute(
                    "INSERT INTO book_authors (book_id, author_id) VALUES (?, ?)", (cur.lastrowid, author_id)
                )

        # у каждой книги 1-2 экземпляра, тут номера книг
        copies = [1, 1, 2, 2, 3, 3, 4, 5, 5, 6]
        conn.executemany("INSERT INTO copies (book_id) VALUES (?)", [(b,) for b in copies])

        conn.executemany(
            "INSERT INTO staff (full_name, position, role, login, password_hash) VALUES (?, ?, ?, ?, ?)",
            [
                ("Иванова Анна Сергеевна", "Заведующая", "администратор", "admin", hash_password("1234")),
                ("Петров Олег Игоревич", "Библиотекарь", "библиотекарь", "lib", hash_password("1111")),
            ],
        )

        conn.executemany(
            "INSERT INTO readers (full_name, phone, address, birth_date) VALUES (?, ?, ?, ?)",
            [
                ("Смирнов Игорь Павлович", "89001112233", "ул. Ленина, 10, кв. 5", "2001-03-15"),
                ("Кузнецова Мария Олеговна", "89004445566", "ул. Мира, 3, кв. 12", "1998-07-02"),
                ("Орлов Денис Андреевич", "89007778899", "пр. Победы, 45, кв. 7", "2004-11-21"),
            ],
        )

    # выдаю через свои же функции, чтобы заодно заполнился журнал
    # Исторические сроки задаются только для начальных тестовых данных.
    _issue_book(2, 1, 2, (date.today() - timedelta(days=5)).isoformat())
    _issue_book(9, 3, 2, (date.today() - timedelta(days=2)).isoformat())
    issue_book(copy_id=5, reader_id=2, staff_id=2)
    issue_book(copy_id=3, reader_id=3, staff_id=2)
    return_book(copy_id=3, staff_id=2)  # чтобы в журнале был и возврат


def check_login(login, password):
    # вернёт сотрудника или None если логин или пароль не подходят
    with connect() as conn:
        return conn.execute(
            "SELECT id, full_name, role FROM staff WHERE login = ? AND password_hash = ?",
            (login.strip(), hash_password(password)),
        ).fetchone()


def get_genres():
    with connect() as conn:
        return conn.execute("SELECT id, name FROM genres ORDER BY name").fetchall()


def get_readers():
    return search_readers()


def search_readers(text="", field="all"):
    """ФИО — все введённые слова; билет — точный номер; телефон — цифры."""
    if field not in ("all", "name", "ticket", "phone"):
        raise ValueError("Неизвестный вид поиска читателей.")
    query = py_lower(text)
    conditions, params = [], []
    if query:
        ticket = query.lstrip("№# ")
        if field == "ticket" or (field == "all" and ticket.isdecimal()):
            conditions.append("r.id = ?")
            params.append(number_value(ticket))
        elif field == "phone":
            digits = phone_digits(query)
            if digits.startswith("8") and len(digits) >= 4:
                conditions.append("(instr(phone_digits(r.phone), ?) > 0 OR instr(phone_digits(r.phone), ?) > 0)")
                params.extend((digits, "7" + digits[1:]))
            elif digits:
                conditions.append("instr(phone_digits(r.phone), ?) > 0")
                params.append(digits)
            else:
                conditions.append("0")
        else:
            for token in query.split():
                conditions.append("instr(py_lower(r.full_name), ?) > 0")
                params.append(token)
    with connect() as conn:
        return conn.execute(
            "SELECT r.*, (SELECT count(*) FROM copies c WHERE c.reader_id = r.id) AS loan_count "
            "FROM readers r WHERE " + (" AND ".join(conditions) or "1") +
            " ORDER BY py_lower(r.full_name), r.id", params,
        ).fetchall()


def get_reader_card(reader_id):
    """Данные, текущие книги и полный журнал одного читателя из одного снимка БД."""
    with connect() as conn:
        conn.execute("BEGIN")
        reader = conn.execute("SELECT * FROM readers WHERE id = ?", (reader_id,)).fetchone()
        if reader is None:
            raise ValueError("Читатель не найден.")
        loans = conn.execute("""
            SELECT c.id AS copy_id, b.title, c.due_date,
                   CASE WHEN c.due_date < date('now', 'localtime')
                        THEN CAST(julianday(date('now', 'localtime')) - julianday(c.due_date) AS INTEGER)
                        ELSE 0 END AS days_late
              FROM copies c
              JOIN books b ON b.id = c.book_id
             WHERE c.reader_id = ?
             ORDER BY c.due_date, c.id
        """, (reader_id,)).fetchall()
        history = conn.execute("""
            SELECT o.op_date, o.op_type, o.copy_id, b.title,
                   s.full_name AS staff, o.due_date
              FROM operations o
              JOIN copies c ON c.id = o.copy_id
              JOIN books b ON b.id = c.book_id
              JOIN staff s ON s.id = o.staff_id
             WHERE o.reader_id = ?
             ORDER BY o.id DESC
        """, (reader_id,)).fetchall()
        return {"reader": reader, "loans": loans, "history": history}


def add_reader(full_name, phone, address, birth_date):
    full_name = " ".join(full_name.split())
    phone, address = phone.strip(), " ".join(address.split())
    if not all((full_name, phone, address)):
        raise ValueError("Заполните ФИО, телефон и адрес.")
    if not re.fullmatch(r"\+?[\d()\s-]+", phone) or not 7 <= len(phone_digits(phone)) <= 15:
        raise ValueError("Телефон должен содержать от 7 до 15 цифр; допустимы +, пробелы, скобки и дефисы.")
    try:
        born = date.fromisoformat(birth_date)
    except (ValueError, TypeError):
        raise ValueError("Укажите дату рождения в формате ГГГГ-ММ-ДД.") from None
    if born > date.today():
        raise ValueError("Дата рождения не может быть в будущем.")
    birth_date = born.isoformat()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM readers WHERE py_lower(full_name) = ? AND birth_date = ? "
            "AND phone_digits(phone) = ?",
            (py_lower(full_name), birth_date, phone_digits(phone)),
        ).fetchone()
        if existing:
            raise ValueError(f"Этот читатель уже зарегистрирован. Номер билета: {existing['id']}.")
        cur = conn.execute(
            "INSERT INTO readers (full_name, phone, address, birth_date) VALUES (?, ?, ?, ?)",
            (full_name.strip(), phone.strip(), address.strip(), birth_date),
        )
        return cur.lastrowid  # это номер билета нового читателя


# ищем сразу по названию, авторам и жанру
# внешний select нужен, чтобы в where можно было использовать authors и available
SEARCH_SQL = """
    SELECT * FROM (
        SELECT c.id AS copy_id,
               b.title,
               (SELECT group_concat(a.last_name || ' ' || substr(a.first_name, 1, 1) || '.', ', ')
                  FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                 WHERE ba.book_id = b.id) AS authors,
               (SELECT group_concat(a.last_name || ' ' || coalesce(a.first_name, '') || ' ' || coalesce(a.middle_name, ''), ' ')
                  FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                 WHERE ba.book_id = b.id) AS author_names,
               g.name AS genre, g.id AS genre_id,
               b.year,
               c.reader_id IS NULL AS available,
               c.due_date
          FROM copies c
          JOIN books b ON b.id = c.book_id
          JOIN genres g ON g.id = b.genre_id
    )
"""


def search_books(text="", only_available=False, genre_id=None):
    query = py_lower(text)
    conditions, params = ["(available = 1 OR ? = 0)"], [int(only_available)]
    if genre_id is not None:
        conditions.append("genre_id = ?")
        params.append(genre_id)
    if query.lstrip("№# ").isdecimal():
        number = query.lstrip("№# ")
        copy_id = number_value(number)
        if query.startswith(("№", "#")):
            conditions.append("copy_id = ?")
            params.append(copy_id)
        else:
            conditions.append("(copy_id = ? OR instr(py_lower(title), ?) > 0)")
            params.extend((copy_id, query))
    else:
        for token in query.split():
            conditions.append("instr(py_lower(title || ' ' || coalesce(author_names, '') || ' ' || genre), ?) > 0")
            params.append(token)
    with connect() as conn:
        return conn.execute(SEARCH_SQL + " WHERE " + " AND ".join(conditions) +
                            " ORDER BY py_lower(title), copy_id", params).fetchall()


def issue_book(copy_id, reader_id, staff_id, days=LOAN_DAYS):
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Срок выдачи должен быть от 1 до 365 дней.")
    due = (date.today() + timedelta(days=days)).isoformat()
    return _issue_book(copy_id, reader_id, staff_id, due)


def _issue_book(copy_id, reader_id, staff_id, due):
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM staff WHERE id = ?", (staff_id,)).fetchone():
            raise ValueError("Сотрудник не найден.")
        row = conn.execute("SELECT reader_id FROM copies WHERE id = ?", (copy_id,)).fetchone()
        if row is None:
            raise ValueError("Такого экземпляра нет.")
        if row["reader_id"] is not None:
            raise ValueError("Этот экземпляр уже выдан.")
        if not conn.execute("SELECT 1 FROM readers WHERE id = ?", (reader_id,)).fetchone():
            raise ValueError("Читатель не найден.")
        conn.execute(
            "UPDATE copies SET reader_id = ?, due_date = ? WHERE id = ?", (reader_id, due, copy_id)
        )
        conn.execute(
            "INSERT INTO operations (op_type, copy_id, reader_id, staff_id, due_date) VALUES ('выдача', ?, ?, ?, ?)",
            (copy_id, reader_id, staff_id, due),
        )
    return due


def return_book(copy_id, staff_id, expected_loan_id=None):
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM staff WHERE id = ?", (staff_id,)).fetchone():
            raise ValueError("Сотрудник не найден.")
        row = conn.execute("SELECT reader_id FROM copies WHERE id = ?", (copy_id,)).fetchone()
        if row is None or row["reader_id"] is None:
            raise ValueError("Этот экземпляр не числится выданным.")
        if expected_loan_id is not None:
            loan = conn.execute(
                "SELECT max(id) FROM operations WHERE copy_id = ? AND op_type = 'выдача'", (copy_id,)
            ).fetchone()[0]
            if loan != expected_loan_id:
                raise ValueError("Выдача изменилась с момента выбора книги. Обновите список и выберите экземпляр заново.")
        # сначала пишем в журнал, пока ещё знаем у кого была книга
        conn.execute(
            "INSERT INTO operations (op_type, copy_id, reader_id, staff_id) VALUES ('возврат', ?, ?, ?)",
            (copy_id, row["reader_id"], staff_id),
        )
        conn.execute(
            "UPDATE copies SET reader_id = NULL, due_date = NULL WHERE id = ?", (copy_id,)
        )


def get_issued():
    # join с readers оставляет только выданные экземпляры
    with connect() as conn:
        return conn.execute("""
            SELECT c.id AS copy_id, b.title, r.id AS ticket, r.full_name, r.phone, c.due_date,
                   (SELECT max(o.id) FROM operations o WHERE o.copy_id = c.id AND o.op_type = 'выдача') AS loan_id
              FROM copies c
              JOIN books b ON b.id = c.book_id
              JOIN readers r ON r.id = c.reader_id
             ORDER BY c.due_date
        """).fetchall()


def get_debtors():
    with connect() as conn:
        return conn.execute("""
            SELECT r.id AS ticket, r.full_name, r.phone, c.id AS copy_id, b.title, c.due_date,
                   CAST(julianday(date('now', 'localtime')) - julianday(c.due_date) AS INTEGER) AS days_late
              FROM copies c
              JOIN books b ON b.id = c.book_id
              JOIN readers r ON r.id = c.reader_id
             WHERE c.due_date < date('now', 'localtime')
             ORDER BY days_late DESC
        """).fetchall()


def get_history(limit=100):
    with connect() as conn:
        return conn.execute("""
            SELECT o.op_date, o.op_type, o.copy_id, b.title,
                   r.full_name AS reader, s.full_name AS staff, o.due_date
              FROM operations o
              JOIN copies c ON c.id = o.copy_id
              JOIN books b ON b.id = c.book_id
              JOIN readers r ON r.id = o.reader_id
              JOIN staff s ON s.id = o.staff_id
             ORDER BY o.id DESC
             LIMIT ?
        """, (limit,)).fetchall()


def get_stats():
    # цифры для главного экрана
    with connect() as conn:
        one = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            "books": one("SELECT COUNT(*) FROM books"),
            "copies": one("SELECT COUNT(*) FROM copies"),
            "issued": one("SELECT COUNT(*) FROM copies WHERE reader_id IS NOT NULL"),
            "debtors": one("SELECT COUNT(*) FROM copies WHERE due_date < date('now', 'localtime')"),
        }


def init_db():
    create_tables()
    fill_test_data()




def get_authors():
    with connect() as conn:
        return conn.execute("SELECT id, last_name || ' ' || coalesce(first_name, '') AS name FROM authors ORDER BY last_name").fetchall()


def add_book(title, genre_id, author_ids, year, copies, staff_id):
    """Книга, её авторы и экземпляры добавляются как единое целое."""
    if not title.strip() or not author_ids:
        raise ValueError('Введите название и выберите хотя бы одного автора.')
    if not 1 <= copies <= 100 or not 1 <= year <= date.today().year:
        raise ValueError('Проверьте год издания и количество экземпляров (1–100).')
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        staff = conn.execute('SELECT role FROM staff WHERE id = ?', (staff_id,)).fetchone()
        if not staff or staff['role'] != 'администратор':
            raise ValueError('Добавлять книги может только администратор.')
        book_id = conn.execute('INSERT INTO books(title, genre_id, year) VALUES (?, ?, ?)', (title.strip(), genre_id, year)).lastrowid
        conn.executemany('INSERT INTO book_authors(book_id, author_id) VALUES (?, ?)', [(book_id, a) for a in set(author_ids)])
        conn.executemany('INSERT INTO copies(book_id) VALUES (?)', [(book_id,)] * copies)
        return book_id


def backup_database(path, staff_id):
    target = Path(path).resolve()
    if target == DB_PATH.resolve():
        raise ValueError('Резервная копия должна иметь другое имя файла.')
    # Не перезаписываем случайно выбранную существующую БД.
    if target.exists():
        raise ValueError('Файл уже существует. Выберите новое имя резервной копии.')
    with connect() as source:
        staff = source.execute('SELECT role FROM staff WHERE id = ?', (staff_id,)).fetchone()
        if not staff or staff['role'] != 'администратор':
            raise ValueError('Создавать резервную копию может только администратор.')
        try:
            # x исключает гонку с созданием файла другим процессом.
            with target.open('xb'):
                pass
        except FileExistsError:
            raise ValueError('Файл уже существует. Выберите новое имя.') from None
        try:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
            finally:
                destination.close()
        except Exception:
            target.unlink(missing_ok=True)
            raise


# проверка без окон: python database.py
if __name__ == "__main__":
    init_db()
    print("база:", DB_PATH)
    print("статистика:", get_stats())
    user = check_login("admin", "1234")
    print("вход admin:", dict(user) if user else "ошибка")
    print("вход с неверным паролем:", check_login("admin", "0000"))  # должно быть None
    print("\nпоиск 'стру':")
    for r in search_books("стру"):
        state = "в наличии" if r["available"] else f"выдана до {r['due_date']}"
        print(f"  {r['copy_id']:>3}  {r['title']:<32} {r['authors']:<28} {state}")
    print("\nдолжники:")
    for r in get_debtors():
        print(f"  {r['full_name']:<26} {r['title']:<32} просрочка {r['days_late']} дн.")
    print("\nжурнал:")
    for r in get_history(10):
        print(f"  {r['op_date']}  {r['op_type']:<8} №{r['copy_id']:<3} {r['title']:<32} {r['reader']}")
