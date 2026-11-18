# Library

A library management app built with Python, PyQt6, and SQLite, for a coursework comparison with Microsoft Access. Includes book search, loans and returns, reader registration and cards, CSV reports, and database backups.

## Run

Requires Python 3.10+.

```sh
git clone https://github.com/drugdamage/library.git
cd library
python3 -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux. In Windows PowerShell, create the environment with `python` and activate with `.\.venv\Scripts\Activate.ps1`. Then:

```sh
pip install -r requirements.txt
python main.py
```

Demo logins: `admin / 1234`, `lib / 1111`. The app creates `library.db` on first launch and keeps existing data on later launches.

Open **Выдача → Читатели**, select a reader, then click **Карточка выбранного читателя** or double-click the row. The card shows contact details, current loans with overdue days, and the reader's full operation history.

## Tests

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Tests use temporary databases. This is a learning project; its login system does not protect the database file from direct access. Record editing/deletion, reference data management, and report printing are unfinished; the Access comparison is ongoing.

The original [Access database](%D0%91%D0%B8%D0%B1%D0%BB%D0%B8%D0%BE%D1%82%D0%B5%D0%BA%D0%B0.accdb) is included as a comparison baseline. Its tables have been inspected without changing the file; its forms and macros still need to be tested in Access. Its data differs from the Python demo data.

Project docs (Russian): [requirements](%D0%A2%D0%97.md), [Access comparison](comparison.md), [stack and commands](stack.txt), [source materials](docs/).
