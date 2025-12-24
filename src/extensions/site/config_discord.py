import asyncio
from datetime import datetime

from logs import log_info, log_warning, log_error

active_config_links = {}

async def expire_config_link():
    while True:
        await asyncio.sleep(10)
        for token in list(active_config_links.keys()):
            link_info = active_config_links[token]
            if datetime.now() >= link_info['expiration_time']:
                del active_config_links[token]
                break