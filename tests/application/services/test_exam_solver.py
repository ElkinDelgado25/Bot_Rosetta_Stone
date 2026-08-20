import pytest
from rosseta_stone_script_a.application.services.exam_solver import ExamSolver
from rosseta_stone_script_a.domain.entities.exam import (
    ExamActivity,
    ExamOption,
    ExamStep,
)


def test_solver_uses_verified_answers():
    solver = ExamSolver()
    # Use known step ID from our extracted HAR bank
    known_step_id = "ed786919-2b37-4cd6-bb33-91cfdd0942d3"
    
    # Check if known_step_id exists in verified answers
    if known_step_id in solver._verified_answers:
        expected_content_id = solver._verified_answers[known_step_id]
        
        step = ExamStep(
            activity_step_id=known_step_id,
            step_type="multipleChoice",
            prompt="I ____ like to cook.",
            options=[
                ExamOption(id=expected_content_id, text="don't"),
                ExamOption(id="wrong_id", text="no"),
            ],
        )
        
        answer = solver.solve_step(step)
        assert answer is not None
        assert answer.activity_step_id == known_step_id
        assert answer.content_id == expected_content_id


def test_solver_heuristic_grammar():
    solver = ExamSolver()
    # Step with unknown ID
    step = ExamStep(
        activity_step_id="unknown_step_999",
        step_type="multipleChoice",
        prompt="This sweatshirt doesn't belong to me; it's ____.",
        options=[
            ExamOption(id="opt1", text="her"),
            ExamOption(id="opt2", text="hers"),
            ExamOption(id="opt3", text="she"),
            ExamOption(id="opt4", text="herself"),
        ],
    )
    
    answer = solver.solve_step(step)
    assert answer is not None
    assert answer.activity_step_id == "unknown_step_999"
    assert answer.content_id == "opt2"  # "hers"


def test_solver_fallback_first_option():
    solver = ExamSolver()
    step = ExamStep(
        activity_step_id="unknown_step_abc",
        step_type="multipleChoice",
        prompt="Arbitrary unindexed prompt",
        options=[
            ExamOption(id="first_choice", text="First choice"),
            ExamOption(id="second_choice", text="Second choice"),
        ],
    )
    
    answer = solver.solve_step(step)
    assert answer is not None
    assert answer.content_id == "first_choice"
