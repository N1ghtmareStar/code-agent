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

@app.post("/webhook")
async def webhook(request: Request):
    """HTTP 上报备用路由（保留但暂不启用）"""
    try:
        data = await request.json()
        print(f"Received webhook: {data}")
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ webhook 处理失败: {e}")
        return {"status": "error"}

# ========== WebSocket 路由 ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔗 WebSocket 客户端已连接")
    try:
        while True:
            # 接收 NapCat 发送的消息
            data = await websocket.receive_text()
            print(f"📨 收到 WebSocket 消息：{data[:200]}...")
            
            try:
                msg = json.loads(data)
                
                # 处理消息事件
                if msg.get("post_type") == "message":
                    # 提取用户输入
                    user_input = msg.get("message", "")
                    if isinstance(user_input, list):
                        text_parts = []
                        for seg in user_input:
                            if seg.get("type") == "text":
                                text_parts.append(seg.get("data", {}).get("text", ""))
                        user_input = "".join(text_parts)
                    
                    # 调用 Agent 获取回复
                    reply = run_agent(user_input) if user_input else "请说点什么"
                    
                    # 获取群号和用户ID（用于 @）
                    group_id = msg.get("group_id")
                    user_id = msg.get("user_id")
                    
                    if group_id and user_id:
                        # 构造 send_msg API 请求（OneBot 标准）
                        api_request = {
                            "action": "send_msg",
                            "params": {
                                "message_type": "group",
                                "group_id": group_id,
                                "message": [
                                    {"type": "at", "data": {"qq": user_id}},
                                    {"type": "text", "data": {"text": " " + reply}}
                                ]
                            },
                            "echo": "reply_" + str(msg.get("message_id", ""))
                        }
                        # 通过 WebSocket 发送 API 请求给 NapCat
                        await websocket.send_text(json.dumps(api_request))
                        print(f"✅ 已发送 API 请求：{api_request}")
                    else:
                        print("⚠️ 缺少 group_id 或 user_id，无法回复")
                
                else:
                    # 非消息事件（心跳、生命周期等），返回空响应保持连接
                    await websocket.send_text(json.dumps({"status": "ok"}))
                    print(f"ℹ️ 已响应非消息事件：{msg.get('meta_event_type', 'unknown')}")
            
            except json.JSONDecodeError:
                print("⚠️ 无法解析 JSON")
                # 发送错误响应
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
        try:
            await websocket.send_text(json.dumps({
                "status": "failed",
                "retcode": 500,
                "data": None,
                "message": f"服务器错误：{str(e)}"
            }))
        except:
            pass