from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


PUNCH_TYPES = ["entrada", "pausa", "retorno", "saida"]


@dataclass
class ScheduleEvent:
    time: str
    punch_type: str


@dataclass
class ScheduleProfile:
    name: str
    enabled: bool = True
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    events: list[ScheduleEvent] = field(default_factory=list)


@dataclass
class AppConfig:
    login_url: str = "https://app.mywork.com.br/"
    punch_page_url: str = "https://app.mywork.com.br/ponto"
    email_selector: str = "input[type='email']"
    password_selector: str = "input[type='password']"
    submit_selector: str = "button[type='submit']"
    punch_button_selector: str = "button:has-text('Bater ponto')"
    reason_entrada: str = "entrada"
    reason_pausa: str = "pausa"
    reason_retorno: str = "retorno"
    reason_saida: str = "saida"
    prevent_same_description: bool = True
    tolerance_minutes: int = 5
    auto_start_windows: bool = False
    headless_browser: bool = False
    profiles: list[ScheduleProfile] = field(default_factory=list)


@dataclass
class LogRecord:
    timestamp: str
    level: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls, level: str, message: str, details: dict[str, Any] | None = None
    ) -> "LogRecord":
        return cls(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            level=level,
            message=message,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
