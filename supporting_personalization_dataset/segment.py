import os

def load_documents(folder_path):
    docs = []
    for file in os.listdir(folder_path):
        if file.endswith(".txt"):
            with open(os.path.join(folder_path, file), encoding="utf-8") as f:
                docs.append({
                    "source": file,
                    "content": f.read()
                })
    return docs


def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Split on punctuation boundaries
        if "." in chunk:
            end = start + chunk.rfind(".") + 1

        chunks.append(text[start:end])
        start = end - overlap

    return chunks


def segment_documents(docs):
    all_chunks = []

    for doc in docs:
        chunks = chunk_text(doc["content"])
        for c in chunks:
            all_chunks.append({
                "source": doc["source"],
                "content": c
            })

    return all_chunks
