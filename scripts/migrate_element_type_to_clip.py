from pathlib import Path

root = Path(__file__).resolve().parents[1] / "web" / "src"
for path in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
    if path.name == "projectStore.ts":
        continue
    t = path.read_text(encoding="utf-8")
    o = t
    t = t.replace("type Element,", "type Clip,")
    t = t.replace("type Element }", "type Clip }")
    t = t.replace("Element as TimelineElement", "Clip as TimelineClip")
    t = t.replace("Element[]", "Clip[]")
    if t != o:
        path.write_text(t, encoding="utf-8")
        print(path.relative_to(root.parent.parent))
