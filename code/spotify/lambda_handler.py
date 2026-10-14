import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from spoty import get_access_token, get_top_tracks, search_tracks


def lambda_handler(event, context):
    action = event.get("action", "top_tracks")
    access_token = get_access_token()

    if action == "top_tracks":
        limit = event.get("limit", 10)
        time_range = event.get("time_range", "medium_term")
        result = get_top_tracks(access_token, limit=limit, time_range=time_range)
    elif action == "search":
        query = event.get("query", "")
        result = search_tracks(access_token, query)
    else:
        return {"statusCode": 400, "body": json.dumps({"error": f"Unknown action: {action}"})}

    return {"statusCode": 200, "body": json.dumps(result, ensure_ascii=False)}
