from grpc import AuthMetadataPlugin, AuthMetadataContext, AuthMetadataPluginCallback

from threading import Thread
import aiohttp
import asyncio
import json
from time import time

import logging
logger = logging.getLogger('ntx_python')
logging.getLogger('asyncio').setLevel(logging.CRITICAL)


async def wait_with_reraising(*args, **kwargs):
    for done in (await asyncio.wait(*args, **kwargs))[0]:
        done.result()  # Reraise exceptions


class FatalCondition(Exception):
    pass


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


class Token:
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


class WaitableToken:
    def __init__(self, loop):
        self.filled = asyncio.Event(loop=loop)
        self.token = None
    
    def set(self, token: Token):
        self.token = token
        self.filled.set()


class NewtonAuthMetadataPlugin:
    def __init__(self, conf):
        self.conf = {
            '_default_headers': {'Content-Type': 'application/json'},
            '_fatal_response': {404},
            '_adept_for_another_try': {401, 403},
            '_additional_attempts': 2,
            '_attempt_delay': 3,
            '_pause_after_failure': 60,
            **conf}
        self.InitialAttemptCondition = AttemptCondition(self.conf['_additional_attempts'])
        self._access_token = WaitableToken(None)
        self.ntx_token = WaitableToken(None)
        self.fatal = asyncio.Future()

    async def obtain(self, attempt: AttemptCondition, endpoint='/', body={}, headers={}):
        check(attempt.unexhausted())
        async with aiohttp.ClientSession() as session:
            request_body = json.dumps(body).encode()
            request_headers = {**headers, **self.conf['_default_headers']}
            async with session.post(f'{self.conf["audience"]}{endpoint}', data=request_body, headers=request_headers) as response:
                if response.status in self.conf['_adept_for_another_try']:
                    raise attempt.another()
                if response.status in self.conf['_fatal_response']:
                    raise FatalCondition
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
            logger.info('An attempt to obtain failed because: %s.', e)
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
            logger.warning('Keeping authenticated failed, trying again after %s s.', self.conf['_pause_after_failure'])
            await asyncio.sleep(self.conf['_pause_after_failure']) # TODO exponential backoff

    async def keep_authorized(self):
        while True:
            await self.authenticated()
            await self.keep_fresh(self.ntx_token, self.obtain_ntx_token, 'ntxToken')
            logger.warning('Keeping authorized failed, trying again after %s s.', self.conf['_pause_after_failure'])
            await asyncio.sleep(self.conf['_pause_after_failure']) # TODO exponential backoff

    async def purvey(self):
        try:
            await asyncio.gather(
                self.keep_authenticated(),
                self.keep_authorized())
        except FatalCondition as e:
            self.fatal.set_exception(e)
            await asyncio.Event().wait()  # Sleep forever

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
        self.fatal = asyncio.Future(loop=self.loop)
        self._thread = Thread(target=self._thread_function, daemon=self.conf['daemon'])
        self._thread.start()
        return UnderlyingMetadataPlugin(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        asyncio.run_coroutine_threadsafe(self.stop(), self.loop)
        if not self.conf['daemon']:
            self._thread.join()


class UnderlyingMetadataPlugin(AuthMetadataPlugin):
    def __init__(self, authenticator: NewtonAuthMetadataPlugin):
        self.authenticator = authenticator

    async def _async_wait(self):
        await self.authenticator.authenticated()
        logger.debug('Access token: %s', self.authenticator._access_token.token.data)
        await self.authenticator.authorized()
        logger.debug('Ntx token: %s', self.authenticator.ntx_token.token.data)

    async def async_wait(self):
        await wait_with_reraising({self._async_wait(), self.authenticator.fatal},
            return_when=asyncio.FIRST_COMPLETED)

    def wait(self):
        asyncio.run_coroutine_threadsafe(self.async_wait(), self.authenticator.loop).result()

    def __call__(self, context: AuthMetadataContext, callback: AuthMetadataPluginCallback):
        self.wait()
        callback((('ntx-token', self.authenticator.ntx_token.token.data),), None)


class BasicNewtonMetadataPlugin(AuthMetadataPlugin):
    def __init__(self, token: str):
        self.token = token

    def __call__(self, context: AuthMetadataContext, callback: AuthMetadataPluginCallback):
        callback((('ntx-token', self.token),), None)

    def wait(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
