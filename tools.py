import urllib.request
import urllib.parse
import ssl
import re

def search_web(query: str) -> str:
    """Use this tool ONLY to search the internet for real-time information, current events, or specific facts you don't confidently know. Do NOT use this tool for conversational chit-chat, personal questions, or general knowledge."""
    print(f"\n[AI is searching the web for: '{query}'...]", flush=True)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    encoded_query = urllib.parse.quote(query)
    req = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?q={encoded_query}",
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Extract basic result snippets from DuckDuckGo lite HTML
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            
            clean_snippets = []
            for s in snippets:
                # Remove HTML tags
                clean_s = re.sub(r'<[^>]+>', '', s)
                # Decode basic HTML entities
                clean_s = clean_s.replace('&#39;', "'").replace('&quot;', '"').replace('&amp;', '&')
                clean_snippets.append(clean_s.strip())
                
            res = "\n---\n".join(clean_snippets[:5])
            if not res:
                return "No results found for the query."
            return "Search Results:\n" + res
            
    except Exception as e:
        return f"Search failed due to an error: {e}"
