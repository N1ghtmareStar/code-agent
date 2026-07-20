import requests
import json
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
ARENA_BASE = "https://arena.pesiu.org"
EAST_SCORE_VIEW_ID = "6a52b2d3f7292de3bc3c25d5"
SOUTH_SCORE_VIEW_ID = "6a527ee23b56c4a692c6b0c6"
CONTEST_ID = "6a5265acf78ec7d0138baa2d"
EAST_TRACK_ID = "6a5265acf78ec7d0138baa2e"
SOUTH_TRACK_ID = "6a526941f78ec7d0138baa33"

# ============================================================
# 顺位点（规则书第3.1、3.2节）
# ============================================================
EAST_RANK_BONUS = {1: 27, 2: 3, 3: -9, 4: -21}
SOUTH_RANK_BONUS = {1: 45, 2: 5, 3: -15, 4: -35}

# 学校名称修正映射
SCHOOL_NAME_FIX = {
    "上海第二工业大": "上海第二工业大学",
    "北京航空航天大": "北京航空航天大学",
    "北京信息科技大": "北京信息科技大学",
    "上海工程技术大": "上海工程技术大学",
    "南京航空航天大": "南京航空航天大学",
    "西安电子科技大": "西安电子科技大学",
    "西北农林科技大": "西北农林科技大学",
    "中南财经政法大": "中南财经政法大学",
    "对外经济贸易大": "对外经济贸易大学",
}

# 每周对应的轮次（常规赛：每周2轮）
WEEK_ROUNDS = {
    1: [1, 2],
    2: [3, 4],
    3: [5, 6],
    4: [7, 8],
}


# ============================================================
# 数据获取
# ============================================================

def fetch_score_view(score_view_id: str) -> dict:
    """获取指定 score-view 的完整数据"""
    url = f"{ARENA_BASE}/api/score-views/{score_view_id}/input"
    print(f"📡 正在请求: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_participants(contest_id: str) -> Dict[str, str]:
    """获取参赛方列表，返回 { participantId: school_name } 映射"""
    url = f"{ARENA_BASE}/api/contests/{contest_id}/participants"
    print(f"📡 正在请求参赛方列表: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    name_map = {}
    for item in data.get("items", []):
        pid = item.get("id")
        name = item.get("name", "")
        if pid and name:
            if name in SCHOOL_NAME_FIX:
                name = SCHOOL_NAME_FIX[name]
            name_map[pid] = name
    
    print(f"✅ 获取到 {len(name_map)} 个参赛方名称")
    return name_map


def fetch_contest_data() -> Tuple[dict, dict, Dict[str, str]]:
    """获取东风、半庄赛道数据以及参赛方名称映射"""
    east_data = fetch_score_view(EAST_SCORE_VIEW_ID)
    south_data = fetch_score_view(SOUTH_SCORE_VIEW_ID)
    participants = fetch_participants(CONTEST_ID)
    return east_data, south_data, participants


# ============================================================
# 计算单场完整得分
# ============================================================

def calc_single_game_score(score: int, rank: int, rank_bonus: Dict[int, int]) -> float:
    """
    单场完整得分 = 精算点 + 顺位点
    精算点 = (完场点数 - 25000) / 1000
    """
    alap_score = (score - 25000) / 1000.0
    rank_point = rank_bonus.get(rank, 0)
    return alap_score + rank_point


# ============================================================
# 获取已完成轮次
# ============================================================

def get_latest_completed_rounds(round_count: int = 2) -> List[int]:
    """
    获取最近已完成的轮次（status == 'finished'）
    """
    east_data = fetch_score_view(EAST_SCORE_VIEW_ID)
    completed_rounds = []
    
    # 从 rounds 中获取状态为 finished 的轮次
    for round_info in east_data.get("rounds", []):
        round_num = round_info.get("number")
        status = round_info.get("status")
        if round_num is not None and status == "finished":
            completed_rounds.append(round_num)
    
    sorted_rounds = sorted(completed_rounds)
    # 返回最近的 round_count 轮
    return sorted_rounds[-round_count:] if sorted_rounds else []


def get_rounds_for_week(week_number: int) -> List[int]:
    """
    根据周数获取对应的轮次
    """
    if week_number in WEEK_ROUNDS:
        return WEEK_ROUNDS[week_number]
    # 如果周数超出定义范围，尝试计算：第1周=1,2轮，第2周=3,4轮，以此类推
    start_round = (week_number - 1) * 2 + 1
    return [start_round, start_round + 1]


# ============================================================
# 数据解析：按赛道、轮次聚合（支持轮次过滤）
# ============================================================

def parse_rounds_and_scores(data: dict, track_id: str, rank_bonus: Dict[int, int], round_filter: Optional[List[int]] = None) -> Dict[int, Dict[str, dict]]:
    """
    解析指定赛道，支持按轮次过滤
    round_filter: 指定要包含的轮次列表，如 [1, 2, 3, 4]
    """
    round_data = defaultdict(lambda: defaultdict(lambda: {"total_score": 0.0, "rank": 0, "details": []}))
    stages = data.get("stages", [])
    stage_track_map = {s.get("id"): s.get("trackId") for s in stages}
    
    for match in data.get("matches", []):
        if stage_track_map.get(match.get("stageId")) != track_id:
            continue
        
        round_num = match.get("roundNumber")
        if round_num is None:
            continue
        
        # 如果指定了轮次过滤，跳过不在列表中的轮次
        if round_filter is not None and round_num not in round_filter:
            continue
        
        for game in match.get("games", []):
            for player in game.get("players", []):
                pid = player.get("participantId")
                score = player.get("score", 0)
                rank = player.get("rank", 0)
                player_name = player.get("snapshot", {}).get("nickname", "未知选手")
                if pid:
                    single_score = calc_single_game_score(score, rank, rank_bonus)
                    round_data[round_num][pid]["total_score"] += single_score
                    round_data[round_num][pid]["rank"] = rank
                    round_data[round_num][pid]["details"].append({
                        "player_name": player_name,
                        "score": score,
                        "rank": rank,
                        "single_score": single_score
                    })
    
    return round_data


def calculate_team_scores(round_data: Dict[int, Dict[str, dict]]) -> Dict[str, dict]:
    """
    计算每个队伍的总分、顺位分布和明细
    """
    team_data = defaultdict(lambda: {
        "total_score": 0.0,
        "rank_1": 0,
        "rank_2": 0,
        "rank_3": 0,
        "rank_4": 0,
        "details": []
    })
    
    for round_num, participants in round_data.items():
        for pid, data in participants.items():
            total = data["total_score"]
            rank = data["rank"]
            details = data["details"]
            
            team_data[pid]["total_score"] += total
            team_data[pid]["details"].extend(details)
            
            if rank == 1:
                team_data[pid]["rank_1"] += 1
            elif rank == 2:
                team_data[pid]["rank_2"] += 1
            elif rank == 3:
                team_data[pid]["rank_3"] += 1
            elif rank == 4:
                team_data[pid]["rank_4"] += 1
    
    return dict(team_data)


# ============================================================
# 主函数
# ============================================================

def fetch_weekly_report_data(round_filter: Optional[List[int]] = None) -> dict:
    """
    从 Arena 获取数据，支持按轮次过滤
    round_filter: 指定要包含的轮次列表，如 [1, 2] 表示第1、2轮
    """
    print("📊 开始从 Arena 获取数据...")
    if round_filter:
        print(f"📌 过滤轮次: 第 {', '.join(map(str, round_filter))} 轮")
    
    east_data, south_data, participants = fetch_contest_data()
    
    east_rounds = parse_rounds_and_scores(east_data, EAST_TRACK_ID, EAST_RANK_BONUS, round_filter)
    south_rounds = parse_rounds_and_scores(south_data, SOUTH_TRACK_ID, SOUTH_RANK_BONUS, round_filter)
    
    east_scores = calculate_team_scores(east_rounds)
    south_scores = calculate_team_scores(south_rounds)
    
    all_participants = set(east_scores.keys()) | set(south_scores.keys())
    
    result = {
        "contest_name": east_data.get("contest", {}).get("name", "联合杯"),
        "current_round": east_data.get("phases", [{}])[0].get("activeRoundNumber", 0),
        "teams": {},
        "rankings": []
    }
    
    for pid in all_participants:
        east = east_scores.get(pid, {"total_score": 0, "rank_1": 0, "rank_2": 0, "rank_3": 0, "rank_4": 0, "details": []})
        south = south_scores.get(pid, {"total_score": 0, "rank_1": 0, "rank_2": 0, "rank_3": 0, "rank_4": 0, "details": []})
        
        total = east["total_score"] + south["total_score"]
        name = participants.get(pid, pid[:8] + "...")
        
        result["teams"][pid] = {
            "name": name,
            "east": east,
            "south": south,
            "total_score": round(total, 1)
        }
    
    sorted_teams = sorted(
        result["teams"].items(),
        key=lambda x: x[1]["total_score"],
        reverse=True
    )
    for rank, (pid, data) in enumerate(sorted_teams, 1):
        data["final_rank"] = rank
        result["rankings"].append((pid, data["total_score"]))
    
    print(f"✅ 成功获取 {len(result['teams'])} 个队伍的数据")
    return result


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    try:
        print("\n=== 测试1：获取最新两轮 ===")
        latest_rounds = get_latest_completed_rounds(2)
        print(f"📌 最新已完成轮次: {latest_rounds}")
        data = fetch_weekly_report_data(latest_rounds)
        print(f"📋 比赛: {data['contest_name']}")
        print(f"📌 包含轮次: {latest_rounds}")
        print(f"🏫 参赛队伍: {len(data['teams'])} 个")
        
        # 检查上海第二工业大学
        for pid, team in data['teams'].items():
            if "第二工业" in team['name']:
                print(f"  ✅ {team['name']}: {team['total_score']:.1f} 分")
        
        print("\n=== 测试2：获取第1周战报（第1、2轮）===")
        week1_rounds = get_rounds_for_week(1)
        data_week1 = fetch_weekly_report_data(week1_rounds)
        for pid, team in data_week1['teams'].items():
            if "第二工业" in team['name']:
                print(f"  ✅ {team['name']}: {team['total_score']:.1f} 分")
        
        with open("arena_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 完整数据已保存到 arena_data.json")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()