import requests
from bs4 import BeautifulSoup

def crawl_and_extract(url, chunk_size=500, overlap=50):
    """Fetch a URL, strip boilerplate, return overlapping text chunks."""
    
    # Define headers to mimic a real browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # Pass headers here to fix the 403 error
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.extract()

        text = soup.get_text(separator=" ")
        text = " ".join(text.split())  # collapse whitespace

        if not text:
            return []

        step = max(chunk_size - overlap, 1)
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), step)]
        return [c for c in chunks if c.strip()]

    except Exception as e:
        print(f"Error reading {url}: {e}")
        return []