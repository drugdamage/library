# часть 2: точка входа в программу, запускать так: python main.py
# готовит базу, задаёт общее оформление, показывает окно входа и потом главное окно
# кнопка «Выйти» в главном окне снова открывает окно входа для другого сотрудника

import sys  # нужен для аргументов запуска и кода выхода

from PyQt6.QtGui import QFont  # шрифт для всей программы
from PyQt6.QtWidgets import QApplication, QDialog  # само приложение и диалог

from database import init_db  # подготовка базы
from ui.login import LoginDialog  # окно входа
from ui.main_window import MainWindow  # главное окно

STYLE = """
    QWidget { color: #222; }
    QMainWindow, QDialog { background: #f6f7f9; }
    QPushButton { padding: 6px 18px; border-radius: 4px; background: #2f6fb3; color: white; border: none; }
    QPushButton:hover { background: #255d99; }
    QLineEdit { padding: 5px; border: 1px solid #c4c8cf; border-radius: 4px; background: white; }
    QLineEdit:focus { border: 1px solid #2f6fb3; }
    #menu { background: #26313d; color: #e8ecf1; border: none; font-size: 15px; padding-top: 8px; }
    #menu::item { padding: 10px 16px; }
    #menu::item:selected { background: #2f6fb3; color: white; }
    #card { background: white; border: 1px solid #dde1e6; border-radius: 8px; padding: 8px; }
    #cardNumber { font-size: 34px; font-weight: bold; }
    #pageTitle { font-size: 22px; font-weight: bold; }
    #loginTitle { font-size: 24px; font-weight: bold; }
    #hint { color: #666; }
    #error { color: #d9534f; }
    QStatusBar QLabel { padding-left: 6px; }
"""  # общее оформление для всех окон, похоже на css


def main():  # главная функция программы
    init_db()  # создаём базу и тестовые данные если их ещё нет
    app = QApplication(sys.argv)  # без этого объекта окна pyqt не работают
    app.setFont(QFont(app.font().family(), 12))  # читаемый размер шрифта везде
    app.setStyleSheet(STYLE)  # единое оформление
    app.setQuitOnLastWindowClosed(False)  # когда выходить решаем сами, иначе при смене пользователя всё закроется

    def login():  # показывает окно входа и открывает главное окно
        dialog = LoginDialog()  # создаём окно входа
        if dialog.exec() != QDialog.DialogCode.Accepted:  # нажали esc или закрыли крестиком
            app.quit()  # выходим из программы
            return False  # сообщаем что вход не состоялся
        window = MainWindow(dialog.user)  # главное окно для вошедшего сотрудника
        window.logout.connect(login)  # «Выйти» снова вызывает эту же функцию
        window.show()  # показываем окно
        app.main_window = window  # держим ссылку, иначе python удалит окно
        return True  # вход удался

    if login():  # первый вход при запуске
        sys.exit(app.exec())  # запускаем обработку событий до закрытия программы


if __name__ == "__main__":  # только при запуске этого файла напрямую
    main()  # запускаем программу
