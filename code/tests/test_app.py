import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import lambda_handler


def test_lambda_handler():
    event = {"key": "value"}
    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "message" in body
