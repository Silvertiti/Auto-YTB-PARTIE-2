import requests
import os
from dotenv import load_dotenv
import urllib3

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_KEY = os.getenv("LATE_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

BASE_URLS = [
    "https://getlate.dev/api/v1/posts",
    "https://getlate.dev/api/v1/posts/",
    "https://getlate.dev/api/posts",
    "https://api.getlate.dev/v1/posts",
    "https://getlate.dev/v1/posts"
]

def test_endpoint(url):
    print(f"\n--- Testing {url} ---")
    
    # 1. Try GET (List posts) - Should be allowed if endpoint exists
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=5)
        print(f"GET Status: {resp.status_code}")
    except Exception as e:
        print(f"GET Error: {e}")

    # 2. Try OPTIONS (Check allowed methods)
    try:
        resp = requests.options(url, headers=HEADERS, verify=False, timeout=5)
        print(f"OPTIONS Status: {resp.status_code}")
        print(f"Allow Header: {resp.headers.get('Allow', 'None')}")
    except Exception as e:
        print(f"OPTIONS Error: {e}")

    # 3. Try POST (Create post - dummy data)
    try:
        # Minimal payload that might fail validation but hopefully not 404/405
        data = {"content": "Test"} 
        resp = requests.post(url, headers=HEADERS, json=data, verify=False, timeout=5)
        print(f"POST Status: {resp.status_code}")
        # print(f"Response: {resp.text[:100]}...")
    except Exception as e:
        print(f"POST Error: {e}")

print("Starting Late API Debug Probe...")
for url in BASE_URLS:
    test_endpoint(url)
