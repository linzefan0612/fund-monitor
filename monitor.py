# -*- coding: utf-8 -*-
"""
基金实时监控助手 - 监控和提醒模块
负责监控基金数据变化并触发提醒
"""

import json
import logging
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum

from config import (
    PRICE_CHANGE_THRESHOLD,
    ESTIMATE_DEVIATION_THRESHOLD,
    STOCK_CHANGE_THRESHOLD,
    MAX_DRAWDOWN_THRESHOLD,
    DATA_FILE,
    HISTORY_KEEP_DAYS,
    RISK_LEVELS
)
from fund_data import data_source_manager, get_fund_data, get_fund_realtime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AlertType(Enum):
    """提醒类型枚举"""
    PRICE_CHANGE = "涨跌幅提醒"
    ESTIMATE_DEVIATION = "估值偏差提醒"
    STOCK_CHANGE = "持仓股票异动"
    MAX_DRAWDOWN = "最大回撤提醒"
    MANAGER_CHANGE = "基金经理变更"
    SCALE_CHANGE = "规模暴增"


@dataclass
class Alert:
    """提醒数据类"""
    fund_code: str
    fund_name: str
    alert_type: AlertType
    message: str
    value: float
    threshold: float
    time: str
    date: str  # 新增日期字段，用于过滤当天提醒
    level: str = "warning"  # warning, danger, info

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'fund_code': self.fund_code,
            'fund_name': self.fund_name,
            'alert_type': self.alert_type.value,
            'message': self.message,
            'value': self.value,
            'threshold': self.threshold,
            'time': self.time,
            'date': self.date,
            'level': self.level
        }


@dataclass
class FundPosition:
    """基金持仓配置"""
    fund_code: str
    fund_name: str = ""
    current_amount: float = 0.0  # 当前持仓金额
    max_amount: float = 0.0  # 持仓上限金额
    holding_return_rate: float = 0.0  # 当前持有收益率（%）
    last_return_update_date: str = ""  # 上次更新持有收益率的日期
    last_amount_update_date: str = ""  # 上次更新持仓金额的日期

    def to_dict(self) -> dict:
        return asdict(self)


class FundMonitor:
    """基金监控器"""

    def __init__(self):
        """初始化监控器"""
        self.funds: Dict[str, Dict[str, Any]] = {}  # 基金数据缓存
        self.positions: Dict[str, FundPosition] = {}  # 持仓配置
        self.alerts: List[Alert] = []  # 提醒列表
        self.history: Dict[str, List[Dict]] = {}  # 历史数据
        self.alert_callbacks: List[Callable[[Alert], None]] = []  # 提醒回调函数
        self.last_alert_clear_date: str = ""  # 上次清除提醒的日期

        # 加载存储的数据
        self._load_data()

        # 检查是否需要清除过期的提醒
        self._check_and_clear_old_alerts()

    def _load_data(self):
        """从文件加载数据"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 加载持仓配置
                    for code, pos_data in data.get('positions', {}).items():
                        self.positions[code] = FundPosition(
                            fund_code=code,
                            fund_name=pos_data.get('fund_name', ''),
                            current_amount=pos_data.get('current_amount', 0),
                            max_amount=pos_data.get('max_amount', 0),
                            holding_return_rate=pos_data.get('holding_return_rate', 0),
                            last_return_update_date=pos_data.get('last_return_update_date', ''),
                            last_amount_update_date=pos_data.get('last_amount_update_date', '')
                        )
                    # 加载历史数据
                    self.history = data.get('history', {})
                    # 加载上次清除日期
                    self.last_alert_clear_date = data.get('last_alert_clear_date', '')
                logger.info(f"已加载数据文件: {DATA_FILE}")
            except Exception as e:
                logger.error(f"加载数据文件失败: {e}")

    def _save_data(self):
        """保存数据到文件"""
        try:
            data = {
                'positions': {code: pos.to_dict() for code, pos in self.positions.items()},
                'history': self._clean_history(),
                'last_alert_clear_date': self.last_alert_clear_date
            }
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"数据已保存到: {DATA_FILE}")
        except Exception as e:
            logger.error(f"保存数据文件失败: {e}")

    def _clean_history(self) -> dict:
        """清理过期历史数据"""
        cutoff_date = datetime.now() - timedelta(days=HISTORY_KEEP_DAYS)
        cleaned = {}
        for code, records in self.history.items():
            cleaned[code] = [
                r for r in records
                if datetime.strptime(r.get('time', '1970-01-01'), '%Y-%m-%d %H:%M:%S') > cutoff_date
            ]
        return cleaned

    def _check_and_clear_old_alerts(self):
        """检查并清除过期的提醒（非当天的提醒）"""
        today = date.today().isoformat()

        # 如果是新的一天，清除所有旧提醒
        if self.last_alert_clear_date != today:
            # 检查当前时间是否在交易时段开始前（9:05之前）
            now = datetime.now()
            current_time = now.hour * 100 + now.minute

            if current_time < 905:
                # 交易日开始前，清除所有提醒
                old_count = len(self.alerts)
                self.alerts = []
                self.last_alert_clear_date = today
                self._save_data()
                logger.info(f"新交易日开始，已清除 {old_count} 条历史提醒")
            else:
                # 交易时段内，只保留当天的提醒
                today_alerts = [a for a in self.alerts if a.date == today]
                old_count = len(self.alerts) - len(today_alerts)
                if old_count > 0:
                    self.alerts = today_alerts
                    logger.info(f"已清除 {old_count} 条非当日提醒")
                self.last_alert_clear_date = today
                self._save_data()

    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """添加提醒回调函数"""
        self.alert_callbacks.append(callback)

    def _trigger_alert(self, alert: Alert):
        """触发提醒"""
        self.alerts.insert(0, alert)  # 从头部添加，最新提醒显示在最前面
        logger.warning(f"[{alert.alert_type.value}] {alert.fund_name}({alert.fund_code}): {alert.message}")
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"提醒回调执行失败: {e}")

    def add_fund(self, fund_code: str, current_amount: float = 0, max_amount: float = 0, holding_return_rate: float = 0) -> bool:
        """
        添加监控基金

        Args:
            fund_code: 基金代码
            current_amount: 当前持仓金额
            max_amount: 持仓上限金额
            holding_return_rate: 持有收益率

        Returns:
            是否添加成功
        """
        # 获取基金数据验证代码有效性
        data = get_fund_realtime(fund_code)
        if not data:
            logger.error(f"添加基金失败: 无效的基金代码 {fund_code}")
            return False

        # 添加持仓配置
        self.positions[fund_code] = FundPosition(
            fund_code=fund_code,
            fund_name=data.get('fund_name', ''),
            current_amount=current_amount,
            max_amount=max_amount,
            holding_return_rate=holding_return_rate,
            last_return_update_date=''
        )

        # 初始化历史数据
        if fund_code not in self.history:
            self.history[fund_code] = []

        # 保存数据
        self._save_data()

        logger.info(f"已添加基金: {data.get('fund_name')}({fund_code})")
        return True

    def remove_fund(self, fund_code: str) -> bool:
        """
        移除监控基金

        Args:
            fund_code: 基金代码

        Returns:
            是否移除成功
        """
        if fund_code in self.positions:
            del self.positions[fund_code]
            self._save_data()
            logger.info(f"已移除基金: {fund_code}")
            return True
        return False

    def clear_all_funds(self):
        """
        清除所有监控基金

        Returns:
            清除的基金数量
        """
        count = len(self.positions)
        self.positions.clear()
        self.funds.clear()
        self.alerts.clear()
        self.history.clear()
        self._save_data()
        logger.info(f"已清除所有基金，共 {count} 只")
        return count

    def update_position(self, fund_code: str, current_amount: float = None, max_amount: float = None) -> bool:
        """
        更新持仓配置

        Args:
            fund_code: 基金代码
            current_amount: 当前持仓金额
            max_amount: 持仓上限金额

        Returns:
            是否更新成功
        """
        if fund_code not in self.positions:
            return False

        if current_amount is not None:
            self.positions[fund_code].current_amount = current_amount
        if max_amount is not None:
            self.positions[fund_code].max_amount = max_amount

        self._save_data()
        return True

    def update_holding_return_rate(self, fund_code: str, return_rate: float) -> bool:
        """
        更新持有收益率

        Args:
            fund_code: 基金代码
            return_rate: 持有收益率（%）

        Returns:
            是否更新成功
        """
        if fund_code not in self.positions:
            return False

        self.positions[fund_code].holding_return_rate = return_rate
        self._save_data()
        return True

    def _get_previous_trading_day_return(self, fund_code: str) -> Optional[float]:
        """
        获取上一个交易日的涨跌幅

        Args:
            fund_code: 基金代码

        Returns:
            上一个交易日的涨跌幅（%），如果无法获取则返回None
        """
        data = self.funds.get(fund_code)
        if not data:
            return None

        # 从历史记录中获取最近的涨跌幅
        # 如果nav_date是上一个交易日，则estimated_change可能是今天的估算
        # 我们需要从基金详情获取上一个交易日的实际涨跌幅
        from fund_data import data_source_manager

        try:
            # 获取基金详情数据
            fetcher = data_source_manager.get_fetcher()
            detail = fetcher.get_fund_detail_data(fund_code)

            if detail:
                returns = detail.get('returns', {})
                # 返回近一月的收益率变化作为上一个交易日的涨幅（近似）
                # 实际应该从历史净值数据中计算
                # 这里我们使用另一种方法：从历史数据中获取

            # 从历史净值数据获取上一个交易日的涨跌幅
            history = data_source_manager.get_fund_history(fund_code, '1m')
            if history and history.get('history'):
                # 历史数据第一条是最近的
                hist_list = history.get('history', [])
                if len(hist_list) >= 2:
                    # 获取上一个交易日的涨跌幅
                    prev_change = hist_list[-2].get('change', 0)  # 倒数第二条是上一个交易日
                    return prev_change
                elif len(hist_list) >= 1:
                    # 只有一条记录，使用第一条
                    return hist_list[-1].get('change', 0)
        except Exception as e:
            logger.error(f"获取上一交易日涨跌幅失败: {e}")

        return None

    def _should_update_holding_return(self, fund_code: str) -> bool:
        """
        判断是否应该更新持有收益率

        更新条件：
        1. 今天是交易日
        2. 今天还没有更新过
        3. 已经获取到上一个交易日的涨跌幅

        Args:
            fund_code: 基金代码

        Returns:
            是否应该更新
        """
        position = self.positions.get(fund_code)
        if not position:
            return False

        # 判断是否是交易日
        if not self._is_trading_day():
            return False

        today = date.today().isoformat()

        # 如果今天已经更新过，不再更新
        if position.last_return_update_date == today:
            return False

        # 检查是否获取到上一个交易日的净值数据
        # 通过比较nav_date和今天日期来判断
        data = self.funds.get(fund_code)
        if not data:
            return False

        nav_date = data.get('nav_date', '')
        if not nav_date:
            return False

        # 将nav_date转换为日期格式
        try:
            # nav_date格式可能是 "2024-04-19" 或 "2024-04-19 00:00:00"
            nav_date_str = nav_date.split(' ')[0] if ' ' in nav_date else nav_date
            nav_date_obj = datetime.strptime(nav_date_str, '%Y-%m-%d').date()
            today_obj = date.today()

            # 如果净值日期是今天之前（即上一个交易日），说明净值已更新
            if nav_date_obj < today_obj:
                return True

        except Exception as e:
            logger.warning(f"解析净值日期失败: {e}")

        return False

    def _update_holding_return_rate(self, fund_code: str):
        """
        更新持有收益率（内部方法）

        根据上一个交易日的涨跌幅更新持有收益率

        Args:
            fund_code: 基金代码
        """
        position = self.positions.get(fund_code)
        if not position:
            return

        # 获取上一个交易日的涨跌幅
        prev_day_return = self._get_previous_trading_day_return(fund_code)

        if prev_day_return is None:
            # 如果无法获取历史数据，尝试使用估算涨跌幅（仅作为备选）
            data = self.funds.get(fund_code)
            if data:
                # 使用estimated_change作为上日涨跌幅的近似值
                # 但这仅在净值已更新的情况下才准确
                nav_date = data.get('nav_date', '')
                today = date.today().isoformat()
                if nav_date and nav_date.split(' ')[0] < today:
                    prev_day_return = data.get('estimated_change', 0)
                else:
                    logger.info(f"基金 {fund_code} 净值尚未更新，暂不更新持有收益率")
                    return
            else:
                return

        # 更新持有收益率
        # 公式: 新持有收益率 = 旧持有收益率 + 上日涨跌幅
        old_return = position.holding_return_rate or 0
        new_return = old_return + prev_day_return

        # 更新数据
        position.holding_return_rate = new_return
        position.last_return_update_date = date.today().isoformat()

        logger.info(f"基金 {fund_code} 持有收益率已更新: {old_return:.2f}% -> {new_return:.2f}% "
                   f"(上日涨跌: {prev_day_return:.2f}%)")

        self._save_data()

    def _is_trading_day(self) -> bool:
        """
        判断今天是否是交易日

        Returns:
            是否是交易日
        """
        today = date.today()
        weekday = today.weekday()  # 0=周一, 6=周日

        # 周末不是交易日
        if weekday >= 5:  # 5=周六, 6=周日
            return False

        # TODO: 可以添加节假日判断
        # 节假日列表可以从外部文件加载或使用API获取

        return True

    def _should_update_position_amount(self, fund_code: str) -> bool:
        """
        判断是否应该更新持仓金额

        更新条件：
        1. 今天是交易日
        2. 今天还没有更新过
        3. 在交易时间段内
        4. 已经获取到上一个交易日的净值数据
        5. 有持仓金额（大于0）

        Args:
            fund_code: 基金代码

        Returns:
            是否应该更新
        """
        position = self.positions.get(fund_code)
        if not position:
            return False

        # 没有持仓金额则不需要更新
        if position.current_amount <= 0:
            return False

        # 判断是否是交易日
        if not self._is_trading_day():
            return False

        today = date.today().isoformat()

        # 如果今天已经更新过，不再更新
        if position.last_amount_update_date == today:
            return False

        # 检查是否在交易时间段内（9:05 - 15:00）
        now = datetime.now()
        current_time = now.hour * 100 + now.minute
        if current_time < 905 or current_time > 1500:
            return False

        # 检查是否获取到上一个交易日的净值数据
        data = self.funds.get(fund_code)
        if not data:
            return False

        nav_date = data.get('nav_date', '')
        if not nav_date:
            return False

        # 将nav_date转换为日期格式
        try:
            nav_date_str = nav_date.split(' ')[0] if ' ' in nav_date else nav_date
            nav_date_obj = datetime.strptime(nav_date_str, '%Y-%m-%d').date()
            today_obj = date.today()

            # 如果净值日期是今天之前（即上一个交易日），说明净值已更新
            if nav_date_obj < today_obj:
                return True

        except Exception as e:
            logger.warning(f"解析净值日期失败: {e}")

        return False

    def _update_position_amount(self, fund_code: str):
        """
        更新持仓金额（内部方法）

        根据上一个交易日的涨跌幅更新持仓金额
        公式: 新持仓金额 = 旧持仓金额 * (1 + 上日涨跌幅/100)

        Args:
            fund_code: 基金代码
        """
        position = self.positions.get(fund_code)
        if not position or position.current_amount <= 0:
            return

        # 获取上一个交易日的涨跌幅
        prev_day_return = self._get_previous_trading_day_return(fund_code)

        if prev_day_return is None:
            # 如果无法获取历史数据，尝试使用估算涨跌幅（仅作为备选）
            data = self.funds.get(fund_code)
            if data:
                nav_date = data.get('nav_date', '')
                today = date.today().isoformat()
                if nav_date and nav_date.split(' ')[0] < today:
                    prev_day_return = data.get('estimated_change', 0)
                else:
                    logger.info(f"基金 {fund_code} 净值尚未更新，暂不更新持仓金额")
                    return
            else:
                return

        # 更新持仓金额
        # 公式: 新持仓金额 = 旧持仓金额 * (1 + 上日涨跌幅/100)
        old_amount = position.current_amount
        new_amount = old_amount * (1 + prev_day_return / 100)

        # 更新数据
        position.current_amount = new_amount
        position.last_amount_update_date = date.today().isoformat()

        logger.info(f"基金 {fund_code} 持仓金额已更新: ¥{old_amount:.2f} -> ¥{new_amount:.2f} "
                   f"(上日涨跌: {prev_day_return:.2f}%)")

        self._save_data()

    def get_monitored_funds(self) -> List[str]:
        """获取所有监控的基金代码列表"""
        return list(self.positions.keys())

    def refresh_data(self) -> Dict[str, Dict[str, Any]]:
        """
        刷新所有基金数据

        Returns:
            基金数据字典
        """
        # 先检查是否需要清除旧提醒
        self._check_and_clear_old_alerts()

        results = {}
        today = date.today().isoformat()

        for fund_code in self.positions.keys():
            data = get_fund_data(fund_code)
            if data:
                self.funds[fund_code] = data
                results[fund_code] = data

                # 保存到历史记录
                history_record = {
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'nav': data.get('nav'),
                    'estimated_nav': data.get('estimated_nav'),
                    'estimated_change': data.get('estimated_change')
                }
                if fund_code not in self.history:
                    self.history[fund_code] = []
                self.history[fund_code].append(history_record)

                # 执行监控检查
                self._check_alerts(fund_code, data, today)

                # 检查并更新持有收益率（每天只更新一次）
                if self._should_update_holding_return(fund_code):
                    self._update_holding_return_rate(fund_code)

                # 检查并更新持仓金额（交易时间内，每天只更新一次）
                if self._should_update_position_amount(fund_code):
                    self._update_position_amount(fund_code)

        # 保存数据
        self._save_data()

        return results

    def _check_alerts(self, fund_code: str, data: Dict[str, Any], alert_date: str):
        """
        检查是否需要触发提醒

        Args:
            fund_code: 基金代码
            data: 基金数据
            alert_date: 提醒日期
        """
        fund_name = data.get('fund_name', fund_code)
        now = datetime.now()

        # 1. 检查涨跌幅提醒
        estimated_change = data.get('estimated_change', 0)
        if abs(estimated_change) >= PRICE_CHANGE_THRESHOLD:
            level = "danger" if abs(estimated_change) >= 3 else "warning"
            direction = "上涨" if estimated_change > 0 else "下跌"
            self._trigger_alert(Alert(
                fund_code=fund_code,
                fund_name=fund_name,
                alert_type=AlertType.PRICE_CHANGE,
                message=f"估算{direction} {abs(estimated_change):.2f}%，超过阈值 {PRICE_CHANGE_THRESHOLD}%",
                value=estimated_change,
                threshold=PRICE_CHANGE_THRESHOLD,
                time=now.strftime('%Y-%m-%d %H:%M:%S'),
                date=alert_date,
                level=level
            ))

        # 2. 检查估值偏差提醒
        nav = data.get('nav', 0)
        estimated_nav = data.get('estimated_nav', 0)
        if nav and estimated_nav:
            deviation = abs((estimated_nav - nav) / nav * 100)
            if deviation >= ESTIMATE_DEVIATION_THRESHOLD:
                self._trigger_alert(Alert(
                    fund_code=fund_code,
                    fund_name=fund_name,
                    alert_type=AlertType.ESTIMATE_DEVIATION,
                    message=f"估算净值与实际净值偏差 {deviation:.2f}%，超过阈值 {ESTIMATE_DEVIATION_THRESHOLD}%",
                    value=deviation,
                    threshold=ESTIMATE_DEVIATION_THRESHOLD,
                    time=now.strftime('%Y-%m-%d %H:%M:%S'),
                    date=alert_date,
                    level="warning"
                ))

        # 3. 检查持仓股票异动
        stock_positions = data.get('stock_positions', [])
        for stock in stock_positions:
            stock_change = stock.get('change_percent', 0)
            if abs(stock_change) > STOCK_CHANGE_THRESHOLD:
                direction = "上涨" if stock_change > 0 else "下跌"
                self._trigger_alert(Alert(
                    fund_code=fund_code,
                    fund_name=fund_name,
                    alert_type=AlertType.STOCK_CHANGE,
                    message=f"重仓股 {stock.get('name', '')} {direction} {abs(stock_change):.2f}%",
                    value=stock_change,
                    threshold=STOCK_CHANGE_THRESHOLD,
                    time=now.strftime('%Y-%m-%d %H:%M:%S'),
                    date=alert_date,
                    level="warning"
                ))

        # 4. 检查最大回撤提醒
        max_drawdown = data.get('max_drawdown', 0)
        if max_drawdown >= MAX_DRAWDOWN_THRESHOLD:
            self._trigger_alert(Alert(
                fund_code=fund_code,
                fund_name=fund_name,
                alert_type=AlertType.MAX_DRAWDOWN,
                message=f"最大回撤 {max_drawdown:.2f}%，超过风险阈值 {MAX_DRAWDOWN_THRESHOLD}%",
                value=max_drawdown,
                threshold=MAX_DRAWDOWN_THRESHOLD,
                time=now.strftime('%Y-%m-%d %H:%M:%S'),
                date=alert_date,
                level="danger"
            ))

    def get_risk_level(self, fund_code: str) -> Dict[str, Any]:
        """
        获取基金风险等级

        Args:
            fund_code: 基金代码

        Returns:
            风险等级信息
        """
        data = self.funds.get(fund_code, {})
        max_drawdown = data.get('max_drawdown', 0)

        for level_name, level_info in RISK_LEVELS.items():
            if max_drawdown <= level_info['max_drawdown']:
                return {
                    'level': level_name,
                    'label': level_info['label'],
                    'color': level_info['color'],
                    'max_drawdown': max_drawdown
                }

        return {
            'level': 'high',
            'label': '高风险',
            'color': 'red',
            'max_drawdown': max_drawdown
        }

    def get_fund_data(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取单个基金数据"""
        if fund_code in self.funds:
            return self.funds[fund_code]

        # 如果缓存中没有，尝试获取
        data = get_fund_data(fund_code)
        if data:
            self.funds[fund_code] = data
        return data

    def get_all_funds_data(self) -> Dict[str, Dict[str, Any]]:
        """获取所有基金数据"""
        result = {}
        for code, data in self.funds.items():
            fund_data = data.copy()
            # 添加持仓信息和持有收益率
            position = self.positions.get(code)
            if position:
                fund_data['current_amount'] = position.current_amount
                fund_data['max_amount'] = position.max_amount
                fund_data['holding_return_rate'] = position.holding_return_rate
                fund_data['last_return_update_date'] = position.last_return_update_date
            result[code] = fund_data
        return result

    def get_alerts(self, fund_code: str = None, today_only: bool = True) -> List[Dict]:
        """
        获取提醒列表

        Args:
            fund_code: 基金代码（可选，不传则返回所有）
            today_only: 是否只返回当天的提醒

        Returns:
            提醒列表
        """
        today = date.today().isoformat()
        alerts = self.alerts

        if today_only:
            alerts = [a for a in alerts if a.date == today]

        if fund_code:
            return [a.to_dict() for a in alerts if a.fund_code == fund_code]
        return [a.to_dict() for a in alerts]

    def clear_alerts(self):
        """清除所有提醒"""
        self.alerts = []
        self._save_data()

    def get_position(self, fund_code: str) -> Optional[FundPosition]:
        """获取基金持仓配置"""
        return self.positions.get(fund_code)

    def get_all_positions(self) -> Dict[str, FundPosition]:
        """获取所有持仓配置"""
        return self.positions


# 创建全局监控器实例
monitor = FundMonitor()


if __name__ == '__main__':
    # 测试代码
    print("测试基金监控器...")

    # 添加测试基金
    monitor.add_fund('000001', current_amount=10000, max_amount=50000)

    # 刷新数据
    print("\n刷新数据...")
    data = monitor.refresh_data()

    # 显示结果
    for code, fund_data in data.items():
        print(f"\n基金: {fund_data.get('fund_name')}({code})")
        print(f"  最新净值: {fund_data.get('nav')}")
        print(f"  估算净值: {fund_data.get('estimated_nav')}")
        print(f"  估算涨跌: {fund_data.get('estimated_change')}%")

    # 显示提醒
    print("\n提醒:")
    for alert in monitor.get_alerts():
        print(f"  [{alert['alert_type']}] {alert['message']}")
