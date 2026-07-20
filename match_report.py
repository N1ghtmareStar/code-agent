import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from arena_fetcher import fetch_weekly_report_data, EAST_RANK_BONUS, SOUTH_RANK_BONUS, get_rounds_for_week, get_latest_completed_rounds

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
        
        total_str = f"+{total_score:.2f}" if total_score >= 0 else f"{total_score:.2f}"
        result_lines.append(f"•  {player_name} | {rank}位 | {score}（{total_str}）")
    
    if not result_lines:
        return "暂无详细数据"
    return "\n".join(result_lines)


def generate_weekly_report(
    school_keyword: str = "第二工业",
    week_number: Optional[int] = None,
    round_numbers: Optional[List[int]] = None,
    last_week_data: Optional[dict] = None,
    title: Optional[str] = None
) -> List[str]:
    """
    生成战报
    
    参数:
        school_keyword: 学校关键词
        week_number: 周数（1-4），如果指定则自动计算对应的轮次
        round_numbers: 指定轮次列表，如 [1, 2, 3, 4]
        last_week_data: 上周数据（用于计算增量）
        title: 自定义标题，如果不指定则自动生成
    
    优先级: round_numbers > week_number > 默认（最新两轮）
    """
    original_keyword = school_keyword
    
    # 确定轮次
    if round_numbers is not None:
        target_rounds = round_numbers
    elif week_number is not None:
        target_rounds = get_rounds_for_week(week_number)
    else:
        # 默认：获取最新已完成的两轮
        target_rounds = get_latest_completed_rounds(2)
    
    try:
        arena_data = fetch_weekly_report_data(target_rounds)
    except Exception as e:
        return [f"❌ 从 Arena 获取数据失败：{str(e)}"]
    
    school_name, school_data = find_school_in_arena(arena_data, school_keyword)
    if not school_data:
        return [f"❌ 未找到学校：'{original_keyword}' 未参加第五届联合杯，或学校名称不匹配。"]
    
    # 上周数据
    last_total = 0.0
    if last_week_data:
        last_team = find_school_in_arena(last_week_data, school_keyword)
        if last_team and last_team[1]:
            last_total = last_team[1].get("total_score", 0.0)
    
    east = school_data.get("east", {})
    south = school_data.get("south", {})
    total_score = school_data.get("total_score", 0.0)
    final_rank = school_data.get("final_rank", 0)
    
    delta_total = total_score - last_total
    delta_east = east.get("total_score", 0.0)
    delta_south = south.get("total_score", 0.0)
    rank_desc = "持平"
    
    # 生成标题
    if title:
        week_title = title
    elif week_number is not None:
        week_title = f"第{week_number}周战报"
    else:
        round_str = f"第{target_rounds[0]}-{target_rounds[-1]}轮" if len(target_rounds) > 1 else f"第{target_rounds[0]}轮"
        week_title = f"{round_str}战报"
    
    east_details = east.get("details", [])
    south_details = south.get("details", [])
    east_detail = format_details_from_arena(east_details, EAST_RANK_BONUS)
    south_detail = format_details_from_arena(south_details, SOUTH_RANK_BONUS)
    
    msg1 = f"""📊 第五届联合杯 · {week_title}

🏫 参赛学校：{school_name}
📅 报告生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}

─────────────────────────────
📈 本周战况：
•  上周累计分数：{last_total:.1f} 分
•  本周新增分数：{delta_total:+.1f} 分
•  当前累计分数：{total_score:.1f} 分
•  当前排名：第 {final_rank} 名（{rank_desc}）"""

    msg2 = f"""🀀 东风赛道：{east.get('total_score', 0):.1f} 分（{delta_east:+.1f} 分）
•  顺位：1位{east.get('rank_1', 0)}次 / 2位{east.get('rank_2', 0)}次 / 3位{east.get('rank_3', 0)}次 / 4位{east.get('rank_4', 0)}次

─────────────────────────────
📌 本周明细（东风）：
{east_detail}"""

    msg3 = f"""🀁 半庄赛道：{south.get('total_score', 0):.1f} 分（{delta_south:+.1f} 分）
•  顺位：1位{south.get('rank_1', 0)}次 / 2位{south.get('rank_2', 0)}次 / 3位{south.get('rank_3', 0)}次 / 4位{south.get('rank_4', 0)}次

─────────────────────────────
📌 本周明细（半庄）：
{south_detail}"""

    return [msg1, msg2, msg3]


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    try:
        print("\n=== 测试1：默认（最新两轮）===")
        reports = generate_weekly_report(school_keyword="第二工业")
        for i, msg in enumerate(reports, 1):
            print(f"消息{i}:\n{msg}\n")
        
        print("\n=== 测试2：第1周（第1、2轮）===")
        reports_week1 = generate_weekly_report(school_keyword="第二工业", week_number=1)
        for i, msg in enumerate(reports_week1, 1):
            print(f"消息{i}:\n{msg}\n")
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()


generate_weekly_report_text = generate_weekly_report