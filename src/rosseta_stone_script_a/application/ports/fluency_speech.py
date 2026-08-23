from abc import ABC, abstractmethod


class FluencySpeechPort(ABC):
    """Browser workflow required by speech-recognition Fluency activities."""

    @abstractmethod
    async def complete_activity(
        self,
        *,
        course_title: str,
        lesson_title: str,
        activity_id: str,
        expected_steps: int,
    ) -> bool:
        """Complete one conversation activity through the real lesson player."""
        ...
