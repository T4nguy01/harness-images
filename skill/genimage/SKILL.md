---
name: genimage
description: Generate free AI images (Cloudflare Workers AI, FLUX / SDXL) with the `genimage` command. Use when asked to create, draw or illustrate an image.
---

# genimage

1. Write the prompt in English, detailed: subject, style, light, framing, mood.
2. Run `genimage "prompt" [-o /abs/path/image.jpg] [--model flux|sdxl] [--steps N] [--seed N] [--size 768x512]`.
   - `flux` (default): best quality, always 1024x1024, no seed. `sdxl`: fast, free sizes (256-1024), seed.
   - Without `-o` the image goes to `<workspace>/images/YYYY-MM/`. The command prints the absolute path: cite it.
3. `genimage --quota` shows the free daily budget (10,000 neurons, about 170 FLUX images, reset 00:00 UTC).
   Over quota the command fails; it never bills.
4. Keys `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are read from Settings -> Keys. Never print them.
5. Show the user the result and offer variations (another seed with sdxl, other wording with flux).
