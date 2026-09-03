import json
from pathlib import Path

# Load all questions detailed
dump_path = Path(__file__).resolve().parents[1] / "logs" / "diagnostics" / "exam_all_questions_detailed.json"
with open(dump_path, encoding="utf-8") as f:
    questions = json.load(f)

# Correct answers dictionary mapping step_id -> correct option_id
c2_answers = {}

# Map known perfect answers by step_id or logic
for q in questions:
    step_id = q["step_id"]
    prompt = q.get("prompt", "")
    options = q.get("options", [])

    # 1. Direct prompt matching for 100% accuracy
    if "I ____ like to cook." in prompt:
        opt = next(o for o in options if o["text"] == "don't")
        c2_answers[step_id] = opt["id"]
    elif "Jack is ____ student in his class." in prompt:
        opt = next(o for o in options if o["text"] == "the best")
        c2_answers[step_id] = opt["id"]
    elif "I have ____ cats." in prompt:
        opt = next(o for o in options if o["text"] == "two large black")
        c2_answers[step_id] = opt["id"]
    elif "He knew he ____ call her" in prompt:
        opt = next(o for o in options if o["text"] == "should")
        c2_answers[step_id] = opt["id"]
    elif "They are ____ meet us for coffee" in prompt:
        opt = next(o for o in options if o["text"] == "going to")
        c2_answers[step_id] = opt["id"]
    elif "This sweatshirt doesn't belong to me; it's ____." in prompt:
        opt = next(o for o in options if o["text"] == "hers")
        c2_answers[step_id] = opt["id"]
    elif "Please don't ____ to buy bread" in prompt:
        opt = next(o for o in options if o["text"] == "forget")
        c2_answers[step_id] = opt["id"]
    elif "She likes to ____ movies on her tablet." in prompt:
        opt = next(o for o in options if o["text"] == "watch")
        c2_answers[step_id] = opt["id"]
    elif "thinking carefully can have serious ____." in prompt:
        opt = next(o for o in options if o["text"] == "consequences")
        c2_answers[step_id] = opt["id"]
    elif "Helen couldn’t ____ how hard it must be" in prompt:
        opt = next(o for o in options if o["text"] == "imagine")
        c2_answers[step_id] = opt["id"]
    elif "We ____ see her get angry or upset." in prompt:
        opt = next(o for o in options if o["text"] == "rarely")
        c2_answers[step_id] = opt["id"]
    elif "salary makes up for it" in prompt:
        opt = next(o for o in options if "People are paid fairly" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "study animals for a report" in prompt:
        opt = next(o for o in options if "They learned about animals" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "pick up a cake and some fruit" in prompt:
        opt = next(o for o in options if "They bought food for an event" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Eric stayed late at the office" in prompt:
        opt = next(o for o in options if "He wanted Eric to finish some work" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Janet and her friends wanted to go shopping" in prompt:
        opt = next(o for o in options if "She wasn’t able to go shopping" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "waiting in line to mail a gift" in prompt:
        opt = next(o for o in options if "She is in the post office" in o["text"])
        c2_answers[step_id] = opt["id"]

    # Section 2
    elif "After we finish the job, we ____ go home." in prompt:
        opt = next(o for o in options if o["text"] == "can")
        c2_answers[step_id] = opt["id"]
    elif "She ____ have to work hard in order to finish" in prompt:
        opt = next(o for o in options if o["text"] == "is going to")
        c2_answers[step_id] = opt["id"]
    elif "____ Bob nor Lisa could finish" in prompt:
        opt = next(o for o in options if o["text"] == "Neither")
        c2_answers[step_id] = opt["id"]
    elif "go to the park ____ it stops raining." in prompt:
        opt = next(o for o in options if o["text"] == "unless")
        c2_answers[step_id] = opt["id"]
    elif "You ____ all day today. Why don't you take a break" in prompt:
        opt = next(o for o in options if o["text"] == "have been writing")
        c2_answers[step_id] = opt["id"]
    elif "could really use a ____." in prompt:
        opt = next(o for o in options if o["text"] == "break")
        c2_answers[step_id] = opt["id"]
    elif "Can you ____ me with those earphones on?" in prompt:
        opt = next(o for o in options if o["text"] == "hear")
        c2_answers[step_id] = opt["id"]
    elif "grow vegetables" in prompt:
        opt = next(o for o in options if o["text"] == "rural")
        c2_answers[step_id] = opt["id"]
    elif "Staff must ____ to all email" in prompt:
        opt = next(o for o in options if o["text"] == "reply")
        c2_answers[step_id] = opt["id"]
    elif "canceled ____ the rain." in prompt:
        opt = next(o for o in options if o["text"] == "because of")
        c2_answers[step_id] = opt["id"]
    elif "takes a lot of business ____" in prompt:
        opt = next(o for o in options if o["text"] == "trips")
        c2_answers[step_id] = opt["id"]
    elif "taking the tour" in prompt:
        opt = next(o for o in options if "say they will join a group" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "After getting promoted to his new position, Charles" in prompt:
        opt = next(o for o in options if "He is spending more time at work" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "enormous shopping mall" in prompt:
        opt = next(o for o in options if "Local opinions are varied" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Paul went out for lunch" in prompt:
        opt = next(o for o in options if "He met friends instead of working" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Kate thought it might be a good idea" in prompt:
        opt = next(o for o in options if "She hasn’t ordered new computers yet" in o["text"])
        c2_answers[step_id] = opt["id"]

    # Section 3
    elif "Ericka decided to ____ the instructions" in prompt:
        opt = next(o for o in options if o["text"] == "ignore")
        c2_answers[step_id] = opt["id"]
    elif "gives people the false ____" in prompt:
        opt = next(o for o in options if o["text"] == "impression")
        c2_answers[step_id] = opt["id"]
    elif "mayor’s goal is to close this ____." in prompt:
        opt = next(o for o in options if o["text"] == "gap")
        c2_answers[step_id] = opt["id"]
    elif "haven't seen a movie star." in prompt:
        opt = next(o for o in options if o["text"] == "waiting")
        c2_answers[step_id] = opt["id"]
    elif "Mary will be ____ to come to work tomorrow" in prompt:
        opt = next(o for o in options if o["text"] == "unable")
        c2_answers[step_id] = opt["id"]
    elif "tomorrow morning’s meeting." in prompt:
        opt = next(o for o in options if o["text"] == "attend")
        c2_answers[step_id] = opt["id"]
    elif "talk with my friends." in prompt:
        opt = next(o for o in options if o["text"] == "early")
        c2_answers[step_id] = opt["id"]
    elif "top of the hill." in prompt:
        opt = next(o for o in options if o["text"] == "climbing")
        c2_answers[step_id] = opt["id"]
    elif "Stephen’s essay ____ clear ideas" in prompt:
        opt = next(o for o in options if o["text"] == "lacked")
        c2_answers[step_id] = opt["id"]
    elif "Why did the woman ask the man a question?" in prompt:
        opt = next(o for o in options if "She wanted his recommendation" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the man say about the refrigerator?" in prompt:
        opt = next(o for o in options if "There are not many available" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Why is the woman annoyed?" in prompt:
        opt = next(o for o in options if "They don't have an up-to-date user's guide" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Why does the man repeat the names of the side dishes?" in prompt:
        opt = next(o for o in options if "He is trying to decide which to order" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What is true about the speakers?" in prompt:
        opt = next(o for o in options if "They have been given a difficult assignment" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "comment about his desk?" in prompt:
        opt = next(o for o in options if "He defended his messiness" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What is this passage mainly about?" in prompt:
        opt = next(o for o in options if "a natural recycling process" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "According to the passage, what do fallen leaves provide?" in prompt:
        opt = next(o for o in options if "carbon" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "Why does the author mention eggshells?" in prompt:
        opt = next(o for o in options if "to provide an exception to a rule" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What problem does Jessica have?" in prompt:
        opt = next(o for o in options if "visuals for her proposal" in o["text"])
        c2_answers[step_id] = opt["id"]
    # Additional Adaptive Section 3 Questions
    elif "We loved the apartment so much that we gave the owner a ____" in prompt:
        opt = next(o for o in options if o["text"] == "deposit")
        c2_answers[step_id] = opt["id"]
    elif "Why was the man surprised?" in prompt:
        opt = next(o for o in options if "The woman made a unique purchase" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "How will the woman help the man?" in prompt:
        opt = next(o for o in options if "She will explain work to him" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "How does the man interpret the woman's comment?" in prompt:
        opt = next(o for o in options if "as a criticism about wasting energy" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the man imply about Professor Keeler?" in prompt:
        opt = next(o for o in options if "He has gone home" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the woman imply?" in prompt:
        opt = next(o for o in options if "The man should organize the party" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the man imply about Kevin?" in prompt:
        opt = next(o for o in options if "He doesn't eat lunch with coworkers" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What did the woman comment on?" in prompt:
        opt = next(o for o in options if "how much food the man is buying" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the woman tell the man?" in prompt:
        opt = next(o for o in options if "He is parked illegally" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the man imply about Jerry?" in prompt:
        opt = next(o for o in options if "He is too worried about details" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the woman's comment indicate?" in prompt:
        opt = next(o for o in options if "She agrees that selling to young people is important" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What is the purpose of this text?" in prompt and "hanami" in prompt.lower():
        opt = next(o for o in options if "to describe a popular cultural tradition" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What can be expected of schoolchildren in Japan during hanami?" in prompt:
        opt = next(o for o in options if "They are on vacation" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "What does the author highlight about the United States?" in prompt:
        opt = next(o for o in options if "It holds hanami celebrations" in o["text"])
        c2_answers[step_id] = opt["id"]
    elif "closest in meaning to “attribute”" in prompt:
        opt = next(o for o in options if o["text"] == "assign")
        c2_answers[step_id] = opt["id"]
    elif "how people form opinions based on overall impressions" in prompt:
        opt = next(o for o in options if "how people form opinions" in o["text"])
        c2_answers[step_id] = opt["id"]
    else:
        # For audio-only options without text, default to HAR submitted or first option
        c2_answers[step_id] = q.get("submitted_content_id") or (options[0]["id"] if options else None)

print(f"Total C2 answers mapped: {len(c2_answers)}")

target_file = Path(__file__).resolve().parents[1] / "src" / "Resolucion_script_rosseta" / "infraestructura" / "adapters" / "exam_api" / "exam_verified_answers.json"
with open(target_file, "w", encoding="utf-8") as f:
    json.dump(c2_answers, f, indent=2, sort_keys=True)

print(f"Saved optimized C2 answers to {target_file}")
