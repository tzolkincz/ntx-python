# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

import engine_pb2 as engine__pb2


class EngineServiceStub(object):
    """Missing associated documentation comment in .proto file"""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.StreamingRecognize = channel.stream_stream(
                '/ntx.v2t.engine.EngineService/StreamingRecognize',
                request_serializer=engine__pb2.EngineStream.SerializeToString,
                response_deserializer=engine__pb2.EngineStream.FromString,
                )


class EngineServiceServicer(object):
    """Missing associated documentation comment in .proto file"""

    def StreamingRecognize(self, request_iterator, context):
        """Missing associated documentation comment in .proto file"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_EngineServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'StreamingRecognize': grpc.stream_stream_rpc_method_handler(
                    servicer.StreamingRecognize,
                    request_deserializer=engine__pb2.EngineStream.FromString,
                    response_serializer=engine__pb2.EngineStream.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'ntx.v2t.engine.EngineService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class EngineService(object):
    """Missing associated documentation comment in .proto file"""

    @staticmethod
    def StreamingRecognize(request_iterator,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.stream_stream(request_iterator, target, '/ntx.v2t.engine.EngineService/StreamingRecognize',
            engine__pb2.EngineStream.SerializeToString,
            engine__pb2.EngineStream.FromString,
            options, channel_credentials,
            call_credentials, compression, wait_for_ready, timeout, metadata)
