from fastapi import FastAPI, Request, Query, WebSocket, WebSocketDisconnect
import json
import os
import requests
import re
import asyncio
import logging
import ssl
from typing import Optional, Dict, Any
from datetime import datetime

import websockets
import aiohttp

from agent import run_agent
from match_report import generate_weekly_report

# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI()

BOT_QQ = os.getenv("BOT_QQ", "1905238428")
NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://localhost:3000")

# ============================================================
# QQ 官方 API 配置（需要到 q.qq.com 申请）
# ============================================================
QQ_APP_ID = os.getenv("QQ_APP_ID", "YOUR_APP_ID")  # 替换为您的 AppID
QQ_APP_SECRET = os.getenv("QQ_APP_SECRET", "YOUR_APP_SECRET")  # 替换为您的 AppSecret
QQ_ACCOUNT = os.getenv("QQ_ACCOUNT", "1905238428")


# ============================================================
# 基础路由
# ============================================================
@app.get("/")
async def index():
    return {"status": "ok", "message": "战报机器人运行中"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# 战报 API（供外部调用）
# ============================================================
@app.get("/api/match-report/generate")
async def generate_report_api(
    school: str = Query(..., description="学校名称或别名"),
    week: int = Query(None, description="周数"),
    rounds: str = Query(None, description="轮次，逗号分隔")
):
    """生成第五届联合杯战报"""
    try:
        round_numbers = None
        if rounds:
            round_numbers = [int(r.strip()) for r in rounds.split(",") if r.strip()]
        reports = generate_weekly_report(
            school_keyword=school,
            week_number=week,
            round_numbers=round_numbers
        )
        return {
            "status": "success",
            "data": {
                "messages": reports,
                "full_text": "\n\n".join(reports)
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/match-report/schools")
async def search_schools(keyword: str = Query(..., description="学校关键词")):
    """搜索学校"""
    from match_report import SCHOOL_ALIAS
    results = []
    for alias, full_name in SCHOOL_ALIAS.items():
        if keyword.lower() in alias.lower() or keyword.lower() in full_name.lower():
            results.append({"alias": alias, "full_name": full_name})
    seen = set()
    unique = []
    for r in results:
        if r["full_name"] not in seen:
            seen.add(r["full_name"])
            unique.append(r)
    return {"status": "success", "data": unique[:10]}


# ============================================================
# Webhook（兼容 LangBot）
# ============================================================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "Invalid JSON"}

    # 只处理群消息
    if data.get("post_type") != "message" or data.get("message_type") != "group":
        return {"status": "ok"}

    # 检查是否 @ 了机器人
    if not is_at_bot(data):
        return {"status": "ok"}

    user_input = extract_user_input(data)
    if not user_input:
        return {"status": "ok"}

    user_id = data.get("user_id")
    group_id = data.get("group_id")

    print(f"📩 收到消息：{user_input}")

    # 战报指令处理
    if re.search(r'战报|生成战报', user_input):
        match = re.search(r'(?:战报|生成战报)(?:[\s]+)?(.+?)(?:\s|$)', user_input)
        school = match.group(1) if match else "第二工业"
        
        try:
            reports = generate_weekly_report(school_keyword=school)
            send_forward(group_id, user_id, reports)
            return {"status": "ok"}
        except Exception as e:
            send_message(group_id, f"@{user_id} ❌ 生成战报失败：{str(e)}")
            return {"status": "ok"}

    # 其他指令交给 Agent
    result = run_agent(user_input, str(user_id))
    send_reply(group_id, user_id, result)

    return {"status": "ok"}


@app.post("/bots/{bot_id}")
async def bot_webhook(bot_id: str, request: Request):
    """兼容 LangBot 的 webhook 地址格式"""
    print(f"📩 通过 /bots/{bot_id} 收到请求")
    return await webhook(request)


# ============================================================
# QQ 消息辅助函数
# ============================================================
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


# ============================================================
# QQ 官方 API WebSocket 客户端
# ============================================================
class QQBot:
    def __init__(self, app_id: str, secret: str, account: str):
        self.app_id = app_id
        self.secret = secret
        self.account = account
        self.ws = None
        self.session = None
        self.logger = logging.getLogger("qq_bot")
        self.logger.setLevel(logging.INFO)
        self._running = False
        self._heartbeat_interval = 30
        self._seq = 0
        self._handlers = []

    def on_message(self, handler):
        """注册消息处理器"""
        self._handlers.append(handler)
        return handler

    async def start(self):
        """启动机器人"""
        self._running = True
        self.session = aiohttp.ClientSession()
        
        gateway_url = await self._get_gateway()
        
        while self._running:
            try:
                await self._connect_and_listen(gateway_url)
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.error(f"连接关闭: {e}")
            except Exception as e:
                self.logger.error(f"连接错误: {e}")
            
            if self._running:
                self.logger.info("5秒后重连...")
                await asyncio.sleep(5)

    async def _get_gateway(self) -> str:
        """获取 WebSocket 网关地址"""
        url = "https://api.sgroup.qq.com/gateway"
        headers = {"Authorization": f"Bot {self.app_id}.{self.secret}"}
        
        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()
            self.logger.info(f"获取网关成功")
            return data.get("url") + "?v=1"

    async def _connect_and_listen(self, gateway_url: str):
        """连接并监听 WebSocket"""
        self.logger.info(f"正在连接 WebSocket...")
        
        # 忽略 SSL 验证（生产环境请移除）
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            gateway_url,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=10,
            max_size=2**23
        ) as ws:
            self.ws = ws
            self.logger.info("✅ WebSocket 已连接")
            
            await self._send_identify()
            
            async for message in ws:
                await self._handle_message(message)

    async def _send_identify(self):
        """发送认证信息"""
        identify_payload = {
            "op": 2,
            "d": {
                "token": f"Bot {self.app_id}.{self.secret}",
                "intents": 1 << 9,  # 群消息
                "shard": [0, 1],
                "properties": {
                    "os": "Linux",
                    "browser": "LangBot",
                    "device": "LangBot"
                }
            }
        }
        await self.ws.send(json.dumps(identify_payload))
        self.logger.info("✅ 已发送认证信息")

    async def _handle_message(self, raw_message: str):
        """处理收到的消息"""
        try:
            payload = json.loads(raw_message)
            op = payload.get("op")
            
            if op == 0:
                await self._handle_event(payload.get("d", {}))
            elif op == 10:
                self._heartbeat_interval = payload["d"]["heartbeat_interval"] / 1000
                asyncio.create_task(self._heartbeat_loop())
            elif op == 11:
                pass
        except json.JSONDecodeError:
            self.logger.error(f"无效 JSON: {raw_message[:100]}")

    async def _handle_event(self, event: Dict[str, Any]):
        """处理事件"""
        event_type = event.get("type")
        
        if event_type == "GROUP_AT_MESSAGE_CREATE":
            await self._handle_group_message(event)
        elif event_type == "GROUP_MESSAGE_CREATE":
            await self._handle_group_message(event)

    async def _handle_group_message(self, event: Dict[str, Any]):
        """处理群消息"""
        # 解析消息内容
        message = ""
        for msg in event.get("message", []):
            if msg.get("type") == "text":
                message += msg.get("data", {}).get("text", "")
        
        # 检查是否 @ 机器人
        at_bot = False
        for msg in event.get("message", []):
            if msg.get("type") == "at" and str(msg.get("data", {}).get("qq")) == self.account:
                at_bot = True
                break
        
        if not at_bot:
            return
        
        group_id = event.get("group_id")
        user_id = event.get("author", {}).get("id")
        
        self.logger.info(f"📩 收到群消息: {message}")
        
        # 调用注册的消息处理器
        for handler in self._handlers:
            try:
                result = handler(message, group_id, user_id)
                if result:
                    await self.send_group_message(group_id, result)
                    break
            except Exception as e:
                self.logger.error(f"消息处理器错误: {e}")

    async def send_group_message(self, group_id: str, content: str):
        """发送群消息"""
        url = f"https://api.sgroup.qq.com/v2/groups/{group_id}/messages"
        headers = {
            "Authorization": f"Bot {self.app_id}.{self.secret}",
            "Content-Type": "application/json"
        }
        data = {"content": content}
        
        try:
            async with self.session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    self.logger.info(f"✅ 消息已发送: {content[:50]}...")
                else:
                    text = await resp.text()
                    self.logger.error(f"发送消息失败: {resp.status} {text}")
        except Exception as e:
            self.logger.error(f"发送消息异常: {e}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running and self.ws:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self.ws.send(json.dumps({"op": 1, "d": self._seq}))
            except Exception:
                break

    async def stop(self):
        """停止机器人"""
        self._running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


# ============================================================
# QQ 机器人实例
# ============================================================
qq_bot = QQBot(QQ_APP_ID, QQ_APP_SECRET, QQ_ACCOUNT)


@qq_bot.on_message
def handle_qq_message(message: str, group_id: str, user_id: str):
    """处理 QQ 消息"""
    print(f"🤖 处理消息: {message}")
    
    # 战报指令
    if re.search(r'战报|生成战报', message):
        match = re.search(r'(?:战报|生成战报)(?:[\s]+)?(.+?)(?:\s|$)', message)
        school = match.group(1) if match else "第二工业"
        
        try:
            reports = generate_weekly_report(school_keyword=school)
            return "\n\n".join(reports)
        except Exception as e:
            return f"❌ 生成战报失败：{str(e)}"
    
    # 普通对话（可选）
    return "发送 '战报 学校名称' 获取战报"


# ============================================================
# 启动事件
# ============================================================
@app.on_event("startup")
async def startup_event():
    """应用启动时运行 QQ 机器人"""
    asyncio.create_task(qq_bot.start())
    print("🚀 QQ 机器人已启动")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止 QQ 机器人"""
    await qq_bot.stop()
    print("🛑 QQ 机器人已停止")


# ============================================================
# 启动入口（兼容 Railway）
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)