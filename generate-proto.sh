#!/bin/bash

OUT_DIR=./ntx_protobuf

#python -m pip install grpcio
#python -m pip install grpcio-tools

python -m grpc_tools.protoc -I. --python_out=$OUT_DIR --grpc_python_out=$OUT_DIR engine.proto