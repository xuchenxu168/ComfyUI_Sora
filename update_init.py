import os

# Read current __init__.py
with open('__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import for storyboard_character if not exists
import_line = '''
try:
    from .storyboard_character import NODE_CLASS_MAPPINGS as STORYBOARD_CHAR_CLASS, NODE_DISPLAY_NAME_MAPPINGS as STORYBOARD_CHAR_NAMES
    NODE_CLASS_MAPPINGS.update(STORYBOARD_CHAR_CLASS)
    NODE_DISPLAY_NAME_MAPPINGS.update(STORYBOARD_CHAR_NAMES)
    print('[ComfyUI_Sora] StoryboardCharacter node loaded')
except Exception as e:
    print(f'[ComfyUI_Sora] Failed to load StoryboardCharacter: {e}')
'''

if 'storyboard_character' not in content:
    # Find the last NODE_DISPLAY_NAME_MAPPINGS.update line and add after it
    lines = content.split('\n')
    insert_pos = len(lines) - 1
    for i, line in enumerate(lines):
        if 'NODE_DISPLAY_NAME_MAPPINGS.update' in line:
            insert_pos = i + 1
    
    # Insert import
    lines.insert(insert_pos, import_line)
    new_content = '\n'.join(lines)
    
    with open('__init__.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Updated __init__.py successfully!')
else:
    print('storyboard_character already in __init__.py')
