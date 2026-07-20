import asyncio
import json
import websockets
import sys
import os
import ast
import re
from typing import List

# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent, get_user_school
from match_report import generate_weekly_report, SCHOOL_ALIAS, get_display_name

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


# ========== 生成动态提醒文本 ==========
def generate_at_text(user_input: str, result_type: str = "结果") -> str:
    """生成 @ 用户的提示文本"""
    if "战报" in user_input:
        week_match = re.search(r'第(\d+)周', user_input)
        if week_match:
            return f" 您要的第{week_match.group(1)}周战报已生成，请查看下方聊天记录 👇"
        round_match = re.search(r'第([\d、,，\-到]+)轮', user_input)
        if round_match:
            return f" 您要的第{round_match.group(1)}轮战报已生成，请查看下方聊天记录 👇"
        return " 您要的战报已生成，请查看下方聊天记录 👇"
    elif "帮助" in user_input or "help" in user_input.lower():
        return " 您要的帮助信息已生成，请查看下方聊天记录 👇"
    elif "学校列表" in user_input:
        return " 您要的学校列表已生成，请查看下方聊天记录 👇"
    elif "绑定" in user_input:
        return " 绑定操作已完成，请查看下方聊天记录 👇"
    elif "缓存" in user_input:
        return " 缓存操作已完成，请查看下方聊天记录 👇"
    return f" 您要的{result_type}已生成，请查看下方聊天记录 👇"


# ========== 🔥 统一发送消息（全部走合并转发） ==========
async def send_group_message(websocket, group_id: int, content):
    """发送群消息（单条）"""
    payload = {
        "action": "send_group_msg",
        "params": {
            "group_id": group_id,
            "message": content
        }
    }
    await websocket.send(json.dumps(payload))


async def send_forward_message(websocket, group_id: int, user_id: int, user_input: str, messages, result_type: str = "结果"):
    """
    🔥 统一发送消息，自动判断类型并走合并转发
    
    Args:
        messages: 可以是 str 或 list
        result_type: 结果类型描述
    """
    # 统一转为列表
    if isinstance(messages, str):
        messages_list = [messages]
    elif isinstance(messages, list):
        messages_list = messages
    else:
        messages_list = [str(messages)]
    
    # 过滤空消息
    messages_list = [msg for msg in messages_list if msg and msg.strip()]
    
    if not messages_list:
        messages_list = ["⚠️ 结果为空，请稍后重试"]
    
    # 生成 @ 提示
    at_text = generate_at_text(user_input, result_type)
    at_segments = [
        {"type": "at", "data": {"qq": user_id}},
        {"type": "text", "data": {"text": at_text}}
    ]
    await send_group_message(websocket, group_id, at_segments)
    await asyncio.sleep(0.3)
    
    # 构建合并转发节点
    forward_nodes = []
    for msg in messages_list:
        node = {
            "type": "node",
            "data": {
                "name": "战报机器人",
                "uin": str(BOT_QQ),
                "content": msg
            }
        }
        forward_nodes.append(node)
    
    # 发送合并转发
    forward_data = {
        "action": "send_group_forward_msg",
        "params": {
            "group_id": group_id,
            "messages": forward_nodes
        }
    }
    await websocket.send(json.dumps(forward_data))
    print(f"✅ 已发送合并转发（共 {len(messages_list)} 条消息）", flush=True)


# ========== 🔥 改进的学校提取 ==========
def extract_school_from_input(user_input: str) -> str:
    """从用户输入中提取学校名称（支持别名）"""
    # 先检查别名映射
    for alias, full_name in SCHOOL_ALIAS.items():
        if alias in user_input or full_name in user_input:
            return full_name
    
    # 移除战报相关关键词，避免误匹配
    clean_input = re.sub(r'生成|战报|战绩|排名|查询|看看|显示|多少|现在|当前', '', user_input)
    clean_input = re.sub(r'第[\d一二三四五六七八九十]+周', '', clean_input)
    clean_input = re.sub(r'第[\d、,，\-到]+轮', '', clean_input)
    clean_input = clean_input.strip()
    
    if not clean_input:
        return None
    
    # 匹配常见学校名（2-4个中文字符，可能以大学/学院/大结尾）
    school_match = re.search(r'([\u4e00-\u9fa5]{2,4}(?:大学|学院|大)?)', clean_input)
    if school_match:
        school = school_match.group(1)
        invalid_words = ["请", "我", "你", "他", "这", "那", "什么", "怎么", "的", "了", "吗", "呢", "吧", "啊", "如何", "联合杯"]
        if school not in invalid_words:
            return school
    
    # 模糊匹配：2-4个中文字符
    school_match = re.search(r'([\u4e00-\u9fa5]{2,4})', clean_input)
    if school_match:
        school = school_match.group(1)
        invalid_words = ["请", "我", "你", "他", "这", "那", "什么", "怎么", "的", "了", "吗", "呢", "吧", "啊", "如何", "联合杯"]
        if school not in invalid_words:
            return school
    
    return None


# ========== 判断是否战报意图 ==========
def is_report_intent(user_input: str) -> bool:
    """判断用户是否想要战报"""
    # 明确包含战报关键词
    if re.search(r'战报|战绩|排名', user_input):
        return True
    
    # 包含学校名称 + 查询意图
    school = extract_school_from_input(user_input)
    if school:
        query_keywords = ['怎么样', '如何', '情况', '查询', '看看', '显示', '多少', '现在', '当前']
        if any(kw in user_input for kw in query_keywords):
            return True
    
    return False


# ========== 生成绑定提示 ==========
def get_bind_prompt(user_id: int) -> List[str]:
    """生成绑定学校提示（返回列表，用于合并转发）"""
    return [
        "⚠️ 您还没有绑定学校，无法生成战报。",
        "",
        "📌 **请先绑定学校**，例如：",
        "  @机器人 绑定学校 二工大",
        "  @机器人 绑定学校 交大",
        "  @机器人 绑定学校 复旦",
        "",
        "📋 **查看所有参赛学校**：",
        "  @机器人 学校列表",
        "",
        "💡 绑定后，直接发送「生成战报」即可查询绑定学校的战报。"
    ]


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
        await send_forward_message(websocket, group_id, user_id, user_input, 
                                   ["请告诉我你的需求，比如：生成战报 或 帮助"], "提示")
        return

    print(f"📩 收到群消息：{user_input}", flush=True)

    # ===== 🔥 战报指令检测 =====
    if is_report_intent(user_input):
        # 尝试从输入中提取学校名
        school = extract_school_from_input(user_input)
        
        if school is not None:
            # ===== 有学校名 → 本地规则路径（快速） =====
            print(f"⚡ 本地规则处理，学校：{school}", flush=True)
            
            try:
                reports = generate_weekly_report(school_keyword=school)
                await send_forward_message(websocket, group_id, user_id, user_input, reports, "战报")
                return
            except Exception as e:
                error_msg = f"❌ 生成战报失败：{str(e)}"
                print(error_msg, flush=True)
                await send_forward_message(websocket, group_id, user_id, user_input, [error_msg], "错误")
                return
        
        else:
            # ===== 没有学校名 → 检查用户绑定 =====
            bound_school = get_user_school(str(user_id), default=None)
            
            if bound_school is not None:
                # ===== 有绑定学校 → 使用绑定学校查询 =====
                # 获取显示名称用于日志
                display_name = get_display_name(bound_school)
                print(f"🔗 使用绑定学校：{display_name}（用户 {user_id}）", flush=True)
                
                try:
                    reports = generate_weekly_report(school_keyword=bound_school)
                    await send_forward_message(websocket, group_id, user_id, user_input, reports, "战报")
                    return
                except Exception as e:
                    error_msg = f"❌ 生成战报失败：{str(e)}"
                    print(error_msg, flush=True)
                    await send_forward_message(websocket, group_id, user_id, user_input, [error_msg], "错误")
                    return
            
            else:
                # ===== 无绑定学校 → 提示绑定（走合并转发） =====
                print(f"⚠️ 用户 {user_id} 未绑定学校，发送绑定提示", flush=True)
                await send_forward_message(websocket, group_id, user_id, user_input, 
                                           get_bind_prompt(user_id), "绑定提示")
                return

    # ===== 非战报指令，交给 agent.py =====
    try:
        result = await asyncio.to_thread(run_agent, user_input, str(user_id))
        await send_forward_message(websocket, group_id, user_id, user_input, result, "结果")
    except Exception as e:
        error_msg = f"❌ 处理出错：{str(e)}"
        print(error_msg, flush=True)
        await send_forward_message(websocket, group_id, user_id, user_input, [error_msg], "错误")


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