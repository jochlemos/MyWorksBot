import time
import hashlib

from collections.abc import Callable
from datetime import datetime
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.models import AppConfig

RobotStepCallback = Callable[[str], None] | None


class MyworkApiClient:
    def __init__(self, config: AppConfig, email: str, password: str) -> None:
        self.config = config
        self.email = email.strip()
        self.password = password

    @staticmethod
    def _step(on_step: RobotStepCallback, message: str) -> None:
        if on_step:
            try:
                on_step(message)
            except Exception:
                pass

    def _nav_timeout(self) -> int:
        return max(1000, int(self.config.playwright_navigation_timeout_ms))

    def _field_timeout(self) -> int:
        return max(1000, int(self.config.playwright_field_timeout_ms))

    def _email_selectors(self) -> list[str]:
        return self._unique_selectors(
            [self.config.email_selector, *self.config.selector_fallback_email]
        )

    def _password_selectors(self) -> list[str]:
        return self._unique_selectors(
            [self.config.password_selector, *self.config.selector_fallback_password]
        )

    def _submit_selectors(self) -> list[str]:
        return self._unique_selectors(
            [self.config.submit_selector, *self.config.selector_fallback_submit]
        )

    def _apply_post_run_pause(self, page, on_step: RobotStepCallback) -> None:
        if self.config.headless_browser:
            return
        cap = max(0, int(self.config.browser_pause_max_seconds))
        sec = max(0, min(cap, int(self.config.browser_pause_seconds or 0)))
        if sec <= 0:
            return
        self._step(
            on_step,
            f"Navegador visível: aguardando {sec}s antes de fechar (ajuste em Configuração).",
        )
        page.wait_for_timeout(sec * 1000)

    def is_configured(self) -> bool:
        return bool(
            self.email
            and self.password
            and self.config.login_url
            and self.config.punch_page_url
            and self.config.email_selector
            and self.config.password_selector
            and self.config.submit_selector
            and self.config.punch_button_selector
        )

    def register_punch(
        self,
        punch_type: str,
        custom_reason: str | None = None,
        on_step: RobotStepCallback = None,
    ) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Robô não configurado (credenciais/URLs/seletores)."
        punch_to = max(1000, int(self.config.playwright_punch_click_timeout_ms))
        hist_to = max(1000, int(self.config.playwright_history_wait_timeout_ms))
        post_login = max(0, int(self.config.playwright_post_login_stabilize_ms))
        try:
            with sync_playwright() as p:
                self._step(on_step, "Iniciando motor do navegador (Playwright).")
                headless = self.config.headless_browser
                self._step(
                    on_step,
                    "Modo do navegador: oculto (headless)."
                    if headless
                    else "Modo do navegador: janela visível.",
                )
                browser = p.chromium.launch(headless=headless)
                self._step(on_step, "Navegador aberto; criando nova aba.")
                page = browser.new_page()
                self._perform_login(page, on_step)
                self._step(on_step, "Estabilizando sessão após login.")
                if post_login:
                    page.wait_for_timeout(post_login)
                self._ensure_on_punch_page(page, on_step)
                reason_text = (custom_reason or "").strip() or self._reason_text_for_punch(punch_type)
                self._step(on_step, "Verificando regras de descrição e histórico.")
                max_per_day = max(1, int(getattr(self.config, "max_records_per_day", 4)))
                today_count = self._count_today_history_records(page)
                if today_count >= max_per_day:
                    self._apply_post_run_pause(page, on_step)
                    browser.close()
                    return (
                        False,
                        f"Bloqueado: já existem {max_per_day} registros para hoje no histórico.",
                    )
                if self._has_same_punch_type_today(page, punch_type):
                    self._apply_post_run_pause(page, on_step)
                    browser.close()
                    return (
                        False,
                        f"Bloqueado: já existe registro de {punch_type} hoje no histórico.",
                    )
                if self.config.prevent_same_description:
                    latest_comment = self._get_latest_history_comment(page)
                    if latest_comment and self._normalize_text(latest_comment) == self._normalize_text(
                        reason_text
                    ):
                        self._apply_post_run_pause(page, on_step)
                        browser.close()
                        return (
                            False,
                            "Bloqueado: a última descrição no histórico é igual à nova descrição.",
                        )
                self._wait_for_history_ready(page, timeout_ms=min(hist_to, 6000))
                history_before = self._history_snapshot(page)
                self._step(
                    on_step,
                    f"Snapshot histórico (antes): hoje={history_before.get('today_count', 0)}, "
                    f"primeira_linha_hash={history_before.get('first_row_hash', '')}.",
                )
                self._step(on_step, "Aguardando controles de ação de ponto ficarem prontos.")
                self._wait_for_punch_action_ready(page, punch_type=punch_type, timeout_ms=min(punch_to, 8000))
                self._step(on_step, f"Clicando no tipo de batida: {punch_type}.")
                try:
                    used_selector = self._click_first_with_selector(
                        page,
                        self._selectors_for_punch(punch_type),
                        timeout_ms=punch_to,
                    )
                    self._step(on_step, f"Clique executado com seletor: {used_selector}")
                except RuntimeError:
                    self._step(on_step, "Tentando abrir área de ponto pelo menu.")
                    self._try_open_punch_area(page)
                    used_selector = self._click_first_with_selector(
                        page,
                        self._selectors_for_punch(punch_type),
                        timeout_ms=punch_to,
                    )
                    self._step(on_step, f"Clique executado após menu com seletor: {used_selector}")
                self._step(on_step, "Preenchendo motivo / modal (se aparecer).")
                modal_status = self._handle_reason_modal(
                    page, punch_type, custom_reason=reason_text, on_step=on_step
                )
                self._step(
                    on_step,
                    "Status modal: "
                    f"visivel={modal_status.get('modal_visible')}, "
                    f"preenchido={modal_status.get('filled')}, "
                    f"confirmado={modal_status.get('confirmed')}.",
                )
                self._step(on_step, "Aguardando atualização da tabela de histórico.")
                history_changed = self._wait_for_history_change(
                    page, history_before, punch_type=punch_type, timeout_ms=hist_to
                )
                if not history_changed:
                    history_after = self._history_snapshot(page)
                    self._step(
                        on_step,
                        f"Snapshot histórico (depois): hoje={history_after.get('today_count', 0)}, "
                        f"primeira_linha_hash={history_after.get('first_row_hash', '')}.",
                    )
                    if self._has_visible_error_feedback(page):
                        raise RuntimeError(
                            "Clique executado, mas a tela exibiu erro de validação/confirmação."
                        )
                    raise RuntimeError(
                        "Clique executado, mas não houve confirmação no histórico dentro do tempo esperado."
                    )
                self._apply_post_run_pause(page, on_step)
                self._step(on_step, "Encerrando navegador.")
                browser.close()
                return True, f"Ponto {punch_type} executado pelo robô."
        except PlaywrightTimeoutError as exc:
            return False, f"Timeout no robô: {exc}"
        except PlaywrightError as exc:
            return False, f"Erro no Playwright: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Erro inesperado: {exc}"

    def test_connection(self, on_step: RobotStepCallback = None) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Configure credenciais e seletores primeiro."
        try:
            with sync_playwright() as p:
                headless = self.config.headless_browser
                self._step(
                    on_step,
                    "Teste: navegador em modo oculto."
                    if headless
                    else "Teste: navegador com janela visível.",
                )
                browser = p.chromium.launch(headless=headless)
                page = browser.new_page()
                self._perform_login(page, on_step)
                self._ensure_on_punch_page(page, on_step)
                self._apply_post_run_pause(page, on_step)
                self._step(on_step, "Teste: fechando navegador.")
                browser.close()
            return True, "Login automatizado executado."
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def verify_punch_in_history(
        self,
        punch_type: str,
        on_step: RobotStepCallback = None,
    ) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Robô não configurado (credenciais/URLs/seletores)."
        post_login = max(0, int(self.config.playwright_post_login_stabilize_ms))
        try:
            with sync_playwright() as p:
                self._step(on_step, "Verificação tardia: iniciando navegador.")
                browser = p.chromium.launch(headless=self.config.headless_browser)
                page = browser.new_page()
                self._perform_login(page, on_step)
                if post_login:
                    page.wait_for_timeout(post_login)
                self._ensure_on_punch_page(page, on_step)
                self._wait_for_history_ready(page, timeout_ms=6000)
                count = self._count_today_history_records_by_type(page, punch_type)
                self._apply_post_run_pause(page, on_step)
                browser.close()
                if count > 0:
                    return True, f"Verificação tardia: encontrado(s) {count} registro(s) de {punch_type} hoje."
                return False, f"Verificação tardia: nenhum registro de {punch_type} encontrado hoje na tabela."
        except Exception as exc:  # noqa: BLE001
            return False, f"Verificação tardia falhou: {exc}"

    def _perform_login(self, page, on_step: RobotStepCallback = None) -> None:
        nav_to = self._nav_timeout()
        field_to = self._field_timeout()
        self._step(on_step, "Abrindo URL de login.")
        page.goto(self.config.login_url, wait_until="domcontentloaded", timeout=nav_to)
        self._step(on_step, "Preenchendo e-mail.")
        self._fill_first(
            page,
            self._email_selectors(),
            value=self.email,
            timeout_ms=field_to,
            field_name="usuário/e-mail",
        )
        self._step(on_step, "Preenchendo senha.")
        self._fill_first(
            page,
            self._password_selectors(),
            value=self.password,
            timeout_ms=field_to,
            field_name="senha",
        )
        pre_submit_url = (page.url or "").strip()
        self._step(on_step, "Enviando formulário de login.")
        self._click_first(
            page,
            self._submit_selectors(),
            timeout_ms=field_to,
        )
        self._step(on_step, "Aguardando confirmação do login (sessão).")
        self._wait_for_login_success(page, pre_submit_url)
        self._step(on_step, "Login confirmado.")

    def _login_error_visible(self, page) -> bool:
        selectors = self.config.login_error_selectors
        keywords = [
            "credenciais inválidas",
            "usuario ou senha incorretos",
            "usuário ou senha incorretos",
            "senha incorreta",
            "dados inválidos",
            "login inválido",
            "falha no login",
        ]
        for selector in selectors:
            for ctx in self._iter_contexts(page):
                try:
                    loc = ctx.locator(selector).first
                    if loc.count() > 0 and loc.is_visible():
                        txt = self._normalize_text(loc.inner_text() or "")
                        if any(k in txt for k in keywords):
                            return True
                except Exception:
                    continue
        return False

    def _still_on_login_form(self, page) -> bool:
        pwd_sel = (self.config.still_on_login_password_selector or "").strip()
        if not pwd_sel:
            return False
        subs = self.config.still_on_login_submit_selectors
        sub_joined = ", ".join(subs) if subs else ""
        try:
            for ctx in self._iter_contexts(page):
                pwd = ctx.locator(pwd_sel).first
                if pwd.count() == 0:
                    continue
                if not sub_joined:
                    return True
                sub = ctx.locator(sub_joined).first
                if sub.count() > 0:
                    return True
        except Exception:
            pass
        return False

    def _has_logged_in_ui(self, page) -> bool:
        if self._is_punch_context(page):
            return True
        for selector in self.config.logged_in_ui_markers:
            for ctx in self._iter_contexts(page):
                try:
                    loc = ctx.locator(selector).first
                    if loc.count() > 0 and loc.is_visible():
                        return True
                except Exception:
                    continue
        return False

    def _wait_for_login_success(self, page, pre_submit_url: str, timeout_ms: int | None = None) -> None:
        if timeout_ms is None:
            timeout_ms = max(1000, int(self.config.playwright_login_wait_timeout_ms))
        poll = max(50, int(self.config.playwright_login_poll_ms))
        trans = max(50, int(self.config.playwright_login_transition_ms))
        deadline = time.monotonic() + timeout_ms / 1000.0
        pre = (pre_submit_url or "").strip()
        while time.monotonic() < deadline:
            # Considera erro de login apenas enquanto ainda estamos no formulário.
            if self._still_on_login_form(page) and self._login_error_visible(page):
                raise RuntimeError(
                    "Falha no login: mensagem de erro na tela ou credenciais inválidas."
                )
            if self._is_punch_context(page):
                return
            if self._has_logged_in_ui(page):
                return
            cur = (page.url or "").strip()
            if cur != pre:
                low = cur.lower()
                path_markers = self.config.login_wait_redirect_path_substrings
                if path_markers and any((m and m.lower() in low) for m in path_markers):
                    page.wait_for_timeout(poll)
                    continue
                oauth_markers = self.config.login_wait_oauth_substring_markers
                if oauth_markers and all((m and m.lower() in low) for m in oauth_markers):
                    page.wait_for_timeout(poll)
                    continue
                return
            if not self._still_on_login_form(page):
                page.wait_for_timeout(trans)
                if not self._still_on_login_form(page):
                    return
            page.wait_for_timeout(poll)

        if self._still_on_login_form(page) and self._login_error_visible(page):
            raise RuntimeError("Falha no login: verifique usuário e senha.")
        if self._has_logged_in_ui(page) or self._is_punch_context(page):
            return
        if self._still_on_login_form(page):
            # Fallback para fluxos que mantêm /login por mais tempo: tenta abrir
            # diretamente a página de ponto para validar sessão autenticada.
            try:
                probe_url = self._effective_punch_url()
                if probe_url:
                    page.goto(probe_url, wait_until="domcontentloaded", timeout=self._nav_timeout())
                    if self._is_punch_context(page) or self._has_logged_in_ui(page):
                        return
            except Exception:
                pass
            raise RuntimeError(
                f"Login não foi concluído no tempo esperado (sessão não detectada). URL: {page.url}"
            )
        raise RuntimeError(f"Não foi possível confirmar o login. URL: {page.url}")

    def _effective_punch_url(self) -> str:
        configured = (self.config.punch_page_url or "").strip()
        if not configured:
            return ""
        lowered = configured.rstrip("/").lower()
        redirects = self.config.punch_page_url_redirects or {}
        for key, target in redirects.items():
            k = (key or "").strip().rstrip("/").lower()
            if k and k == lowered:
                return (target or "").strip()
        return configured

    def _ensure_on_punch_page(self, page, on_step: RobotStepCallback = None) -> None:
        nav_to = self._nav_timeout()
        target = self._effective_punch_url()
        if not target:
            raise RuntimeError("URL da página de ponto não configurada.")
        self._step(on_step, f"Carregando página de ponto ({target}).")
        page.goto(target, wait_until="domcontentloaded", timeout=nav_to)
        if self._is_punch_context(page):
            self._step(on_step, "Página de ponto detectada.")
            return

        self._step(on_step, "Procurando atalho para Ponto no menu.")
        self._try_open_punch_area(page)
        if self._is_punch_context(page):
            self._step(on_step, "Página de ponto aberta pelo menu.")
            return

        self._step(on_step, "Segunda tentativa de carregamento (rede).")
        page.goto(target, wait_until="networkidle", timeout=nav_to)
        if self._is_punch_context(page):
            self._step(on_step, "Página de ponto carregada (2ª tentativa).")
            return
        raise RuntimeError(f"Não foi possível abrir a página de ponto. URL atual: {page.url}")

    def _is_punch_context(self, page) -> bool:
        current_url = (page.url or "").lower()
        for sub in self.config.punch_context_url_substrings:
            if sub and sub.lower() in current_url:
                return True
        for selector in self.config.punch_context_indicators:
            for ctx in self._iter_contexts(page):
                try:
                    locator = ctx.locator(selector).first
                    if locator.count() and locator.is_visible():
                        return True
                except Exception:
                    continue
        return False

    def _iter_contexts(self, page) -> list:
        return [page, *page.frames]

    def _fill_first(
        self,
        page,
        selectors: list[str],
        value: str,
        timeout_ms: int,
        field_name: str,
    ) -> None:
        errors: list[str] = []
        for selector in self._unique_selectors(selectors):
            for ctx in self._iter_contexts(page):
                try:
                    field = ctx.locator(selector).first
                    if field.count() == 0:
                        continue
                    field.scroll_into_view_if_needed(timeout=timeout_ms)
                    try:
                        field.fill(value, timeout=timeout_ms)
                    except Exception:
                        field.click(timeout=timeout_ms)
                        field.evaluate(
                            """(el, v) => {
                                el.value = v;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }""",
                            value,
                        )
                    return
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{selector}: {exc}")
        sample_inputs = self._collect_input_diagnostics(page)
        raise RuntimeError(
            f"Nenhum seletor de {field_name} funcionou. "
            + " | ".join(errors[:3])
            + f" | Inputs encontrados: {sample_inputs}"
        )

    def _click_first(self, page, selectors: list[str], timeout_ms: int) -> None:
        self._click_first_with_selector(page, selectors, timeout_ms)

    def _click_first_with_selector(self, page, selectors: list[str], timeout_ms: int) -> str:
        errors: list[str] = []
        for selector in self._unique_selectors(selectors):
            for ctx in self._iter_contexts(page):
                try:
                    button = ctx.locator(selector).first
                    if button.count() == 0:
                        continue
                    button.scroll_into_view_if_needed(timeout=timeout_ms)
                    button.click(timeout=timeout_ms)
                    return selector
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{selector}: {exc}")
        visible_buttons = self._collect_button_diagnostics(page)
        raise RuntimeError(
            "Nenhum seletor de botão funcionou. "
            + " | ".join(errors[:3])
            + f" | URL atual: {page.url}"
            + f" | Botões encontrados: {visible_buttons}"
        )

    def _wait_for_history_ready(self, page, timeout_ms: int = 5000) -> None:
        elapsed = 0
        step = 500
        while elapsed < timeout_ms:
            snap = self._history_snapshot(page)
            if int(snap.get("today_count", 0) or 0) > 0 or str(snap.get("first_row_hash", "") or ""):
                return
            page.wait_for_timeout(step)
            elapsed += step

    def _wait_for_punch_action_ready(self, page, punch_type: str, timeout_ms: int = 8000) -> None:
        selectors = self._selectors_for_punch(punch_type)
        elapsed = 0
        step = 400
        while elapsed < timeout_ms:
            for selector in selectors:
                for ctx in self._iter_contexts(page):
                    try:
                        loc = ctx.locator(selector).first
                        if loc.count() > 0 and loc.is_visible():
                            return
                    except Exception:
                        continue
            page.wait_for_timeout(step)
            elapsed += step

    def _collect_input_diagnostics(self, page) -> str:
        snippets: list[str] = []
        for ctx in self._iter_contexts(page):
            try:
                fields = ctx.locator("input").all()[:6]
                for field in fields:
                    kind = field.get_attribute("type") or ""
                    name = field.get_attribute("name") or ""
                    field_id = field.get_attribute("id") or ""
                    placeholder = field.get_attribute("placeholder") or ""
                    snippets.append(
                        f"type={kind},name={name},id={field_id},placeholder={placeholder}"
                    )
            except Exception:
                continue
            if len(snippets) >= 6:
                break
        if not snippets:
            return "nenhum input visível"
        return "; ".join(snippets[:6])

    def _collect_button_diagnostics(self, page) -> str:
        snippets: list[str] = []
        for ctx in self._iter_contexts(page):
            try:
                buttons = ctx.locator("button, input[type='button'], input[type='submit']").all()[:8]
                for button in buttons:
                    text = (button.inner_text() or "").strip()
                    if not text:
                        text = (button.get_attribute("value") or "").strip()
                    button_id = button.get_attribute("id") or ""
                    button_name = button.get_attribute("name") or ""
                    snippets.append(f"text={text},id={button_id},name={button_name}")
            except Exception:
                continue
            if len(snippets) >= 8:
                break
        if not snippets:
            return "nenhum botão visível"
        return "; ".join(snippets[:8])

    def _history_snapshot(self, page) -> dict[str, str | int]:
        today_label = datetime.now().strftime("%d/%m/%Y")
        first_row_text = ""
        today_count = 0
        for ctx in self._iter_contexts(page):
            try:
                rows = ctx.locator("table tbody tr").all()
            except Exception:
                continue
            for idx, row in enumerate(rows):
                try:
                    row_text = self._normalize_text(row.inner_text() or "")
                    if idx == 0 and row_text and not first_row_text:
                        first_row_text = row_text
                    first_cell = row.locator("td").first
                    if first_cell.count() == 0:
                        continue
                    text = (first_cell.inner_text() or "").strip()
                    if today_label in text:
                        today_count += 1
                except Exception:
                    continue
        return {
            "today_count": today_count,
            "first_row_text": first_row_text,
            "first_row_hash": self._stable_hash(first_row_text),
        }

    def _get_latest_history_comment(self, page) -> str:
        for selector in self.config.history_comment_cell_selectors:
            for ctx in self._iter_contexts(page):
                try:
                    cell = ctx.locator(selector).first
                    if cell.count() == 0:
                        continue
                    text = (cell.inner_text() or "").strip()
                    if text:
                        return text
                except Exception:
                    continue
        return ""

    def _wait_for_history_change(
        self,
        page,
        history_before: dict[str, str | int],
        punch_type: str,
        timeout_ms: int,
    ) -> bool:
        elapsed = 0
        step = max(200, int(self.config.playwright_history_poll_step_ms))
        target = self._normalize_text(punch_type)
        while elapsed < timeout_ms:
            try:
                page.wait_for_timeout(step)
                history_after = self._history_snapshot(page)
            except PlaywrightError as exc:
                # Alguns fluxos fecham/recarregam a página logo após confirmar o ponto.
                # Neste caso mantemos "sem confirmação" e deixamos o chamador decidir
                # sem transformar automaticamente em falha dura.
                text = self._normalize_text(str(exc))
                if "target page" in text and "has been closed" in text:
                    return False
                raise
            before_count = int(history_before.get("today_count", 0) or 0)
            after_count = int(history_after.get("today_count", 0) or 0)
            after_row = self._normalize_text(str(history_after.get("first_row_text", "") or ""))
            # Critério forte: número de linhas de hoje aumentou e a primeira linha
            # contém o tipo esperado. Evita falso positivo por pequena variação
            # visual/textual sem novo registro real.
            if after_count > before_count and (not target or target in after_row):
                return True
            # Fallback: alguns ambientes podem não expor data de hoje no primeiro
            # campo da linha, mantendo contagem 0. Nesse caso, só aceita mudança
            # da primeira linha quando ela contém o tipo esperado.
            before_row = self._normalize_text(str(history_before.get("first_row_text", "") or ""))
            if before_count == 0 and after_count == 0 and after_row and after_row != before_row and target in after_row:
                return True
            elapsed += step
        return False

    @staticmethod
    def _stable_hash(value: str) -> str:
        # Hash curto para logs técnicos sem expor texto completo da linha.
        text = (value or "").strip()
        if not text:
            return ""
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return digest[:10]

    def _count_today_history_records(self, page) -> int:
        snapshot = self._history_snapshot(page)
        return int(snapshot.get("today_count", 0) or 0)

    def _count_today_history_records_by_type(self, page, punch_type: str) -> int:
        today_label = datetime.now().strftime("%d/%m/%Y")
        target = self._normalize_text(punch_type)
        if not target:
            return 0
        count = 0
        for ctx in self._iter_contexts(page):
            try:
                rows = ctx.locator("table tbody tr").all()
            except Exception:
                continue
            for row in rows:
                try:
                    cells = row.locator("td").all()
                    if not cells:
                        continue
                    first_text = (cells[0].inner_text() or "").strip()
                    if today_label not in first_text:
                        continue
                    row_text = self._normalize_text(row.inner_text() or "")
                    if target in row_text:
                        count += 1
                except Exception:
                    continue
        return count

    def _has_same_punch_type_today(self, page, punch_type: str) -> bool:
        today_label = datetime.now().strftime("%d/%m/%Y")
        target = self._normalize_text(punch_type)
        if not target:
            return False
        for ctx in self._iter_contexts(page):
            try:
                rows = ctx.locator("table tbody tr").all()
            except Exception:
                continue
            for row in rows:
                try:
                    cells = row.locator("td").all()
                    if not cells:
                        continue
                    first_text = (cells[0].inner_text() or "").strip()
                    if today_label not in first_text:
                        continue
                    row_text = self._normalize_text(row.inner_text() or "")
                    if target in row_text:
                        return True
                except Exception:
                    continue
        return False

    def _handle_reason_modal(
        self,
        page,
        punch_type: str,
        custom_reason: str | None = None,
        on_step: RobotStepCallback = None,
    ) -> dict[str, bool]:
        reason_text = (custom_reason or "").strip() or self._reason_text_for_punch(punch_type)
        modal_contexts = self._visible_reason_modal_contexts(page)
        status = {"modal_visible": bool(modal_contexts), "filled": False, "confirmed": False}
        if not modal_contexts:
            return status
        fill_to = max(500, int(self.config.playwright_reason_modal_fill_timeout_ms))
        confirm_to = max(500, int(self.config.playwright_reason_modal_confirm_timeout_ms))
        after_to = max(0, int(self.config.playwright_reason_modal_after_click_ms))
        for modal in modal_contexts:
            try:
                filled = self._fill_first_in_context(
                    modal,
                    self.config.reason_modal_fields,
                    value=reason_text,
                    timeout_ms=fill_to,
                )
                status["filled"] = status["filled"] or bool(filled)
            except Exception:
                pass
            if self._click_first_in_context(
                modal,
                self.config.reason_modal_confirm_buttons,
                timeout_ms=confirm_to,
            ):
                status["confirmed"] = True
                break
        if after_to:
            page.wait_for_timeout(after_to)
        if on_step and status["modal_visible"] and not status["confirmed"]:
            self._step(on_step, "Modal visível, mas sem botão de confirmação clicado.")
        return status

    def _is_reason_modal_visible(self, page) -> bool:
        return bool(self._visible_reason_modal_contexts(page))

    def _visible_reason_modal_contexts(self, page) -> list:
        contexts: list = []
        # Prefer explicit dialog containers to avoid clicking unrelated submit buttons.
        dialog_like = [".modal-dialog", "[role='dialog']", ".modal"]
        for selector in dialog_like:
            for ctx in self._iter_contexts(page):
                try:
                    loc = ctx.locator(selector).all()
                    for item in loc:
                        try:
                            if item.is_visible():
                                contexts.append(item)
                        except Exception:
                            continue
                except Exception:
                    continue
        if contexts:
            return contexts

        # Fallback to configured indicators when dialog containers are not available.
        for selector in self.config.reason_modal_indicators:
            for ctx in self._iter_contexts(page):
                try:
                    loc = ctx.locator(selector).first
                    if loc.count() and loc.is_visible():
                        contexts.append(loc)
                except Exception:
                    continue
        return contexts

    def _fill_first_in_context(self, context, selectors: list[str], value: str, timeout_ms: int) -> bool:
        for selector in self._unique_selectors(selectors):
            try:
                field = context.locator(selector).first
                if field.count() == 0:
                    continue
                field.scroll_into_view_if_needed(timeout=timeout_ms)
                try:
                    field.fill(value, timeout=timeout_ms)
                except Exception:
                    field.click(timeout=timeout_ms)
                    field.evaluate(
                        """(el, v) => {
                            el.value = v;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""",
                        value,
                    )
                return True
            except Exception:
                continue
        return False

    def _click_first_in_context(self, context, selectors: list[str], timeout_ms: int) -> bool:
        for selector in self._unique_selectors(selectors):
            try:
                button = context.locator(selector).first
                if button.count() == 0:
                    continue
                button.scroll_into_view_if_needed(timeout=timeout_ms)
                button.click(timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    def _has_visible_error_feedback(self, page) -> bool:
        for selector in self.config.visible_error_feedback_selectors:
            for ctx in self._iter_contexts(page):
                try:
                    locator = ctx.locator(selector).first
                    if locator.count() and locator.is_visible():
                        return True
                except Exception:
                    continue
        return False

    def _reason_text_for_punch(self, punch_type: str) -> str:
        normalized = (punch_type or "").strip().lower()
        extra = (self.config.reason_by_punch_type or {}).get(normalized)
        if extra:
            return extra
        by_type = {
            "entrada": self.config.reason_entrada,
            "pausa": self.config.reason_pausa,
            "retorno": self.config.reason_retorno,
            "saida": self.config.reason_saida,
        }
        return by_type.get(normalized, normalized or "registro")

    def _selectors_for_punch(self, punch_type: str) -> list[str]:
        known_portal_selectors = [
            "div[data-testid='clock-children'] button[type='button']",
            "div[data-testid='clock-children'] button.ant-btn-primary",
        ]
        base = self._unique_selectors(
            [*known_portal_selectors, self.config.punch_button_selector, *self.config.punch_selectors_base]
        )
        pt = (punch_type or "").lower()
        extra = self.config.punch_selectors_by_type.get(pt, [])
        # Prioriza seletores específicos do tipo (pausa/retorno/etc.) para evitar
        # cliques em links/botões genéricos de "Bater ponto" que apenas navegam.
        merged = [*extra, *base]
        if pt and pt != "entrada":
            # Para tipos diferentes de entrada, evita fallback em links genéricos
            # que só navegam para a tela (sem acionar registro real).
            merged = [s for s in merged if not s.strip().lower().startswith("a:has-text(")]
        return self._unique_selectors(merged)

    def _try_open_punch_area(self, page) -> None:
        menu_to = max(500, int(self.config.playwright_menu_click_timeout_ms))
        after_to = max(0, int(self.config.playwright_menu_after_click_ms))
        try:
            self._click_first(page, self.config.navigation_menu_selectors, timeout_ms=menu_to)
            if after_to:
                page.wait_for_timeout(after_to)
        except Exception:
            return

    @staticmethod
    def _unique_selectors(selectors: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for selector in selectors:
            current = (selector or "").strip()
            if not current or current in seen:
                continue
            seen.add(current)
            cleaned.append(current)
        return cleaned

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join((value or "").strip().lower().split())
