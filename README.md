# Library

A library management app built with Python, PyQt6, and SQLite, for a coursework comparison with Microsoft Access. Includes book search, loans and returns, reader registration, CSV reports, and database backups.

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

## Tests

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Tests use temporary databases. This is a learning project; its login system does not protect the database file from direct access. Record editing/deletion, reference data management, and report printing are unfinished; the Access comparison is ongoing.

Project docs (Russian): [requirements](%D0%A2%D0%97.md), [Access comparison](comparison.md), [stack and commands](stack.txt), [source materials](docs/).
