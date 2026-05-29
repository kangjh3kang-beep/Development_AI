#!/usr/bin/env python3
"""Safe apiClient cleanup — import removal + queryFn mock replacement.

Strategy:
1. Remove import lines containing 'apiClient' or 'ApiClientError'
2. Replace simple single-line apiClient.get<T>("/path") with ({} as T)
3. Replace single-line apiClient.post<T>("/path", body) with ({} as T)
4. For multi-line apiClient calls, replace from 'apiClient.' to closing ')' with ({} as T)
5. Simplify extractErrorMessage if it references ApiClientError
"""

import re
import sys
from pathlib import Path

def process_file(filepath: str) -> tuple[bool, list[str]]:
    """Process a single file. Returns (changed, messages)."""
    path = Path(filepath)
    original = path.read_text(encoding="utf-8")
    lines = original.split("\n")
    changes = []
    
    # Phase 1: Remove apiClient/ApiClientError imports
    new_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import") and ("apiClient" in stripped or "ApiClientError" in stripped):
            # Check if this is the only import from api-client
            if "api-client" in stripped:
                changes.append(f"  Removed import at line {i+1}")
                continue
        new_lines.append(line)
    
    lines = new_lines
    text = "\n".join(lines)
    
    # Phase 2: Replace single-line apiClient.get<Type>("...") 
    # Pattern: apiClient.get<SomeType>("/some/path")
    pattern_get = r'apiClient\.get<([^>]+)>\([^)]*\)'
    def replace_get(m):
        type_name = m.group(1)
        changes.append(f"  Replaced apiClient.get<{type_name}>")
        return f'({{}} as {type_name})'
    text = re.sub(pattern_get, replace_get, text)
    
    # Phase 3: Replace single-line apiClient.post<Type>("...", ...) 
    # This is tricky for multi-line, so only match single-line simple cases
    pattern_post_simple = r'apiClient\.post<([^>]+)>\([^)]*\)'
    def replace_post(m):
        type_name = m.group(1)
        changes.append(f"  Replaced apiClient.post<{type_name}>")
        return f'({{}} as {type_name})'
    text = re.sub(pattern_post_simple, replace_post, text)

    # Phase 4: Replace apiClient.put<Type>
    pattern_put = r'apiClient\.put<([^>]+)>\([^)]*\)'
    def replace_put(m):
        type_name = m.group(1)
        changes.append(f"  Replaced apiClient.put<{type_name}>")
        return f'({{}} as {type_name})'
    text = re.sub(pattern_put, replace_put, text)
    
    # Phase 5: Handle multi-line apiClient calls
    # Find remaining apiClient references and handle them
    lines = text.split("\n")
    result_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for multi-line apiClient call start
        if "apiClient." in line and "import" not in line:
            # Extract the type from apiClient.method<Type>(
            m = re.search(r'apiClient\.\w+<([^>]+)>\(', line)
            if m:
                type_name = m.group(1)
                # Find the full expression by counting parens
                paren_depth = 0
                collected = ""
                j = i
                started = False
                while j < len(lines):
                    for ch in lines[j]:
                        if ch == '(':
                            paren_depth += 1
                            started = True
                        elif ch == ')':
                            paren_depth -= 1
                        collected += ch
                        if started and paren_depth == 0:
                            break
                    if started and paren_depth == 0:
                        break
                    j += 1
                
                # Replace the apiClient.xxx<T>(...) call with ({} as T)
                before_api = line[:line.index("apiClient")]
                # Find what comes after the closing paren on line j
                if j < len(lines):
                    after_match = lines[j][lines[j].rindex(')') + 1:] if ')' in lines[j] else ""
                else:
                    after_match = ""
                
                replacement = f"{before_api}({{}} as {type_name}){after_match}"
                result_lines.append(replacement)
                changes.append(f"  Replaced multi-line apiClient call at line {i+1}-{j+1}")
                i = j + 1
                continue
            else:
                # apiClient without type param (rare) - just comment it out
                pass
        
        # Phase 6: Remove ApiClientError references in extractErrorMessage
        if "ApiClientError" in line and "import" not in line:
            # Skip lines that are part of ApiClientError handling
            if "instanceof ApiClientError" in line:
                # Skip the if block
                brace_depth = 0
                j = i
                while j < len(lines):
                    for ch in lines[j]:
                        if ch == '{':
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth -= 1
                    if brace_depth <= 0 and j > i:
                        break
                    j += 1
                changes.append(f"  Removed ApiClientError block at lines {i+1}-{j+1}")
                i = j + 1
                continue
        
        result_lines.append(line)
        i += 1
    
    final_text = "\n".join(result_lines)
    
    if final_text != original:
        path.write_text(final_text, encoding="utf-8")
        return True, changes
    return False, []


def main():
    base = Path("/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/components")
    files = sorted(base.rglob("*.tsx"))
    
    total_changed = 0
    total_errors = 0
    
    for f in files:
        rel = f.relative_to(base)
        # Skip auth files
        if "Auth" in f.name or "Kakao" in f.name:
            continue
        # Only process files that contain apiClient
        content = f.read_text(encoding="utf-8")
        if "apiClient" not in content:
            continue
        
        try:
            changed, messages = process_file(str(f))
            if changed:
                total_changed += 1
                print(f"✅ {rel}")
                for msg in messages:
                    print(msg)
            else:
                print(f"⏭️ {rel} (no changes needed)")
        except Exception as e:
            total_errors += 1
            print(f"❌ {rel}: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Files changed: {total_changed}")
    print(f"Errors: {total_errors}")
    
    # Verify no apiClient remains
    remaining = 0
    for f in files:
        if "Auth" in f.name or "Kakao" in f.name:
            continue
        content = f.read_text(encoding="utf-8")
        if "apiClient" in content:
            remaining += 1
            print(f"⚠️ apiClient still in: {f.relative_to(base)}")
    
    print(f"Files still containing apiClient: {remaining}")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
