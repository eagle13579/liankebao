"""FeedbackStore: 匹配反馈闭环服务"""

import json
import os
import time

# 项目根目录 = backend 的父目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
DATA_FILE = os.path.join(DATA_DIR, "feedback.jsonl")


class FeedbackStore:
    """持久化的匹配反馈存储，支持添加反馈与统计查询。"""

    def __init__(self, data_file: str = DATA_FILE):
        self.data_file = data_file
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        if not os.path.exists(data_file):
            with open(data_file, "w", encoding="utf-8") as f:
                f.write("")

    @property
    def feedbacks(self) -> list[dict]:
        """读取所有反馈记录（每次从文件重新加载）。"""
        records = []
        if not os.path.exists(self.data_file):
            return records
        with open(self.data_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def add_feedback(self, match_id: str, rating: int, comment: str, user_id: str) -> dict:
        """添加一条反馈记录，持久化到 feedback.jsonl。
        
        Args:
            match_id: 匹配 ID
            rating: 评分 1-5
            comment: 评论文本
            user_id: 用户 ID

        Returns:
            写入的记录字典
        """
        if not (1 <= rating <= 5):
            raise ValueError(f"rating 必须在 1-5 之间，收到: {rating}")

        record = {
            "match_id": match_id,
            "rating": rating,
            "comment": comment,
            "user_id": user_id,
            "timestamp": time.time(),
        }
        with open(self.data_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def get_feedback_stats(self) -> dict:
        """计算并返回反馈统计信息。

        Returns:
            {
                "total": int,
                "avg_rating": float,
                "rating_distribution": {1: int, 2: int, ...},
                "by_date": {"2025-01-01": int, ...}
            }
        """
        records = self.feedbacks
        total = len(records)

        if total == 0:
            return {
                "total": 0,
                "avg_rating": 0.0,
                "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "by_date": {},
            }

        rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        rating_sum = 0
        by_date = {}

        for r in records:
            rat = r["rating"]
            rating_distribution[rat] = rating_distribution.get(rat, 0) + 1
            rating_sum += rat

            ts = r.get("timestamp", 0)
            date_str = time.strftime("%Y-%m-%d", time.localtime(ts))
            by_date[date_str] = by_date.get(date_str, 0) + 1

        return {
            "total": total,
            "avg_rating": round(rating_sum / total, 2),
            "rating_distribution": rating_distribution,
            "by_date": by_date,
        }
