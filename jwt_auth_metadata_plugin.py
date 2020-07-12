import logging, sys
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
from typing import Callable, Dict


from grpc import AuthMetadataPlugin, AuthMetadataContext, AuthMetadataPluginCallback

from threading import Thread
import aiohttp
import asyncio
import json
from time import time


class CheckError(Exception):
    pass


# Like assert statement, but this one is logical, you can't switch it off
def check(expression: bool):
    if not expression:
        raise CheckError


class AttemptCondition(Exception):
    def __init__(self, remaining_number):
        self.remaining_number = remaining_number
    
    def unexhausted(self):
        return 0 < self.remaining_number

    def another(self):
        return AttemptCondition(self.remaining_number - 1)


class Token():
    VALID_PART = 0.75

    def __init__(self, data, key):
        self.arrival = int(time())
        self.data = data[key]
        self.expiration = int(data['expiresAt'])
    
    def _valid_duration(self):
        return self.VALID_PART * (self.expiration - self.arrival)

    async def become_stale(self):
        stale_timestamp = self.arrival + self._valid_duration()
        await asyncio.sleep(stale_timestamp - int(time()))


class WaitableToken():
    def __init__(self, loop):
        self.filled = asyncio.Event(loop=loop)
        self.token = None
    
    def set(self, token: Token):
        self.token = token
        self.filled.set()


class JwtAuthMetadataPlugin():
    def __init__(self, conf):
        self.conf = {
            '_default_headers': {'Content-Type': 'application/json'},
            '_adept_for_another_try': {401, 403},
            '_additional_attempts': 2,
            '_attempt_delay': 3,
            '_pause_after_failure': 60,
            **conf}
        self.InitialAttemptCondition = AttemptCondition(self.conf['_additional_attempts'])
        self._access_token = WaitableToken(None)
        self.ntx_token = WaitableToken(None)

    async def obtain(self, attempt: AttemptCondition, endpoint='/', body={}, headers={}):
        check(attempt.unexhausted())
        async with aiohttp.ClientSession() as session:
            request_body = json.dumps(body).encode()
            request_headers = {**headers, **self.conf['_default_headers']}
            async with session.post(f'{self.conf["audience"]}{endpoint}', data=request_body, headers=request_headers) as response:
                if response.status in self.conf['_adept_for_another_try']:
                    raise attempt.another()
                check(response.status == 200)
                return await response.text()

    async def obtain_access_token(self, attempt):
        return await self.obtain(attempt, '/login/access-token',
            {k:v for k,v in self.conf.items() if k in {'username', 'password'}})

    async def obtain_ntx_token(self, attempt):
        check(self._access_token is not None)
        return await self.obtain(attempt, '/store/ntx-token',
            {k:v for k,v in self.conf.items() if k in {'id', 'label'}},
            {'ntx-token': self._access_token.token.data})

    async def attempt_repeatedly(self, obtainer):
        try:
            attempt = self.InitialAttemptCondition
            while True:
                try:
                    return json.loads(await obtainer(attempt))
                except AttemptCondition as another_attempt:
                    attempt = another_attempt
                    await asyncio.sleep(self.conf['_attempt_delay'])
        except (CheckError, TypeError, json.decoder.JSONDecodeError, KeyError) as e:
            logging.info('An attempt to obtain failed because: %s.', e)
            raise CheckError

    async def authenticated(self):
        await self._access_token.filled.wait()
    
    async def authorized(self):
        await self.ntx_token.filled.wait()

    async def keep_fresh(self, w_token: WaitableToken, obtainer, extracting_key: str):
        try:
            while True:
                w_token.set(Token(await self.attempt_repeatedly(obtainer), extracting_key))
                await w_token.token.become_stale()
        except CheckError:
            w_token.filled.clear()

    async def keep_authenticated(self):
        while True:
            await self.keep_fresh(self._access_token, self.obtain_access_token, 'accessToken')
            logging.warning('Keeping authenticated failed, trying again after %s s.', self.conf['_pause_after_failure'])
            await asyncio.sleep(self.conf['_pause_after_failure']) # TODO exponential backoff

    async def keep_authorized(self):
        while True:
            await self.authenticated()
            await self.keep_fresh(self.ntx_token, self.obtain_ntx_token, 'ntxToken')
            logging.warning('Keeping authorized failed, trying again after %s s.', self.conf['_pause_after_failure'])
            await asyncio.sleep(self.conf['_pause_after_failure']) # TODO exponential backoff

    async def purvey(self):
        await asyncio.gather(
            self.keep_authenticated(),
            self.keep_authorized())

    async def _stopper(self):
        await self._stop_signal.wait()

    async def stop(self):
        self._stop_signal.set()

    async def _stoppable_purvey(self):
        await asyncio.wait({self.purvey(), self._stopper()},
            return_when=asyncio.FIRST_COMPLETED)

    def _thread_function(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._stoppable_purvey())
        self.loop.close()

    def __enter__(self):
        """For non-async code"""
        self.loop = asyncio.new_event_loop()
        self._stop_signal = asyncio.Event(loop=self.loop)
        self._access_token = WaitableToken(self.loop)
        self.ntx_token = WaitableToken(self.loop)
        self._thread = Thread(target=self._thread_function, daemon=self.conf['daemon'])
        self._thread.start()
        return UnderlyingMetadataPlugin(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        asyncio.run_coroutine_threadsafe(self.stop(), self.loop)
        if not self.conf['daemon']:
            self._thread.join()


class UnderlyingMetadataPlugin(AuthMetadataPlugin):
    def __init__(self, authenticator: JwtAuthMetadataPlugin):
        self.authenticator = authenticator

    async def _wait(self):
        await self.authenticator.authenticated()
        logging.debug('Access token: %s', self.authenticator._access_token.token.data)
        await self.authenticator.authorized()
        logging.debug('Ntx token: %s', self.authenticator.ntx_token.token.data)

    def wait(self):
        asyncio.run_coroutine_threadsafe(self._wait(), self.authenticator.loop).result()

    def __call__(self, context: AuthMetadataContext, callback: AuthMetadataPluginCallback):
        self.wait()
        callback((('ntx-token', self.authenticator.ntx_token.token.data),), None)

def main_with_async():
    from __config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL
    m = JwtAuthMetadataPlugin({
            'audience': AUDIENCE,
            'username': USERNAME,
            'password': PASSWORD,
            'id': ID,
            'label': LABEL})
    u = UnderlyingMetadataPlugin(m)
    all_async = asyncio.wait({u._wait(), m.purvey()}, return_when=asyncio.FIRST_COMPLETED)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(all_async)

def main():
    from __config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL
    with JwtAuthMetadataPlugin({
            'audience': AUDIENCE,
            'username': USERNAME,
            'password': PASSWORD,
            'id': ID,
            'label': LABEL}) as u:
        u.wait()

if __name__=='__main__':
    #main_with_async()
    main()