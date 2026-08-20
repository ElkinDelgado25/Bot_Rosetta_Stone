from typing import Any, Dict, List, Optional

from rosseta_stone_script_a.domain.entities.exam import (
    ExamActivity,
    ExamOption,
    ExamProgress,
    ExamScore,
    ExamStep,
    ExamStepResult,
)


class ExamStepParser:
    """Parser to transform GraphQL assessmentStep response JSON into domain entities."""

    @staticmethod
    def parse_step_response(data: Dict[str, Any]) -> ExamStepResult:
        """Parse raw assessmentStep GraphQL dictionary into ExamStepResult."""
        assess = data.get("assessmentStep") or {}
        assessment_name = assess.get("assessmentName", "")
        form_number = assess.get("formNumber", 0)

        # Parse activity if present
        raw_activity = assess.get("activity")
        activity = ExamStepParser._parse_activity(raw_activity) if raw_activity else None

        # Parse progress if present
        raw_progress = assess.get("progress")
        progress = ExamStepParser._parse_progress(raw_progress) if raw_progress else None

        # Parse score if present
        raw_score = assess.get("score")
        score = ExamStepParser._parse_score(raw_score) if raw_score else None

        is_complete = assessment_name == "testComplete" or (activity is None and score is not None)

        return ExamStepResult(
            assessment_name=assessment_name,
            form_number=form_number,
            activity=activity,
            progress=progress,
            score=score,
            is_complete=is_complete,
        )

    @staticmethod
    def _parse_activity(raw: Dict[str, Any]) -> ExamActivity:
        activity_id = raw.get("activityId", "")
        activity_type = raw.get("activityType", "")
        interaction = raw.get("interaction", "test")
        skills = raw.get("skills") or {}

        steps: List[ExamStep] = []
        for raw_step in raw.get("steps", []):
            step = ExamStepParser._parse_step(raw_step)
            steps.append(step)

        # Activity instructions (could be string or list of dicts)
        inst_val = raw.get("instructions")
        instructions_text = None
        if isinstance(inst_val, str):
            instructions_text = inst_val
        elif isinstance(inst_val, list) and inst_val:
            for item in inst_val:
                if isinstance(item, dict) and item.get("locale", "").startswith("en"):
                    instructions_text = item.get("text")
                    break

        return ExamActivity(
            activity_id=activity_id,
            activity_type=activity_type,
            interaction=interaction,
            skills=skills,
            steps=steps,
            instructions=instructions_text,
        )

    @staticmethod
    def _parse_step(raw: Dict[str, Any]) -> ExamStep:
        step_id = raw.get("activityStepId", "")
        step_type = raw.get("type", "multipleChoice")

        prompt = ""
        passage_html = None
        audio_uri = None
        options: List[ExamOption] = []

        content = raw.get("content", [])

        # Content[0] typically holds prompt, passage, audio URI
        if len(content) > 0:
            first_block = content[0]
            items = first_block if isinstance(first_block, list) else [first_block]
            prompt_parts = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "htmlText" in item:
                    passage_html = item["htmlText"]
                if "text" in item:
                    prompt_parts.append(item["text"])
                if "audios" in item and item["audios"]:
                    audio_info = item["audios"][0]
                    audio_uri = audio_info.get("media_uri")
            if prompt_parts:
                prompt = " | ".join(prompt_parts)

        # Content[1] typically holds choices/options
        if len(content) > 1:
            second_block = content[1]
            items = second_block if isinstance(second_block, list) else [second_block]
            for item in items:
                if not isinstance(item, dict):
                    continue
                opt_id = item.get("id", "")
                opt_text = item.get("text")
                opt_audio = None
                if "audios" in item and item["audios"]:
                    opt_audio = item["audios"][0].get("media_uri")
                options.append(ExamOption(id=opt_id, text=opt_text, audio_uri=opt_audio))

        # Instructions localized
        inst_val = raw.get("instructions")
        instructions_text = None
        if isinstance(inst_val, str):
            instructions_text = inst_val
        elif isinstance(inst_val, list):
            for block in inst_val:
                items = block if isinstance(block, list) else [block]
                for item in items:
                    if isinstance(item, dict) and item.get("locale", "").startswith("en"):
                        instructions_text = item.get("text")
                        break
                if instructions_text:
                    break

        return ExamStep(
            activity_step_id=step_id,
            step_type=step_type,
            prompt=prompt,
            passage_html=passage_html,
            audio_uri=audio_uri,
            options=options,
            instructions=instructions_text,
        )

    @staticmethod
    def _parse_progress(raw: Dict[str, Any]) -> ExamProgress:
        return ExamProgress(
            question_no=raw.get("questionNo", 0),
            no_of_questions=raw.get("noOfQuestions", 0),
            section=raw.get("section", 1),
            tally=raw.get("tally"),
            ability=raw.get("ability"),
            standard_error=raw.get("standardError"),
        )

    @staticmethod
    def _parse_score(raw: Dict[str, Any]) -> Optional[ExamScore]:
        score_val = raw.get("score")
        if score_val is None:
            return None
        return ExamScore(
            score=int(score_val),
            max_score=int(raw.get("maxScore", 400)),
            cefr=str(raw.get("cefr", "")),
            ilr=raw.get("ilr"),
            clb=raw.get("clb"),
            warning=raw.get("warning"),
        )
