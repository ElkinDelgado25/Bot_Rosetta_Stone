from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from Resolucion_script_rosseta.dominio.values.rosetta_product import RosettaProduct
from Resolucion_script_rosseta.compartido.mixins import LoggingMixin


class DashboardPagePort(ABC, LoggingMixin):
    """
    Port for Dashboard navigation after login.
    Responsible for navigating to different sections from the main dashboard.
    """

    @abstractmethod
    async def detect_product(self) -> RosettaProduct:
        """Detect which product this account offers, without navigating or failing."""
        ...

    @abstractmethod
    async def open_foundations(self) -> None:
        """Navigate to Foundations from the dashboard (e.g., click on 'Foundations')."""
        ...

    @abstractmethod
    async def open_fluency_builder(self) -> None:
        """Navigate into Fluency Builder from the dashboard (click the product tile)."""
        ...

    @abstractmethod
    async def open_exam(self) -> None:
        """Navigate into the Exam / Assessment from the dashboard."""
        ...

    @abstractmethod
    async def get_user_name(self) -> Optional[str]:
        """Get the user's name displayed on the dashboard."""
        ...

