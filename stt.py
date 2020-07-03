from __config__ import DOMAIN

from typing import Iterator

from threading import Event
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


class NewtonEngine():
    def __init__(self, config, creds_plugin: UnderlyingMetadataPlugin):
        self.config = config
        self.creds_plugin = creds_plugin
        self.finnished = Event()

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
    def _audio_chunk_to_event(data: bytes, offset=None, duration=None) -> EventsPush:
        return EventsPush(
            push=Events(
                events=[Event(
                    audio=Audio(
                        body=data,
                        offset=offset,
                        duration=duration))],
                    lookahead=False))

    def _filter_pushes(self, stream: Iterator[EngineStream]) -> Iterator[EventsPush]:
        for tidbit in stream:
            kind = tidbit.WhichOneof('payload')
            if 'start' == kind:
                self.finnished.clear()
            elif 'end' == kind:
                self.finnished.set()
            elif 'push' == kind:
                yield tidbit.push

    @staticmethod
    def _event_to_label(pushes: EventsPush) -> Iterator[Label]:
        return (ev for ev in pushes.events.events if ev.WhichOneof('body') == 'label')

    @staticmethod
    def _filter_labels(labels: Iterator[Label]) -> Iterator[Label]:
        return (l for l in labels if l.WhichOneOf('label') in {'item', 'plus'}) # filter out noise labels

    def send_audio_chunks(self, audio_chunks_provider: Iterator[bytes]):
        self._provider = audio_chunks_provider
        #self.completed_transription.clear()
        return map(NewtonEngine._filter_labels,
            map(NewtonEngine._event_to_label,
                map(self._filter_pushes,
                    self.stub.StreamingRecognize(
                        chain(
                            _start(),
                            map(NewtonEngine._audio_chunk_to_event, self._provider),
                            _end()),
                        metadata=(('no-flow-control', 'true'),)))))


if __name__ == '__main__':
    with JwtAuthMetadataPlugin() as auth_plugin:
        print("Waiting")
        auth_plugin.wait()
        conf = {
            'domain': DOMAIN,
            'rate': AudioFormat.AUDIO_SAMPLE_RATE_8000,
            'format': AudioFormat.AUDIO_SAMPLE_FORMAT_S16LE,
            'channels': AudioFormat.AUDIO_CHANNEL_LAYOUT_MONO}
        with NewtonEngine(conf, auth_plugin) as engine:
            #print(''.join(engine.send_audio_chunks())) #engine.send_audio_chunks()
            #engine.finnished.wait()
            pass
        print("Done")
