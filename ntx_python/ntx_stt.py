from typing import Iterator, Any, Tuple
from threading import Event as ThreadEvent
from itertools import chain

import grpc
from ntx_protobuf.engine_pb2 import EngineStream, EngineContext, EngineContextStart, EngineContextEnd, EventsPush, Events, Event, Lexicon, AudioFormat
import ntx_protobuf.engine_pb2_grpc as engine_pb2_grpc

from ntx_python.ntx_auth_metadata_plugin import NewtonAuthMetadataPlugin, UnderlyingMetadataPlugin, BasicNewtonMetadataPlugin

import logging, sys
logging.basicConfig(stream=sys.stderr, level=logging.INFO)


#Python is a little different – the Python compiler generates a module with a static descriptor of each message type in your .proto, which is then used with a metaclass to create the necessary Python data access class at runtime.
#pylint: disable=no-member
ChannelLayout = AudioFormat.ChannelLayout; SampleFormat = AudioFormat.SampleFormat; SampleRate = AudioFormat.SampleRate; AutoDetect = AudioFormat.AutoDetect; PCM = AudioFormat.PCM; Header = AudioFormat.Header
V2TConfig = EngineContext.V2TConfig; VADConfig = EngineContext.VADConfig; PNCConfig = EngineContext.PNCConfig; PPCConfig = EngineContext.PPCConfig; AudioChannel = EngineContext.AudioChannel
LexItem = Lexicon.LexItem; MainItem = Lexicon.MainItem; NoiseItem = Lexicon.NoiseItem; UserItem = Lexicon.UserItem
Meta = Event.Meta; Audio = Event.Audio; Label = Event.Label; Timestamp = Event.Timestamp


# Similar to Haskell's join :: Monad m => m (m a) -> m a
# Lazy version of itertools.chain(*gen_of_gens)
def join(gen_of_gens: Iterator[Iterator[Any]]) -> Iterator[Any]:
    for gen in gen_of_gens:
        yield from gen


class UnderlyingNewtonEngine:
    def __init__(self, config, creds_plugin: UnderlyingMetadataPlugin):
        self.config = config
        self.creds_plugin = creds_plugin
        self.finished = ThreadEvent()

    def __enter__(self):
        ssl_cred = grpc.ssl_channel_credentials()  # Default from Mozilla
        call_cred = grpc.metadata_call_credentials(self.creds_plugin)
        composed_creds = grpc.composite_channel_credentials(ssl_cred, call_cred)
        self._channel = grpc.secure_channel(f'{self.config["domain"]}:443', composed_creds)
        self.stub = engine_pb2_grpc.EngineServiceStub(self._channel)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._channel.close()

    def _start(self):
        if self.config['pnc'] and self.config['ppc']:
            v2t = V2TConfig(withPNC=PNCConfig(), withPPC=PPCConfig())
        elif self.config['pnc']:
            v2t = V2TConfig(withPNC=PNCConfig())
        elif self.config['ppc']:
            v2t = V2TConfig(withPPC=PPCConfig())
        else:
            v2t = V2TConfig()
        yield EngineStream(
            start=EngineContextStart(
                context=EngineContext(
                    v2t=v2t,
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

    def _audio_chunk_to_engine_stream(self, data: bytes, offset=None, duration=None) -> EngineStream:
        return EngineStream(
            push=EventsPush(
                events=Events(
                    events=[Event(
                        audio=Audio(
                            body=data,
                            offset=offset,
                            duration=duration))],
                        lookahead=self.config['lookahead'])))

    def _filter_pushes(self, stream: Iterator[EngineStream]) -> Iterator[EventsPush]:
        for tidbit in stream:
            kind = tidbit.WhichOneof('payload')
            if 'start' == kind:
                self.finished.clear()
            elif 'end' == kind:
                self.finished.set()
            elif 'push' == kind:
                yield tidbit.push

    def _push_to_decorated_labels(self, push: EventsPush) -> Iterator[Tuple[Label, Meta, Timestamp]]:
        for event in push.events.events:
            kind = event.WhichOneof('body')
            if 'meta' == kind and event.meta.WhichOneof('body') == 'confidence':
                self._last_meta_event_with_confidence = event.meta
            elif 'timestamp' == kind:
                self._last_timestamp = event.timestamp
            elif 'label' == kind:
                yield event.label, self._last_meta_event_with_confidence, self._last_timestamp

        return (ev.label for ev in push.events.events if ev.WhichOneof('body') == 'label')

    @staticmethod
    def _filter_decorated_labels(labels: Iterator[Tuple[Label, Meta, Timestamp]]) -> Iterator[Tuple[Label, Meta, Timestamp]]:
        return (l for l in labels if l[0].WhichOneof('label') in {'item', 'plus'}) # filter out noise labels

    def send_audio_chunks(self, audio_chunks_provider: Iterator[bytes]) -> Iterator[Tuple[Label, Meta, Timestamp]]:
        self._last_meta_event_with_confidence = None
        self._last_timestamp = None
        return UnderlyingNewtonEngine._filter_decorated_labels(
                    join(map(self._push_to_decorated_labels,
                        self._filter_pushes(
                            self.stub.StreamingRecognize(
                                chain(
                                    self._start(),
                                    map(self._audio_chunk_to_engine_stream, audio_chunks_provider),
                                    UnderlyingNewtonEngine._end()),
                                metadata=(('no-flow-control', 'true'),))))))


def label_to_str(label: Label) -> str:
    kind = label.WhichOneof('label')
    if 'item' == kind:
        return label.item
    elif 'plus' == kind:
        return label.plus


def to_strings(decorated_labels: Iterator[Tuple[Label, Meta, Timestamp]]) -> Iterator[str]:
    return map(lambda t: label_to_str(t[0]), decorated_labels)


class NewtonEngine:
    def __init__(self, conf):
        self.conf = {
            'rate': AudioFormat.AUDIO_SAMPLE_RATE_8000,
            'format': AudioFormat.AUDIO_SAMPLE_FORMAT_S16LE,
            'channels': AudioFormat.AUDIO_CHANNEL_LAYOUT_MONO,
            **conf}
        self._stream = self._create()
        next(self._stream)  # Priming, initializing `with` objects

    def recognize(self, feeder: Iterator[bytes]) -> Iterator[str]:
        responder = self._stream.send(feeder)
        next(self._stream)  # Advancing back to arguments
        return responder

    def _create(self):
        with (NewtonAuthMetadataPlugin(self.conf['auth'])
                if isinstance(self.conf['auth'], dict)
                else BasicNewtonMetadataPlugin(self.conf['auth'])) as self._auth_plugin:
            with UnderlyingNewtonEngine(self.conf, self._auth_plugin) as self._engine:
                self._auth_plugin.wait()  # Obtaining access
                while True:
                    yield self._engine.send_audio_chunks((yield))

    def stop(self):
        self._stream.close()

    def __del__(self):
        self.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.stop()
