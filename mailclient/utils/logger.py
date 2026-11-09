"""Journal technique volontairement limité aux événements sans données mail."""
import logging
from logging.handlers import RotatingFileHandler

def configure(directory):
    logger = logging.getLogger('smail')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(directory / 'smail.log', maxBytes=500_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    return logger
