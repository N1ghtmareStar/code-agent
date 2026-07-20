import os
import re
import json
import glob
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from match_report import generate_weekly_report_text, SCHOOL_ALIAS, clear_cache

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
# 1. 🔥 改进的工具函数 - 提取参数（支持更多别名）
# ============================================================

def extract_school_keyword(text: str) -> Optional[str]:
    """提取学校关键词，支持别名映射"""
    cleaned = re.sub(r'生成|战报', '', text).strip()
    cleaned = re.sub(r'第[\d一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'第[\d、,，\-到]+轮', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+轮', '', cleaned)
    cleaned = re.sub(r'首周|次周|首轮|次轮', '', cleaned)
    cleaned = cleaned.strip()
    
    if not cleaned:
        return None
    
    # 🔥 先检查别名映射
    for alias, full_name in SCHOOL_ALIAS.items():
        if alias in cleaned or full_name in cleaned:
            return full_name
    
    # 匹配学校名（2-4个中文字符，可能以大学/学院/大结尾）
    match = re.search(r'([\u4e00-\u9fa5]{2,4}(?:大学|学院|大)?)', cleaned)
    if match:
        school = match.group(1)
        # 过滤无效词
        invalid_words = ["请", "我", "你", "他", "这", "那", "什么", "怎么", "的", "了", "吗", "呢", "吧", "啊", "如何", "联合杯"]
        if school not in invalid_words:
            return school
    
    # 模糊匹配：2-4个中文字符
    match = re.search(r'([\u4e00-\u9fa5]{2,4})', cleaned)
    if match:
        school = match.group(1)
        invalid_words = ["请", "我", "你", "他", "这", "那", "什么", "怎么", "的", "了", "吗", "呢", "吧", "啊", "如何", "联合杯"]
        if school not in invalid_words:
            return school
    
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
            {"role": "system", "content": """你是一个战报机器人助手，帮助用户生成立直麻将比赛战报。

学校别名参考（当用户使用简称时，请映射到全称）：
- 二工大/二工/上二工大 → 上海第二工业大
- 交大/上交/上交大 → 上海交通大学
- 华师/华师大 → 华东师范大学
- 复旦 → 复旦大学
- 同济 → 同济大学
- 上外 → 上海外国语大学
- 东华 → 东华大学
- 上理 → 上海理工大学
- 海事 → 上海海事大学
- 海洋 → 上海海洋大学
- 上财 → 上海财经大学
- 上戏 → 上海戏剧学院
- 上音 → 上海音乐学院
- 体院 → 上海体育学院
- 上政 → 上海政法学院
- 上应 → 上海应用技术大学
- 上科大/上海科技 → 上海科技大学
- 国科大/中科院 → 中国科学院大学
- 社科大 → 中国社会科学院大学

其他高校别名也支持，请根据常见简称自动匹配。
"""},
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
# 3. 🔥 改进的大模型解析
# ============================================================

def parse_with_llm(user_input: str, user_id: str = None) -> dict:
    """
    用大模型解析用户指令，返回结构化的参数
    """
    bound_school = get_user_school(user_id, default="第二工业") if user_id else "第二工业"
    
    # 构建别名列表供大模型参考
    alias_list = "\n".join([f"- {k} → {v}" for k, v in list(SCHOOL_ALIAS.items())[:30]])
    
    prompt = f"""
用户说："{user_input}"

请解析用户的意图，返回JSON格式。

可能的意图：
1. "生成战报" - 用户想生成战报
2. "绑定学校" - 用户想绑定学校
3. "查看绑定" - 用户想查看绑定的学校
4. "解绑学校" - 用户想解绑学校
5. "清除缓存" - 用户想清除战报缓存
6. "学校列表" - 用户想查看所有参赛学校
7. "帮助" - 用户想查看帮助
8. "闲聊" - 用户只是闲聊

如果是"生成战报"，请提取：
- school: 学校名称（从用户输入中提取，支持别名），如果没提到则用 "{bound_school}"
- week: 周数（如果有"第X周"），否则 null
- rounds: 轮次列表（如果有"第X轮"或"第X、Y轮"），否则 null

常用别名参考：
{alias_list}

只返回JSON，不要其他内容。
格式示例：
{{"intent": "生成战报", "school": "二工大", "week": null, "rounds": [3, 4]}}
{{"intent": "绑定学校", "school": "北大"}}
{{"intent": "查看绑定"}}
{{"intent": "解绑学校"}}
{{"intent": "清除缓存"}}
{{"intent": "学校列表"}}
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
# 4. 🔥 增强的帮助信息
# ============================================================

def get_help_text() -> str:
    return """📖 **战报机器人使用帮助**

**基本用法：**
@机器人 生成战报

**学校指定（临时）：**
• 生成二工大战报
• 生成北大战报
• 生成上大战报
• 生成交大战报
• 生成华师战报

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

**缓存管理（管理员）：**
• 清除缓存  ← 清除所有缓存
• 清除缓存 二工大  ← 清除指定学校缓存

**其他功能：**
• 学校列表  ← 查看所有参赛学校

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
# 5. 🔥 学校列表
# ============================================================

def get_school_list() -> str:
    """获取所有参赛学校列表（从 arena 数据中提取）"""
    try:
        from arena_fetcher import fetch_weekly_report_data, get_latest_completed_rounds
        rounds = get_latest_completed_rounds(2)
        data = fetch_weekly_report_data(rounds)
        schools = []
        for pid, team in data.get("teams", {}).items():
            schools.append(team.get("name", "未知"))
        schools.sort()
        if schools:
            return f"📋 **第五届联合杯参赛学校列表**（共 {len(schools)} 所）：\n\n" + "\n".join(f"• {s}" for s in schools)
        else:
            return "⚠️ 暂时无法获取学校列表"
    except Exception as e:
        return f"❌ 获取学校列表失败：{str(e)}"


# ============================================================
# 6. 🔥 安全执行代码（返回列表，支持合并转发）
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
        "clear_cache": clear_cache,
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
# 7. 🔥 生成代码（支持更多参数）
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
1. school_keyword: 从输入中提取学校简称（支持别名），没有则用"{school}"
2. week_number: 如果提到"第X周"、"第一周"、"首周"，提取数字；否则为 None
3. round_numbers: 如果提到"第X轮"或"第X、Y轮"，提取列表；否则为 None

常用别名：二工大→上海第二工业大，交大→上海交通大学，华师→华东师范大学

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
# 8. 🔥 核心函数（增强版）
# ============================================================

def run_agent(user_input: str, user_id: str = None):
    print(f"📩 用户输入：{user_input}")
    print(f"👤 用户ID：{user_id}")
    
    user_input_clean = user_input.strip()
    
    # ---- 1. 本地快速匹配 ----
    
    # 🔥 清除缓存
    if "清除缓存" in user_input_clean or "清缓存" in user_input_clean:
        match = re.search(r'清除缓存\s*([\u4e00-\u9fa5]{2,}?)', user_input_clean)
        if match:
            school = match.group(1).strip()
            if school:
                return clear_cache(school)
        return clear_cache()
    
    # 🔥 学校列表
    if "学校列表" in user_input_clean or "参赛学校" in user_input_clean:
        return get_school_list()
    
    # 绑定学校
    if "绑定学校" in user_input_clean:
        match = re.search(r'绑定学校\s*([\u4e00-\u9fa5]{2,}?)', user_input_clean)
        if match:
            school = match.group(1).strip()
            return set_user_school(user_id, school)
        return "⚠️ 请指定要绑定的学校，例如：绑定学校 二工大"
    
    # 查看绑定
    if "查看绑定" in user_input_clean:
        school = get_user_school(user_id, default="第二工业")
        return f"📌 你当前绑定的学校是：{school}"
    
    # 解绑学校
    if "解绑学校" in user_input_clean:
        return clear_user_school(user_id)
    
    # 帮助
    help_keywords = ["帮助", "help", "怎么用", "使用方法", "指令", "功能"]
    user_lower = user_input_clean.lower()
    if user_lower in ["帮助", "help"] or any(kw in user_lower for kw in ["怎么用", "使用方法", "指令", "功能"]):
        return get_help_text()
    
    # 问候
    if user_lower in ["你好", "hello", "hi", "hey"]:
        import random
        greetings = ["你好呀！😊", "嗨！有什么可以帮你的？", "hello！需要生成战报吗？", "我在呢！👋"]
        return random.choice(greetings)
    
    # ---- 2. 战报生成 ----
    if "生成" in user_input_clean and "战报" in user_input_clean:
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
        "学校列表",
        "清除缓存",
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