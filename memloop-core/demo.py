import google.generativeai as genai
from memloop import MemLoop

genai.configure(api_key="YOUR_GEMINI_KEY")
model = genai.GenerativeModel('gemini-2.5-flash')
brain = MemLoop()

print(f"Learned {brain.learn_url('https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)')} chunks.")

query = "What is a transformer?"
context = brain.recall(query)

response = model.generate_content(f"Answer using this context:\n{context}\n\nUser: {query}")

print(f"\n Context Found:\n{context[:200]}...\n") 
print(f" Gemini Says:\n{response.text}")