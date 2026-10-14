import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from espn_results import fetch_html, extract_state, get_scoreboard, normalize_date


def lambda_handler(event, context):
    date = normalize_date(event.get("date"))
    html = fetch_html(date)
    state = extract_state(html)
    scoreboard = get_scoreboard(state)
    return {"statusCode": 200, "body": json.dumps(scoreboard, ensure_ascii=False)}
