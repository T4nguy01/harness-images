export function mount(el, ctx) {
  const fr = ctx.lang === "fr";
  const T = (a, b) => (fr ? a : b);
  el.innerHTML = `
    <div class="ui-page" style="max-width:980px">
      <h1 class="ui-h1">${T("Images IA", "AI images")}</h1>
      <div class="ui-card"><div class="ui-stack" style="padding:16px;gap:12px">
        <textarea class="ui-textarea" name="prompt" rows="3" placeholder="${T("Décris l'image (l'anglais donne de meilleurs résultats) - Ctrl+Entrée pour générer", "Describe the image - Ctrl+Enter to generate")}"></textarea>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <select class="ui-select" name="model" style="width:auto;min-width:150px"></select>
          <input class="ui-input" name="steps" type="number" min="1" max="8" placeholder="steps" style="width:90px">
          <input class="ui-input" name="seed" type="number" placeholder="seed" style="width:110px">
          <select class="ui-select" name="size" style="width:auto;min-width:150px"><option value="1024x1024">1024×1024</option><option value="768x512">768×512</option><option value="512x768">512×768</option><option value="1024x576">1024×576</option><option value="512x512">512×512</option></select>
          <span style="flex:1"></span>
          <button class="ui-btn" name="go">${T("Générer", "Generate")}</button>
        </div>
        <div class="ui-small ui-muted" data-q></div>
        <div class="ui-progress" data-bar><div style="width:0%"></div></div>
        <div class="ui-callout ui-error" data-err hidden></div>
      </div></div>
      <h2 class="ui-h2" style="margin-top:20px">${T("Galerie", "Gallery")}</h2>
      <div class="ui-grid" data-grid></div>
      <p class="ui-muted" data-empty hidden>${T("Aucune image pour l'instant.", "No image yet.")}</p>
    </div>`;
  const $ = (s) => el.querySelector(s);
  const q = (n) => el.querySelector(`[name=${n}]`);
  let models = {};
  const quotaLine = (k) => {
    $("[data-q]").textContent = T(`Gratuit aujourd'hui : ${k.used} / ${k.limit} neurons utilisés, ~${k.approx_images_left} images restantes (remise à zéro 00:00 UTC)`,
      `Free today: ${k.used} / ${k.limit} neurons used, ~${k.approx_images_left} images left (resets 00:00 UTC)`);
    $("[data-bar] div").style.width = Math.min(100, (k.used / k.limit) * 100) + "%";
  };
  const card = (it) => {
    const c = document.createElement("div");
    c.className = "ui-card";
    const img = document.createElement("img");
    img.style.cssText = "width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px 8px 0 0;background:var(--muted)";
    img.alt = it.prompt;
    ctx.api("thumb/" + it.id).then((r) => (img.src = r.src)).catch(() => {});
    const info = document.createElement("div");
    info.style.padding = "10px";
    const p = document.createElement("div");
    p.className = "ui-small";
    p.textContent = it.prompt.length > 110 ? it.prompt.slice(0, 110) + "…" : it.prompt;
    const meta = document.createElement("div");
    meta.className = "ui-small ui-muted";
    meta.textContent = `${it.model} · ${it.w}×${it.h} · ${it.steps} steps${it.seed != null ? " · seed " + it.seed : ""}`;
    const path = document.createElement("code");
    path.className = "ui-code ui-small";
    path.style.cssText = "display:block;word-break:break-all;margin-top:4px";
    path.textContent = it.path;
    const row = document.createElement("div");
    row.className = "ui-row";
    row.style.marginTop = "6px";
    const reuse = document.createElement("button");
    reuse.className = "ui-btn ui-sm ui-secondary";
    reuse.textContent = T("Réutiliser", "Reuse");
    reuse.onclick = () => { q("prompt").value = it.prompt; q("model").value = it.model; window.scrollTo({ top: 0, behavior: "smooth" }); };
    const del = document.createElement("button");
    del.className = "ui-btn ui-sm ui-danger";
    del.textContent = T("Supprimer", "Delete");
    del.onclick = async () => { if (confirm(T("Supprimer cette image ?", "Delete this image?"))) render(await ctx.api("item/" + it.id, { method: "DELETE" })); };
    row.append(reuse, del);
    info.append(p, meta, path, row);
    c.append(img, info);
    return c;
  };
  const render = (s) => {
    if (s.quota) quotaLine(s.quota);
    if (s.items) {
      $("[data-grid]").replaceChildren(...s.items.map(card));
      $("[data-empty]").hidden = !!s.items.length;
    }
  };
  ctx.api("status").then((s) => {
    models = s.models;
    q("model").replaceChildren(...Object.entries(models).map(([k, m]) => Object.assign(document.createElement("option"), { value: k, textContent: m.label })));
    render(s);
    sync();
  });
  const sync = () => { const m = models[q("model").value] || {}; q("size").disabled = !m.sized; q("seed").disabled = !m.seed; };
  q("model").addEventListener("change", sync);
  q("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) q("go").click(); });
  q("go").addEventListener("click", async () => {
    const prompt = q("prompt").value.trim();
    if (!prompt) return;
    const [width, height] = q("size").value.split("x").map(Number);
    const btn = q("go"), err = $("[data-err]");
    btn.disabled = true; err.hidden = true; btn.textContent = T("Génération…", "Generating…");
    try {
      await ctx.api("generate", { method: "POST", body: { prompt, model: q("model").value, steps: Number(q("steps").value) || null, seed: q("seed").value === "" ? null : Number(q("seed").value), width, height } });
      render(await ctx.api("status"));
    } catch (e) {
      err.textContent = (e && e.message) || String(e);
      err.hidden = false;
    } finally {
      btn.disabled = false; btn.textContent = T("Générer", "Generate");
    }
  });
}
