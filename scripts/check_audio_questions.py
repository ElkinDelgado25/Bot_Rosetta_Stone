import json
from pathlib import Path

har_path = Path(__file__).resolve().parents[1] / "hars" / "login.rosettastone.com.har"
with open(har_path, encoding="utf-8") as f:
    har = json.load(f)

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "gaia-server.rosettastone.com" in url and e["request"]["method"] == "POST":
        resp = json.loads(e["response"].get("content", {}).get("text", "{}"))
        act = resp.get("data", {}).get("assessmentStep", {}).get("activity")
        if act and act.get("activityType") in ("OTextOQuestionOAnswers", "ShortDialogueWQuestionWAnswers"):
            print(f"\nActivity: {act.get('activityId')} ({act.get('activityType')})")
            for s in act.get("steps", []):
                print(f"  Step: {s.get('activityStepId')}")
                content = s.get("content", [])
                if len(content) > 0:
                    print(f"    Prompt/Audio content: {content[0]}")
                if len(content) > 1:
                    print(f"    Options count: {len(content[1])}")
                    for opt in content[1]:
                        print(f"      Option: {opt}")
