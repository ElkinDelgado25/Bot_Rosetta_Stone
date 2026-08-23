"""One-off HAR analyzer for exam flow."""
import json
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

har_path = Path(__file__).resolve().parents[1] / "hars" / "login.rosettastone.com.har"
print(f"Loading {har_path}...")
with open(har_path, encoding="utf-8") as f:
    har = json.load(f)

entries = har["log"]["entries"]
print(f"Total entries: {len(entries)}")

by_domain = Counter()
exam_related = []
tracking = []
graphql = []
gaia = []
insert_assessment = []

for e in entries:
    req = e["request"]
    url = req["url"]
    parsed = urlparse(url)
    domain = parsed.netloc
    by_domain[domain] += 1

    url_lower = url.lower()
    if any(k in url_lower for k in ("exam", "assessment", "milestone", "checkpoint", "screener")):
        exam_related.append(e)
    if "tracking.rosettastone.com" in url:
        tracking.append(e)
    if "graph.rosettastone.com" in url:
        graphql.append(e)
    if "gaia-server.rosettastone.com" in url:
        gaia.append(e)
        body = req.get("postData", {}).get("text", "")
        if body and "insertAssessmentStep" in body:
            insert_assessment.append(e)

print("\n=== TOP DOMAINS ===")
for d, c in by_domain.most_common(15):
    print(f"  {c:5d}  {d}")

print(f"\n=== insertAssessmentStep calls: {len(insert_assessment)} ===")
for i, e in enumerate(insert_assessment):
    req = e["request"]
    body_text = req.get("postData", {}).get("text", "")
    resp_text = e["response"].get("content", {}).get("text", "")
    print(f"\n--- Step {i + 1} ---")
    print(f"Status: {e['response']['status']}")
    try:
        body = json.loads(body_text)
        variables = body.get("variables", {})
        print(f"Variables keys: {list(variables.keys())}")
        print(f"Payload: {json.dumps(variables, indent=2)[:800]}")
    except json.JSONDecodeError:
        print(f"Body (raw): {body_text[:400]}")
    try:
        resp = json.loads(resp_text)
        data = resp.get("data", {})
        step = data.get("insertAssessmentStep", {}).get("assessmentStep", {})
        if step:
            act = step.get("activity") or {}
            print(f"Response activity id: {act.get('id')}")
            print(f"Response assessmentName: {step.get('assessmentName')}")
            print(f"Response score: {step.get('score')}")
            steps = act.get("steps") or []
            if steps:
                s0 = steps[0]
                print(f"First step id: {s0.get('id')}, type: {s0.get('type')}")
                opts = s0.get("options") or []
                print(f"Options count: {len(opts)}")
                if opts:
                    print(f"First option: {opts[0].get('id')} -> {str(opts[0].get('content', ''))[:80]}")
    except (json.JSONDecodeError, TypeError):
        print(f"Response (raw): {resp_text[:400]}")

print(f"\n=== TRACKING unique paths ===")
tracking_paths = Counter()
for e in tracking:
    p = urlparse(e["request"]["url"])
    tracking_paths[f"{e['request']['method']} {p.path}"] += 1
for u, c in tracking_paths.most_common(20):
    print(f"  {c:3d}  {u}")

print(f"\n=== GAIA GraphQL operations ===")
gql_ops = Counter()
for e in gaia:
    body = e["request"].get("postData", {}).get("text", "")
    op = "unknown"
    if body:
        try:
            j = json.loads(body)
            op = j.get("operationName", j.get("query", "")[:60])
        except json.JSONDecodeError:
            pass
    gql_ops[op] += 1
for op, c in gql_ops.most_common(20):
    print(f"  {c:3d}  {op}")

print(f"\n=== EXAM URL hits: {len(exam_related)} ===")
for e in exam_related[:20]:
    print(f"  {e['request']['method']} {e['request']['url'][:120]}")
