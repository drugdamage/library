from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from database import check_login

ERROR_STYLE = "border: 2px solid #d9534f;"  # красная рамка у неправильного поля


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.user = None  # сюда попадёт сотрудник если вход удался
        self.setWindowTitle("Вход — Библиотека")
        self.setFixedWidth(360)

        title = QLabel("Библиотека")
        title.setObjectName("loginTitle")
        hint = QLabel("Введите логин и пароль сотрудника")
        hint.setObjectName("hint")

        self.login = QLineEdit()
        self.login.setPlaceholderText("например, lib")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)  # пароль точками
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.hide()

        self.button = QPushButton("Войти")
        self.button.setDefault(True)  # чтобы срабатывала по enter
        self.button.clicked.connect(self.try_login)

        form = QFormLayout()
        form.addRow("Логин:", self.login)
        form.addRow("Пароль:", self.password)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.button)

        # когда человек начинает исправлять, ошибку убираем
        for field in (self.login, self.password):
            field.textChanged.connect(self.clear_error)
        self.login.setFocus()

    def clear_error(self):
        self.login.setStyleSheet("")
        self.password.setStyleSheet("")
        self.error.hide()

    def show_error(self, text, *fields):
        # fields это поля которые надо обвести красным
        self.error.setText(text)
        self.error.show()
        for field in fields:
            field.setStyleSheet(ERROR_STYLE)
        fields[0].setFocus()

    def try_login(self):
        empty = [f for f in (self.login, self.password) if not f.text().strip()]
        if empty:
            self.show_error("Заполните логин и пароль.", *empty)
            return
        user = check_login(self.login.text(), self.password.text())
        if user is None:
            self.password.clear()
            self.show_error("Неверный логин или пароль.", self.password)
            return
        self.user = user
        self.accept()  # закрывает окно, exec() в main.py вернёт Accepted
