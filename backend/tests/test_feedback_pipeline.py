"""链客宝 — 反馈采集管道测试
============================
测试覆盖:
  1. 提交 like 反馈
  2. 提交 dislike 反馈
  3. 提交 rating 反馈 (带评分)
  4. 提交 report 反馈 (带评论)
  5. 提交反馈时 context 字段
  6. 查询目标统计
  7. 查询用户反馈历史 (翻页)
  8. 查询最近反馈 (时间范围)
  9. 无效 target_type 报错
  10. rating 缺少 score 报错
"""

import os
import sys
import json
from datetime import datetime, timedelta

# 确保项目根目录 (backend/) 在 sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _project_root)

from app.database import Base, SessionLocal, engine
from app.services.feedback_service import FeedbackService
from app.models.feedback import Feedback, FeedbackStats


def setup():
    """创建测试表"""
    Base.metadata.create_all(bind=engine)


def teardown():
    """清理测试数据"""
    db = SessionLocal()
    try:
        db.query(Feedback).delete()
        db.commit()
    finally:
        db.close()


def test_submit_like():
    """TC1: 提交 like 反馈"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        fb = svc.submit_feedback(
            user_id="u001",
            target_type="card",
            target_id="card_001",
            feedback_type="like",
        )
        assert fb.id is not None, "ID should be set"
        assert fb.user_id == "u001"
        assert fb.target_type == "card"
        assert fb.feedback_type == "like"
        assert fb.score is None
        print(f"  ✓ TC1: submit_like → id={fb.id}")
    finally:
        db.close()


def test_submit_dislike():
    """TC2: 提交 dislike 反馈"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        fb = svc.submit_feedback(
            user_id="u001",
            target_type="enterprise",
            target_id="ent_001",
            feedback_type="dislike",
        )
        assert fb.feedback_type == "dislike"
        print(f"  ✓ TC2: submit_dislike → id={fb.id}")
    finally:
        db.close()


def test_submit_rating():
    """TC3: 提交 rating 反馈 (带评分)"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        fb = svc.submit_feedback(
            user_id="u002",
            target_type="match",
            target_id="match_001",
            feedback_type="rating",
            score=4,
        )
        assert fb.score == 4
        print(f"  ✓ TC3: submit_rating → id={fb.id}, score={fb.score}")
    finally:
        db.close()


def test_submit_report_with_comment():
    """TC4: 提交 report 反馈 (带评论)"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        fb = svc.submit_feedback(
            user_id="u003",
            target_type="enterprise",
            target_id="ent_002",
            feedback_type="report",
            comment="虚假信息，请审核",
        )
        assert fb.comment == "虚假信息，请审核"
        print(f"  ✓ TC4: submit_report → id={fb.id}, comment='{fb.comment}'")
    finally:
        db.close()


def test_submit_with_context():
    """TC5: 提交反馈时携带 context JSON"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        fb = svc.submit_feedback(
            user_id="u004",
            target_type="card",
            target_id="card_002",
            feedback_type="like",
            context={"page": "match_result", "session_id": "abc123"},
        )
        assert fb.context == {"page": "match_result", "session_id": "abc123"}
        print(f"  ✓ TC5: submit_with_context → id={fb.id}, context={fb.context}")
    finally:
        db.close()


def test_get_stats():
    """TC6: 查询目标统计"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        # Submit a like, a dislike, and a rating for the same target
        svc.submit_feedback("u001", "card", "card_stat_01", "like")
        svc.submit_feedback("u002", "card", "card_stat_01", "dislike")
        svc.submit_feedback("u003", "card", "card_stat_01", "rating", score=5)

        stats = svc.get_stats("card", "card_stat_01")
        assert stats.like_count >= 1
        assert stats.dislike_count >= 1
        assert stats.avg_rating == 5.0
        assert stats.total_count >= 3
        print(f"  ✓ TC6: get_stats → likes={stats.like_count}, dislikes={stats.dislike_count}, "
              f"avg={stats.avg_rating}, total={stats.total_count}")
    finally:
        db.close()


def test_get_user_feedback():
    """TC7: 查询用户反馈历史 (翻页)"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        # Submit multiple feedbacks from same user
        svc.submit_feedback("usr_page", "card", "c1", "like")
        svc.submit_feedback("usr_page", "card", "c2", "dislike")
        svc.submit_feedback("usr_page", "card", "c3", "like")
        svc.submit_feedback("usr_page", "card", "c4", "rating", score=3)

        # Page 1: first 2
        page1 = svc.get_user_feedback("usr_page", limit=2, offset=0)
        assert len(page1) == 2, f"Expected 2, got {len(page1)}"
        # Page 2: next 2
        page2 = svc.get_user_feedback("usr_page", limit=2, offset=2)
        assert len(page2) == 2, f"Expected 2, got {len(page2)}"
        # Ensure different items
        assert page1[0].id != page2[0].id
        print(f"  ✓ TC7: get_user_feedback → page1={len(page1)}, page2={len(page2)}")
    finally:
        db.close()


def test_get_recent_feedback():
    """TC8: 查询最近反馈"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        # Submit some recent feedback
        svc.submit_feedback("u_rec", "card", "c_rec1", "like")
        svc.submit_feedback("u_rec", "card", "c_rec2", "dislike")

        recent = svc.get_recent_feedback(hours=24)
        assert len(recent) >= 2, f"Expected >=2 recent, got {len(recent)}"
        # Verify ordering (newest first)
        assert recent[0].created_at >= recent[-1].created_at
        print(f"  ✓ TC8: get_recent_feedback(24h) → {len(recent)} records, "
              f"newest={recent[0].created_at}")
    finally:
        db.close()


def test_invalid_target_type():
    """TC9: 无效 target_type 报错"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        try:
            svc.submit_feedback("u001", "invalid_type", "x", "like")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "无效 target_type" in str(e)
            print(f"  ✓ TC9: invalid target_type → '{e}'")
    finally:
        db.close()


def test_rating_without_score():
    """TC10: rating 缺少 score 报错"""
    db = SessionLocal()
    try:
        svc = FeedbackService(db)
        try:
            svc.submit_feedback("u001", "card", "x", "rating")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "必须提供 score" in str(e)
            print(f"  ✓ TC10: rating without score → '{e}'")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("链客宝 — 反馈采集管道测试")
    print("=" * 50)

    setup()

    tests = [
        test_submit_like,
        test_submit_dislike,
        test_submit_rating,
        test_submit_report_with_comment,
        test_submit_with_context,
        test_get_stats,
        test_get_user_feedback,
        test_get_recent_feedback,
        test_invalid_target_type,
        test_rating_without_score,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: FAILED — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    teardown()

    print()
    print("=" * 50)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 测试用例")
    print("=" * 50)
    sys.exit(1 if failed > 0 else 0)
