"""Directly test what happens when we serve / via the gateway logic"""
import os

DIST = r'D:\向海容的知识库\wiki\wiki\记忆宫殿\L5孵化室\产品开发\战略合作\链客宝\linkbao\frontend\dist'

# Simulate _serve_static for path "/"
clean_path = "/".split("?")[0]
file_path = os.path.normpath(os.path.join(DIST, clean_path.lstrip("/")))
print(f"clean_path: '{clean_path}'")
print(f"Stripped: '{clean_path.lstrip('/')}'")
print(f"file_path: '{file_path}'")
print(f"isfile: {os.path.isfile(file_path)}")

# Simulate SPA fallback
index_path = os.path.join(DIST, "index.html")
print(f"index_path: '{index_path}'")
print(f"index exists: {os.path.isfile(index_path)}")
if os.path.isfile(index_path):
    with open(index_path, "rb") as f:
        content = f.read()
    print(f"index.html size: {len(content)} bytes")
    print(f"content: {content[:200]}")
