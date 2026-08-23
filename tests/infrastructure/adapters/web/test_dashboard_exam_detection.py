import asyncio
from types import SimpleNamespace

from rosseta_stone_script_a.domain.values.rosetta_product import RosettaProduct
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.dashboard_page import (
    DashboardPage,
)


class _Interactor:
    async def exists(self, selector, timeout=None):
        return False


def _dashboard(url: str) -> DashboardPage:
    session = SimpleNamespace(
        interactor=_Interactor(),
        _page=SimpleNamespace(url=url),
    )
    return DashboardPage(session)


def test_unknown_dashboard_does_not_fall_back_to_exam():
    product = asyncio.run(_dashboard("https://example.test/launchpad").detect_product())

    assert product == RosettaProduct.UNKNOWN


def test_assessment_url_is_detected_as_exam():
    product = asyncio.run(
        _dashboard("https://learn.rosettastone.com/assessments/123").detect_product()
    )

    assert product == RosettaProduct.EXAM
