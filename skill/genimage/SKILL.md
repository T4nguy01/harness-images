---
name: genimage
description: Generate free AI images (Cloudflare FLUX / SDXL) with the `genimage` command. Use when asked to create, draw, illustrate or edit an image.
---

# genimage

1. Rewrite the request as an English prompt of 30-70 words, 1-2 natural sentences. Order: subject (precise, with action) > setting > medium/style > light > framing > mood. No negations (say "empty street", not "no people"), no quality-tag lists, light and framing always explicit, text in the image only if short (1-6 words, quoted), hide hands unless asked. SDXL likes comma keywords, FLUX full sentences.
2. Run `genimage "prompt" [--style NAME] [--ratio 16:9] [--model flux|sdxl|klein|dreamshaper] [--seed N] [-n 1-4] [--x2] [-o /abs/path.jpg]`.
   - `flux` (default): best value, 1024x1024 (cropped to `--ratio`), no seed. `klein`: finer, ~95/day. `sdxl`: fast, free sizes (`--size 768x512`), seed.
   - Styles (`genimage --styles`): photo portrait cinematic flat watercolor oil 3d isometric logo icon banner pixel anime sketch product cyberpunk exploded blueprint patent knolling cutaway macro marble glass liquid-metal clay papercut bronze gold floating splash vinyl-toy crochet miniature cross-stitch halftone stained-glass woodcarving dreamy god-rays neon-night golden-rim chibi kawaii ink-wash chrome-text crystal-text inflatable-text neon-text ice-text plant-text concrete-text fine-dining food-photo gelato drink-splash. Ratios: 1:1 16:9 9:16 3:2 2:3 4:3 3:4.
   - Recipes (`genimage --recipes`, 41 templates: movie poster, trading card, 9-view grid, album/book/magazine cover, billboard, product shots, toy packaging, crafts, light moods, food plating): `genimage --recipe movie-poster "a lone astronaut on a red desert"`. The argument is only the subject; the recipe sets the composition and the ratio. Combine with `--style` if useful.
   - Method (from the "IA Boss" guide): give a precise subject (replace every placeholder), set the ratio for the destination (4:5/3:4 Instagram, 9:16 Reel, 1:1 square), keep an object or packaging by editing a reference (`--from`, say what must not change), then refine with one targeted change at a time. FLUX draws long text badly: keep text to 1-6 quoted words or leave space and add the text afterwards. Check logos, dimensions and image rights before commercial use.
   - Edit an image: `--model dreamshaper --from image.jpg --strength 0.6` (0.3 subtle, 0.8 strong). Upscale: `--x2` or `genimage --upscale image.jpg`.
   - Without `-o` the image goes to `<workspace>/images/YYYY-MM/`. The command prints the absolute path on stdout: cite it.
3. `genimage --quota`: free daily budget 10,000 neurons (about 170 FLUX images, reset 00:00 UTC). Callers other than the page are capped (40/day by default, 20% of the budget kept for the page, 10/min); on refusal stop and tell the user, never loop.
4. Keys `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` come from Settings -> Keys. Never print them.
5. Show the result, then offer variations (`-n 4`, another style or ratio).
