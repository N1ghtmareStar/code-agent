import os
import json
import requests
import io
import contextlib
from dotenv import load_dotenv

# 导入战报生成函数
from match_report import generate_weekly_report_text

load_dotenv()

# ========== 1. 调用火山引擎豆包大模型 ==========
def call_llm(messages):
    api_key = os.getenv("VOLC_ACCESS_KEY")
    if not api_key:
        raise ValueError("请在 .env 文件中设置 VOLC_ACCESS_KEY")
    
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "doubao-1.5-pro-32k-250115",
        "messages": messages,
        "temperature": 0.1
    }
    response = requests.post(url, headers=headers, json=data, timeout=30)
    result = response.json()
    if "choices" not in result:
        print("API返回错误：", result)
        return None
    return result["choices"][0]["message"]["content"]

# ========== 2. 安全执行代码（沙箱） ==========
def execute_code_safe(code_string: str) -> str:
    DANGEROUS_NAMES = [
        'open', 'eval', 'exec', 'execfile', 'compile',
        '__import__', 'globals', 'locals', 'vars',
        'dir', 'help', 'input', 'memoryview',
        'breakpoint', 'exit', 'quit',
        'os', 'subprocess', 'sys', 'shutil',
        'socket', 'urllib', 'requests',
    ]
    safe_builtins = {}
    
    # 兼容 __builtins__ 可能是模块或字典
    if hasattr(__builtins__, '__dict__'):
        for name, value in __builtins__.__dict__.items():
            if name not in DANGEROUS_NAMES:
                safe_builtins[name] = value
    elif isinstance(__builtins__, dict):
        for name, value in __builtins__.items():
            if name not in DANGEROUS_NAMES:
                safe_builtins[name] = value
    else:
        safe_builtins = {}
    
    safe_builtins['input'] = input

    safe_modules = {
        'math': __import__('math'),
        'random': __import__('random'),
        'datetime': __import__('datetime'),
        'json': __import__('json'),
        're': __import__('re'),
        'collections': __import__('collections'),
        'itertools': __import__('itertools'),
        'functools': __import__('functools'),
        'string': __import__('string'),
        'glob': __import__('glob'),
    }
    
    safe_globals = {
        '__builtins__': safe_builtins,
        '__name__': '__sandbox__',
        **safe_modules,
        'generate_weekly_report_text': generate_weekly_report_text,
    }
    
    output_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(code_string, safe_globals)
        result = output_buffer.getvalue()
        return result or "代码执行成功，但没有输出。"
    except Exception as e:
        return f"代码执行出错：{str(e)}"

# ========== 3. Agent 主逻辑 ==========
def run_agent(user_input):
    system_prompt = (
        "你是一个专业的 Python 代码生成助手。根据用户需求，生成可直接运行的 Python 代码。\n"
        "\n"
        "## 可用的自定义函数\n"
        "你可以调用以下预置函数，它们已经导入并可用：\n"
        "\n"
        "1. `generate_weekly_report_text(current_week_file, school_keyword=\"第二工业\", last_week_file=None, week_number=None)`\n"
        "   - 功能：根据 Excel 文件生成赛事战报\n"
        "   - 参数：\n"
        "     - current_week_file: 本周 Excel 文件路径（必需），例如 \"20260712_第1周.xlsx\"\n"
        "     - school_keyword: 学校关键词，默认 \"第二工业\"\n"
        "     - last_week_file: 上周 Excel 文件路径（可选），用于对比周度变化\n"
        "     - week_number: 周次（可选），不提供则自动从文件名提取\n"
        "   - 返回值：格式化的战报文本\n"
        "\n"
        "2. 你可以使用 `glob` 模块来查找当前目录下的文件：\n"
        "   - `glob` 已经预先导入，可直接使用 `glob.glob(\"*.xlsx\")`，无需写 `import glob`\n"
        "\n"
        "## 核心规则\n"
        "1. 只输出代码，不要有任何解释。用 ```python 和 ``` 包裹。\n"
        "2. 使用 `print()` 输出结果。\n"
        "3. 遇到需要生成战报的任务时，必须调用 `generate_weekly_report_text` 函数。\n"
        "4. 如果用户没有指定文件名，使用 `glob.glob(\"*.xlsx\")` 自动查找当前目录下的 Excel 文件，取最新的（排序后取最后一个）。\n"
        "5. 禁止使用任何 `import` 语句，因为所需模块（如 glob）已经预先导入，可以直接使用。\n"
        "\n"
        "## 示例\n"
        "用户需求：生成战报\n"
        "```python\n"
        "files = glob.glob(\"*.xlsx\")\n"
        "if files:\n"
        "    latest_file = sorted(files)[-1]\n"
        "    print(generate_weekly_report_text(latest_file))\n"
        "else:\n"
        "    print(\"未找到 Excel 文件\")\n"
        "```\n"
        "\n"
        "用户需求：" + user_input
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    print(f"用户输入：{user_input}")
    print("\n--- 正在请求大模型生成代码 ---")
    
    llm_response = call_llm(messages)
    if not llm_response:
        return "大模型返回为空，请检查网络或API配置。"
    
    print("模型返回：\n", llm_response)
    
    if "```python" in llm_response and "```" in llm_response:
        code_start = llm_response.find("```python") + 9
        code_end = llm_response.find("```", code_start)
        code_to_execute = llm_response[code_start:code_end].strip()
    else:
        code_to_execute = llm_response.strip()
    
    print("\n--- 提取到的代码 ---")
    print(code_to_execute)
    print("\n--- 正在执行代码 ---")
    
    result = execute_code_safe(code_to_execute)
    print("执行结果：", result)
    return result

# ========== 4. 交互式启动 ==========
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 代码生成型 Agent 已启动")
    print("输入 'exit' 或 'quit' 退出程序")
    print("=" * 50)
    
    while True:
        user_input = input("\n💬 请输入你的需求：")
        if user_input.lower() in ['exit', 'quit', 'q']:
            print("👋 再见！")
            break
        if not user_input.strip():
            print("⚠️ 请输入有效内容")
            continue
        print("\n" + "-" * 30)
        run_agent(user_input)
        print("-" * 30)