# a.py - Wasmer 入口文件
from app import app
from flask import request
from agent import run_agent
import json

@app.route('/webhook', methods=['POST'])
def webhook():
    """接收 NapCat 的 HTTP 上报消息"""
    try:
        # 1. 先获取原始请求体（bytes）
        raw_data = request.get_data()
        print(f"📨 Raw data received: {raw_data}")
        print(f"📨 Raw data decoded: {raw_data.decode('utf-8', errors='ignore')}")
        
        # 2. 尝试解析 JSON
        try:
            data = json.loads(raw_data)
            print(f"✅ Parsed JSON: {data}")
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON 解析失败: {e}")
            # 如果解析失败，可能是 NapCat 发送了纯文本
            # 将原始数据作为消息内容
            text_content = raw_data.decode('utf-8', errors='ignore').strip()
            if text_content:
                # 模拟消息结构
                data = {
                    "post_type": "message",
                    "message": text_content,
                    "user_id": 0
                }
            else:
                return [], 200
        
        # 3. 处理消息
        if data and data.get('post_type') == 'message':
            message = data.get('message', '')
            if isinstance(message, list):
                text_parts = []
                for seg in message:
                    if seg.get('type') == 'text':
                        text_parts.append(seg.get('data', {}).get('text', ''))
                message = ''.join(text_parts)
            
            print(f"📩 提取的消息: {message}")
            
            if not message:
                return [], 200
            
            # 调用 Agent 处理
            try:
                reply = run_agent(message)
                print(f"🤖 Agent 回复: {reply}")
            except Exception as e:
                print(f"❌ run_agent 执行失败: {e}")
                import traceback
                traceback.print_exc()
                reply = f"❌ 处理出错: {str(e)}"
            
            # 返回 OneBot 标准格式
            return [{"type": "text", "data": {"text": reply}}], 200
        
        return [], 200
        
    except Exception as e:
        print(f"❌ webhook 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return [], 200