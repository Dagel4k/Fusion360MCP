import urllib.request
import sys

url = "http://127.0.0.1:3000/sse"
print(f"Diagnostics: Opening {url}")
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        for i in range(20):
            line = response.readline()
            if not line:
                print("EOF reached")
                break
            print(f"Line {i}: {line.decode('utf-8').strip()}")
except Exception as e:
    print(f"Error: {e}")
