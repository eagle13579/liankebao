"""
去重引擎 - 三重匹配：名字相似度 + 手机号精确 + 微信ID精确 + 公司名模糊
"""
import difflib
from typing import Dict, List, Optional, Tuple, Any

# 中文字符集（用于判断是否含中文）
CJK_RANGE = set(chr(i) for i in range(0x4E00, 0x9FFF + 1))


def _has_chinese(text: str) -> bool:
    """判断字符串是否包含中文字符"""
    return any(ch in CJK_RANGE for ch in text)


def _normalize_phone(phone: str) -> str:
    """归一化手机号：去除非数字字符"""
    return "".join(ch for ch in phone if ch.isdigit())


def _normalize_name(name: str) -> str:
    """归一化姓名：去除空格和特殊字符，转为小写"""
    return "".join(ch for ch in name.strip() if ch.isalnum() or ch in CJK_RANGE).lower()


def name_similarity(name1: str, name2: str) -> float:
    """
    计算两个名字的相似度 (0.0 ~ 1.0)
    使用 difflib.SequenceMatcher，对中文名和英文名都有效
    """
    if not name1 or not name2:
        return 0.0
    n1 = _normalize_name(name1)
    n2 = _normalize_name(name2)
    if not n1 or not n2:
        return 0.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def company_similarity(comp1: Optional[str], comp2: Optional[str]) -> float:
    """公司名模糊匹配"""
    if not comp1 or not comp2:
        return 0.0
    c1 = comp1.strip().lower()
    c2 = comp2.strip().lower()
    if not c1 or not c2:
        return 0.0
    return difflib.SequenceMatcher(None, c1, c2).ratio()


def phone_exact_match(phone1: Optional[str], phone2: Optional[str]) -> bool:
    """手机号精确匹配（归一化后比较）"""
    if not phone1 or not phone2:
        return False
    p1 = _normalize_phone(phone1)
    p2 = _normalize_phone(phone2)
    if not p1 or not p2:
        return False
    return p1 == p2


def wechat_exact_match(wechat1: Optional[str], wechat2: Optional[str]) -> bool:
    """微信ID精确匹配（忽略大小写）"""
    if not wechat1 or not wechat2:
        return False
    return wechat1.strip().lower() == wechat2.strip().lower()


def email_exact_match(email1: Optional[str], email2: Optional[str]) -> bool:
    """邮箱精确匹配（忽略大小写）"""
    if not email1 or not email2:
        return False
    return email1.strip().lower() == email2.strip().lower()


# ===== 核心去重逻辑 =====

NAME_SIMILARITY_THRESHOLD = 0.75  # 姓名相似度阈值


class DuplicateGroup:
    """一组重复候选记录"""

    def __init__(
        self,
        source_idx: int,
        duplicate_idx: int,
        similarity_score: float,
        match_type: str,
    ):
        self.source_idx = source_idx
        self.duplicate_idx = duplicate_idx
        self.similarity_score = similarity_score
        self.match_type = match_type  # 'name_fuzzy' / 'phone_exact' / 'wechat_exact' / 'company_fuzzy'

    def __repr__(self) -> str:
        return (
            f"DuplicateGroup(source={self.source_idx}, dup={self.duplicate_idx}, "
            f"score={self.similarity_score:.2f}, type={self.match_type})"
        )


def _evaluate_name_pair(
    i: int,
    j: int,
    normalized: List[dict],
    offset: int,
    matched_pairs: set,
    results: List[DuplicateGroup],
    name_threshold: float,
) -> None:
    """评估一对名字是否重复（供分桶后调用）"""
    # 至少一个在导入范围内
    if i >= offset and j >= offset:
        return

    # 跳过已在精确匹配中出现的对
    pair_key = (min(i, j), max(i, j))
    if pair_key in matched_pairs:
        return

    # 长度差过滤
    len_i = len(normalized[i]["name_raw"])
    len_j = len(normalized[j]["name_raw"])
    if abs(len_i - len_j) > 3:
        return

    score = name_similarity(
        normalized[i]["name_raw"],
        normalized[j]["name_raw"],
    )

    if score >= name_threshold:
        matched_pairs.add(pair_key)
        results.append(DuplicateGroup(
            source_idx=i,
            duplicate_idx=j,
            similarity_score=score,
            match_type="name_fuzzy",
        ))
        return

    # 公司名模糊匹配（仅当名字相似度较低时才尝试，避免误判）
    comp_score = company_similarity(
        normalized[i]["company_raw"],
        normalized[j]["company_raw"],
    )
    if comp_score >= 0.85 and score >= 0.4:
        matched_pairs.add(pair_key)
        results.append(DuplicateGroup(
            source_idx=i,
            duplicate_idx=j,
            similarity_score=(score + comp_score) / 2,
            match_type="company_fuzzy",
        ))


def detect_duplicates(
    contacts: List[Dict[str, Any]],
    existing_contacts: Optional[List[Dict[str, Any]]] = None,
    name_threshold: float = NAME_SIMILARITY_THRESHOLD,
) -> List[DuplicateGroup]:
    """
    检测一组联系人中的重复项（三重匹配）

    Args:
        contacts: 待检查的联系人列表（字典，字段: name, phone, wechat_id, company）
        existing_contacts: 数据库中的已有联系人（可选），与 contacts 联合去重
        name_threshold: 姓名相似度阈值（默认0.75）

    Returns:
        List[DuplicateGroup] — 按相似度降序排列
    """
    all_contacts = list(contacts)
    if existing_contacts:
        all_contacts.extend(existing_contacts)

    offset = len(contacts)  # 新导入的联系人范围是 [0, offset)

    results: List[DuplicateGroup] = []

    # 预处理：归一化所有字段
    normalized = []
    for c in all_contacts:
        normalized.append({
            "name": _normalize_name(c.get("name", "") or ""),
            "phone": _normalize_phone(c.get("phone", "") or ""),
            "wechat": (c.get("wechat_id", "") or "").strip().lower(),
            "company": (c.get("company", "") or "").strip().lower(),
            "email": (c.get("email", "") or "").strip().lower(),
            "name_raw": c.get("name", "") or "",
            "company_raw": c.get("company", "") or "",
        })

    # 1) 手机号精确匹配
    phone_map: Dict[str, List[int]] = {}
    for i, n in enumerate(normalized):
        if n["phone"]:
            phone_map.setdefault(n["phone"], []).append(i)

    for phone, indices in phone_map.items():
        if len(indices) >= 2:
            for idx in indices:
                for jdx in indices:
                    if idx < jdx:
                        # 至少一个在导入范围内
                        if idx < offset or jdx < offset:
                            results.append(DuplicateGroup(
                                source_idx=idx,
                                duplicate_idx=jdx,
                                similarity_score=1.0,
                                match_type="phone_exact",
                            ))

    # 2) 微信ID精确匹配
    wechat_map: Dict[str, List[int]] = {}
    for i, n in enumerate(normalized):
        if n["wechat"]:
            wechat_map.setdefault(n["wechat"], []).append(i)

    for wechat_id, indices in wechat_map.items():
        if len(indices) >= 2:
            for idx in indices:
                for jdx in indices:
                    if idx < jdx:
                        if idx < offset or jdx < offset:
                            # 避免与phone_exact重复
                            already = any(
                                r.source_idx == idx and r.duplicate_idx == jdx
                                for r in results
                            )
                            if not already:
                                results.append(DuplicateGroup(
                                    source_idx=idx,
                                    duplicate_idx=jdx,
                                    similarity_score=1.0,
                                    match_type="wechat_exact",
                                ))

    # 3) 邮箱精确匹配
    email_map: Dict[str, List[int]] = {}
    for i, n in enumerate(normalized):
        if n["email"]:
            email_map.setdefault(n["email"], []).append(i)

    for email_addr, indices in email_map.items():
        if len(indices) >= 2:
            for idx in indices:
                for jdx in indices:
                    if idx < jdx:
                        if idx < offset or jdx < offset:
                            already = any(
                                r.source_idx == idx and r.duplicate_idx == jdx
                                for r in results
                            )
                            if not already:
                                results.append(DuplicateGroup(
                                    source_idx=idx,
                                    duplicate_idx=jdx,
                                    similarity_score=1.0,
                                    match_type="email_exact",
                                ))

    # 4) 名字模糊匹配（优化版：按首字分桶 + 长度过滤，避免 O(n²)）
    # 构建名字首字索引
    name_first_char_map: Dict[str, List[int]] = {}
    for i, n in enumerate(normalized):
        raw = n["name_raw"]
        if not raw:
            continue
        # 取第一个非空字符
        raw_stripped = raw.strip()
        if not raw_stripped:
            continue
        first_char = raw_stripped[0].lower()
        name_first_char_map.setdefault(first_char, []).append(i)

    # 只比较同首字的条目，且长度差 <= 3
    matched_pairs: set = set()
    for first_char, indices in name_first_char_map.items():
        if len(indices) < 2:
            continue
        # 对超过 100 条同首字的桶，再按前2字二次分桶
        if len(indices) > 100:
            sub_buckets: Dict[str, List[int]] = {}
            for idx in indices:
                raw = normalized[idx]["name_raw"].strip()
                prefix = raw[:2].lower() if len(raw) >= 2 else raw.lower()
                sub_buckets.setdefault(prefix, []).append(idx)
            for prefix, sub_indices in sub_buckets.items():
                if len(sub_indices) < 2:
                    continue
                for ii in range(len(sub_indices)):
                    i = sub_indices[ii]
                    for jj in range(ii + 1, len(sub_indices)):
                        j = sub_indices[jj]
                        _evaluate_name_pair(i, j, normalized, offset, matched_pairs, results, name_threshold)
        else:
            for ii in range(len(indices)):
                i = indices[ii]
                for jj in range(ii + 1, len(indices)):
                    j = indices[jj]
                    _evaluate_name_pair(i, j, normalized, offset, matched_pairs, results, name_threshold)

    # 按相似度降序排列
    results.sort(key=lambda r: r.similarity_score, reverse=True)
    return results


def group_duplicates(
    contacts: List[Dict[str, Any]],
    existing_contacts: Optional[List[Dict[str, Any]]] = None,
    name_threshold: float = NAME_SIMILARITY_THRESHOLD,
) -> List[List[DuplicateGroup]]:
    """
    将重复项分组（每个组内所有记录互为重复）

    Returns:
        每个组包含该组内所有 DuplicateGroup
    """
    pairs = detect_duplicates(contacts, existing_contacts, name_threshold)

    # 用并查集(DSU)分组
    total = len(contacts) + (len(existing_contacts) if existing_contacts else 0)
    parent = list(range(total))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for pair in pairs:
        union(pair.source_idx, pair.duplicate_idx)

    # 按根节点分组
    groups_dict: Dict[int, List[DuplicateGroup]] = {}
    for pair in pairs:
        root = find(pair.source_idx)
        groups_dict.setdefault(root, []).append(pair)

    return list(groups_dict.values())
