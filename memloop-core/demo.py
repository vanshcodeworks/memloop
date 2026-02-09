from memloop import MemLoop

brain = MemLoop()
brain.add_memory("The secret code is 42.")

def chat_with_memory(user_query):
    context = brain.recall(user_query)
    print(f"[DEBUG] Retrieved Context: {context}")
    return context


print(chat_with_memory("What is the secret code?"))