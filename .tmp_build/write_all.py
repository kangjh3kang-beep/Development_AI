import os

BASE = "/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/tests/integration"

files_to_read = {
    "test_full_pipeline.py": "/home/kangjh3kang/My_Projects/Development_AI/.tmp_build/f1.txt",
    "test_lifecycle_flow.py": "/home/kangjh3kang/My_Projects/Development_AI/.tmp_build/f2.txt",
    "test_esg_flow.py": "/home/kangjh3kang/My_Projects/Development_AI/.tmp_build/f3.txt",
}

for target_name, source in files_to_read.items():
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
        target = os.path.join(BASE, target_name)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Written {len(content)} chars to {target}")
    else:
        print(f"Source not found: {source}")
