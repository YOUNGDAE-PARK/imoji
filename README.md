# Imoji MVP

Pencil sketch to a KakaoTalk-style 320x320 GIF emoticon generator.

## Run

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set `GEMINI_API_KEY` and `MOCK_GENERATION=false` to call Gemini Vision and Imagen. Without a key, the app uses mock GIF generation so the full MVP flow can be tested locally.

The paid path first analyzes the uploaded sketch with Gemini Vision, then uses `imagen-4.0-fast-generate-001` to create four still frames and merges them into one GIF.
The worker waits between Imagen requests using `IMAGEN_REQUEST_GAP_MS` to stay under the default 10 requests/minute quota.

If you use conda, keep GIF conversion on the WSL Python where MoviePy is installed:

```bash
PYTHON_BIN=/usr/bin/python3
```

For real frame-to-GIF conversion, install Python dependencies:

```bash
pip install -r requirements.txt
```
