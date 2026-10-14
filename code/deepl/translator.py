#!/usr/bin/env python3
"""
DeepL Translator Agent — sample project
Supports: text translation, file translation, language detection, glossary management
"""
import os
import deepl
from dotenv import load_dotenv

load_dotenv()
translator = deepl.Translator(os.environ["DEEPL_API_KEY"])


def translate(text: str, target: str, source: str = None) -> str:
    result = translator.translate_text(text, target_lang=target, source_lang=source)
    return result.text


def detect_and_translate(text: str, target: str) -> dict:
    result = translator.translate_text(text, target_lang=target)
    return {"detected_source": result.detected_source_lang, "translation": result.text}


def translate_file(input_path: str, output_path: str, target: str, source: str = None):
    translator.translate_document_from_filepath(
        input_path, output_path, target_lang=target, source_lang=source
    )
    print(f"Translated file saved to {output_path}")


def list_languages():
    print("Source languages:")
    for lang in translator.get_source_languages():
        print(f"  {lang.code}: {lang.name}")
    print("\nTarget languages:")
    for lang in translator.get_target_languages():
        print(f"  {lang.code}: {lang.name}")


def usage():
    u = translator.get_usage()
    print(f"Characters used: {u.character.count:,} / {u.character.limit:,}")


if __name__ == "__main__":
    # Sample usage
    usage()
    print()

    # Basic translation
    print(translate("Hello, how are you?", target="ES"))
    print(translate("Hola, ¿cómo estás?", target="EN-US"))

    # Auto-detect source
    result = detect_and_translate("Bonjour le monde", target="EN-US")
    print(f"Detected: {result['detected_source']} → {result['translation']}")
