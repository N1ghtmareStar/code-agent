import os
import re
import json
import glob
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from match_report import generate_weekly_report_text

# ============================================================
# 配置
# ============================================================
VOLC_ACCESS_KEY = os.getenv("VOLC_ACCESS_KEY")
VOLC_ENDPOINT_ID = os.getenv("VOLC_ENDPOINT_ID")

if not VOLC_ACCESS_KEY:
    print("⚠️ 警告：VOLC_ACCESS_KEY 未设置，大模型功能不可用")
if not VOLC_ENDPOINT_ID:
    print("⚠️ 警告：VOLC_ENDPOINT_ID 未设置，大模型功能不可用")

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = VOLC_ENDPOINT_ID

# ============================================================
# 用户绑定管理
# ============================================================

BINDINGS_FILE = "user_bindings.json"


def load_bindings() -> dict:
    if os.path.exists(BINDINGS_FILE):
        try:
            with open(BINDINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_bindings(bindings: dict):
    with open(BINDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(bindings, f, ensure_ascii=False, indent=2)


def get_user_school(user_id: str, default: str = "第二工业") -> str:
    bindings = load_bindings()
    return bindings.get(str(user_id), default)


def set_user_school(user_id: str, school: str) -> str:
    bindings = load_bindings()
    bindings[str(user_id)] = school
    save_bindings(bindings)
    return f"✅ 已绑定学校：{school}"


def clear_user_school(user_id: str) -> str:
    bindings = load_bindings()
    if str(user_id) in bindings:
        del bindings[str(user_id)]
        save_bindings(bindings)
        return "✅ 已解绑，恢复默认学校「第二工业」"
    return "⚠️ 你尚未绑定任何学校"


# ============================================================
# 1. 工具函数 - 提取参数
# ============================================================

def extract_school_keyword(text: str) -> Optional[str]:
    """提取学校关键词，没有则返回 None"""
    cleaned = re.sub(r'生成|战报', '', text).strip()
    cleaned = re.sub(r'第[\d一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'第[\d、,，\-到]+轮', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+轮', '', cleaned)
    cleaned = re.sub(r'首周|次周|首轮|次轮', '', cleaned)
    cleaned = cleaned.strip()
    
    if not cleaned:
        return None
    
    match = re.search(r'([\u4e00-\u9fa5]{2,4}(?:大学|学院|大)?)', cleaned)
    if match:
        return match.group(1)
    
    match = re.search(r'([\u4e00-\u9fa5]{2,4})', cleaned)
    if match:
        return match.group(1)
    
    return None


def extract_week_number(text: str) -> Optional[int]:
    match = re.search(r'第(\d+)周', text)
    if match:
        return int(match.group(1))
    chinese_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    match = re.search(r'([一二三四五六七八九十]+)周', text)
    if match:
        ch = match.group(1)
        if ch in chinese_map:
            return chinese_map[ch]
    if "首周" in text:
        return 1
    return None


def extract_round_numbers(text: str) -> Optional[List[int]]:
    match = re.search(r'第([\d、,，]+)轮', text)
    if match:
        parts = re.split(r'[、,，]', match.group(1))
        rounds = [int(p.strip()) for p in parts if p.strip().isdigit()]
        if rounds:
            return rounds
    match = re.search(r'第(\d+)[-到](\d+)轮', text)
    if match:
        return list(range(int(match.group(1)), int(match.group(2)) + 1))
    match = re.search(r'第(\d+)轮', text)
    if match:
        return [int(match.group(1))]
    return None


# ============================================================
# 2. 大模型调用
# ============================================================

def call_llm(prompt: str) -> str:
    if not VOLC_ACCESS_KEY or not VOLC_ENDPOINT_ID:
        print("⚠️ 大模型未配置")
        return None
    
    headers = {
        "Authorization": f"Bearer {VOLC_ACCESS_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个战报机器人助手，帮助用户生成立直麻将比赛战报。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 800,
        "temperature": 0.3
    }
    
    try:
        resp = requests.post(API_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"⚠️ 大模型调用失败：{e}")
        return None


# ============================================================
# 3. 用大模型解析用户指令
# ============================================================

def parse_with_llm(user_input: str, user_id: str = None) -> dict:
    """
    用大模型解析用户指令，返回结构化的参数
    """
    bound_school = get_user_school(user_id, default="第二工业") if user_id else "第二工业"
    
    prompt = f"""
用户说："{user_input}"

请解析用户的意图，返回JSON格式。

可能的意图：
1. "生成战报" - 用户想生成战报
2. "绑定学校" - 用户想绑定学校
3. "查看绑定" - 用户想查看绑定的学校
4. "解绑学校" - 用户想解绑学校
5. "帮助" - 用户想查看帮助
6. "闲聊" - 用户只是闲聊

如果是"生成战报"，请提取：
- school: 学校名称（从用户输入中提取，如"二工大"、"北大"），如果没提到则用 "{bound_school}"
- week: 周数（如果有"第X周"），否则 null
- rounds: 轮次列表（如果有"第X轮"或"第X、Y轮"），否则 null

只返回JSON，不要其他内容。
格式示例：
{{"intent": "生成战报", "school": "二工大", "week": null, "rounds": [3, 4]}}
{{"intent": "绑定学校", "school": "北大"}}
{{"intent": "查看绑定"}}
{{"intent": "解绑学校"}}
{{"intent": "帮助"}}
{{"intent": "闲聊", "message": "你好啊"}}
"""
    
    response = call_llm(prompt)
    
    if response is None:
        return {"intent": "error", "message": "大模型不可用"}
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            return {"intent": "error", "message": "无法解析大模型响应"}
    except json.JSONDecodeError:
        return {"intent": "error", "message": "大模型返回格式错误"}


# ============================================================
# 4. 帮助信息
# ============================================================

def get_help_text() -> str:
    return """📖 **战报机器人使用帮助**

**基本用法：**
@机器人 生成战报

**学校指定（临时）：**
• 生成二工大战报
• 生成北大战报
• 生成上大战报

**绑定学校（永久）：**
• 绑定学校 二工大
• 绑定学校 北大
• 查看绑定
• 解绑学校

**周数/轮次指定：**
• 生成第1周战报
• 生成第2周战报
• 生成第3、4轮战报
• 生成第1-4轮战报

**默认：**
• 绑定后，直接「生成战报」即可查询绑定学校
• 未绑定时，默认查询「上海第二工业大学」
• 不指定时间时，默认查询最新已完成的两轮

**示例：**
@机器人 绑定学校 二工大
@机器人 生成战报  ← 自动查询二工大
@机器人 生成第2周战报
@机器人 生成第3、4轮战报"""


# ============================================================
# 5. 🔥 安全执行代码（返回列表，支持合并转发）
# ============================================================

def safe_execute(code: str, globals_dict: dict = None):
    """
    安全执行代码并返回结果
    返回值：如果是战报，返回列表；否则返回字符串
    """
    if globals_dict is None:
        globals_dict = {}
    
    safe_globals = {
        "generate_weekly_report_text": generate_weekly_report_text,
        "datetime": datetime,
        "os": os,
        "json": json,
        "glob": glob,
        "print": print,
    }
    safe_globals.update(globals_dict)
    
    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        exec(code, safe_globals)
        
        # 🔥 关键：先获取 result 变量
        result = safe_globals.get('result', None)
        
        # 如果有打印输出，也捕获
        output = sys.stdout.getvalue()
        
        # 如果 result 是列表，直接返回
        if isinstance(result, list):
            return result
        
        # 如果 result 是字符串，返回字符串
        if isinstance(result, str):
            return result
        
        # 如果有打印输出，返回输出
        if output.strip():
            return output.strip()
        
        return "执行完成（无输出）"
            
    except Exception as e:
        return f"❌ 代码执行出错：{str(e)}"
    finally:
        sys.stdout = old_stdout


# ============================================================
# 6. 🔥 生成代码（不 print，赋值给变量）
# ============================================================

def generate_code_with_llm(user_input: str, user_id: str = None) -> str:
    """
    生成调用战报函数的代码
    """
    school = extract_school_keyword(user_input)
    
    if school is None:
        if user_id:
            school = get_user_school(user_id, default="第二工业")
        else:
            school = "第二工业"
    
    week = extract_week_number(user_input)
    rounds = extract_round_numbers(user_input)
    
    # 构建代码模板 - 赋值给 result，不 print
    if week is not None:
        return f"""
result = generate_weekly_report_text(school_keyword="{school}", week_number={week})
"""
    elif rounds is not None:
        return f"""
result = generate_weekly_report_text(school_keyword="{school}", round_numbers={rounds})
"""
    else:
        # 调用大模型解析
        print("--- 调用大模型解析指令 ---")
        
        prompt = f"""
用户输入：{user_input}

请生成Python代码调用 generate_weekly_report_text 函数。

规则：
1. school_keyword: 从输入中提取学校简称（如"二工大"→"二工大"），没有则用"{school}"
2. week_number: 如果提到"第X周"、"第一周"、"首周"，提取数字；否则为 None
3. round_numbers: 如果提到"第X轮"或"第X、Y轮"，提取列表；否则为 None

只返回Python代码，不要任何解释。格式如：
result = generate_weekly_report_text(school_keyword="二工大", week_number=1)
"""
        
        code = call_llm(prompt)
        
        if code is None:
            print("⚠️ 大模型不可用，使用本地规则兜底")
            return f"""
result = generate_weekly_report_text(school_keyword="{school}")
"""
        
        code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        return code.strip()


# ============================================================
# 7. 🔥 核心函数
# ============================================================

def run_agent(user_input: str, user_id: str = None):
    print(f"📩 用户输入：{user_input}")
    print(f"👤 用户ID：{user_id}")
    
    # ---- 1. 本地快速匹配 ----
    
    # 绑定学校
    if "绑定学校" in user_input:
        match = re.search(r'绑定学校\s*([\u4e00-\u9fa5]{2,4}大?)', user_input)
        if match:
            school = match.group(1)
            return set_user_school(user_id, school)
        return "⚠️ 请指定要绑定的学校，例如：绑定学校 二工大"
    
    # 查看绑定
    if "查看绑定" in user_input:
        school = get_user_school(user_id, default="第二工业")
        return f"📌 你当前绑定的学校是：{school}"
    
    # 解绑学校
    if "解绑学校" in user_input:
        return clear_user_school(user_id)
    
    # 帮助
    help_keywords = ["帮助", "help", "怎么用", "使用方法", "指令", "功能"]
    user_lower = user_input.lower().strip()
    if user_lower in ["帮助", "help"] or any(kw in user_lower for kw in ["怎么用", "使用方法", "指令", "功能"]):
        return get_help_text()
    
    # 问候
    if user_lower in ["你好", "hello", "hi", "hey"]:
        import random
        greetings = ["你好呀！😊", "嗨！有什么可以帮你的？", "hello！需要生成战报吗？", "我在呢！👋"]
        return random.choice(greetings)
    
    # ---- 2. 战报生成 ----
    if "生成" in user_input and "战报" in user_input:
        print("--- 正在生成战报 ---")
        code = generate_code_with_llm(user_input, user_id)
        print(f"📄 生成的代码：\n{code}")
        
        print("--- 执行代码 ---")
        result = safe_execute(code)
        print(f"📤 执行结果类型：{type(result)}")
        
        if isinstance(result, list):
            print(f"📤 返回列表，长度：{len(result)}")
            return result
        
        if isinstance(result, str):
            print(f"📤 返回字符串，长度：{len(result)}")
            return result
        
        print(f"📤 返回其他类型：{result}")
        return str(result) if result else "执行完成（无输出）"
    
    # ---- 3. 其他指令交给大模型 ----
    print("🤖 使用大模型处理通用指令")
    
    prompt = f"""
用户说："{user_input}"

请作为战报机器人助手回复用户。用户可能询问比赛信息、学校排名、赛制等。
如果用户的问题超出你的知识范围，请礼貌地建议用户发送「帮助」查看使用说明。

保持回复简洁、友好。
"""
    
    response = call_llm(prompt)
    
    if response is None:
        return "抱歉，我暂时无法处理这个请求。\n\n发送「帮助」查看使用说明。"
    
    return response


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    test_inputs = [
        "帮助",
        "绑定学校 二工大",
        "查看绑定",
        "生成战报",
        "生成第2周战报",
        "解绑学校",
    ]
    
    test_user_id = "1761473633"
    
    for inp in test_inputs:
        print("\n" + "="*50)
        print(f"测试输入：{inp}")
        result = run_agent(inp, test_user_id)
        if isinstance(result, list):
            for i, msg in enumerate(result, 1):
                print(f"消息{i}:\n{msg}\n")
        else:
            print(f"结果：{result}")