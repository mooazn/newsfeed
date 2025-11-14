import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logger():
    logs_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_path = os.path.join(logs_dir, "newsfeed.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5
    )
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler, console]
    )

    return logging.getLogger("newsfeed")
