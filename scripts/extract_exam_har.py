"""Extract exam bootstrap and final step details from HAR."""
import json
from pathlib import Path

har_path = Path(__file__).resolve().parents[1] / "hars" / "login.rosettastone.com.har"
with open(har_path, encoding="utf-8") as f:
    har = json.load(f)

insert_calls = []
for e in har["log"]["entries"]:
    body = e["request"].get("postData", {}).get("text", "")
    if body and "insertAssessmentStep" in body:
        insert_calls.append(e)

print(f"Total insertAssessmentStep: {len(insert_calls)}")

# Bootstrap (step 1)
e = insert_calls[0]
resp = json.loads(e["response"]["content"]["text"])
step = resp["data"]["assessmentStep"]
print("\n=== BOOTSTRAP RESPONSE ===")
print(f"assessmentName: {step.get('assessmentName')}")
act = step.get("activity") or {}
print(f"activityId: {act.get('activityId')}")
print(f"activityType: {act.get('activityType')}")
steps = act.get("steps") or []
print(f"steps count: {len(steps)}")
if steps:
    s = steps[0]
    print(f"first step id: {s.get('activityStepId')}")
    print(f"first step type: {s.get('type')}")

# Final steps
for label, idx in [("second-to-last request", -2), ("last request", -1)]:
    e = insert_calls[idx]
    req_body = json.loads(e["request"]["postData"]["text"])
    msg = req_body["variables"]["message"]
    print(f"\n=== {label.upper()} REQUEST ===")
    print(json.dumps(msg, indent=2))
    resp = json.loads(e["response"]["content"]["text"])
    step = resp["data"]["assessmentStep"]
    print(f"Response assessmentName: {step.get('assessmentName')}")
    print(f"Response activity: {step.get('activity')}")
    score = step.get("score")
    if score:
        print(f"Score: {score}")

# Auth headers on first gaia call
e = insert_calls[0]
print("\n=== HEADERS (bootstrap) ===")
for h in e["request"]["headers"]:
    name = h["name"].lower()
    if name in ("authorization", "cookie", "origin", "referer"):
        val = h["value"]
        if name == "authorization":
            val = val[:40] + "..."
        print(f"  {h['name']}: {val}")

# Navigation URLs
print("\n=== NAVIGATION URLS ===")
for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if any(d in url for d in ("learn.rosettastone.com", "login.rosettastone.com/launchpad", "screener", "assessment")):
        if ".js" not in url and ".css" not in url and ".png" not in url:
            print(f"  {e['request']['method']} {url[:150]}")

# Extract verified answers from HAR
answers = {}
for e in insert_calls[1:]:
    req_body = json.loads(e["request"]["postData"]["text"])
    msg = req_body["variables"]["message"]
    for ans in msg.get("answers") or []:
        answers[ans["activityStepId"]] = ans["contentId"]

print(f"\n=== VERIFIED ANSWERS FROM HAR: {len(answers)} ===")
out = Path(__file__).resolve().parents[1] / "src" / "Resolucion_script_rosseta" / "infraestructura" / "adapters" / "exam_api" / "exam_verified_answers_har.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(answers, f, indent=2, sort_keys=True)
print(f"Wrote {out}")
