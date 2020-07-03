from __config__ import DOMAIN

from typing import Iterator

from threading import Event as ThreadEvent
from itertools import chain

import grpc
import protobuf.engine_pb2 as engine_pb2
from protobuf.engine_pb2 import EngineStream, EngineContext, EngineContextStart, EngineContextEnd, EventsPush, EventsPull, Events, Event, Lexicon, AudioFormat
#Python is a little different – the Python compiler generates a module with a static descriptor of each message type in your .proto, which is then used with a metaclass to create the necessary Python data access class at runtime.
#pylint: disable=no-member
ChannelLayout = AudioFormat.ChannelLayout; SampleFormat = AudioFormat.SampleFormat; SampleRate = AudioFormat.SampleRate; AutoDetect = AudioFormat.AutoDetect; PCM = AudioFormat.PCM; Header = AudioFormat.Header
V2TConfig = EngineContext.V2TConfig; VADConfig = EngineContext.VADConfig; PNCConfig = EngineContext.PNCConfig; PPCConfig = EngineContext.PPCConfig; AudioChannel = EngineContext.AudioChannel
LexItem = Lexicon.LexItem; MainItem = Lexicon.MainItem; NoiseItem = Lexicon.NoiseItem; UserItem = Lexicon.UserItem
Meta = Event.Meta; Audio = Event.Audio; Label = Event.Label; Timestamp = Event.Timestamp

import sys, os; sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'protobuf')) # Python yuck
import protobuf.engine_pb2_grpc as engine_pb2_grpc

from jwt_auth_metadata_plugin import JwtAuthMetadataPlugin, UnderlyingMetadataPlugin

from scipy.io.wavfile import read as read_wav
#import numpy as np


class NewtonEngine():
    def __init__(self, config, creds_plugin: UnderlyingMetadataPlugin):
        self.config = config
        self.creds_plugin = creds_plugin
        self.finished = ThreadEvent()

    def __enter__(self):
        ssl_cred = grpc.ssl_channel_credentials() # Default from Mozilla
        call_cred = grpc.metadata_call_credentials(self.creds_plugin)
        composed_creds = grpc.composite_channel_credentials(ssl_cred, call_cred)
        self._channel = grpc.secure_channel(f'{self.config["domain"]}:443', composed_creds)
        self.stub = engine_pb2_grpc.EngineServiceStub(self._channel)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._channel.close()

    def _start(self):
        yield EngineStream(
            start=EngineContextStart(
                context=EngineContext(
                    v2t=V2TConfig(
                        withPNC=PNCConfig(),
                        withPPC=PPCConfig()),
                    audioChannel=EngineContext.AUDIO_CHANNEL_DOWNMIX,
                    audioFormat=AudioFormat(
                        pcm=PCM(
                            channelLayout=self.config['channels'],
                            sampleRate=self.config['rate'],
                            sampleFormat=self.config['format'])))))

    @staticmethod
    def _end():
        yield EngineStream(
            end=EngineContextEnd())

    @staticmethod
    def _audio_chunk_to_engine_stream(data: bytes, offset=None, duration=None) -> EngineStream:
        return EngineStream(
            push=EventsPush(
                events=Events(
                    events=[Event(
                        audio=Audio(
                            body=data,
                            offset=offset,
                            duration=duration))],
                        lookahead=False)))

    def _filter_pushes(self, stream: Iterator[EngineStream]) -> Iterator[EventsPush]:
        for tidbit in stream:
            kind = tidbit.WhichOneof('payload')
            if 'start' == kind:
                self.finished.clear()
            elif 'end' == kind:
                self.finished.set()
            elif 'push' == kind:
                yield tidbit.push

    @staticmethod
    def _push_to_labels(push: EventsPush) -> Iterator[Label]:
        return (ev.label for ev in push.events.events if ev.WhichOneof('body') == 'label')

    @staticmethod
    def _filter_labels(labels: Iterator[Label]) -> Iterator[Label]:
        return (l for l in labels if l.WhichOneof('label') in {'item', 'plus'}) # filter out noise labels

    @staticmethod
    def _label_to_str(label: Label) -> str:
        kind = label.WhichOneof('label')
        if 'item' == kind:
            return label.item
        elif 'plus' == kind:
            return label.plus

    def send_audio_chunks(self, audio_chunks_provider: Iterator[bytes]) -> Iterator[Label]:
        #self._provider = audio_chunks_provider
        #self.completed_transription.clear()
        return map(NewtonEngine._label_to_str,
            NewtonEngine._filter_labels(
                chain(*map(NewtonEngine._push_to_labels,
                    self._filter_pushes(
                        self.stub.StreamingRecognize(
                            chain(
                                self._start(),
                                map(NewtonEngine._audio_chunk_to_engine_stream, audio_chunks_provider),
                                NewtonEngine._end()),
                            metadata=(('no-flow-control', 'true'),)))))))


def test_audio(path='ahoj-svete-8000-mono.wav'):
    w = read_wav(path)
    rate = w[0]
    data = w[1]
    position = 0
    chunk_size = int(0.125 * rate)
    while position != data.size:
        chunk = data[position:(position+chunk_size)]
        position = position + chunk.size
        yield bytes(chunk)


if __name__ == '__main__':
    with JwtAuthMetadataPlugin() as auth_plugin:
        conf = {
            'domain': DOMAIN,
            'rate': AudioFormat.AUDIO_SAMPLE_RATE_8000,
            'format': AudioFormat.AUDIO_SAMPLE_FORMAT_S16LE,
            'channels': AudioFormat.AUDIO_CHANNEL_LAYOUT_MONO}
        with NewtonEngine(conf, auth_plugin) as engine:
            print(''.join(engine.send_audio_chunks(test_audio())))
            #engine.finished.wait()
