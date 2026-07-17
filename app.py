from flask import Flask
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

# 注意：/webhook 路由已迁移到 a.py，这里不再重复定义

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