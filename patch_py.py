import re

with open("tools/start_screen.py", "r") as f:
    content = f.read()

# Add StartScreenColors array generation
new_emit = """    for name in ("PF0L", "PF1L", "PF2L", "PF0R", "PF1R", "PF2R"):
        lines.append(f"StartScreen{name}:")
        vals = tables[name]
        for i in range(0, len(vals), 16):
            chunk = vals[i : i + 16]
            lines.append("    .byte " + ",".join(f"${b:02X}" for b in chunk))
        lines.append("")

    lines.append("StartScreenColors:")
    colors = [0x28 if 4 <= y <= 48 else 0x0E for y in range(ROWS)]
    for i in range(0, len(colors), 16):
        chunk = colors[i : i + 16]
        lines.append("    .byte " + ",".join(f"${b:02X}" for b in chunk))
    lines.append("")"""

content = re.sub(
    r'    for name in \("PF0L", "PF1L", "PF2L", "PF0R", "PF1R", "PF2R"\):.*?lines\.append\(""\)',
    new_emit,
    content,
    flags=re.DOTALL
)

with open("tools/start_screen.py", "w") as f:
    f.write(content)
