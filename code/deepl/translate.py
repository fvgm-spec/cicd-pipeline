#!/usr/bin/env python3
"""Usage: python3 translate.py "text" [target_lang] [source_lang]
Auto-detects source language. Defaults: EN→ES, other→EN-US."""
import sys, os, deepl
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

args = sys.argv[1:]
if not args:
    sys.exit("Usage: translate.py <text> [target_lang] [source_lang]")

text   = args[0]
source = args[2] if len(args) > 2 else None
translator = deepl.Translator(os.environ["DEEPL_API_KEY"])

if len(args) > 1:
    target = args[1]
else:
    # detect source first to pick a sensible default target
    detected = translator.translate_text(text, target_lang="ES", source_lang=source).detected_source_lang
    target = "ES" if detected.startswith("EN") else "EN-US"
    source = detected

result = translator.translate_text(text, target_lang=target, source_lang=source)
print(f"[{result.detected_source_lang} → {target}] {result.text}")
