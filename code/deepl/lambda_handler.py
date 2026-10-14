import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from translator import translate, detect_and_translate


def lambda_handler(event, context):
    text = event.get("text", "")
    target = event.get("target_lang", "EN-US")
    source = event.get("source_lang")
    if source:
        result = translate(text, target, source)
    else:
        result = detect_and_translate(text, target)
    return {"statusCode": 200, "body": json.dumps({"translation": result}, ensure_ascii=False)}
