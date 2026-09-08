from sentence_transformers import SentenceTransformer

import faiss
import numpy as np

# =========================
# LOAD MODEL
# =========================

model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# =========================
# KNOWLEDGE BASE
# =========================

documents = [
    "Site visit requests are usually confirmed within 1 business day after the customer shares the preferred project, time window, and callback number.",
    "Payment receipts and ledger clarifications require the transaction reference, payment date, amount paid, and the related project or unit reference.",
    "Construction progress updates must stay aligned with approved milestone reports, and exact possession dates should not be promised unless officially confirmed.",
    "Handover and maintenance issues should include the project name, tower or unit number, and photo or video evidence for faster triage.",
    "Legal and registration document requests should capture the buyer name, project name, booking reference, and exact document needed.",
    "Safety-sensitive issues such as leakage, electrical faults, or structural concerns should be escalated with high priority."
]

# =========================
# CREATE EMBEDDINGS
# =========================

embeddings = model.encode(documents)

# =========================
# CREATE FAISS INDEX
# =========================

dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(dimension)

index.add(
    np.array(embeddings)
)

# =========================
# SEARCH KNOWLEDGE BASE
# =========================

def search_knowledge_base(query):

    query_embedding = model.encode([query])

    distances, indices = index.search(
        np.array(query_embedding),
        k=1
    )

    return documents[
        indices[0][0]
    ]