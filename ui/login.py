# часть 2: окно входа в программу
# сотрудник вводит логин и пароль, проверка идёт через check_login из database.py
# если вход удался, в self.user лежит сотрудник: id, фио и роль

from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout  # нужные виджеты

from database import check_login  # проверка логина и пароля в базе

ERROR_STYLE = "border: 2px solid #d9534f;"  # красная рамка для пустого поля


class LoginDialog(QDialog):  # окно входа, наследуем от обычного диалога
    def __init__(self):  # создаём окно
        super().__init__()  # сначала создаём сам диалог
        self.user = None  # тут будет сотрудник после удачного входа
        self.setWindowTitle("Вход — Библиотека")  # заголовок окна
        self.setFixedWidth(360)  # ширина постоянная, растягивать незачем

        title = QLabel("Библиотека")  # крупная надпись сверху
        title.setObjectName("loginTitle")  # имя нужно чтобы задать стиль в main.py
        hint = QLabel("Введите логин и пароль сотрудника")  # подсказка что делать
        hint.setObjectName("hint")  # серый мелкий текст

        self.login = QLineEdit()  # поле логина
        self.login.setPlaceholderText("например, lib")  # серая подсказка внутри поля
        self.password = QLineEdit()  # поле пароля
        self.password.setEchoMode(QLineEdit.EchoMode.Password)  # вместо букв точки
        self.error = QLabel()  # сюда пишем ошибку
        self.error.setObjectName("error")  # красный текст
        self.error.hide()  # пока ошибки нет, прячем

        self.button = QPushButton("Войти")  # основная кнопка
        self.button.setDefault(True)  # enter в любом поле нажимает её
        self.button.clicked.connect(self.try_login)  # по нажатию проверяем вход

        form = QFormLayout()  # подписи слева, поля справа
        form.addRow("Логин:", self.login)  # строка логина
        form.addRow("Пароль:", self.password)  # строка пароля

        layout = QVBoxLayout(self)  # всё окно сверху вниз
        layout.setContentsMargins(24, 20, 24, 20)  # отступы от краёв окна
        layout.setSpacing(10)  # расстояние между элементами
        layout.addWidget(title)  # заголовок
        layout.addWidget(hint)  # подсказка
        layout.addLayout(form)  # поля
        layout.addWidget(self.error)  # ошибка
        layout.addWidget(self.button)  # кнопка внизу

        for field in (self.login, self.password):  # для обоих полей
            field.textChanged.connect(self.clear_error)  # начали печатать и ошибка пропадает
        self.login.setFocus()  # курсор сразу в поле логина

    def clear_error(self):  # убирает красные рамки и текст ошибки
        self.login.setStyleSheet("")  # обычная рамка у логина
        self.password.setStyleSheet("")  # и у пароля
        self.error.hide()  # прячем надпись

    def show_error(self, text, *fields):  # показывает ошибку и подсвечивает поля
        self.error.setText(text)  # текст ошибки
        self.error.show()  # показываем надпись
        for field in fields:  # каждое переданное поле
            field.setStyleSheet(ERROR_STYLE)  # обводим красным
        fields[0].setFocus()  # курсор в первое проблемное поле

    def try_login(self):  # проверка при нажатии «Войти»
        empty = [f for f in (self.login, self.password) if not f.text().strip()]  # какие поля пустые
        if empty:  # что-то не заполнено
            self.show_error("Заполните логин и пароль.", *empty)  # подсвечиваем пустые
            return  # в базу не идём
        user = check_login(self.login.text(), self.password.text())  # спрашиваем базу
        if user is None:  # не нашли такого сотрудника
            self.password.clear()  # пароль стираем, чтобы ввести заново
            self.show_error("Неверный логин или пароль.", self.password)  # понятное сообщение без подробностей
            return  # окно не закрываем
        self.user = user  # запоминаем кто вошёл
        self.accept()  # закрываем окно с успехом
