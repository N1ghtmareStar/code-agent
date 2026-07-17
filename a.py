# a.py - FastAPI 入口（同时支持 HTTP 和 WebSocket）
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
import json
import os
from agent import run_agent

app = FastAPI()

# ========== HTTP 路由 ==========
@app.get("/")
async def hello():
    return {"message": "QQ Bot Agent is running! (WebSocket service is active)"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# ========== 核心：HTTP 上报路由 ==========
@app.post("/webhook")
async def webhook(request: Request):
    """接收 NapCat 的 HTTP 上报消息，调用 run_agent 并返回回复"""
    try:
        # 获取原始 JSON 数据
        data = await request.json()
        print(f"✅ Received webhook: {data}")

        # 只处理消息事件
        if data and data.get("post_type") == "message":
            # 提取用户输入（兼容 message 为字符串或数组）
            user_input = data.get("message", "")
            if isinstance(user_input, list):
                text_parts = []
                for seg in user_input:
                    if seg.get("type") == "text":
                        text_parts.append(seg.get("data", {}).get("text", ""))
                user_input = "".join(text_parts)
            
            print(f"📩 用户输入: {user_input}")

            # 调用 Agent 处理
            try:
                reply = run_agent(user_input) if user_input else "请说点什么"
                print(f"🤖 Agent 回复: {reply[:100]}...")
                # 返回 OneBot 标准格式（数组）
                return [{"type": "text", "data": {"text": reply}}]
            except Exception as e:
                print(f"❌ run_agent 执行失败: {e}")
                import traceback
                traceback.print_exc()
                return [{"type": "text", "data": {"text": f"❌ 处理出错: {str(e)}"}}]
        
        # 非消息事件，返回空响应
        return [], 200

    except Exception as e:
        print(f"❌ webhook 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return [], 500

# ========== WebSocket 路由（备用，目前未使用） ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔗 WebSocket 客户端已连接")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📨 收到 WebSocket 消息：{data[:200]}...")
            # 简单回应，避免连接断开
            await websocket.send_text(json.dumps({"status": "ok"}))
    except WebSocketDisconnect:
        print("🔌 WebSocket 客户端已断开")
    except Exception as e:
        print(f"❌ WebSocket 异常：{e}")