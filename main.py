import sys

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QDialog

from database import init_db
from ui.login import LoginDialog
from ui.main_window import MainWindow

# оформление для всех окон сразу, пишется почти как css
# #card и т.д. это имена которые задаются через setObjectName
STYLE = """
    QWidget { color: #222; }
    QMainWindow, QDialog { background: #f6f7f9; }
    QPushButton { padding: 6px 18px; border-radius: 4px; background: #2f6fb3; color: white; border: none; }
    QPushButton:hover { background: #255d99; }
    QPushButton:disabled { background: #dde1e6; color: #626d79; }
    QLineEdit {
        padding: 5px; border: 1px solid #c4c8cf; border-radius: 4px;
        background: white; color: #222;
    }
    QLineEdit:focus { border: 1px solid #2f6fb3; }
    QAbstractSpinBox QLineEdit { padding: 0; border: none; background: transparent; }
    QAbstractItemView {
        background: white; alternate-background-color: #f0f3f7; color: #222;
        selection-background-color: #2f6fb3; selection-color: white;
    }
    QHeaderView::section {
        background: #e9eef4; color: #222; padding: 5px;
        border: none; border-right: 1px solid #c4c8cf; border-bottom: 1px solid #c4c8cf;
    }
    QStatusBar { background: #f6f7f9; color: #222; }
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


def apply_light_theme(app):
    # Светлый интерфейс не должен смешиваться с тёмной системной палитрой macOS.
    # Fusion и явные цвета применяются ко всем элементам приложения.
    app.setStyle("Fusion")
    palette = app.style().standardPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f6f7f9"),
        (QPalette.ColorRole.WindowText, "#222222"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f0f3f7"),
        (QPalette.ColorRole.Text, "#222222"),
        (QPalette.ColorRole.Button, "#e9eef4"),
        (QPalette.ColorRole.ButtonText, "#222222"),
        (QPalette.ColorRole.Highlight, "#2f6fb3"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.PlaceholderText, "#626d79"),
        (QPalette.ColorRole.ToolTipBase, "#ffffff"),
        (QPalette.ColorRole.ToolTipText, "#222222"),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#626d79"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def main():
    init_db()  # создаст базу если её ещё нет
    app = QApplication(sys.argv)
    app.setFont(QFont(app.font().family(), 12))
    apply_light_theme(app)
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
