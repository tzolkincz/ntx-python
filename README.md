# Configuration for examples

Create `ntx_python/__config__.py` in the root directory and fill it like this:

```
AUDIENCE='https://example.com' # Without the root slash in the path part
USERNAME='your-username'
PASSWORD='your-password'

ID='id-of-service'
LABEL='label-for-service'
DOMAIN='example.com'

TOKEN='static-token-here' # The trascription example is setup to use the static token
```

# Running the examples

## Transcription

`python -m ntx_python ahoj-svete-8000-mono.wav`

## Token

`python -m ntx_python.__main_token__`
