import json
from dataclasses import asdict
from pathlib import Path

from src.defaults_loader import deep_merge, load_bundled_defaults
from src.models import AppConfig, LogRecord, app_config_from_merged_dict


class Storage:
    def __init__(self) -> None:
        self.app_dir = Path.home() / "AppData" / "Roaming" / "MyworkPontoBot"
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.app_dir / "config.json"
        self.logs_file = self.app_dir / "logs.json"
        self.history_file = self.app_dir / "history.json"
        self.runtime_file = self.app_dir / "runtime_state.json"
        bundled = load_bundled_defaults()
        self.logs_max_stored = int(bundled.get("logs_max_stored", 2000))
        self.history_max_stored = int(bundled.get("history_max_stored", 5000))

    def load_config(self) -> AppConfig:
        defaults = load_bundled_defaults()
        if not self.config_file.exists():
            merged = dict(defaults)
            cfg = app_config_from_merged_dict(merged)
            self._sync_store_limits(cfg)
            self.save_config(cfg)
            return cfg

        try:
            user_raw = json.loads(self.config_file.read_text(encoding="utf-8"))
            if not isinstance(user_raw, dict):
                user_raw = {}
        except (OSError, json.JSONDecodeError):
            user_raw = {}

        merged = deep_merge(defaults, user_raw)
        cfg = app_config_from_merged_dict(merged)
        self._sync_store_limits(cfg)
        return cfg

    def _sync_store_limits(self, config: AppConfig) -> None:
        self.logs_max_stored = max(1, int(config.logs_max_stored))
        self.history_max_stored = max(1, int(config.history_max_stored))

    def save_config(self, config: AppConfig) -> None:
        self._sync_store_limits(config)
        self.config_file.write_text(
            json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def append_log(self, record: LogRecord) -> None:
        cap = self.logs_max_stored
        data = self.get_logs(limit=cap)
        data.append(record.to_dict())
        data = data[-cap:]
        self.logs_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get_logs(self, limit: int = 200) -> list[dict]:
        if not self.logs_file.exists():
            return []
        raw = json.loads(self.logs_file.read_text(encoding="utf-8"))
        return raw[-limit:]

    def clear_logs(self) -> None:
        self.logs_file.write_text("[]", encoding="utf-8")

    def append_history(self, entry: dict) -> None:
        cap = self.history_max_stored
        data = self.get_history(limit=cap)
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
        data = data[-cap:]
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
