"""
训练数据管道 — TrainingPipeline
- 从代码资产库提取代码 + 文档 → ChatML 格式
- 生成训练样本对 (question / answer)
- 导出为 MLX 训练的 JSONL 格式
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ChatML 模板常量
CHATML_SYSTEM = "<|im_start|>system\n你是一个 AI 数字名片助手，基于企业内部代码资产库和文档回答问题。\n<|im_end|>"
CHATML_USER = "<|im_start|>user\n{question}\n<|im_end|>"
CHATML_ASSISTANT = "<|im_start|>assistant\n{answer}\n<|im_end|>"


class TrainingPipeline:
    """训练数据管道：代码/文档 → ChatML 样本 → JSONL。"""

    def __init__(self, asset_root: str | None = None):
        self.asset_root = Path(asset_root) if asset_root else Path.cwd()

    # ── 提取代码资产 ──────────────────────────────────────────

    def _collect_code_files(self) -> list[Path]:
        """递归收集所有 .py / .md / .txt / .rst 文件。"""
        extensions = {".py", ".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json"}
        files = []
        for ext in extensions:
            files.extend(self.asset_root.rglob(f"*{ext}"))
        # 排除 __pycache__、.git、node_modules
        files = [
            f
            for f in files
            if not any(part.startswith("__pycache__") or part in (".git", "node_modules", ".venv") for part in f.parts)
        ]
        return sorted(files)

    def _file_to_chunk(self, path: Path) -> dict[str, str] | None:
        """读取文件并结构化为一个代码块。"""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug("跳过 %s: %s", path, e)
            return None
        rel = path.relative_to(self.asset_root) if path.is_relative_to(self.asset_root) else path
        ext = path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".json": "json",
        }
        lang = lang_map.get(ext, "text")
        return {
            "path": str(rel),
            "language": lang,
            "content": content[:8000],  # 截断超长文件
        }

    def prepare_training_data(self) -> list[dict[str, str]]:
        """从代码资产库提取代码 + 文档 → 结构化列表。"""
        files = self._collect_code_files()
        logger.info("收集到 %d 个代码/文档文件", len(files))
        chunks = []
        for f in files:
            chunk = self._file_to_chunk(f)
            if chunk:
                chunks.append(chunk)
        logger.info("提取 %d 个有效代码块", len(chunks))
        return chunks

    # ── 生成训练样本 ──────────────────────────────────────────

    def generate_training_samples(self, chunks: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
        """将代码块转换为 ChatML 问答样本对。

        自动生成 question:
          - Python 文件: "解释 {path} 的功能"
          - 文档: "总结 {path} 的内容"
        answer = 代码块内容。
        """
        if chunks is None:
            chunks = self.prepare_training_data()

        samples = []
        for chunk in chunks:
            path = chunk["path"]
            content = chunk["content"]
            lang = chunk["language"]

            if lang == "python":
                q = f"请解释 {path} 的功能和实现方式。"
            elif lang in ("markdown", "text"):
                q = f"请总结文档 {path} 的核心内容。"
            else:
                q = f"请分析配置文件 {path} 的用途。"

            a = f"```{lang}\n{content}\n```"
            samples.append({"question": q, "answer": a})
        logger.info("生成了 %d 个训练样本", len(samples))
        return samples

    # ── ChatML 格式化 ─────────────────────────────────────────

    def _to_chatml(self, question: str, answer: str) -> str:
        """单条样本 → ChatML 格式字符串。"""
        parts = [CHATML_SYSTEM]
        parts.append(CHATML_USER.format(question=question))
        parts.append(CHATML_ASSISTANT.format(answer=answer))
        parts.append("<|im_start|>assistant")  # MLX prompt 结束标记
        return "\n".join(parts)

    def export_to_jsonl(
        self,
        output_path: str | Path,
        samples: list[dict[str, str]] | None = None,
    ) -> int:
        """导出为 MLX 训练的 JSONL 格式 (ChatML)。"""
        if samples is None:
            samples = self.generate_training_samples()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with output_path.open("w", encoding="utf-8") as f:
            for s in samples:
                chatml = self._to_chatml(s["question"], s["answer"])
                record = {
                    "messages": [
                        {"role": "system", "content": CHATML_SYSTEM},
                        {"role": "user", "content": s["question"]},
                        {"role": "assistant", "content": s["answer"]},
                    ],
                    "text": chatml,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

        logger.info("导出 %d 条样本到 %s", count, output_path)
        return count
