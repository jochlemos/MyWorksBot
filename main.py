import argparse
import json
import sys

from PySide6.QtWidgets import QApplication

from src.api_client import MyworkApiClient
from src.models import AppConfig, LogRecord, ScheduleProfile
from src.scheduler_service import SchedulerService
from src.security import SecureCredentialsStore
from src.startup import is_startup_enabled, set_startup
from src.storage import Storage
from src.ui_main import MainWindow


class AppController:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.storage = Storage()
        self.secure_store = SecureCredentialsStore()
        self.config = self.storage.load_config()
        self.email, self.password = self.secure_store.load_credentials()
        self.window: MainWindow | None = None
        self.scheduler = SchedulerService(
            storage=self.storage,
            get_config=lambda: self.config,
            get_api_client=lambda: MyworkApiClient(self.config, self.email, self.password),
            on_log=self.log,
            on_notify=self.notify,
        )

    def bind_window(self, window: MainWindow) -> None:
        self.window = window

    def start(self) -> None:
        self.scheduler.start()
        self.log("INFO", "Aplicação iniciada.")

    def get_config_and_credentials(self) -> tuple[AppConfig, str, str]:
        self.config.auto_start_windows = is_startup_enabled()
        return self.config, self.email, self.password

    def save_config_and_credentials(self, config: AppConfig, email: str, password: str) -> None:
        self.config = config
        self.email = email
        self.password = password
        self.storage.save_config(config)
        self.secure_store.save_credentials(email, password)
        set_startup(config.auto_start_windows)
        self.log("INFO", "Configuração salva.")

    def save_profiles(self, profiles: list[ScheduleProfile]) -> None:
        self.config.profiles = profiles
        self.storage.save_config(self.config)
        self.log("INFO", "Perfis de horários atualizados.")

    def get_current_profiles(self) -> list[ScheduleProfile]:
        return self.config.profiles

    def get_profiles_json(self) -> str:
        return json.dumps(
            [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "weekdays": p.weekdays,
                    "events": [{"time": e.time, "punch_type": e.punch_type} for e in p.events],
                }
                for p in self.config.profiles
            ],
            indent=2,
            ensure_ascii=False,
        )

    def get_status_text(self) -> str:
        if not (self.email and self.password):
            return "Credenciais não configuradas"
        return "Agendador ativo"

    def get_logs_text(self) -> str:
        logs = self.storage.get_logs(limit=300)
        return "\n".join(
            [f"[{x['timestamp']}] {x['level']}: {x['message']} {x.get('details', {})}" for x in logs]
        )

    def get_history_text(self) -> str:
        history = self.storage.get_history(limit=500)
        if not history:
            return "Sem registros ainda."
        return "\n".join(
            [
                (
                    f"[{x.get('timestamp', '-')}] "
                    f"{x.get('status', '-').upper()} | "
                    f"{x.get('punch_type', '-')} | "
                    f"origem={x.get('source', '-')} | "
                    f"{x.get('message', '')}"
                )
                for x in history
            ]
        )

    def clear_logs(self) -> None:
        self.storage.clear_logs()
        if self.window:
            self.window.refresh_logs()

    def clear_history(self) -> None:
        self.storage.clear_history()
        if self.window:
            self.window.refresh_history()

    def log(self, level: str, message: str, details=None) -> None:
        self.storage.append_log(LogRecord.create(level, message, details))
        if self.window:
            self.window.refresh_logs()
            self.window.refresh_history()

    def notify(self, message: str) -> None:
        if self.window:
            self.window.notify(message)

    def manual_punch(self, punch_type: str, custom_reason: str | None = None) -> tuple[bool, str]:
        return self.scheduler.manual_punch(punch_type, custom_reason=custom_reason)

    def test_connection(self) -> tuple[bool, str]:
        client = MyworkApiClient(self.config, self.email, self.password)
        return client.test_connection()

    def quit_app(self) -> None:
        self.scheduler.stop()
        self.app.quit()


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    controller = AppController(app)
    window = MainWindow(controller)
    controller.bind_window(window)
    controller.start()

    if args.minimized:
        window.hide()
    else:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
