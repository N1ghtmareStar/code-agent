from fastapi import FastAPI, Request
import json
import os
import requests
from agent import run_agent

app = FastAPI()

BOT_QQ = os.getenv("BOT_QQ", "1257934564")
NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://localhost:3000")


@app.get("/")
async def index():
    return {"status": "ok", "message": "战报机器人运行中"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "Invalid JSON"}

    if data.get("post_type") != "message" or data.get("message_type") != "group":
        return {"status": "ok"}

    if not is_at_bot(data):
        return {"status": "ok"}

    user_input = extract_user_input(data)
    if not user_input:
        return {"status": "ok"}

    user_id = data.get("user_id")
    group_id = data.get("group_id")

    print(f"📩 收到消息：{user_input}")

    result = run_agent(user_input, str(user_id))
    send_reply(group_id, user_id, result)

    return {"status": "ok"}


def is_at_bot(data: dict) -> bool:
    for seg in data.get("message", []):
        if seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == BOT_QQ:
            return True
    return False


def extract_user_input(data: dict) -> str:
    text = ""
    for seg in data.get("message", []):
        if seg.get("type") == "text":
            text += seg.get("data", {}).get("text", "")
    return text.strip()


def send_reply(group_id: int, user_id: int, result):
    if isinstance(result, list):
        send_forward(group_id, user_id, result)
    else:
        send_message(group_id, f"@{user_id} {result}")


def send_message(group_id: int, content: str):
    url = f"{NAPCAT_API_URL}/send_group_msg"
    try:
        requests.post(url, json={"group_id": group_id, "message": content}, timeout=5)
    except Exception as e:
        print(f"发送消息失败: {e}")


def send_forward(group_id: int, user_id: int, messages: list):
    send_message(group_id, f"@{user_id} 您要的战报已生成，请查看下方聊天记录 👇")
    nodes = []
    for msg in messages:
        nodes.append({
            "type": "node",
            "data": {"name": "战报机器人", "uin": BOT_QQ, "content": msg}
        })
    url = f"{NAPCAT_API_URL}/send_group_forward_msg"
    try:
        requests.post(url, json={"group_id": group_id, "messages": nodes}, timeout=5)
    except Exception as e:
        print(f"发送合并转发失败: {e}")
