# a.py - Wasmer 入口文件
from app import app
from flask import request, jsonify
import traceback

# 导入 run_agent
try:
    from agent import run_agent
    print("✅ 成功导入 run_agent")
except Exception as e:
    print(f"❌ 导入 run_agent 失败: {e}")
    run_agent = None

@app.route('/webhook', methods=['POST'])
def webhook():
    """接收 NapCat 的 HTTP 上报消息，返回 OneBot 标准响应"""
    try:
        data = request.get_json()
        print(f"✅ Received webhook: {data}")
        
        # 仅处理消息事件
        if data and data.get('post_type') == 'message':
            # 提取消息内容
            message = data.get('message', '')
            if isinstance(message, list):
                text_parts = []
                for seg in message:
                    if seg.get('type') == 'text':
                        text_parts.append(seg.get('data', {}).get('text', ''))
                message = ''.join(text_parts)
            
            print(f"📩 提取的消息: {message}")
            
            # 检查 run_agent 是否可用
            if run_agent is None:
                return [{"type": "text", "data": {"text": "❌ Agent 未初始化"}}], 200
            
            # 调用 Agent 处理
            try:
                reply = run_agent(message) if message else "请说点什么"
                print(f"🤖 Agent 回复: {reply}")
            except Exception as e:
                print(f"❌ run_agent 执行失败: {e}")
                traceback.print_exc()
                reply = f"❌ 处理出错: {str(e)}"
            
            # 返回 OneBot 标准 array 格式
            return [{"type": "text", "data": {"text": reply}}], 200
        
        # 非消息事件，返回空数组（不回复）
        return [], 200
        
    except Exception as e:
        print(f"❌ webhook 处理失败: {e}")
        traceback.print_exc()
        return [{"type": "text", "data": {"text": f"❌ 服务错误: {str(e)}"}}], 200