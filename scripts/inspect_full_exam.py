import json
from pathlib import Path

har_path = Path(__file__).resolve().parents[1] / "hars" / "login.rosettastone.com.har"
with open(har_path, encoding="utf-8") as f:
    har = json.load(f)

steps_summary = []
all_answers = {}
activity_types = set()

for idx, e in enumerate(har["log"]["entries"]):
    req = e["request"]
    url = req["url"]
    if "gaia-server.rosettastone.com" in url and req["method"] == "POST":
        body = json.loads(req.get("postData", {}).get("text", "{}"))
        resp = json.loads(e["response"].get("content", {}).get("text", "{}"))
        
        msg = body.get("variables", {}).get("message", {})
        step_data = resp.get("data", {}).get("assessmentStep", {})
        
        act = step_data.get("activity") or {}
        prog = step_data.get("progress") or {}
        score = step_data.get("score") or {}
        
        if act.get("activityType"):
            activity_types.add(act["activityType"])

        for ans in msg.get("answers", []):
            all_answers[ans["activityStepId"]] = ans["contentId"]
            
        p_str = f"Q{prog.get('questionNo')}/{prog.get('noOfQuestions')} (sec {prog.get('section')})" if prog else "None"
        steps_summary.append({
            "step_num": len(steps_summary) + 1,
            "har_index": idx,
            "req_activity_id": msg.get("activityId"),
            "answers_submitted": len(msg.get("answers", [])),
            "resp_assessment_name": step_data.get("assessmentName"),
            "resp_activity_id": act.get("activityId"),
            "resp_activity_type": act.get("activityType"),
            "resp_steps_count": len(act.get("steps", [])),
            "progress": p_str,
            "score": score.get("score"),
            "cefr": score.get("cefr"),
        })

print(f"Total exam step requests: {len(steps_summary)}")
print(f"Activity types seen: {activity_types}")
print(f"Total unique verified answers collected: {len(all_answers)}")

print("\n--- FIRST 5 CALLS ---")
for s in steps_summary[:5]:
    print(json.dumps(s, indent=2))

print("\n--- LAST 5 CALLS ---")
for s in steps_summary[-5:]:
    print(json.dumps(s, indent=2))
