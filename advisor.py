# -*- coding: utf-8 -*-
"""
基金实时监控助手 - 智能建议模块
根据基金数据和市场情况生成买卖建议
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass

from config import (
    VALUATION_LOW_THRESHOLD,
    VALUATION_HIGH_THRESHOLD,
    CONTINUOUS_UP_DAYS,
    BIG_DROP_THRESHOLD,
    BIG_RISE_THRESHOLD,
    BATCH_BUY_THRESHOLD,
    TAKE_PROFIT_THRESHOLD,
    AFTERNOON_REMINDER_TIME,
    HIGH_HOLDING_RETURN_THRESHOLD,
    LOSS_WARNING_THRESHOLD
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AdviceType(Enum):
    """建议类型枚举"""
    ADD_POSITION = "建议加仓"
    REDUCE_POSITION = "建议减仓"
    HOLD = "建议持有观望"
    BATCH_BUY = "建议分批低吸"
    TAKE_PROFIT = "建议止盈部分仓位"
    CAUTIOUS = "建议谨慎观望"
    NO_CHANGE = "暂无操作建议"


@dataclass
class FundAdvice:
    """基金建议数据类"""
    fund_code: str
    fund_name: str
    advice_type: AdviceType
    reason: str
    confidence: float  # 建议置信度 0-1
    estimated_change: float
    suggested_amount: float = 0.0  # 建议操作金额
    current_amount: float = 0.0  # 当前持仓
    max_amount: float = 0.0  # 持仓上限
    holding_return_rate: float = 0.0  # 持有收益率
    time: str = ""

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'fund_code': self.fund_code,
            'fund_name': self.fund_name,
            'advice_type': self.advice_type.value,
            'reason': self.reason,
            'confidence': self.confidence,
            'estimated_change': self.estimated_change,
            'suggested_amount': self.suggested_amount,
            'current_amount': self.current_amount,
            'max_amount': self.max_amount,
            'holding_return_rate': self.holding_return_rate,
            'time': self.time
        }


class FundAdvisor:
    """基金智能建议生成器"""

    def __init__(self, monitor):
        """
        初始化建议生成器

        Args:
            monitor: FundMonitor实例
        """
        self.monitor = monitor
        self.history_analysis = {}  # 历史趋势分析缓存

    def analyze_trend(self, fund_code: str) -> Dict[str, Any]:
        """
        分析基金趋势

        Args:
            fund_code: 基金代码

        Returns:
            趋势分析结果
        """
        history = self.monitor.history.get(fund_code, [])
        if len(history) < 2:
            return {
                'trend': 'unknown',
                'continuous_up': 0,
                'continuous_down': 0,
                'volatility': 0
            }

        # 计算连续涨跌天数
        changes = [h.get('estimated_change') if h.get('estimated_change') is not None else 0 for h in history[-10:]]
        continuous_up = 0
        continuous_down = 0

        for change in reversed(changes):
            if change > 0:
                if continuous_down == 0:
                    continuous_up += 1
                else:
                    break
            elif change < 0:
                if continuous_up == 0:
                    continuous_down += 1
                else:
                    break
            else:
                break

        # 计算波动率
        if len(changes) >= 5:
            avg_change = sum(changes) / len(changes)
            volatility = sum((c - avg_change) ** 2 for c in changes) / len(changes) ** 0.5
        else:
            volatility = 0

        # 判断趋势
        if continuous_up >= 3:
            trend = 'up'
        elif continuous_down >= 3:
            trend = 'down'
        elif volatility > 2:
            trend = 'volatile'
        else:
            trend = 'stable'

        return {
            'trend': trend,
            'continuous_up': continuous_up,
            'continuous_down': continuous_down,
            'volatility': volatility
        }

    def generate_advice(self, fund_code: str) -> Optional[FundAdvice]:
        """
        生成单个基金的操作建议

        Args:
            fund_code: 基金代码

        Returns:
            基金建议
        """
        # 获取基金数据
        data = self.monitor.get_fund_data(fund_code)
        if not data:
            return None

        # 获取持仓配置
        position = self.monitor.get_position(fund_code)
        current_amount = position.current_amount if position else 0
        max_amount = position.max_amount if position else 0
        holding_return_rate = position.holding_return_rate if position else 0

        fund_name = data.get('fund_name', fund_code)
        estimated_change = data.get('estimated_change')
        if estimated_change is None:
            estimated_change = 0
        returns = data.get('returns', {}) or {}
        max_drawdown = data.get('max_drawdown')
        if max_drawdown is None:
            max_drawdown = 0

        # 分析趋势
        trend_analysis = self.analyze_trend(fund_code)

        # 生成建议
        advice_type, reason, confidence = self._evaluate_advice(
            estimated_change=estimated_change,
            returns=returns,
            max_drawdown=max_drawdown,
            trend_analysis=trend_analysis,
            current_amount=current_amount,
            max_amount=max_amount,
            holding_return_rate=holding_return_rate
        )

        # 计算建议操作金额
        suggested_amount = self._calculate_suggested_amount(
            advice_type=advice_type,
            estimated_change=estimated_change,
            current_amount=current_amount,
            max_amount=max_amount,
            holding_return_rate=holding_return_rate
        )

        return FundAdvice(
            fund_code=fund_code,
            fund_name=fund_name,
            advice_type=advice_type,
            reason=reason,
            confidence=confidence,
            estimated_change=estimated_change,
            suggested_amount=suggested_amount,
            current_amount=current_amount,
            max_amount=max_amount,
            holding_return_rate=holding_return_rate,
            time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def _evaluate_advice(
        self,
        estimated_change: float,
        returns: Dict[str, float],
        max_drawdown: float,
        trend_analysis: Dict[str, Any],
        current_amount: float,
        max_amount: float,
        holding_return_rate: float = 0
    ) -> tuple:
        """
        评估并生成建议

        Returns:
            (建议类型, 原因, 置信度)
        """
        one_year_return = returns.get('one_year', 0) if returns else 0
        # 确保返回值不为None
        if one_year_return is None:
            one_year_return = 0
        trend = trend_analysis.get('trend', 'unknown')
        continuous_up = trend_analysis.get('continuous_up', 0)

        # 确保 max_drawdown 不为 None
        if max_drawdown is None:
            max_drawdown = 0

        # 确保持有收益率不为None
        if holding_return_rate is None:
            holding_return_rate = 0

        # 1. 单日大跌 >= 3% → 建议分批低吸
        if estimated_change <= BATCH_BUY_THRESHOLD:
            # 如果持有收益为正，分批低吸更安全
            if holding_return_rate > 0:
                return (
                    AdviceType.BATCH_BUY,
                    f"今日估算下跌 {abs(estimated_change):.2f}%，持有收益率 {holding_return_rate:.2f}% 为正，适合分批低吸降低成本",
                    0.85
                )
            return (
                AdviceType.BATCH_BUY,
                f"今日估算下跌 {abs(estimated_change):.2f}%，超过 {abs(BATCH_BUY_THRESHOLD)}% 阈值，适合分批低吸",
                0.8
            )

        # 2. 单日大涨 >= 4% → 建议止盈部分仓位
        if estimated_change >= TAKE_PROFIT_THRESHOLD:
            # 如果持有收益较高，止盈更有意义
            if holding_return_rate > 10:
                return (
                    AdviceType.TAKE_PROFIT,
                    f"今日估算上涨 {estimated_change:.2f}%，持有收益率已达 {holding_return_rate:.2f}%，强烈建议止盈锁定收益",
                    0.9
                )
            elif holding_return_rate > 0:
                return (
                    AdviceType.TAKE_PROFIT,
                    f"今日估算上涨 {estimated_change:.2f}%，持有收益率 {holding_return_rate:.2f}%，建议止盈部分仓位",
                    0.85
                )
            return (
                AdviceType.TAKE_PROFIT,
                f"今日估算上涨 {estimated_change:.2f}%，超过 {TAKE_PROFIT_THRESHOLD}% 阈值，建议止盈部分仓位",
                0.8
            )

        # 3. 持有收益亏损较多 + 估值低位 + 趋势向上 → 建议加仓摊薄成本
        if (holding_return_rate < -10 and
            one_year_return <= VALUATION_LOW_THRESHOLD and
            trend in ['up', 'stable']):
            return (
                AdviceType.ADD_POSITION,
                f"持有收益率 {holding_return_rate:.2f}% 亏损较大，基金处于估值低位且趋势{'向上' if trend == 'up' else '稳定'}，建议加仓摊薄成本",
                0.8
            )

        # 4. 估值低位 + 趋势向上 + 回撤较小 → 建议加仓
        if (one_year_return <= VALUATION_LOW_THRESHOLD and
            trend in ['up', 'stable'] and
            max_drawdown < 10):
            return (
                AdviceType.ADD_POSITION,
                f"近1年收益率 {one_year_return:.2f}% 处于低位，趋势{'向上' if trend == 'up' else '稳定'}，回撤较小，适合加仓",
                0.75
            )

        # 5. 持有收益较高 + 估值高位 + 连续上涨 → 建议减仓锁定收益
        if (holding_return_rate > 15 and
            one_year_return >= VALUATION_HIGH_THRESHOLD and
            continuous_up >= CONTINUOUS_UP_DAYS):
            return (
                AdviceType.REDUCE_POSITION,
                f"持有收益率已达 {holding_return_rate:.2f}%，近1年收益率 {one_year_return:.2f}% 处于高位，连续上涨 {continuous_up} 次，建议减仓锁定收益",
                0.85
            )

        # 6. 估值高位 + 连续上涨 + 回撤扩大 → 建议减仓
        if (one_year_return >= VALUATION_HIGH_THRESHOLD and
            continuous_up >= CONTINUOUS_UP_DAYS and
            max_drawdown > 10):
            return (
                AdviceType.REDUCE_POSITION,
                f"近1年收益率 {one_year_return:.2f}% 处于高位，连续上涨 {continuous_up} 次，回撤扩大至 {max_drawdown:.2f}%，建议减仓",
                0.75
            )

        # 7. 持有收益亏损 + 连续下跌 → 建议谨慎观望
        if holding_return_rate < -5 and trend == 'down':
            return (
                AdviceType.CAUTIOUS,
                f"持有收益率 {holding_return_rate:.2f}% 亏损，且趋势连续下跌，建议谨慎观望，不宜盲目加仓",
                0.7
            )

        # 8. 持有收益较高 → 提醒关注止盈机会
        if holding_return_rate > 20:
            return (
                AdviceType.HOLD,
                f"持有收益率已达 {holding_return_rate:.2f}%，收益丰厚，建议关注止盈机会，可分批减仓",
                0.65
            )

        # 9. 默认建议持有观望
        return (
            AdviceType.HOLD,
            "当前市场震荡，无明显操作信号，建议持有观望",
            0.5
        )

    def _calculate_suggested_amount(
        self,
        advice_type: AdviceType,
        estimated_change: float,
        current_amount: float,
        max_amount: float,
        holding_return_rate: float = 0
    ) -> float:
        """
        计算建议操作金额

        Args:
            advice_type: 建议类型
            estimated_change: 估算涨跌幅
            current_amount: 当前持仓金额
            max_amount: 持仓上限金额
            holding_return_rate: 持有收益率

        Returns:
            建议操作金额
        """
        if max_amount <= 0:
            return 0

        if advice_type == AdviceType.ADD_POSITION:
            # 加仓建议：建议加到上限的30%-50%
            # 如果持有收益亏损较多，适当增加加仓比例
            if holding_return_rate < -10:
                target_ratio = 0.5  # 亏损较多时更积极加仓
            else:
                target_ratio = 0.4
            target_amount = max_amount * target_ratio
            return max(0, target_amount - current_amount)

        elif advice_type == AdviceType.REDUCE_POSITION:
            # 减仓建议：根据持有收益率决定减仓比例
            if holding_return_rate > 20:
                return current_amount * 0.5  # 收益较高，减仓一半
            elif holding_return_rate > 10:
                return current_amount * 0.4
            else:
                return current_amount * 0.3

        elif advice_type == AdviceType.BATCH_BUY:
            # 分批低吸：建议买入持仓上限的10%-20%
            if current_amount < max_amount:
                # 根据跌幅和持有收益调整买入比例
                base_ratio = min(0.15, abs(estimated_change) / 10)
                if holding_return_rate < 0:
                    # 亏损时更积极买入摊薄成本
                    buy_ratio = base_ratio * 1.2
                else:
                    buy_ratio = base_ratio
                return min(max_amount * buy_ratio, max_amount - current_amount)
            return 0

        elif advice_type == AdviceType.TAKE_PROFIT:
            # 止盈：根据持有收益率决定止盈比例
            if holding_return_rate > 20:
                return current_amount * 0.35  # 收益较高，止盈更多
            elif holding_return_rate > 10:
                return current_amount * 0.25
            else:
                return current_amount * 0.2

        return 0

    def generate_all_advices(self) -> List[FundAdvice]:
        """
        生成所有基金的操作建议

        Returns:
            建议列表
        """
        advices = []
        for fund_code in self.monitor.get_monitored_funds():
            advice = self.generate_advice(fund_code)
            if advice:
                advices.append(advice)
        return advices

    def generate_afternoon_report(self) -> Dict[str, Any]:
        """
        生成下午2:40定时报告

        Returns:
            报告数据
        """
        # 检查是否在提醒时间（允许±5分钟误差）
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        reminder_hour, reminder_minute = AFTERNOON_REMINDER_TIME

        # 生成所有建议
        advices = self.generate_all_advices()

        # 统计数据
        total_funds = len(advices)
        add_count = sum(1 for a in advices if a.advice_type == AdviceType.ADD_POSITION)
        reduce_count = sum(1 for a in advices if a.advice_type == AdviceType.REDUCE_POSITION)
        buy_count = sum(1 for a in advices if a.advice_type == AdviceType.BATCH_BUY)
        profit_count = sum(1 for a in advices if a.advice_type == AdviceType.TAKE_PROFIT)
        hold_count = sum(1 for a in advices if a.advice_type == AdviceType.HOLD)

        # 计算总建议操作金额
        total_buy_amount = sum(
            a.suggested_amount for a in advices
            if a.advice_type in [AdviceType.ADD_POSITION, AdviceType.BATCH_BUY]
        )
        total_sell_amount = sum(
            a.suggested_amount for a in advices
            if a.advice_type in [AdviceType.REDUCE_POSITION, AdviceType.TAKE_PROFIT]
        )

        report = {
            'time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'is_reminder_time': (
                current_hour == reminder_hour and
                abs(current_minute - reminder_minute) <= 5
            ),
            'summary': {
                'total_funds': total_funds,
                'add_position_count': add_count,
                'reduce_position_count': reduce_count,
                'batch_buy_count': buy_count,
                'take_profit_count': profit_count,
                'hold_count': hold_count,
                'total_buy_amount': total_buy_amount,
                'total_sell_amount': total_sell_amount
            },
            'advices': [a.to_dict() for a in advices]
        }

        logger.info(f"生成下午报告: 共 {total_funds} 只基金，"
                   f"建议买入 {total_buy_amount:.2f} 元，"
                   f"建议卖出 {total_sell_amount:.2f} 元")

        return report


# 创建全局建议生成器（在导入monitor后初始化）
_advisor = None


def init_advisor(monitor_instance):
    """初始化全局建议生成器"""
    global _advisor
    _advisor = FundAdvisor(monitor_instance)


def get_advisor():
    """获取全局建议生成器实例"""
    global _advisor
    if _advisor is None:
        raise RuntimeError("Advisor not initialized. Call init_advisor() first.")
    return _advisor


if __name__ == '__main__':
    # 测试代码
    from monitor import monitor

    init_advisor(monitor)

    print("测试智能建议模块...")

    # 添加测试基金
    monitor.add_fund('000001', current_amount=10000, max_amount=50000)

    # 刷新数据
    monitor.refresh_data()

    # 生成建议
    print("\n生成建议...")
    advices = advisor.generate_all_advices()

    for advice in advices:
        print(f"\n{advice.fund_name}({advice.fund_code}):")
        print(f"  建议: {advice.advice_type.value}")
        print(f"  原因: {advice.reason}")
        print(f"  置信度: {advice.confidence:.0%}")
        print(f"  建议金额: {advice.suggested_amount:.2f} 元")

    # 生成下午报告
    print("\n下午报告:")
    report = advisor.generate_afternoon_report()
    print(f"  总基金数: {report['summary']['total_funds']}")
    print(f"  总买入金额: {report['summary']['total_buy_amount']:.2f}")
    print(f"  总卖出金额: {report['summary']['total_sell_amount']:.2f}")
