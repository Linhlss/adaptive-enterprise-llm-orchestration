import json

def mock_llm(prompt):
    # Replace this mock with OpenAI / Gemini if available.
    return [
        {
            "question": "What is the main content of this passage?",
            "answer": prompt[:100]
        }
    ]


def generate_qa_from_chunk(chunk):
    prompt = f"""
    Generate 2-3 question-answer pairs from the passage below:

    {chunk}
    """

    qa_pairs = mock_llm(prompt)

    results = []
    for qa in qa_pairs:
        results.append({
            "question": qa["question"],
            "answer": qa["answer"],
            "source": chunk
        })

    return results


def generate_dataset(chunks):
    dataset = []

    for chunk in chunks:
        qa_pairs = generate_qa_from_chunk(chunk["content"])
        dataset.extend(qa_pairs)

    return dataset


def save_dataset(dataset, path="generated_qa.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
