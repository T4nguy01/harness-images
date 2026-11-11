# AI images for Harness Maxxing

![banner](assets/banner.jpg)

Free AI image generation for [Harness Maxxing](https://harness-maxxing.com), powered by Cloudflare Workers AI
(FLUX.1 schnell and SDXL Lightning). No credit card, about 170 images a day on the free plan.

- **Page "AI images"**: prompt, model, steps, seed, size, a gallery with thumbnails, the daily quota gauge.
- **`genimage` command**: `genimage "a lighthouse at dawn, watercolor" --model sdxl --size 768x512`, usable by Claude in any session or script.
- **Skill** (optional) so Claude knows how and when to use it.

## Requirements

- A free Cloudflare account and an API token with the **Workers AI** permission.
- Settings -> Keys: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`.
- ImageMagick (`convert`) for the gallery thumbnails.

## What is sent, and where

Only your prompt and the generation settings go to `api.cloudflare.com` (with your token). Images come back and are
stored on your server in `<workspace>/images/YYYY-MM/`; the history (prompt, model, size, cost, path) is in the
extension's state directory. Nothing else leaves the server. This extension runs code on the server (`api.py`,
`genimage.py`, both short and stdlib only): read them first.

## Limits

Free plan: 10,000 neurons a day (reset 00:00 UTC), roughly 170 FLUX images at 1024x1024. Beyond that Cloudflare
refuses the request: the command stops with an error and nothing is billed. The counter shown is computed
locally (FLUX cost from Cloudflare's published prices, SDXL is an estimate); Cloudflare stays the authority.
FLUX schnell is always 1024x1024 and takes no seed; SDXL Lightning takes sizes from 256 to 1024 and a seed.

## Install

```bash
git clone https://github.com/T4nguy01/harness-images /root/maxxing/extensions/images
ln -s /root/maxxing/extensions/images/genimage.py /usr/local/bin/genimage
ln -s /root/maxxing/extensions/images/skill/genimage /root/maxxing/.claude/skills/genimage   # optional
```

Then Settings -> Pages -> Rescan, and add the two keys in Settings -> Keys. Note the skill adds about 300 characters
to the skills budget Claude reads in every prompt; skip it if `maxxing doctor` says you are near the limit
(the `CLAUDE.md` of your workspace can describe the command instead).

For an agent in a sandbox: give it the two keys (its `keys` list) and the domain `api.cloudflare.com`.

## Uninstall

```bash
rm /usr/local/bin/genimage /root/maxxing/.claude/skills/genimage
rm -rf /root/maxxing/extensions/images /root/maxxing/images   # the last one deletes your generated pictures
```

## License

MIT.
