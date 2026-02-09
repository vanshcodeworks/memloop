# MemLoop 

**The Plug-and-Play Memory Engine for AI Agents.**

[![PyPI version](https://badge.fury.io/py/memloop.svg)](https://badge.fury.io/py/memloop)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MemLoop** is a local-first Python library that gives LLMs "Infinite Memory". It ingests documents (PDF, CSV, TXT) and websites, stores them in a local vector database, and retrieves them with citation-style mapping.

No API keys required. 100% Offline Capable.

---

##  Quick Start

### Installation

```bash
pip install memloop
```

### The 30-Second Demo (Interactive CLI)

```bash
memloop
```

---

##  Build Your First RAG Agent (The 20-Line Tutorial)

Retrieval-Augmented Generation (RAG) usually requires setting up Vector DBs, Embedding Models, and Retrievers. **MemLoop** handles that complexity so you can focus on the logic.

### With Gemini

```python
import google.generativeai as genai
from memloop import MemLoop

# --- Configuration ---
genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel('gemini-pro')
brain = MemLoop()

# --- Step 1: Ingest (Run once, persist forever) ---
# brain.learn_url("https://docs.python.org/3/glossary.html") 

# --- Step 2: Retrieve ---
query = "What is a decorator in Python?"
context = brain.recall(query) # <--- MemLoop does the heavy lifting

# --- Step 3: Generate ---
prompt = f"Use this context to answer:\n{context}\n\nUser: {query}"
response = model.generate_content(prompt)

print(response.text)
```

### With OpenAI

```python
from openai import OpenAI
from memloop import MemLoop

client = OpenAI(api_key="YOUR_KEY")
brain = MemLoop()

# brain.learn_local("./my_docs")

query = "Summarize the documents."
context = brain.recall(query)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": f"Context:\n{context}\n\nQ: {query}"}]
)
print(response.choices[0].message.content)
```

---

##  API Reference

### `MemLoop()`
The main entry point. Initializes the local vector store (ChromaDB) in `./memloop_data`.
```python
brain = MemLoop(db_path="./custom_folder")
```

### `.learn_url(url: str)`
Scrapes a webpage, cleans the HTML, chunks the text, and stores vectors locally.
* **Returns:** `int` (Number of chunks ingested).

### `.learn_local(folder_path: str)`
Recursively ingests a local folder. Supports `.pdf` (with page tracking), `.csv` (row linearization), `.txt`, and `.md`.
* **Returns:** `int` (Number of documents processed).

### `.recall(query: str)`
Retrieves the most relevant context.
1. Checks **Semantic Cache** (O(1) return if query is repeated).
2. If miss, performs **Vector Search** (Cosine Similarity).
3. Returns formatted string with Citations.

---

##  Pro Tip: The "Persistent Brain"

Because MemLoop uses **ChromaDB** locally, you don't need to run `.learn_url` every time!

Run the script once to learn:

```python
brain.learn_url("https://docs.python.org") # Run this ONCE
```

Then comment it out. Your agent now "remembers" that data forever in future runs.

---

##  Technology Stack

*   **Vector Querying**: ChromaDB
*   **Embeddings**: all-MiniLM-L6-v2 (HuggingFace)
*   **Parsing**: BeautifulSoup4 (Web), PyPDF (Docs)

---

*Built with ❤️ by Vansh.*