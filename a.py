# a.py
from app import app
from flask import request

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print(f"Received webhook: {data}")
    return {"status": "ok"}