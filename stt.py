import grpc
import protobuf.engine_pb2 as engine_pb2

import sys, os; sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'protobuf')) # Python yuck
import protobuf.engine_pb2_grpc as engine_pb2_grpc

import asyncio
from threading import Thread
from jwt_auth_metadata_plugin import JwtAuthMetadataPlugin

from __config__ import DOMAIN

def test():
    ssl_cred = grpc.ssl_channel_credentials() # Default from Mozilla
    channel = grpc.secure_channel(f'{DOMAIN}:443', ssl_cred)
    stub = engine_pb2_grpc.EngineServiceStub(channel)


if __name__ == '__main__':
    with JwtAuthMetadataPlugin() as awaiter:
        print("Waiting")
        awaiter.wait()
        print("Done")
