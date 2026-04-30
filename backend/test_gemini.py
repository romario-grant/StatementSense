import os
from google import genai
from dotenv import load_dotenv

load_dotenv('c:/Users/Romario Grant/Desktop/StatementSense/.env')

try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents="Hello",
        config={"tools": [{"googleSearch": {}}]}
    )
    print("SUCCESS googleSearch:", resp.text[:20])
except Exception as e:
    print("ERROR googleSearch:", str(e))

try:
    resp = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents="Hello",
        config={"tools": [{"google_search": {}}]}
    )
    print("SUCCESS google_search:", resp.text[:20])
except Exception as e:
    print("ERROR google_search:", str(e))
