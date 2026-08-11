import asyncio
from pathlib import Path
from typing import Optional, Union

from rosseta_stone_script_a.domain.entities.credentials import Credentials
from rosseta_stone_script_a.domain.values.rosetta_product import RosettaProduct
from rosseta_stone_script_a.infrastructure.adapters.web import PlaywrightBrowserProvider
from rosseta_stone_script_a.infrastructure.core import get_base_dir, get_settings
from rosseta_stone_script_a.shared.mixins import LoggingMixin

from .dependency_factory import DependencyFactory


class RosettaCLI(LoggingMixin):
    """CLI interface with centralized logging."""

    async def enter_rosetta(
        self,
        *,
        rosseta_login_url: str,
        user_credentials: Credentials,
        units_to_complete: list[int] = None,
        lessons_to_complete: list[int] = None,
        path_types_to_complete: list[str] = None,
        target_score_percent: int = 100,
        max_start_time_offset_ms: int = 300000,
        inter_path_delay_ms: int = 500,
        inter_path_delay_min_ms: int = 1500,
        inter_path_delay_max_ms: int = 5000,
        force_recomplete: bool = False,
        human_mode: bool = False,
        batch_min_paths: int = 6,
        batch_max_paths: int = 14,
        max_paths_per_day: int = 18,
        state_dir: Path | None = None,
    ):
        """
        Run a hierarchical learning session following Course → Lesson → Activity flow.
        This follows the proper Rosetta Stone hierarchy.
        """
        browser_settings = get_settings().browser_settings

        provider = PlaywrightBrowserProvider(
            headless=browser_settings.headless,
            slow_mo=browser_settings.slow_mo,
            user_agent=browser_settings.user_agent,
            locale=browser_settings.locale,
            viewport={
                "width": browser_settings.viewport_width,
                "height": browser_settings.viewport_height,
            },
        )

        await provider.start()
        self.logger.info("BrowserProvider started")

        try:
            web = provider.new_web_session()
            async with web.session() as web_session:
                # Create dependency factory
                factory = DependencyFactory(
                    web_session=web_session,
                    rosseta_login_url=rosseta_login_url,
                    units_to_complete=units_to_complete,
                    lessons_to_complete=lessons_to_complete,
                    path_types_to_complete=path_types_to_complete,
                    target_score_percent=target_score_percent,
                    max_start_time_offset_ms=max_start_time_offset_ms,
                    inter_path_delay_ms=inter_path_delay_ms,
                    inter_path_delay_min_ms=inter_path_delay_min_ms,
                    inter_path_delay_max_ms=inter_path_delay_max_ms,
                    force_recomplete=force_recomplete,
                    human_mode=human_mode,
                    batch_min_paths=batch_min_paths,
                    batch_max_paths=batch_max_paths,
                    max_paths_per_day=max_paths_per_day,
                    state_dir=state_dir,
                )

                # Login, detect the product, and navigate into it
                open_fundations = factory.create_open_fundations()
                captured_data = await open_fundations.execute(
                    credentials=user_credentials,
                )

                # Route by detected product
                product = captured_data.get("product")
                if product == RosettaProduct.FLUENCY_BUILDER.value:
                    self.logger.info("Account uses Fluency Builder; running write phase")
                    complete_fluency = factory.create_complete_fluency_orchestrator()
                    await complete_fluency.execute(captured_data)
                else:
                    complete_foundations = (
                        factory.create_complete_foundations_orchestrator()
                    )
                    await complete_foundations.execute(captured_data)

                self.logger.info("Learning session finished successfully")

        finally:
            await provider.stop()
            self.logger.info("BrowserProvider stopped")

    def main_cli(self):
        """
        Entry point invocado desde main.py o directamente si quieres.
        Puede parsear argumentos, aquí lo dejamos simple y usa settings.

        Por defecto ejecuta una sesión completa de aprendizaje.
        """
        rosseta_settings = get_settings().rosseta_settings
        user_credentials = Credentials(
            email=rosseta_settings.rosetta_email,
            password=rosseta_settings.rosetta_password,
        )

        state_dir = get_base_dir() / rosseta_settings.rosetta_state_dir

        asyncio.run(
            self.enter_rosetta(
                rosseta_login_url=rosseta_settings.rosetta_login_url,
                user_credentials=user_credentials,
                units_to_complete=rosseta_settings.rosetta_units_to_complete,
                lessons_to_complete=rosseta_settings.rosetta_lessons_to_complete,
                path_types_to_complete=rosseta_settings.rosetta_path_types_to_complete,
                target_score_percent=rosseta_settings.rosetta_target_score_percent,
                max_start_time_offset_ms=rosseta_settings.rosetta_max_start_time_offset_ms,
                inter_path_delay_ms=rosseta_settings.rosetta_inter_path_delay_ms,
                inter_path_delay_min_ms=rosseta_settings.rosetta_inter_path_delay_min_ms,
                inter_path_delay_max_ms=rosseta_settings.rosetta_inter_path_delay_max_ms,
                force_recomplete=rosseta_settings.rosetta_force_recomplete,
                human_mode=rosseta_settings.rosetta_human_mode,
                batch_min_paths=rosseta_settings.rosetta_batch_min_paths,
                batch_max_paths=rosseta_settings.rosetta_batch_max_paths,
                max_paths_per_day=rosseta_settings.rosetta_max_paths_per_day,
                state_dir=state_dir,
            )
        )


def main_cli():
    """Legacy function - use CLI().main_cli() instead."""
    cli = RosettaCLI()
    cli.main_cli()
