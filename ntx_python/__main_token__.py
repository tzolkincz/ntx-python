from ntx_python.ntx_auth_metadata_plugin import NewtonAuthMetadataPlugin, UnderlyingMetadataPlugin
import asyncio


def main_with_async():
    from ntx_python.__config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL
    m = NewtonAuthMetadataPlugin({
        'audience': AUDIENCE,
        'username': USERNAME,
        'password': PASSWORD,
        'id': ID,
        'label': LABEL})
    u = UnderlyingMetadataPlugin(m)
    all_async = asyncio.wait({u.async_wait(), m.purvey()}, return_when=asyncio.FIRST_COMPLETED)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(all_async)


def main():
    from ntx_python.__config__ import AUDIENCE, USERNAME, PASSWORD, ID, LABEL
    with NewtonAuthMetadataPlugin({
        'daemon': False,
        'audience': AUDIENCE,
        'username': USERNAME,
        'password': PASSWORD,
        'id': ID,
        'label': LABEL
    }) as u:
        u.wait()


if __name__=='__main__':
    #main_with_async()
    main()
