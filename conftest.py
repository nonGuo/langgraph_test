"""
Pytest 配置，自动加载 .env 环境变量。
"""
from dotenv import load_dotenv

# 在测试开始前加载 .env 文件
load_dotenv(".env")
