# -*- coding: utf-8 -*-
"""
基金实时监控助手 - 基金数据获取模块
支持多个数据源获取基金数据
"""

import re
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from abc import ABC, abstractmethod

import requests

from config import (
    FUND_INFO_API, HEADERS, REQUEST_TIMEOUT,
    REQUEST_RETRIES, PROXY
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaseDataFetcher(ABC):
    """数据获取器基类"""

    def __init__(self, name: str):
        self.name = name
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.trust_env = False  # 忽略系统代理设置，避免SSL错误
        if PROXY:
            self.session.proxies.update(PROXY)

    def _fetch_with_retry(self, url: str, params: dict = None, headers: dict = None) -> Optional[str]:
        """带重试机制的请求方法"""
        req_headers = headers or HEADERS
        for attempt in range(REQUEST_RETRIES):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=req_headers,
                    timeout=REQUEST_TIMEOUT
                )
                response.encoding = 'utf-8'
                return response.text
            except requests.RequestException as e:
                logger.warning(f"[{self.name}] 请求失败 (尝试 {attempt + 1}/{REQUEST_RETRIES}): {e}")
                if attempt < REQUEST_RETRIES - 1:
                    time.sleep(1)
        return None

    @abstractmethod
    def get_fund_realtime_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金实时数据"""
        pass

    @abstractmethod
    def get_fund_detail_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详细数据"""
        pass

    @staticmethod
    def _safe_float(value: Any) -> float:
        """安全转换为浮点数"""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def get_fund_history(self, fund_code: str, period: str = '1y') -> Optional[Dict[str, Any]]:
        """获取基金历史净值数据（子类可重写）"""
        return None

    def get_fund_holdings(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金持仓数据（子类可重写）"""
        return None


class TiantianFundFetcher(BaseDataFetcher):
    """天天基金网数据源"""

    def __init__(self):
        super().__init__("天天基金")
        self.info_api = "http://fundgz.1234567.com.cn/js/{fund_code}.js"
        self.detail_api = "http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"

    def _parse_jsonp(self, text: str) -> Optional[dict]:
        """解析JSONP格式响应"""
        try:
            match = re.search(r'jsonpgz\((.*)\)', text)
            if match:
                return json.loads(match.group(1))
            match = re.search(r'jsonp\((.*)\)', text)
            if match:
                return json.loads(match.group(1))
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"[{self.name}] JSON解析失败: {e}")
            return None

    def get_fund_realtime_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金实时数据"""
        url = self.info_api.format(fund_code=fund_code)
        text = self._fetch_with_retry(url)

        if not text:
            logger.error(f"[{self.name}] 获取基金 {fund_code} 实时数据失败")
            return None

        data = self._parse_jsonp(text)
        if not data:
            # 估值接口返回空数据，尝试使用移动端API获取基本信息
            logger.info(f"[{self.name}] 估值接口无数据，尝试移动端API: {fund_code}")
            return self._get_fund_data_from_mobile_api(fund_code)

        try:
            result = {
                'fund_code': fund_code,
                'fund_name': data.get('name', ''),
                'fund_type': data.get('fundtype', ''),
                'nav': self._safe_float(data.get('dwjz')),
                'nav_date': data.get('jzrq', ''),
                'estimated_nav': self._safe_float(data.get('gsz')),
                'estimated_time': data.get('gztime', ''),
                'estimated_change': self._safe_float(data.get('gszzl')),
                'yesterday_nav': self._safe_float(data.get('dwjz')),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': self.name
            }
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 数据失败: {e}")
            return None

    def _get_fund_data_from_mobile_api(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        从pingzhongdata接口获取基金数据（备选方案）

        当估值接口不支持某些基金时使用
        """
        url = self.detail_api.format(fund_code=fund_code)
        text = self._fetch_with_retry(url)

        if not text or len(text) < 100:
            return None

        try:
            # 提取基金名称
            fund_name = ''
            match = re.search(r'fS_name\s*=\s*["\']([^"\']+)["\']', text)
            if match:
                fund_name = match.group(1)

            # 从净值趋势数据获取最新净值
            nav = 0
            nav_date = ''
            match = re.search(r'Data_netWorthTrend\s*=\s*(\[[^\]]+\])', text)
            if match:
                try:
                    import json as json_module
                    trend_data = json_module.loads(match.group(1))
                    if trend_data and len(trend_data) > 0:
                        last_item = trend_data[-1]
                        nav = last_item.get('y', 0)
                        # 转换时间戳
                        ts = last_item.get('x', 0)
                        if ts:
                            from datetime import datetime as dt
                            nav_date = dt.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
                except:
                    pass

            # 获取收益率
            syl_1y = 0
            match = re.search(r'syl_1y\s*=\s*"([^"]+)"', text)
            if match:
                syl_1y = self._safe_float(match.group(1))

            if not fund_name or nav == 0:
                return None

            return {
                'fund_code': fund_code,
                'fund_name': fund_name,
                'fund_type': '',
                'nav': nav,
                'nav_date': nav_date,
                'estimated_nav': 0,  # 此接口不提供估算净值
                'estimated_time': '',
                'estimated_change': 0,  # 此接口不提供估算涨跌
                'yesterday_nav': nav,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': self.name,
                'returns': {
                    'one_year': syl_1y
                }
            }
        except Exception as e:
            logger.error(f"[{self.name}] pingzhongdata接口获取基金 {fund_code} 数据失败: {e}")
            return None

    def get_fund_detail_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详细信息"""
        url = self.detail_api.format(fund_code=fund_code)
        text = self._fetch_with_retry(url)

        if not text:
            return None

        try:
            result = {
                'fund_code': fund_code,
                'manager': self._extract_manager(text),
                'manager_date': self._extract_manager_date(text),
                'fund_scale': self._extract_scale(text),
                'stock_positions': self._extract_stock_positions(text),
                'returns': self._extract_returns(text),
                'max_drawdown': self._extract_max_drawdown(text)
            }
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 详细数据失败: {e}")
            return None

    def _extract_manager(self, text: str) -> str:
        match = re.search(r'fund_manager[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]', text)
        return match.group(1) if match else ''

    def _extract_manager_date(self, text: str) -> str:
        match = re.search(r'fund_manager_date[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]', text)
        return match.group(1) if match else ''

    def _extract_scale(self, text: str) -> float:
        match = re.search(r'fund_scale[\'"]\s*:\s*([\d.]+)', text)
        return float(match.group(1)) if match else 0.0

    def _extract_stock_positions(self, text: str) -> List[Dict[str, Any]]:
        positions = []
        try:
            stock_codes_match = re.search(r'stockCodes[\'"]\s*:\s*\[([^\]]+)\]', text)
            stock_names_match = re.search(r'stockNames[\'"]\s*:\s*\[([^\]]+)\]', text)
            stock_weights_match = re.search(r'stockWeights[\'"]\s*:\s*\[([^\]]+)\]', text)

            if stock_codes_match and stock_names_match and stock_weights_match:
                codes = re.findall(r'[\'"]([^\'"]+)[\'"]', stock_codes_match.group(1))
                names = re.findall(r'[\'"]([^\'"]+)[\'"]', stock_names_match.group(1))
                weights = re.findall(r'([\d.]+)', stock_weights_match.group(1))

                for i in range(min(len(codes), len(names), len(weights))):
                    positions.append({
                        'code': codes[i],
                        'name': names[i],
                        'weight': float(weights[i])
                    })
        except Exception as e:
            logger.warning(f"[{self.name}] 解析持仓股票失败: {e}")
        return positions

    def _extract_returns(self, text: str) -> Dict[str, float]:
        returns = {}
        try:
            match = re.search(r'syl_1y[\'"]\s*:\s*([-\d.]+)', text)
            returns['one_month'] = float(match.group(1)) if match else None

            match = re.search(r'syl_3y[\'"]\s*:\s*([-\d.]+)', text)
            returns['three_month'] = float(match.group(1)) if match else None

            match = re.search(r'syl_6y[\'"]\s*:\s*([-\d.]+)', text)
            returns['six_month'] = float(match.group(1)) if match else None

            match = re.search(r'syl_1n[\'"]\s*:\s*([-\d.]+)', text)
            returns['one_year'] = float(match.group(1)) if match else None

            match = re.search(r'syl_3n[\'"]\s*:\s*([-\d.]+)', text)
            returns['three_year'] = float(match.group(1)) if match else None
        except Exception as e:
            logger.warning(f"[{self.name}] 解析收益率失败: {e}")
        return returns

    def _extract_max_drawdown(self, text: str) -> float:
        try:
            match = re.search(r'MaxDrawdown[\'"]\s*:\s*([-\d.]+)', text)
            if match:
                return abs(float(match.group(1)))
        except Exception:
            pass
        return 0.0

    def _format_scale(self, scale: float) -> str:
        """格式化基金规模"""
        if scale <= 0:
            return '--'
        if scale >= 100:
            return f'{scale:.2f}亿'
        return f'{scale:.2f}亿'

    def get_fund_history(self, fund_code: str, period: str = '1y') -> Optional[Dict[str, Any]]:
        """
        获取基金历史净值数据

        Args:
            fund_code: 基金代码
            period: 时间范围 (1m=一月, 3m=三月, 1y=一年, 3y=三年)

        Returns:
            历史净值数据
        """
        # 时间范围映射 - 用于确定获取的数据量
        period_map = {
            '1m': 30,
            '3m': 90,
            '1y': 365,
            '3y': 1095
        }
        days = period_map.get(period, 365)

        # 使用新的 API
        url = "http://api.fund.eastmoney.com/f10/lsjz"
        params = {
            'fundCode': fund_code,
            'pageIndex': '1',
            'pageSize': str(min(days, 365))  # 最多获取365条
        }

        headers = {
            **HEADERS,
            'Referer': 'http://fund.eastmoney.com/'
        }

        text = self._fetch_with_retry(url, params=params, headers=headers)
        if not text:
            return None

        try:
            data = json.loads(text)
            lsjz_list = data.get('Data', {}).get('LSJZList', [])

            if not lsjz_list:
                logger.warning(f"[{self.name}] 基金 {fund_code} 无历史净值数据")
                return None

            # 解析历史净值
            history = []
            for item in lsjz_list:
                try:
                    date_str = item.get('FSRQ', '')  # 日期
                    nav = self._safe_float(item.get('DWJZ'))  # 单位净值
                    change = self._safe_float(item.get('JZZZL'))  # 净值增长率

                    if date_str and nav:
                        history.append({
                            'date': date_str,
                            'nav': nav,
                            'change': change
                        })
                except Exception:
                    continue

            # 按日期正序排列（API返回的是倒序）
            history.reverse()

            return {
                'fund_code': fund_code,
                'period': period,
                'history': history
            }
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 历史数据失败: {e}")
            return None

    def get_fund_holdings(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        获取基金持仓数据

        Args:
            fund_code: 基金代码

        Returns:
            持仓数据
        """
        # 使用 pingzhongdata 接口获取持仓信息
        url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        text = self._fetch_with_retry(url)

        if not text:
            return None

        try:
            holdings = []

            # 解析股票持仓
            stock_codes_match = re.search(r'stockCodes[\'"]\s*:\s*\[([^\]]+)\]', text)
            stock_names_match = re.search(r'stockNames[\'"]\s*:\s*\[([^\]]+)\]', text)
            stock_weights_match = re.search(r'stockWeights[\'"]\s*:\s*\[([^\]]+)\]', text)

            if stock_codes_match and stock_names_match and stock_weights_match:
                codes = re.findall(r'[\'"]([^\'"]+)[\'"]', stock_codes_match.group(1))
                names = re.findall(r'[\'"]([^\'"]+)[\'"]', stock_names_match.group(1))
                weights = re.findall(r'([\d.]+)', stock_weights_match.group(1))

                for i in range(min(len(codes), len(names), len(weights), 10)):
                    holdings.append({
                        'rank': i + 1,
                        'code': codes[i],
                        'name': names[i],
                        'ratio': self._safe_float(weights[i])
                    })

            # 解析资产配置比例
            stock_ratio = 0
            bond_ratio = 0
            cash_ratio = 0

            # 股票占比
            match = re.search(r'fund_stock比例[\'"]?\s*:\s*([\d.]+)', text)
            if match:
                stock_ratio = float(match.group(1))

            # 债券占比
            match = re.search(r'fund_zq比例[\'"]?\s*:\s*([\d.]+)', text)
            if match:
                bond_ratio = float(match.group(1))

            # 现金占比
            match = re.search(r'fund现金比例[\'"]?\s*:\s*([\d.]+)', text)
            if match:
                cash_ratio = float(match.group(1))

            # 如果没有获取到比例，根据持仓估算
            if stock_ratio == 0 and holdings:
                stock_ratio = sum(h.get('ratio', 0) for h in holdings)

            return {
                'fund_code': fund_code,
                'stock_holdings': holdings,
                'asset_allocation': {
                    'stock': stock_ratio,
                    'bond': bond_ratio,
                    'cash': cash_ratio,
                    'other': max(0, 100 - stock_ratio - bond_ratio - cash_ratio)
                }
            }
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 持仓数据失败: {e}")
            return None

    def get_fund_full_detail(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        获取基金完整详情（用于查询弹窗）

        Args:
            fund_code: 基金代码

        Returns:
            基金完整详情
        """
        # 获取实时数据
        realtime = self.get_fund_realtime_data(fund_code)
        if not realtime:
            return None

        # 获取详情数据
        detail = self.get_fund_detail_data(fund_code)

        # 获取基金公司、板块等信息
        url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
        text = self._fetch_with_retry(url)

        company = ''
        board = ''
        establish_date = ''

        if text:
            try:
                # 从其他接口获取更多信息
                info_url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
                info_text = self._fetch_with_retry(info_url)

                if info_text:
                    # 基金公司
                    match = re.search(r'fund_company[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', info_text)
                    if match:
                        company = match.group(1)

                    # 板块/主题
                    match = re.search(r'fund_board[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', info_text)
                    if match:
                        board = match.group(1)

                    # 成立日期
                    match = re.search(r'fund_establish[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', info_text)
                    if match:
                        establish_date = match.group(1)
            except Exception:
                pass

        result = {
            **realtime,
            'manager': detail.get('manager', '') if detail else '',
            'scale': self._format_scale(detail.get('fund_scale', 0)) if detail else '--',
            'returns': detail.get('returns', {}) if detail else {},
            'max_drawdown': detail.get('max_drawdown', 0) if detail else 0,
            'company': company or '--',
            'sector': board or '--',
            'establish_date': establish_date
        }

        return result


class DanjuanFundFetcher(BaseDataFetcher):
    """蛋卷基金数据源"""

    def __init__(self):
        super().__init__("蛋卷基金")
        self.api_base = "https://fund.xueqiu.com/dj/open/fund"

    def get_fund_realtime_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金实时数据"""
        url = f"{self.api_base}/growing/{fund_code}"
        headers = {
            **HEADERS,
            'Referer': 'https://danjuanfunds.com/',
            'Origin': 'https://danjuanfunds.com'
        }

        text = self._fetch_with_retry(url, headers=headers)
        if not text:
            logger.error(f"[{self.name}] 获取基金 {fund_code} 实时数据失败")
            return None

        try:
            data = json.loads(text)
            if data.get('code') != 0:
                return None

            item = data.get('data', {})
            result = {
                'fund_code': fund_code,
                'fund_name': item.get('fd_name', ''),
                'fund_type': item.get('fd_type', ''),
                'nav': self._safe_float(item.get('nav')),
                'nav_date': item.get('nav_date', ''),
                'estimated_nav': self._safe_float(item.get('estimate_nav')),
                'estimated_time': item.get('estimate_date', ''),
                'estimated_change': self._safe_float(item.get('estimate_pct')),
                'yesterday_nav': self._safe_float(item.get('nav')),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': self.name
            }
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 数据失败: {e}")
            return None

    def get_fund_detail_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详细信息 - 蛋卷暂不支持详情"""
        return {
            'fund_code': fund_code,
            'manager': '',
            'manager_date': '',
            'fund_scale': 0.0,
            'stock_positions': [],
            'returns': {},
            'max_drawdown': 0.0
        }


class AlipayFundFetcher(BaseDataFetcher):
    """支付宝基金数据源（蚂蚁财富）"""

    def __init__(self):
        super().__init__("蚂蚁财富")
        self.api_base = "https://fundmobapi.eastmoney.com/FundMNewApi"

    def get_fund_realtime_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金实时数据"""
        url = f"{self.api_base}/FundMNewInfo"
        params = {
            'FCODE': fund_code,
            'deviceid': 'Wap',
            'plat': 'Wap',
            'product': 'EFund',
            'version': '2.0.0'
        }

        text = self._fetch_with_retry(url, params=params)
        if not text:
            logger.error(f"[{self.name}] 获取基金 {fund_code} 实时数据失败")
            return None

        try:
            data = json.loads(text)
            if data.get('ErrCode') != 0:
                return None

            item = data.get('Datas', {})
            result = {
                'fund_code': fund_code,
                'fund_name': item.get('SHORTNAME', ''),
                'fund_type': item.get('FTYPE', ''),
                'nav': self._safe_float(item.get('NAV')),
                'nav_date': item.get('PDATE', ''),
                'estimated_nav': self._safe_float(item.get('GSZ')),
                'estimated_time': item.get('GZTIME', ''),
                'estimated_change': self._safe_float(item.get('GSZZL')),
                'yesterday_nav': self._safe_float(item.get('NAV')),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': self.name
            }
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 数据失败: {e}")
            return None

    def get_fund_detail_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详细信息"""
        url = f"{self.api_base}/FundMNDInfo"
        params = {
            'FCODE': fund_code,
            'deviceid': 'Wap',
            'plat': 'Wap',
            'product': 'EFund',
            'version': '2.0.0'
        }

        text = self._fetch_with_retry(url, params=params)
        if not text:
            return {
                'fund_code': fund_code,
                'manager': '',
                'manager_date': '',
                'fund_scale': 0.0,
                'stock_positions': [],
                'returns': {},
                'max_drawdown': 0.0
            }

        try:
            data = json.loads(text)
            item = data.get('Datas', {})
            return {
                'fund_code': fund_code,
                'manager': item.get('JJJL', ''),
                'manager_date': item.get('FEMPDATE', ''),
                'fund_scale': self._safe_float(item.get('FSCALE')),
                'stock_positions': [],
                'returns': {
                    'one_month': self._safe_float(item.get('SYL_1Y')),
                    'three_month': self._safe_float(item.get('SYL_3Y')),
                    'six_month': self._safe_float(item.get('SYL_6Y')),
                    'one_year': self._safe_float(item.get('SYL_1N')),
                },
                'max_drawdown': self._safe_float(item.get('MAXDRAWDOWN'))
            }
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 详细数据失败: {e}")
            return None


class HowBuyFundFetcher(BaseDataFetcher):
    """且慢数据源"""

    def __init__(self):
        super().__init__("且慢")
        self.api_base = "https://www.howbuy.com/fund/api"

    def get_fund_realtime_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金实时数据"""
        url = f"{self.api_base}/fundtrend/{fund_code}.htm"
        headers = {
            **HEADERS,
            'Referer': f'https://www.howbuy.com/fund/{fund_code}/'
        }

        text = self._fetch_with_retry(url, headers=headers)
        if not text:
            logger.error(f"[{self.name}] 获取基金 {fund_code} 实时数据失败")
            return None

        try:
            # 且慢返回的是JSONP格式
            match = re.search(r'jsonpgz\((.+)\);?', text)
            if match:
                data = json.loads(match.group(1))
            else:
                data = json.loads(text)

            result = {
                'fund_code': fund_code,
                'fund_name': data.get('name', ''),
                'fund_type': '',
                'nav': self._safe_float(data.get('dwjz')),
                'nav_date': data.get('jzrq', ''),
                'estimated_nav': self._safe_float(data.get('gsz')),
                'estimated_time': data.get('gztime', ''),
                'estimated_change': self._safe_float(data.get('gszzl')),
                'yesterday_nav': self._safe_float(data.get('dwjz')),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': self.name
            }
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 解析基金 {fund_code} 数据失败: {e}")
            return None

    def get_fund_detail_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详细信息"""
        return {
            'fund_code': fund_code,
            'manager': '',
            'manager_date': '',
            'fund_scale': 0.0,
            'stock_positions': [],
            'returns': {},
            'max_drawdown': 0.0
        }


# 数据源管理器
class DataSourceManager:
    """数据源管理器 - 支持多数据源切换"""

    SOURCES = {
        'tiantian': {'name': '天天基金', 'class': TiantianFundFetcher},
        'danjuan': {'name': '蛋卷基金', 'class': DanjuanFundFetcher},
        'alipay': {'name': '蚂蚁财富', 'class': AlipayFundFetcher},
        'howbuy': {'name': '且慢', 'class': HowBuyFundFetcher},
    }

    DEFAULT_SOURCE = 'tiantian'

    def __init__(self):
        self._current_source = self.DEFAULT_SOURCE
        self._fetchers = {}

    @property
    def current_source(self) -> str:
        return self._current_source

    @current_source.setter
    def current_source(self, source: str):
        if source in self.SOURCES:
            self._current_source = source
        else:
            raise ValueError(f"不支持的数据源: {source}")

    def get_fetcher(self) -> BaseDataFetcher:
        """获取当前数据源的fetcher实例"""
        # 每次都创建新实例，确保使用最新配置
        fetcher_class = self.SOURCES[self._current_source]['class']
        return fetcher_class()

    def get_available_sources(self) -> List[Dict[str, str]]:
        """获取所有可用的数据源列表"""
        return [
            {'id': key, 'name': info['name']}
            for key, info in self.SOURCES.items()
        ]

    def get_source_name(self, source_id: str = None) -> str:
        """获取数据源名称"""
        sid = source_id or self._current_source
        return self.SOURCES.get(sid, {}).get('name', '未知')

    def get_fund_history(self, fund_code: str, period: str = '1y') -> Optional[Dict[str, Any]]:
        """获取基金历史净值数据"""
        fetcher = self.get_fetcher()
        if hasattr(fetcher, 'get_fund_history'):
            data = fetcher.get_fund_history(fund_code, period)
            if data:
                # 转换为前端需要的格式
                history = data.get('history', [])
                return {
                    'fund_code': fund_code,
                    'period': period,
                    'dates': [h.get('date', '') for h in history],
                    'navs': [h.get('nav', 0) for h in history],
                    'changes': [h.get('change', 0) for h in history]
                }
        return None

    def get_fund_holdings(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金持仓数据"""
        fetcher = self.get_fetcher()
        if hasattr(fetcher, 'get_fund_holdings'):
            data = fetcher.get_fund_holdings(fund_code)
            if data:
                # 构建资产配置列表
                asset_allocation = data.get('asset_allocation', {})
                allocation_list = []
                if asset_allocation.get('stock', 0) > 0:
                    allocation_list.append({'name': '股票', 'ratio': asset_allocation['stock']})
                if asset_allocation.get('bond', 0) > 0:
                    allocation_list.append({'name': '债券', 'ratio': asset_allocation['bond']})
                if asset_allocation.get('cash', 0) > 0:
                    allocation_list.append({'name': '现金', 'ratio': asset_allocation['cash']})
                if asset_allocation.get('other', 0) > 0:
                    allocation_list.append({'name': '其他', 'ratio': asset_allocation['other']})

                return {
                    'fund_code': fund_code,
                    'stock_positions': data.get('stock_holdings', []),
                    'asset_allocation': allocation_list
                }
        return None

    def get_fund_full_detail(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金完整详情"""
        fetcher = self.get_fetcher()
        if hasattr(fetcher, 'get_fund_full_detail'):
            return fetcher.get_fund_full_detail(fund_code)

        # 如果数据源不支持，使用基本方法组装
        realtime = self.get_fetcher().get_fund_realtime_data(fund_code)
        if not realtime:
            return None

        detail = self.get_fetcher().get_fund_detail_data(fund_code)

        return {
            **realtime,
            'manager': detail.get('manager', '') if detail else '',
            'scale': self._format_scale(detail.get('fund_scale', 0)) if detail else '--',
            'sector': '--',
            'company': '--',
            'returns': detail.get('returns', {}) if detail else {}
        }

    def _format_scale(self, scale: float) -> str:
        """格式化基金规模"""
        if scale <= 0:
            return '--'
        if scale >= 100:
            return f'{scale:.2f}亿'
        return f'{scale:.2f}亿'


# 创建全局管理器实例
data_source_manager = DataSourceManager()


# 兼容旧代码的便捷函数
def get_fund_data(fund_code: str) -> Optional[Dict[str, Any]]:
    """获取基金完整数据的便捷函数"""
    fetcher = data_source_manager.get_fetcher()

    realtime_data = fetcher.get_fund_realtime_data(fund_code)
    detail_data = fetcher.get_fund_detail_data(fund_code)

    result = {
        'fund_code': fund_code,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_source': data_source_manager.get_source_name()
    }

    if realtime_data:
        result.update(realtime_data)

    if detail_data:
        result.update(detail_data)

    return result


def get_fund_realtime(fund_code: str) -> Optional[Dict[str, Any]]:
    """获取基金实时数据的便捷函数"""
    fetcher = data_source_manager.get_fetcher()
    return fetcher.get_fund_realtime_data(fund_code)


if __name__ == '__main__':
    # 测试代码
    test_code = '000001'

    print("可用数据源:")
    for source in data_source_manager.get_available_sources():
        print(f"  - {source['id']}: {source['name']}")

    print(f"\n当前数据源: {data_source_manager.get_source_name()}")
    print(f"\n正在获取基金 {test_code} 的数据...")

    data = get_fund_data(test_code)
    if data:
        print("\n基金数据:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("获取数据失败")
