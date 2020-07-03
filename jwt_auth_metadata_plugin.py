from grpc import AuthMetadataPlugin, AuthMetadataContext, AuthMetadataPluginCallback

from threading import Thread
import aiohttp
import asyncio
import json
from time import time

from __config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL

_DEFAULT_HEADERS = {'Content-Type': 'application/json'}
_ADEPT_FOR_ANOTHER_TRY = {401, 403}
_NUMBER_OF_ADDITIONAL_ATTEMPTS = 2
_ATTEMPT_DELAY = 3
_PAUSE_AFTER_FAILURE = 60

from typing import Callable, Dict


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
    def __init__(self, audience=AUDIENCE, username=USERNAME, password=PASSWORD, id=ID, label=LABEL):
        self.InitialAttemptCondition = AttemptCondition(_NUMBER_OF_ADDITIONAL_ATTEMPTS)
        self._access_token = WaitableToken(None)
        self.ntx_token = WaitableToken(None)
        #self.loop = asyncio.get_event_loop()
        
        self.audience = audience
        self.username = username
        self.password = password
        self.id = id
        self.label = label

    async def obtain(self, attempt: AttemptCondition, endpoint='/', body={}, headers={}):
        check(attempt.unexhausted())
        async with aiohttp.ClientSession() as session:
            request_body = json.dumps(body).encode()
            request_headers = {**headers, **_DEFAULT_HEADERS}
            async with session.post(f'{self.audience}{endpoint}', data=request_body, headers=request_headers) as response:
                if response.status in _ADEPT_FOR_ANOTHER_TRY:
                    raise attempt.another()
                check(response.status == 200)
                return await response.text()

    async def obtain_access_token(self, attempt):
        return await self.obtain(attempt, '/login/access-token',
            {'username': self.username, 'password': self.password})

    async def obtain_ntx_token(self, attempt):
        check(self._access_token is not None)
        return await self.obtain(attempt, '/store/ntx-token',
            {'id': self.id, 'label': self.label},
            {'ntx-token': self._access_token.token.data})

    async def attempt_repeatedly(self, obtainer):
        try:
            attempt = self.InitialAttemptCondition
            while True:
                try:
                    return json.loads(await obtainer(attempt))
                except AttemptCondition as another_attempt:
                    attempt = another_attempt
                    await asyncio.sleep(_ATTEMPT_DELAY)
        except (CheckError, TypeError, json.decoder.JSONDecodeError, KeyError):
            # TODO log
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
            # TODO log
            await asyncio.sleep(_PAUSE_AFTER_FAILURE)

    async def keep_authorized(self):
        while True:
            await self.authenticated()
            await self.keep_fresh(self.ntx_token, self.obtain_ntx_token, 'ntxToken')
            # TODO log
            await asyncio.sleep(_PAUSE_AFTER_FAILURE)

    async def purvey(self):
        await asyncio.gather(
            self.keep_authorized(),
            self.keep_authenticated())

    def _thread_function(self, authenticator, loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(authenticator.purvey())

    def __enter__(self):
        """For non-async code"""
        self.loop = asyncio.new_event_loop()
        self._access_token = WaitableToken(self.loop)
        self.ntx_token = WaitableToken(self.loop)
        self._thread = Thread(target=self._thread_function, args=(self, self.loop))
        self._thread.setDaemon(True)
        self._thread.start()
        return UnderlyingMetadataPlugin(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        #self._thread.join()
        pass


class UnderlyingMetadataPlugin(AuthMetadataPlugin):
    def __init__(self, authenticator: JwtAuthMetadataPlugin):
        self.authenticator = authenticator

    async def _wait(self):
        await self.authenticator.authenticated()
        print(self.authenticator._access_token.token.data)
        await self.authenticator.authorized()
        print(self.authenticator.ntx_token.token.data)

    def wait(self):
        asyncio.run_coroutine_threadsafe(self._wait(), self.authenticator.loop).result()

    def __call__(self, context: AuthMetadataContext, callback: AuthMetadataPluginCallback):
        self.wait()
        callback((('ntx-token', self.authenticator.ntx_token.token.data),), None)

def main():
    m = JwtAuthMetadataPlugin()
    u = UnderlyingMetadataPlugin(m)
    all_async = asyncio.wait({u._wait(), m.purvey()}, return_when=asyncio.FIRST_COMPLETED)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(all_async)

if __name__=='__main__':
    main()