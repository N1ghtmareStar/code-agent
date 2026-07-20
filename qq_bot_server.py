import asyncio
import json
import websockets
import sys
import os
import ast
import re

# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent

# ========== 配置 ==========
HOST = "0.0.0.0"
PORT = 8765
BOT_QQ = 1257934564  # 你的机器人 QQ 号

print(f"🤖 QQ Bot WebSocket 服务启动中...", flush=True)
print(f"📡 监听地址：ws://{HOST}:{PORT}", flush=True)
print(f"🤖 机器人 QQ：{BOT_QQ}", flush=True)


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


# ========== 尝试将字符串解析为列表 ==========
def try_parse_list(content):
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, list):
                    return parsed
            except (SyntaxError, ValueError):
                pass
    return content


# ========== 生成动态提醒文本 ==========
def generate_at_text(user_input: str) -> str:
    if "战报" in user_input:
        week_match = re.search(r'第(\d+)周', user_input)
        if week_match:
            return f" 您要的第{week_match.group(1)}周战报已生成，请查看下方聊天记录 👇"
        round_match = re.search(r'第([\d、,，\-到]+)轮', user_input)
        if round_match:
            return f" 您要的第{round_match.group(1)}轮战报已生成，请查看下方聊天记录 👇"
        return " 您要的战报已生成，请查看下方聊天记录 👇"
    return " 您要的结果已生成，请查看下方聊天记录 👇"


# ========== 处理单条消息 ==========
async def handle_message(message_data: dict):
    message_type = message_data.get("message_type")
    user_id = message_data.get("user_id")
    group_id = message_data.get("group_id")

    if message_type != "group":
        return None, None, None, None, ""

    if not is_at_bot(message_data):
        return None, None, None, None, ""

    user_input = extract_text_without_at(message_data)
    if not user_input:
        return "请告诉我你的需求，比如：给我10个随机数 或 生成战报", message_type, group_id, user_id, user_input

    print(f"📩 收到群消息：{user_input}", flush=True)

    try:
        # 🔥 传入 user_id 以支持绑定学校功能
        result = await asyncio.to_thread(run_agent, user_input, str(user_id))
        result = try_parse_list(result)
        return result, message_type, group_id, user_id, user_input
    except Exception as e:
        error_msg = f"❌ 处理出错：{str(e)}"
        print(error_msg, flush=True)
        return error_msg, message_type, group_id, user_id, user_input


# ========== WebSocket 服务端 ==========
async def websocket_handler(websocket):
    print(f"🔗 客户端已连接：{websocket.remote_address}", flush=True)

    try:
        async for message in websocket:
            print(f"📨 收到原始消息：{message[:200]}...", flush=True)
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                print(f"⚠️ 无法解析 JSON", flush=True)
                continue

            if data.get("post_type") == "meta_event":
                continue

            reply_content, msg_type, group_id, user_id, user_input = await handle_message(data)
            if reply_content is None:
                continue

            if isinstance(reply_content, str):
                messages_to_send = [reply_content]
            elif isinstance(reply_content, list):
                messages_to_send = reply_content
            else:
                messages_to_send = [str(reply_content)]

            if msg_type == "group" and group_id:
                # 1. 发送 @ 提醒
                at_text = generate_at_text(user_input)
                at_segments = [
                    {"type": "at", "data": {"qq": user_id}},
                    {"type": "text", "data": {"text": at_text}}
                ]
                at_reply = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": group_id,
                        "message": at_segments
                    }
                }
                await websocket.send(json.dumps(at_reply))
                await asyncio.sleep(0.5)

                # 2. 构建合并转发节点
                forward_nodes = []
                for msg in messages_to_send:
                    node = {
                        "type": "node",
                        "data": {
                            "name": "战报机器人",
                            "uin": str(BOT_QQ),
                            "content": msg
                        }
                    }
                    forward_nodes.append(node)

                forward_data = {
                    "action": "send_group_forward_msg",
                    "params": {
                        "group_id": group_id,
                        "messages": forward_nodes
                    }
                }
                await websocket.send(json.dumps(forward_data))
                print(f"✅ 已发送合并转发（共 {len(messages_to_send)} 条消息）", flush=True)

            elif msg_type == "private":
                reply_data = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": user_id,
                        "message": "\n".join(messages_to_send)
                    }
                }
                await websocket.send(json.dumps(reply_data))
                print(f"✅ 已私聊回复（{user_id}）", flush=True)

    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 客户端已断开", flush=True)
    except Exception as e:
        print(f"❌ 连接出错：{e}", flush=True)


# ========== 启动 ==========
async def main():
    async with websockets.serve(websocket_handler, HOST, PORT):
        print(f"✅ WebSocket 服务已启动，监听 ws://{HOST}:{PORT}", flush=True)
        print("等待 NapCat 连接...", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())