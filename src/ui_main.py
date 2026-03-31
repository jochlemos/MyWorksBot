import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtGui import QAction, QIcon, QTextCursor
from PySide6.QtCore import QMetaObject, Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.models import ScheduleEvent, ScheduleProfile


class MainWindow(QMainWindow):
    _ROBOT_UI_TIMEOUT_MS = 300_000

    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._robot_op_generation = 0
        self._robot_timed_out = False
        self._robot_timeout_timer: QTimer | None = None
        self.main_tabs: QTabWidget | None = None
        self._logs_tab_index = 3
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._refresh_home_panel)
        self.setWindowTitle("Mywork Ponto Bot")
        self.resize(900, 620)
        self._setup_ui()
        self._setup_tray()
        self.refresh_all()
        self._clock_timer.start()

    def _setup_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        home_grid = QGridLayout()
        home_grid.setContentsMargins(0, 0, 0, 0)
        home_grid.setHorizontalSpacing(18)
        home_grid.setVerticalSpacing(2)
        home_grid.setColumnStretch(0, 1)
        home_grid.setColumnMinimumWidth(1, 280)

        left_title = QLabel("Próximos agendamentos:")
        left_title.setStyleSheet("font-weight: 600;")
        left_title.setContentsMargins(0, 0, 0, 0)

        self.next_schedules_label = QLabel("Carregando...")
        self.next_schedules_label.setWordWrap(True)
        self.next_schedules_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.next_schedules_label.setContentsMargins(0, 0, 0, 0)

        self.clock_label = QLabel("--:--")
        self.clock_label.setStyleSheet("font-size: 96px; font-weight: 700;")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.clock_label.setContentsMargins(0, 0, 0, 0)

        home_grid.addWidget(
            left_title,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        home_grid.addWidget(
            self.next_schedules_label,
            1,
            0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        home_grid.addWidget(
            self.clock_label,
            0,
            1,
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

        layout.addLayout(home_grid)

        self.status_label = QLabel("Status: -")
        layout.addWidget(self.status_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_config_tab(), "Configuração")
        tabs.addTab(self._build_schedule_tab(), "Agendamentos")
        tabs.addTab(self._build_history_tab(), "Histórico")
        tabs.addTab(self._build_logs_tab(), "Logs")
        self.main_tabs = tabs
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
        self.prevent_same_description_check = QCheckBox("Bloquear descrição repetida no site")
        self.tolerance_input = QSpinBox()
        self.tolerance_input.setRange(0, 20)
        self.startup_check = QCheckBox("Iniciar com Windows")
        self.headless_check = QCheckBox("Ocultar janela do navegador (headless)")
        self.browser_pause_spin = QSpinBox()
        self.browser_pause_spin.setRange(0, 120)
        self.browser_pause_spin.setSuffix(" s")
        self.browser_pause_spin.setToolTip(
            "Com a janela visível, tempo de espera no final antes de fechar o navegador. "
            "Use 0 para fechar imediatamente após concluir."
        )
        self.headless_check.toggled.connect(lambda checked: self.browser_pause_spin.setEnabled(not checked))
        save_btn = QPushButton("Salvar configuração")
        save_btn.setDefault(True)
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
        form.addRow("", self.prevent_same_description_check)
        form.addRow("Tolerância (min):", self.tolerance_input)
        form.addRow("", self.startup_check)
        form.addRow("", self.headless_check)
        form.addRow("Pausa com janela visível antes de fechar:", self.browser_pause_spin)
        footer_btns = QWidget()
        footer_layout = QHBoxLayout(footer_btns)
        footer_layout.setContentsMargins(0, 12, 0, 0)
        footer_layout.addStretch()
        footer_layout.addWidget(test_btn)
        footer_layout.addSpacing(10)
        footer_layout.addWidget(save_btn)
        form.addRow(footer_btns)
        return tab

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)
        layout.setContentsMargins(4, 8, 4, 8)

        self.schedule_profile_enabled = QCheckBox("Perfil ativo")
        self.schedule_profile_enabled.setChecked(True)

        self.schedule_profile_name = QLineEdit()
        self.schedule_profile_name.setText("Dias úteis")
        self.schedule_profile_name.setPlaceholderText("Dias úteis")

        profile_row = QHBoxLayout()
        profile_row.setSpacing(20)
        profile_row.addWidget(self.schedule_profile_enabled, 0, Qt.AlignmentFlag.AlignTop)
        name_block = QVBoxLayout()
        name_block.setSpacing(4)
        name_block.setContentsMargins(0, 0, 0, 0)
        name_block.addWidget(QLabel("Nome do perfil:"))
        name_block.addWidget(self.schedule_profile_name)
        profile_row.addLayout(name_block, 1)

        weekdays_row = QHBoxLayout()
        weekdays_row.setSpacing(10)
        weekday_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        self.weekday_checks: list[QCheckBox] = []
        for day in weekday_names:
            chk = QCheckBox(day)
            chk.setChecked(day in ["Seg", "Ter", "Qua", "Qui", "Sex"])
            self.weekday_checks.append(chk)
            weekdays_row.addWidget(chk)
        weekdays_row.addStretch()
        self.max_records_per_day_spin = QSpinBox()
        self.max_records_per_day_spin.setRange(1, 20)
        self.max_records_per_day_spin.setValue(4)
        self.max_records_per_day_spin.setToolTip(
            "Quantidade máxima de registros permitidos por dia no Mywork."
        )

        self.event_time_input = QLineEdit()
        self.event_time_input.setPlaceholderText("HH:MM")
        self.event_time_input.setFixedWidth(72)
        self.event_type_combo = QComboBox()
        self.event_type_combo.setMinimumWidth(120)
        self.event_description_input = QLineEdit()
        self.event_description_input.setPlaceholderText("Descrição (opcional)")
        self.event_description_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        add_event_btn = QPushButton("Adicionar evento")
        add_event_btn.clicked.connect(self._add_schedule_event)

        event_row = QHBoxLayout()
        event_row.setSpacing(8)
        al = Qt.AlignmentFlag.AlignVCenter
        event_row.addWidget(QLabel("Hora:"), 0, al)
        event_row.addWidget(self.event_time_input, 0, al)
        event_row.addWidget(QLabel("Tipo:"), 0, al)
        event_row.addWidget(self.event_type_combo, 0, al)
        event_row.addWidget(QLabel("Descrição:"), 0, al)
        event_row.addWidget(self.event_description_input, 1, al)
        event_row.addWidget(add_event_btn, 0, al)

        self.schedule_events_table = QTableWidget(0, 3)
        self.schedule_events_table.setHorizontalHeaderLabels(["Hora", "Tipo", "Descrição"])
        self.schedule_events_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.schedule_events_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.schedule_events_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.schedule_events_table.setAlternatingRowColors(True)
        self.schedule_events_table.setMinimumHeight(180)
        self.schedule_events_table.verticalHeader().setVisible(False)
        h = self.schedule_events_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.schedule_events_table.itemChanged.connect(self._on_schedule_table_item_changed)

        self.remove_schedule_btn = QPushButton("Remover selecionado")
        self.remove_schedule_btn.setVisible(False)
        self.remove_schedule_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #c2410c;
                color: #ffffff;
                border: 1px solid #9a3412;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #ea580c;
                border-color: #c2410c;
            }
            QPushButton:pressed {
                background-color: #9a3412;
            }
            """
        )
        self.remove_schedule_btn.clicked.connect(self._remove_selected_schedule_event)

        sel = self.schedule_events_table.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(self._on_schedule_table_selection_changed)

        test_schedule_btn = QPushButton("Teste de registro (real)")
        test_schedule_btn.setToolTip(
            "Executa um registro real no Mywork usando o tipo selecionado."
        )
        test_schedule_btn.clicked.connect(self._test_schedule_punch)
        save = QPushButton("Salvar agendamentos")
        save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        save.clicked.connect(self._save_schedules)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)
        actions_row.addWidget(test_schedule_btn)
        actions_row.addWidget(self.remove_schedule_btn)
        actions_row.addWidget(save, 1)

        layout.addLayout(profile_row)
        layout.addWidget(QLabel("Dias da semana:"))
        layout.addLayout(weekdays_row)
        max_row = QHBoxLayout()
        max_row.setSpacing(8)
        max_row.addWidget(QLabel("Máximo de registros por dia:"))
        max_row.addWidget(self.max_records_per_day_spin, 0, Qt.AlignmentFlag.AlignLeft)
        max_row.addStretch()
        layout.addLayout(max_row)
        layout.addLayout(event_row)
        layout.addWidget(
            QLabel(
                "Eventos do perfil: edite hora, tipo e descrição diretamente na tabela "
                "(duplo clique na célula ou F2). Os campos acima servem apenas para "
                "incluir um evento novo com «Adicionar evento»."
            )
        )
        layout.addWidget(self.schedule_events_table, 1)
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
        self.prevent_same_description_check.setChecked(cfg.prevent_same_description)
        self.tolerance_input.setValue(cfg.tolerance_minutes)
        self.startup_check.setChecked(cfg.auto_start_windows)
        self.headless_check.setChecked(cfg.headless_browser)
        self.browser_pause_spin.setRange(0, max(0, int(cfg.browser_pause_max_seconds)))
        self.browser_pause_spin.setValue(cfg.browser_pause_seconds)
        self.browser_pause_spin.setEnabled(not cfg.headless_browser)
        self.max_records_per_day_spin.setValue(max(1, int(cfg.max_records_per_day)))
        self.event_type_combo.clear()
        self.event_type_combo.addItems(list(cfg.punch_types) if cfg.punch_types else [])
        self.status_label.setText(f"Status: {self.controller.get_status_text()}")
        self._load_schedule_ui_from_profiles(self.controller.get_current_profiles())
        self._refresh_home_panel()
        self.refresh_logs()
        self.refresh_history()

    def refresh_logs(self) -> None:
        logs = self.controller.get_logs_text()
        self.logs_view.setPlainText(logs)
        self.logs_view.moveCursor(QTextCursor.MoveOperation.End)

    @Slot()
    def request_refresh_logs_ui(self) -> None:
        self.refresh_logs()
        self.refresh_history()

    def enqueue_notify(self, message: str) -> None:
        self._notify_pending = message
        QMetaObject.invokeMethod(
            self,
            "apply_pending_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def apply_pending_notify(self) -> None:
        self.notify(getattr(self, "_notify_pending", "") or "")

    def refresh_history(self) -> None:
        history = self.controller.get_history_text()
        self.history_view.setPlainText(history)

    def notify(self, text: str) -> None:
        self.tray.showMessage("Mywork Ponto Bot", text, QSystemTrayIcon.MessageIcon.Information, 4000)
        self.status_label.setText(f"Status: {text}")

    def _run_async_robot(
        self,
        task: Callable[[], tuple[bool, str]],
        on_finished: Callable[[bool, str], None],
        *,
        focus_logs_tab: bool = True,
        timeout_ms: int | None = None,
    ) -> None:
        if self._robot_timeout_timer is not None:
            self._robot_timeout_timer.stop()
        self._robot_op_generation += 1
        gen = self._robot_op_generation
        self._robot_timed_out = False

        limit = (
            timeout_ms
            if timeout_ms is not None
            else max(1000, int(self.controller.config.robot_ui_timeout_ms))
        )
        app = QApplication.instance()
        if app is not None:
            app.setOverrideCursor(Qt.CursorShape.WaitCursor)

        if focus_logs_tab and self.main_tabs is not None:
            self.main_tabs.setCurrentIndex(self._logs_tab_index)
        self.controller.log("INFO", "Robô: operação iniciada.")

        timer = QTimer(self)
        timer.setSingleShot(True)
        self._robot_timeout_timer = timer

        def on_timeout() -> None:
            if gen != self._robot_op_generation:
                return
            self._robot_timed_out = True
            self.controller.log(
                "WARN",
                f"Robô: tempo limite de {limit // 1000}s atingido. "
                "O navegador pode ainda finalizar em segundo plano.",
            )
            if app is not None:
                app.restoreOverrideCursor()
            QMessageBox.warning(
                self,
                "Tempo limite",
                f"A operação ultrapassou {limit // 1000} segundos.\n"
                "As etapas registradas estão na aba Logs.",
            )

        timer.timeout.connect(on_timeout)
        timer.start(limit)

        def work() -> None:
            try:
                ok, msg = task()
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, str(exc)
            self._robot_async_finish = (gen, ok, msg, timer, on_finished)
            QMetaObject.invokeMethod(
                self,
                "_complete_robot_operation",
                Qt.ConnectionType.QueuedConnection,
            )

        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def _complete_robot_operation(self) -> None:
        payload = getattr(self, "_robot_async_finish", None)
        if payload is None:
            return
        gen, ok, msg, timer, on_finished = payload
        self._robot_async_finish = None
        app = QApplication.instance()
        if self._robot_timeout_timer is timer:
            timer.stop()
        if gen != self._robot_op_generation:
            return
        if self._robot_timed_out:
            self.controller.log(
                "INFO",
                f"Robô: tarefa encerrou após o tempo limite (resultado={'ok' if ok else 'falha'}).",
            )
            return
        if app is not None:
            app.restoreOverrideCursor()
        on_finished(ok, msg)

    def _manual_punch(self, ptype: str) -> None:
        def task() -> tuple[bool, str]:
            return self.controller.manual_punch(ptype, on_step=self.controller.robot_step)

        def done(ok: bool, msg: str) -> None:
            QMessageBox.information(self, "Bater ponto", msg if ok else f"Falhou: {msg}")
            self.refresh_logs()
            self.refresh_history()

        self._run_async_robot(task, done)

    def _save_config(self) -> None:
        prev = self.controller.config
        cfg = replace(
            prev,
            login_url=self.login_url_input.text().strip(),
            punch_page_url=self.punch_page_url_input.text().strip(),
            email_selector=self.email_selector_input.text().strip(),
            password_selector=self.password_selector_input.text().strip(),
            submit_selector=self.submit_selector_input.text().strip(),
            punch_button_selector=self.punch_button_selector_input.text().strip(),
            prevent_same_description=self.prevent_same_description_check.isChecked(),
            tolerance_minutes=self.tolerance_input.value(),
            auto_start_windows=self.startup_check.isChecked(),
            headless_browser=self.headless_check.isChecked(),
            browser_pause_seconds=self.browser_pause_spin.value(),
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
            name = self.schedule_profile_name.text().strip() or "Dias úteis"
            weekdays = [idx for idx, chk in enumerate(self.weekday_checks) if chk.isChecked()]
            if not weekdays:
                raise ValueError("Selecione ao menos um dia da semana.")
            events = self._parse_events_from_table()
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
            self.controller.save_profiles(
                profiles,
                max_records_per_day=self.max_records_per_day_spin.value(),
            )
            QMessageBox.information(self, "Agendamentos", "Agendamentos salvos.")
            self._load_schedule_ui_from_profiles(profiles)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Erro no agendamento", str(exc))

    def _on_schedule_table_selection_changed(self, *_args) -> None:
        row = self.schedule_events_table.currentRow()
        self.remove_schedule_btn.setVisible(row >= 0)

    def _on_schedule_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self.schedule_events_table.signalsBlocked():
            return
        col = item.column()
        if col == 0:
            raw = item.text().strip()
            try:
                m = self._hhmm_to_minutes(raw)
            except ValueError:
                return
            norm = self._normalize_hhmm_from_minutes(m)
            if norm != item.text().strip():
                self.schedule_events_table.blockSignals(True)
                item.setText(norm)
                self.schedule_events_table.blockSignals(False)
            self._resort_schedule_table_preserving_selection()
        elif col == 1:
            low = item.text().strip().lower()
            if low != item.text().strip():
                self.schedule_events_table.blockSignals(True)
                item.setText(low)
                self.schedule_events_table.blockSignals(False)

    def _resort_schedule_table_preserving_selection(self) -> None:
        row = self.schedule_events_table.currentRow()
        key: tuple[str, str, str] | None = None
        if row >= 0:
            evs = self._get_events_from_table()
            if row < len(evs):
                e = evs[row]
                key = (e.time, e.punch_type.lower(), (e.description or "").strip())
        events = self._get_events_from_table()
        self._set_table_from_events(events)
        if key is None:
            return
        for r in range(self.schedule_events_table.rowCount()):
            it0 = self.schedule_events_table.item(r, 0)
            it1 = self.schedule_events_table.item(r, 1)
            it2 = self.schedule_events_table.item(r, 2)
            if not it0 or not it1:
                continue
            d = it2.text().strip() if it2 else ""
            if (
                it0.text().strip() == key[0]
                and it1.text().strip().lower() == key[1]
                and d == key[2]
            ):
                self.schedule_events_table.selectRow(r)
                break

    def _event_from_form_fields(self) -> ScheduleEvent:
        time_value = self.event_time_input.text().strip()
        ptype = self.event_type_combo.currentText().strip().lower()
        desc = self.event_description_input.text().strip()
        if not time_value:
            raise ValueError("Informe o horário no formato HH:MM.")
        try:
            m = self._hhmm_to_minutes(time_value)
        except ValueError as exc:
            raise ValueError("Horário inválido. Use HH:MM (ex.: 08:00).") from exc
        norm = self._normalize_hhmm_from_minutes(m)
        valid_types = {x.strip().lower() for x in self.controller.config.punch_types}
        if not valid_types:
            raise ValueError("Lista punch_types vazia na configuração.")
        if ptype not in valid_types:
            raise ValueError(f"Tipo inválido: '{ptype}'.")
        return ScheduleEvent(time=norm, punch_type=ptype, description=desc)

    def _add_schedule_event(self) -> None:
        try:
            new_ev = self._event_from_form_fields()
        except ValueError as exc:
            QMessageBox.warning(self, "Evento", str(exc))
            return
        minutes_set = self._collect_time_minutes_from_table()
        try:
            m = self._hhmm_to_minutes(new_ev.time)
        except ValueError:
            return
        if m in minutes_set:
            QMessageBox.warning(
                self,
                "Evento",
                "Já existe um agendamento neste horário. Cada evento deve ter um horário único.",
            )
            return
        events = self._get_events_from_table()
        events.append(new_ev)
        try:
            self._validate_unique_event_times(events)
        except ValueError as exc:
            QMessageBox.warning(self, "Evento", str(exc))
            return
        self._set_table_from_events(events)

    def _remove_selected_schedule_event(self) -> None:
        row = self.schedule_events_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Evento", "Selecione um evento na tabela.")
            return
        self.schedule_events_table.removeRow(row)
        self._on_schedule_table_selection_changed()

    @staticmethod
    def _hhmm_to_minutes(time_str: str) -> int:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError("formato")
        hh_s, mm_s = parts[0].strip(), parts[1].strip()
        if not hh_s.isdigit() or not mm_s.isdigit():
            raise ValueError("formato")
        hh, mm = int(hh_s), int(mm_s)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("intervalo")
        return hh * 60 + mm

    @staticmethod
    def _normalize_hhmm_from_minutes(total_minutes: int) -> str:
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    def _get_events_from_table(self) -> list[ScheduleEvent]:
        events: list[ScheduleEvent] = []
        for row in range(self.schedule_events_table.rowCount()):
            it0 = self.schedule_events_table.item(row, 0)
            it1 = self.schedule_events_table.item(row, 1)
            it2 = self.schedule_events_table.item(row, 2)
            if not it0 or not it1:
                continue
            t = it0.text().strip()
            ptype = it1.text().strip().lower()
            desc = it2.text().strip() if it2 else ""
            try:
                m = self._hhmm_to_minutes(t)
            except ValueError:
                continue
            norm = self._normalize_hhmm_from_minutes(m)
            events.append(ScheduleEvent(time=norm, punch_type=ptype, description=desc))
        return events

    def _set_table_from_events(self, events: list[ScheduleEvent]) -> None:
        ordered = sorted(events, key=lambda e: self._hhmm_to_minutes(e.time))
        self.schedule_events_table.blockSignals(True)
        try:
            self.schedule_events_table.setRowCount(0)
            for ev in ordered:
                r = self.schedule_events_table.rowCount()
                self.schedule_events_table.insertRow(r)
                self.schedule_events_table.setItem(r, 0, QTableWidgetItem(ev.time))
                self.schedule_events_table.setItem(r, 1, QTableWidgetItem(ev.punch_type))
                self.schedule_events_table.setItem(
                    r, 2, QTableWidgetItem((ev.description or "").strip())
                )
        finally:
            self.schedule_events_table.blockSignals(False)
        self._on_schedule_table_selection_changed()

    def _collect_time_minutes_from_table(self) -> set[int]:
        found: set[int] = set()
        for row in range(self.schedule_events_table.rowCount()):
            it = self.schedule_events_table.item(row, 0)
            if not it:
                continue
            try:
                found.add(self._hhmm_to_minutes(it.text().strip()))
            except ValueError:
                continue
        return found

    def _validate_unique_event_times(self, events: list[ScheduleEvent]) -> None:
        seen: set[int] = set()
        for ev in events:
            try:
                m = self._hhmm_to_minutes(ev.time)
            except ValueError as exc:
                raise ValueError(f"Horário inválido: '{ev.time}'.") from exc
            if m in seen:
                label = self._normalize_hhmm_from_minutes(m)
                raise ValueError(
                    f"Horário duplicado: {label}. Cada agendamento deve ter um horário único no perfil."
                )
            seen.add(m)

    def _parse_events_from_table(self) -> list[ScheduleEvent]:
        events = self._get_events_from_table()
        valid_types = {x.strip().lower() for x in self.controller.config.punch_types}
        if not valid_types:
            raise ValueError("Lista punch_types vazia na configuração.")
        for ev in events:
            if ev.punch_type.lower() not in valid_types:
                raise ValueError(f"Tipo inválido: '{ev.punch_type}'.")
            try:
                self._hhmm_to_minutes(ev.time)
            except ValueError as exc:
                raise ValueError(f"Horário inválido: '{ev.time}'.") from exc
        self._validate_unique_event_times(events)
        return events

    def _load_schedule_ui_from_profiles(self, profiles: list[ScheduleProfile]) -> None:
        if not profiles:
            self.schedule_events_table.setRowCount(0)
            self._on_schedule_table_selection_changed()
            return
        profile = profiles[0]
        self.schedule_profile_name.setText(profile.name)
        self.schedule_profile_enabled.setChecked(profile.enabled)
        for idx, chk in enumerate(self.weekday_checks):
            chk.setChecked(idx in profile.weekdays)
        self._set_table_from_events(list(profile.events))
        self._refresh_home_panel()

    def _refresh_home_panel(self) -> None:
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M"))
        self.next_schedules_label.setText(self._build_next_schedules_text(now))

    def _build_next_schedules_text(self, now: datetime) -> str:
        candidates = []
        weekday_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        profiles = self.controller.get_current_profiles()
        for profile in profiles:
            if not profile.enabled:
                continue
            for day_offset in range(0, 8):
                dt_day = now + timedelta(days=day_offset)
                weekday = dt_day.weekday()
                if weekday not in profile.weekdays:
                    continue
                for ev in profile.events:
                    try:
                        hh, mm = ev.time.split(":")
                        event_dt = dt_day.replace(
                            hour=int(hh),
                            minute=int(mm),
                            second=0,
                            microsecond=0,
                        )
                    except ValueError:
                        continue
                    if event_dt >= now:
                        candidates.append(
                            (event_dt, ev.punch_type, profile.name, weekday_names[weekday], (ev.description or "").strip())
                        )

        if not candidates:
            return "- Nenhum agendamento ativo."

        candidates.sort(key=lambda item: item[0])
        n = max(1, int(self.controller.config.next_appointments_count))
        next_items = candidates[:n]
        lines = []
        for dt, punch_type, profile_name, weekday, desc in next_items:
            base = f"- {dt.strftime('%d/%m %H:%M')} ({weekday}) - {punch_type} [{profile_name}]"
            if desc:
                base = f"{base} — {desc}"
            lines.append(base)
        return "\n".join(lines)

    def _test_connection(self) -> None:
        prev = self.controller.config
        cfg = replace(
            prev,
            login_url=self.login_url_input.text().strip(),
            punch_page_url=self.punch_page_url_input.text().strip(),
            email_selector=self.email_selector_input.text().strip(),
            password_selector=self.password_selector_input.text().strip(),
            submit_selector=self.submit_selector_input.text().strip(),
            punch_button_selector=self.punch_button_selector_input.text().strip(),
            prevent_same_description=self.prevent_same_description_check.isChecked(),
            tolerance_minutes=self.tolerance_input.value(),
            auto_start_windows=self.startup_check.isChecked(),
            headless_browser=self.headless_check.isChecked(),
            browser_pause_seconds=self.browser_pause_spin.value(),
            profiles=self.controller.get_current_profiles(),
        )
        self.controller.save_config_and_credentials(
            cfg,
            self.email_input.text().strip(),
            self.password_input.text(),
        )

        def task() -> tuple[bool, str]:
            return self.controller.test_connection(on_step=self.controller.robot_step)

        def done(ok: bool, msg: str) -> None:
            QMessageBox.information(self, "Teste robô", msg if ok else f"Falhou: {msg}")

        self._run_async_robot(task, done)

    def _test_schedule_punch(self) -> None:
        punch_type = self.event_type_combo.currentText().strip() or "entrada"
        desc = self.event_description_input.text().strip()
        reason = desc or f"teste {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        answer = QMessageBox.question(
            self,
            "Teste de registro",
            (
                "Este teste executa um REGISTRO REAL no Mywork.\n\n"
                f"Tipo: {punch_type}\n"
                f"Descrição: {reason}\n\n"
                "Deseja continuar?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def task() -> tuple[bool, str]:
            return self.controller.manual_punch(
                punch_type,
                custom_reason=reason,
                on_step=self.controller.robot_step,
            )

        def done(ok: bool, msg: str) -> None:
            QMessageBox.information(self, "Teste de registro", msg if ok else f"Falhou: {msg}")
            self.refresh_logs()
            self.refresh_history()

        self._run_async_robot(task, done)

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
