# часть 1: база данных библиотеки
# тут создаются таблицы, тестовые данные и функции для работы с базой
# окна на pyqt6 будут в следующих частях и будут брать данные отсюда

import sqlite3  # встроенная в python библиотека для базы sqlite
import hashlib  # нужна чтобы хранить пароли не открытым текстом
from datetime import date, timedelta  # для дат выдачи и сроков возврата
from pathlib import Path  # удобная работа с путями к файлам

DB_PATH = Path(__file__).with_name("library.db")  # файл базы лежит рядом с этим скриптом
LOAN_DAYS = 14  # на сколько дней выдаём книгу по умолчанию


def py_lower(text):  # переводит текст в нижний регистр для поиска
    return text.lower() if text else ""  # sqlite сам не умеет нормально понижать русские буквы


def connect():  # открывает соединение с базой
    conn = sqlite3.connect(DB_PATH)  # подключаемся к файлу, если его нет он создастся
    conn.row_factory = sqlite3.Row  # теперь столбцы можно брать по имени, например row["title"]
    conn.execute("PRAGMA foreign_keys = ON")  # включаем проверку связей между таблицами
    conn.create_function("py_lower", 1, py_lower)  # даём sqlite нашу функцию для поиска без учёта регистра
    return conn  # отдаём готовое соединение


def hash_password(password):  # превращает пароль в хеш
    return hashlib.sha256(password.encode("utf-8")).hexdigest()  # в базе хранится хеш, а не сам пароль


# ---------- создание таблиц ----------

def create_tables():  # создаёт все таблицы если их ещё нет
    with connect() as conn:  # with сам сохранит изменения в конце
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS genres (                     -- жанры
                id   INTEGER PRIMARY KEY AUTOINCREMENT,             -- номер жанра, ставится сам
                name TEXT NOT NULL UNIQUE                           -- название, повторять нельзя
            );
            CREATE TABLE IF NOT EXISTS authors (                    -- авторы
                id          INTEGER PRIMARY KEY AUTOINCREMENT,      -- номер автора
                last_name   TEXT NOT NULL,                          -- фамилия обязательна
                first_name  TEXT,                                   -- имя
                middle_name TEXT                                    -- отчество, может быть пустым
            );
            CREATE TABLE IF NOT EXISTS books (                      -- книги как издания
                id       INTEGER PRIMARY KEY AUTOINCREMENT,         -- код книги
                title    TEXT NOT NULL,                             -- название
                genre_id INTEGER NOT NULL REFERENCES genres(id),    -- ссылка на жанр
                year     INTEGER                                    -- год издания
            );
            CREATE TABLE IF NOT EXISTS book_authors (               -- связь многие ко многим
                book_id   INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,  -- удалили книгу и связь пропала
                author_id INTEGER NOT NULL REFERENCES authors(id),  -- ссылка на автора
                PRIMARY KEY (book_id, author_id)                    -- пара книга автор только один раз
            );
            CREATE TABLE IF NOT EXISTS readers (                    -- читатели
                id         INTEGER PRIMARY KEY AUTOINCREMENT,       -- он же номер читательского билета
                full_name  TEXT NOT NULL,                           -- фио
                phone      TEXT NOT NULL,                           -- телефон
                address    TEXT NOT NULL,                           -- фактический адрес
                birth_date TEXT NOT NULL,                           -- дата рождения в виде гггг-мм-дд
                reg_date   TEXT NOT NULL DEFAULT (date('now', 'localtime'))  -- дата регистрации ставится сама
            );
            CREATE TABLE IF NOT EXISTS staff (                      -- сотрудники
                id            INTEGER PRIMARY KEY AUTOINCREMENT,    -- код сотрудника
                full_name     TEXT NOT NULL,                        -- фио
                position      TEXT,                                 -- должность
                role          TEXT NOT NULL CHECK (role IN ('администратор', 'библиотекарь')),  -- только две роли
                login         TEXT NOT NULL UNIQUE,                 -- логин не повторяется
                password_hash TEXT NOT NULL                         -- хеш пароля
            );
            CREATE TABLE IF NOT EXISTS copies (                     -- экземпляры на полке
                id        INTEGER PRIMARY KEY AUTOINCREMENT,        -- инвентарный номер
                book_id   INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,  -- какой книги экземпляр
                reader_id INTEGER REFERENCES readers(id),           -- у кого сейчас, пусто если в библиотеке
                due_date  TEXT                                      -- до какого числа вернуть
            );
            CREATE TABLE IF NOT EXISTS operations (                 -- журнал выдач и возвратов
                id        INTEGER PRIMARY KEY AUTOINCREMENT,        -- номер операции
                op_type   TEXT NOT NULL CHECK (op_type IN ('выдача', 'возврат')),  -- какая операция
                op_date   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),   -- когда, дата и время
                copy_id   INTEGER NOT NULL REFERENCES copies(id) ON DELETE CASCADE,  -- что выдали
                reader_id INTEGER NOT NULL REFERENCES readers(id),  -- кому
                staff_id  INTEGER NOT NULL REFERENCES staff(id),    -- кто выдал или принял
                due_date  TEXT                                      -- срок возврата, только у выдачи
            );
        """)  # конец скрипта создания таблиц


# ---------- тестовые данные ----------

def fill_test_data():  # заполняет пустую базу примерами
    with connect() as conn:  # открываем базу
        if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] > 0:  # если книги уже есть
            return  # второй раз ничего не добавляем

        genres = ["Роман", "Фантастика", "Детектив", "Поэзия"]  # список жанров
        conn.executemany("INSERT INTO genres (name) VALUES (?)", [(g,) for g in genres])  # добавляем все жанры разом

        authors = [  # фамилия, имя, отчество
            ("Толстой", "Лев", "Николаевич"),  # автор 1
            ("Достоевский", "Фёдор", "Михайлович"),  # автор 2
            ("Стругацкий", "Аркадий", "Натанович"),  # автор 3
            ("Стругацкий", "Борис", "Натанович"),  # автор 4
            ("Кристи", "Агата", None),  # автор 5, отчества нет
            ("Пушкин", "Александр", "Сергеевич"),  # автор 6
        ]  # конец списка авторов
        conn.executemany(  # добавляем авторов
            "INSERT INTO authors (last_name, first_name, middle_name) VALUES (?, ?, ?)", authors  # запрос и данные
        )  # конец вставки

        books = [  # название, номер жанра, год, номера авторов
            ("Война и мир", 1, 1869, [1]),  # один автор
            ("Преступление и наказание", 1, 1866, [2]),  # один автор
            ("Пикник на обочине", 2, 1972, [3, 4]),  # два автора
            ("Трудно быть богом", 2, 1964, [3, 4]),  # два автора
            ("Убийство в Восточном экспрессе", 3, 1934, [5]),  # детектив
            ("Евгений Онегин", 4, 1833, [6]),  # поэзия
        ]  # конец списка книг
        for title, genre_id, year, author_ids in books:  # перебираем книги по одной
            cur = conn.execute(  # добавляем книгу
                "INSERT INTO books (title, genre_id, year) VALUES (?, ?, ?)", (title, genre_id, year)  # запрос
            )  # конец вставки
            for author_id in author_ids:  # для каждого автора этой книги
                conn.execute(  # добавляем связь книга автор
                    "INSERT INTO book_authors (book_id, author_id) VALUES (?, ?)", (cur.lastrowid, author_id)  # lastrowid это номер только что добавленной книги
                )  # конец вставки

        copies = [1, 1, 2, 2, 3, 3, 4, 5, 5, 6]  # номера книг, по одному на каждый экземпляр
        conn.executemany("INSERT INTO copies (book_id) VALUES (?)", [(b,) for b in copies])  # все экземпляры пока в библиотеке

        conn.executemany(  # добавляем сотрудников
            "INSERT INTO staff (full_name, position, role, login, password_hash) VALUES (?, ?, ?, ?, ?)",  # запрос
            [  # данные сотрудников
                ("Иванова Анна Сергеевна", "Заведующая", "администратор", "admin", hash_password("1234")),  # админ
                ("Петров Олег Игоревич", "Библиотекарь", "библиотекарь", "lib", hash_password("1111")),  # библиотекарь
            ],  # конец данных
        )  # конец вставки

        conn.executemany(  # добавляем читателей
            "INSERT INTO readers (full_name, phone, address, birth_date) VALUES (?, ?, ?, ?)",  # запрос
            [  # данные читателей
                ("Смирнов Игорь Павлович", "89001112233", "ул. Ленина, 10, кв. 5", "2001-03-15"),  # читатель 1
                ("Кузнецова Мария Олеговна", "89004445566", "ул. Мира, 3, кв. 12", "1998-07-02"),  # читатель 2
                ("Орлов Денис Андреевич", "89007778899", "пр. Победы, 45, кв. 7", "2004-11-21"),  # читатель 3
            ],  # конец данных
        )  # конец вставки

    # выдачи делаем через обычные функции, чтобы журнал заполнился правильно
    issue_book(copy_id=2, reader_id=1, staff_id=2, days=-5)  # смирнов, срок уже прошёл 5 дней назад
    issue_book(copy_id=9, reader_id=3, staff_id=2, days=-2)  # орлов, тоже должник
    issue_book(copy_id=5, reader_id=2, staff_id=2)  # кузнецова, срок ещё не наступил
    issue_book(copy_id=3, reader_id=3, staff_id=2)  # орлов взял ещё одну книгу
    return_book(copy_id=3, staff_id=2)  # и вернул её, чтобы в журнале был возврат


# ---------- вход в систему ----------

def check_login(login, password):  # проверяет логин и пароль
    with connect() as conn:  # открываем базу
        return conn.execute(  # ищем сотрудника с таким логином и хешем пароля
            "SELECT id, full_name, role FROM staff WHERE login = ? AND password_hash = ?",  # знаки ? защищают от sql инъекций
            (login.strip(), hash_password(password)),  # strip убирает случайные пробелы в логине
        ).fetchone()  # вернёт сотрудника или None если не нашли


# ---------- справочники для выпадающих списков ----------

def get_genres():  # список жанров
    with connect() as conn:  # открываем базу
        return conn.execute("SELECT id, name FROM genres ORDER BY name").fetchall()  # все жанры по алфавиту


def get_readers():  # список читателей
    with connect() as conn:  # открываем базу
        return conn.execute("SELECT * FROM readers ORDER BY full_name").fetchall()  # все читатели по алфавиту


def add_reader(full_name, phone, address, birth_date):  # регистрирует нового читателя
    with connect() as conn:  # открываем базу
        cur = conn.execute(  # добавляем строку
            "INSERT INTO readers (full_name, phone, address, birth_date) VALUES (?, ?, ?, ?)",  # запрос
            (full_name.strip(), phone.strip(), address.strip(), birth_date),  # убираем лишние пробелы
        )  # конец вставки
        return cur.lastrowid  # номер нового читательского билета


# ---------- поиск книг ----------

SEARCH_SQL = """
    SELECT * FROM (                                                   -- внешний запрос нужен для фильтра
        SELECT c.id AS copy_id,                                       -- инвентарный номер
               b.title,                                               -- название
               (SELECT group_concat(a.last_name || ' ' || substr(a.first_name, 1, 1) || '.', ', ')
                  FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                 WHERE ba.book_id = b.id) AS authors,                 -- все авторы книги одной строкой
               g.name AS genre,                                       -- жанр
               b.year,                                                -- год
               c.reader_id IS NULL AS available,                      -- 1 если книга на полке
               c.due_date                                             -- срок возврата если выдана
          FROM copies c                                               -- берём экземпляры
          JOIN books b ON b.id = c.book_id                            -- к ним книги
          JOIN genres g ON g.id = b.genre_id                          -- и жанры
    )
    WHERE py_lower(title || ' ' || coalesce(authors, '') || ' ' || genre) LIKE ?  -- ищем сразу везде
      AND (available = 1 OR ? = 0)                                    -- фильтр только доступные
    ORDER BY title, copy_id                                           -- по алфавиту
"""  # конец текста запроса поиска


def search_books(text="", only_available=False):  # поиск среди всех книг или только доступных
    pattern = f"%{text.strip().lower()}%"  # % значит любые символы до и после
    with connect() as conn:  # открываем базу
        return conn.execute(SEARCH_SQL, (pattern, int(only_available))).fetchall()  # список найденных экземпляров


# ---------- выдача и возврат ----------

def issue_book(copy_id, reader_id, staff_id, days=LOAN_DAYS):  # выдаёт экземпляр читателю
    due = (date.today() + timedelta(days=days)).isoformat()  # считаем срок возврата
    with connect() as conn:  # всё внутри with выполнится целиком или не выполнится вообще
        row = conn.execute("SELECT reader_id FROM copies WHERE id = ?", (copy_id,)).fetchone()  # смотрим экземпляр
        if row is None:  # такого номера нет
            raise ValueError("Такого экземпляра нет.")  # сообщаем об ошибке
        if row["reader_id"] is not None:  # экземпляр уже у кого-то
            raise ValueError("Этот экземпляр уже выдан.")  # второй раз выдать нельзя
        conn.execute(  # отмечаем у экземпляра читателя и срок
            "UPDATE copies SET reader_id = ?, due_date = ? WHERE id = ?", (reader_id, due, copy_id)  # запрос
        )  # конец обновления
        conn.execute(  # пишем операцию в журнал
            "INSERT INTO operations (op_type, copy_id, reader_id, staff_id, due_date) VALUES ('выдача', ?, ?, ?, ?)",
            (copy_id, reader_id, staff_id, due),  # кто что кому и до какого числа
        )  # конец вставки
    return due  # возвращаем срок чтобы показать его пользователю


def return_book(copy_id, staff_id):  # принимает экземпляр обратно
    with connect() as conn:  # открываем базу
        row = conn.execute("SELECT reader_id FROM copies WHERE id = ?", (copy_id,)).fetchone()  # смотрим экземпляр
        if row is None or row["reader_id"] is None:  # нет такого или он и так в библиотеке
            raise ValueError("Этот экземпляр не числится выданным.")  # принимать нечего
        conn.execute(  # пишем возврат в журнал, читателя берём из экземпляра
            "INSERT INTO operations (op_type, copy_id, reader_id, staff_id) VALUES ('возврат', ?, ?, ?)",
            (copy_id, row["reader_id"], staff_id),  # данные операции
        )  # конец вставки
        conn.execute(  # освобождаем экземпляр
            "UPDATE copies SET reader_id = NULL, due_date = NULL WHERE id = ?", (copy_id,)  # читатель и срок пустые
        )  # конец обновления


# ---------- данные для отчётов ----------

def get_issued():  # какие книги сейчас выданы и когда вернут
    with connect() as conn:  # открываем базу
        return conn.execute("""
            SELECT c.id AS copy_id, b.title, r.id AS ticket, r.full_name, r.phone, c.due_date  -- что показываем
              FROM copies c                                    -- экземпляры
              JOIN books b ON b.id = c.book_id                 -- названия книг
              JOIN readers r ON r.id = c.reader_id             -- только выданные, у них есть читатель
             ORDER BY c.due_date                               -- сверху кто должен вернуть раньше
        """).fetchall()  # список выданных


def get_debtors():  # должники, у кого срок уже прошёл
    with connect() as conn:  # открываем базу
        return conn.execute("""
            SELECT r.id AS ticket, r.full_name, r.phone, c.id AS copy_id, b.title, c.due_date,  -- что показываем
                   CAST(julianday(date('now', 'localtime')) - julianday(c.due_date) AS INTEGER) AS days_late  -- дней просрочки
              FROM copies c                                    -- экземпляры
              JOIN books b ON b.id = c.book_id                 -- названия
              JOIN readers r ON r.id = c.reader_id             -- читатели
             WHERE c.due_date < date('now', 'localtime')       -- срок меньше сегодняшней даты
             ORDER BY days_late DESC                           -- сверху самые злостные
        """).fetchall()  # список должников


def get_history(limit=100):  # журнал операций, новые сверху
    with connect() as conn:  # открываем базу
        return conn.execute("""
            SELECT o.op_date, o.op_type, o.copy_id, b.title,   -- когда, что за операция, что
                   r.full_name AS reader, s.full_name AS staff, o.due_date  -- кому и кто
              FROM operations o                                -- журнал
              JOIN copies c ON c.id = o.copy_id                -- экземпляр
              JOIN books b ON b.id = c.book_id                 -- название
              JOIN readers r ON r.id = o.reader_id             -- читатель
              JOIN staff s ON s.id = o.staff_id                -- сотрудник
             ORDER BY o.id DESC                                -- последние операции сверху
             LIMIT ?                                           -- не больше limit строк
        """, (limit,)).fetchall()  # список операций


def get_stats():  # цифры для главного окна
    with connect() as conn:  # открываем базу
        one = lambda sql: conn.execute(sql).fetchone()[0]  # маленькая функция, достаёт одно число
        return {  # словарь с цифрами
            "books": one("SELECT COUNT(*) FROM books"),  # сколько книг
            "copies": one("SELECT COUNT(*) FROM copies"),  # сколько экземпляров
            "issued": one("SELECT COUNT(*) FROM copies WHERE reader_id IS NOT NULL"),  # сколько выдано
            "debtors": one("SELECT COUNT(*) FROM copies WHERE due_date < date('now', 'localtime')"),  # сколько просрочено
        }  # конец словаря


def init_db():  # готовит базу к работе, вызывается при запуске программы
    create_tables()  # создаём таблицы если их нет
    fill_test_data()  # заполняем примерами если база пустая


# ---------- проверка без окон ----------

if __name__ == "__main__":  # этот блок работает только при запуске файла напрямую
    init_db()  # готовим базу
    print("база:", DB_PATH)  # где лежит файл базы
    print("статистика:", get_stats())  # общие цифры
    user = check_login("admin", "1234")  # пробуем войти как админ
    print("вход admin:", dict(user) if user else "ошибка")  # dict превращает строку в словарь для печати
    print("вход с неверным паролем:", check_login("admin", "0000"))  # должно быть None
    print("\nпоиск 'стру':")  # заголовок
    for r in search_books("стру"):  # ищем по части фамилии
        state = "в наличии" if r["available"] else f"выдана до {r['due_date']}"  # состояние экземпляра
        print(f"  {r['copy_id']:>3}  {r['title']:<32} {r['authors']:<28} {state}")  # печатаем строку
    print("\nдолжники:")  # заголовок
    for r in get_debtors():  # перебираем должников
        print(f"  {r['full_name']:<26} {r['title']:<32} просрочка {r['days_late']} дн.")  # печатаем строку
    print("\nжурнал:")  # заголовок
    for r in get_history(10):  # последние 10 операций
        print(f"  {r['op_date']}  {r['op_type']:<8} №{r['copy_id']:<3} {r['title']:<32} {r['reader']}")  # строка журнала
