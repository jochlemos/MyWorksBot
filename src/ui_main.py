import json
from datetime import datetime

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.models import AppConfig, PUNCH_TYPES, ScheduleEvent, ScheduleProfile


class MainWindow(QMainWindow):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Mywork Ponto Bot")
        self.resize(900, 620)
        self._setup_ui()
        self._setup_tray()
        self.refresh_all()

    def _setup_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        manual_box = QGroupBox("Bater ponto agora")
        manual_layout = QHBoxLayout(manual_box)
        for ptype in ["entrada", "pausa", "retorno", "saida"]:
            btn = QPushButton(ptype.capitalize())
            btn.clicked.connect(lambda _, t=ptype: self._manual_punch(t))
            manual_layout.addWidget(btn)
        layout.addWidget(manual_box)

        self.status_label = QLabel("Status: -")
        layout.addWidget(self.status_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_config_tab(), "Configuração")
        tabs.addTab(self._build_schedule_tab(), "Agendamentos")
        tabs.addTab(self._build_history_tab(), "Histórico")
        tabs.addTab(self._build_logs_tab(), "Logs")
        layout.addWidget(tabs)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon())
        self.tray.setToolTip("Mywork Ponto Bot")
        menu = QMenu()
        show_action = QAction("Abrir", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.controller.quit_app)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _build_config_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.email_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_url_input = QLineEdit()
        self.punch_page_url_input = QLineEdit()
        self.email_selector_input = QLineEdit()
        self.password_selector_input = QLineEdit()
        self.submit_selector_input = QLineEdit()
        self.punch_button_selector_input = QLineEdit()
        self.reason_entrada_input = QLineEdit()
        self.reason_pausa_input = QLineEdit()
        self.reason_retorno_input = QLineEdit()
        self.reason_saida_input = QLineEdit()
        self.prevent_same_description_check = QCheckBox("Bloquear descrição repetida no site")
        self.tolerance_input = QSpinBox()
        self.tolerance_input.setRange(0, 20)
        self.startup_check = QCheckBox("Iniciar com Windows")
        self.headless_check = QCheckBox("Executar navegador oculto (headless)")
        save_btn = QPushButton("Salvar configuração")
        save_btn.clicked.connect(self._save_config)
        test_btn = QPushButton("Testar login robô")
        test_btn.clicked.connect(self._test_connection)

        form.addRow("E-mail:", self.email_input)
        form.addRow("Senha:", self.password_input)
        form.addRow("URL de login:", self.login_url_input)
        form.addRow("URL da página de ponto:", self.punch_page_url_input)
        form.addRow("Seletor campo e-mail:", self.email_selector_input)
        form.addRow("Seletor campo senha:", self.password_selector_input)
        form.addRow("Seletor botão login:", self.submit_selector_input)
        form.addRow("Seletor botão bater ponto:", self.punch_button_selector_input)
        form.addRow("Descrição entrada:", self.reason_entrada_input)
        form.addRow("Descrição pausa:", self.reason_pausa_input)
        form.addRow("Descrição retorno:", self.reason_retorno_input)
        form.addRow("Descrição saída:", self.reason_saida_input)
        form.addRow("", self.prevent_same_description_check)
        form.addRow("Tolerância (min):", self.tolerance_input)
        form.addRow("", self.startup_check)
        form.addRow("", self.headless_check)
        form.addRow(save_btn, test_btn)
        return tab

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.schedule_profile_name = QLineEdit()
        self.schedule_profile_name.setText("Agenda principal")
        self.schedule_profile_enabled = QCheckBox("Perfil ativo")
        self.schedule_profile_enabled.setChecked(True)

        weekdays_row = QHBoxLayout()
        weekday_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        self.weekday_checks: list[QCheckBox] = []
        for day in weekday_names:
            chk = QCheckBox(day)
            chk.setChecked(day in ["Seg", "Ter", "Qua", "Qui", "Sex"])
            self.weekday_checks.append(chk)
            weekdays_row.addWidget(chk)

        event_row = QHBoxLayout()
        self.event_time_input = QLineEdit()
        self.event_time_input.setPlaceholderText("HH:MM")
        self.event_type_combo = QComboBox()
        self.event_type_combo.addItems(PUNCH_TYPES)
        add_event_btn = QPushButton("Adicionar evento")
        add_event_btn.clicked.connect(self._add_schedule_event)
        remove_event_btn = QPushButton("Remover último")
        remove_event_btn.clicked.connect(self._remove_last_schedule_event)
        test_schedule_btn = QPushButton("Teste de registro")
        test_schedule_btn.clicked.connect(self._test_schedule_punch)
        event_row.addWidget(QLabel("Hora:"))
        event_row.addWidget(self.event_time_input)
        event_row.addWidget(QLabel("Tipo:"))
        event_row.addWidget(self.event_type_combo)
        event_row.addWidget(add_event_btn)
        event_row.addWidget(remove_event_btn)
        event_row.addWidget(test_schedule_btn)

        self.schedule_events_editor = QTextEdit()
        self.schedule_events_editor.setPlaceholderText("08:00 entrada")
        self.schedule_events_editor.setMinimumHeight(140)

        actions_row = QHBoxLayout()
        save = QPushButton("Salvar agendamentos")
        save.clicked.connect(self._save_schedules)
        actions_row.addWidget(save)

        layout.addWidget(QLabel("Nome do perfil:"))
        layout.addWidget(self.schedule_profile_name)
        layout.addWidget(self.schedule_profile_enabled)
        layout.addWidget(QLabel("Dias da semana:"))
        layout.addLayout(weekdays_row)
        layout.addLayout(event_row)
        layout.addWidget(QLabel("Eventos do perfil (um por linha: HH:MM tipo):"))
        layout.addWidget(self.schedule_events_editor)
        layout.addLayout(actions_row)
        return tab

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        actions = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar logs")
        refresh_btn.clicked.connect(self.refresh_logs)
        clear_btn = QPushButton("Limpar logs")
        clear_btn.clicked.connect(self._clear_logs)
        self.logs_view = QPlainTextEdit()
        self.logs_view.setReadOnly(True)
        actions.addWidget(refresh_btn)
        actions.addWidget(clear_btn)
        layout.addLayout(actions)
        layout.addWidget(self.logs_view)
        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        actions = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar histórico")
        refresh_btn.clicked.connect(self.refresh_history)
        clear_btn = QPushButton("Limpar histórico")
        clear_btn.clicked.connect(self._clear_history)
        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        actions.addWidget(refresh_btn)
        actions.addWidget(clear_btn)
        layout.addLayout(actions)
        layout.addWidget(self.history_view)
        return tab

    def refresh_all(self) -> None:
        cfg, email, password = self.controller.get_config_and_credentials()
        self.email_input.setText(email)
        self.password_input.setText(password)
        self.login_url_input.setText(cfg.login_url)
        self.punch_page_url_input.setText(cfg.punch_page_url)
        self.email_selector_input.setText(cfg.email_selector)
        self.password_selector_input.setText(cfg.password_selector)
        self.submit_selector_input.setText(cfg.submit_selector)
        self.punch_button_selector_input.setText(cfg.punch_button_selector)
        self.reason_entrada_input.setText(cfg.reason_entrada)
        self.reason_pausa_input.setText(cfg.reason_pausa)
        self.reason_retorno_input.setText(cfg.reason_retorno)
        self.reason_saida_input.setText(cfg.reason_saida)
        self.prevent_same_description_check.setChecked(cfg.prevent_same_description)
        self.tolerance_input.setValue(cfg.tolerance_minutes)
        self.startup_check.setChecked(cfg.auto_start_windows)
        self.headless_check.setChecked(cfg.headless_browser)
        self.status_label.setText(f"Status: {self.controller.get_status_text()}")
        self._load_schedule_ui_from_profiles(self.controller.get_current_profiles())
        self.refresh_logs()
        self.refresh_history()

    def refresh_logs(self) -> None:
        logs = self.controller.get_logs_text()
        self.logs_view.setPlainText(logs)

    def refresh_history(self) -> None:
        history = self.controller.get_history_text()
        self.history_view.setPlainText(history)

    def notify(self, text: str) -> None:
        self.tray.showMessage("Mywork Ponto Bot", text, QSystemTrayIcon.MessageIcon.Information, 4000)
        self.status_label.setText(f"Status: {text}")

    def _manual_punch(self, ptype: str) -> None:
        ok, msg = self.controller.manual_punch(ptype)
        QMessageBox.information(self, "Bater ponto", msg if ok else f"Falhou: {msg}")
        self.refresh_logs()
        self.refresh_history()

    def _save_config(self) -> None:
        cfg = AppConfig(
            login_url=self.login_url_input.text().strip(),
            punch_page_url=self.punch_page_url_input.text().strip(),
            email_selector=self.email_selector_input.text().strip(),
            password_selector=self.password_selector_input.text().strip(),
            submit_selector=self.submit_selector_input.text().strip(),
            punch_button_selector=self.punch_button_selector_input.text().strip(),
            reason_entrada=self.reason_entrada_input.text().strip() or "entrada",
            reason_pausa=self.reason_pausa_input.text().strip() or "pausa",
            reason_retorno=self.reason_retorno_input.text().strip() or "retorno",
            reason_saida=self.reason_saida_input.text().strip() or "saida",
            prevent_same_description=self.prevent_same_description_check.isChecked(),
            tolerance_minutes=self.tolerance_input.value(),
            auto_start_windows=self.startup_check.isChecked(),
            headless_browser=self.headless_check.isChecked(),
            profiles=self.controller.get_current_profiles(),
        )
        self.controller.save_config_and_credentials(
            cfg,
            self.email_input.text().strip(),
            self.password_input.text(),
        )
        QMessageBox.information(self, "Configuração", "Configuração salva.")
        self.refresh_all()

    def _save_schedules(self) -> None:
        try:
            name = self.schedule_profile_name.text().strip() or "Agenda principal"
            weekdays = [idx for idx, chk in enumerate(self.weekday_checks) if chk.isChecked()]
            if not weekdays:
                raise ValueError("Selecione ao menos um dia da semana.")
            events = self._parse_events_text(self.schedule_events_editor.toPlainText())
            if not events:
                raise ValueError("Adicione ao menos um evento.")
            profiles = [
                ScheduleProfile(
                    name=name,
                    enabled=self.schedule_profile_enabled.isChecked(),
                    weekdays=weekdays,
                    events=events,
                )
            ]
            self.controller.save_profiles(profiles)
            QMessageBox.information(self, "Agendamentos", "Agendamentos salvos.")
            self._load_schedule_ui_from_profiles(profiles)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Erro no agendamento", str(exc))

    def _add_schedule_event(self) -> None:
        time_value = self.event_time_input.text().strip()
        ptype = self.event_type_combo.currentText().strip()
        if not time_value:
            QMessageBox.warning(self, "Evento", "Informe o horário no formato HH:MM.")
            return
        current = self.schedule_events_editor.toPlainText().strip()
        line = f"{time_value} {ptype}"
        self.schedule_events_editor.setPlainText(f"{current}\n{line}".strip())

    def _remove_last_schedule_event(self) -> None:
        lines = [x for x in self.schedule_events_editor.toPlainText().splitlines() if x.strip()]
        if not lines:
            return
        lines.pop()
        self.schedule_events_editor.setPlainText("\n".join(lines))

    def _parse_events_text(self, text: str) -> list[ScheduleEvent]:
        events: list[ScheduleEvent] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"Linha inválida: '{line}'. Use: HH:MM tipo")
            ev_time, ev_type = parts[0], parts[1].lower()
            if ev_type not in PUNCH_TYPES:
                raise ValueError(f"Tipo inválido: '{ev_type}'.")
            hh_mm = ev_time.split(":")
            if len(hh_mm) != 2 or not all(x.isdigit() for x in hh_mm):
                raise ValueError(f"Horário inválido: '{ev_time}'.")
            events.append(ScheduleEvent(time=ev_time, punch_type=ev_type))
        return events

    def _load_schedule_ui_from_profiles(self, profiles: list[ScheduleProfile]) -> None:
        if not profiles:
            self.schedule_events_editor.setPlainText("")
            return
        profile = profiles[0]
        self.schedule_profile_name.setText(profile.name)
        self.schedule_profile_enabled.setChecked(profile.enabled)
        for idx, chk in enumerate(self.weekday_checks):
            chk.setChecked(idx in profile.weekdays)
        lines = [f"{ev.time} {ev.punch_type}" for ev in profile.events]
        self.schedule_events_editor.setPlainText("\n".join(lines))

    def _test_connection(self) -> None:
        cfg = AppConfig(
            login_url=self.login_url_input.text().strip(),
            punch_page_url=self.punch_page_url_input.text().strip(),
            email_selector=self.email_selector_input.text().strip(),
            password_selector=self.password_selector_input.text().strip(),
            submit_selector=self.submit_selector_input.text().strip(),
            punch_button_selector=self.punch_button_selector_input.text().strip(),
            reason_entrada=self.reason_entrada_input.text().strip() or "entrada",
            reason_pausa=self.reason_pausa_input.text().strip() or "pausa",
            reason_retorno=self.reason_retorno_input.text().strip() or "retorno",
            reason_saida=self.reason_saida_input.text().strip() or "saida",
            prevent_same_description=self.prevent_same_description_check.isChecked(),
            tolerance_minutes=self.tolerance_input.value(),
            auto_start_windows=self.startup_check.isChecked(),
            headless_browser=self.headless_check.isChecked(),
            profiles=self.controller.get_current_profiles(),
        )
        self.controller.save_config_and_credentials(
            cfg,
            self.email_input.text().strip(),
            self.password_input.text(),
        )
        ok, msg = self.controller.test_connection()
        QMessageBox.information(self, "Teste robô", msg if ok else f"Falhou: {msg}")

    def _test_schedule_punch(self) -> None:
        punch_type = self.event_type_combo.currentText().strip() or "entrada"
        reason = f"teste {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        ok, msg = self.controller.manual_punch(punch_type, custom_reason=reason)
        QMessageBox.information(self, "Teste de registro", msg if ok else f"Falhou: {msg}")
        self.refresh_logs()
        self.refresh_history()

    def _clear_logs(self) -> None:
        answer = QMessageBox.question(
            self,
            "Limpar logs",
            "Deseja realmente limpar todos os logs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.controller.clear_logs()
        self.refresh_logs()

    def _clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Limpar histórico",
            "Deseja realmente limpar todo o histórico?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.controller.clear_history()
        self.refresh_history()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.hide()
        self.notify("Aplicativo rodando em background.")
        event.ignore()
