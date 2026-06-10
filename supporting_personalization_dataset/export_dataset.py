import json

def export_lora_format(input_path, output_path):
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    formatted = []

    for item in data:
        formatted.append({
            "instruction": item["question"],
            "input": "",
            "output": item["answer"]
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)