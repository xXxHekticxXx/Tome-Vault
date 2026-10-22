"""
Runs on GitHub during each app build:
  * writes app/www/config.json (version, repo for update checks, optional default vault address)
  * downloads the free SRD 5.2.1 (CC-BY-4.0) and builds its cover and search index,
    so the app opens with a rulebook on the shelf even before it connects.
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WWW = os.path.join(ROOT, "app", "www")
SRD_URL = "https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf"


def write_config():
    cfg = {
        "version": os.environ.get("TV_VERSION", "dev"),
        "repo": os.environ.get("TV_REPO", ""),
        "defaultServer": (os.environ.get("TV_DEFAULT_SERVER") or "").strip().rstrip("/"),
    }
    with open(os.path.join(WWW, "config.json"), "w") as f:
        json.dump(cfg, f)
    print("config.json:", cfg)


def clean(text):
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def build_srd():
    out = os.path.join(WWW, "srd")
    os.makedirs(out, exist_ok=True)
    pdf_path = os.path.join(out, "book.pdf")
    try:
        req = urllib.request.Request(SRD_URL, headers={"User-Agent": "TomeVaultBuild/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(pdf_path, "wb") as f:
            f.write(r.read())
    except Exception as e:  # the app still works without it
        print("SRD download failed, building without the built-in rules:", e)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return
    import pymupdf as fitz
    doc = fitz.open(pdf_path)
    first = doc[0]
    zoom = 520 / first.rect.width
    first.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(os.path.join(out, "cover.jpg"), jpg_quality=85)
    pages = [clean(p.get_text()) for p in doc]
    with open(os.path.join(out, "text.json"), "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    meta = {"title": "System Reference Document 5.2.1", "pages": len(pages),
            "size": os.path.getsize(pdf_path), "version": 521}
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f)
    print("Built-in SRD ready:", meta)


if __name__ == "__main__":
    if not os.path.isdir(WWW):
        sys.exit("Run scripts/copy-web.js first")
    write_config()
    build_srd()
