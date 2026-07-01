import os
import re

from PIL import Image, ImageEnhance, ImageFilter

# ── PaddleOCR 可用性检测（骨架集成，无需实际安装 paddlepaddle） ──────────────
try:
    from paddleocr import PaddleOCR

    _PADDLE_AVAILABLE = True
except ImportError:
    _PADDLE_AVAILABLE = False


class OCRScanner:
    """OCR 扫描器 - 名片图像预处理 + 联系方式提取

    注意：核心 OCR 识别需要外部 OCR 引擎（如 PaddleOCR / Tesseract），
    这里提供图像预处理 + 正则匹配 + 预留 OCR 接口。
    """

    # 手机号正则（支持国际格式）
    PHONE_PATTERN = re.compile(r"(?:\+86[-\s]?)?1[3-9]\d{9}")
    # 座机号
    LANDLINE_PATTERN = re.compile(r"(?:0\d{2,3}[-\s]?)?\d{7,8}")
    # 邮箱
    EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    # 微信号
    WECHAT_PATTERN = re.compile(r"(?:微信|微|WX|WeChat)[：:\s]*([a-zA-Z0-9_]{4,20})", re.IGNORECASE)

    @staticmethod
    def preprocess_image(image: Image.Image) -> Image.Image:
        """名片图像预处理（增强 OCR 识别率）

        Args:
            image: PIL Image 对象

        Returns:
            预处理后的 PIL Image 对象
        """
        # 1. 转灰度
        if image.mode != "L":
            image = image.convert("L")

        # 2. 增强对比度
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # 3. 增强锐度
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)

        # 4. 二值化（自适应阈值简化版）
        image = image.point(lambda x: 255 if x > 160 else 0)

        # 5. 降噪（轻微模糊后还原边缘）
        image = image.filter(ImageFilter.MedianFilter(size=3))

        return image

    @staticmethod
    def scan_card(
        image_or_path: str | Image.Image,
        use_external_ocr: bool = False,
    ) -> str:
        """扫描名片图像，提取文本

        Args:
            image_or_path: 图像路径或 PIL Image 对象
            use_external_ocr: 是否使用外部 OCR 引擎（需安装 PaddleOCR）

        Returns:
            提取的文本内容
        """
        # ── 1) 尝试 PaddleOCR（自动检测，无需 use_external_ocr 开关） ──────────
        if isinstance(image_or_path, str):
            if not os.path.exists(image_or_path):
                raise FileNotFoundError(f"图像文件不存在: {image_or_path}")
            image_path = image_or_path
            image = Image.open(image_or_path)
        else:
            image_path = None
            image = image_or_path

        if image_path and _PADDLE_AVAILABLE:
            text, conf = OCRScanner.scan_with_paddle(image_path)
            if text.strip():
                return text

        # ── 2) 传统流程：预处理 → 外部 OCR / 占位提示 ─────────────────────
        if not isinstance(image_or_path, str):
            # PIL Image 无路径时存临时文件再试 PaddleOCR
            if _PADDLE_AVAILABLE:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                    image.save(tmp_path, "PNG")
                try:
                    text, conf = OCRScanner.scan_with_paddle(tmp_path)
                    if text.strip():
                        return text
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        # 预处理
        processed = OCRScanner.preprocess_image(image)

        if use_external_ocr:
            return OCRScanner._external_ocr(processed)

        # 内置 OCR 提示：建议安装 PaddleOCR
        return "【OCR 识别建议】图像已预处理完成。如需文字识别，请安装 PaddleOCR：pip install paddlepaddle paddleocr"

    @staticmethod
    def _external_ocr(image: Image.Image) -> str:
        """使用 PaddleOCR 进行文字识别"""
        try:
            from paddleocr import PaddleOCR

            ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

            # 保存临时文件供 PaddleOCR 处理
            temp_path = "/tmp/_ocr_temp.png"
            image.save(temp_path)

            result = ocr.ocr(temp_path, cls=True)

            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if not result or not result[0]:
                return ""

            texts = []
            for line in result[0]:
                text = line[1][0] if len(line) > 1 else ""
                if text:
                    texts.append(text)

            return "\n".join(texts)

        except ImportError:
            return "【PaddleOCR 未安装】请执行: pip install paddlepaddle paddleocr"
        except Exception as e:
            return f"【OCR 识别失败】{str(e)}"

    @staticmethod
    def extract_contact_info(text: str) -> dict:
        """从 OCR 文本中提取联系方式

        Args:
            text: OCR 识别后的文本

        Returns:
            {"phone": str|None, "email": str|None, "wechat": str|None}
        """
        result = {
            "phone": None,
            "email": None,
            "wechat": None,
        }

        # 手机号
        phones = OCRScanner.PHONE_PATTERN.findall(text)
        if phones:
            result["phone"] = phones[0]
        else:
            # 尝试座机号
            landlines = OCRScanner.LANDLINE_PATTERN.findall(text)
            if landlines:
                result["phone"] = landlines[0]

        # 邮箱
        emails = OCRScanner.EMAIL_PATTERN.findall(text)
        if emails:
            result["email"] = emails[0]

        # 微信
        wechat_match = OCRScanner.WECHAT_PATTERN.search(text)
        if wechat_match:
            result["wechat"] = wechat_match.group(1)
        else:
            # 兜底：找纯字母数字4-20位可能是微信号
            candidates = re.findall(r"(?:^|\s)([a-zA-Z][a-zA-Z0-9_]{3,19})(?:\s|$)", text)
            if candidates:
                # 找最短的（微信号通常较短）
                candidates.sort(key=len)
                result["wechat"] = candidates[0]

        return result

    @staticmethod
    def extract_business_info(text: str) -> dict:
        """从 OCR 文本中提取企业信息

        Args:
            text: OCR 识别后的文本

        Returns:
            {
                "company_name": str|None,
                "position": str|None,
                "address": str|None,
                "website": str|None,
            }
        """
        result = {
            "company_name": None,
            "position": None,
            "address": None,
            "website": None,
        }

        # 公司名（中英文）
        company_match = re.search(r"(?:公司|企业|有限公司|集团|Co\.|Inc\.|Ltd\.)[：:\s]*([\u4e00-\u9fa5a-zA-Z]+)", text)
        if company_match:
            result["company_name"] = company_match.group(1)
        else:
            # 尝试取包含"公司"的行
            for line in text.split("\n"):
                if "公司" in line or "企业" in line:
                    result["company_name"] = line.strip()
                    break

        # 职位
        position_match = re.search(
            r"(?:职位|职务|title|position|CEO|CTO|COO|总监|经理|主管|工程师)[：:\s]*([\u4e00-\u9fa5a-zA-Z/]+)",
            text,
            re.IGNORECASE,
        )
        if position_match:
            result["position"] = position_match.group(1)
        else:
            # 常见职位关键词
            for line in text.split("\n"):
                if any(kw in line for kw in ["总监", "经理", "主管", "工程师", "CEO", "CTO", "创始人"]):
                    result["position"] = line.strip()
                    break

        # 地址
        addr_match = re.search(r"(?:地址|Addr|address|Location)[：:\s]*(.{5,50})", text, re.IGNORECASE)
        if addr_match:
            result["address"] = addr_match.group(1)

        # 网址
        url_match = re.search(r"(https?://[^\s]+|www\.[^\s]+)", text)
        if url_match:
            result["website"] = url_match.group(1)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    #  PaddleOCR 骨架集成
    # ═══════════════════════════════════════════════════════════════════════

    def __init__(self):
        """OCRScanner 实例初始化时检测 PaddleOCR 可用性"""
        try:
            from paddleocr import PaddleOCR  # noqa: F401

            self.paddle_available = True
        except ImportError:
            self.paddle_available = False

    @staticmethod
    def scan_with_paddle(image_path: str) -> tuple:
        """使用 PaddleOCR 扫描图像，返回 (识别文本, 平均置信度)

        Args:
            image_path: 图像文件路径（支持 jpg/png/bmp 等常见格式）

        Returns:
            (text: str, confidence: float)
            - text: 拼接后的所有识别文本行，用换行符分隔
            - confidence: 所有文本行的平均置信度（0.0 ~ 1.0）
            若 PaddleOCR 不可用或识别失败，返回 ("", 0.0)
        """
        # ── 骨架保护：PaddleOCR 未安装时静默跳过 ──────────────────────────
        if not _PADDLE_AVAILABLE:
            return "", 0.0

        if not os.path.exists(image_path):
            return "", 0.0

        try:
            # 每次调用创建新实例（避免多线程状态冲突）
            ocr = PaddleOCR(
                use_angle_cls=True,  # 启用文字方向分类
                lang="ch",  # 中英文模型
                show_log=False,  # 静默模式
                use_gpu=False,  # CPU 推理（兼容无 GPU 环境）
            )

            # PaddleOCR 返回格式（标准版）:
            #   result = [ [[x1,y1,...], (text, conf)], ... ]
            #   或 result = [ [ [box, (text, conf)], ... ], ... ] （batch 维度）
            result = ocr.ocr(image_path, cls=True)

            # ── 解析结果 ──────────────────────────────────────────────────
            if not result:
                return "", 0.0

            texts: list[str] = []
            confs: list[float] = []

            # result 可能有两层嵌套: result -> [batch0] -> [line0, line1, ...]
            batch = result[0] if isinstance(result, list) and len(result) > 0 else result
            if not batch:
                return "", 0.0

            for line in batch:
                # line 格式: [bbox, (text, confidence)]
                if not isinstance(line, (list, tuple)) or len(line) < 2:
                    continue
                text, confidence = line[1]  # type: ignore[misc]
                if text and isinstance(text, str) and text.strip():
                    texts.append(text.strip())
                    confs.append(float(confidence))

            if not texts:
                return "", 0.0

            avg_confidence = sum(confs) / len(confs)
            return "\n".join(texts), avg_confidence

        except Exception:
            # 静默失败，由调用方决定回退策略
            return "", 0.0

    @staticmethod
    def scan_with_paddle_detailed(image_path: str) -> list[dict]:
        """使用 PaddleOCR 扫描图像，返回每行文本的详细信息

        Args:
            image_path: 图像文件路径

        Returns:
            [{"text": str, "confidence": float, "box": list}, ...]
            失败时返回空列表
        """
        if not _PADDLE_AVAILABLE:
            return []

        if not os.path.exists(image_path):
            return []

        try:
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=False,
            )
            result = ocr.ocr(image_path, cls=True)
            if not result or not result[0]:
                return []

            details: list[dict] = []
            for line in result[0]:
                if not isinstance(line, (list, tuple)) or len(line) < 2:
                    continue
                box, (text, confidence) = line
                if text and isinstance(text, str) and text.strip():
                    details.append(
                        {
                            "text": text.strip(),
                            "confidence": float(confidence),
                            "box": box,
                        }
                    )
            return details

        except Exception:
            return []
