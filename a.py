# a.py - Wasmer 入口文件
from app import app
from flask import request
from agent import run_agent

@app.route('/webhook', methods=['POST'])
def webhook():
    """接收 NapCat 的 HTTP 上报消息，返回 OneBot 标准响应"""
    data = request.get_json()
    print(f"Received webhook: {data}")
    
    # 仅处理消息事件
    if data and data.get('post_type') == 'message':
        # 提取消息内容（根据不同消息类型，可能为数组或字符串）
        message = data.get('message', '')
        # 如果 message 是数组，提取纯文本
        if isinstance(message, list):
            text_parts = []
            for seg in message:
                if seg.get('type') == 'text':
                    text_parts.append(seg.get('data', {}).get('text', ''))
            message = ''.join(text_parts)
        
        # 调用 Agent 处理
        reply = run_agent(message) if message else "请说点什么"
        
        # 返回 OneBot 标准 array 格式
        return [
            {"type": "text", "data": {"text": reply}}
        ]
    
    # 非消息事件，返回空数组（不回复）
    return [], 200