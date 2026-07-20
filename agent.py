import os
import re
import json
import glob
from datetime import datetime
from typing import List, Dict, Any, Optional

from match_report import generate_weekly_report_text


# ============================================================
# 1. 工具函数（简化为只做基本清理）
# ============================================================

def extract_school_keyword(text: str, default: str = "第二工业") -> str:
    """简单提取学校关键词，其余交给大模型"""
    # 移除"生成"和"战报"字样
    cleaned = text.replace("生成", "").replace("战报", "").strip()
    # 移除"第X周"、"第X轮"等
    cleaned = re.sub(r'第[\d一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'第[\d、,，\-到]+轮', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+周', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十]+轮', '', cleaned)
    cleaned = cleaned.strip()
    
    if not cleaned:
        return default
    
    # 提取2-4个字符的学校简称
    match = re.search(r'([\u4e00-\u9fa5]{2,4}大?)', cleaned)
    if match:
        return match.group(1)
    
    return default


def extract_week_number(text: str) -> Optional[int]:
    """提取周数，支持"第1周"和"第一周" """
    # "第1周"
    match = re.search(r'第(\d+)周', text)
    if match:
        return int(match.group(1))
    # "第一周"
    chinese_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    match = re.search(r'([一二三四五六七八九十]+)周', text)
    if match:
        ch = match.group(1)
        if ch in chinese_map:
            return chinese_map[ch]
    return None


def extract_round_numbers(text: str) -> Optional[List[int]]:
    """提取轮次，支持"第1轮"、"第1、2轮"、"第1-2轮" """
    # "第1、2轮"
    match = re.search(r'第([\d、,，]+)轮', text)
    if match:
        parts = re.split(r'[、,，]', match.group(1))
        rounds = [int(p.strip()) for p in parts if p.strip().isdigit()]
        if rounds:
            return rounds
    # "第1-2轮"
    match = re.search(r'第(\d+)[-到](\d+)轮', text)
    if match:
        return list(range(int(match.group(1)), int(match.group(2)) + 1))
    # "第1轮"
    match = re.search(r'第(\d+)轮', text)
    if match:
        return [int(match.group(1))]
    return None


# ============================================================
# 2. 核心函数
# ============================================================

def safe_execute(code: str, globals_dict: dict = None) -> str:
    """安全执行生成的代码"""
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
        return output if output else "执行完成（无输出）"
    except Exception as e:
        return f"代码执行出错：{str(e)}"
    finally:
        sys.stdout = old_stdout


def generate_code_with_llm(user_input: str) -> str:
    """
    大模型生成代码（模拟）
    实际部署时，这里调用真实的大模型API
    """
    # 先用本地规则简单解析，作为备用
    school = extract_school_keyword(user_input, default="第二工业")
    week = extract_week_number(user_input)
    rounds = extract_round_numbers(user_input)
    
    # 构建代码
    if week is not None:
        return f"""
print(generate_weekly_report_text(school_keyword="{school}", week_number={week}))
"""
    elif rounds is not None:
        return f"""
print(generate_weekly_report_text(school_keyword="{school}", round_numbers={rounds}))
"""
    else:
        return f"""
print(generate_weekly_report_text(school_keyword="{school}"))
"""


def run_agent(user_input: str) -> str:
    """主处理函数"""
    print(f"用户输入：{user_input}")
    
    # 检查是否与战报相关
    if "生成" in user_input and "战报" in user_input:
        print("--- 正在生成战报 ---")
        
        # 让大模型生成代码
        code = generate_code_with_llm(user_input)
        print(f"生成的代码：\n{code}")
        
        # 提取代码块
        code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
        else:
            code = code.strip()
        
        print("--- 执行代码 ---")
        result = safe_execute(code)
        print(f"执行结果：{result}")
        return result
    
    # 其他指令
    return "抱歉，我暂时无法处理这个请求。"


# ============================================================
# 3. 测试入口
# ============================================================

if __name__ == "__main__":
    test_inputs = [
        "生成二工大战报",
        "生成二工大第一周战报",
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