from abc import ABC, abstractmethod


class FluencySpeechPort(ABC):
    """Browser workflow required by the tree conversations of Fluency.

    Las dos ``DialogueExpression*``: la que se contesta hablando y la que se
    contesta pulsando. La API no acredita ninguna de las dos por mucho que se le
    mande el mensaje correcto, así que las resuelve el reproductor real.
    """

    @abstractmethod
    async def complete_activity(
        self,
        *,
        course_title: str,
        lesson_title: str,
        activity_id: str,
        expected_steps: int,
    ) -> bool:
        """Complete one conversation activity through the real lesson player.

        ``expected_steps`` es una cota superior: en un árbol cuenta todos los
        nodos, no los del camino que se recorre.
        """
        ...
