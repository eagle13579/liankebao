"""
Celery application for ChainKe backend.

Connects to Redis as broker (localhost:6379/0) and result backend.
Auto-discovers tasks from registered Django/FastAPI apps or the features.tasks module.
"""

from celery import Celery

app = Celery(
    "chainke",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=[
        "features.tasks.embed_tasks",
    ],
)

# Optional configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    beat_schedule={
        "precompute-embeddings-every-10-minutes": {
            "task": "features.tasks.embed_tasks.precompute_embeddings",
            "schedule": 600.0,  # every 10 minutes
            "options": {"queue": "embeddings"},
        },
    },
)


if __name__ == "__main__":
    app.start()
