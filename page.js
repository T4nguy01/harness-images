export function mount(el, ctx) {
  const fr = ctx.lang === "fr";
  const T = (a, b) => (fr ? a : b);
  const flex = "display:flex;flex-wrap:wrap;gap:8px;align-items:center";
  el.innerHTML = `
    <div class="ui-page" style="max-width:1040px">
      <h1 class="ui-h1">${T("Images IA", "AI images")}</h1>
      <div class="ui-card"><div class="ui-stack" style="padding:16px;gap:12px">
        <textarea class="ui-textarea" name="prompt" rows="3" placeholder="${T("Décris l'image (l'anglais donne de meilleurs résultats) - Ctrl+Entrée pour générer", "Describe the image - Ctrl+Enter to generate")}"></textarea>
        <div style="${flex}">
          <select class="ui-select" name="model" style="width:auto;min-width:150px"></select>
          <select class="ui-select" name="style" style="width:auto"></select>
          <select class="ui-select" name="ratio" style="width:auto"></select>
          <input class="ui-input" name="steps" type="number" min="1" max="8" placeholder="steps" style="width:80px">
          <input class="ui-input" name="seed" type="number" placeholder="seed" style="width:110px">
          <select class="ui-select" name="n" style="width:auto"><option value="1">×1</option><option value="2">×2</option><option value="4">×4</option></select>
          <label class="ui-check" style="white-space:nowrap;display:inline-flex;gap:6px;align-items:center"><input type="checkbox" name="x2"> ×2 ${T("agrandi", "upscale")}</label>
        </div>
        <div style="${flex}" data-src hidden>
          <span class="ui-small">${T("Image source :", "Source image:")} <b data-srcname></b></span>
          <label class="ui-small">${T("force", "strength")} <input class="ui-input" name="strength" type="number" min="0.1" max="1" step="0.05" value="0.65" style="width:80px"></label>
          <button class="ui-btn ui-sm ui-ghost" name="nosrc">${T("Retirer", "Remove")}</button>
        </div>
        <div style="${flex}"><button class="ui-btn" name="go">${T("Générer", "Generate")}</button><span style="flex:1"></span>
          <button class="ui-btn ui-sm ui-outline" name="cfg">${T("Réglages", "Settings")}</button></div>
        <div class="ui-small ui-muted" data-q></div>
        <div class="ui-progress" data-bar><div style="width:0%"></div></div>
        <div class="ui-callout ui-error" data-err hidden></div>
        <div class="ui-callout ui-info" data-ok hidden></div>
        <div class="ui-stack" data-cfg hidden style="gap:8px">
          <label class="ui-check" style="white-space:nowrap;display:inline-flex;gap:6px;align-items:center"><input type="checkbox" name="c_fallback"> ${T("Secours AI Horde quand Cloudflare échoue (vos prompts partent chez des machines bénévoles, qualité moyenne, 512² max, ~1 min)", "AI Horde fallback when Cloudflare fails (prompts go to volunteers' machines, average quality, 512² max, ~1 min)")}</label>
          <div style="${flex}"><label class="ui-small">${T("Plafond par agent/jour", "Cap per agent/day")} <input class="ui-input" name="c_caller_daily_max" type="number" min="0" style="width:80px"></label>
          <label class="ui-small">${T("Part réservée à la page (%)", "Share kept for the page (%)")} <input class="ui-input" name="c_human_reserve_pct" type="number" min="0" max="90" style="width:80px"></label>
          <label class="ui-small">${T("Max par minute", "Max per minute")} <input class="ui-input" name="c_max_per_minute" type="number" min="1" style="width:80px"></label>
          <button class="ui-btn ui-sm" name="savecfg">${T("Enregistrer", "Save")}</button></div>
        </div>
      </div></div>
      <div style="${flex};margin-top:20px"><h2 class="ui-h2" style="margin:0">${T("Galerie", "Gallery")}</h2><span style="flex:1"></span>
        <input class="ui-input" name="search" placeholder="${T("Rechercher un prompt", "Search prompts")}" style="width:200px">
        <label class="ui-check" style="white-space:nowrap;display:inline-flex;gap:6px;align-items:center"><input type="checkbox" name="favonly"> ★ ${T("favoris", "favorites")}</label>
        <button class="ui-btn ui-sm ui-secondary" name="zip">${T("Zip des favoris", "Zip favorites")}</button></div>
      <div class="ui-grid" data-grid style="margin-top:12px"></div>
      <p class="ui-muted" data-empty hidden>${T("Aucune image pour l'instant.", "No image yet.")}</p>
    </div>`;
  const $ = (s) => el.querySelector(s);
  const q = (n) => el.querySelector(`[name=${n}]`);
  const opt = (v, t) => Object.assign(document.createElement("option"), { value: v, textContent: t });
  let st = { models: {} }, source = null, timer;
  const quotaLine = (k) => {
    const by = Object.entries(k.by_caller || {}).map(([a, n]) => `${a} ${n}`).join(" · ");
    $("[data-q]").textContent = T(`Gratuit aujourd'hui : ${k.used} / ${k.limit} neurons, ~${k.approx_images_left} images restantes (remise à zéro 00:00 UTC)`,
      `Free today: ${k.used} / ${k.limit} neurons, ~${k.approx_images_left} images left (resets 00:00 UTC)`) + (by ? " — " + by : "");
    $("[data-bar] div").style.width = Math.min(100, (k.used / k.limit) * 100) + "%";
  };
  const say = (node, msg) => { node.textContent = msg || ""; node.hidden = !msg; };
  const btn = (label, cls, fn) => { const b = document.createElement("button"); b.className = "ui-btn ui-sm " + cls; b.textContent = label; b.onclick = fn; return b; };
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
    p.textContent = it.prompt.length > 120 ? it.prompt.slice(0, 120) + "…" : it.prompt;
    const meta = document.createElement("div");
    meta.className = "ui-small ui-muted";
    meta.textContent = `${it.model}${it.style ? " · " + it.style : ""} · ${it.w}×${it.h} · ${it.steps} steps${it.seed != null ? " · seed " + it.seed : ""}${it.provider === "horde" ? " · Horde" : ""}`;
    const path = document.createElement("code");
    path.className = "ui-code ui-small";
    path.style.cssText = "display:block;word-break:break-all;margin-top:4px";
    path.textContent = it.path;
    const row = document.createElement("div");
    row.style.cssText = flex + ";margin-top:6px";
    row.append(
      btn(it.fav ? "★" : "☆", "ui-ghost", async () => { await ctx.api("fav/" + it.id, { method: "POST", body: { fav: !it.fav } }); refresh(); }),
      btn(T("Réutiliser", "Reuse"), "ui-secondary", () => { q("prompt").value = it.prompt; if (st.models[it.model]) q("model").value = it.model; if (it.seed != null) q("seed").value = it.seed; sync(); window.scrollTo({ top: 0, behavior: "smooth" }); }),
      btn(T("Retoucher", "Edit"), "ui-secondary", () => { source = it; q("model").value = "dreamshaper"; $("[data-srcname]").textContent = it.id; $("[data-src]").hidden = false; sync(); window.scrollTo({ top: 0, behavior: "smooth" }); }),
      btn("×2", "ui-outline", async () => { const r = await ctx.api("upscale/" + it.id, { method: "POST" }); say($("[data-ok]"), T("Agrandi : ", "Upscaled: ") + r.path); }),
      btn(T("Supprimer", "Delete"), "ui-danger", async () => { if (confirm(T("Supprimer cette image ?", "Delete this image?"))) { await ctx.api("item/" + it.id + (it.fav ? "?force=1" : ""), { method: "DELETE" }); refresh(); } }));
    info.append(p, meta, path, row);
    c.append(img, info);
    return c;
  };
  const render = (s) => {
    st = Object.assign(st, s);
    if (s.quota) quotaLine(s.quota);
    if (s.items) {
      $("[data-grid]").replaceChildren(...s.items.map(card));
      $("[data-empty]").hidden = !!s.items.length;
    }
  };
  const refresh = async () => render(await ctx.api("status?q=" + encodeURIComponent(q("search").value) + (q("favonly").checked ? "&fav=1" : "")));
  const sync = () => {
    const m = st.models[q("model").value] || {};
    q("seed").disabled = !m.seed;
    q("ratio").title = m.sized ? "" : T("FLUX : recadrage au ratio", "FLUX: cropped to the ratio");
    $("[data-src]").hidden = !source;
  };
  ctx.api("status").then((s) => {
    render(s);
    q("model").replaceChildren(...Object.entries(s.models).map(([k, m]) => opt(k, m.label)));
    q("style").replaceChildren(opt("", T("Style : aucun", "Style: none")), ...s.styles.map((x) => opt(x, x)));
    q("ratio").replaceChildren(...s.ratios.map((x) => opt(x, x)));
    q("c_fallback").checked = s.config.fallback;
    for (const k of ["caller_daily_max", "human_reserve_pct", "max_per_minute"]) q("c_" + k).value = s.config[k];
    sync();
  });
  q("model").addEventListener("change", sync);
  q("nosrc").onclick = () => { source = null; sync(); };
  q("cfg").onclick = () => { $("[data-cfg]").hidden = !$("[data-cfg]").hidden; };
  q("savecfg").onclick = async () => {
    const cfg = { fallback: q("c_fallback").checked };
    for (const k of ["caller_daily_max", "human_reserve_pct", "max_per_minute"]) cfg[k] = Number(q("c_" + k).value);
    await ctx.api("config", { method: "PUT", body: cfg });
    say($("[data-ok]"), T("Réglages enregistrés.", "Settings saved."));
  };
  q("zip").onclick = async () => {
    const ids = (st.items || []).filter((i) => i.fav).map((i) => i.id);
    try { say($("[data-ok]"), T("Archive : ", "Archive: ") + (await ctx.api("zip", { method: "POST", body: { ids } })).path); } catch (e) { say($("[data-err]"), e.message); }
  };
  q("search").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(refresh, 300); });
  q("favonly").addEventListener("change", refresh);
  q("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) q("go").click(); });
  q("go").addEventListener("click", async () => {
    const prompt = q("prompt").value.trim();
    if (!prompt) return;
    const b = q("go");
    b.disabled = true; say($("[data-err]"), ""); say($("[data-ok]"), ""); b.textContent = T("Génération…", "Generating…");
    try {
      await ctx.api("generate", { method: "POST", body: { prompt, model: q("model").value, style: q("style").value, ratio: q("ratio").value,
        steps: Number(q("steps").value) || null, seed: q("seed").value === "" ? null : Number(q("seed").value), n: Number(q("n").value),
        x2: q("x2").checked, source: source && source.id, strength: Number(q("strength").value) } });
      await refresh();
    } catch (e) {
      say($("[data-err]"), (e && e.message) || String(e));
      refresh();
    } finally {
      b.disabled = false; b.textContent = T("Générer", "Generate");
    }
  });
}
