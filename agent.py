import os
import re
import json
import glob
from datetime import datetime
from typing import List, Dict, Any, Optional

from match_report import generate_weekly_report_text


# ============================================================
# 1. 工具函数
# ============================================================

def extract_school_keyword(text: str, default: str = "第二工业") -> str:
    # 先移除周数和轮数信息
    cleaned = text
    # 移除 "第X周"
    cleaned = re.sub(r'第\d+周', '', cleaned)
    # 移除 "第X、Y轮" 或 "第X-Y轮"
    cleaned = re.sub(r'第[\d、,，\-到]+轮', '', cleaned)
    cleaned = cleaned.strip()
    
    patterns = [
        r"生成(.+?)战报",
        r"战报(.+?)学校",
        r"查询(.+?)战报",
        r"(.+?)战报",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            keyword = match.group(1).strip()
            if keyword in ["生成", "战报", "的", "个"]:
                continue
            if len(keyword) >= 2 and not re.search(r'[^a-zA-Z\u4e00-\u9fa5]', keyword):
                return keyword
    return default


def extract_week_number(text: str) -> Optional[int]:
    """从用户输入中提取周数，如 '第1周'、'第2周' """
    pattern = r'第(\d+)周'
    match = re.search(pattern, text)
    if match:
        return int(match.group(1))
    return None


def extract_round_numbers(text: str) -> Optional[List[int]]:
    """从用户输入中提取轮次，如 '第1轮'、'第3、4轮'、'第1-2轮' """
    # 匹配 "第1、2轮" 或 "第1,2轮"
    pattern1 = r'第([\d、,，]+)轮'
    match = re.search(pattern1, text)
    if match:
        parts = re.split(r'[、,，]', match.group(1))
        rounds = []
        for p in parts:
            p = p.strip()
            if p and p.isdigit():
                rounds.append(int(p))
        if rounds:
            return rounds
    
    # 匹配 "第1-2轮" 或 "第1到2轮"
    pattern2 = r'第(\d+)[-到](\d+)轮'
    match = re.search(pattern2, text)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        return list(range(start, end + 1))
    
    # 匹配 "第1轮"（单轮）
    pattern3 = r'第(\d+)轮'
    match = re.search(pattern3, text)
    if match:
        return [int(match.group(1))]
    
    return None


def generate_code_with_llm(user_input: str) -> str:
    """使用大模型生成代码（模拟）"""
    if "战报" in user_input:
        school_keyword = extract_school_keyword(user_input, default="第二工业")
        
        week_num = extract_week_number(user_input)
        if week_num is not None:
            return f"""
print(generate_weekly_report_text(school_keyword="{school_keyword}", week_number={week_num}))
"""
        
        round_nums = extract_round_numbers(user_input)
        if round_nums is not None:
            return f"""
print(generate_weekly_report_text(school_keyword="{school_keyword}", round_numbers={round_nums}))
"""
        
        return f"""
print(generate_weekly_report_text(school_keyword="{school_keyword}"))
"""
    
    return """
print("抱歉，我暂时无法处理这个请求。")
"""


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
        return output if output else "执行完成（无输出）"
    except Exception as e:
        return f"代码执行出错：{str(e)}"
    finally:
        sys.stdout = old_stdout


def run_agent(user_input: str) -> str:
    print(f"用户输入：{user_input}")
    
    if "生成" in user_input and "战报" in user_input:
        school_keyword = extract_school_keyword(user_input, default="第二工业")
        
        week_num = extract_week_number(user_input)
        if week_num is not None:
            result = generate_weekly_report_text(school_keyword=school_keyword, week_number=week_num)
            if isinstance(result, list):
                return result
            else:
                return str(result)
        
        round_nums = extract_round_numbers(user_input)
        if round_nums is not None:
            result = generate_weekly_report_text(school_keyword=school_keyword, round_numbers=round_nums)
            if isinstance(result, list):
                return result
            else:
                return str(result)
        
        result = generate_weekly_report_text(school_keyword=school_keyword)
        if isinstance(result, list):
            return result
        else:
            return str(result)
    
    print("--- 正在请求大模型生成代码 ---")
    code = generate_code_with_llm(user_input)
    print(f"模型返回：\n{code}")
    
    code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    else:
        code = code.strip()
    
    print(f"--- 提取到的代码 ---\n{code}")
    print("--- 正在执行代码 ---")
    
    result = safe_execute(code)
    print(f"执行结果：{result}")
    return result


if __name__ == "__main__":
    test_inputs = [
        "生成战报",
        "生成二工大战报",
        "生成二工大第一周战报",
        "生成第2周战报",
        "生成第1、2轮战报",
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