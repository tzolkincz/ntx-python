from ntx_python.ntx_stt import NewtonEngine, to_strings
from scipy.io.wavfile import read as read_wav
import sys


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
    sys.argv = sys.argv[1:]
    from ntx_python.__config__ import DOMAIN, AUDIENCE, USERNAME, PASSWORD, ID, LABEL, TOKEN
    auth_conf = {
        'daemon': False,  # set to True if you're not using `with NewtonEngineWrapped(conf) ...`
        'audience': AUDIENCE,
        'username': USERNAME,
        'password': PASSWORD,
        'id': ID,
        'label': LABEL}
    conf = {
        'pnc': False,
        'ppc': True,
        'lookahead': False,
        'domain': DOMAIN,
        'auth': TOKEN  # static token #auth_conf
    }
    with NewtonEngine(conf) as engine:
        for txt in to_strings(engine.recognize(test_audio(sys.argv[0]))):
            print(txt, flush=True, end='')
        print()
