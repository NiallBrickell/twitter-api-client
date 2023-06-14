import asyncio
import logging
import math
import platform
import random
import time
from logging import Logger
from pathlib import Path

import orjson
from httpx import AsyncClient, Client

from .constants import *
from .login import login
from .util import set_qs, get_headers, find_key

reset = '\u001b[0m'
colors = [f'\u001b[{i}m' for i in range(30, 38)]

logger = logging.getLogger(__name__)

try:
    if get_ipython().__class__.__name__ == 'ZMQInteractiveShell':
        import nest_asyncio

        nest_asyncio.apply()
except:
    ...

if platform.system() != 'Windows':
    try:
        import uvloop

        uvloop.install()
    except ImportError as e:
        ...


class Search:
    def __init__(self, email: str = None, username: str = None, password: str = None, session: Client = None, client_kwargs: dict = {}, **kwargs):
        self.session = self._validate_session(email, username, password, session, **kwargs)
        self.api = 'https://api.twitter.com/2/search/adaptive.json?'
        self.save = kwargs.get('save', True)
        self.debug = kwargs.get('debug', 0)
        self.client = AsyncClient(headers=get_headers(self.session), **client_kwargs)

    async def aclose(self):
        return await self.client.aclose()

    def run(self, *args, out: str = 'data', **kwargs):
        out_path = self.make_output_dirs(out)
        if kwargs.get('latest', False):
            search_config['tweet_search_mode'] = 'live'
        return asyncio.run(self.process(args, search_config, out_path, **kwargs))

    async def process(self, queries: tuple, config: dict, out: Path, **kwargs) -> list:
        return await asyncio.gather(*(self.paginate(q, self.client, config, out, **kwargs) for q in queries))

    async def paginate(self, query: str, session: AsyncClient, config: dict, out: Path, **kwargs) -> list[dict]:
        config['q'] = query
        data, next_cursor = await self.backoff(lambda: self.get(session, config), query, **kwargs)
        all_data = [data]
        c = colors.pop() if colors else ''
        ids = set()
        while next_cursor:
            ids |= set(data['globalObjects']['tweets'])
            if len(ids) >= kwargs.get('limit', math.inf):
                if self.debug:
                    logger.debug(
                        f'Returned {len(ids)} search results for {query}')
                return all_data
            if self.debug:
                logger.debug(f'{query}')
            config['cursor'] = next_cursor

            data, next_cursor = await self.backoff(lambda: self.get(session, config), query, **kwargs)
            if not data:
                return all_data

            data['query'] = query

            if self.save:
                (out / f'raw/{time.time_ns()}.json').write_text(
                    orjson.dumps(data, option=orjson.OPT_INDENT_2).decode(),
                    encoding='utf-8'
                )
            all_data.append(data)
        return all_data

    async def backoff(self, fn, info, **kwargs):
        retries = kwargs.get('retries', 3)
        for i in range(retries + 1):
            try:
                data, next_cursor = await fn()
                if not data.get('globalObjects', {}).get('tweets'):
                    raise Exception
                return data, next_cursor
            except Exception as e:
                if i == retries:
                    if self.debug:
                        logger.debug(f'Max retries exceeded: {e}')
                    return None, None
                t = 2 ** i + random.random()
                if self.debug:
                    logger.debug(
                        f'No data for: {info}, retrying in {f"{t:.2f}"} seconds: {e}')
                time.sleep(t)

    async def get(self, session: AsyncClient, params: dict) -> tuple:
        url = set_qs(self.api, params, update=True, safe='()')
        r = await session.get(url)
        data = r.json()
        next_cursor = self.get_cursor(data)
        return data, next_cursor

    def get_cursor(self, res: dict):
        try:
            if live := find_key(res, 'value'):
                if cursor := [x for x in live if 'scroll' in x]:
                    return cursor[0]
            for instr in res['timeline']['instructions']:
                if replaceEntry := instr.get('replaceEntry'):
                    cursor = replaceEntry['entry']['content']['operation']['cursor']
                    if cursor['cursorType'] == 'Bottom':
                        return cursor['value']
                    continue
                for entry in instr['addEntries']['entries']:
                    if entry['entryId'] == 'cursor-bottom-0':
                        return entry['content']['operation']['cursor']['value']
        except Exception as e:
            if self.debug:
                logger.debug(e)

    def make_output_dirs(self, path: str) -> Path:
        p = Path(f'{path}')
        (p / 'raw').mkdir(parents=True, exist_ok=True)
        (p / 'processed').mkdir(parents=True, exist_ok=True)
        (p / 'final').mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def _validate_session(*args, **kwargs):
        email, username, password, session = args
        if session and all(session.cookies.get(c) for c in {'ct0', 'auth_token'}):
            # authenticated session provided
            return session
        if not session:
            # no session provided, log-in to authenticate
            return login(email, username, password, **kwargs)
        raise Exception('Session not authenticated. '
                        'Please use an authenticated session or remove the `session` argument and try again.')
