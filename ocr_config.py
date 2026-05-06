# -*- coding: utf-8 -*-
"""
基金实时监控助手 - OCR配置文件
配置第三方OCR服务，用于图片识别
"""

# ==================== OCR服务配置 ====================
# 启用第三方OCR服务（True=启用, False=禁用，使用本地Tesseract.js）
OCR_ENABLED = False

# OCR服务类型: "baidu" | "tencent" | "aliyun" | "custom"
OCR_PROVIDER = "baidu"

# ==================== 百度OCR配置 ====================
# 申请地址: https://cloud.baidu.com/product/ocr
BAIDU_OCR = {
    "app_id": "",      # 百度云AppID
    "api_key": "",     # 百度云API Key
    "secret_key": "",  # 百度云Secret Key
}

# ==================== 腾讯OCR配置 ====================
# 申请地址: https://cloud.tencent.com/product/ocr
TENCENT_OCR = {
    "secret_id": "",    # 腾讯云SecretId
    "secret_key": "",   # 腾讯云SecretKey
    "region": "ap-guangzhou",  # 地域
}

# ==================== 阿里云OCR配置 ====================
# 申请地址: https://www.aliyun.com/product/ocr
ALIYUN_OCR = {
    "access_key_id": "",     # 阿里云AccessKey ID
    "access_key_secret": "", # 阿里云AccessKey Secret
    "endpoint": "ocr-api.cn-hangzhou.aliyuncs.com",
}

# ==================== 自定义OCR配置 ====================
# 如果使用其他OCR服务，可在此配置
CUSTOM_OCR = {
    "api_url": "",      # OCR API地址
    "api_key": "",      # API密钥
    "headers": {},      # 自定义请求头
}
