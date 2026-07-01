"""AI 能力模块 - Lazy imports to avoid circular import chain.

The eager imports from this package trigger a circular chain:
  ai.__init__ → vector_search → models.tag → models.__init__ → crm.crm_models
  → crm.__init__ → crm_router → routers.auth → services → ai (loop!)

Use lazy imports: `from app.ai.vector_search import X` instead of `from app.ai import X`.
"""

# ── Lazy imports via __getattr__ (Python 3.12 __getattr__ on modules) ──────
# This allows `from app.ai import VectorSearchEngine` to work as before,
# but the import doesn't happen until the attribute is actually accessed.

import importlib
import logging

logger = logging.getLogger(__name__)

_MODULE_MAP = {
    # ai_module_name -> (package, attribute_name)
    "AIExtractor": ("app.ai.extractor", "AIExtractor"),
    "OCRScanner": ("app.ai.ocr", "OCRScanner"),
    "VectorSearchEngine": ("app.ai.vector_search", "VectorSearchEngine"),
    "VectorSearchIndex": ("app.ai.vector_search", "VectorSearchIndex"),
    "DocumentBuilder": ("app.ai.vector_search", "DocumentBuilder"),
    "EmbeddingBackend": ("app.ai.vector_search", "EmbeddingBackend"),
    "get_embedding_backend": ("app.ai.vector_search", "get_embedding_backend"),
    "get_vector_index": ("app.ai.vector_search", "get_vector_index"),
    "embed_text": ("app.ai.vector_search", "embed_text"),
    "embed_single": ("app.ai.vector_search", "embed_single"),
    "rerank": ("app.ai.vector_search", "rerank"),
    "cosine_similarity": ("app.ai.vector_search", "cosine_similarity"),
    "sync_vector_index": ("app.ai.vector_search", "sync_vector_index"),
    "WritingAssistant": ("app.ai.writing_assistant", "WritingAssistant"),
    "OptimizationAnalyzer": ("app.ai.optimization", "OptimizationAnalyzer"),
    "ABTestingEngine": ("app.ai.ab_testing", "ABTestingEngine"),
    "get_ab_testing_engine": ("app.ai.ab_testing", "get_ab_testing_engine"),
    "RAGPipeline": ("app.ai.rag_pipeline", "RAGPipeline"),
    "DeepSeekClient": ("app.ai.rag_pipeline", "DeepSeekClient"),
    "ContextBuilder": ("app.ai.rag_pipeline", "ContextBuilder"),
    "RAGContext": ("app.ai.rag_pipeline", "RAGContext"),
    "RAGResponse": ("app.ai.rag_pipeline", "RAGResponse"),
    "KnowledgeGraph": ("app.ai.knowledge_graph", "KnowledgeGraph"),
    "KnowledgeGraphBuilder": ("app.ai.knowledge_graph", "KnowledgeGraphBuilder"),
    "CachedKnowledgeGraphBuilder": ("app.ai.knowledge_graph", "CachedKnowledgeGraphBuilder"),
    "GraphNode": ("app.ai.knowledge_graph", "GraphNode"),
    "GraphEdge": ("app.ai.knowledge_graph", "GraphEdge"),
    "RecommendEngine": ("app.ai.recommendation", "RecommendEngine"),
    "RecommendItem": ("app.ai.recommendation", "RecommendItem"),
    "RecommendResult": ("app.ai.recommendation", "RecommendResult"),
    "GaiaEvolutionBrain": ("app.ai.gaia_evolution_brain", "GaiaEvolutionBrain"),
    "get_gaia_brain": ("app.ai.gaia_evolution_brain", "get_gaia_brain"),
    "GaiaTrainer": ("app.ai.gaia_trainer", "GaiaTrainer"),
    "get_gaia_trainer": ("app.ai.gaia_trainer", "get_gaia_trainer"),
    "FeedbackLoop": ("app.ai.feedback_loop", "FeedbackLoop"),
    "OnlineLearningPipeline": ("app.ai.online_learning", "OnlineLearningPipeline"),
    "OnlineLearningEngine": ("app.ai.online_learning", "OnlineLearningEngine"),
    "get_online_learning_engine": ("app.ai.online_learning", "get_online_learning_engine"),
    "trigger_learning": ("app.ai.online_learning", "trigger_learning"),
    "get_learning_status": ("app.ai.online_learning", "get_learning_status"),
    "load_online_weights": ("app.ai.online_learning", "load_online_weights"),
    "get_online_weight": ("app.ai.online_learning", "get_online_weight"),
}


def __getattr__(name):
    """Lazy import: resolve attributes on first access."""
    if name in _MODULE_MAP:
        package, attr = _MODULE_MAP[name]
        mod = importlib.import_module(package)
        result = getattr(mod, attr)
        # Cache on module for next access
        globals()[name] = result
        return result
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}. "
        f"Try `from app.ai.{name.lower() if name.isupper() else name} import {name}`"
    )


__all__ = list(_MODULE_MAP.keys())
