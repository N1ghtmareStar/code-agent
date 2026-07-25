import requests
import json
import time
import re
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

REQUEST_TIMEOUT = 30
MAX_RETRIES = 2

# ============================================================
# 顺位点
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

WEEK_ROUNDS = {1: [1, 2], 2: [3, 4], 3: [5, 6], 4: [7, 8]}

# ============================================================
# 全局开关
# ============================================================
DEBUG = False


def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


# ============================================================
# 清洗函数
# ============================================================

def clean_name(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = re.sub(r'[\u3164\u200b\u200c\u200d\u2060\uFEFF\u00A0\u3000]', '', text)
    return text.strip()


# ============================================================
# 带重试的请求函数
# ============================================================

def fetch_with_retry(url: str, max_retries: int = MAX_RETRIES, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            debug_print(f"⏱️ 请求超时，第 {attempt + 1}/{max_retries} 次重试...")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                raise Exception(f"请求超时")
        except requests.exceptions.RequestException as e:
            debug_print(f"⚠️ 请求失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                raise


# ============================================================
# 数据获取（带缓存）
# ============================================================

_cache = {}


def fetch_score_view(score_view_id: str) -> dict:
    if score_view_id in _cache:
        debug_print(f"📦 使用缓存: {score_view_id}")
        return _cache[score_view_id]
    
    url = f"{ARENA_BASE}/api/score-views/{score_view_id}/input"
    debug_print(f"📡 正在请求: {url}")
    resp = fetch_with_retry(url)
    data = resp.json()
    _cache[score_view_id] = data
    return data


def fetch_participants(contest_id: str) -> Dict[str, str]:
    cache_key = f"participants_{contest_id}"
    if cache_key in _cache:
        debug_print("📦 使用缓存的参赛方列表")
        return _cache[cache_key]
    
    url = f"{ARENA_BASE}/api/contests/{contest_id}/participants"
    debug_print(f"📡 正在请求参赛方列表: {url}")
    resp = fetch_with_retry(url)
    data = resp.json()
    
    name_map = {}
    for item in data.get("items", []):
        pid = item.get("id")
        name = item.get("name", "")
        if pid and name:
            name = clean_name(name)
            if name in SCHOOL_NAME_FIX:
                name = SCHOOL_NAME_FIX[name]
            name_map[pid] = name
    
    _cache[cache_key] = name_map
    debug_print(f"✅ 获取到 {len(name_map)} 个参赛方名称")
    return name_map


def fetch_contest_data() -> Tuple[dict, dict, Dict[str, str]]:
    import concurrent.futures
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        east_future = executor.submit(fetch_score_view, EAST_SCORE_VIEW_ID)
        south_future = executor.submit(fetch_score_view, SOUTH_SCORE_VIEW_ID)
        participants_future = executor.submit(fetch_participants, CONTEST_ID)
        
        east_data = east_future.result()
        south_data = south_future.result()
        participants = participants_future.result()
    
    return east_data, south_data, participants


def clear_cache():
    global _cache
    _cache = {}


# ============================================================
# 计算单场完整得分
# ============================================================

def calc_single_game_score(score: int, rank: int, rank_bonus: Dict[int, int]) -> float:
    alap_score = (score - 25000) / 1000.0
    rank_point = rank_bonus.get(rank, 0)
    return alap_score + rank_point


# ============================================================
# 获取已完成轮次
# ============================================================

def get_latest_completed_rounds(round_count: int = 2) -> List[int]:
    east_data = fetch_score_view(EAST_SCORE_VIEW_ID)
    completed_rounds = []
    for round_info in east_data.get("rounds", []):
        round_num = round_info.get("number")
        status = round_info.get("status")
        if round_num is not None and status == "finished":
            completed_rounds.append(round_num)
    sorted_rounds = sorted(completed_rounds)
    return sorted_rounds[-round_count:] if sorted_rounds else []


def get_rounds_for_week(week_number: int) -> List[int]:
    if week_number in WEEK_ROUNDS:
        return WEEK_ROUNDS[week_number]
    start_round = (week_number - 1) * 2 + 1
    return [start_round, start_round + 1]


# ============================================================
# 数据解析
# ============================================================

def parse_rounds_and_scores(data: dict, track_id: str, rank_bonus: Dict[int, int], round_filter: Optional[List[int]] = None) -> Dict[int, Dict[str, dict]]:
    round_data = defaultdict(lambda: defaultdict(lambda: {"total_score": 0.0, "details": []}))
    stages = data.get("stages", [])
    stage_track_map = {s.get("id"): s.get("trackId") for s in stages}
    
    for match in data.get("matches", []):
        if stage_track_map.get(match.get("stageId")) != track_id:
            continue
        round_num = match.get("roundNumber")
        if round_num is None:
            continue
        if round_filter is not None and round_num not in round_filter:
            continue
        
        for game in match.get("games", []):
            for player in game.get("players", []):
                pid = player.get("participantId")
                score = player.get("score", 0)
                rank = player.get("rank", 0)
                raw_name = player.get("snapshot", {}).get("nickname", "未知选手")
                player_name = clean_name(raw_name)
                if pid:
                    single_score = calc_single_game_score(score, rank, rank_bonus)
                    round_data[round_num][pid]["total_score"] += single_score
                    round_data[round_num][pid]["details"].append({
                        "player_name": player_name,
                        "score": score,
                        "rank": rank,
                        "single_score": single_score,
                        "round": round_num
                    })
    
    return round_data


def calculate_team_scores(round_data: Dict[int, Dict[str, dict]]) -> Dict[str, dict]:
    team_data = defaultdict(lambda: {
        "total_score": 0.0,
        "rank_1": 0,
        "rank_2": 0,
        "rank_3": 0,
        "rank_4": 0,
        "details": [],
        "round_scores": {}
    })
    
    for round_num, participants in round_data.items():
        for pid, data in participants.items():
            total = data["total_score"]
            details = data["details"]
            
            team_data[pid]["total_score"] += total
            team_data[pid]["round_scores"][round_num] = total
            team_data[pid]["details"].extend(details)
    
    # 统计顺位
    for pid, data in team_data.items():
        for detail in data["details"]:
            rank = detail.get("rank")
            if rank == 1:
                data["rank_1"] += 1
            elif rank == 2:
                data["rank_2"] += 1
            elif rank == 3:
                data["rank_3"] += 1
            elif rank == 4:
                data["rank_4"] += 1
    
    return dict(team_data)


# ============================================================
# 主函数
# ============================================================

def fetch_weekly_report_data(round_filter: Optional[List[int]] = None) -> dict:
    if round_filter:
        debug_print(f"📌 过滤轮次: 第 {', '.join(map(str, round_filter))} 轮")
    
    all_rounds = list(range(1, max(round_filter) + 1)) if round_filter else None
    
    east_data, south_data, participants = fetch_contest_data()
    
    east_rounds = parse_rounds_and_scores(east_data, EAST_TRACK_ID, EAST_RANK_BONUS, all_rounds)
    south_rounds = parse_rounds_and_scores(south_data, SOUTH_TRACK_ID, SOUTH_RANK_BONUS, all_rounds)
    
    east_scores = calculate_team_scores(east_rounds)
    south_scores = calculate_team_scores(south_rounds)
    
    all_participants = set(east_scores.keys()) | set(south_scores.keys())
    
    result = {
        "contest_name": east_data.get("contest", {}).get("name", "联合杯"),
        "current_round": east_data.get("phases", [{}])[0].get("activeRoundNumber", 0),
        "teams": {},
        "rankings": [],
        "promotion_line": 0.0  # 🔥 默认值
    }
    
    for pid in all_participants:
        east = east_scores.get(pid, {"total_score": 0, "rank_1": 0, "rank_2": 0, "rank_3": 0, "rank_4": 0, "details": [], "round_scores": {}})
        south = south_scores.get(pid, {"total_score": 0, "rank_1": 0, "rank_2": 0, "rank_3": 0, "rank_4": 0, "details": [], "round_scores": {}})
        
        total = east["total_score"] + south["total_score"]
        name = participants.get(pid, pid[:8] + "...")
        
        result["teams"][pid] = {
            "name": name,
            "east": east,
            "south": south,
            "total_score": round(total, 1)
        }
    
    # 生成排名
    sorted_teams = sorted(
        result["teams"].items(),
        key=lambda x: x[1]["total_score"],
        reverse=True
    )
    
    rankings = []
    for rank, (pid, data) in enumerate(sorted_teams, 1):
        data["final_rank"] = rank
        rankings.append((pid, data["total_score"]))
    
    result["rankings"] = rankings
    
    # 🔥 获取晋级线（第32名分数）
    if len(rankings) >= 32:
        result["promotion_line"] = rankings[31][1]
        debug_print(f"🔍 晋级线（第32名）：{result['promotion_line']:.1f} 分")
    else:
        result["promotion_line"] = 0.0
        debug_print(f"⚠️ 排名数据不足32条，当前只有 {len(rankings)} 条")
    
    debug_print(f"✅ 成功获取 {len(result['teams'])} 个队伍的数据")
    return result


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    import arena_fetcher
    arena_fetcher.DEBUG = True
    
    try:
        print("\n=== 测试：获取第3-4轮数据 ===")
        start = time.time()
        data = fetch_weekly_report_data([3, 4])
        elapsed = time.time() - start
        print(f"⏱️ 耗时: {elapsed:.2f} 秒")
        
        print(f"📊 晋级线（第32名）：{data.get('promotion_line', 0):.1f} 分")
        print(f"🏫 参赛队伍数：{len(data['teams'])}")
        
        for pid, team in data['teams'].items():
            if "第二工业" in team['name']:
                print(f"✅ {team['name']}:")
                print(f"   总累计: {team['total_score']:.1f}")
                print(f"   东风累计: {team['east']['total_score']:.1f}")
                print(f"   东风顺位: 1位{team['east']['rank_1']}次 / 2位{team['east']['rank_2']}次 / 3位{team['east']['rank_3']}次 / 4位{team['east']['rank_4']}次")
                print(f"   半庄累计: {team['south']['total_score']:.1f}")
                print(f"   半庄顺位: 1位{team['south']['rank_1']}次 / 2位{team['south']['rank_2']}次 / 3位{team['south']['rank_3']}次 / 4位{team['south']['rank_4']}次")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()