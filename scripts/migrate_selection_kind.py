import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "src"

SELECTION_FILES = list(ROOT.rglob("*.ts")) + list(ROOT.rglob("*.tsx"))

IMPORT_LINE = "import { isClipSelection } from '@/lib/selection'\n"

for path in SELECTION_FILES:
    if path.name == "selection.ts":
        continue
    text = path.read_text(encoding="utf-8")
    original = text

    text = text.replace("| { kind: 'element';", "| { kind: 'clip';")
    text = text.replace("kind: 'element',", "kind: 'clip',")
    text = text.replace("effectScope: 'element'", "effectScope: 'clip'")
    text = re.sub(
        r"selection\?\.kind === 'element'",
        "isClipSelection(selection)",
        text,
    )
    text = re.sub(
        r"sel\?\.kind !== 'element'",
        "!isClipSelection(sel)",
        text,
    )
    text = re.sub(
        r"selection\?\.kind !== 'element'",
        "!isClipSelection(selection)",
        text,
    )
    text = re.sub(
        r"s\.selection\?\.kind === 'element'",
        "isClipSelection(s.selection)",
        text,
    )

    if text != original:
        if "isClipSelection" in text and IMPORT_LINE.strip() not in text:
            if text.startswith("import "):
                first_nl = text.find("\n") + 1
                text = text[:first_nl] + IMPORT_LINE + text[first_nl:]
            else:
                text = IMPORT_LINE + text
        path.write_text(text, encoding="utf-8")
        print(f"updated {path.relative_to(ROOT.parent.parent)}")
