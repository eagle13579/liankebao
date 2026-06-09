"""Debug gateway response for /"""

import urllib.request
import os

DIST = r"D:\向海容的知识库\wiki\wiki\记忆宫殿\L5孵化室\产品开发\战略合作\链客宝AI\linkbao\frontend\dist"
index_path = os.path.join(DIST, "index.html")
print(f"index.html exists: {os.path.isfile(index_path)}")
print(
    f"file size: {os.path.getsize(index_path) if os.path.isfile(index_path) else 'N/A'}"
)

try:
    r = urllib.request.urlopen("http://localhost:5136/", timeout=5)
    print(f"Status: {r.status}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    body = r.read()
    print(f"Body length: {len(body)} bytes")
    print(f"Body preview: {body[:200]}")
except Exception as e:
    print(f"Error: {e}")
