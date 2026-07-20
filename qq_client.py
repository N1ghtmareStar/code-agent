import asyncio
import json
import logging
import ssl
from typing import Optional, Dict, Any

import aiohttp
import websockets

class QQBot:
    def __init__(self, app_id: str, secret: str, account: str):
        self.app_id = app_id
        self.secret = secret
        self.account = account
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger("qq_bot")
        self._running = False
        self._heartbeat_interval = 30
        self._seq = 0
        
        # 消息处理器
        self.message_handlers = []
    
    def on_message(self, handler):
        """注册消息处理器"""
        self.message_handlers.append(handler)
        return handler
    
    async def start(self):
        """启动机器人"""
        self._running = True
        self.session = aiohttp.ClientSession()
        
        # 获取 WebSocket 网关地址
        gateway_url = await self._get_gateway()
        
        while self._running:
            try:
                await self._connect_and_listen(gateway_url)
            except Exception as e:
                self.logger.error(f"连接断开: {e}，5秒后重连...")
                await asyncio.sleep(5)
    
    async def _get_gateway(self) -> str:
        """获取 WebSocket 网关地址"""
        url = "https://api.sgroup.qq.com/gateway"
        headers = {
            "Authorization": f"Bot {self.app_id}.{self.secret}"
        }
        
        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()
            self.logger.info(f"获取网关成功: {data}")
            return data.get("url") + "?v=1"
    
    async def _connect_and_listen(self, gateway_url: str):
        """连接并监听 WebSocket"""
        self.logger.info(f"正在连接 WebSocket: {gateway_url}")
        
        # 忽略 SSL 验证（生产环境请移除）
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            gateway_url,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=10
        ) as ws:
            self.ws = ws
            self.logger.info("✅ WebSocket 已连接")
            
            # 发送认证
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
                "shard": [0, 1]
            }
        }
        await self.ws.send(json.dumps(identify_payload))
        self.logger.info("✅ 已发送认证信息")
    
    async def _handle_message(self, raw_message: str):
        """处理收到的消息"""
        try:
            payload = json.loads(raw_message)
            op = payload.get("op")
            
            if op == 0:  # 事件
                await self._handle_event(payload.get("d", {}))
            elif op == 10:  # Hello
                self._heartbeat_interval = payload["d"]["heartbeat_interval"] / 1000
                asyncio.create_task(self._heartbeat_loop())
            elif op == 11:  # Heartbeat ACK
                pass
            elif op == 0:
                pass
        except json.JSONDecodeError:
            self.logger.error(f"无效 JSON: {raw_message[:100]}")
    
    async def _handle_event(self, event: Dict[str, Any]):
        """处理事件"""
        event_type = event.get("type")
        
        if event_type == "GROUP_AT_MESSAGE_CREATE":  # 群 @ 消息
            await self._handle_group_message(event)
    
    async def _handle_group_message(self, event: Dict[str, Any]):
        """处理群消息"""
        message = event.get("message", "")
        group_id = event.get("group_id")
        user_id = event.get("author", {}).get("id")
        
        self.logger.info(f"📩 收到群消息: {message}")
        
        # 调用注册的消息处理器
        for handler in self.message_handlers:
            try:
                result = handler(message, group_id, user_id)
                if result:
                    await self.send_group_message(group_id, result)
            except Exception as e:
                self.logger.error(f"消息处理器错误: {e}")
    
    async def send_group_message(self, group_id: str, content: str):
        """发送群消息"""
        url = "https://api.sgroup.qq.com/v2/groups/{group_id}/messages"
        headers = {
            "Authorization": f"Bot {self.app_id}.{self.secret}",
            "Content-Type": "application/json"
        }
        data = {
            "content": content
        }
        
        try:
            async with self.session.post(
                url.format(group_id=group_id),
                headers=headers,
                json=data
            ) as resp:
                if resp.status != 200:
                    self.logger.error(f"发送消息失败: {resp.status}")
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