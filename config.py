# -*- coding: utf-8 -*-
"""
基金实时监控助手 - 配置文件
所有可自定义的参数都在这里配置
"""

# ==================== 数据获取配置 ====================
# 数据刷新间隔（秒）
REFRESH_INTERVAL = 30

# 基金数据API（天天基金网公开接口）
FUND_INFO_API = "http://fundgz.1234567.com.cn/js/{fund_code}.js"
FUND_DETAIL_API = "http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
FUND_LIST_API = "http://fund.eastmoney.com/tssj/jjjz_{page}.html"

# ==================== 监控阈值配置 ====================
# 单日涨跌幅提醒阈值（%）
PRICE_CHANGE_THRESHOLD = 1.5

# 估算净值与实际净值偏差提醒阈值（%）
ESTIMATE_DEVIATION_THRESHOLD = 0.3

# 重仓股涨跌幅提醒阈值（%）
STOCK_CHANGE_THRESHOLD = 5.0

# 最大回撤风险提醒阈值（%）
MAX_DRAWDOWN_THRESHOLD = 15.0

# ==================== 智能建议阈值配置 ====================
# 估值低位判断（近1年收益率低于此值视为低位）
VALUATION_LOW_THRESHOLD = -10.0

# 估值高位判断（近1年收益率高于此值视为高位）
VALUATION_HIGH_THRESHOLD = 30.0

# 连续上涨天数判断
CONTINUOUS_UP_DAYS = 3

# 大跌提醒阈值（%）
BIG_DROP_THRESHOLD = 3.0

# 大涨提醒阈值（%）
BIG_RISE_THRESHOLD = 4.0

# 分批低吸建议触发阈值（%）
BATCH_BUY_THRESHOLD = -3.0

# 止盈建议触发阈值（%）
TAKE_PROFIT_THRESHOLD = 4.0

# 持有收益率相关阈值
# 高收益提醒阈值（%）
HIGH_HOLDING_RETURN_THRESHOLD = 20.0

# 亏损预警阈值（%）
LOSS_WARNING_THRESHOLD = -10.0

# ==================== 定时提醒配置 ====================
# 下午2:40提醒时间（小时，分钟）
AFTERNOON_REMINDER_TIME = (14, 40)

# ==================== 风险等级配置 ====================
# 风险等级划分
RISK_LEVELS = {
    'low': {
        'max_drawdown': 5.0,
        'label': '低风险',
        'color': 'green'
    },
    'medium': {
        'max_drawdown': 15.0,
        'label': '中风险',
        'color': 'orange'
    },
    'high': {
        'max_drawdown': float('inf'),
        'label': '高风险',
        'color': 'red'
    }
}

# ==================== 数据存储配置 ====================
# 基金数据存储文件
DATA_FILE = "fund_data.json"

# 历史数据保留天数
HISTORY_KEEP_DAYS = 30

# ==================== 代理配置（可选） ====================
# 如果需要代理访问，配置如下
PROXY = None
# PROXY = {
#     'http': 'http://127.0.0.1:7890',
#     'https': 'http://127.0.0.1:7890'
# }

# ==================== 请求配置 ====================
# 请求超时时间（秒）
REQUEST_TIMEOUT = 10

# 请求重试次数
REQUEST_RETRIES = 3

# 请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'http://fund.eastmoney.com/'
}
