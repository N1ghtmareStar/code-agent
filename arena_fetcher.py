import requests
import json
import asyncio
import concurrent.futures
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# ============================================================
# 配置
# ============================================================
ARENA_API_BASE = "https://arena.pesiu.org"

# 顺位点
EAST_RANK_BONUS = {1: 50, 2: 10, 3: -10, 4: -30}
SOUTH_RANK_BONUS = {1: 60, 2: 20, 3: -20, 4: -40}


# ============================================================
# 基础 API 请求
# ============================================================
def api_get(endpoint: str, params: dict = None) -> dict:
    """发送 GET 请求到 Arena API"""
    url = f"{ARENA_API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ API 请求失败: {url}, 错误: {e}", flush=True)
        raise


# ============================================================
# 获取参赛队伍列表
# ============================================================
def fetch_participants() -> List[dict]:
    """获取所有参赛队伍"""
    data = api_get("/api/teams")
    return data.get("teams", [])


# ============================================================
# 获取单轮比赛数据
# ============================================================
def fetch_round_data(round_number: int) -> dict:
    """获取指定轮次的比赛数据"""
    data = api_get(f"/api/rounds/{round_number}")
    return data


# ============================================================
# 获取比赛数据（东风 + 半庄）
# ============================================================
def fetch_contest_data() -> Tuple[dict, dict, dict]:
    """
    获取东风和半庄的比赛数据
    返回: (east_data, south_data, participants)
    """
    # 使用线程池并发获取数据
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        east_future = executor.submit(api_get, "/api/rounds?type=east")
        south_future = executor.submit(api_get, "/api/rounds?type=south")
        teams_future = executor.submit(api_get, "/api/teams")
        
        try:
            east_data = east_future.result()
            south_data = south_future.result()
            teams_data = teams_future.result()
        except Exception as e:
            print(f"⚠️ 获取比赛数据失败: {e}", flush=True)
            raise
    
    participants = {team["id"]: team for team in teams_data.get("teams", [])}
    return east_data, south_data, participants


# ============================================================
# 获取轮次对应的周数
# ============================================================
def get_rounds_for_week(week_number: int) -> List[int]:
    """
    获取指定周对应的轮次
    第1周: [1, 2]
    第2周: [3, 4]
    第3周: [5, 6]
    第4周: [7, 8]
    """
    start_round = (week_number - 1) * 2 + 1
    return [start_round, start_round + 1]


def get_week_from_round(round_number: int) -> int:
    """根据轮次计算周数"""
    return (round_number - 1) // 2 + 1


# ============================================================
# 获取最新已完成轮次
# ============================================================
def get_latest_completed_rounds(count: int = 2) -> List[int]:
    """
    获取最新已完成的轮次列表
    默认返回最新2轮
    """
    # 获取所有轮次数据
    try:
        data = api_get("/api/rounds")
        rounds = data.get("rounds", [])
        # 按轮次编号排序
        completed = [r for r in rounds if r.get("status") == "completed"]
        if not completed:
            return [1, 2]  # 默认返回第1、2轮
        
        # 获取最新的 count 个轮次
        latest = sorted(completed, key=lambda x: x["round_number"], reverse=True)[:count]
        return sorted([r["round_number"] for r in latest])
    except Exception as e:
        print(f"⚠️ 获取最新轮次失败: {e}", flush=True)
        return [3, 4]  # 默认返回第3、4轮


# ============================================================
# 获取当前最大轮次
# ============================================================
def get_latest_round() -> int:
    """
    获取当前已完成的最大轮次
    返回最大轮次数字，例如：5
    """
    # 尝试从缓存获取
    if hasattr(get_latest_round, '_cache'):
        cached_time, cached_round = getattr(get_latest_round, '_cache')
        if time.time() - cached_time < 300:  # 5分钟缓存
            return cached_round
    
    max_round = 0
    # 从第1轮开始尝试，最多尝试到第20轮
    for r in range(1, 21):
        try:
            data = fetch_round_data(r)
            # 检查数据是否有效
            if data and 'teams' in data and data['teams']:
                max_round = r
            else:
                break
        except Exception as e:
            print(f"⚠️ 获取第{r}轮数据失败: {e}", flush=True)
            break
    
    # 缓存结果
    get_latest_round._cache = (time.time(), max_round)
    return max_round


# ============================================================
# 获取周战报数据
# ============================================================
def fetch_weekly_report_data(round_numbers: List[int]) -> dict:
    """
    获取周战报数据
    返回格式:
    {
        "teams": {
            "team_id": {
                "name": "学校名称",
                "total_score": 总分数,
                "final_rank": 最终排名,
                "east": {
                    "total_score": 东风总分,
                    "round_scores": {轮次: 分数},
                    "details": [{"round": 轮次, "player_name": "", "rank": 顺位, "score": 得分}]
                },
                "south": {
                    "total_score": 半庄总分,
                    "round_scores": {轮次: 分数},
                    "details": [{"round": 轮次, "player_name": "", "rank": 顺位, "score": 得分}]
                }
            }
        },
        "promotion_line": 晋级线
    }
    """
    # 获取所有比赛数据
    east_data, south_data, participants = fetch_contest_data()
    
    # 整理数据
    result = {
        "teams": {},
        "promotion_line": 0.0
    }
    
    # 获取晋级线
    # 从 API 数据中获取，如果没有则计算
    if "promotion_line" in east_data:
        result["promotion_line"] = east_data["promotion_line"]
    elif "promotion_line" in south_data:
        result["promotion_line"] = south_data["promotion_line"]
    
    # 处理东风数据
    for team_id, team_info in east_data.get("teams", {}).items():
        if team_id not in result["teams"]:
            result["teams"][team_id] = {
                "name": participants.get(team_id, {}).get("name", f"队伍{team_id}"),
                "total_score": 0.0,
                "final_rank": 0,
                "east": {
                    "total_score": 0.0,
                    "round_scores": {},
                    "details": []
                },
                "south": {
                    "total_score": 0.0,
                    "round_scores": {},
                    "details": []
                }
            }
        
        # 计算东风总分
        total_east = 0.0
        for round_num in round_numbers:
            round_score = team_info.get("round_scores", {}).get(str(round_num), 0)
            total_east += round_score
            result["teams"][team_id]["east"]["round_scores"][round_num] = round_score
        
        result["teams"][team_id]["east"]["total_score"] = total_east
        
        # 获取东风详情
        for detail in team_info.get("details", []):
            if detail.get("round") in round_numbers:
                result["teams"][team_id]["east"]["details"].append(detail)
    
    # 处理半庄数据
    for team_id, team_info in south_data.get("teams", {}).items():
        if team_id not in result["teams"]:
            result["teams"][team_id] = {
                "name": participants.get(team_id, {}).get("name", f"队伍{team_id}"),
                "total_score": 0.0,
                "final_rank": 0,
                "east": {
                    "total_score": 0.0,
                    "round_scores": {},
                    "details": []
                },
                "south": {
                    "total_score": 0.0,
                    "round_scores": {},
                    "details": []
                }
            }
        
        # 计算半庄总分
        total_south = 0.0
        for round_num in round_numbers:
            round_score = team_info.get("round_scores", {}).get(str(round_num), 0)
            total_south += round_score
            result["teams"][team_id]["south"]["round_scores"][round_num] = round_score
        
        result["teams"][team_id]["south"]["total_score"] = total_south
        
        # 获取半庄详情
        for detail in team_info.get("details", []):
            if detail.get("round") in round_numbers:
                result["teams"][team_id]["south"]["details"].append(detail)
    
    # 计算总分和排名
    for team_id, team_data in result["teams"].items():
        total = team_data["east"]["total_score"] + team_data["south"]["total_score"]
        team_data["total_score"] = total
    
    # 按总分排序
    sorted_teams = sorted(result["teams"].items(), key=lambda x: x[1]["total_score"], reverse=True)
    for rank, (team_id, team_data) in enumerate(sorted_teams, 1):
        team_data["final_rank"] = rank
    
    return result


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    try:
        print("=== 测试获取最新轮次 ===")
        latest = get_latest_round()
        print(f"最新轮次: {latest}")
        
        print("\n=== 测试获取周战报数据 ===")
        data = fetch_weekly_report_data([3, 4])
        print(f"队伍数量: {len(data['teams'])}")
        print(f"晋级线: {data['promotion_line']}")
        for team_id, team in list(data["teams"].items())[:3]:
            print(f"  {team['name']}: {team['total_score']:.1f} 分 (排名: {team['final_rank']})")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()