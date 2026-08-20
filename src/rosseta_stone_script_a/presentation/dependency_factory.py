from rosseta_stone_script_a.application.orchestrators.complete_exam_orchestrator import (
    CompleteExamOrchestrator,
)
from rosseta_stone_script_a.application.orchestrators.complete_fluency_orchestrator import (
    CompleteFluencyOrchestrator,
)
from rosseta_stone_script_a.application.orchestrators.complete_foundations_orchestrator import (
    CompleteFoundationsOrchestrator,
)
from rosseta_stone_script_a.application.orchestrators.fluency_orchestrator import (
    FluencyOrchestrator,
)
from rosseta_stone_script_a.application.orchestrators.open_fundations import (
    OpenFundations,
)
from rosseta_stone_script_a.application.ports.web import IWebSession
from rosseta_stone_script_a.application.services.exam_solver import ExamSolver
from rosseta_stone_script_a.application.services.fluency_session_capturer import (
    FluencySessionCapturer,
)
from rosseta_stone_script_a.application.services.rosetta_session_capturer import (
    RosettaSessionCapturer,
)
from rosseta_stone_script_a.application.use_cases.complete_exam import (
    CompleteExamUseCase,
)
from rosseta_stone_script_a.application.use_cases.complete_foundations import (
    CompleteFoundationsUseCase,
)
from rosseta_stone_script_a.application.use_cases.go_to_foundations import (
    GoToFundationsUseCase,
)
from rosseta_stone_script_a.application.use_cases.login_rosseta import (
    LoginRossetaUseCase,
)
from rosseta_stone_script_a.infrastructure.adapters.exam_api.playwright_exam_api import (
    PlaywrightExamApiAdapter,
)
from rosseta_stone_script_a.infrastructure.adapters.fluency_api.playwright_fluency_api import (
    PlaywrightFluencyApiAdapter,
)
from rosseta_stone_script_a.infrastructure.adapters.foundations_api.playwright_foundations_api import (
    PlaywrightFoundationsApiAdapter,
)
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.dashboard_page import (
    DashboardPage,
)
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.login_page import (
    LoginPage,
)


class DependencyFactory:
    """Factory for creating orchestrators with proper dependency injection."""

    def __init__(
        self,
        web_session: IWebSession,
        rosseta_login_url: str,
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
        self.web_session = web_session
        self.rosseta_login_url = rosseta_login_url
        self.units_to_complete = units_to_complete or []
        self.lessons_to_complete = lessons_to_complete or []
        self.path_types_to_complete = path_types_to_complete or []
        self.target_score_percent = target_score_percent
        self.max_start_time_offset_ms = max_start_time_offset_ms
        self.inter_path_delay_ms = inter_path_delay_ms
        self.inter_path_delay_min_ms = inter_path_delay_min_ms
        self.inter_path_delay_max_ms = inter_path_delay_max_ms
        self.force_recomplete = force_recomplete
        self.human_mode = human_mode
        self.batch_min_paths = batch_min_paths
        self.batch_max_paths = batch_max_paths
        self.max_paths_per_day = max_paths_per_day
        self.state_dir = state_dir

    def create_open_fundations(self) -> OpenFundations:
        """Create OpenFoundations orchestrator with dependencies."""
        # Create pages
        login_page = LoginPage(
            web_session=self.web_session, rosetta_login_url=self.rosseta_login_url
        )
        dashboard_page = DashboardPage(web_session=self.web_session)

        # Create services
        session_capturer = RosettaSessionCapturer()
        fluency_capturer = FluencySessionCapturer()

        # Create use cases
        login_use_case = LoginRossetaUseCase(
            web_session=self.web_session, login_page=login_page
        )
        navigate_use_case = GoToFundationsUseCase(
            web_session=self.web_session,
            dashboard_page=dashboard_page,
        )
        # Create orchestrator
        return OpenFundations(
            login_use_case=login_use_case,
            navigate_use_case=navigate_use_case,
            web_session=self.web_session,
            session_capturer=session_capturer,
            fluency_capturer=fluency_capturer,
        )

    def create_fluency_orchestrator(self) -> FluencyOrchestrator:
        """Create the read-only Fluency Builder orchestrator with its API adapter."""
        return FluencyOrchestrator(api_port=self._fluency_api_adapter())

    def create_complete_fluency_orchestrator(self) -> CompleteFluencyOrchestrator:
        """Create the Fluency write orchestrator, bounded by env-var safety knobs.

        FLUENCY_MAX_LESSONS: how many pending lessons to complete this run
            (default 1 for a controlled first run; set to 0 or "all" for no limit).
        FLUENCY_DRY_RUN: "1"/"true" to build and log messages without sending.
        """
        import os

        raw_max = os.getenv("FLUENCY_MAX_LESSONS", "1").strip().lower()
        if raw_max in ("0", "all", "none", ""):
            max_lessons = None
        else:
            try:
                max_lessons = int(raw_max)
            except ValueError:
                max_lessons = 1

        dry_run = os.getenv("FLUENCY_DRY_RUN", "").strip().lower() in ("1", "true", "yes")

        try:
            delay_ms = int(os.getenv("FLUENCY_DELAY_MS", "500"))
        except ValueError:
            delay_ms = 500

        return CompleteFluencyOrchestrator(
            api_port=self._fluency_api_adapter(),
            state_dir=self.state_dir,
            max_lessons=max_lessons,
            dry_run=dry_run,
            course_filter=os.getenv("FLUENCY_COURSE") or None,
            lesson_filter=os.getenv("FLUENCY_LESSON") or None,
            delay_ms=delay_ms,
        )

    def _fluency_api_adapter(self) -> PlaywrightFluencyApiAdapter:
        page = getattr(self.web_session, "_page", None)
        if not page:
            raise RuntimeError("Web session not initialized correctly")
        return PlaywrightFluencyApiAdapter(page.request)

    def create_complete_foundations_orchestrator(
        self,
    ) -> CompleteFoundationsOrchestrator:
        """Create CompleteFoundations orchestrator with dependencies."""
        # Access the underlying Playwright page to get the request context
        page = getattr(self.web_session, "_page", None)
        if not page:
            raise RuntimeError("Web session not initialized correctly")

        foundations_api_adapter = PlaywrightFoundationsApiAdapter(page.request)

        complete_foundations_use_case = CompleteFoundationsUseCase(
            api_port=foundations_api_adapter,
            units_to_complete=self.units_to_complete,
            lessons_to_complete=self.lessons_to_complete,
            path_types_to_complete=self.path_types_to_complete,
            target_score_percent=self.target_score_percent,
            max_start_time_offset_ms=self.max_start_time_offset_ms,
            inter_path_delay_ms=self.inter_path_delay_ms,
            inter_path_delay_min_ms=self.inter_path_delay_min_ms,
            inter_path_delay_max_ms=self.inter_path_delay_max_ms,
            force_recomplete=self.force_recomplete,
            human_mode=self.human_mode,
            batch_min_paths=self.batch_min_paths,
            batch_max_paths=self.batch_max_paths,
            max_paths_per_day=self.max_paths_per_day,
            state_dir=self.state_dir,
        )

        return CompleteFoundationsOrchestrator(
            complete_foundations_use_case=complete_foundations_use_case
        )

    def create_complete_exam_orchestrator(
        self,
        authorization_header: str | None = None,
        min_delay_seconds: float = 2.0,
        max_delay_seconds: float = 5.0,
        dry_run: bool = False,
    ) -> CompleteExamOrchestrator:
        """Create CompleteExam orchestrator with dependencies."""
        api_adapter = self._exam_api_adapter(authorization_header=authorization_header)
        solver = ExamSolver()
        complete_exam_use_case = CompleteExamUseCase(
            api_port=api_adapter,
            solver=solver,
            min_delay_seconds=min_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            state_dir=self.state_dir,
            dry_run=dry_run,
        )
        return CompleteExamOrchestrator(complete_exam_use_case=complete_exam_use_case)

    def _exam_api_adapter(
        self, authorization_header: str | None = None
    ) -> PlaywrightExamApiAdapter:
        page = getattr(self.web_session, "_page", None)
        if not page:
            raise RuntimeError("Web session not initialized correctly")
        return PlaywrightExamApiAdapter(
            request_context=page.request,
            authorization_header=authorization_header,
        )
