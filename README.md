# Imoji MVP

Pencil sketch to a KakaoTalk-style 320x320 GIF emoticon generator with selectable 1-24 item output.

## Run

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set `GEMINI_API_KEY` and `MOCK_GENERATION=false` to call Gemini Vision and the image-reference sprite generator. Without a key, the app falls back to a local source-image motion preview so the full MVP flow can still be tested locally.

The production path first analyzes the uploaded sketch with Gemini Vision, then sends the uploaded image itself as `inlineData` reference input to `GEMINI_IMAGE_MODEL` for each selected situation. The model creates one sixteen-frame 4x4 sprite sheet, and `scripts/sprite_sheet_to_gif.py` splits, aligns, labels, and encodes it into a 320x320 GIF.

Useful generation settings:

```bash
GENERATION_MODE=image_reference_sprite
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_VISION_MODEL=gemini-2.5-flash
IMAGE_GENERATION_MAX_ATTEMPTS=6
IMAGE_GENERATION_RETRY_BASE_MS=15000
LABEL_TEXT_ENABLED=false
```

`LABEL_TEXT_ENABLED` defaults off — the character's pose and expression are expected to convey the situation, so generated GIFs are text-free. Set it to `1` to overlay the Korean text variant. When enabled, the labeler picks one position outside the union of all 16 frame foregrounds, or drops the label entirely if no overlap-free slot exists.

`GENERATION_MODE=source_motion` uses the uploaded image directly with local crop/transform motion only. It is intended as an API-key-free preview/fallback, not the production quality path. `GENERATION_MODE=imagen_sprite` keeps the older text-prompt sprite route for comparison.

The worker waits between image generation requests using `IMAGEN_REQUEST_GAP_MS` to reduce quota pressure. Temporary 503/high-demand responses are retried with exponential backoff using `IMAGE_GENERATION_MAX_ATTEMPTS` and `IMAGE_GENERATION_RETRY_BASE_MS`.

Situation labels, witty text variants, and action prompts are maintained in `data/situations.json`. `label` is the selectable situation name, while `textVariants` contains the actual Korean text overlaid on GIFs.

If you use conda, keep GIF conversion on the WSL Python where MoviePy is installed:

```bash
PYTHON_BIN=/usr/bin/python3
```

For real frame-to-GIF conversion, install Python dependencies:

```bash
pip install -r requirements.txt
```
