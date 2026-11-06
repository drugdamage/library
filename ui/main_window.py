from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QLabel,
    QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from database import get_stats
from ui.workflows import CatalogPage, ReturnPage, ReadersPage, ReportsPage, AdminPage

# ключ из get_stats() и подпись под цифрой
CARDS = [
    ("books", "Книг в каталоге"),
    ("copies", "Экземпляров"),
    ("issued", "Выдано сейчас"),
    ("debtors", "Просрочено"),
]


# карточка на главном экране: большая цифра и подпись
class StatCard(QFrame):
    def __init__(self, caption):
        super().__init__()
        self.setObjectName("card")
        self.number = QLabel("0")
        self.number.setObjectName("cardNumber")
        label = QLabel(caption)
        label.setObjectName("hint")
        layout = QVBoxLayout(self)
        layout.addWidget(self.number)
        layout.addWidget(label)

    def set_value(self, value, warn=False):
        self.number.setText(str(value))
        self.number.setStyleSheet("color: #d9534f;" if warn else "")  # warn = красная цифра


class HomePage(QWidget):
    def __init__(self, user):
        super().__init__()
        first_names = " ".join(user["full_name"].split()[1:])  # убираем фамилию, остаётся имя отчество
        hello = QLabel("Библиотека")
        hello.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hello.setObjectName("pageTitle")
        hint = QLabel(f"Здравствуйте, {first_names}! Выберите раздел.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("hint")

        # карточки сеткой 2 на 2
        grid = QGridLayout()
        grid.setSpacing(16)
        self.cards = {}
        for i, (key, caption) in enumerate(CARDS):
            self.cards[key] = StatCard(caption)
            grid.addWidget(self.cards[key], i // 2, i % 2)

        layout = QVBoxLayout(self)
        layout.addWidget(hello)
        layout.addWidget(hint)
        layout.addSpacing(12)
        layout.addLayout(grid)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        stats = get_stats()
        for key, card in self.cards.items():
            card.set_value(stats[key], warn=(key == "debtors" and stats[key] > 0))


class MainWindow(QMainWindow):
    logout = pyqtSignal()  # main.py ловит его и снова показывает окно входа

    def __init__(self, user):
        super().__init__()
        self.user = user
        self.logging_out = False  # чтобы отличать «Выйти» от закрытия крестиком
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Библиотека")
        self.resize(1000, 640)

        self.pages = QStackedWidget()
        self.home = HomePage(user)
        self.pages.addWidget(self.home)
        self.sections = {}
        # Четыре основные кнопки и их порядок повторяют фГлавная в Access.
        buttons = QVBoxLayout()
        for title in ("Администрирование", "Выдача", "Отчёты", "Отдача"):
            button = QPushButton(title)
            button.setMinimumHeight(38)
            button.setMaximumWidth(440)
            button.setEnabled(title != "Администрирование" or user["role"] == "администратор")
            button.clicked.connect(lambda checked=False, name=title: self.open_named(name))
            buttons.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.home.layout().insertLayout(2, buttons)
        self.back = QPushButton("Закрыть — вернуться в главное меню")
        self.back.clicked.connect(lambda: self.open_section(0))
        self.back.hide()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.pages, 1)
        layout.addWidget(self.back)
        self.setCentralWidget(central)

        # строка состояния внизу
        who = QLabel(f"Вошёл: {user['full_name']} ({user['role']})")
        exit_button = QPushButton("Выйти")
        exit_button.clicked.connect(self.do_logout)
        self.statusBar().addWidget(who)
        self.statusBar().addPermanentWidget(exit_button)

    def open_named(self, name):
        if name == "Администрирование" and self.user["role"] != "администратор":
            return
        if name not in self.sections:
            if name == "Выдача":
                page = CatalogPage(self.user, issuing=True)
                readers = QPushButton("Читатели — регистрация и поиск")
                readers.clicked.connect(lambda: self.open_named("Читатели"))
                page.layout.addWidget(readers)
            elif name == "Отдача":
                page = ReturnPage(self.user)
            elif name == "Поиск книг":
                page = CatalogPage(self.user)
            elif name == "Читатели":
                page = ReadersPage()
            elif name == "Отчёты":
                page = ReportsPage()
                search = QPushButton("Поиск книг")
                search.clicked.connect(lambda: self.open_named("Поиск книг"))
                page.layout.addWidget(search)
            else:
                page = AdminPage(self.user)
            self.sections[name] = self.pages.addWidget(page)
        index = self.sections[name]
        page = self.pages.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()
        self.open_section(index)

    def open_section(self, row):
        self.pages.setCurrentIndex(row)
        self.back.setVisible(row != 0)
        if row == 0:
            self.home.refresh()

    def do_logout(self):
        self.logging_out = True
        self.close()
        self.logout.emit()

    def closeEvent(self, event):
        # если закрыли крестиком, выходим из программы совсем
        if not self.logging_out:
            QApplication.quit()
        super().closeEvent(event)
