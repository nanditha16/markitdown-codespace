from sentence_transformers import SentenceTransformer
from pathlib import Path
import numpy as np
import sys

query = sys.argv[1] if len(sys.argv) > 1 else None

if not query:
    print("❌ Provide a query")
    exit(1)

print("🧠 Semantic retrieval...")

model = SentenceTransformer("all-MiniLM-L6-v2")

chunks_dir = Path("chunks")

documents = []
files = []

for f in chunks_dir.glob("*.md"):
    text = f.read_text().strip()
    if text:
        documents.append(text)
        files.append(f)

if not documents:
    print("❌ No chunks found")
    exit(1)

# ✅ Encode documents and query
doc_embeddings = model.encode(documents)
query_embedding = model.encode([query])[0]

# ✅ Compute similarity
scores = np.dot(doc_embeddings, query_embedding)

# ✅ Get top 4 chunks
top_indices = np.argsort(scores)[-4:][::-1]

output_file = "semantic_prompt.txt"

with open(output_file, "w") as out:
    out.write("You are analyzing relevant document sections.\n")
    out.write("Answer using ONLY the context below.\n\n")
    out.write("QUESTION:\n")
    out.write(query + "\n\n")
    out.write("RELEVANT CHUNKS:\n")

    for i in top_indices:
        f = files[i]
        out.write(f"\n----- {f.name} -----\n")

        # ✅ limit chunk size (important)
        lines = documents[i].split("\n")[:60]
        out.write("\n".join(lines))
        out.write("\n")

print(f"✅ Saved to {output_file}")
