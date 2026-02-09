import sys
import time
from .brain import MemLoop

def type_writer(text, speed=0.02):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    print("")

def main():
    print("\n" + "=" * 40)
    print("   MEMLOOP v0.1.0 - Local Vector Memory")
    print("=" * 40)
    print("Initializing...")

    agent = MemLoop()

    print("\ncommands:")
    print("  /learn <url>   ->  Ingest a website into Long-Term Memory")
    print("  /status        ->  Show memory stats")
    print("  /forget        ->  Clear semantic cache")
    print("  /exit          ->  Close the session")
    print("  <text>         ->  Chat/Add to Memory")
    print("-" * 40 + "\n")

    while True:
        try:
            user_input = input("\n[USER]: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "/exit":
                type_writer("[SYSTEM]: Shutting down memory core. Goodbye.")
                break

            elif user_input.lower() == "/status":
                print(f"[SYSTEM]: {agent.status()}")

            elif user_input.lower() == "/forget":
                agent.forget_cache()
                type_writer("[SYSTEM]: Semantic cache cleared.")

            elif user_input.startswith("/learn "):
                url = user_input.split(" ", 1)[1]
                type_writer(f"[SYSTEM]: Deploying spider to {url}...")
                try:
                    count = agent.learn_url(url)
                    type_writer(f"[SYSTEM]: Success. Absorbed {count} knowledge chunks.")
                except Exception as e:
                    type_writer(f"[ERROR]: Failed to ingest. {e}")

            elif user_input.startswith("/read "):
                path = user_input.split(" ", 1)[1].strip()
                type_writer(f"[SYSTEM]: Ingesting local data from {path}...")
                try:
                    count = agent.learn_local(path)
                    type_writer(f"[SYSTEM]: Success. Indexed {count} documents/rows.")
                except Exception as e:
                    type_writer(f"[ERROR]: Could not read path. {e}")

            else:
                agent.add_memory(user_input)
                type_writer("[SYSTEM]: Searching Vector Space...")
                response = agent.recall(user_input)

                print("\n[MEMLOOP KNOWLEDGE GRAPH]:")
                print("-" * 40)
                print(response)
                print("-" * 40)
                print("Tip: Use sources to verify facts.\n")

        except KeyboardInterrupt:
            print("\n[SYSTEM]: Force quit detected.")
            break

if __name__ == "__main__":
    main()
