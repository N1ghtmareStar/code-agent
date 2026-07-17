from flask import Flask, request
import threading
import subprocess
import os

app = Flask(__name__)

@app.route('/')
def hello():
    return "QQ Bot Agent is running! (WebSocket service is active)"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/test')
def test():
    key = os.getenv("VOLC_ACCESS_KEY")
    if key:
        return f"VOLC_ACCESS_KEY is set: {key[:10]}... (truncated)"
    else:
        return "VOLC_ACCESS_KEY is NOT set"

# ========== 新增：接收 NapCat HTTP 上报 ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    """接收 NapCat 的 HTTP 上报消息"""
    data = request.get_json()
    print(f"Received webhook: {data}")
    
    # 可以在这里调用 run_agent 处理消息，并返回回复
    # from agent import run_agent
    # reply = run_agent(...)
    # return {"reply": reply}
    
    return {"status": "ok"}

def run_bot():
    # 启动 QQ 机器人 WebSocket 服务
    subprocess.run(["python", "qq_bot_server.py"])

if __name__ == '__main__':
    # 在后台线程中运行机器人服务
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    # 启动 Flask 服务，监听 0.0.0.0 和 Wasmer 分配的端口
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)