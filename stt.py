import grpc
import protobuf.engine_pb2

import sys, os; sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'protobuf')) # Python yuck
import protobuf.engine_pb2_grpc

from ntx_token import main

#def test():
#    channel = grpc.insecure_channel()
#    stub = engine_pb2_grpc.

if __name__ == '__main__':
    main()
