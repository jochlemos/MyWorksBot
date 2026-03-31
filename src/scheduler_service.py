from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from threading import Event, Lock, Thread
from time import sleep

from src.api_client import MyworkApiClient
from src.models import AppConfig
from src.storage import Storage


class SchedulerService:
    def __init__(
        self,
        storage: Storage,
        get_config,
        get_api_client,
        on_log,
        on_notify,
    ) -> None:
        self.storage = storage
        self.get_config = get_config
        self.get_api_client = get_api_client
        self.on_log = on_log
        self.on_notify = on_notify
        self._stop = Event()
        self._thread: Thread | None = None
        self._punch_lock = Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.on_log("INFO", "Agendador iniciado.")

    def stop(self) -> None:
        self._stop.set()
        self.on_log("INFO", "Agendador parado.")

    def _loop(self) -> None:
        while not self._stop.is_set():
            cfg: AppConfig = self.get_config()
            interval = max(1, int(cfg.scheduler_poll_interval_seconds))
            try:
                if cfg.enable_offline_retry:
                    self._flush_offline_queue()
                self._run_due_events()
            except Exception as exc:  # noqa: BLE001
                self.on_log("ERROR", "Erro no agendador.", {"error": str(exc)})
            sleep(interval)

    def _flush_offline_queue(self) -> None:
        cfg: AppConfig = self.get_config()
        state = self.storage.load_runtime_state()
        queue = state.get("offline_queue", [])
        if not queue:
            return
        client: MyworkApiClient = self.get_api_client()
        if not client.is_configured():
            return

        remaining = []
        now = datetime.now()
        for item in queue:
            if not self._can_attempt_new_punch(state, now, cfg):
                remaining.append(item)
                continue
            next_retry_raw = item.get("next_retry_at")
            if next_retry_raw:
                try:
                    next_retry = datetime.fromisoformat(next_retry_raw)
                    if now < next_retry:
                        remaining.append(item)
                        continue
                except ValueError:
                    pass

            _ = datetime.fromisoformat(item["timestamp"])
            ok, msg = client.register_punch(
                item["punch_type"],
                on_step=lambda m: self.on_log("INFO", f"Robô (reenvio): {m}"),
            )
            if ok:
                self._mark_last_successful_punch(state, now)
                self.on_log("INFO", "Reenvio offline realizado.", item)
                self._append_history(
                    punch_type=item["punch_type"],
                    source="retry",
                    success=True,
                    message=msg,
                )
            else:
                retries = int(item.get("retries", 0)) + 1
                next_retry_at = now + timedelta(minutes=cfg.retry_cooldown_minutes)
                item["retries"] = retries
                item["next_retry_at"] = next_retry_at.isoformat(timespec="seconds")
                remaining.append(item)
                self.on_log("WARN", "Reenvio offline falhou.", {"msg": msg, "item": item})
                self._append_history(
                    punch_type=item["punch_type"],
                    source="retry",
                    success=False,
                    message=msg,
                )
        state["offline_queue"] = remaining
        self.storage.save_runtime_state(state)

    def _run_due_events(self) -> None:
        cfg: AppConfig = self.get_config()
        now = datetime.now()
        weekday = now.weekday()
        state = self.storage.load_runtime_state()
        executions = state.get("executions", {})
        failed_attempts = state.get("failed_attempts", {})
        today_key = now.strftime("%Y-%m-%d")
        tolerance = max(0, int(cfg.tolerance_minutes))

        for profile in cfg.profiles:
            if not profile.enabled or weekday not in profile.weekdays:
                continue
            for ev in profile.events:
                key = f"{today_key}|{profile.name}|{ev.punch_type}|{ev.time}"
                if executions.get(key):
                    continue
                failed_at = failed_attempts.get(key)
                if failed_at:
                    try:
                        last_fail = datetime.fromisoformat(failed_at)
                        if now < last_fail + timedelta(minutes=cfg.auto_failure_cooldown_minutes):
                            continue
                    except ValueError:
                        pass
                try:
                    hh, mm = ev.time.split(":")
                    target_minutes = int(hh) * 60 + int(mm)
                except ValueError:
                    self.on_log("WARN", "Horario invalido ignorado.", {"profile": profile.name, "time": ev.time})
                    continue
                now_minutes = now.hour * 60 + now.minute
                if abs(now_minutes - target_minutes) <= tolerance:
                    custom = (ev.description or "").strip() or None
                    success, _ = self._execute_punch(ev.punch_type, source="auto", custom_reason=custom)
                    if success:
                        executions[key] = now.isoformat()
                        failed_attempts.pop(key, None)
                    else:
                        failed_attempts[key] = now.isoformat()
        # Recarrega estado para não sobrescrever chaves atualizadas por _execute_punch
        # (ex.: last_successful_punch_at / successful_contents).
        latest_state = self.storage.load_runtime_state()
        latest_state["executions"] = {k: v for k, v in executions.items() if k.startswith(today_key)}
        latest_state["failed_attempts"] = {
            k: v for k, v in failed_attempts.items() if k.startswith(today_key)
        }
        self.storage.save_runtime_state(latest_state)

    def _execute_punch(
        self,
        punch_type: str,
        source: str,
        custom_reason: str | None = None,
        on_step: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        if not self._punch_lock.acquire(blocking=False):
            self.on_log(
                "WARN",
                "Tentativa de registro ignorada: já existe outra operação em andamento.",
                {"source": source, "punch_type": punch_type},
            )
            return False, "Já existe um registro em andamento. Aguarde a conclusão da operação atual."
        try:
            cfg: AppConfig = self.get_config()
            client: MyworkApiClient = self.get_api_client()
            now = datetime.now()
            state = self.storage.load_runtime_state()
            if self._has_successful_type_today(punch_type, now):
                self.on_log(
                    "WARN",
                    "Registro bloqueado: tipo já registrado com sucesso hoje.",
                    {
                        "source": source,
                        "punch_type": punch_type,
                        "rule": "type_already_success_today",
                    },
                )
                return False, f"Bloqueado: já existe registro de {punch_type} com sucesso hoje."
            effective_reason = self._effective_reason_text(cfg, punch_type, custom_reason)
            if self._has_same_content_today(state, now, punch_type, effective_reason):
                self.on_log(
                    "WARN",
                    "Registro bloqueado por conteúdo repetido no dia.",
                    {
                        "source": source,
                        "punch_type": punch_type,
                        "reason": effective_reason,
                        "rule": "same_type_and_description_today",
                    },
                )
                return False, "Bloqueado: já existe registro com mesmo tipo e descrição hoje."
            if not self._can_attempt_new_punch(state, now, cfg):
                sec = int(cfg.duplicate_guard_seconds)
                msg = (
                    "Bloqueado para evitar duplicidade: já houve registro recente. "
                    f"Aguarde {sec}s."
                )
                self.on_log(
                    "WARN",
                    "Registro bloqueado por proteção de duplicidade.",
                    {"source": source, "rule": "duplicate_guard_seconds"},
                )
                return False, msg
            step_cb: Callable[[str], None] | None
            if on_step is not None:
                step_cb = on_step
            elif source == "auto":
                step_cb = lambda m: self.on_log("INFO", f"Robô (agendado): {m}")
            else:
                step_cb = None
            ok, msg = client.register_punch(punch_type, custom_reason=custom_reason, on_step=step_cb)
            if ok:
                self._mark_last_successful_punch(state, now)
                self._remember_successful_content(state, now, punch_type, effective_reason)
                self.storage.save_runtime_state(state)
                self.on_log("INFO", f"Ponto {punch_type} registrado ({source}).", {"api": msg})
                self._append_history(
                    punch_type=punch_type,
                    source=source,
                    success=True,
                    message=msg,
                )
                self.on_notify(f"Ponto {punch_type} registrado com sucesso.")
                return True, msg

            self.on_log("ERROR", f"Falha ao registrar ponto {punch_type} ({source}).", {"api": msg})
            self._append_history(
                punch_type=punch_type,
                source=source,
                success=False,
                message=msg,
            )
            state["offline_queue"] = []
            self.storage.save_runtime_state(state)
            self.on_notify(f"Falha no registro ({punch_type}). Sem retry automático.")
            return False, msg
        finally:
            self._punch_lock.release()

    def manual_punch(
        self,
        punch_type: str,
        custom_reason: str | None = None,
        on_step: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        return self._execute_punch(
            punch_type,
            source="manual",
            custom_reason=custom_reason,
            on_step=on_step,
        )

    def _append_history(self, punch_type: str, source: str, success: bool, message: str) -> None:
        self.storage.append_history(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "punch_type": punch_type,
                "source": source,
                "status": "sucesso" if success else "falha",
                "message": message,
            }
        )

    def _can_attempt_new_punch(self, state: dict, now: datetime, cfg: AppConfig) -> bool:
        last_success = state.get("last_successful_punch_at")
        if not last_success:
            return True
        try:
            last_dt = datetime.fromisoformat(last_success)
        except ValueError:
            return True
        return (now - last_dt).total_seconds() >= int(cfg.duplicate_guard_seconds)

    def _mark_last_successful_punch(self, state: dict, when: datetime) -> None:
        state["last_successful_punch_at"] = when.isoformat(timespec="seconds")

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def _effective_reason_text(
        self,
        cfg: AppConfig,
        punch_type: str,
        custom_reason: str | None,
    ) -> str:
        custom = (custom_reason or "").strip()
        if custom:
            return custom
        pt = (punch_type or "").strip().lower()
        by_type_extra = (cfg.reason_by_punch_type or {}).get(pt)
        if by_type_extra:
            return by_type_extra
        fallback = {
            "entrada": cfg.reason_entrada,
            "pausa": cfg.reason_pausa,
            "retorno": cfg.reason_retorno,
            "saida": cfg.reason_saida,
        }
        return fallback.get(pt, pt or "registro")

    def _prune_successful_contents(self, state: dict, now: datetime) -> list[dict]:
        day = now.strftime("%Y-%m-%d")
        raw = state.get("successful_contents", [])
        kept: list[dict] = []
        if not isinstance(raw, list):
            return kept
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts = str(item.get("timestamp", "") or "")
            ptype = str(item.get("punch_type", "") or "")
            reason = str(item.get("reason", "") or "")
            if not ts or not ptype:
                continue
            if not ts.startswith(day):
                continue
            kept.append({"timestamp": ts, "punch_type": ptype, "reason": reason})
        return kept

    def _has_same_content_today(
        self,
        state: dict,
        now: datetime,
        punch_type: str,
        reason: str,
    ) -> bool:
        day_items = self._prune_successful_contents(state, now)
        state["successful_contents"] = day_items
        ptype_norm = self._normalize_text(punch_type)
        reason_norm = self._normalize_text(reason)
        for item in day_items:
            if (
                self._normalize_text(item.get("punch_type", "")) == ptype_norm
                and self._normalize_text(item.get("reason", "")) == reason_norm
            ):
                return True
        return False

    def _remember_successful_content(
        self,
        state: dict,
        now: datetime,
        punch_type: str,
        reason: str,
    ) -> None:
        day_items = self._prune_successful_contents(state, now)
        day_items.append(
            {
                "timestamp": now.isoformat(timespec="seconds"),
                "punch_type": (punch_type or "").strip().lower(),
                "reason": (reason or "").strip(),
            }
        )
        state["successful_contents"] = day_items

    def _has_successful_type_today(self, punch_type: str, now: datetime) -> bool:
        today = now.strftime("%Y-%m-%d")
        target = self._normalize_text(punch_type)
        if not target:
            return False
        # Usa histórico persistido para cobrir reinício da aplicação no mesmo dia.
        entries = self.storage.get_history(limit=max(300, int(self.storage.history_max_stored)))
        for item in entries:
            try:
                ts = str(item.get("timestamp", "") or "")
                if not ts.startswith(today):
                    continue
                status = self._normalize_text(str(item.get("status", "") or ""))
                if status != "sucesso":
                    continue
                ptype = self._normalize_text(str(item.get("punch_type", "") or ""))
                if ptype == target:
                    return True
            except Exception:
                continue
        return False
