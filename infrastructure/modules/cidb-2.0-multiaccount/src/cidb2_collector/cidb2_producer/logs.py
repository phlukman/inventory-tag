import logging
root = logging.getLogger()
if root.hasHandlers():
    root.handlers.clear
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)