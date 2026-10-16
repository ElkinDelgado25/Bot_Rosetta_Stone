import json
from typing import Any, Dict, List, Optional

from Resolucion_script_rosseta.dominio.entities.fluency_activity import FluencyActivity
from Resolucion_script_rosseta.dominio.entities.fluency_sequence import FluencySequence
from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyAnswer, FluencyStep


class FluencySequenceParser:
    """Parse a ``getSequence`` GraphQL response into a FluencySequence.

    The ``activities`` field is a JSON scalar: it may arrive already decoded as a
    list, or as a JSON-encoded string. Each step carries a ``correct`` list of
    option ids and, for conversations, a ``postProcess.successResponses`` list
    with the accepted subset — the closing steps of a dialogue accept only one
    option and speaking any other aborts the tree. Vocabulary cards have no
    ``correct`` field: their word ids are taken from ``content[].carousel``
    items with ``type: "word"``.
    """

    @staticmethod
    def parse(data: Dict[str, Any], course_id: str) -> FluencySequence:
        payload = data.get("data", data) or {}
        seq = payload.get("sequence", payload) or {}

        activities = FluencySequenceParser._activities(
            FluencySequenceParser._decode(seq.get("activities"))
        )

        return FluencySequence(
            sequence_id=seq.get("sequenceId") or seq.get("id"),
            course_id=course_id,
            title=FluencySequenceParser._text(seq.get("title")),
            version=seq.get("version"),
            activities=activities,
        )

    @staticmethod
    def _decode(activities: Any) -> List[Dict[str, Any]]:
        if activities is None:
            return []
        if isinstance(activities, str):
            try:
                activities = json.loads(activities)
            except (ValueError, TypeError):
                return []
        return activities if isinstance(activities, list) else []

    @staticmethod
    def _activities(raw: List[Dict[str, Any]]) -> List[FluencyActivity]:
        result: List[FluencyActivity] = []
        for a in raw:
            if not isinstance(a, dict):
                continue
            result.append(
                FluencyActivity(
                    activity_id=a.get("activityId"),
                    activity_type=a.get("activityType"),
                    interaction=a.get("interaction"),
                    ordering=a.get("ordering"),
                    steps=FluencySequenceParser._steps(a.get("steps")),
                )
            )
        return result

    @staticmethod
    def _steps(raw: Any) -> List[FluencyStep]:
        steps: List[FluencyStep] = []
        for s in raw or []:
            if not isinstance(s, dict):
                continue
            ids = FluencySequenceParser._correct(s.get("correct"))
            if not ids and (s.get("type") or "").lower() == "card":
                ids = FluencySequenceParser._carousel_word_ids(s)
            steps.append(
                FluencyStep(
                    step_id=s.get("activityStepId"),
                    type=s.get("type"),
                    correct_answer_ids=ids,
                    success_answer_ids=FluencySequenceParser._success(s.get("postProcess")),
                    answers=FluencySequenceParser._answers(s, ids),
                )
            )
        return steps

    @staticmethod
    def _success(post_process: Any) -> List[str]:
        """Los ids aceptados del paso (``postProcess.successResponses``).

        Sin este dato, una actividad restringida se contesta a ciegas: en los
        pasos de cierre del diálogo solo una opción continúa el árbol, y hablar
        cualquier otra lo corta y el reproductor abandona la conversación.
        """
        if not isinstance(post_process, dict):
            return []
        seen: List[str] = []
        for respuesta in post_process.get("successResponses") or []:
            if not isinstance(respuesta, dict):
                continue
            rid = respuesta.get("responseId")
            if isinstance(rid, str) and rid and rid not in seen:
                seen.append(rid)
        return seen

    @staticmethod
    def _answers(step: Dict[str, Any], ids: List[str]) -> List[FluencyAnswer]:
        """Las opciones renderizadas: id, texto visible y sha del audio.

        El texto y el audio viven en ``contentChunks`` de cada opción; el sha
        es el nombre del recurso en ``resources.rosettastone.com`` y aparece al
        final de la URL que captura el reproductor al pulsar el altavoz.
        """
        id_set = set(ids)
        answers: List[FluencyAnswer] = []
        for grupo in step.get("content") or []:
            if not isinstance(grupo, (list, tuple)):
                continue
            for item in grupo:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id")
                if item_id not in id_set:
                    continue
                answers.append(
                    FluencyAnswer(
                        id=item_id,
                        text=FluencySequenceParser._option_text(item),
                        audio_sha=FluencySequenceParser._option_sha(item),
                    )
                )
        return answers

    @staticmethod
    def _option_text(item: Dict[str, Any]) -> str:
        chunks = item.get("contentChunks")
        if isinstance(chunks, list) and chunks:
            texts = [
                (chunk.get("text") or "").strip()
                for chunk in chunks
                if isinstance(chunk, dict) and (chunk.get("text") or "").strip()
            ]
            if texts:
                return " ".join(texts)
        return (item.get("text") or "").strip()

    @staticmethod
    def _option_sha(item: Dict[str, Any]) -> Optional[str]:
        for chunk in item.get("contentChunks") or []:
            if not isinstance(chunk, dict):
                continue
            sha = FluencySequenceParser._media_sha(chunk.get("audios"))
            if sha:
                return sha
        return FluencySequenceParser._media_sha(item.get("audios"))

    @staticmethod
    def _media_sha(audios: Any) -> Optional[str]:
        for audio in audios or []:
            if not isinstance(audio, dict):
                continue
            uri = audio.get("media_uri")
            if not isinstance(uri, str) or not uri:
                continue
            return uri.rsplit(":", 1)[-1] or None
        return None

    @staticmethod
    def _correct(value: Any) -> List[str]:
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        if isinstance(value, str):
            return [value]
        return []

    @staticmethod
    def _carousel_word_ids(step: Dict[str, Any]) -> List[str]:
        """Vocabulary/KeyVocabulary: un solo step ``card``, N palabras en carousel."""
        seen: List[str] = []
        for item in FluencySequenceParser._walk(step.get("content")):
            if not isinstance(item, dict) or item.get("type") != "word":
                continue
            word_id = item.get("id") or item.get("wordId")
            if isinstance(word_id, str) and word_id and word_id not in seen:
                seen.append(word_id)
        return seen

    @staticmethod
    def _walk(value: Any):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from FluencySequenceParser._walk(nested)
            return
        if isinstance(value, list):
            for nested in value:
                yield from FluencySequenceParser._walk(nested)

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("text")
        return None

