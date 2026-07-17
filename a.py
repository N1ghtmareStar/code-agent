# a.py - Wasmer 入口文件
from app import app
from flask import request
import json

@app.route('/webhook', methods=['POST'])
def webhook():
    # 打印请求信息
    print(f"📨 Request method: {request.method}")
    print(f"📨 Request headers: {dict(request.headers)}")
    raw_data = request.get_data()
    print(f"📨 Raw data (bytes): {raw_data}")
    print(f"📨 Raw data (decoded): {raw_data.decode('utf-8', errors='ignore')}")

    # 尝试解析 JSON
    try:
        data = json.loads(raw_data) if raw_data else None
        print(f"✅ Parsed JSON: {data}")
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 解析失败: {e}")
        data = None

    # 处理消息...
    # 返回标准响应
    return [{"type": "text", "data": {"text": "收到消息"}}], 200