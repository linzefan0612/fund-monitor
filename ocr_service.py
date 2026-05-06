# -*- coding: utf-8 -*-
"""
基金实时监控助手 - OCR识别服务
支持多种OCR服务，用于识别持仓截图
"""

import re
import json
import base64
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

# 导入配置
try:
    from ocr_config import (
        OCR_ENABLED, OCR_PROVIDER,
        BAIDU_OCR, TENCENT_OCR, ALIYUN_OCR, CUSTOM_OCR
    )
except ImportError:
    OCR_ENABLED = False
    OCR_PROVIDER = "baidu"
    BAIDU_OCR = {}
    TENCENT_OCR = {}
    ALIYUN_OCR = {}
    CUSTOM_OCR = {}

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class OCRResult:
    """OCR识别结果"""
    def __init__(self, success: bool, funds: List[Dict] = None, message: str = ""):
        self.success = success
        self.funds = funds or []
        self.message = message

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "funds": self.funds,
            "message": self.message
        }


class BaiduOCR:
    """百度OCR服务"""

    def __init__(self, config: dict):
        self.config = config
        self.access_token = None

    def _get_access_token(self) -> Optional[str]:
        """获取百度OCR access_token"""
        if not self.config.get("api_key") or not self.config.get("secret_key"):
            return None

        try:
            import requests
            url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={self.config['api_key']}&client_secret={self.config['secret_key']}"
            response = requests.post(url, timeout=10)
            result = response.json()
            return result.get("access_token")
        except Exception as e:
            logger.error(f"获取百度OCR access_token失败: {e}")
            return None

    def recognize(self, image_data: bytes) -> Optional[str]:
        """识别图片中的文字"""
        token = self._get_access_token()
        if not token:
            return None

        try:
            import requests
            url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={token}"
            img_base64 = base64.b64encode(image_data).decode()
            data = {"image": img_base64}
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = requests.post(url, data=data, headers=headers, timeout=30)
            result = response.json()

            if "words_result" in result:
                texts = [item["words"] for item in result["words_result"]]
                return "\n".join(texts)
            return None
        except Exception as e:
            logger.error(f"百度OCR识别失败: {e}")
            return None


class TencentOCR:
    """腾讯OCR服务"""

    def __init__(self, config: dict):
        self.config = config

    def recognize(self, image_data: bytes) -> Optional[str]:
        """识别图片中的文字"""
        if not self.config.get("secret_id") or not self.config.get("secret_key"):
            return None

        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.ocr.v20181119 import ocr_client, models

            cred = credential.Credential(self.config["secret_id"], self.config["secret_key"])
            httpProfile = HttpProfile()
            httpProfile.endpoint = "ocr.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile

            client = ocr_client.OcrClient(cred, self.config.get("region", "ap-guangzhou"), clientProfile)
            req = models.GeneralAccurateOCRRequest()
            req.ImageBase64 = base64.b64encode(image_data).decode()

            resp = client.GeneralAccurateOCR(req)
            texts = [item.DetectedText for item in resp.TextDetects]
            return "\n".join(texts)
        except ImportError:
            logger.warning("腾讯云SDK未安装，请执行: pip install tencentcloud-sdk-python")
            return None
        except Exception as e:
            logger.error(f"腾讯OCR识别失败: {e}")
            return None


class AliyunOCR:
    """阿里云OCR服务"""

    def __init__(self, config: dict):
        self.config = config

    def recognize(self, image_data: bytes) -> Optional[str]:
        """识别图片中的文字"""
        if not self.config.get("access_key_id") or not self.config.get("access_key_secret"):
            return None

        try:
            import requests
            url = f"https://{self.config.get('endpoint', 'ocr-api.cn-hangzhou.aliyuncs.com')}/"
            img_base64 = base64.b64encode(image_data).decode()

            # 阿里云OCR需要签名，这里简化处理
            # 实际使用需要安装 aliyun-python-sdk-core
            logger.warning("阿里云OCR需要安装SDK并配置签名，请参考文档")
            return None
        except Exception as e:
            logger.error(f"阿里云OCR识别失败: {e}")
            return None


class FundParser:
    """基金信息解析器"""

    # 基金代码正则（6位数字）
    FUND_CODE_PATTERN = re.compile(r'\b(\d{6})\b')

    # 收益率正则
    RETURN_RATE_PATTERNS = [
        re.compile(r'收益率\s*[:：]?\s*([+-]?\d+\.?\d*)\s*%?'),
        re.compile(r'持有收益[率]?\s*[:：]?\s*([+-]?\d+\.?\d*)\s*%?'),
        re.compile(r'盈亏[比例]?\s*[:：]?\s*([+-]?\d+\.?\d*)\s*%?'),
        re.compile(r'([+-]\d+\.?\d*)\s*%'),
    ]

    # 基金名称常见关键词（用于识别基金名称行）
    FUND_KEYWORDS = ['基金', 'ETF', 'LOF', 'QDII', '混合', '股票', '债券', '指数', '货币', '理财', '联接', '定投']

    # 基金类型后缀（C/A类）
    FUND_TYPE_SUFFIX = ['A', 'C', 'E', 'R']

    def parse_text(self, text: str) -> List[Dict]:
        """解析OCR识别出的文本，提取基金信息"""
        funds = []
        lines = text.split('\n')

        current_fund = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 尝试匹配基金代码
            code_match = self.FUND_CODE_PATTERN.search(line)
            if code_match:
                code = code_match.group(1)

                # 如果找到新的基金代码，保存之前的基金信息
                if current_fund and (current_fund.get('fund_code') or current_fund.get('fund_name')):
                    funds.append(current_fund)

                # 开始新的基金信息
                current_fund = {
                    'fund_code': code,
                    'fund_name': '',
                    'current_amount': 0,
                    'holding_return_rate': 0,
                    'raw_line': line
                }

                # 尝试提取基金名称（代码后的文字）
                name_part = line[code_match.end():].strip()
                if name_part:
                    # 清理名称
                    for kw in self.FUND_KEYWORDS:
                        if kw in name_part:
                            current_fund['fund_name'] = name_part[:30]
                            break
            else:
                # 没有基金代码，尝试识别基金名称
                # 检查是否是基金名称行（包含基金关键词和金额）
                has_fund_keyword = any(kw in line for kw in self.FUND_KEYWORDS)
                # 检查是否有金额格式 (如 1,153.60 或 5,882.09)
                has_amount = bool(re.search(r'[\d,]+\.\d{2}', line))

                if has_fund_keyword and has_amount:
                    # 可能是基金名称行
                    fund_name = self._extract_fund_name(line)

                    if fund_name and len(fund_name) >= 4:
                        # 保存之前的基金
                        if current_fund and (current_fund.get('fund_code') or current_fund.get('fund_name')):
                            funds.append(current_fund)

                        # 提取金额 - 找第一个看起来像金额的数字
                        amount = 0
                        amount_match = re.search(r'([\d,]+\.\d{2})', line)
                        if amount_match:
                            try:
                                amount = float(amount_match.group(1).replace(',', ''))
                            except ValueError:
                                pass

                        # 提取收益率 - 找最后一个带%的数字或带+/-的数字
                        return_rate = 0
                        rate_matches = re.findall(r'([+-]?\d+\.?\d*)\s*%?', line)
                        if rate_matches:
                            # 优先找带+或-的数字
                            for r in rate_matches:
                                try:
                                    val = float(r)
                                    if val != amount:
                                        # 排除金额，取最后一个作为收益率
                                        return_rate = val
                                except ValueError:
                                    pass

                        current_fund = {
                            'fund_code': '',
                            'fund_name': fund_name,
                            'current_amount': amount,
                            'holding_return_rate': return_rate,
                            'raw_line': line
                        }

            # 尝试匹配持仓金额
            if current_fund:
                for pattern in self.RETURN_RATE_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        try:
                            current_fund['holding_return_rate'] = float(match.group(1))
                            break
                        except ValueError:
                            pass

        # 添加最后一个基金
        if current_fund and (current_fund.get('fund_code') or current_fund.get('fund_name')):
            funds.append(current_fund)

        # 过滤无效结果
        valid_funds = []
        for fund in funds:
            # 有基金代码的，验证格式
            code = fund.get('fund_code', '')
            if code:
                if code and (code.startswith('0') or code.startswith('1') or code.startswith('2') or
                            code.startswith('3') or code.startswith('5') or code.startswith('6')):
                    valid_funds.append(fund)
            # 没有基金代码但有基金名称的也保留
            elif fund.get('fund_name'):
                valid_funds.append(fund)

        return valid_funds

    def _extract_fund_name(self, line: str) -> str:
        """从行中提取基金名称"""
        # 移除空格以便匹配
        line_no_space = line.replace(' ', '')

        # 尝试匹配各种基金名称模式
        patterns = [
            # ETF联接C/A
            r'([\u4e00-\u9fa5]+ETF联接[A-C])',
            # ETF
            r'([\u4e00-\u9fa5]+ETF)',
            # 混合C/A
            r'([\u4e00-\u9fa5]+混合[发起]?[A-C]?)',
            # 债券C/A
            r'([\u4e00-\u9fa5]+债券[A-C])',
            # 指数C/A
            r'([\u4e00-\u9fa5]+指数[A-C]?)',
            # 股票C/A
            r'([\u4e00-\u9fa5]+股票[A-C]?)',
            # 智选混合
            r'([\u4e00-\u9fa5]+智选混合[发起]?[A-C]?)',
            # 其他带关键词的
            r'([\u4e00-\u9fa5]+(?:基金|LOF|QDII|货币|理财)[A-C]?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, line_no_space)
            if match:
                name = match.group(1)
                # 补全可能的联接C等后缀
                if 'ETF' in name and '联接' not in name:
                    # 检查后面是否有联接C
                    after_match = line_no_space[match.end():match.end()+4]
                    if after_match.startswith('联接'):
                        name += after_match[:4]
                return name

        # 如果上面都没匹配，尝试从原始行提取
        # 找中文字符开头的部分
        chinese_match = re.search(r'([\u4e00-\u9fa5][\u4e00-\u9fa5\s]+(?:ETF|LOF|QDII|混合|股票|债券|指数|货币|理财|联接)[A-C]?)', line)
        if chinese_match:
            return chinese_match.group(1).replace(' ', '')

        return ''


class OCRService:
    """OCR服务统一接口"""

    def __init__(self):
        self.parser = FundParser()
        self.provider = None

        if OCR_ENABLED:
            if OCR_PROVIDER == "baidu":
                self.provider = BaiduOCR(BAIDU_OCR)
            elif OCR_PROVIDER == "tencent":
                self.provider = TencentOCR(TENCENT_OCR)
            elif OCR_PROVIDER == "aliyun":
                self.provider = AliyunOCR(ALIYUN_OCR)
            elif OCR_PROVIDER == "custom":
                # 自定义OCR，需要实现recognize方法
                pass

    def is_third_party_enabled(self) -> bool:
        """检查是否启用了第三方OCR"""
        return OCR_ENABLED and self.provider is not None

    def get_provider_name(self) -> str:
        """获取当前OCR服务商名称"""
        if not OCR_ENABLED:
            return "本地Tesseract"
        return {
            "baidu": "百度OCR",
            "tencent": "腾讯OCR",
            "aliyun": "阿里云OCR",
            "custom": "自定义OCR"
        }.get(OCR_PROVIDER, "未知")

    def recognize_image(self, image_data: bytes) -> OCRResult:
        """
        识别图片中的基金信息

        Args:
            image_data: 图片二进制数据

        Returns:
            OCRResult对象，包含识别结果
        """
        text = None

        # 尝试使用第三方OCR
        if self.is_third_party_enabled() and self.provider:
            logger.info(f"使用第三方OCR服务: {self.get_provider_name()}")
            text = self.provider.recognize(image_data)

        # 如果第三方OCR失败，返回提示使用前端Tesseract
        if not text:
            return OCRResult(
                success=False,
                message="第三方OCR未配置或识别失败，请使用前端本地识别",
                funds=[]
            )

        # 解析文本
        funds = self.parser.parse_text(text)

        return OCRResult(
            success=True,
            funds=funds,
            message=f"识别完成，共发现 {len(funds)} 只基金"
        )


# 创建全局实例
ocr_service = OCRService()
