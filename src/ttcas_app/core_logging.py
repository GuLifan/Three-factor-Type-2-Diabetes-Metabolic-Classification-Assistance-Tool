from __future__ import annotations

# 日志模块（TTCAS）
# - 所有模块统一使用同一个 logger name（ttcas），便于过滤/检索
# - 采用 RotatingFileHandler：限制单文件大小，避免日志无限增长

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_app_logger(*, logs_dir: Path) -> logging.Logger:
    """
    统一的滚动日志：
    - 默认写入 AppData/logs/app.log
    - 关键链路与异常堆栈都应记录，方便临床现场追溯与迭代排错
    """

    # 确保日志目录存在
    logs_dir.mkdir(parents=True, exist_ok=True)
    # 统一日志文件名
    log_file = logs_dir / "app.log"

    # 统一 logger 名称：便于在 GUI/压力测试中追加 handler
    logger = logging.getLogger("ttcas")
    # 默认级别：INFO（错误堆栈用 logger.exception 会自动带 traceback）
    logger.setLevel(logging.INFO)
    # 不向 root logger 传播，避免重复输出
    logger.propagate = False

    # 重新初始化前先清理旧 handler，避免重复写入
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # 统一格式：时间 | 级别 | logger name | message
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件滚动：2MB 一个文件，最多保留 5 个备份
    fh = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台输出：开发/测试时便于直接在终端观察
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # 启动即打一条日志，便于确认路径
    logger.info("日志初始化完成：%s", str(log_file))
    return logger
