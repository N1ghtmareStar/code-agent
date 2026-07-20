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
from match_report import generate_weekly_report

# ========== 配置 ==========
HOST = "0.0.0.0"
PORT = 8765
BOT_QQ = 1257934564

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


# ========== 发送消息的辅助函数 ==========
async def send_group_message(websocket, group_id: int, content):
    """发送群消息"""
    payload = {
        "action": "send_group_msg",
        "params": {
            "group_id": group_id,
            "message": content
        }
    }
    await websocket.send(json.dumps(payload))


async def send_forward_message(websocket, group_id: int, user_id: int, user_input: str, messages: list):
    """发送合并转发消息"""
    # 1. 发送 @ 提醒
    at_text = generate_at_text(user_input)
    at_segments = [
        {"type": "at", "data": {"qq": user_id}},
        {"type": "text", "data": {"text": at_text}}
    ]
    await send_group_message(websocket, group_id, at_segments)
    await asyncio.sleep(0.5)

    # 2. 构建合并转发节点
    forward_nodes = []
    for msg in messages:
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
    print(f"✅ 已发送合并转发（共 {len(messages)} 条消息）", flush=True)


# ========== 提取学校名称 ==========
def extract_school_from_input(user_input: str) -> str:
    """从用户输入中提取学校名称"""
    clean = re.sub(r'生成|战报', '', user_input).strip()
    
    if not clean:
        return None
    
    clean = re.sub(r'第[\d一二三四五六七八九十]+周', '', clean)
    clean = re.sub(r'第[\d、,，\-到]+轮', '', clean)
    clean = re.sub(r'[一二三四五六七八九十]+周', '', clean)
    clean = re.sub(r'[一二三四五六七八九十]+轮', '', clean)
    clean = clean.strip()
    
    if not clean:
        return None
    
    parts = clean.split()
    school = parts[0] if parts else None
    
    invalid_words = ["请", "我", "你", "他", "这", "那", "什么", "怎么", "的", "了", "吗", "呢", "吧", "啊"]
    if school in invalid_words:
        return None
    
    return school


def extract_week_from_input(user_input: str) -> int:
    """从用户输入中提取周数"""
    match = re.search(r'第(\d+)周', user_input)
    if match:
        return int(match.group(1))
    return None


def extract_rounds_from_input(user_input: str) -> list:
    """从用户输入中提取轮次"""
    match = re.search(r'第([\d、,，]+)轮', user_input)
    if match:
        parts = re.split(r'[、,，]', match.group(1))
        rounds = [int(p.strip()) for p in parts if p.strip().isdigit()]
        if rounds:
            return rounds
    match = re.search(r'第(\d+)[-到](\d+)轮', user_input)
    if match:
        return list(range(int(match.group(1)), int(match.group(2)) + 1))
    match = re.search(r'第(\d+)轮', user_input)
    if match:
        return [int(match.group(1))]
    return None


# ========== 处理单条消息 ==========
async def handle_message(message_data: dict, websocket):
    message_type = message_data.get("message_type")
    user_id = message_data.get("user_id")
    group_id = message_data.get("group_id")

    if message_type != "group":
        return

    if not is_at_bot(message_data):
        return

    user_input = extract_text_without_at(message_data)
    if not user_input:
        await send_group_message(websocket, group_id, "请告诉我你的需求，比如：生成战报 或 帮助")
        return

    print(f"📩 收到群消息：{user_input}", flush=True)

    # ===== 战报指令处理 =====
    if re.search(r'战报|生成战报', user_input):
        school = extract_school_from_input(user_input)
        week = extract_week_from_input(user_input)
        rounds = extract_rounds_from_input(user_input)
        
        # 判断是本地规则还是需要大模型
        if school is not None:
            # ===== 本地规则路径（不显示"正在查询"） =====
            print(f"⚡ 本地规则处理，学校：{school}", flush=True)
            
            try:
                if week is not None:
                    reports = generate_weekly_report(school_keyword=school, week_number=week)
                elif rounds is not None:
                    reports = generate_weekly_report(school_keyword=school, round_numbers=rounds)
                else:
                    reports = generate_weekly_report(school_keyword=school)
                
                if isinstance(reports, list):
                    await send_forward_message(websocket, group_id, user_id, user_input, reports)
                else:
                    await send_group_message(websocket, group_id, reports)
                
                return
            except Exception as e:
                error_msg = f"❌ 生成战报失败：{str(e)}"
                print(error_msg, flush=True)
                await send_group_message(websocket, group_id, error_msg)
                return
        
        else:
            # ===== 🔥 大模型路径（显示"正在查询"） =====
            print(f"🤖 需要大模型解析指令", flush=True)
            
            # 先发送"正在查询"提示
            await send_group_message(websocket, group_id, f"⏳ 正在解析您的指令，请稍候...")
            
            try:
                # 调用 agent.py 处理（会调用大模型）
                result = await asyncio.to_thread(run_agent, user_input, str(user_id))
                
                print(f"📤 qq_bot_server 收到结果类型：{type(result)}", flush=True)
                
                # 🔥 检查结果类型，支持合并转发
                if isinstance(result, list):
                    print(f"📤 发送合并转发，共 {len(result)} 条", flush=True)
                    await send_forward_message(websocket, group_id, user_id, user_input, result)
                else:
                    await send_group_message(websocket, group_id, str(result))
                
                return
            except Exception as e:
                error_msg = f"❌ 处理失败：{str(e)}"
                print(error_msg, flush=True)
                await send_group_message(websocket, group_id, error_msg)
                return

    # ===== 非战报指令，直接交给 agent.py =====
    try:
        result = await asyncio.to_thread(run_agent, user_input, str(user_id))
        
        if isinstance(result, list):
            await send_forward_message(websocket, group_id, user_id, user_input, result)
        else:
            await send_group_message(websocket, group_id, str(result))
        
    except Exception as e:
        error_msg = f"❌ 处理出错：{str(e)}"
        print(error_msg, flush=True)
        await send_group_message(websocket, group_id, error_msg)


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

            await handle_message(data, websocket)

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