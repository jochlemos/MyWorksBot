from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.models import AppConfig


class MyworkApiClient:
    def __init__(self, config: AppConfig, email: str, password: str) -> None:
        self.config = config
        self.email = email.strip()
        self.password = password

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

    def register_punch(self, punch_type: str, custom_reason: str | None = None) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Robô não configurado (credenciais/URLs/seletores)."
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.config.headless_browser)
                page = browser.new_page()
                self._perform_login(page)
                page.wait_for_timeout(2500)
                self._ensure_on_punch_page(page)
                reason_text = (custom_reason or "").strip() or self._reason_text_for_punch(punch_type)
                if self.config.prevent_same_description:
                    latest_comment = self._get_latest_history_comment(page)
                    if latest_comment and self._normalize_text(latest_comment) == self._normalize_text(reason_text):
                        browser.close()
                        return (
                            False,
                            "Bloqueado: a última descrição no histórico é igual à nova descrição.",
                        )
                marker_before = self._get_history_marker(page)
                try:
                    self._click_first(
                        page,
                        self._selectors_for_punch(punch_type),
                        timeout_ms=15000,
                    )
                except RuntimeError:
                    self._try_open_punch_area(page)
                    self._click_first(
                        page,
                        self._selectors_for_punch(punch_type),
                        timeout_ms=15000,
                    )
                self._handle_reason_modal(page, punch_type, custom_reason=reason_text)
                if not self._wait_for_history_change(page, marker_before, timeout_ms=20000):
                    # O Mywork pode demorar para refletir na tabela; se não houver erro visível,
                    # consideramos a ação como aceita para evitar falso negativo.
                    if self._has_visible_error_feedback(page):
                        raise RuntimeError(
                            "Clique executado, mas a tela exibiu erro de validação/confirmação."
                        )
                browser.close()
                return True, f"Ponto {punch_type} executado pelo robô."
        except PlaywrightTimeoutError as exc:
            return False, f"Timeout no robô: {exc}"
        except PlaywrightError as exc:
            return False, f"Erro no Playwright: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Erro inesperado: {exc}"

    def test_connection(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Configure credenciais e seletores primeiro."
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                self._perform_login(page)
                self._ensure_on_punch_page(page)
                page.wait_for_timeout(3000)
                browser.close()
            return True, "Login automatizado executado."
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _perform_login(self, page) -> None:
        page.goto(self.config.login_url, wait_until="domcontentloaded", timeout=30000)
        self._fill_first(
            page,
            [
                self.config.email_selector,
                "input[type='email']",
                "input[name='email']",
                "input[name='username']",
                "input[name='login']",
                "input[id*='email']",
                "input[id*='user']",
                "input[type='text']",
            ],
            value=self.email,
            timeout_ms=12000,
            field_name="usuário/e-mail",
        )
        self._fill_first(
            page,
            [
                self.config.password_selector,
                "input[type='password']",
                "input[name='password']",
                "input[id*='pass']",
            ],
            value=self.password,
            timeout_ms=12000,
            field_name="senha",
        )
        self._click_first(
            page,
            [
                self.config.submit_selector,
                "button[type='submit']",
                "button:has-text('Entrar')",
                "button:has-text('Login')",
                "input[type='submit']",
            ],
            timeout_ms=12000,
        )

    def _effective_punch_url(self) -> str:
        configured = (self.config.punch_page_url or "").strip()
        if not configured:
            return "https://app.mywork.com.br/ponto"
        lowered = configured.rstrip("/").lower()
        if lowered in {"https://app.mywork.com.br", "https://app.mywork.com.br/"}:
            return "https://app.mywork.com.br/ponto"
        return configured

    def _ensure_on_punch_page(self, page) -> None:
        target = self._effective_punch_url()
        page.goto(target, wait_until="domcontentloaded", timeout=30000)
        if self._is_punch_context(page):
            return

        # Fallback para navegação por menu em layouts SPA.
        self._try_open_punch_area(page)
        if self._is_punch_context(page):
            return

        # Segunda tentativa com espera de rede ociosa.
        page.goto(target, wait_until="networkidle", timeout=30000)
        if self._is_punch_context(page):
            return
        raise RuntimeError(f"Não foi possível abrir a página de ponto. URL atual: {page.url}")

    def _is_punch_context(self, page) -> bool:
        current_url = (page.url or "").lower()
        if "/ponto" in current_url:
            return True
        indicators = [
            "text='Bater ponto'",
            "text='Bater seu ponto'",
            "text='Histórico de pontos'",
            "h1:has-text('Ponto')",
            "h2:has-text('Ponto')",
        ]
        for selector in indicators:
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
        errors: list[str] = []
        for selector in self._unique_selectors(selectors):
            for ctx in self._iter_contexts(page):
                try:
                    button = ctx.locator(selector).first
                    if button.count() == 0:
                        continue
                    button.scroll_into_view_if_needed(timeout=timeout_ms)
                    button.click(timeout=timeout_ms)
                    return
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{selector}: {exc}")
        visible_buttons = self._collect_button_diagnostics(page)
        raise RuntimeError(
            "Nenhum seletor de botão funcionou. "
            + " | ".join(errors[:3])
            + f" | URL atual: {page.url}"
            + f" | Botões encontrados: {visible_buttons}"
        )

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

    def _get_history_marker(self, page) -> str:
        selectors = [
            "table tbody tr:first-child td:first-child",
            ".table tbody tr:first-child td:first-child",
            "tbody tr:first-child td:first-child",
        ]
        for selector in selectors:
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

    def _get_latest_history_comment(self, page) -> str:
        selectors = [
            "table tbody tr:first-child td:nth-child(6)",
            ".table tbody tr:first-child td:nth-child(6)",
            "tbody tr:first-child td:nth-child(6)",
        ]
        for selector in selectors:
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

    def _wait_for_history_change(self, page, marker_before: str, timeout_ms: int) -> bool:
        elapsed = 0
        step = 1000
        while elapsed < timeout_ms:
            page.wait_for_timeout(step)
            marker_after = self._get_history_marker(page)
            if marker_after and marker_after != marker_before:
                return True
            elapsed += step
        return False

    def _handle_reason_modal(self, page, punch_type: str, custom_reason: str | None = None) -> None:
        reason_text = (custom_reason or "").strip() or self._reason_text_for_punch(punch_type)
        if not self._is_reason_modal_visible(page):
            return
        reason_fields = [
            "textarea",
            "input[placeholder*='Coment' i]",
            "input[placeholder*='coment' i]",
            "input[placeholder*='ponto' i]",
            "textarea[name*='motivo' i]",
            "textarea[id*='motivo' i]",
            "textarea[name*='comment' i]",
            "textarea[id*='comment' i]",
            "input[name*='motivo' i]",
            "input[id*='motivo' i]",
            "input[name*='comment' i]",
            "input[id*='comment' i]",
        ]
        try:
            self._fill_first(page, reason_fields, reason_text, timeout_ms=3000, field_name="motivo")
        except Exception:
            pass

        confirm_buttons = [
            "button:has-text('Salvar')",
            "button:has-text('Confirmar')",
            "button:has-text('Registrar')",
            "button:has-text('OK')",
            "button:has-text('Enviar')",
            "button[type='submit']",
            "[role='button']:has-text('Salvar')",
            "[role='button']:has-text('Confirmar')",
            "input[type='submit']",
        ]
        self._click_first(page, confirm_buttons, timeout_ms=8000)
        page.wait_for_timeout(1200)

    def _is_reason_modal_visible(self, page) -> bool:
        modal_indicators = [
            "text='Bater seu ponto'",
            ".modal:has-text('Bater seu ponto')",
            ".modal-dialog",
            "[role='dialog']",
        ]
        for selector in modal_indicators:
            for ctx in self._iter_contexts(page):
                try:
                    locator = ctx.locator(selector).first
                    if locator.count() and locator.is_visible():
                        return True
                except Exception:
                    continue
        return False

    def _has_visible_error_feedback(self, page) -> bool:
        error_selectors = [
            ".alert-danger",
            ".error",
            ".toast-error",
            "text='erro'",
            "text='falha'",
            "text='inválido'",
            "text='obrigatório'",
        ]
        for selector in error_selectors:
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
        by_type = {
            "Entrada": self.config.reason_entrada,
            "Pausa": self.config.reason_pausa,
            "Retorno": self.config.reason_retorno,
            "Saída": self.config.reason_saida,
        }
        return by_type.get(normalized, normalized or "registro")

    def _selectors_for_punch(self, punch_type: str) -> list[str]:
        base = [
            self.config.punch_button_selector,
            "button:has-text('Bater ponto')",
            "button:has-text('Registrar ponto')",
            "button:has-text('Marcar ponto')",
            "[role='button']:has-text('Bater ponto')",
            "[role='button']:has-text('Registrar ponto')",
            "a:has-text('Bater ponto')",
            "a:has-text('Registrar ponto')",
            "[aria-label*='ponto' i]",
            "[title*='ponto' i]",
        ]
        per_type = {
            "entrada": [
                "button:has-text('Entrada')",
                "button:has-text('Iniciar jornada')",
                "button:has-text('Iniciar expediente')",
                "[role='button']:has-text('Entrada')",
                "a:has-text('Entrada')",
            ],
            "pausa": [
                "button:has-text('Pausa')",
                "button:has-text('Intervalo')",
                "button:has-text('Iniciar pausa')",
                "button:has-text('Iniciar intervalo')",
                "[role='button']:has-text('Pausa')",
                "[role='button']:has-text('Intervalo')",
                "a:has-text('Pausa')",
                "a:has-text('Intervalo')",
            ],
            "retorno": [
                "button:has-text('Retorno')",
                "button:has-text('Voltar')",
                "button:has-text('Fim da pausa')",
                "button:has-text('Fim do intervalo')",
                "[role='button']:has-text('Retorno')",
                "a:has-text('Retorno')",
            ],
            "saida": [
                "button:has-text('Saida')",
                "button:has-text('Saída')",
                "button:has-text('Encerrar jornada')",
                "button:has-text('Encerrar expediente')",
                "[role='button']:has-text('Saída')",
                "[role='button']:has-text('Saida')",
                "a:has-text('Saída')",
                "a:has-text('Saida')",
            ],
        }
        return [*base, *per_type.get((punch_type or "").lower(), [])]

    def _try_open_punch_area(self, page) -> None:
        navigation_selectors = [
            "a:has-text('Ponto')",
            "a:has-text('Meu ponto')",
            "a:has-text('Jornada')",
            "button:has-text('Ponto')",
            "[role='button']:has-text('Ponto')",
            "[href*='ponto' i]",
            "[href*='time' i]",
        ]
        try:
            self._click_first(page, navigation_selectors, timeout_ms=4000)
            page.wait_for_timeout(1500)
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
