import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QDialog

from database import init_db
from ui.login import LoginDialog
from ui.main_window import MainWindow

# оформление для всех окон сразу, пишется почти как css
# #menu, #card и т.д. это имена которые задаются через setObjectName
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
"""


def main():
    init_db()  # создаст базу если её ещё нет
    app = QApplication(sys.argv)
    app.setFont(QFont(app.font().family(), 12))
    app.setStyleSheet(STYLE)
    # иначе при нажатии «Выйти» закроется главное окно и вся программа вместе с ним
    app.setQuitOnLastWindowClosed(False)

    def login():
        dialog = LoginDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:  # закрыли окно входа или нажали esc
            app.quit()
            return False
        window = MainWindow(dialog.user)
        window.logout.connect(login)  # после «Выйти» снова показываем вход
        window.show()
        app.main_window = window  # если не сохранить ссылку, окно сразу пропадёт
        return True

    if login():
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
