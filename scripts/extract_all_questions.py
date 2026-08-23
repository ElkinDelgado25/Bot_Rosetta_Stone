import json
from pathlib import Path

har_path = Path(__file__).resolve().parents[1] / "hars" / "login.rosettastone.com.har"
with open(har_path, encoding="utf-8") as f:
    har = json.load(f)

exam_steps = []
for idx, e in enumerate(har["log"]["entries"]):
    req = e["request"]
    url = req["url"]
    if "gaia-server.rosettastone.com" in url and req["method"] == "POST":
        req_body = json.loads(req.get("postData", {}).get("text", "{}"))
        resp_body = json.loads(e["response"].get("content", {}).get("text", "{}"))

        msg = req_body.get("variables", {}).get("message", {})
        step_data = resp_body.get("data", {}).get("assessmentStep", {})

        exam_steps.append({
            "req_msg": msg,
            "resp_step": step_data
        })

print(f"Total steps: {len(exam_steps)}")

# Let's inspect each activity and its question details
detailed_questions = []

for i, step in enumerate(exam_steps):
    resp_step = step["resp_step"]
    act = resp_step.get("activity")
    if not act:
        continue

    act_id = act.get("activityId")
    act_type = act.get("activityType")
    prog = resp_step.get("progress") or {}

    for s_idx, s in enumerate(act.get("steps", [])):
        step_id = s.get("activityStepId")
        step_type = s.get("type")
        content = s.get("content", [])

        prompt = []
        passage = None
        audio = None
        options = []

        if len(content) > 0:
            c0 = content[0]
            items = c0 if isinstance(c0, list) else [c0]
            for it in items:
                if isinstance(it, dict):
                    if "text" in it:
                        prompt.append(it["text"])
                    if "htmlText" in it:
                        passage = it["htmlText"]
                    if "audios" in it and it["audios"]:
                        audio = it["audios"][0].get("media_uri")

        if len(content) > 1:
            c1 = content[1]
            items = c1 if isinstance(c1, list) else [c1]
            for it in items:
                if isinstance(it, dict):
                    options.append({
                        "id": it.get("id"),
                        "text": it.get("text"),
                        "audio": it.get("audios", [{}])[0].get("media_uri") if it.get("audios") else None
                    })

        # Find what the user submitted in the next request for this step_id
        submitted_answer = None
        if i + 1 < len(exam_steps):
            next_req_msg = exam_steps[i + 1]["req_msg"]
            for ans in next_req_msg.get("answers", []):
                if ans.get("activityStepId") == step_id:
                    submitted_answer = ans.get("contentId")

        detailed_questions.append({
            "step_num": len(detailed_questions) + 1,
            "activity_id": act_id,
            "activity_type": act_type,
            "step_id": step_id,
            "section": prog.get("section"),
            "question_no": prog.get("questionNo"),
            "no_of_questions": prog.get("noOfQuestions"),
            "prompt": " | ".join(prompt),
            "passage": passage,
            "audio": audio,
            "options": options,
            "submitted_content_id": submitted_answer,
        })

out_path = Path(__file__).resolve().parents[1] / "logs" / "diagnostics" / "exam_all_questions_detailed.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(detailed_questions, f, indent=2, ensure_ascii=False)

print(f"Extracted {len(detailed_questions)} questions to {out_path}")
