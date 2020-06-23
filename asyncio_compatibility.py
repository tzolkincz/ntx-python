# https://stackoverflow.com/a/55595696
import sys, asyncio

def run(aw):
    if sys.version_info >= (3, 7):
        #pylint: disable=no-member
        return asyncio.run(aw)

    # Emulate asyncio.run() on older versions
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(aw)
    finally:
        loop.close()
        asyncio.set_event_loop(None)