from loguru import logger
import sys

def setup_logging():
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
    logger.add("logs/app.log", rotation="500 MB", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {file} | {line} | {message}")
    return logger

app_logger = setup_logging()
