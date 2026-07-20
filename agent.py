import os
import re
import json
import glob
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# ============================================================
# 加载 .env 文件
# ============================================================
load_dotenv()

from match_report import generate_weekly_report_text

# ============================================================
# 配置（从环境变量读取）
# ============================================================
VOLC_ACCESS_KEY = os.getenv("VOLC_ACCESS_KEY")
VOLC_ENDPOINT_ID = os.getenv("VOLC_ENDPOINT_ID")

if not VOLC_ACCESS_KEY:
    print("⚠️ 警告：VOLC_ACCESS_KEY 未设置，大模型功能不可用")
if not VOLC_ENDPOINT_ID:
    print("⚠️ 警告：VOLC_ENDPOINT_ID 未设置，大模型功能不可用")

API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = VOLC_ENDPOINT_ID  # 使用 Endpoint ID 作为 model


# ============================================================
# 1. 工具函数（备用，当大模型不可用时使用）
# ============================================================

def extract_school_keyword(text: str, default: str = "第二工业") -> str:
    cleaned = text.replace("生成", "").replace("战报", "").strip()
    cleaned = re.sub(r'第[\d一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'第[\d、,，\-到]+轮', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+轮', '', cleaned)
    cleaned = re.sub(r'首周', '', cleaned)
    cleaned = re.sub(r'次周', '', cleaned)
    cleaned = re.sub(r'首轮', '', cleaned)
    cleaned = re.sub(r'次轮', '', cleaned)
    cleaned = cleaned.strip()
    
    if not cleaned:
        return default
    
    match = re.search(r'([\u4e00-\u9fa5]{2,4}大?)', cleaned)
    if match:
        return match.group(1)
    
    return default


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
    """调用火山引擎大模型"""
    if not VOLC_ACCESS_KEY or not VOLC_ENDPOINT_ID:
        print("⚠️ 大模型未配置，使用本地规则")
        return None
    
    headers = {
        "Authorization": f"Bearer {VOLC_ACCESS_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个代码生成助手，只输出Python代码，不要输出任何其他内容。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.1
    }
    
    try:
        resp = requests.post(API_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"⚠️ 大模型调用失败：{e}")
        return None


def generate_code_with_llm(user_input: str) -> str:
    """使用大模型解析用户输入，生成代码"""
    
    # 先尝试本地规则快速匹配（备用）
    school = extract_school_keyword(user_input, default="第二工业")
    week = extract_week_number(user_input)
    rounds = extract_round_numbers(user_input)
    
    # 如果本地规则已经明确匹配到了，直接用（更快）
    if week is not None:
        return f"""
print(generate_weekly_report_text(school_keyword="{school}", week_number={week}))
"""
    elif rounds is not None:
        return f"""
print(generate_weekly_report_text(school_keyword="{school}", round_numbers={rounds}))
"""
    
    # 否则调用大模型
    print("--- 调用大模型解析指令 ---")
    
    prompt = f"""
用户输入：{user_input}

请生成Python代码调用 generate_weekly_report_text 函数。

规则：
1. school_keyword: 从输入中提取学校简称（如"二工大"→"二工大"），没有则用"第二工业"
2. week_number: 如果提到"第X周"、"第一周"、"首周"，提取数字；否则为 None
3. round_numbers: 如果提到"第X轮"或"第X、Y轮"，提取列表；否则为 None

只返回Python代码，不要任何解释。格式如：
print(generate_weekly_report_text(school_keyword="二工大", week_number=1))
"""
    
    code = call_llm(prompt)
    
    # 如果大模型调用失败，使用本地规则兜底
    if code is None:
        print("⚠️ 大模型不可用，使用本地规则兜底")
        return f"""
print(generate_weekly_report_text(school_keyword="{school}"))
"""
    
    # 提取代码块中的代码
    code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()
    
    # 如果没有代码块标记，直接返回
    return code.strip()


# ============================================================
# 3. 核心函数
# ============================================================

def safe_execute(code: str, globals_dict: dict = None) -> str:
    if globals_dict is None:
        globals_dict = {}
    
    globals_dict.update({
        "generate_weekly_report_text": generate_weekly_report_text,
        "datetime": datetime,
        "os": os,
        "json": json,
        "glob": glob,
        "print": print,
    })
    
    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        exec(code, globals_dict)
        output = sys.stdout.getvalue()
        # 过滤调试信息
        lines = output.split('\n')
        filtered_lines = []
        for line in lines:
            if any(line.startswith(prefix) for prefix in ['📡', '📊', '📌', '✅', '⏱️', '⚠️', '❌']):
                continue
            filtered_lines.append(line)
        output = '\n'.join(filtered_lines).strip()
        return output if output else "执行完成（无输出）"
    except Exception as e:
        return f"代码执行出错：{str(e)}"
    finally:
        sys.stdout = old_stdout


def run_agent(user_input: str) -> str:
    print(f"用户输入：{user_input}")
    
    if "生成" in user_input and "战报" in user_input:
        print("--- 正在生成战报 ---")
        code = generate_code_with_llm(user_input)
        print(f"生成的代码：\n{code}")
        
        code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
        else:
            code = code.strip()
        
        print("--- 执行代码 ---")
        result = safe_execute(code)
        print(f"执行结果：{result}")
        return result
    
    return "抱歉，我暂时无法处理这个请求。"


if __name__ == "__main__":
    test_inputs = [
        "生成二工大战报",
        "生成二工大第一周战报",
        "生成二工大首周战报",
        "生成战报",
        "生成第2周战报",
        "生成第3、4轮战报",
    ]
    
    for inp in test_inputs:
        print("\n" + "="*50)
        print(f"测试输入：{inp}")
        result = run_agent(inp)
        if isinstance(result, list):
            for i, msg in enumerate(result, 1):
                print(f"消息{i}:\n{msg}\n")
        else:
            print(f"结果：{result}")