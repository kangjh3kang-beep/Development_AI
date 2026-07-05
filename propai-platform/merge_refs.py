import re

with open("services/deliberation-review/apps/api/app/services/explain/legal_refs.py", "r") as f:
    text = f.read()

refs_match = re.search(r'_REFS: dict\[str, LegalRef\] = \{(.*?)\n\}', text, re.DOTALL)
if not refs_match:
    print("Could not find _REFS")
    exit(1)

refs_str = refs_match.group(1)

# Extract each LegalRef
ref_pattern = r'"([^"]+)": LegalRef\(\s*ref_id="[^"]+", law="([^"]+)", article="([^"]*)",\s*summary=(?:"([^"]+)"|\(\s*"([^"]+)"\s*"([^"]+)"\s*\)),(?:.*?)source=(.*?)\)'

new_refs = []
for match in re.finditer(r'"([^"]+)": LegalRef\((.*?)\)', refs_str, re.DOTALL):
    key = match.group(1)
    props = match.group(2)
    
    law_m = re.search(r'law="([^"]+)"', props)
    law = law_m.group(1) if law_m else ""
    
    art_m = re.search(r'article="([^"]+)"', props)
    art = art_m.group(1) if art_m else "None"
    if art != "None":
        art = f'"{art}"'
    
    sum_m = re.search(r'summary="([^"]+)"', props)
    if sum_m:
        summary = sum_m.group(1)
    else:
        # try multiline summary
        sum_m2 = re.search(r'summary=\(\s*"([^"]+)"\s*"([^"]+)"', props)
        if sum_m2:
            summary = sum_m2.group(1) + sum_m2.group(2)
        else:
            summary = ""
            
    new_refs.append(f'    "{key}": _ref("{law}", {art}, "{summary}"),')

# Now read legal_reference_registry.py
with open("apps/api/app/services/legal/legal_reference_registry.py", "r") as f:
    registry_text = f.read()

# insert before _ALIASES: dict[str, str] = {
# actually insert inside LEGAL_REFERENCES

lines = registry_text.split('\n')
insert_idx = -1
for i, line in enumerate(lines):
    if line.strip() == "}":
        # check if it's the end of LEGAL_REFERENCES
        if i > 100 and "LEGAL_REFERENCES" in "".join(lines[100:i]):
            insert_idx = i
            break

if insert_idx != -1:
    lines.insert(insert_idx, "    # ── 심의 엔진(deliberation) 흡수 ──")
    for r in new_refs:
        lines.insert(insert_idx + 1, r)
        insert_idx += 1

with open("apps/api/app/services/legal/legal_reference_registry.py", "w") as f:
    f.write("\n".join(lines))

print(f"Injected {len(new_refs)} refs into LEGAL_REFERENCES")
