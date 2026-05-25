# -*- coding: utf-8 -*-
import os, json, base64

# Git Bash maps /home to C:\Program Files\Git\home
BASE = r"C:\Program Files\Git\home\kangjh3kang\My_Projects\Development_AI\propai-platform\apps\api"
DATA_FILE = r"\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI\propai-platform\_phase8_data_1.json"

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

NL = chr(10)
count = 0
for rel_path, b64data in data.items():
    full_path = os.path.join(BASE, rel_path.replace("/", os.sep))
    d = os.path.dirname(full_path)
    os.makedirs(d, exist_ok=True)
    file_content = base64.b64decode(b64data).decode("utf-8")
    with open(full_path, "w", encoding="utf-8", newline=NL) as f:
        f.write(file_content)
    print("[OK] Created:", rel_path)
    count += 1

print()
print("=== Total files created:", count, "===")
