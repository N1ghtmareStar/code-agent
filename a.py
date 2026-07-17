# a.py - FastAPI 入口（同时支持 HTTP 和 WebSocket）
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
import json
import os
import asyncio
from agent import run_agent

app = FastAPI()

# ========== HTTP 路由 ==========
@app.get("/")
async def hello():
    return {"message": "QQ Bot Agent is running! (WebSocket service is active)"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    """HTTP 上报备用路由"""
    try:
        data = await request.json()
        print(f"Received webhook: {data}")
        if data and data.get("post_type") == "message":
            user_input = data.get("message", "")
            if isinstance(user_input, list):
                text_parts = []
                for seg in user_input:
                    if seg.get("type") == "text":
                        text_parts.append(seg.get("data", {}).get("text", ""))
                user_input = "".join(text_parts)
            reply = run_agent(user_input) if user_input else "请说点什么"
            return [{"type": "text", "data": {"text": reply}}]
        return [], 200
    except Exception as e:
        print(f"❌ webhook 处理失败: {e}")
        return [], 200

# ========== WebSocket 路由 ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔗 WebSocket 客户端已连接")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📨 收到 WebSocket 消息：{data[:200]}...")
            try:
                msg = json.loads(data)
                # 处理消息事件
                if msg.get("post_type") == "message":
                    user_input = msg.get("message", "")
                    if isinstance(user_input, list):
                        text_parts = []
                        for seg in user_input:
                            if seg.get("type") == "text":
                                text_parts.append(seg.get("data", {}).get("text", ""))
                        user_input = "".join(text_parts)
                    reply = run_agent(user_input) if user_input else "请说点什么"
                    
                    # 🔥 返回 OneBot 标准 API 响应格式
                    response_data = {
                        "status": "ok",
                        "retcode": 0,
                        "data": {
                            "message": reply
                        },
                        "echo": msg.get("echo")  # 如果有 echo 字段，原样返回
                    }
                    await websocket.send_text(json.dumps(response_data))
                    print(f"✅ 已回复：{reply[:50]}...")
                else:
                    # 对非消息事件（如心跳、生命周期），返回空响应保持连接
                    await websocket.send_text(json.dumps({"status": "ok"}))
                    print(f"ℹ️ 已响应非消息事件")
            except json.JSONDecodeError:
                print("⚠️ 无法解析 JSON")
                await websocket.send_text(json.dumps({
                    "status": "failed",
                    "retcode": 100,
                    "data": None,
                    "message": "JSON 解析失败"
                }))
    except WebSocketDisconnect:
        print("🔌 WebSocket 客户端已断开")
    except Exception as e:
        print(f"❌ WebSocket 异常：{e}")