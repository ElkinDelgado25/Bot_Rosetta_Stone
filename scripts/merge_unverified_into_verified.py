import json
from pathlib import Path

# Load current verified answers
target_file = Path(__file__).resolve().parents[1] / "src" / "rosseta_stone_script_a" / "infrastructure" / "adapters" / "exam_api" / "exam_verified_answers.json"
with open(target_file, "r", encoding="utf-8") as f:
    verified = json.load(f)

# Direct exact mappings for all newly discovered Section 3 adaptive questions
new_verified_answers = {
    # "We loved the apartment so much that we gave the owner a ____" -> deposit
    "2cccd891-51a0-4cf4-9961-7bc2916e45b2": "c6cd1ebc-9ba0-463a-b4c3-0a0f7c286fea",
    # "Why was the man surprised?" -> The woman made a unique purchase.
    "31a4209e-58fe-4d70-832d-ec9c13664aa9": "c368babb-8482-45df-ac07-e2fd8f459679",
    # "How will the woman help the man?" -> She will explain work to him.
    "cbee70a4-0ffc-4243-9a7b-4741961b5d2a": "f9e6ec45-c971-4a57-a4e0-91ff603865f7",
    # "How does the man interpret the woman's comment?" -> as a criticism about wasting energy
    "0044ab00-5660-4001-aff4-9d522e900b19": "0d946a4e-10f7-464d-a144-686a22acccc6",
    # "What does the man imply about Professor Keeler?" -> He has gone home.
    "a8389c87-3bb8-4d10-84d3-f045adb0a034": "cc5cdbb1-b356-4821-88a6-3f15696b6c13",
    # "What does the woman imply?" -> The man should organize the party.
    "6e991df4-871b-48ac-af05-a098a29c36e2": "7b39ee2e-ea04-44b0-9f29-54ef4ea06458",
    # "What does the man imply about Kevin?" -> He doesn't like to spend money for food.
    "6048c76d-7e9e-4ce4-a767-b44b654b01f6": "8bc58763-4345-40b1-9116-e86d504f9cab",
    # "What did the woman comment on?" -> how much food the man is buying
    "af944098-0676-4346-9f80-924fb3718f4f": "44740509-f9de-4e34-b43c-75b80790a39d",
    # "What does the woman tell the man?" -> He is parked illegally.
    "c3e238aa-8536-4663-a77f-b5a9adc719ba": "1bd67096-6233-4a55-901a-a7ee49d6e0ff",
    # "What does the man imply about Jerry?" -> He is too worried about details.
    "d500e869-7b2d-4225-86d6-1ee7ca55b0a5": "72b289ce-f733-4066-bb7f-ed5c6ef3f682",
    # "What does the woman's comment indicate?" -> She agrees that selling to young people is important.
    "6b4e2820-d384-4997-8b40-cbf44b4bce4f": "822195fd-e710-44d2-9798-70ddf8415d3a",
    # "What is the purpose of this text?" (Hanami) -> to describe a popular cultural tradition
    "b2a269e1-c5c7-4557-b0af-de26691e1414": "0b32e2bb-7989-47ef-8de4-e6cc98706516",
    # "What can be expected of schoolchildren in Japan during hanami?" -> They are on vacation.
    "ea151e9c-9e76-44ef-ab2c-e3d5e9a048cf": "dc71d101-f324-46ea-88e0-a9ef161152fe",
    # "What does the author highlight about the United States?" -> It holds hanami celebrations.
    "216e1a90-3243-4f78-bc41-339a2a72fcc2": "eeee4f9b-3823-4aa3-89b2-13c962fa6371",
    # "What is this passage mainly about?" (Halo effect) -> to discuss how people form opinions based on overall impressions
    "87b1dac7-ad39-4dcf-afea-4f3f37e30ada": "85004045-0124-4f7a-b06f-49daa2ecbbb2",
    # "Which word is closest in meaning to “attribute”..." -> assign
    "8dffe865-6a88-41d3-882e-0dbb865b7bf0": "4b5927d9-f4a8-4ca3-a53e-86056b1fd6ec",
    # "What does the author imply about overcoming bias?" -> It requires conscious effort.
    "c26788ba-ac48-4187-b508-02c5b75d88e9": "0adeb7f4-ccdf-403f-aac0-9aacd7eb854b",
}

verified.update(new_verified_answers)

with open(target_file, "w", encoding="utf-8") as f:
    json.dump(verified, f, indent=2, sort_keys=True)

print(f"Successfully updated verified answers! Total bank size: {len(verified)}")
