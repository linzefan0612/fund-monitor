# 基金实时监控助手

一个基于 Python Flask 的基金实时监控 Web 应用，支持实时数据获取、智能建议、风险提醒、图片识别等功能。

## 功能特性

### 1. 实时数据获取
- 从天天基金网获取实时基金净值、估算净值、涨跌幅
- 支持获取基金经理、持仓股票、最大回撤、收益率等详细数据
- 每30秒自动刷新数据
- 支持多数据源切换（天天基金、蛋卷基金、蚂蚁财富、且慢）

### 2. 智能监控提醒
- 单日涨跌幅 ≥ ±1.5% 自动提醒
- 估算净值与实际净值偏差 ≥ 0.3% 自动提醒
- 重仓股涨跌幅 > 5% 自动提醒
- 最大回撤超过阈值自动风险提醒

### 3. 智能操作建议
根据估值位置、趋势、回撤等综合分析生成建议：
- **建议加仓**: 估值低位 + 趋势向上 + 回撤较小
- **建议减仓**: 估值高位 + 连续上涨 + 回撤扩大
- **建议持有观望**: 中期震荡 + 无明确方向
- **建议分批低吸**: 单日大跌 ≥ 3%
- **建议止盈部分仓位**: 单日大涨 ≥ 4%
- **建议谨慎观望**: 基金经理变更、规模暴增等

### 4. 持仓管理
- 支持设置当前持仓金额和持仓上限
- 自动计算持仓比例和预估收益
- 下午2:40自动生成操作建议报告

### 5. 图片识别同步持仓
- 支持 OCR 图片识别，快速导入持仓
- 支持天天基金、支付宝、券商APP持仓截图
- 支持文本输入和Excel批量导入

### 6. 当日榜单
- 实时展示所有基金涨跌排名
- 支持按估算涨跌、预估收益排序

### 7. 基金查询
- 输入基金代码查看详细信息
- 展示净值走势图和持仓分布

## 快速开始

### 方式一：使用启动脚本（推荐）

双击运行 `start.bat`，脚本会自动：
1. 检查 Python 环境
2. 安装依赖
3. 启动服务

### 方式二：手动启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动应用
python app.py
```

启动后访问: http://localhost:5000

## 使用说明

### 添加基金
1. 输入6位基金代码（如：000001）
2. 可选填入当前持仓金额、持仓上限、持有收益率
3. 点击"添加基金"

### 同步持仓（图片识别）
1. 点击"📥 同步持仓"按钮
2. 上传持仓截图（支持天天基金、支付宝、券商APP）
3. 系统自动识别基金信息和持仓金额
4. 勾选需要添加的基金，点击确认

也可使用文本输入或Excel批量导入。

### 编辑持仓
- 点击基金卡片上的"编辑持仓"按钮
- 输入当前持仓金额和持仓上限
- 保存后自动刷新

### 移除基金
- 点击基金卡片上的"移除"按钮
- 确认后即可移除监控

### 查看报告
- 点击"📋 操作建议"按钮查看当日操作建议汇总
- 点击"🏆 当日榜单"按钮查看涨跌排名

### 基金查询
- 点击"🔍 基金查询"按钮
- 输入基金代码查看详细信息、净值走势、持仓分布

## 参数配置

编辑 `config.py` 文件可自定义以下参数：

### 监控阈值
```python
# 单日涨跌幅提醒阈值（%）
PRICE_CHANGE_THRESHOLD = 1.5

# 估算净值偏差提醒阈值（%）
ESTIMATE_DEVIATION_THRESHOLD = 0.3

# 重仓股涨跌幅提醒阈值（%）
STOCK_CHANGE_THRESHOLD = 5.0

# 最大回撤风险提醒阈值（%）
MAX_DRAWDOWN_THRESHOLD = 15.0
```

### 智能建议阈值
```python
# 估值低位判断（近1年收益率低于此值视为低位）
VALUATION_LOW_THRESHOLD = -10.0

# 估值高位判断（近1年收益率高于此值视为高位）
VALUATION_HIGH_THRESHOLD = 30.0

# 大跌提醒阈值（%）
BIG_DROP_THRESHOLD = 3.0

# 大涨提醒阈值（%）
BIG_RISE_THRESHOLD = 4.0
```

### 其他配置
```python
# 数据刷新间隔（秒）
REFRESH_INTERVAL = 30

# 下午提醒时间（小时，分钟）
AFTERNOON_REMINDER_TIME = (14, 40)
```

### OCR 配置（图片识别）
```python
# 是否启用 OCR 功能
OCR_ENABLED = True

# OCR 识别语言
OCR_LANGUAGE = 'chi_sim+eng'

# Tesseract OCR 路径（Windows）
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

## 项目结构

```
fund-monitor/
├── app.py              # Flask 主应用
├── config.py           # 配置文件
├── fund_data.py        # 基金数据获取模块
├── monitor.py          # 监控和提醒模块
├── advisor.py          # 智能建议模块
├── ocr_service.py      # OCR 图片识别模块
├── requirements.txt    # 依赖列表
├── start.bat           # Windows 启动脚本
├── fund_data.json      # 数据存储文件（运行时自动生成）
└── templates/
    ├── index_vue.html      # 前端页面（Ant Design Vue版）
```

## 访问地址

- Ant Design Vue 版本: http://localhost:5000/
- Element Plus 版本: http://localhost:5000/element

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/funds` | GET | 获取所有基金数据 |
| `/api/funds/refresh` | POST | 刷新所有基金数据 |
| `/api/funds/add` | POST | 添加监控基金 |
| `/api/funds/batch` | POST | 批量添加基金 |
| `/api/funds/<code>` | DELETE | 移除监控基金 |
| `/api/funds/clear-all` | DELETE | 清除所有基金 |
| `/api/funds/<code>/position` | PUT | 更新持仓配置 |
| `/api/fund/query/<code>` | GET | 查询单只基金详情 |
| `/api/fund/history/<code>` | GET | 获取基金历史净值 |
| `/api/fund/holdings/<code>` | GET | 获取基金持仓信息 |
| `/api/fund/search` | GET | 按名称搜索基金 |
| `/api/alerts` | GET | 获取提醒列表 |
| `/api/alerts/clear` | POST | 清除所有提醒 |
| `/api/advices` | GET | 获取操作建议 |
| `/api/report` | GET | 获取下午报告 |
| `/api/datasource` | GET/PUT | 获取/切换数据源 |
| `/api/ocr/recognize` | POST | OCR 图片识别 |
| `/api/ocr/parse` | POST | 解析 OCR 文本 |

## 常见问题

### Q: 为什么获取数据失败？
A: 请检查网络连接，确保能访问天天基金网。如果在国内网络环境下仍无法访问，可能需要配置代理。

### Q: 如何配置代理？
A: 编辑 `config.py` 文件，取消 `PROXY` 配置的注释并填入代理地址：
```python
PROXY = {
    'http': 'http://127.0.0.1:7890',
    'https': 'http://127.0.0.1:7890'
}
```

### Q: 数据存储在哪里？
A: 基金配置和历史数据存储在 `fund_data.json` 文件中，删除该文件将清空所有配置。

### Q: OCR 识别不准确怎么办？
A:
1. 确保截图清晰，基金名称和代码完整可见
2. 安装 Tesseract OCR 提高识别准确率
3. 识别后可手动修改金额
4. 使用文本输入方式替代

### Q: 如何安装 Tesseract OCR？
A:
1. Windows: 从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装
2. 安装 Python 依赖: `pip install pytesseract pillow`
3. 如未安装到默认路径，在 `config.py` 中配置 `TESSERACT_PATH`

## 注意事项

1. 本工具仅供学习参考，不构成投资建议
2. 数据来源于天天基金网公开接口，请合理使用
3. 投资有风险，决策需谨慎

## 技术栈

- Python 3.8+
- Flask 2.3
- Vue 3 (CDN)
- Ant Design Vue 4.2
- ECharts 5.4 (图表)
- Tesseract.js / pytesseract (OCR图片识别)

## License

MIT License
