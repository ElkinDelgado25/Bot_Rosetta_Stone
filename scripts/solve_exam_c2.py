import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "logs" / "diagnostics" / "exam_all_questions_detailed.json"
with open(p, encoding="utf-8") as f:
    questions = json.load(f)

out_txt = Path(__file__).resolve().parents[1] / "logs" / "diagnostics" / "exam_questions_dump.txt"
with open(out_txt, "w", encoding="utf-8") as out:
    out.write(f"Total questions in exam: {len(questions)}\n")
    for q in questions:
        out.write(f"\n==================================================\n")
        out.write(f"#{q['step_num']} | Section {q['section']} | Q{q['question_no']} | Type: {q['activity_type']}\n")
        if q.get("prompt"):
            out.write(f"Prompt: {q['prompt']}\n")
        if q.get("passage"):
            out.write(f"Passage: {q['passage']}\n")
        if q.get("audio"):
            out.write(f"Audio URI: {q['audio']}\n")

        out.write("Options:\n")
        for opt in q["options"]:
            is_sub = " <--- [SUBMITTED IN HAR]" if opt["id"] == q["submitted_content_id"] else ""
            out.write(f"  [{opt['id']}] {opt.get('text')}{is_sub}\n")

print(f"Dumped {len(questions)} questions to {out_txt}")
