import os
import re
import json
import glob
from datetime import datetime
from typing import List, Dict, Any, Optional

# 导入战报生成函数
from match_report import generate_weekly_report_text


# ============================================================
# 1. 工具函数：提取学校关键词
# ============================================================

def extract_school_keyword(text: str, default: str = "第二工业") -> str:
    """
    从用户输入中提取学校关键词
    例如："生成二工大战报" -> "二工大"
         "生成北大战报" -> "北大"
    """
    # 常见的学校简称模式
    patterns = [
        r"生成(.+?)战报",
        r"战报(.+?)学校",
        r"查询(.+?)战报",
        r"(.+?)战报",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            keyword = match.group(1).strip()
            # 如果提取到的关键词太短或包含特殊字符，使用默认值
            if len(keyword) >= 2 and not re.search(r'[^a-zA-Z\u4e00-\u9fa5]', keyword):
                return keyword
    
    # 如果没有匹配到，返回默认值
    return default


# ============================================================
# 2. 大模型代码生成（保留原有逻辑）
# ============================================================

def generate_code_with_llm(user_input: str) -> str:
    """
    使用大模型生成代码（模拟）
    实际部署时，这里会调用大模型 API
    """
    # 这里是一个模拟的大模型响应
    # 实际使用时，请替换为真实的大模型 API 调用
    
    if "战报" in user_input:
        school_keyword = extract_school_keyword(user_input, default="第二工业")
        # 直接调用，不需要文件路径
        return f"""
print(generate_weekly_report_text(school_keyword="{school_keyword}"))
"""
    
    # 其他指令的处理...
    return """
print("抱歉，我暂时无法处理这个请求。")
"""


# ============================================================
# 3. 安全执行代码
# ============================================================

def safe_execute(code: str, globals_dict: dict = None) -> str:
    """
    安全执行生成的代码，并捕获输出
    """
    if globals_dict is None:
        globals_dict = {}
    
    # 注入必要的函数和变量
    globals_dict.update({
        "generate_weekly_report_text": generate_weekly_report_text,
        "datetime": datetime,
        "os": os,
        "json": json,
        "glob": glob,
        "print": print,
    })
    
    # 创建一个字符串IO来捕获输出
    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        # 执行代码
        exec(code, globals_dict)
        output = sys.stdout.getvalue()
        return output if output else "执行完成（无输出）"
    except Exception as e:
        return f"代码执行出错：{str(e)}"
    finally:
        sys.stdout = old_stdout


# ============================================================
# 4. 主处理函数
# ============================================================

def run_agent(user_input: str) -> str:
    """
    主处理函数：接收用户输入，返回回复内容
    """
    print(f"用户输入：{user_input}")
    
    # 1. 检查是否包含"生成战报"关键词
    if "生成" in user_input and "战报" in user_input:
        # 直接调用战报生成函数，不需要大模型
        school_keyword = extract_school_keyword(user_input, default="第二工业")
        result = generate_weekly_report_text(school_keyword=school_keyword)
        
        # 如果返回的是列表（多条消息），将其转换为字符串列表
        if isinstance(result, list):
            return result
        else:
            return str(result)
    
    # 2. 其他指令：使用大模型生成代码
    print("--- 正在请求大模型生成代码 ---")
    code = generate_code_with_llm(user_input)
    print(f"模型返回：\n{code}")
    
    # 提取代码块
    code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    else:
        # 如果不是代码块格式，尝试直接使用
        code = code.strip()
    
    print(f"--- 提取到的代码 ---\n{code}")
    print("--- 正在执行代码 ---")
    
    result = safe_execute(code)
    print(f"执行结果：{result}")
    
    return result


# ============================================================
# 5. 测试入口
# ============================================================

if __name__ == "__main__":
    # 测试用例
    test_inputs = [
        "生成二工大战报",
        "生成北大战报",
        "生成战报",
        "给我10个随机数",
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