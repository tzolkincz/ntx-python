import aiohttp
import asyncio, asyncio_compatibility # The compatibility layer after asyncio

import json

from __config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL

_DEFAULT_HEADERS = {'Content-Type': 'application/json'}

async def obtain_access_token(audience=AUDIENCE, username=USERNAME, password=PASSWORD):
    async with aiohttp.ClientSession() as session:
        request_body = json.dumps({'username': username, 'password': password}).encode()
        async with session.post(f'{audience}/login/access-token', data=request_body, headers=_DEFAULT_HEADERS) as response:
            if response.status != 200:
                return None
            return await response.text()

_ACCESS_TOKEN = None

async def set_access_token():
    global _ACCESS_TOKEN
    access_token_response = await obtain_access_token()
    try:
        access_token_data = json.loads(access_token_response)
        _ACCESS_TOKEN = access_token_data['accessToken']
    except (TypeError, json.decoder.JSONDecodeError, KeyError):
        # TODO log
        _ACCESS_TOKEN = None
    

async def obtain_ntx_token(id=ID, label=LABEL, audience=AUDIENCE, access_token=None):
    if access_token == None:
        global _ACCESS_TOKEN
        access_token = _ACCESS_TOKEN
    async with aiohttp.ClientSession() as session:
        request_body = json.dumps({'id': id, 'label': label})
        request_headers = {**{'ntx-token': access_token}, **_DEFAULT_HEADERS}
        async with session.post(f'{audience}/store/ntx-token', data=request_body, headers=request_headers) as response:
            if response.status != 200:
                return None
            return await response.text()

NTX_TOKEN = None

async def set_ntx_token():
    global NTX_TOKEN
    ntx_token_response = await obtain_ntx_token()
    try:
        ntx_token_data = json.loads(ntx_token_response)
        NTX_TOKEN = ntx_token_data['ntxToken']
    except (TypeError, json.decoder.JSONDecodeError, KeyError):
        # TODO log
        NTX_TOKEN = None

async def authenticate_and_authorize():
    await set_access_token()
    await set_ntx_token()
    #return NTX_TOKEN

def main():
    asyncio_compatibility.run(authenticate_and_authorize())
    print(_ACCESS_TOKEN)
    print(NTX_TOKEN)

if __name__ == '__main__':
    main()