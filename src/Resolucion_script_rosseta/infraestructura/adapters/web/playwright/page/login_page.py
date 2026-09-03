from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from Resolucion_script_rosseta.aplicacion.ports.web import AuthPort, IWebSession, Selector
from Resolucion_script_rosseta.dominio.entities.credentials import Credentials
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.patterns import (
    AuthPatterns,
)
from Resolucion_script_rosseta.compartido.utils.compile_case_insensitive import (
    compile_case_insensitive,
)

cci = compile_case_insensitive


@dataclass(frozen=True)
class LoginPagePatterns:
    """Local patterns specific to the login page."""

    EMAIL_LABEL = cci(r"correo\s*electr[óo]nico|email\s*address")
    PASSWORD_LABEL = cci(r"contrase[ñn]a|password")


class LoginPage(AuthPort):
    """
    Page Object del Login que usa selectores semánticos (regex permitido en patrones).
    Todas las acciones pasan por self.web_session.interactor.
    """

    def __init__(
        self,
        web_session: IWebSession,
        rosetta_login_url: str,
    ) -> None:
        super().__init__()
        self.web_session = web_session
        self.rosetta_login_url = rosetta_login_url
        # Whether the institutional (uleam) step appeared and was clicked. The
        # verification flow reports it: a login that silently skipped this step
        # is the usual reason a capture ends up incomplete.
        self.institution_selected: bool = False

        # --- Selectors ---

        self.EMAIL_INPUT = Selector.role_textbox(
            name_pattern=LoginPagePatterns.EMAIL_LABEL
        )
        self.PASSWORD_INPUT = Selector.role_textbox(
            name_pattern=LoginPagePatterns.PASSWORD_LABEL
        )
        self.SIGN_IN_BTN = Selector.role_button(name_pattern=AuthPatterns.SIGN_IN)

    async def login(self, creds: "Credentials") -> None:
        """Implementation of AuthPort interface using Credentials."""
        self.logger.info("Starting login process")

        await self.web_session.navigator.go_to(
            self.rosetta_login_url, wait_for_load=True
        )
        self.logger.info("Navigated to login URL")

        await self.web_session.debug_dumpper.dump_screenshot("before_login")

        # Fill email using interactor with Selector
        self.logger.info(f"Filling email field for user: {creds.email}")
        await self.web_session.interactor.fill(self.EMAIL_INPUT, str(creds.email))

        # Fill password using interactor with Selector
        self.logger.info("Filling password field")
        await self.web_session.interactor.fill(self.PASSWORD_INPUT, creds.password)

        # Click submit button using interactor with Selector
        self.logger.info("Clicking sign-in button")
        await self.web_session.interactor.click(self.SIGN_IN_BTN)

        await self.web_session.navigator.wait_for_load()

        # Handle institutional account selection
        self.institution_selected = bool(
            await self._handle_institutional_account_selection(creds)
        )

        self.logger.info("Login process completed successfully")

    async def logout(self) -> None:
        """Cerrar la sesión en el servidor de Rosetta, no solo el navegador.

        Rosetta autentica con Keycloak: la sesión vive del lado del servidor y
        sigue viva aunque el navegador muera. Por eso la siguiente vez que el
        usuario entra le avisan que su cuenta está abierta en otro navegador.

        La UI real lo resuelve con una navegación simple a ``/logout``: así
        quedó grabado en el HAR del logout manual (login -> learn -> login ->
        /logout), sin POST ni cabeceras propias, solo las cookies de sesión.
        """
        logout_url = urljoin(self.rosetta_login_url, "/logout")
        self.logger.info(f"Cerrando sesión en {logout_url}")
        await self.web_session.navigator.go_to(logout_url, wait_for_load=True)
        self.logger.info("Sesión cerrada en el servidor")

    async def _handle_institutional_account_selection(
        self, creds: "Credentials"
    ) -> bool:
        """Handle institutional account selection if multiple accounts are associated."""
        try:
            # Wait a moment for the page to load after initial login attempt
            await self.web_session.navigator.wait_for_load(timeout=5000)

            institutional_selectors = [
                Selector.by_text("uleam"),
                Selector.by_css("[data-testid*='uleam']"),
                Selector.by_css("button:has-text('uleam')"),
                Selector.by_css("div:has-text('uleam')"),
                Selector.by_css("span:has-text('uleam')"),
            ]

            account_found = False
            for selector in institutional_selectors:
                try:
                    if await self.web_session.interactor.exists(selector, timeout=3000):
                        self.logger.info(
                            "Found institutional account selector (uleam)..."
                        )
                        await self.web_session.interactor.click_first(selector)
                        account_found = True
                        break
                except Exception:
                    continue

            if not account_found:
                try:
                    uleam_selector = Selector.by_text("uleam")
                    if await self.web_session.interactor.exists(
                        uleam_selector, timeout=3000
                    ):
                        self.logger.info(
                            "Detected institutional account page, looking for clickable elements..."
                        )
                        await self.web_session.interactor.click_first(uleam_selector)
                        account_found = True
                except Exception:
                    pass

            if account_found:
                self.logger.info(
                    "Selected institutional account, re-entering password..."
                )
                await self.web_session.navigator.wait_for_load(timeout=8000)

                # Re-enter password
                await self.web_session.interactor.fill(
                    self.PASSWORD_INPUT, creds.password
                )
                await self.web_session.interactor.click(self.SIGN_IN_BTN)

                await self.web_session.navigator.wait_for_load(timeout=10000)

                try:
                    await self.web_session.debug_dumpper.dump_screenshot(
                        "institutional_login_complete"
                    )
                except Exception:
                    pass

                return True

        except Exception as e:
            self.logger.warning(f"Error during institutional account handling: {e}")

        return False

