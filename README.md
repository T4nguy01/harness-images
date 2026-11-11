# AI images for Harness Maxxing

![banner](assets/banner.jpg)

Free AI image generation for [Harness Maxxing](https://harness-maxxing.com), powered by Cloudflare Workers AI
(FLUX.1 schnell and SDXL Lightning). No credit card, about 170 images a day on the free plan.

- **Page "AI images"**: prompt, 4 models, 16 style presets, ratios, steps, seed, 1-4 variants, optional 2x upscale, image-to-image
  ("Edit"), a gallery with thumbnails, favorites, prompt search, zip of favorites, the daily quota gauge and the settings below.
- **`genimage` command**: `genimage "a lighthouse at dawn" --style watercolor --ratio 16:9`, usable by Claude in any session, agent or script.
- **Skill** (optional) with a prompt-writing guide, so Claude turns a short request into an effective English prompt.
- **Guard rails for agents**: a daily cap per caller, a share of the quota kept for the page, a per-minute limit.
- **Optional fallback** (off by default): free AI Horde when Cloudflare is out of quota or fails.

## Requirements

- A free Cloudflare account and an API token with the **Workers AI** permission.
- Settings -> Keys: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`.
- ImageMagick (`convert`) for the gallery thumbnails.

## What is sent, and where

Only your prompt and the generation settings go to `api.cloudflare.com` (with your token); in image-to-image mode the source image is sent there too. If you switch on the **AI Horde fallback** in the page settings, the prompt also goes to `aihorde.net` (volunteers' machines, anonymous, 512x512 at most) when Cloudflare fails; the result is then downloaded from a URL chosen by Horde. It is off by default. Images come back and are
stored on your server in `<workspace>/images/YYYY-MM/`; the history (prompt, model, size, cost, path) is in the
extension's state directory (`GENIMAGE_STATE` to change it; `MAXXING_WORKSPACE` sets `<workspace>`). Nothing else leaves the server. This extension runs code on the server (`api.py`,
`genimage.py`, both short and stdlib only): read them first.

## Limits

Free plan: 10,000 neurons a day (reset 00:00 UTC), roughly 170 FLUX images at 1024x1024. Beyond that Cloudflare
refuses the request: the command stops with an error and nothing is billed. The counter shown is computed
locally (FLUX cost from Cloudflare's published prices, SDXL is an estimate); Cloudflare stays the authority.
FLUX schnell is always 1024x1024 (cropped to the ratio) and takes no seed; SDXL Lightning, FLUX.2 klein and DreamShaper take sizes from 256 to 1024; SDXL and DreamShaper take a seed. FLUX.2 klein costs more (estimated ~105 neurons at 1024x1024). The FLUX.1 cost comes from Cloudflare's price list; the others are estimates.

## Install

```bash
git clone https://github.com/T4nguy01/harness-images <workspace>/extensions/images
ln -s <workspace>/extensions/images/genimage.py /usr/local/bin/genimage
ln -s <workspace>/extensions/images/skill/genimage <workspace>/.claude/skills/genimage   # optional
```

Then Settings -> Pages -> Rescan, and add the two keys in Settings -> Keys. Note the skill adds about 300 characters
to the skills budget Claude reads in every prompt; skip it if `maxxing doctor` says you are near the limit
(the `CLAUDE.md` of your workspace can describe the command instead).

For an agent in a sandbox: give it the two keys (its `keys` list) and the domain `api.cloudflare.com`.

## Uninstall

```bash
rm /usr/local/bin/genimage <workspace>/.claude/skills/genimage
rm -rf <workspace>/extensions/images <workspace>/images   # the last one deletes your generated pictures
```

## License

MIT.
