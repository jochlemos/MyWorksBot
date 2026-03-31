from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScheduleEvent:
    time: str
    punch_type: str
    # Texto enviado ao site como motivo/descrição; vazio = padrão da configuração por tipo.
    description: str = ""


@dataclass
class ScheduleProfile:
    name: str
    enabled: bool = True
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    events: list[ScheduleEvent] = field(default_factory=list)


def parse_profiles_from_raw(raw: list[dict[str, Any]] | None) -> list[ScheduleProfile]:
    if not raw:
        return []
    profiles: list[ScheduleProfile] = []
    for p in raw:
        events = [
            ScheduleEvent(
                time=str(e["time"]),
                punch_type=str(e["punch_type"]),
                description=str(e.get("description", "") or ""),
            )
            for e in p.get("events", [])
        ]
        profiles.append(
            ScheduleProfile(
                name=str(p.get("name", "Perfil")),
                enabled=bool(p.get("enabled", True)),
                weekdays=list(p.get("weekdays", [0, 1, 2, 3, 4])),
                events=events,
            )
        )
    return profiles


@dataclass
class AppConfig:
    login_url: str = ""
    punch_page_url: str = ""
    punch_page_url_redirects: dict[str, str] = field(default_factory=dict)
    email_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""
    punch_button_selector: str = ""
    reason_entrada: str = ""
    reason_pausa: str = ""
    reason_retorno: str = ""
    reason_saida: str = ""
    reason_by_punch_type: dict[str, str] = field(default_factory=dict)
    prevent_same_description: bool = True
    tolerance_minutes: int = 5
    auto_start_windows: bool = False
    headless_browser: bool = False
    enable_notification_sounds: bool = True
    collapsed_ui_scale: str = "medio"
    browser_pause_seconds: int = 15
    browser_pause_max_seconds: int = 120
    punch_types: list[str] = field(default_factory=list)
    scheduler_poll_interval_seconds: int = 20
    max_records_per_day: int = 4
    duplicate_guard_seconds: int = 90
    auto_failure_cooldown_minutes: int = 3
    retry_cooldown_minutes: int = 5
    enable_offline_retry: bool = False
    robot_ui_timeout_ms: int = 300_000
    next_appointments_count: int = 3
    logs_display_limit: int = 300
    history_display_limit: int = 500
    logs_max_stored: int = 2000
    history_max_stored: int = 5000
    playwright_navigation_timeout_ms: int = 30_000
    playwright_field_timeout_ms: int = 12_000
    playwright_post_login_stabilize_ms: int = 800
    playwright_login_wait_timeout_ms: int = 30_000
    playwright_login_poll_ms: int = 400
    playwright_login_transition_ms: int = 600
    playwright_punch_click_timeout_ms: int = 15_000
    playwright_history_wait_timeout_ms: int = 20_000
    playwright_history_poll_step_ms: int = 1000
    playwright_reason_modal_fill_timeout_ms: int = 3000
    playwright_reason_modal_confirm_timeout_ms: int = 8000
    playwright_reason_modal_after_click_ms: int = 1200
    playwright_menu_click_timeout_ms: int = 4000
    playwright_menu_after_click_ms: int = 1500
    selector_fallback_email: list[str] = field(default_factory=list)
    selector_fallback_password: list[str] = field(default_factory=list)
    selector_fallback_submit: list[str] = field(default_factory=list)
    login_error_selectors: list[str] = field(default_factory=list)
    still_on_login_password_selector: str = ""
    still_on_login_submit_selectors: list[str] = field(default_factory=list)
    login_wait_redirect_path_substrings: list[str] = field(default_factory=list)
    login_wait_oauth_substring_markers: list[str] = field(default_factory=list)
    logged_in_ui_markers: list[str] = field(default_factory=list)
    punch_context_url_substrings: list[str] = field(default_factory=list)
    punch_context_indicators: list[str] = field(default_factory=list)
    navigation_menu_selectors: list[str] = field(default_factory=list)
    punch_selectors_base: list[str] = field(default_factory=list)
    punch_selectors_by_type: dict[str, list[str]] = field(default_factory=dict)
    reason_modal_fields: list[str] = field(default_factory=list)
    reason_modal_confirm_buttons: list[str] = field(default_factory=list)
    reason_modal_indicators: list[str] = field(default_factory=list)
    visible_error_feedback_selectors: list[str] = field(default_factory=list)
    history_marker_selectors: list[str] = field(default_factory=list)
    history_comment_cell_selectors: list[str] = field(default_factory=list)
    profiles: list[ScheduleProfile] = field(default_factory=list)


def app_config_from_merged_dict(raw: dict[str, Any]) -> AppConfig:
    redirects = raw.get("punch_page_url_redirects")
    if not isinstance(redirects, dict):
        redirects = {}
    punch_sel_by_type = raw.get("punch_selectors_by_type")
    if not isinstance(punch_sel_by_type, dict):
        punch_sel_by_type = {}
    cleaned_by_type: dict[str, list[str]] = {}
    for k, v in punch_sel_by_type.items():
        if isinstance(v, list):
            cleaned_by_type[str(k)] = [str(x) for x in v]

    reason_by = raw.get("reason_by_punch_type")
    if not isinstance(reason_by, dict):
        reason_by = {}

    def _str_list(key: str) -> list[str]:
        v = raw.get(key)
        if not isinstance(v, list):
            return []
        return [str(x) for x in v]

    profiles = parse_profiles_from_raw(raw.get("profiles"))

    return AppConfig(
        login_url=str(raw.get("login_url", "") or ""),
        punch_page_url=str(raw.get("punch_page_url", "") or ""),
        punch_page_url_redirects={str(k): str(v) for k, v in redirects.items()},
        email_selector=str(raw.get("email_selector", "") or ""),
        password_selector=str(raw.get("password_selector", "") or ""),
        submit_selector=str(raw.get("submit_selector", "") or ""),
        punch_button_selector=str(raw.get("punch_button_selector", "") or ""),
        reason_entrada=str(raw.get("reason_entrada", "") or ""),
        reason_pausa=str(raw.get("reason_pausa", "") or ""),
        reason_retorno=str(raw.get("reason_retorno", "") or ""),
        reason_saida=str(raw.get("reason_saida", "") or ""),
        reason_by_punch_type={str(k): str(v) for k, v in reason_by.items()},
        prevent_same_description=bool(raw.get("prevent_same_description", True)),
        tolerance_minutes=int(raw.get("tolerance_minutes", 5)),
        auto_start_windows=bool(raw.get("auto_start_windows", False)),
        headless_browser=bool(raw.get("headless_browser", False)),
        enable_notification_sounds=bool(raw.get("enable_notification_sounds", True)),
        collapsed_ui_scale=str(raw.get("collapsed_ui_scale", "medio") or "medio"),
        browser_pause_seconds=int(raw.get("browser_pause_seconds", 15)),
        browser_pause_max_seconds=int(raw.get("browser_pause_max_seconds", 120)),
        punch_types=_str_list("punch_types"),
        scheduler_poll_interval_seconds=int(raw.get("scheduler_poll_interval_seconds", 20)),
        max_records_per_day=int(raw.get("max_records_per_day", 4)),
        duplicate_guard_seconds=int(raw.get("duplicate_guard_seconds", 90)),
        auto_failure_cooldown_minutes=int(raw.get("auto_failure_cooldown_minutes", 3)),
        retry_cooldown_minutes=int(raw.get("retry_cooldown_minutes", 5)),
        enable_offline_retry=bool(raw.get("enable_offline_retry", False)),
        robot_ui_timeout_ms=int(raw.get("robot_ui_timeout_ms", 300_000)),
        next_appointments_count=int(raw.get("next_appointments_count", 3)),
        logs_display_limit=int(raw.get("logs_display_limit", 300)),
        history_display_limit=int(raw.get("history_display_limit", 500)),
        logs_max_stored=int(raw.get("logs_max_stored", 2000)),
        history_max_stored=int(raw.get("history_max_stored", 5000)),
        playwright_navigation_timeout_ms=int(raw.get("playwright_navigation_timeout_ms", 30_000)),
        playwright_field_timeout_ms=int(raw.get("playwright_field_timeout_ms", 12_000)),
        playwright_post_login_stabilize_ms=int(raw.get("playwright_post_login_stabilize_ms", 800)),
        playwright_login_wait_timeout_ms=int(raw.get("playwright_login_wait_timeout_ms", 30_000)),
        playwright_login_poll_ms=int(raw.get("playwright_login_poll_ms", 400)),
        playwright_login_transition_ms=int(raw.get("playwright_login_transition_ms", 600)),
        playwright_punch_click_timeout_ms=int(raw.get("playwright_punch_click_timeout_ms", 15_000)),
        playwright_history_wait_timeout_ms=int(raw.get("playwright_history_wait_timeout_ms", 20_000)),
        playwright_history_poll_step_ms=int(raw.get("playwright_history_poll_step_ms", 1000)),
        playwright_reason_modal_fill_timeout_ms=int(
            raw.get("playwright_reason_modal_fill_timeout_ms", 3000)
        ),
        playwright_reason_modal_confirm_timeout_ms=int(
            raw.get("playwright_reason_modal_confirm_timeout_ms", 8000)
        ),
        playwright_reason_modal_after_click_ms=int(
            raw.get("playwright_reason_modal_after_click_ms", 1200)
        ),
        playwright_menu_click_timeout_ms=int(raw.get("playwright_menu_click_timeout_ms", 4000)),
        playwright_menu_after_click_ms=int(raw.get("playwright_menu_after_click_ms", 1500)),
        selector_fallback_email=_str_list("selector_fallback_email"),
        selector_fallback_password=_str_list("selector_fallback_password"),
        selector_fallback_submit=_str_list("selector_fallback_submit"),
        login_error_selectors=_str_list("login_error_selectors"),
        still_on_login_password_selector=str(raw.get("still_on_login_password_selector", "") or ""),
        still_on_login_submit_selectors=_str_list("still_on_login_submit_selectors"),
        login_wait_redirect_path_substrings=_str_list("login_wait_redirect_path_substrings"),
        login_wait_oauth_substring_markers=_str_list("login_wait_oauth_substring_markers"),
        logged_in_ui_markers=_str_list("logged_in_ui_markers"),
        punch_context_url_substrings=_str_list("punch_context_url_substrings"),
        punch_context_indicators=_str_list("punch_context_indicators"),
        navigation_menu_selectors=_str_list("navigation_menu_selectors"),
        punch_selectors_base=_str_list("punch_selectors_base"),
        punch_selectors_by_type=cleaned_by_type,
        reason_modal_fields=_str_list("reason_modal_fields"),
        reason_modal_confirm_buttons=_str_list("reason_modal_confirm_buttons"),
        reason_modal_indicators=_str_list("reason_modal_indicators"),
        visible_error_feedback_selectors=_str_list("visible_error_feedback_selectors"),
        history_marker_selectors=_str_list("history_marker_selectors"),
        history_comment_cell_selectors=_str_list("history_comment_cell_selectors"),
        profiles=profiles,
    )


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
