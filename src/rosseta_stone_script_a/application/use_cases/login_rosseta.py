from rosseta_stone_script_a.application.ports.web import IWebSession
from rosseta_stone_script_a.application.ports.web.page import AuthPort
from rosseta_stone_script_a.domain.entities.credentials import Credentials

from ..ports.use_case import UseCasePort


class LoginRossetaUseCase(UseCasePort):
    def __init__(self, web_session: IWebSession, login_page: AuthPort):
        self.web_session = web_session
        self.login_page = login_page

    async def execute(self, credentials: Credentials) -> None:
        await self.login_page.login(credentials)

        await self.web_session.debug_dumpper.dump_screenshot("after_login")

        self.logger.info("Login successful")
