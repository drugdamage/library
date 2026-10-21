# часть 2: каркас главного окна
# слева список разделов, справа содержимое выбранного раздела, внизу кто вошёл и кнопка «Выйти»
# пока готов только главный экран со сводкой, остальные разделы заполним в следующих частях

from PyQt6.QtCore import Qt, pyqtSignal  # константы qt и свои сигналы
from PyQt6.QtWidgets import (  # виджеты интерфейса
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)  # конец списка

from database import get_stats  # цифры для сводки

SECTIONS = [  # название раздела и что в нём будет
    ("Главная", ""),  # сводка, сделана сейчас
    ("Выдача", "Здесь можно будет найти читателя и книгу и выдать её в один экран."),  # часть 4
    ("Возврат", "Здесь можно будет принять книгу по инвентарному номеру."),  # часть 4
    ("Каталог", "Здесь будет список книг с поиском по мере ввода и фильтром по жанру."),  # часть 3
    ("Читатели", "Здесь будет список читателей, поиск и регистрация новых."),  # часть 5
    ("Отчёты", "Здесь будут выданные книги, книги в наличии, должники и журнал операций."),  # часть 7
    ("Администрирование", "Здесь будут жанры, авторы и сотрудники."),  # часть 8, только для админа
]  # конец списка разделов

CARDS = [  # ключ из get_stats и подпись на карточке
    ("books", "Книг в каталоге"),  # сколько изданий
    ("copies", "Экземпляров"),  # сколько всего на учёте
    ("issued", "Выдано сейчас"),  # сколько на руках
    ("debtors", "Просрочено"),  # сколько не вернули вовремя
]  # конец списка карточек


class StatCard(QFrame):  # карточка с одной цифрой на главном экране
    def __init__(self, caption):  # caption это подпись под цифрой
        super().__init__()  # создаём рамку
        self.setObjectName("card")  # для стиля в main.py
        self.number = QLabel("0")  # большая цифра
        self.number.setObjectName("cardNumber")  # крупный шрифт
        label = QLabel(caption)  # подпись
        label.setObjectName("hint")  # серый текст
        layout = QVBoxLayout(self)  # цифра над подписью
        layout.addWidget(self.number)  # цифра
        layout.addWidget(label)  # подпись

    def set_value(self, value, warn=False):  # ставит число, warn красит в красный
        self.number.setText(str(value))  # показываем число
        self.number.setStyleSheet("color: #d9534f;" if warn else "")  # красный если есть просрочка


class HomePage(QWidget):  # главный экран со сводкой
    def __init__(self, user):  # user это вошедший сотрудник
        super().__init__()  # создаём виджет
        first_names = " ".join(user["full_name"].split()[1:])  # имя и отчество без фамилии
        hello = QLabel(f"Здравствуйте, {first_names}!")  # приветствие
        hello.setObjectName("pageTitle")  # крупный заголовок
        hint = QLabel("Сводка по библиотеке на сегодня. Разделы выбираются в списке слева.")  # подсказка
        hint.setObjectName("hint")  # серый текст

        grid = QGridLayout()  # карточки в сетку два на два
        grid.setSpacing(16)  # расстояние между карточками
        self.cards = {}  # карточки по ключу, чтобы потом обновлять
        for i, (key, caption) in enumerate(CARDS):  # перебираем карточки с номером
            self.cards[key] = StatCard(caption)  # создаём карточку
            grid.addWidget(self.cards[key], i // 2, i % 2)  # строка и столбец по номеру

        layout = QVBoxLayout(self)  # всё сверху вниз
        layout.addWidget(hello)  # приветствие
        layout.addWidget(hint)  # подсказка
        layout.addSpacing(12)  # небольшой отступ
        layout.addLayout(grid)  # карточки
        layout.addStretch()  # остальное место пустое снизу
        self.refresh()  # сразу заполняем цифры

    def refresh(self):  # берёт свежие цифры из базы
        stats = get_stats()  # словарь с цифрами
        for key, card in self.cards.items():  # каждая карточка
            card.set_value(stats[key], warn=(key == "debtors" and stats[key] > 0))  # красным только просрочку


def placeholder_page(title, text):  # заглушка для раздела который ещё не сделан
    page = QWidget()  # пустая страница
    header = QLabel(title)  # название раздела
    header.setObjectName("pageTitle")  # крупный шрифт
    info = QLabel(text + "\n\nРаздел появится в следующих частях работы.")  # что тут будет
    info.setObjectName("hint")  # серый текст
    info.setWordWrap(True)  # длинный текст переносится
    layout = QVBoxLayout(page)  # сверху вниз
    layout.addWidget(header)  # заголовок
    layout.addWidget(info)  # пояснение
    layout.addStretch()  # прижимаем всё кверху
    return page  # отдаём готовую страницу


class MainWindow(QMainWindow):  # главное окно программы
    logout = pyqtSignal()  # сигнал «сменить пользователя», его ловит main.py

    def __init__(self, user):  # user это сотрудник из окна входа
        super().__init__()  # создаём окно
        self.user = user  # запоминаем кто работает
        self.logging_out = False  # true когда закрываемся из-за кнопки «Выйти»
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # после закрытия окно удаляется из памяти
        self.setWindowTitle("Библиотека")  # заголовок окна
        self.resize(1000, 640)  # нормальный размер при запуске

        self.menu = QListWidget()  # боковая панель с разделами
        self.menu.setObjectName("menu")  # для стиля
        self.menu.setFixedWidth(200)  # ширина панели
        self.pages = QStackedWidget()  # стопка страниц, видна только одна
        self.home = HomePage(user)  # главный экран

        is_admin = user["role"] == "администратор"  # админ видит больше разделов
        for title, text in SECTIONS:  # добавляем разделы по списку
            if title == "Администрирование" and not is_admin:  # библиотекарю этот раздел не нужен
                continue  # пропускаем
            self.menu.addItem(title)  # пункт в боковой панели
            self.pages.addWidget(self.home if title == "Главная" else placeholder_page(title, text))  # страница раздела
        self.menu.currentRowChanged.connect(self.open_section)  # выбрали пункт и открываем страницу
        self.menu.setCurrentRow(0)  # при запуске открыт главный экран

        central = QWidget()  # центральная часть окна
        layout = QHBoxLayout(central)  # панель слева, страницы справа
        layout.setContentsMargins(0, 0, 0, 0)  # без лишних отступов по краям
        layout.addWidget(self.menu)  # панель
        layout.addWidget(self.pages, 1)  # страницы забирают всё остальное место
        self.setCentralWidget(central)  # ставим в окно

        who = QLabel(f"Вошёл: {user['full_name']} ({user['role']})")  # кто сейчас работает
        exit_button = QPushButton("Выйти")  # смена пользователя
        exit_button.clicked.connect(self.do_logout)  # по нажатию выходим к окну входа
        self.statusBar().addWidget(who)  # фио слева в строке состояния
        self.statusBar().addPermanentWidget(exit_button)  # кнопка справа

    def open_section(self, row):  # показывает страницу выбранного раздела
        self.pages.setCurrentIndex(row)  # номер пункта совпадает с номером страницы
        if row == 0:  # вернулись на главный экран
            self.home.refresh()  # обновляем цифры, вдруг что-то выдали

    def do_logout(self):  # нажали «Выйти»
        self.logging_out = True  # помечаем, что программу закрывать не надо
        self.close()  # закрываем главное окно
        self.logout.emit()  # просим main.py снова показать окно входа

    def closeEvent(self, event):  # срабатывает при любом закрытии окна
        if not self.logging_out:  # закрыли крестиком, а не кнопкой «Выйти»
            QApplication.quit()  # значит выходим из программы совсем
        super().closeEvent(event)  # дальше обычное закрытие
