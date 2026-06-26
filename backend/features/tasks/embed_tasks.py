"""
Embedding precomputation tasks.

Provides a periodic Celery beat task that recomputes embeddings for
content that has changed since the last run.
"""

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="features.tasks.embed_tasks.precompute_embeddings",
    max_retries=3,
    default_retry_delay=60,
    queue="embeddings",
)
def precompute_embeddings(self):
    """
    Periodic task: precompute or refresh embeddings for eligible content.

    This task is triggered by Celery Beat every 10 minutes (configurable
    via beat_schedule in celery_app.py).  It should query the database
    for records whose embedding is missing or stale, generate embeddings
    via the configured embedding model, and persist them.

    Implementation details (to be filled in per project needs):
      - Fetch a batch of items pending embedding (e.g. products, articles).
      - Call the embedding model (OpenAI / local model).
      - Write results back to the database.
    """
    logger.info("precompute_embeddings started")

    try:
        # ──────────────────────────────────────────────────────────
        # TODO: Replace placeholder logic below with real embedding
        #       computation.
        # Example:
        #   from features.products.models import Product
        #   from your_embedding_service import generate_embedding
        #
        #   products = Product.objects.filter(
        #       embedding__isnull=True
        #   )[:50]
        #   for product in products:
        #       vec = generate_embedding(product.description)
        #       product.embedding = vec
        #       product.save(update_fields=["embedding"])
        # ──────────────────────────────────────────────────────────
        logger.info("No embedding logic wired yet — skipping computation.")
    except Exception as exc:
        logger.exception("precompute_embeddings failed")
        raise self.retry(exc=exc)

    logger.info("precompute_embeddings finished successfully")
