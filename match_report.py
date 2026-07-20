import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from arena_fetcher import fetch_weekly_report_data, EAST_RANK_BONUS, SOUTH_RANK_BONUS, get_rounds_for_week, get_latest_completed_rounds


def get_prev_rounds(current_rounds: List[int]) -> List[int]:
    if not current_rounds:
        return []
    min_round = min(current_rounds)
    if min_round <= 1:
        return []
    prev_rounds = [r - 2 for r in current_rounds if r - 2 >= 1]
    return prev_rounds if prev_rounds else []


def get_week_from_rounds(rounds: List[int]) -> Optional[int]:
    if not rounds:
        return None
    min_round = min(rounds)
    week = (min_round - 1) // 2 + 1
    return week


# ============================================================
# 别名映射表
# ============================================================
SCHOOL_ALIAS = {
    "北大": "北京大学",
    "上大": "上海大学",
    "北邮": "北京邮电大学",
    "北航": "北京航空航天大",
    "北航大": "北京航空航天大",
    "川大": "四川大学",
    "中农": "中国农业大学",
    "中农大": "中国农业大学",
    "安农": "安徽农业大学",
    "安农大": "安徽农业大学",
    "清华": "清华大学",
    "西交": "西安交通大学",
    "西交大": "西安交通大学",
    "中大": "中山大学",
    "复旦": "复旦大学",
    "大工": "大连理工大学",
    "大工大": "大连理工大学",
    "对外经贸": "对外经济贸易大",
    "外经贸": "对外经济贸易大",
    "上电": "上海电力大学",
    "山财": "山东财经大学",
    "华科": "华中科技大学",
    "华中大": "华中科技大学",
    "同济": "同济大学",
    "北师大": "北京师范大学",
    "北师": "北京师范大学",
    "广大": "广州大学",
    "西工大": "西北工业大学",
    "西电": "西安电子科技大",
    "华工": "华南理工大学",
    "华南理工": "华南理工大学",
    "上工程": "上海工程技术大",
    "工程大": "上海工程技术大",
    "南宁二中": "南宁市第二中学",
    "哈医大": "哈尔滨医科大学",
    "福医大": "福建医科大学",
    "南开": "南开大学",
    "中央民大": "中央民族大学",
    "民大": "中央民族大学",
    "华南师大": "华南师范大学",
    "华师": "华南师范大学",
    "郑大": "郑州大学",
    "宁诺": "宁波诺丁汉大学",
    "华农": "华南农业大学",
    "福大": "福州大学",
    "东大": "东北大学",
    "中南财大": "中南财经政法大",
    "中南财经": "中南财经政法大",
    "二工大": "上海第二工业大",
    "上二工大": "上海第二工业大",
    "北交": "北京交通大学",
    "北交大": "北京交通大学",
    "上交": "上海交通大学",
    "上交大": "上海交通大学",
    "华东理工": "华东理工大学",
    "华理": "华东理工大学",
    "北理": "北京理工大学",
    "北理工": "北京理工大学",
    "河海": "河海大学",
    "西大": "广西大学",
    "武大": "武汉大学",
    "建桥": "上海建桥学院",
    "建桥学院": "上海建桥学院",
    "汕大": "汕头大学",
    "大外": "大连外国语大学",
    "西农": "西北农林科技大",
    "西北农大": "西北农林科技大",
    "中南": "中南大学",
    "东农": "东北农业大学",
    "东北农大": "东北农业大学",
    "哈工大": "哈尔滨工业大学",
    "天大": "天津大学",
    "江大": "江南大学",
    "华东师大": "华东师范大学",
    "吉大": "吉林大学",
    "上财": "上海财经大学",
    "南航": "南京航空航天大",
    "上师": "上海师范大学",
    "上师大": "上海师范大学",
    "南科": "南方科技大学",
    "南科大": "南方科技大学",
    "宁大": "宁波大学",
    "东林": "东北林业大学",
    "太理": "太原理工大学",
    "太原理工": "太原理工大学",
    "南大": "南京大学",
    "北信": "北京信息科技大",
    "北信科": "北京信息科技大学",
}


def resolve_school_alias(keyword: str) -> str:
    keyword = keyword.strip()
    if keyword in SCHOOL_ALIAS:
        return SCHOOL_ALIAS[keyword]
    if keyword.endswith("大"):
        return keyword[:-1] + "大学"
    return keyword


def find_school_in_arena(data: dict, school_keyword: str) -> Tuple[Optional[str], Optional[dict]]:
    school_keyword = school_keyword.strip()
    if not school_keyword:
        return None, None
    
    resolved = resolve_school_alias(school_keyword)
    
    best_match = None
    best_name = None
    best_score = 0
    
    for pid, team_data in data["teams"].items():
        name = team_data["name"]
        score = 0
        if resolved in name:
            score = 3
        elif school_keyword in name:
            score = 2
        elif any(alias in name for alias in SCHOOL_ALIAS.keys() if school_keyword in alias):
            score = 1
        
        if score > best_score:
            best_score = score
            best_match = team_data
            best_name = name
        elif score == best_score and best_score > 0:
            if len(name) < len(best_name):
                best_match = team_data
                best_name = name
    
    return best_name, best_match


def format_details_from_arena(details: List[dict], rank_bonus: Dict[int, int]) -> str:
    if not details:
        return "暂无详细数据"
    
    result_lines = []
    for item in details:
        player_name = item.get("player_name", "未知选手")
        rank = item.get("rank", 0)
        score = item.get("score", 0)
        alap_score = (score - 25000) / 1000.0
        rank_point = rank_bonus.get(rank, 0)
        total_score = alap_score + rank_point
        
        total_str = f"+{total_score:.1f}" if total_score >= 0 else f"{total_score:.1f}"
        result_lines.append(f"•  {player_name} | {rank}位 | {score}（{total_str}）")
    
    if not result_lines:
        return "暂无详细数据"
    return "\n".join(result_lines)


# ============================================================
# 🔥 新增：消息截断（防止长战报被QQ吞掉）
# ============================================================
MAX_MSG_LENGTH = 1800  # QQ群消息限制约2000字，留200字余量


def truncate_message(msg: str) -> str:
    """截断过长的消息"""
    if len(msg) <= MAX_MSG_LENGTH:
        return msg
    return msg[:MAX_MSG_LENGTH - 50] + "\n\n... (内容过长已截断)"


# ============================================================
# 🔥 新增：统一异常处理
# ============================================================
class ReportError(Exception):
    pass


def generate_weekly_report(
    school_keyword: str = "第二工业",
    week_number: Optional[int] = None,
    round_numbers: Optional[List[int]] = None,
    last_week_data: Optional[dict] = None,
    title: Optional[str] = None
) -> List[str]:
    """
    生成战报
    """
    original_keyword = school_keyword
    
    # 确定轮次
    if round_numbers is not None:
        target_rounds = round_numbers
    elif week_number is not None:
        target_rounds = get_rounds_for_week(week_number)
    else:
        target_rounds = get_latest_completed_rounds(2)
    
    try:
        arena_data = fetch_weekly_report_data(target_rounds)
    except Exception as e:
        return [f"❌ 从 Arena 获取数据失败：{str(e)}"]
    
    school_name, school_data = find_school_in_arena(arena_data, school_keyword)
    if not school_data:
        return [f"❌ 未找到学校：'{original_keyword}' 未参加第五届联合杯，或学校名称不匹配。"]
    
    # ---- 判断模式 ----
    is_single_round = len(target_rounds) == 1
    is_cumulative = len(target_rounds) > 2
    
    if is_cumulative:
        round_label = "累计"
        prev_label = ""
    else:
        round_label = "本轮" if is_single_round else "本周"
        prev_label = "上轮" if is_single_round else "上周"
    
    # ---- 获取上一轮/周数据 ----
    last_final_rank = 0
    if last_week_data is None and not is_cumulative:
        if is_single_round:
            prev_round = target_rounds[0] - 1
            if prev_round >= 1:
                try:
                    prev_data = fetch_weekly_report_data([prev_round])
                    last_week_data = prev_data
                except:
                    last_week_data = None
        else:
            prev_rounds = get_prev_rounds(target_rounds)
            if prev_rounds:
                try:
                    prev_data = fetch_weekly_report_data(prev_rounds)
                    last_week_data = prev_data
                except:
                    last_week_data = None
    
    if last_week_data:
        last_team = find_school_in_arena(last_week_data, school_keyword)
        if last_team and last_team[1]:
            last_final_rank = last_team[1].get("final_rank", 0)
    
    # ---- 当前数据 ----
    east = school_data.get("east", {})
    south = school_data.get("south", {})
    total_score = school_data.get("total_score", 0.0)
    final_rank = school_data.get("final_rank", 0)
    
    east_round_total = sum(score for round_num, score in east.get("round_scores", {}).items() if round_num in target_rounds)
    south_round_total = sum(score for round_num, score in south.get("round_scores", {}).items() if round_num in target_rounds)
    delta_total = east_round_total + south_round_total
    
    last_total = total_score - delta_total
    
    if last_final_rank == 0:
        rank_desc = "持平"
    elif final_rank < last_final_rank:
        rank_desc = f"↑ {last_final_rank - final_rank}"
    elif final_rank > last_final_rank:
        rank_desc = f"↓ {final_rank - last_final_rank}"
    else:
        rank_desc = "持平"
    
    promotion_line = arena_data.get("promotion_line", 0.0)
    if promotion_line > 0:
        diff = total_score - promotion_line
        if diff > 0:
            promotion_text = f"•  超过晋级线：{diff:.1f} 分"
        elif diff == 0:
            promotion_text = "•  正好在晋级线上"
        else:
            promotion_text = f"•  距离晋级线还差：{-diff:.1f} 分"
    else:
        promotion_text = "•  晋级线：暂无数据"
    
    # ---- 生成标题 ----
    if title:
        week_title = title
    elif round_numbers is not None:
        if len(target_rounds) == 1:
            week_title = f"第{target_rounds[0]}轮战报"
        else:
            week_title = f"第{target_rounds[0]}-{target_rounds[-1]}轮战报"
    elif week_number is not None:
        week_title = f"第{week_number}周战报"
    else:
        detected_week = get_week_from_rounds(target_rounds)
        if detected_week is not None and len(target_rounds) == 2:
            week_title = f"第{detected_week}周战报"
        else:
            round_str = f"第{target_rounds[0]}-{target_rounds[-1]}轮" if len(target_rounds) > 1 else f"第{target_rounds[0]}轮"
            week_title = f"{round_str}战报"
    
    # 过滤明细
    east_details = [d for d in east.get("details", []) if d.get("round") in target_rounds]
    south_details = [d for d in south.get("details", []) if d.get("round") in target_rounds]
    
    east_detail = format_details_from_arena(east_details, EAST_RANK_BONUS)
    south_detail = format_details_from_arena(south_details, SOUTH_RANK_BONUS)
    
    east_rank_1 = sum(1 for d in east_details if d.get("rank") == 1)
    east_rank_2 = sum(1 for d in east_details if d.get("rank") == 2)
    east_rank_3 = sum(1 for d in east_details if d.get("rank") == 3)
    east_rank_4 = sum(1 for d in east_details if d.get("rank") == 4)
    
    south_rank_1 = sum(1 for d in south_details if d.get("rank") == 1)
    south_rank_2 = sum(1 for d in south_details if d.get("rank") == 2)
    south_rank_3 = sum(1 for d in south_details if d.get("rank") == 3)
    south_rank_4 = sum(1 for d in south_details if d.get("rank") == 4)
    
    # ===== 消息1 =====
    if is_cumulative:
        msg1 = f"""📊 第五届联合杯 · {week_title}

🏫 参赛学校：{school_name}
📅 报告生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}

─────────────────────────────
📈 累计战况：
•  累计总分数：{total_score:.1f} 分
•  当前排名：第 {final_rank} 名（{rank_desc}）
{promotion_text}"""
    else:
        msg1 = f"""📊 第五届联合杯 · {week_title}

🏫 参赛学校：{school_name}
📅 报告生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}

─────────────────────────────
📈 {round_label}战况：
•  {prev_label}累计分数：{last_total:.1f} 分
•  {round_label}新增分数：{delta_total:+.1f} 分
•  当前累计分数：{total_score:.1f} 分
•  当前排名：第 {final_rank} 名（{rank_desc}）
{promotion_text}"""
    
    # ===== 消息2 =====
    east_total = east.get('total_score', 0.0)
    msg2 = f"""🀀 东风赛道：{east_total:.1f} 分（{east_round_total:+.1f}）
•  顺位：1位{east_rank_1}次 / 2位{east_rank_2}次 / 3位{east_rank_3}次 / 4位{east_rank_4}次

─────────────────────────────
📌 {round_label}明细（东风）：
{east_detail}"""

    # ===== 消息3 =====
    south_total = south.get('total_score', 0.0)
    msg3 = f"""🀁 半庄赛道：{south_total:.1f} 分（{south_round_total:+.1f}）
•  顺位：1位{south_rank_1}次 / 2位{south_rank_2}次 / 3位{south_rank_3}次 / 4位{south_rank_4}次

─────────────────────────────
📌 {round_label}明细（半庄）：
{south_detail}"""

    messages = [msg1, msg2, msg3]
    
    # 🔥 截断过长消息
    messages = [truncate_message(msg) for msg in messages]
    
    return messages


generate_weekly_report_text = generate_weekly_report


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    try:
        print("\n=== 测试：默认最新战报 ===")
        reports = generate_weekly_report(school_keyword="第二工业")
        for i, msg in enumerate(reports, 1):
            print(f"消息{i}:\n{msg}\n")
        
        print("\n=== 测试：第4轮（单轮）===")
        reports_round4 = generate_weekly_report(school_keyword="第二工业", round_numbers=[4])
        for i, msg in enumerate(reports_round4, 1):
            print(f"消息{i}:\n{msg}\n")
        
        print("\n=== 测试：第1-4轮（累计模式）===")
        reports_1_4 = generate_weekly_report(school_keyword="第二工业", round_numbers=[1, 2, 3, 4])
        for i, msg in enumerate(reports_1_4, 1):
            print(f"消息{i}:\n{msg}\n")
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()