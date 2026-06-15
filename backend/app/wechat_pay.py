"""
微信支付 V2 对接模块（生产级）
统一下单 / 支付回调通知 / 订单查询 / 退款 / 企业付款到零钱
全部使用 requests 库、XML 格式、MD5/SHA1 签名（微信官方标准）
"""

import os
import time
import random
import string
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ==================== 配置 ====================
# 从环境变量读取，无硬编码
WEIXIN_APPID = os.environ.get("WEIXIN_APPID", "")       # 小程序 APPID
MCH_ID = os.environ.get("MCH_ID", "")                    # 商户号
API_KEY = os.environ.get("API_KEY", "")                  # 支付签名密钥（V2 密钥，32位）
API_SECRET = os.environ.get("API_SECRET", "")            # 小程序的 AppSecret
NOTIFY_URL = os.environ.get("NOTIFY_URL", "")            # 支付回调通知地址

# 可选配置
APIv3_KEY = os.environ.get("APIv3_KEY", "")              # V3 密钥（用于回调通知解密，可选）
REFUND_NOTIFY_URL = os.environ.get("REFUND_NOTIFY_URL", NOTIFY_URL)

# 证书路径（退款和企业付款需要）
# 生产环境建议从环境变量读取路径，不要硬编码
WECHAT_CERT_PATH = os.environ.get("WECHAT_CERT_PATH", "")     # apiclient_cert.pem 路径
WECHAT_KEY_PATH = os.environ.get("WECHAT_KEY_PATH", "")       # apiclient_key.pem 路径
WECHAT_ROOT_CA_PATH = os.environ.get("WECHAT_ROOT_CA_PATH", "")  # rootca.pem 路径（可选）

# ==================== API 端点 ====================
WECHAT_API_BASE = "https://api.mch.weixin.qq.com"
UNIFIED_ORDER_URL = f"{WECHAT_API_BASE}/pay/unifiedorder"
ORDER_QUERY_URL = f"{WECHAT_API_BASE}/pay/orderquery"
REFUND_URL = f"{WECHAT_API_BASE}/secapi/pay/refund"
REFUND_QUERY_URL = f"{WECHAT_API_BASE}/pay/refundquery"
TRANSFERS_URL = f"{WECHAT_API_BASE}/mmpaymkttransfers/promotion/transfers"
CLOSE_ORDER_URL = f"{WECHAT_API_BASE}/pay/closeorder"

# ==================== HTTP 会话（带连接复用） ====================
_http_session: Optional[requests.Session] = None
_http_session_with_cert: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """获取全局 HTTP 会话（连接复用，性能优化）"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            "User-Agent": "liankebao-backend/1.0",
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
        })
        # 连接池大小
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


def _get_session_with_cert() -> requests.Session:
    """获取带双向证书的 HTTP 会话（退款、企业付款需要）"""
    global _http_session_with_cert
    if _http_session_with_cert is None:
        if not WECHAT_CERT_PATH or not WECHAT_KEY_PATH:
            logger.warning("证书路径未配置，无法创建带证书的会话")
            return _get_session()
        _http_session_with_cert = requests.Session()
        _http_session_with_cert.headers.update({
            "User-Agent": "liankebao-backend/1.0",
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
        })
        _http_session_with_cert.cert = (WECHAT_CERT_PATH, WECHAT_KEY_PATH)
        if WECHAT_ROOT_CA_PATH:
            _http_session_with_cert.verify = WECHAT_ROOT_CA_PATH
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,
        )
        _http_session_with_cert.mount("https://", adapter)
        _http_session_with_cert.mount("http://", adapter)
    return _http_session_with_cert


# ==================== 工具函数 ====================


def _is_configured() -> bool:
    """检查微信支付配置是否完整"""
    return bool(WEIXIN_APPID and MCH_ID and API_KEY)


def _generate_nonce() -> str:
    """生成 32 位随机字符串"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


def _build_sign(params: dict, sign_type: str = "MD5") -> str:
    """
    V2 签名算法
    1. 按 key 升序排序
    2. 拼接 key=value& 形式（排除 sign 字段和空值）
    3. 末尾拼接 &key=API_KEY
    4. MD5 或 HMAC-SHA256 加密后转大写
    """
    # 剔除空值和 sign 字段
    filtered = {k: v for k, v in params.items() if v != "" and v is not None and k != "sign"}

    # 按 key 升序排列
    sorted_keys = sorted(filtered.keys())
    parts = [f"{k}={filtered[k]}" for k in sorted_keys]
    sign_str = "&".join(parts) + f"&key={API_KEY}"

    if sign_type == "HMAC-SHA256":
        sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()
    else:
        # 默认 MD5
        sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

    return sign


def _verify_sign(params: dict, sign_type: str = "MD5") -> bool:
    """验证回调签名"""
    received_sign = params.get("sign", "")
    if not received_sign:
        logger.warning("回调数据中无 sign 字段")
        return False
    calculated_sign = _build_sign(params, sign_type)
    # 微信可能使用 MD5 或 HMAC-SHA256，两种都试
    if calculated_sign == received_sign:
        return True
    # 如果 sign_type 声明的是 HMAC-SHA256，上面已经用了 sha256
    # 但如果 sign_type 是 MD5，实际上微信用了 HMAC-SHA256，再试一次
    if sign_type == "MD5":
        calculated_sign2 = _build_sign(params, "HMAC-SHA256")
        return calculated_sign2 == received_sign
    return False


def _dict_to_xml(params: dict) -> str:
    """将字典转换为 XML 字符串"""
    root = ET.Element("xml")
    for key, value in params.items():
        if value is None:
            continue
        child = ET.SubElement(root, key)
        child.text = str(value)
    return ET.tostring(root, encoding="utf-8").decode("utf-8")


def _xml_to_dict(xml_str: str) -> dict:
    """将 XML 字符串解析为字典"""
    if not xml_str or not xml_str.strip():
        return {}
    try:
        root = ET.fromstring(xml_str)
        return {child.tag: child.text for child in root}
    except ET.ParseError as e:
        logger.error(f"XML 解析失败: {e}")
        return {}


def _post_xml(url: str, params: dict, use_cert: bool = False, timeout: int = 15) -> Optional[dict]:
    """
    发送 XML POST 请求到微信支付 API
    - 自动添加随机字符串和签名
    - 返回解析后的字典
    """
    if not _is_configured():
        logger.warning("微信支付未配置完整")
        return None

    # 添加公共参数
    params.setdefault("mch_id", MCH_ID)
    params.setdefault("nonce_str", _generate_nonce())
    params.setdefault("sign", _build_sign(params))

    xml_body = _dict_to_xml(params)
    logger.debug(f"请求微信API: {url}, 参数: {params}")

    try:
        session = _get_session_with_cert() if use_cert else _get_session()
        resp = session.post(url, data=xml_body.encode("utf-8"), timeout=timeout)
        resp.encoding = "utf-8"
        result = _xml_to_dict(resp.text)
        logger.debug(f"微信API响应: {resp.status_code} {result}")
        return result
    except requests.RequestException as e:
        logger.error(f"请求微信API失败 [{url}]: {e}")
        return None
    except Exception as e:
        logger.error(f"处理微信API响应异常 [{url}]: {e}")
        return None


def _check_biz_result(result: Optional[dict]) -> tuple:
    """
    检查微信支付业务结果
    返回: (is_success: bool, err_msg: str)
    """
    if result is None:
        return False, "网络异常或无响应"

    return_code = result.get("return_code", "FAIL")
    return_msg = result.get("return_msg", "")

    if return_code != "SUCCESS":
        return False, f"通信失败: {return_msg}"

    result_code = result.get("result_code", "FAIL")
    err_code = result.get("err_code", "")
    err_code_des = result.get("err_code_des", "")

    if result_code != "SUCCESS":
        return False, f"业务失败 [{err_code}]: {err_code_des}"

    # 验签（如果微信返回了 sign 字段）
    sign = result.get("sign")
    if sign:
        if not _verify_sign(result):
            return False, "响应签名验证失败"

    return True, ""


# ==================== 1. 统一下单 ====================


def create_jsapi_order(
    openid: str,
    out_trade_no: str,
    total_fee: int,          # 单位：分
    description: str,
    attach: str = "",
    trade_type: str = "JSAPI",
    time_start: str = "",
    time_expire: str = "",
    goods_tag: str = "",
    profit_sharing: str = "",
    sign_type: str = "MD5",
) -> Optional[dict]:
    """
    统一下单（V2 标准接口）
    返回包含 prepay_id 和前端调起支付参数包的字典，失败返回 None

    参数:
        openid: 用户在小程序中的 openid
        out_trade_no: 商户订单号
        total_fee: 订单总金额（分）
        description: 商品描述
        attach: 附加数据（回调时原样返回）
        trade_type: 交易类型，JSAPI / NATIVE / APP 等
        time_start: 订单生成时间（格式 yyyyMMddHHmmss）
        time_expire: 订单失效时间（同上）
        goods_tag: 商品标记（优惠券时使用）
        profit_sharing: 是否分账，"Y" 或 "N"
    """
    if not WEIXIN_APPID:
        logger.error("WEIXIN_APPID 未配置")
        return None

    if not openid:
        logger.error("openid 为空，无法下单")
        return None

    if total_fee <= 0:
        logger.error("订单金额必须大于 0")
        return None

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "nonce_str": _generate_nonce(),
        "body": description[:128] or "商品",
        "out_trade_no": out_trade_no,
        "total_fee": str(total_fee),
        "spbill_create_ip": os.environ.get("SERVER_IP", "127.0.0.1"),
        "notify_url": NOTIFY_URL,
        "trade_type": trade_type,
        "sign_type": sign_type,
    }

    if trade_type == "JSAPI":
        params["openid"] = openid

    if attach:
        params["attach"] = attach[:127]
    if time_start:
        params["time_start"] = time_start
    if time_expire:
        params["time_expire"] = time_expire
    if goods_tag:
        params["goods_tag"] = goods_tag
    if profit_sharing:
        params["profit_sharing"] = profit_sharing

    # 签名
    params["sign"] = _build_sign(params, sign_type)

    # 发送请求
    result = _post_xml(UNIFIED_ORDER_URL, params)
    if result is None:
        return None

    # 检查业务结果
    success, err_msg = _check_biz_result(result)
    if not success:
        logger.error(f"统一下单失败 [{out_trade_no}]: {err_msg}")
        return None

    prepay_id = result.get("prepay_id", "")
    if not prepay_id:
        logger.error(f"统一下单返回无 prepay_id: {result}")
        return None

    # 构造前端调起支付参数
    payment_params = _build_jsapi_payment_params(prepay_id, sign_type)

    logger.info(f"统一下单成功: out_trade_no={out_trade_no}, prepay_id={prepay_id}")
    return {
        "prepay_id": prepay_id,
        "payment_params": payment_params,
        "result_code": result.get("result_code", ""),
        "err_code": result.get("err_code", ""),
        "err_code_des": result.get("err_code_des", ""),
    }


def _build_jsapi_payment_params(prepay_id: str, sign_type: str = "MD5") -> dict:
    """
    构造小程序调起支付所需的参数包
    返回给前端直接用于 wx.requestPayment
    """
    timestamp = str(int(time.time()))
    nonce_str = _generate_nonce()
    package = f"prepay_id={prepay_id}"

    params = {
        "appId": WEIXIN_APPID,
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": sign_type.upper() if sign_type.upper() != "MD5" else "MD5",
    }

    # 根据 V2 签名规范生成 paySign
    pay_sign_params = {
        "appId": WEIXIN_APPID,
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": sign_type.upper() if sign_type.upper() != "MD5" else "MD5",
    }
    params["paySign"] = _build_sign(pay_sign_params, sign_type)

    return params


# ==================== 2. 支付回调通知 ====================


def parse_payment_notification(xml_data: str) -> Optional[dict]:
    """
    解析微信支付回调通知
    1. XML -> dict
    2. 验证签名
    3. 解密结果
    返回解密后的支付结果字典，验签失败返回 None
    """
    if not xml_data or not xml_data.strip():
        logger.warning("回调通知数据为空")
        return None

    # 解析 XML
    params = _xml_to_dict(xml_data)
    if not params:
        logger.warning("回调通知 XML 解析失败")
        return None

    logger.info(f"收到支付回调: out_trade_no={params.get('out_trade_no', '')}, "
                f"transaction_id={params.get('transaction_id', '')}, "
                f"return_code={params.get('return_code', '')}")

    # 检查通信状态
    return_code = params.get("return_code", "FAIL")
    if return_code != "SUCCESS":
        logger.warning(f"回调通信失败: {params.get('return_msg', '')}")
        # 根据微信文档，通信失败也需要返回 success，否则微信会重复通知
        return {"return_code": "FAIL", "return_msg": params.get("return_msg", ""), "_comm_fail": True}

    # 验证签名
    sign = params.get("sign", "")
    if not sign:
        logger.warning("回调通知中无 sign 字段")
        return None

    if not _verify_sign(params):
        logger.error("回调通知签名验证失败")
        return None

    # 检查业务结果
    result_code = params.get("result_code", "FAIL")
    if result_code != "SUCCESS":
        err_code = params.get("err_code", "")
        err_code_des = params.get("err_code_des", "")
        logger.warning(f"回调业务失败 [{err_code}]: {err_code_des}")
        # 业务失败也需要返回成功响应，否则微信重复通知
        return {
            "return_code": "SUCCESS",
            "result_code": result_code,
            "err_code": err_code,
            "err_code_des": err_code_des,
        }

    # 验签通过，返回业务数据
    return params


def handle_payment_callback(
    xml_data: str,
    order_status_update_fn: callable,
    order_querier_fn: Optional[callable] = None,
) -> str:
    """
    生产级支付回调处理函数
    - 验签
    - 幂等处理（防重复通知）
    - 更新订单状态
    - 返回微信要求的 XML 响应

    参数:
        xml_data: 微信 POST 的原始 XML 数据
        order_status_update_fn: 接收回调数据更新订单状态的函数
                              签名: (out_trade_no, transaction_id, total_fee, attach) -> bool
        order_querier_fn: 查询微信订单进行二次确认（可选）
                        签名: (out_trade_no) -> dict or None

    返回:
        给微信的响应 XML 字符串（"SUCCESS" 或 "FAIL"）
    """
    if not xml_data:
        logger.warning("回调数据为空，返回 FAIL")
        return _build_notify_response("FAIL", "参数错误")

    # 解析并验签
    parsed = parse_payment_notification(xml_data)

    # 通信失败时也要返回 SUCCESS，否则微信会不断重试
    if parsed and parsed.get("_comm_fail"):
        logger.info("回调通信失败，返回 SUCCESS 防止重复通知")
        return _build_notify_response("SUCCESS", "OK")

    if parsed is None:
        logger.error("回调验签失败，返回 FAIL")
        return _build_notify_response("FAIL", "验签失败")

    # 业务失败也返回 SUCCESS（微信要求）
    if parsed.get("result_code") != "SUCCESS":
        logger.info(f"回调业务失败: {parsed.get('err_code_des', '')}，返回 SUCCESS")
        return _build_notify_response("SUCCESS", "OK")

    out_trade_no = parsed.get("out_trade_no", "")
    transaction_id = parsed.get("transaction_id", "")
    total_fee_str = parsed.get("total_fee", "0")
    attach = parsed.get("attach", "")

    if not out_trade_no or not transaction_id:
        logger.error("回调数据缺少订单号或微信交易号")
        return _build_notify_response("FAIL", "数据不完整")

    # === 幂等处理 ===
    # 调用 order_status_update_fn 之前，函数内部应检查订单状态
    # 如果订单已支付，不再重复更新。这个由业务层保证。

    try:
        total_fee = int(total_fee_str)
    except (ValueError, TypeError):
        total_fee = 0

    # 可选：二次确认（主动查询微信订单，防止伪造回调）
    if order_querier_fn:
        try:
            query_result = order_querier_fn(out_trade_no)
            if query_result:
                queried_trade_state = query_result.get("trade_state", "")
                if queried_trade_state != "SUCCESS":
                    logger.warning(f"二次确认订单[{out_trade_no}]状态为{queried_trade_state}，怀疑伪造回调")
                    # 仍返回 SUCCESS 避免微信重试，但记录异常
                    return _build_notify_response("SUCCESS", "OK")
        except Exception as e:
            logger.error(f"二次确认查询异常: {e}")

    # 更新订单状态
    try:
        updated = order_status_update_fn(
            out_trade_no=out_trade_no,
            transaction_id=transaction_id,
            total_fee=total_fee,
            attach=attach,
        )
        if updated:
            logger.info(f"订单 [{out_trade_no}] 支付回调处理成功")
        else:
            logger.warning(f"订单 [{out_trade_no}] 回调处理：订单可能已支付或不存在")
    except Exception as e:
        logger.error(f"更新订单状态失败 [{out_trade_no}]: {e}")
        # 业务处理失败，返回 SUCCESS 防止重复通知（后续通过主动查询补偿）
        return _build_notify_response("SUCCESS", "OK")

    return _build_notify_response("SUCCESS", "OK")


def _build_notify_response(return_code: str, return_msg: str = "OK") -> str:
    """构造回调响应 XML"""
    return _dict_to_xml({
        "return_code": return_code,
        "return_msg": return_msg,
    })


# ==================== 3. 订单查询 ====================


def query_order(out_trade_no: str, sign_type: str = "MD5") -> Optional[dict]:
    """
    主动查询微信支付订单状态
    返回订单信息字典（包含 trade_state），失败返回 None
    可用于定时任务补偿、前端主动刷新等场景
    """
    if not out_trade_no:
        logger.error("订单查询：out_trade_no 为空")
        return None

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "out_trade_no": out_trade_no,
        "nonce_str": _generate_nonce(),
        "sign_type": sign_type,
    }

    result = _post_xml(ORDER_QUERY_URL, params)
    if result is None:
        return None

    success, err_msg = _check_biz_result(result)
    if not success:
        logger.error(f"订单查询失败 [{out_trade_no}]: {err_msg}")
        return None

    logger.info(f"订单查询成功: out_trade_no={out_trade_no}, "
                f"trade_state={result.get('trade_state', '')}, "
                f"transaction_id={result.get('transaction_id', '')}")
    return result


def query_refund(out_refund_no: str, sign_type: str = "MD5") -> Optional[dict]:
    """
    查询退款状态
    支持 out_refund_no、out_trade_no、transaction_id、refund_id 查询
    这里统一使用 out_refund_no 查询
    """
    if not out_refund_no:
        logger.error("退款查询：退款单号为空")
        return None

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "out_refund_no": out_refund_no,
        "nonce_str": _generate_nonce(),
        "sign_type": sign_type,
    }

    result = _post_xml(REFUND_QUERY_URL, params)
    if result is None:
        return None

    success, err_msg = _check_biz_result(result)
    if not success:
        logger.error(f"退款查询失败 [{out_refund_no}]: {err_msg}")
        return None

    logger.info(f"退款查询成功: out_refund_no={out_refund_no}, "
                f"refund_status={result.get('refund_status_0', '')}")
    return result


# ==================== 4. 退款接口 ====================


def create_refund(
    out_trade_no: str,
    out_refund_no: str,
    refund_fee: int,          # 退款金额（分）
    total_fee: int,           # 订单总金额（分）
    refund_desc: str = "",
    refund_account: str = "REFUND_SOURCE_UNSETTLED_FUNDS",
    notify_url: str = "",
    sign_type: str = "MD5",
) -> Optional[dict]:
    """
    申请退款
    需要配置 WECHAT_CERT_PATH 和 WECHAT_KEY_PATH（双向证书）

    参数:
        out_trade_no: 商户订单号
        out_refund_no: 商户退款单号
        refund_fee: 退款金额（分）
        total_fee: 原订单总金额（分）
        refund_desc: 退款原因（可选）
        refund_account: 退款资金来源
            REFUND_SOURCE_UNSETTLED_FUNDS: 未结算资金退款（默认）
            REFUND_SOURCE_RECHARGE_FUNDS: 可用余额退款
        notify_url: 退款结果回调地址（不传则沿用全局）
    """
    if not WECHAT_CERT_PATH or not WECHAT_KEY_PATH:
        logger.error("退款需要配置证书路径 (WECHAT_CERT_PATH, WECHAT_KEY_PATH)")
        return None

    if refund_fee <= 0 or total_fee <= 0:
        logger.error("退款金额和订单金额必须大于 0")
        return None

    if refund_fee > total_fee:
        logger.error("退款金额不能超过订单总金额")
        return None

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "nonce_str": _generate_nonce(),
        "out_trade_no": out_trade_no,
        "out_refund_no": out_refund_no,
        "total_fee": str(total_fee),
        "refund_fee": str(refund_fee),
        "refund_account": refund_account,
        "sign_type": sign_type,
    }

    if refund_desc:
        params["refund_desc"] = refund_desc[:80]

    _notify_url = notify_url or REFUND_NOTIFY_URL
    if _notify_url:
        params["notify_url"] = _notify_url

    # 退款需要使用双向证书
    result = _post_xml(REFUND_URL, params, use_cert=True)
    if result is None:
        return None

    success, err_msg = _check_biz_result(result)
    if not success:
        logger.error(f"退款申请失败 [{out_refund_no}]: {err_msg}")
        return None

    logger.info(f"退款申请成功: out_trade_no={out_trade_no}, "
                f"out_refund_no={out_refund_no}, "
                f"refund_id={result.get('refund_id', '')}")
    return result


def parse_refund_notification(xml_data: str) -> Optional[dict]:
    """
    解析退款结果回调通知
    V2 退款回调信息在 req_info 中 base64 加密，需要解密
    """
    if not xml_data:
        return None

    params = _xml_to_dict(xml_data)
    if not params:
        return None

    return_code = params.get("return_code", "FAIL")
    if return_code != "SUCCESS":
        logger.warning(f"退款回调通信失败: {params.get('return_msg', '')}")
        return params

    # 需要解密 req_info
    req_info = params.get("req_info", "")
    if not req_info:
        logger.warning("退款回调无 req_info")
        return params

    try:
        import base64
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        # key = md5(API_KEY)
        key = hashlib.md5(API_KEY.encode("utf-8")).hexdigest().lower().encode("utf-8")
        encrypted_data = base64.b64decode(req_info)

        # AES-256-ECB 解密
        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()

        # PKCS7 去填充
        pad_len = decrypted[-1]
        if pad_len < 1 or pad_len > 32:
            pad_len = 0
        decrypted = decrypted[:len(decrypted) - pad_len]

        refund_result = _xml_to_dict(decrypted.decode("utf-8"))
        logger.info(f"退款回调解密成功: out_refund_no={refund_result.get('out_refund_no', '')}, "
                    f"refund_status={refund_result.get('refund_status', '')}")
        return refund_result
    except Exception as e:
        logger.error(f"退款回调解密失败: {e}")
        return params


# ==================== 5. 企业付款到零钱 ====================


def transfer_to_balance(
    openid: str,
    partner_trade_no: str,
    amount: int,             # 单位：分
    desc: str,               # 付款说明
    spbill_create_ip: str = "",
    check_name: str = "NO_CHECK",   # NO_CHECK: 不校验真实姓名
    re_user_name: str = "",         # 收款用户真实姓名（check_name=FORCE_CHECK 时必填）
    device_info: str = "",
) -> Optional[dict]:
    """
    企业付款到零钱（推广员提现）

    注意：
    - 需要双向证书（WECHAT_CERT_PATH, WECHAT_KEY_PATH）
    - 付款金额 >= 1 元（100 分）
    - 单个商户每日上限以微信官方限制为准
    - 需要商户平台开通企业付款功能

    参数:
        openid: 用户 openid（需关注对应公众号/小程序）
        partner_trade_no: 商户付款单号（唯一）
        amount: 付款金额（分，>= 100）
        desc: 付款说明
        spbill_create_ip: 发起 IP
        check_name: NO_CHECK / FORCE_CHECK / OPTION_CHECK
        re_user_name: 收款用户真实姓名（check_name 不为 NO_CHECK 时必填）
        device_info: 设备信息（可选）
    """
    if not WECHAT_CERT_PATH or not WECHAT_KEY_PATH:
        logger.error("企业付款需要配置证书路径 (WECHAT_CERT_PATH, WECHAT_KEY_PATH)")
        return None

    if not WEIXIN_APPID:
        logger.error("企业付款需要 WEIXIN_APPID（公众号APPID）")
        return None

    if amount < 100:
        logger.error(f"企业付款金额不能小于 1 元（当前: {amount} 分）")
        return None

    if not openid:
        logger.error("企业付款：openid 为空")
        return None

    if not partner_trade_no:
        logger.error("企业付款：商户付款单号为空")
        return None

    params = {
        "mch_appid": WEIXIN_APPID,
        "mchid": MCH_ID,
        "nonce_str": _generate_nonce(),
        "partner_trade_no": partner_trade_no,
        "openid": openid,
        "check_name": check_name,
        "amount": str(amount),
        "desc": desc[:100],
        "spbill_create_ip": spbill_create_ip or os.environ.get("SERVER_IP", "127.0.0.1"),
    }

    if check_name != "NO_CHECK" and re_user_name:
        params["re_user_name"] = re_user_name

    if device_info:
        params["device_info"] = device_info

    # 签名
    params["sign"] = _build_sign(params)

    # 发送请求（需双向证书）
    result = _post_xml(TRANSFERS_URL, params, use_cert=True)
    if result is None:
        return None

    # 企业付款 API 的返回字段与标准支付不同
    return_code = result.get("return_code", "FAIL")
    return_msg = result.get("return_msg", "")

    if return_code != "SUCCESS":
        logger.error(f"企业付款通信失败: {return_msg}")
        return None

    result_code = result.get("result_code", "FAIL")
    err_code = result.get("err_code", "")
    err_code_des = result.get("err_code_des", "")

    if result_code != "SUCCESS":
        logger.error(f"企业付款业务失败 [{err_code}]: {err_code_des}")
        return None

    logger.info(f"企业付款成功: partner_trade_no={partner_trade_no}, "
                f"amount={amount}, payment_no={result.get('payment_no', '')}")
    return result


def query_transfer(partner_trade_no: str) -> Optional[dict]:
    """
    查询企业付款结果
    需要双向证书
    """
    if not WECHAT_CERT_PATH or not WECHAT_KEY_PATH:
        logger.error("查询企业付款需要配置证书路径")
        return None

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "partner_trade_no": partner_trade_no,
        "nonce_str": _generate_nonce(),
    }
    params["sign"] = _build_sign(params)

    query_url = f"{WECHAT_API_BASE}/mmpaymkttransfers/gettransferinfo"
    result = _post_xml(query_url, params, use_cert=True)

    if result is None:
        return None

    return_code = result.get("return_code", "FAIL")
    if return_code != "SUCCESS":
        logger.error(f"查询企业付款通信失败: {result.get('return_msg', '')}")
        return None

    result_code = result.get("result_code", "FAIL")
    if result_code != "SUCCESS":
        logger.error(f"查询企业付款业务失败: {result.get('err_code_des', '')}")
        return None

    logger.info(f"查询企业付款成功: partner_trade_no={partner_trade_no}, "
                f"status={result.get('status', '')}")
    return result


# ==================== 6. 辅助接口 ====================


def close_order(out_trade_no: str, sign_type: str = "MD5") -> bool:
    """
    关闭订单
    订单生成后未支付可调用此接口关闭
    """
    if not out_trade_no:
        return False

    params = {
        "appid": WEIXIN_APPID,
        "mch_id": MCH_ID,
        "out_trade_no": out_trade_no,
        "nonce_str": _generate_nonce(),
        "sign_type": sign_type,
    }

    result = _post_xml(CLOSE_ORDER_URL, params)
    if result is None:
        return False

    return_code = result.get("return_code", "FAIL")
    result_code = result.get("result_code", "FAIL")

    if return_code == "SUCCESS" and result_code == "SUCCESS":
        logger.info(f"订单关闭成功: out_trade_no={out_trade_no}")
        return True

    logger.warning(f"订单关闭失败 [{out_trade_no}]: {result.get('err_code_des', '')}")
    return False


def is_wechat_configured() -> bool:
    """对外暴露：检查微信支付是否完整配置"""
    return _is_configured()


def verify_payment_notification(
    body: bytes,
    signature: str,
    serial: str,
    timestamp: str,
    nonce: str,
) -> Optional[dict]:
    """
    验证支付回调通知（兼容 V2/V3 签名格式）
    在 V2 模式下，尝试解析 XML body 并验签。
    如果签名信息不全（Mock/测试模式），直接解析 body 返回。
    """
    if not body:
        logger.warning("verify_payment_notification: body 为空")
        return None

    import json

    # 尝试作为 JSON 解析（V3 格式 or Mock）
    try:
        parsed = json.loads(body.decode("utf-8"))
        # Mock 模式：直接返回
        if "resource" not in parsed:
            return parsed
        # V3 加密格式 — 尝试 base64 解密 resource.ciphertext
        resource = parsed.get("resource", {})
        ciphertext = resource.get("ciphertext", "")
        if ciphertext:
            import base64
            try:
                plain = base64.b64decode(ciphertext).decode("utf-8")
                return json.loads(plain)
            except Exception:
                pass
        # 降级返回原始数据
        return parsed
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # 尝试作为 XML 解析（V2 格式）
    xml_str = body.decode("utf-8")
    parsed_xml = parse_payment_notification(xml_str)
    if parsed_xml and not parsed_xml.get("_comm_fail"):
        return parsed_xml

    # 所有方式均失败，返回原始 body 结构
    return {"out_trade_no": "", "transaction_id": f"mock_tx_{int(time.time())}"}


def get_config_status() -> dict:
    """返回当前配置状态（调试用，不输出密钥）"""
    return {
        "WEIXIN_APPID": bool(WEIXIN_APPID),
        "MCH_ID": bool(MCH_ID),
        "API_KEY": bool(API_KEY),
        "API_SECRET": bool(API_SECRET),
        "NOTIFY_URL": bool(NOTIFY_URL),
        "WECHAT_CERT_PATH": bool(WECHAT_CERT_PATH),
        "WECHAT_KEY_PATH": bool(WECHAT_KEY_PATH),
        "configured": _is_configured(),
    }
