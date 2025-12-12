# Fix the __init__.py file
with open('__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the malformed import block
lines = content.split('\n')
new_lines = []
skip_until_except_done = False
for i, line in enumerate(lines):
    # Skip the malformed storyboard_character import section
    if 'storyboard_character' in line.lower() and 'try:' not in line.lower():
        continue
    if 'STORYBOARD_CHAR' in line:
        continue
    new_lines.append(line)

# Join and find where to add proper import
content = '\n'.join(new_lines)

# Add the import at the end, before __all__ if exists
import_code = '''
# Storyboard Character node
try:
    from .storyboard_character import NODE_CLASS_MAPPINGS as STORYBOARD_CHAR_CLASS
    from .storyboard_character import NODE_DISPLAY_NAME_MAPPINGS as STORYBOARD_CHAR_NAMES
    NODE_CLASS_MAPPINGS.update(STORYBOARD_CHAR_CLASS)
    NODE_DISPLAY_NAME_MAPPINGS.update(STORYBOARD_CHAR_NAMES)
    print('[ComfyUI_Sora] StoryboardCharacter node loaded')
except Exception as e:
    print(f'[ComfyUI_Sora] Failed to load StoryboardCharacter: {e}')
'''

# Find the last line that contains NODE_DISPLAY_NAME_MAPPINGS.update or the end of try/except blocks
if 'storyboard_character' not in content.lower():
    # Find a good insertion point - after the last except block
    lines = content.split('\n')
    insert_pos = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if \"__all__\" in lines[i]:
            insert_pos = i
            break
        if 'NODE_DISPLAY_NAME_MAPPINGS.update' in lines[i]:
            insert_pos = i + 1
            break
    
    lines.insert(insert_pos, import_code)
    content = '\n'.join(lines)

with open('__init__.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed __init__.py!')
