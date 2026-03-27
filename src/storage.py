import json
from dataclasses import asdict
from pathlib import Path

from src.models import AppConfig, LogRecord, ScheduleEvent, ScheduleProfile


class Storage:
    def __init__(self) -> None:
        self.app_dir = Path.home() / "AppData" / "Roaming" / "MyworkPontoBot"
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.app_dir / "config.json"
        self.logs_file = self.app_dir / "logs.json"
        self.history_file = self.app_dir / "history.json"
        self.runtime_file = self.app_dir / "runtime_state.json"

    def load_config(self) -> AppConfig:
        if not self.config_file.exists():
            cfg = AppConfig(
                profiles=[
                    ScheduleProfile(
                        name="Dias úteis",
                        weekdays=[0, 1, 2, 3, 4],
                        events=[
                            ScheduleEvent(time="08:00", punch_type="entrada"),
                            ScheduleEvent(time="12:00", punch_type="pausa"),
                            ScheduleEvent(time="13:00", punch_type="retorno"),
                            ScheduleEvent(time="18:00", punch_type="saida"),
                        ],
                    )
                ]
            )
            self.save_config(cfg)
            return cfg

        raw = json.loads(self.config_file.read_text(encoding="utf-8"))
        profiles: list[ScheduleProfile] = []
        for p in raw.get("profiles", []):
            events = [ScheduleEvent(**e) for e in p.get("events", [])]
            profiles.append(
                ScheduleProfile(
                    name=p.get("name", "Perfil"),
                    enabled=p.get("enabled", True),
                    weekdays=p.get("weekdays", [0, 1, 2, 3, 4]),
                    events=events,
                )
            )
        return AppConfig(
            login_url=raw.get("login_url", "https://app.mywork.com.br/"),
            punch_page_url=raw.get("punch_page_url", "https://app.mywork.com.br/ponto"),
            email_selector=raw.get("email_selector", "input[type='email']"),
            password_selector=raw.get("password_selector", "input[type='password']"),
            submit_selector=raw.get("submit_selector", "button[type='submit']"),
            punch_button_selector=raw.get("punch_button_selector", "button:has-text('Bater ponto')"),
            reason_entrada=raw.get("reason_entrada", "entrada"),
            reason_pausa=raw.get("reason_pausa", "pausa"),
            reason_retorno=raw.get("reason_retorno", "retorno"),
            reason_saida=raw.get("reason_saida", "saida"),
            prevent_same_description=bool(raw.get("prevent_same_description", True)),
            tolerance_minutes=int(raw.get("tolerance_minutes", 5)),
            auto_start_windows=bool(raw.get("auto_start_windows", False)),
            headless_browser=bool(raw.get("headless_browser", False)),
            profiles=profiles,
        )

    def save_config(self, config: AppConfig) -> None:
        self.config_file.write_text(
            json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def append_log(self, record: LogRecord) -> None:
        data = self.get_logs(limit=2000)
        data.append(record.to_dict())
        data = data[-2000:]
        self.logs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_logs(self, limit: int = 200) -> list[dict]:
        if not self.logs_file.exists():
            return []
        raw = json.loads(self.logs_file.read_text(encoding="utf-8"))
        return raw[-limit:]

    def clear_logs(self) -> None:
        self.logs_file.write_text("[]", encoding="utf-8")

    def append_history(self, entry: dict) -> None:
        data = self.get_history(limit=5000)
        if data:
            last = data[-1]
            same_as_last = (
                last.get("punch_type") == entry.get("punch_type")
                and last.get("source") == entry.get("source")
                and last.get("status") == entry.get("status")
                and (last.get("message") or "").strip() == (entry.get("message") or "").strip()
            )
            if same_as_last:
                return
        data.append(entry)
        data = data[-5000:]
        self.history_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_history(self, limit: int = 300) -> list[dict]:
        if not self.history_file.exists():
            return []
        raw = json.loads(self.history_file.read_text(encoding="utf-8"))
        return raw[-limit:]

    def clear_history(self) -> None:
        self.history_file.write_text("[]", encoding="utf-8")

    def load_runtime_state(self) -> dict:
        if not self.runtime_file.exists():
            return {}
        return json.loads(self.runtime_file.read_text(encoding="utf-8"))

    def save_runtime_state(self, data: dict) -> None:
        self.runtime_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
