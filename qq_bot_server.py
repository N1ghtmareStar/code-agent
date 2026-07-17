import asyncio
import json
import websockets
import sys
import os

# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent

# ========== 配置 ==========
HOST = "127.0.0.1"
PORT = 8765
BOT_QQ = 1257934564  # 你的机器人 QQ 号

print(f"🤖 QQ Bot WebSocket 服务启动中...")
print(f"📡 监听地址：ws://{HOST}:{PORT}")
print(f"🤖 机器人 QQ：{BOT_QQ}")


# ========== 检查是否被 @ ==========
def is_at_bot(message_data: dict) -> bool:
    message_list = message_data.get("message", [])
    for segment in message_list:
        if segment.get("type") == "at":
            target_qq = segment.get("data", {}).get("qq")
            if str(target_qq) == str(BOT_QQ):
                return True
    return False


# ========== 提取纯文本 ==========
def extract_text_without_at(message_data: dict) -> str:
    message_list = message_data.get("message", [])
    text_parts = []
    for segment in message_list:
        seg_type = segment.get("type")
        if seg_type == "text":
            text_parts.append(segment.get("data", {}).get("text", ""))
        elif seg_type == "at":
            target_qq = segment.get("data", {}).get("qq")
            if str(target_qq) == str(BOT_QQ):
                continue
            text_parts.append(f"@{target_qq}")
    return "".join(text_parts).strip()


# ========== 处理单条消息 ==========
async def handle_message(message_data: dict):
    """处理消息，返回 (回复内容, 消息类型, 群号/用户ID, 调用者QQ)"""
    message_type = message_data.get("message_type")
    user_id = message_data.get("user_id")
    group_id = message_data.get("group_id")

    if message_type != "group":
        return None, None, None, None

    if not is_at_bot(message_data):
        return None, None, None, None

    user_input = extract_text_without_at(message_data)
    if not user_input:
        return "请告诉我你的需求，比如：给我10个随机数 或 生成战报", message_type, group_id, user_id

    print(f"📩 收到群消息：{user_input}")

    try:
        result = await asyncio.to_thread(run_agent, user_input)
        return result, message_type, group_id, user_id
    except Exception as e:
        error_msg = f"❌ 处理出错：{str(e)}"
        print(error_msg)
        return error_msg, message_type, group_id, user_id


# ========== WebSocket 服务端 ==========
async def websocket_handler(websocket):
    print(f"🔗 客户端已连接：{websocket.remote_address}")

    try:
        async for message in websocket:
            print(f"📨 收到原始消息：{message[:200]}...")
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                print(f"⚠️ 无法解析 JSON")
                continue

            if data.get("post_type") == "meta_event":
                continue

            # 解包4个返回值
            reply_content, msg_type, group_id, user_id = await handle_message(data)
            if reply_content is None:
                continue

            # 构造回复
            if msg_type == "group" and group_id:
                # 群聊：@ 调用者 + 回复内容
                message_segments = [
                    {"type": "at", "data": {"qq": user_id}},
                    {"type": "text", "data": {"text": " " + reply_content}}
                ]
                reply_data = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": group_id,
                        "message": message_segments
                    }
                }
            elif msg_type == "private":
                reply_data = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": user_id,
                        "message": reply_content
                    }
                }
            else:
                continue

            await websocket.send(json.dumps(reply_data))
            print(f"✅ 已回复（@ {user_id}）")

    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 客户端已断开")
    except Exception as e:
        print(f"❌ 连接出错：{e}")


# ========== 启动 ==========
async def main():
    async with websockets.serve(websocket_handler, HOST, PORT):
        print(f"✅ WebSocket 服务已启动，监听 ws://{HOST}:{PORT}")
        print("等待 NapCat 连接...")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())