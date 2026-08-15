/* SpyBusiness — shell : routing, thème, pages, chat RAG. */

/* Icône assistant IA — tête de robot moderne et colorée (pas monochrome currentColor :
   dégradé blanc/gris pour un rendu "3D" doux, yeux bleus lumineux, antenne rouge accent).
   Auto-suffisante (fonctionne sur n'importe quel fond, clair ou sombre). */
const AI_ICON_SVG = '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style="width:74%;height:74%">'
  + '<defs>'
  + '<linearGradient id="rh-head" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#FFFFFF"/><stop offset="100%" stop-color="#D7DBE3"/></linearGradient>'
  + '<linearGradient id="rh-eye" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#6FEFFF"/><stop offset="100%" stop-color="#1FA6FF"/></linearGradient>'
  + '</defs>'
  + '<line x1="16" y1="3" x2="16" y2="7" stroke="#C3C9D4" stroke-width="1.7" stroke-linecap="round"/>'
  + '<circle cx="16" cy="2.4" r="1.7" fill="#FF4D62"/>'
  + '<rect x="3.3" y="14" width="2.7" height="6.4" rx="1.35" fill="#C3C9D4"/>'
  + '<rect x="26" y="14" width="2.7" height="6.4" rx="1.35" fill="#C3C9D4"/>'
  + '<rect x="6" y="8" width="20" height="17.5" rx="6.2" fill="url(#rh-head)" stroke="#AEB4BF" stroke-width="0.6"/>'
  + '<rect x="8.3" y="10.4" width="15.4" height="9.4" rx="4.2" fill="#EEF1F5"/>'
  + '<circle cx="12.2" cy="16.8" r="2.25" fill="url(#rh-eye)"/>'
  + '<circle cx="19.8" cy="16.8" r="2.25" fill="url(#rh-eye)"/>'
  + '<circle cx="12.95" cy="16.05" r="0.6" fill="#ffffff" opacity=".9"/>'
  + '<circle cx="20.55" cy="16.05" r="0.6" fill="#ffffff" opacity=".9"/>'
  + '<rect x="12.4" y="20.9" width="7.2" height="1.8" rx="0.9" fill="#C7CCD6"/>'
  + '</svg>';

/* ─── thème ─────────────────────────────────────────────────────────── */
function setTheme(t){
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("sb-theme", t);
  // .theme-ic (classe) plutôt qu'un ID unique : plusieurs boutons thème coexistent
  // (app principale + écrans de connexion/disclaimer, avant que #theme-ic n'existe).
  document.querySelectorAll(".theme-ic").forEach(el => { el.textContent = t==="dark" ? "☀" : "☾"; });
  if(window.__redraw) setTimeout(window.__redraw, 60);
}
function toggleTheme(){ setTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark"); }

/* ─── navigation mobile : tiroir off-canvas ───────────────────────────── */
function toggleNav(){
  const shell=document.querySelector(".shell");
  if(window.innerWidth<=900){
    shell.classList.toggle("nav-open");                 // tiroir mobile
  }else{
    shell.classList.toggle("collapsed");                // repli bureau
    setTimeout(()=> window.dispatchEvent(new Event("resize")), 260);
  }
}
function closeNav(){ const s=document.querySelector(".shell"); if(s) s.classList.remove("nav-open"); }

/* ─── count-up animation ─────────────────────────────────────────────── */
function countUp(el, to, dur=1500, fmt=v=>Math.round(v).toLocaleString("fr-FR")){
  const t0=performance.now();
  (function f(t){
    const p=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-p,3);
    el.textContent=fmt(to*e);
    if(p<1) requestAnimationFrame(f);
  })(performance.now());
}
function runCounts(scope){
  scope.querySelectorAll("[data-count]").forEach(el=>{
    const dec=el.dataset.dec, suf=el.dataset.suf||"";
    countUp(el, +el.dataset.count, 1500,
      v=>(dec ? v.toFixed(+dec).replace(".",",") : Math.round(v).toLocaleString("fr-FR"))+suf);
  });
}

/* ─── PAGES ──────────────────────────────────────────────────────────── */
const PAGES = {
  apercu:   { title:"Santé financière",    render: pageApercu   },
  analyse:  { title:"Analyse",            render: pageAnalyse  },
  strategie:{ title:"Stratégie",          render: pageStrategie},
  stratop:  { title:"Stratégie opérationnelle", render: pageStratOp },
  rapports: { title:"Rapports",           render: pageRapports },
  cb:       { title:"Benchmark Concurrentiel",render: pageCB      },
  chat:     { title:"Chat Intelligence",  render: pageChat, full:true },
  admin:    { title:"Administration",     render: pageAdmin    },
};

// Correspondance onglet -> section de droits (cf. dash_app/securite.py). « rapports » n'a pas
// de section propre : il n'expose que ce que les autres pages montrent déjà.
const SECTION_DE_PAGE = {
  apercu:"apercu", analyse:"analyse", cb:"cb", strategie:"strategie",
  stratop:"stratop", chat:"chat", admin:"admin",
};

/* ════════════ VUE D'ENSEMBLE ════════════════════════════════════════ */

// ── Portrait compétitif — légende générée par l'agent IA ────────────────────
function radarInsight(agd) {
  if (!agd || !agd.dimensions) return "";
  const col  = s => s >= 70 ? "#22C55E" : s >= 50 ? "#FFB020" : "#FF4D4D";
  const dims = agd.dimensions;
  const scoreGlobal = Math.round(dims.reduce((a, d) => a + d.score, 0) / dims.length);

  const verdict = scoreGlobal >= 70
    ? `<b style="color:#22C55E">Score global ${scoreGlobal}/100 — ${RADAR_BANK||"SGCI"} au-dessus de la moyenne marché.</b>`
    : scoreGlobal >= 50
    ? `Score global ${scoreGlobal}/100 — ${RADAR_BANK||"SGCI"} dans la moyenne marché.`
    : `<b style="color:#FF4D4D">Score global ${scoreGlobal}/100 — ${RADAR_BANK||"SGCI"} sous la moyenne marché.</b>`;

  return `<div style="padding:10px 14px;font:500 10.5px/1.65 var(--sans);color:var(--muted);border-top:1px solid var(--line-2);margin-top:4px">
    <div style="font:700 9px var(--sans);text-transform:uppercase;letter-spacing:.1em;color:var(--faint);margin-bottom:7px">Analyse stratégique · 100 = meilleur · 50 = moyenne · 0 = dernier · dimensions choisies par l'agent</div>
    ${dims.map(d => `<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:4px">
      <span style="font:700 11px JetBrains Mono,monospace;color:${col(d.score)};width:32px;flex-shrink:0;text-align:right">${d.score}</span>
      <span style="color:var(--faint);flex-shrink:0;font-size:10px">/100</span>
      <span><b style="color:var(--ink)">${d.label}</b> — ${d.explication}</span>
    </div>`).join("")}
    ${agd.synthese ? `<div style="margin-top:7px;padding-top:6px;border-top:1px solid var(--line-2);color:var(--ink)">${agd.synthese}</div>` : ""}
    <div style="margin-top:5px">${verdict}</div>
  </div>`;
}

function updateRadarInsight(agd) {
  const bank = RADAR_BANK || "SGCI";
  const t = document.getElementById("radar-title");
  if (t) t.textContent = `Portrait compétitif ${bank}`;
  const el = document.getElementById("radar-insight");
  if (!el) return;
  if (agd) {
    el.innerHTML = radarInsight(agd);
  }
}

let _LINE_METRIC   = 'rn'; // 'rn' | 'pnb' | 'roe'
let _rnLineTitle   = '';
let _rnAnalysisHtml = '';

function _cBlock(txt){
  return "<div style='margin-top:14px;padding:11px 14px;background:rgba(56,209,240,.07);border-left:3px solid #38D1F0;border-radius:0 6px 6px 0'>"
    + "<div style='font:700 9px var(--sans,sans-serif);text-transform:uppercase;letter-spacing:.08em;color:#38D1F0;margin-bottom:5px'>◆ Analyse</div>"
    + "<div style='font:500 12px/1.6 var(--sans,sans-serif);color:var(--ink,#F6F6F7)'>" + txt + "</div></div>";
}

function _lineMetaUpdate(m){
  const titleEl = document.getElementById('ap-line-title');
  const subEl   = document.getElementById('ap-line-sub');
  const anaEl   = document.getElementById('ap-line-analysis');
  if(!titleEl) return;

  if(m === 'rn'){
    titleEl.textContent = _rnLineTitle;
    if(subEl) subEl.textContent = 'Résultat net · Mds FCFA · évolution AN1→AN3';
    if(anaEl) anaEl.innerHTML = _rnAnalysisHtml;
    return;
  }

  const Q2 = t => `<span style="color:#E8A020;font-weight:700;font-style:italic">${t}</span>`;
  const isROE = m === 'roe';
  const data  = isROE ? ROE_SERIES : PNB_SERIES;

  // Valeur la plus récente + avant-dernière par banque (pour tendance)
  const latest = {}, prev = {};
  Object.entries(data).forEach(([b, yv]) => {
    const yrs = Object.keys(yv).map(Number).sort();
    if(yrs.length >= 1) latest[b] = { yr: yrs[yrs.length-1], val: yv[yrs[yrs.length-1]] };
    if(yrs.length >= 2) prev[b]   = { yr: yrs[yrs.length-2], val: yv[yrs[yrs.length-2]] };
  });
  const sorted    = Object.entries(latest).sort((a,b) => b[1].val - a[1].val);
  const sgci      = latest['SGCI'];
  const sgciPrev  = prev['SGCI'];
  const leader    = sorted[0];
  const second    = sorted[1];
  const sgciRank  = sorted.findIndex(([b]) => b === 'SGCI') + 1;
  const mktAvg    = sorted.length ? sorted.reduce((s,[,d])=>s+d.val,0)/sorted.length : 0;

  if(isROE){
    // Tendance SGCI
    const sgciTrend = sgci && sgciPrev
      ? (sgci.val - sgciPrev.val)
      : null;
    const trendTxt = sgciTrend !== null
      ? (sgciTrend >= 0
          ? `en progression de <b>+${sgciTrend.toFixed(1)}pt</b> vs ${sgciPrev.yr}`
          : `en repli de <b>${sgciTrend.toFixed(1)}pt</b> vs ${sgciPrev.yr}`)
      : '';
    // Banques qui progressent le plus
    const accelerateurs = sorted
      .filter(([b]) => prev[b])
      .map(([b,d]) => [b, d.val - prev[b].val])
      .sort((a,b) => b[1]-a[1])
      .slice(0,2);
    const leaderName = leader ? leader[0] : '?';
    const leaderVal  = leader ? leader[1].val.toFixed(1) : '?';
    const gapToLeader = sgci && leader ? (leader[1].val - sgci.val).toFixed(1) : null;
    const sgciRNLeader = (RN2025 && Object.entries(RN2025).sort((a,b)=>b[1]-a[1])[0])?.[0] === 'SGCI';

    titleEl.textContent = sgci
      ? `ROE ${leader[1].yr} — ${leaderName} leader (${leaderVal}%) · SGCI #${sgciRank}/${sorted.length} (${sgci.val.toFixed(1)}%)`
      : `Évolution ROE · ${sorted.length} banques`;
    if(subEl) subEl.textContent = 'ROE = Résultat net / Capitaux propres · % · rendement des fonds propres actionnaires';
    if(anaEl) anaEl.innerHTML = _cBlock(
      `Le ROE mesure ce que chaque franc investi par les actionnaires rapporte. Un ROE élevé = capital bien employé. Un ROE faible peut signifier que la banque est sous-performante <i>ou</i> qu'elle dispose d'une base de capitaux propres très large — ce qui est le cas de SGCI.<br><br>`
      + (sgci ? `SGCI affiche <b>${sgci.val.toFixed(1)}%</b> en ${sgci.yr}${trendTxt ? ', ' + trendTxt : ''} — rang <b>#${sgciRank}/${sorted.length}</b>. `
               + (sgciRNLeader ? `Paradoxe structurel : SGCI est <b>#1 en Résultat net absolu</b> mais #${sgciRank} en ROE. Cela s'explique par une base de capitaux propres nettement plus lourde que ses concurrents — les actionnaires ont apporté ou accumulé davantage de capital. ` : '')
               + (gapToLeader ? `L'écart avec ${leaderName} (leader à <b>${leaderVal}%</b>) est de <b>${gapToLeader}pt</b> — soit ${Q2('un coût d\'opportunité réel pour les actionnaires SGCI.')} ` : '')
               : '')
      + `<br>Moyenne marché : <b>${mktAvg.toFixed(1)}%</b> — SGCI est ${sgci && sgci.val >= mktAvg ? 'au-dessus' : Q2('en dessous')} de la moyenne.<br>`
      + (accelerateurs.length ? `<b>Qui accélère ?</b> ${accelerateurs.map(([b,d]) => `<b>${b}</b> (+${d.toFixed(1)}pt)`).join(', ')} — des concurrents qui améliorent leur efficacité du capital plus vite que SGCI.<br>` : '')
      + `<br><b>Implication décisionnelle :</b> soit SGCI déploie davantage ce capital (croissance des crédits, acquisitions), soit il envisage une politique de distribution plus agressive (dividendes). Rester sur-capitalisé sans stratégie claire pèsera durablement sur le ROE.`
      + `<br><br><b>Classement ${leader[1].yr} :</b> ${sorted.map(([b,d]) => `<b>${b}</b> ${d.val.toFixed(1)}%`).join(' · ')}.`
    );
  } else {
    // PNB
    const sgciMds    = sgci ? (sgci.val/1000).toFixed(0) : '?';
    const gap12      = sgci && second ? Math.round((sgci.val - second[1].val)/1000) : 0;
    const sgciGrowth = sgci && sgciPrev ? ((sgci.val - sgciPrev.val)/sgciPrev.val*100).toFixed(1) : null;
    // Croissance de chaque banque
    const growths = sorted
      .filter(([b]) => prev[b])
      .map(([b,d]) => [b, ((d.val - prev[b].val)/prev[b].val*100)])
      .sort((a,b) => b[1]-a[1]);
    const fastestGrower = growths[0];

    const pnbLeaderName = sorted.length ? sorted[0][0] : '?';
    const sgciPnbRank   = sorted.findIndex(([b]) => b === 'SGCI') + 1;
    titleEl.textContent = sgci
      ? (pnbLeaderName === 'SGCI'
          ? `SGCI leader PNB — ${sgciMds} Mds · avance de ${gap12} Mds sur ${second ? second[0] : '#2'}`
          : `PNB — ${pnbLeaderName} leader · SGCI #${sgciPnbRank}/${sorted.length} (${sgciMds} Mds)`)
      : `Évolution PNB · ${sorted.length} banques`;
    if(subEl) subEl.textContent = 'PNB = Produit Net Bancaire · M FCFA · revenu d\'activité total de la banque';
    if(anaEl) anaEl.innerHTML = _cBlock(
      `Le PNB est l'équivalent du chiffre d'affaires d'une banque — il agrège les intérêts, commissions et produits financiers nets. C'est le socle à partir duquel s'explique la rentabilité.<br><br>`
      + (sgci ? `SGCI génère <b>${sgciMds} Mds</b> de PNB en ${sgci.yr}${sgciGrowth ? ` (<b>${sgciGrowth > 0 ? '+' : ''}${sgciGrowth}%</b> vs ${sgciPrev.yr})` : ''} — <b>leader incontesté</b> du marché ivoirien. `
               + (gap12 ? `Avance sur le #2 (${second[0]}) : <b>+${gap12} Mds</b> — une dominance commerciale structurelle qui s'explique par la taille du réseau, la base clientèle et la diversité des produits. ` : '')
               : '')
      + (fastestGrower && fastestGrower[0] !== 'SGCI'
          ? `<br>${Q2(`Signal à surveiller :`)} <b>${fastestGrower[0]}</b> affiche la croissance PNB la plus rapide du marché (<b>+${fastestGrower[1].toFixed(1)}%</b>) — une montée en puissance qui pourrait réduire l'écart à moyen terme si SGCI n'accélère pas ses revenus d'activité.`
          : '')
      + (sgciGrowth ? `<br><br><b>Implication décisionnelle :</b> ${
            parseFloat(sgciGrowth) < 5
              ? `La croissance PNB de SGCI (<b>${sgciGrowth}%</b>) est modeste au regard de sa position dominante. Un effet de base explique en partie ce ralentissement, mais la diversification des revenus (commissions, activités de marché) reste un levier à activer pour soutenir la dynamique commerciale.`
              : `La croissance PNB de SGCI (<b>+${sgciGrowth}%</b>) confirme que le leadership n'est pas statique. SGCI génère davantage de revenus tout en maintenant son avance — signe d'une machine commerciale efficace.`
          }` : '')
      + `<br><br><b>Marché ${sgci ? sgci.yr : ''} :</b> ${sorted.map(([b,d]) => `<b>${b}</b> ${(d.val/1000).toFixed(0)} Mds`).join(' · ')}.`
    );
  }
  // ROE/PNB : on n'affiche JAMAIS le template ci-dessus — il est écrasé (même exécution synchrone,
  // donc jamais peint) par l'analyse LLM (line_roe/line_pnb), sinon par un loader. Uniquement du LLM.
  if(anaEl && m !== 'rn'){
    const _llmLine = (window._EF_LLM || {})['line_' + m];
    anaEl.innerHTML = _cBlock(_llmLine || '<span style="opacity:.4">Analyse en cours…</span>');
  }
}

function _drawApLine(){
  try{ Plotly.purge("ap-line"); } catch(e){}
  if(_LINE_METRIC === 'rn'){
    chartRNLine("ap-line", 340);
  } else if(_LINE_METRIC === 'pnb'){
    chartSeriesLine("ap-line", PNB_SERIES, 340, "M FCFA", " M");
  } else {
    chartSeriesLine("ap-line", ROE_SERIES, 340, "%", "%");
  }
}

function setLineMetric(m){
  _LINE_METRIC = m;
  document.querySelectorAll(".line-filter-btn").forEach(b =>
    b.classList.toggle("on", b.dataset.m === m)
  );
  _drawApLine();
  _lineMetaUpdate(m);
}

/* ── PDF Export v6 — document STRUCTURÉ à partir du résumé LLM (plus de capture d'écran) ─── */
function btnPDF(title){
  return `<button class="btn-pdf" onclick="exportPDF('${title}')">⬇ Télécharger PDF</button>`;
}

// Titre affiché sur le bouton → section de résumé backend + segment courant à interroger.
const _PDF_SECTION_MAP = {
  "Santé Financière": "ef",
  "Analyse Tarifaire": "cb",
  "Analyse Concurrentielle": "cb",
  "Benchmark Concurrentiel": "cb",
  "Stratégie SGCI": "strategie",
  "Rapports SGCI": "strategie",
};
function _pdfSegment(section){
  if(section === "strategie") return (typeof STRAT_SEG !== "undefined" && STRAT_SEG) || "Particuliers";
  const f = (typeof APERCU_FILTERS !== "undefined") ? APERCU_FILTERS : {};
  return f.frais_seg || "Particuliers";
}

// Charge une image en HTMLImageElement (nécessaire pour pdf.addImage) — attend le chargement réel.
function _pdfLoadImg(src){
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = rej;
    img.src = src;
  });
}

async function exportPDF(title){
  const date = new Date().toLocaleDateString("fr-FR", {day:"2-digit", month:"long", year:"numeric"});
  const section = _PDF_SECTION_MAP[title] || "strategie";
  const segment = _pdfSegment(section);

  const ov = document.createElement("div");
  ov.id = "_pdf_ov";
  ov.style.cssText = "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.8);display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:system-ui;backdrop-filter:blur(10px)";
  ov.innerHTML = '<div style="text-align:center;color:#fff"><div style="font-size:40px">⏳</div><div style="font:700 17px/1.4 system-ui;margin-top:14px">Génération du résumé…</div><div style="font:400 11px system-ui;color:rgba(255,255,255,.45);margin-top:6px">Rédaction par l\'IA — peut prendre jusqu\'à 20 s la 1ʳᵉ fois</div></div>';
  document.body.appendChild(ov);

  let resume = null;
  try{
    const r = await fetch(`/api/dashboard_resume?section=${section}&segment=${encodeURIComponent(segment)}`);
    const j = await r.json();
    resume = j && j.resume;
    if(resume) resume._stale = j.stale, resume._generatedAt = j.generated_at;
  }catch(e){ /* resume reste null → message d'échec ci-dessous */ }

  if(!resume || !resume.executif){
    document.body.removeChild(ov);
    alert("Résumé indisponible pour le moment (quota ou service IA indisponible).\n\n"+
          "Le PDF est rédigé par l'IA à partir des données actuelles — réessayez dans quelques minutes,\n"+
          "ou utilisez « Rafraîchir les analyses » puis réessayez.");
    return;
  }

  const ok = await _pdfLoadLib();
  if(!ok){
    document.body.removeChild(ov);
    alert("La librairie PDF n'a pas pu être chargée (connexion internet requise la 1ʳᵉ fois).");
    return;
  }

  try{
    await _pdfRenderNative(resume, title, date);
  }catch(e){
    console.error("pdf error", e);
    alert("Erreur lors de la génération du PDF : " + e.message);
  }
  document.body.removeChild(ov);
}

// Rendu PDF NATIF (jsPDF texte/formes directement, AUCUNE capture DOM/html2canvas) — fini les PDF
// vides ou tronqués selon l'état de la page : ici on dessine nous-mêmes, donc c'est déterministe.
async function _pdfRenderNative(resume, title, date){
  const RED = [229, 20, 43], DARKGRAY = [40, 40, 40], MIDGRAY = [110, 110, 110], LIGHTBG = [251, 244, 244], BLUEBG = [243, 245, 248];
  const M = 16;                      // marge (mm)
  // Source unique du logo : le PDF n'affiche QUE le logo SGCI, jamais d'autre marque/monogramme.
  const logo = await _pdfLoadImg("assets/logos/SGCI.png").catch(() => null);

  const src = document.createElement("div");   // requis par html2pdf pour initialiser le worker
  const pdf = await html2pdf().set({jsPDF: {unit: "mm", format: "a4", orientation: "portrait"}})
                                .from(src).toPdf().get("pdf");
  const pageW = pdf.internal.pageSize.getWidth(), pageH = pdf.internal.pageSize.getHeight();
  const contentW = pageW - 2 * M;
  let y = M;

  // ── Filigrane discret — traçabilité si le PDF circule hors de l'app ──
  // Gris très clair, diagonal, sous le contenu : lisible en y regardant de près, jamais gênant
  // pour lire le rapport. Pas de nom d'utilisateur (l'app n'a qu'un identifiant partagé, pas de
  // comptes individuels) — mais la date/heure exacte de génération est une trace suffisante.
  const _wmStamp = new Date().toLocaleString('fr-FR', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'});
  // 2026-07-28 : aligné sur le filigrane écran, rendu plus discret (gris 235 → 244, corps
  // 26 → 22). 2026-07-29 : remonté un peu (244 → 238, 22 → 24) suite au même réglage côté écran.
  const _addWatermark = () => {
    pdf.setFont("helvetica", "bold"); pdf.setFontSize(24);
    pdf.setTextColor(238, 238, 238);
    pdf.text("DIRECTION INNOVATION SGCI", pageW / 2, pageH / 2 - 6, {angle: 40, align: "center"});
    pdf.setFont("helvetica", "normal"); pdf.setFontSize(10);
    pdf.text(_wmStamp, pageW / 2, pageH / 2 + 10, {angle: 40, align: "center"});
  };
  _addWatermark();

  const ensure = (needed) => { if(y + needed > pageH - 14){ pdf.addPage(); _addWatermark(); y = M; } };
  const wrapped = (text, x, w, size, style, color, lh) => {
    pdf.setFont("helvetica", style || "normal"); pdf.setFontSize(size);
    pdf.setTextColor(color[0], color[1], color[2]);
    const lines = pdf.splitTextToSize(text || "", w);
    const lineH = lh || size * 0.42;
    for(const ln of lines){ ensure(lineH); pdf.text(ln, x, y); y += lineH; }
    return y;
  };
  const label = (text, color) => {
    ensure(6);
    pdf.setFont("helvetica", "bold"); pdf.setFontSize(8.5);
    pdf.setTextColor(color[0], color[1], color[2]);
    pdf.text(text.toUpperCase(), M, y);
    y += 5.5;
  };

  /* ── En-tête : logo SGCI (et LUI SEUL) + titre + date ── */
  if(logo){ try{ pdf.addImage(logo, "PNG", M, y - 2, 14, 14); }catch(e){} }
  pdf.setFont("helvetica", "bold"); pdf.setFontSize(15);
  pdf.setTextColor(20, 20, 20);
  pdf.text(resume.titre || resume.section || title, M + (logo ? 18 : 0), y + 4);
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(8.5);
  pdf.setTextColor(MIDGRAY[0], MIDGRAY[1], MIDGRAY[2]);
  pdf.text(`${(resume.section||"").toUpperCase()} · SEGMENT ${(resume.segment||"").toUpperCase()}`, M + (logo ? 18 : 0), y + 9);
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(8.5);
  pdf.text(`Généré le ${date}`, pageW - M, y + 4, {align: "right"});
  pdf.setTextColor(160, 160, 160);
  pdf.text("SpyBusiness · Confidentiel", pageW - M, y + 9, {align: "right"});
  y += 16;
  pdf.setDrawColor(RED[0], RED[1], RED[2]); pdf.setLineWidth(0.8);
  pdf.line(M, y, pageW - M, y);
  y += 9;

  /* ── Avertissement si ce résumé est une version de secours (dernier rafraîchissement échoué) ──
     Visible même après téléchargement — sans ça, un PDF ouvert plus tard ne dit rien de son âge réel. */
  if(resume._stale){
    let genTxt = 'date inconnue';
    if(resume._generatedAt){
      try{ genTxt = new Date(resume._generatedAt).toLocaleDateString('fr-FR', {day:'2-digit',month:'long',year:'numeric'}); }catch(e){}
    }
    pdf.setFont("helvetica", "bold"); pdf.setFontSize(9);
    const warnLines = pdf.splitTextToSize(
      `⚠ ANALYSE DE SECOURS — dernière génération réussie le ${genTxt} (le dernier rafraîchissement a échoué, ce résumé n'est pas le plus récent).`,
      contentW - 10);
    const warnH = warnLines.length * 4.6 + 6;
    ensure(warnH);
    pdf.setFillColor(254, 243, 199); // #FEF3C7
    pdf.rect(M, y - 4, contentW, warnH, "F");
    pdf.setTextColor(146, 64, 14); // #92400E
    let wy = y + 1;
    for(const ln of warnLines){ pdf.text(ln, M + 5, wy); wy += 4.6; }
    y += warnH + 8;
  }

  /* ── Résumé exécutif (bloc coloré) ── */
  label("Résumé exécutif", RED);
  // IMPORTANT : la police DOIT être fixée AVANT splitTextToSize — jsPDF mesure le texte avec la
  // police ACTIVE au moment de l'appel, pas celle utilisée plus tard pour dessiner. Sinon les
  // lignes sont découpées pour une police plus petite que celle rendue → débordement (bug vérifié).
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(10.5);
  const execLines = pdf.splitTextToSize(resume.executif || "", contentW - 10);
  const execH = execLines.length * 5.2 + 6;
  ensure(execH);
  pdf.setFillColor(LIGHTBG[0], LIGHTBG[1], LIGHTBG[2]);
  pdf.setDrawColor(RED[0], RED[1], RED[2]); pdf.setLineWidth(1.2);
  pdf.rect(M, y - 4, contentW, execH, "F");
  pdf.line(M, y - 4, M, y - 4 + execH);
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(10.5); pdf.setTextColor(30, 30, 30);
  let yy = y + 1;
  for(const ln of execLines){ pdf.text(ln, M + 5, yy); yy += 5.2; }
  y += execH + 8;

  /* ── Points clés ── */
  label("Points clés", MIDGRAY);
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(9.5);   // fixé AVANT le splitTextToSize de la boucle
  for(const p of (resume.points || [])){
    const lines = pdf.splitTextToSize(p, contentW - 10);
    ensure(lines.length * 4.6 + 3);
    pdf.setFont("helvetica", "bold"); pdf.setFontSize(10.5); pdf.setTextColor(RED[0], RED[1], RED[2]);
    pdf.text("•", M, y);
    pdf.setFont("helvetica", "normal"); pdf.setFontSize(9.5); pdf.setTextColor(35, 35, 35);
    for(let i = 0; i < lines.length; i++){ pdf.text(lines[i], M + 5, y); y += 4.6; }
    y += 1.5;
  }
  y += 4;

  /* ── Analyse ── */
  label("Analyse", MIDGRAY);
  wrapped(resume.analyse || "", M, contentW - 2, 9.8, "normal", DARKGRAY, 4.8);
  y += 6;

  /* ── À retenir (bloc conclusion) ── */
  pdf.setFont("helvetica", "bold"); pdf.setFontSize(10);   // fixé AVANT le splitTextToSize
  const conclLines = pdf.splitTextToSize(resume.conclusion || "", contentW - 10);
  const conclH = conclLines.length * 5 + 6;
  ensure(conclH + 6);
  pdf.setFillColor(BLUEBG[0], BLUEBG[1], BLUEBG[2]);
  pdf.rect(M, y - 4, contentW, conclH, "F");
  pdf.setFont("helvetica", "bold"); pdf.setFontSize(8.5); pdf.setTextColor(22, 80, 176);
  pdf.text("À RETENIR", M + 5, y);
  pdf.setFont("helvetica", "bold"); pdf.setFontSize(10); pdf.setTextColor(20, 20, 20);
  yy = y + 5.5;
  for(const ln of conclLines){ pdf.text(ln, M + 5, yy); yy += 5; }
  y += conclH + 10;

  /* ── Pied de page ── */
  ensure(8);
  pdf.setFont("helvetica", "normal"); pdf.setFontSize(7.5); pdf.setTextColor(170, 170, 170);
  pdf.text("Résumé rédigé par l'agent IA à partir des données réellement stockées — chaque chiffre est vérifiable dans le dashboard SpyBusiness.",
            pageW / 2, pageH - 10, {align: "center", maxWidth: contentW});

  pdf.save(`SpyBusiness — ${resume.titre || title} — ${date}.pdf`);
}

async function _pdfLoadLib(){
  if(window.html2pdf) return true;
  return new Promise(res=>{
    const s=document.createElement("script");
    s.src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
    s.onload=()=>res(true); s.onerror=()=>res(false);
    document.head.appendChild(s);
  });
}

/* ── Glossaire Santé Financière ─────────────────────────────────────────── */
const GLOSSAIRE_TERMS = [
  {cat:"Performance"},
  {acronym:"ROE", name:"Rentabilité des fonds propres", tag:"perf",
   def:"<b>Définition :</b> Résultat Net ÷ Capitaux Propres × 100.<br><br><b>À quoi ça sert :</b> C'est le thermomètre principal de la performance bancaire. Mesure combien un franc de capital génère de bénéfice. La norme marché UEMOA est de 15–20%.<br><br><b>Comment lire :</b> ROE de 18% = pour 100 FCFA investis par les actionnaires, la banque génère 18 FCFA de profit par an.<br><br><b>Signal d'alerte :</b> ROE < 10% = la banque crée peu de valeur. ROE > 25% = excellence opérationnelle."},
  {acronym:"PNB", name:"Produit Net Bancaire — chiffre d'affaires de la banque", tag:"revenu",
   def:"<b>Définition :</b> Revenus d'intérêts + Commissions − Coût des ressources. Équivalent bancaire du chiffre d'affaires.<br><br><b>À quoi ça sert :</b> Toute la santé financière repose sur le PNB. Sans PNB croissant, impossible de couvrir les charges, provisionner les risques et dégager un bénéfice.<br><br><b>Comment lire :</b> PNB de 100 Mds = la banque a généré 100 milliards de valeur nette avant charges d'exploitation."},
  {acronym:"RN", name:"Résultat Net — le bénéfice final", tag:"perf",
   def:"<b>Définition :</b> Ce qui reste après déduction de TOUTES les charges : frais généraux, coût du risque, impôts, dotations exceptionnelles.<br><br><b>À quoi ça sert :</b> Alimente les réserves (solvabilité), rémunère les actionnaires (dividendes) et mesure l'efficacité globale.<br><br><b>Relation :</b> RN / PNB = Marge nette. Si PNB = 100 Mds et RN = 18 Mds → marge nette 18%."},
  {acronym:"Marge nette", name:"Résultat Net / PNB — conversion en bénéfice", tag:"perf",
   def:"<b>Définition :</b> Résultat Net ÷ PNB × 100. Mesure quelle fraction du PNB est convertie en profit après toutes charges.<br><br><b>À quoi ça sert :</b> Indicateur synthétique d'efficacité globale — intègre la maîtrise des charges (coeff.) ET la qualité du portefeuille (CNR).<br><br><b>Benchmark :</b> Les meilleures banques africaines atteignent 25–30%. Marge < 15% = pression structurelle."},
  {cat:"Efficacité"},
  {acronym:"Coeff. d'exploitation", name:"Charges générales / PNB — l'efficacité opérationnelle", tag:"perf",
   def:"<b>Définition :</b> Charges générales ÷ PNB × 100. Mesure quelle part du PNB est absorbée par les frais de fonctionnement (salaires, loyers, SI, marketing).<br><br><b>À quoi ça sert :</b> C'est l'indicateur d'efficacité opérationnelle de référence dans toute analyse bancaire. Plus il est bas, mieux c'est.<br><br><b>Benchmark BCEAO :</b> Objectif < 70%. Coeff. 60% = pour 100 FCFA de revenus, 60 partent en charges, 40 restent pour risque + bénéfice.<br><br><b>Signal d'alerte :</b> Coeff. > 75% = la banque est peu efficiente et vulnérable à un ralentissement d'activité."},
  {acronym:"RBE", name:"Résultat Brut d'Exploitation — avant coût du risque", tag:"perf",
   def:"<b>Définition :</b> PNB − Charges générales. Résultat avant provisions pour risques et éléments exceptionnels.<br><br><b>À quoi ça sert :</b> Mesure la capacité de la banque à générer des bénéfices sur son activité courante, indépendamment des aléas de crédit.<br><br><b>Relation :</b> RBE = PNB × (1 − Coeff. d'exploitation / 100)."},
  {acronym:"CNR / PNB", name:"Coût du risque sur PNB — poids du risque crédit dans les revenus", tag:"risque",
   def:"<b>Définition :</b> Coût Net du Risque ÷ PNB × 100. Mesure quelle part des revenus bancaires est absorbée par les provisions pour créances douteuses.<br><br><b>À quoi ça sert :</b> C'est le lien entre le risque de crédit et la rentabilité réelle. Un CNR/PNB élevé signifie que la banque génère des revenus mais les perd en provisions — ce qui annule le travail commercial.<br><br><b>Différence avec CNR/Encours :</b> Le CNR/Encours mesure la qualité du portefeuille (combien de crédits tournent mal). Le CNR/PNB mesure l'impact sur les résultats (à quel point cela pèse sur la rentabilité).<br><br><b>Benchmark :</b> CNR/PNB < 15% = situation saine. 15–30% = attention. > 30% = la banque travaille pour couvrir ses propres pertes de crédit.<br><br><b>Exemple :</b> PNB 100 Mds, CNR 25 Mds → CNR/PNB 25% : un quart des revenus partent en provisions avant même les charges générales."},
  {acronym:"Mix revenus", name:"Intérêts vs Commissions — diversification du PNB", tag:"revenu",
   def:"<b>Définition :</b> Décomposition du PNB entre revenus d'intérêts (crédits) et commissions (services, transactions, change).<br><br><b>À quoi ça sert :</b> Un mix équilibré est plus résilient. Les commissions sont moins risquées (pas d'exposition crédit) mais très concurrentielles. Les intérêts sont stables mais sensibles aux taux.<br><br><b>Objectif sain :</b> > 35% de commissions. Mix 70/30 (intérêts/commissions) = forte dépendance crédit, vulnérable aux montées de NPL."},
  {cat:"Risque de crédit"},
  {acronym:"CNR", name:"Coût Net du Risque — provisions pour créances douteuses", tag:"risque",
   def:"<b>Définition :</b> Dotations nettes aux provisions pour créances douteuses sur la période. Ce que la banque met de côté pour couvrir les prêts à risque de non-remboursement.<br><br><b>À quoi ça sert :</b> C'est le coût caché du métier de banquier. Un CNR élevé = trop de crédits mal sélectionnés. Exprimé en Mds FCFA ou en pb (points de base) sur l'encours.<br><br><b>Signal d'alerte :</b> CNR en hausse 3 années consécutives = dégradation structurelle du portefeuille."},
  {acronym:"CNR / Encours (pb)", name:"Ratio CNR sur Encours — en points de base (1pb = 0,01%)", tag:"risque",
   def:"<b>Définition :</b> (CNR ÷ Encours brut de crédit) × 10 000. Permet de comparer le coût du risque entre banques de tailles différentes.<br><br><b>À quoi ça sert :</b> Ratio de référence des analystes pour mesurer la qualité du portefeuille crédit, indépendamment de la taille.<br><br><b>Comment lire :</b> 100 pb = 1% d'encours provisionnés nets par an. Seuil de confort : < 150 pb. > 250 pb = signal de stress sérieux.<br><br><b>BCEAO recommande :</b> < 200 pb en fonctionnement normal."},
  {acronym:"NPL", name:"Non-Performing Loans — créances en souffrance", tag:"risque",
   def:"<b>Définition :</b> Prêts sur lesquels le débiteur n'a pas effectué de paiement depuis plus de 90 jours. Aussi appelés créances douteuses ou créances classées.<br><br><b>À quoi ça sert :</b> Un taux de NPL élevé érode les fonds propres et force des provisions massives qui réduisent le bénéfice.<br><br><b>Calcul :</b> NPL Ratio = Créances douteuses / Total Encours crédit.<br><br><b>Signal d'alerte BCEAO :</b> > 5% = zone de vigilance prudentielle."},
  {cat:"Solidité financière"},
  {acronym:"Solvabilité", name:"Capitaux propres / Total Actif — le coussin de sécurité", tag:"struct",
   def:"<b>Définition :</b> Capitaux propres ÷ Total Actif × 100. Mesure la part de l'actif financée par les fonds propres (et non par la dette ou les dépôts).<br><br><b>À quoi ça sert :</b> C'est le coussin absorbant les pertes. Un ratio élevé = la banque peut encaisser des chocs sans faire défaut aux déposants.<br><br><b>Norme BCEAO :</b> Minimum 8%. Zone de confort : > 12%.<br><br><b>Comment lire :</b> Solvabilité 12% = pour 100 FCFA d'actifs, 12 FCFA sont couverts par les fonds propres."},
  {acronym:"Levier crédit", name:"Créances / Fonds propres — l'exposition au risque de crédit", tag:"risque",
   def:"<b>Définition :</b> Encours brut de crédit ÷ Capitaux propres. Mesure combien les fonds propres sont amplifiés par les crédits accordés.<br><br><b>À quoi ça sert :</b> Plus le levier est élevé, plus la banque est exposée en cas de défauts. Chaque 1% de NPL détruit un multiple de fonds propres.<br><br><b>Comment lire :</b> Levier 8× = pour 1 FCFA de fonds propres, 8 FCFA de crédits accordés → chaque 1% de NPL = 8% des fonds propres perdus."},
  {acronym:"Couverture dépôts", name:"Fonds propres / Dépôts — protection des déposants", tag:"struct",
   def:"<b>Définition :</b> Fonds propres ÷ Dépôts de la clientèle × 100.<br><br><b>À quoi ça sert :</b> Indique la capacité de la banque à rembourser ses déposants si elle subissait des pertes importantes. Ratio rassurant pour la stabilité systémique.<br><br><b>Comment lire :</b> Couverture 15% = pour 100 FCFA déposés, 15 FCFA sont couverts par les fonds propres."},
  {cat:"Cadre réglementaire"},
  {acronym:"BCEAO", name:"Banque Centrale des États de l'Afrique de l'Ouest", tag:"struct",
   def:"<b>Rôle :</b> Banque centrale de l'UEMOA (Bénin, Burkina, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal, Togo). Émet le franc CFA, définit la politique monétaire, supervise et réglemente toutes les banques de la zone.<br><br><b>Normes prudentielles clés :</b><br>• Solvabilité minimum : 8% (zone confort > 12%)<br>• Coefficient d'exploitation cible : < 70%<br>• Ratio de liquidité : > 100%<br>• NPL recommandé : < 5%<br>• CNR / Encours : < 200 pb<br><br><b>Impact :</b> Toutes les données du dashboard respectent le cadre de reporting BCEAO — les banques sont comparables sur des bases communes."},
  {acronym:"UEMOA", name:"Union Économique et Monétaire Ouest-Africaine", tag:"struct",
   def:"<b>Définition :</b> Zone monétaire de 8 pays d'Afrique de l'Ouest partageant le franc CFA BCEAO.<br><br><b>Pertinence :</b> Les 7 banques comparées (SGCI, BICICI, BNI, BACI, ECOBANK CI, SIB, NSIA) opèrent toutes sous la supervision de la BCEAO — elles sont soumises aux mêmes normes prudentielles et utilisent le même référentiel comptable, ce qui rend la comparaison rigoureusement valide."},
];

function _buildGlossaireHTML(){
  const tagLabel = {perf:"Performance",risque:"Risque",struct:"Structure",revenu:"Revenus"};
  const tagCls   = {perf:"perf",risque:"risque",struct:"struct",revenu:"revenu"};
  return GLOSSAIRE_TERMS.map(t => {
    if(t.cat) return `<div class="gloss-cat">${t.cat}</div>`;
    return `<div class="gloss-term" onclick="this.classList.toggle('expanded')">
      <div class="gloss-term-hdr">
        <span class="gloss-acronym">${t.acronym}</span>
        <span class="gloss-name">${t.name}</span>
        <span class="gloss-chev">›</span>
      </div>
      <div class="gloss-term-body">
        <div class="gloss-tag ${tagCls[t.tag]||''}">${tagLabel[t.tag]||t.tag}</div>
        ${t.def}
      </div>
    </div>`;
  }).join("");
}

function _injectGlossaire(){
  if(document.getElementById("gloss-drawer")) return;
  const overlay = document.createElement("div");
  overlay.id = "gloss-overlay"; overlay.className = "gloss-overlay";
  overlay.onclick = () => toggleGloss(false);
  document.body.appendChild(overlay);

  const drawer = document.createElement("div");
  drawer.id = "gloss-drawer"; drawer.className = "gloss-drawer";
  drawer.innerHTML = `
    <div class="gloss-head">
      <div>
        <div style="font:700 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent-2);margin-bottom:6px">SpyBusiness</div>
        <h2>Glossaire</h2>
        <div style="font:500 12px var(--sans);color:var(--muted);margin-top:4px">Tous les termes de Santé Financière expliqués</div>
      </div>
      <button class="close-btn" onclick="toggleGloss(false)">✕</button>
    </div>
    <div class="gloss-body">${_buildGlossaireHTML()}</div>`;
  document.body.appendChild(drawer);
}

function toggleGloss(force){
  _injectGlossaire();
  const drawer  = document.getElementById("gloss-drawer");
  const overlay = document.getElementById("gloss-overlay");
  const open = force !== undefined ? force : !drawer.classList.contains("open");
  drawer.classList.toggle("open", open);
  overlay.classList.toggle("open", open);
  document.body.style.overflow = open ? "hidden" : "";
}

function pageApercu(){
  if(!KPI_DATA) return `<div style="text-align:center;padding:80px;color:var(--muted);font:500 14px var(--sans)">Chargement des données…</div>`;
  // Helpers mise en forme (mêmes que app.data.js)
  const Q = t => `<span style="color:#E8A020;font-weight:700;font-style:italic">${t}</span>`;
  const G = t => `<b>${t}</b>`;
  const K = t => `<b>${t}</b>`;
  const k      = KPI_DATA;
  const f      = APERCU_FILTERS;
  const ord    = n => n===1?"1ᵉʳ":n===2?"2ᵉ":n===3?"3ᵉ":`${n}ᵉ`;
  const anxKey = "Année " + f.rn_anx;
  const ecartLabel  = k.ecart_pct_vs_2 >= 0
    ? k.ecart_pct_vs_2.toFixed(0) + "% devant " + k.banque_2_nom
    : Math.abs(k.ecart_pct_vs_2).toFixed(0) + "% derrière " + k.banque_2_nom;
  const growthSigne = k.sgci_growth_pct >= 0 ? "+" : "";
  const btnAnx = (v,l) => "<button class='" + (f.rn_anx===v?"on":"") + "' onclick=\"setApercuFilter('rn_anx'," + v + ")\">" + l + "</button>";
  const leg  = k.anx_legend || {};
  // Groupes DYNAMIQUES : on regroupe les banques qui partagent la MÊME correspondance
  // AN1/AN2/AN3 → année civile. Une nouvelle banque rejoint automatiquement le bon groupe.
  const grps = (()=>{
    const order = (typeof CB_BANK_ORDER !== "undefined" && CB_BANK_ORDER.length)
      ? CB_BANK_ORDER : Object.keys(leg);
    const byKey = new Map();
    order.forEach(b=>{
      const l = leg[b]; if(!l) return;
      const key = [1,2,3].map(n=>l["AN"+n]||"?").join("|");
      if(!byKey.has(key)) byKey.set(key, []);
      byKey.get(key).push(b);
    });
    const groups = [...byKey.values()].map(bs=>({banks:bs, label:bs.join(" · ")}));
    return groups.length ? groups
      : [{banks:(order||[]), label:(order||[]).join(" · ")}];
  })();

  // ── Données critiques ────────────────────────────────────────────────
  const rn_data = k.rn_data || {};
  const total   = Object.values(rn_data).reduce((a,b)=>a+b,0);
  const sorted  = Object.entries(rn_data).sort((a,b)=>b[1]-a[1]);
  const top3pct = total>0 ? Math.round(sorted.slice(0,3).reduce((a,[,v])=>a+v,0)/total*100) : 0;
  const sgciPct = total>0 ? Math.round((rn_data["SGCI"]||0)/total*100) : 0;
  const sgciMult= total>0 ? ((rn_data["SGCI"]||0)/total*Object.keys(rn_data).length).toFixed(1) : "0";
  const gdata   = k.growths_data || {};
  const sgciG   = gdata["SGCI"]!==undefined ? Math.round(gdata["SGCI"]) : 0;
  const gvals   = Object.values(gdata).sort((a,b)=>a-b);
  const medianG = gvals.length ? +(gvals[Math.floor(gvals.length/2)].toFixed(1)) : 0;
  const fastest = Object.entries(gdata).filter(([b])=>b!=="SGCI").sort((a,b)=>b[1]-a[1])[0] || ["?",0];
  const fasterN = Object.entries(gdata).filter(([b,v])=>b!=="SGCI"&&v>(gdata["SGCI"]||0)).length;
  const avgShare= (100/Math.max(Object.keys(rn_data).length,1)).toFixed(1);
  const sgciROE = ROE_DATA["SGCI"];
  // Valeurs RN AN1 et AN3 pour analyses trajectoire
  const sgciRNseries = (RN_SERIES["SGCI"] || {}).values || [];
  const sgciAN1v = sgciRNseries[0] || 0;
  const sgciAN3v = sgciRNseries[sgciRNseries.length-1] || 0;
  const fastestAN3rn = ((RN_SERIES[fastest[0]] || {}).values || []);
  const fastestAN3v  = fastestAN3rn[fastestAN3rn.length-1] || 0;
  const second = Object.entries(rn_data).filter(([b])=>b!=="SGCI").sort((a,b)=>b[1]-a[1])[0] || ["?",0];
  const gap12  = sgciAN3v > 0 && second[1] > 0 ? Math.round((sgciAN3v - second[1])/1000) : 0;
  // Classement des concurrents par croissance (pour nommer les menaces)
  const concGrowth = Object.entries(gdata).filter(([b])=>b!=="SGCI").sort((a,b)=>b[1]-a[1]);
  const watch1 = concGrowth[0] || ["?",0];
  const watch2 = concGrowth[1] || ["?",0];
  const watch1RN = ((RN_SERIES[watch1[0]]||{}).values||[]);
  const watch2RN = ((RN_SERIES[watch2[0]]||{}).values||[]);
  const watch1v  = (watch1RN[watch1RN.length-1]||0)/1000;
  const watch2v  = (watch2RN[watch2RN.length-1]||0)/1000;

  // Bump ranks AN1 vs AN3
  const vBanks = Object.keys(RN_SERIES).filter(b=>RN_SERIES[b]&&RN_SERIES[b].values&&RN_SERIES[b].values.length>=3);
  const byAN1  = [...vBanks].sort((a,b)=>RN_SERIES[b].values[0]-RN_SERIES[a].values[0]);
  const byAN3  = [...vBanks].sort((a,b)=>(RN_SERIES[b].values[RN_SERIES[b].values.length-1]||0)-(RN_SERIES[a].values[RN_SERIES[a].values.length-1]||0));
  const rAN1={},rAN3={};
  byAN1.forEach((b,i)=>{rAN1[b]=i+1;}); byAN3.forEach((b,i)=>{rAN3[b]=i+1;});
  const movers   = vBanks.filter(b=>b!=="SGCI").map(b=>({b,d:(rAN1[b]||CB_BANKS.length)-(rAN3[b]||CB_BANKS.length)})).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  const topMover = movers[0]||{b:"?",d:0};
  const sgciR3   = rAN3["SGCI"]||1;
  const leader3  = byAN3[0] || "SGCI";   // leader effectif à AN3 — doit être défini avant bumpAnalyse
  const risers   = movers.filter(m=>m.d>0).sort((a,b)=>b.d-a.d);
  const fallers  = movers.filter(m=>m.d<0).sort((a,b)=>a.d-b.d);
  const sibMove    = movers.find(m => m.b === "SIB");
  const sibRan1    = rAN1["SIB"] || "?", sibRan3 = rAN3["SIB"] || "?";
  const sibAlert   = sibMove && Math.abs(sibMove.d) >= 2
    ? " ⚠ <b>Cas SIB : signal d'alarme</b> — 2ème en AN1, elle recule de <b>" + Math.abs(sibMove.d) + " places</b> pour terminer #" + sibRan3 + " en AN3. C'est le recul le plus sévère du marché : une banque qui perd autant de rang en si peu d'années doit examiner d'urgence sa stratégie de croissance et sa rentabilité. "
    : sibMove && sibMove.d < 0
    ? " <b>SIB</b> perd " + Math.abs(sibMove.d) + " place" + (Math.abs(sibMove.d)>1?"s":"") + " (AN1 #" + sibRan1 + " → AN3 #" + sibRan3 + "). "
    : "";
  const bumpAnalyse = "Le classement par Résultat net sur 3 ans révèle qui progresse et qui recule.<br>Un rang stable en tête = avance maintenue. Un rang qui descend = un concurrent qui absorbe des parts de marché en profitabilité.<br>"
    + (leader3 === "SGCI"
    ? "SGCI tient la <b>tête de façon constante</b> sur toute la période — leadership structurellement solide.<br>"
    : "<b>" + leader3 + "</b> s'impose comme nouveau leader — signal d'urgence pour SGCI.<br>")
    + sibAlert
    + "Les banques qui progressent dans ce classement ont en commun une meilleure gestion du risque crédit et des charges — exactement ce que les Sections ③ et ④ analysent pour SGCI.<br>"
    + (risers.filter(m=>m.b!=="SIB").slice(0,2).length
       ? risers.filter(m=>m.b!=="SIB").slice(0,2).map(m=>"<b>"+m.b+"</b> ↑"+m.d+" place"+(m.d>1?"s":"")).join(" · ") + " : dynamique positive à surveiller.<br>" : "")
    + (fallers.filter(m=>m.b!=="SIB").slice(0,1).length
       ? fallers.filter(m=>m.b!=="SIB").slice(0,1).map(m=>"<b>"+m.b+"</b> ↓"+Math.abs(m.d)+" place"+(Math.abs(m.d)>1?"s":"")).join("") + " : décroissance relative confirmée.<br>" : "")
    + (movers.filter(m=>Math.abs(m.d)>=2).length>=3
       ? "Marché <b>en forte recomposition</b>."
       : movers.filter(m=>Math.abs(m.d)>=1).length>=2
       ? "Hiérarchie <b>modérément fluide</b> — " + (leader3==="SGCI" ? "SGCI reste en tête." : "<b>"+leader3+"</b> en tête.")
       : "Classement <b>très stable</b> sur la période.");

  // Titres dynamiques
  // 2026-07-30 : plus de « || 1 ». Un rang inconnu ne doit pas se lire comme un rang 1 :
  // la branche rang===1 affirme « SGCI · trajectoire la plus soutenue du marché ». Sans
  // donnée, on retombe sur le titre neutre (cf. _rnDenom ci-dessous).
  const _sgRankRN = Number(k.sgci_rang_rn) || null;
  // Effectif réel du panel : plus de « || 7 » figé — si une banque est ajoutée, le
  // dénominateur suit ; si les données manquent, on n'affiche aucun dénominateur.
  const _rnDenom  = Object.keys(k.rn_data||{}).length || null;
  const lineTitle = (_sgRankRN && _sgRankRN !== 1)
    ? "Résultat net · SGCI #" + _sgRankRN + (_rnDenom ? "/" + _rnDenom : "") + " · évolution AN1→AN3"
    : !_sgRankRN ? "Résultat net · évolution AN1→AN3"
    : fasterN===0 ? "SGCI · trajectoire de résultat net la plus soutenue du marché"
    : fastest[0]!=="?" ? "SGCI en tête · " + fastest[0] + " accélère plus vite (+" + Math.round(fastest[1]) + "%)"
    : "Résultat net · évolution AN1→AN3";
  const growTitle = "Qui croît, qui recule ? · médiane : " + (medianG>=0?"+":"") + medianG + "%";
  const treeTitle = "SGCI = " + sgciPct + "% des bénéfices · " + sgciMult + "× la part moyenne";
  const bumpTitle = leader3 === "SGCI"
    ? (topMover.b!=="?" && Math.abs(topMover.d)>0
       ? "Classement stable — " + topMover.b + " " + (topMover.d>0?"monte":"recule") + " de " + Math.abs(topMover.d) + " place" + (Math.abs(topMover.d)>1?"s":"")
       : "Classement stable · SGCI #1 confirmé sur 3 ans")
    : leader3 + " détrône SGCI — nouveau leader du marché";

  // Critique card (string concat — pas de backtick imbriqué)
  const C = function(txt, efKey){
    /* LE TEXTE CALCULÉ S'AFFICHE TOUT DE SUITE (2026-08-11).

       La version précédente le jetait au profit d'un « Analyse en cours… », que
       _loadEFAnalysesLLM() devait remplacer par la rédaction du modèle. Tant que le modèle
       répondait, personne ne s'en apercevait. Le jour où son quota journalier s'épuise, les
       quatre tentatives de reprise échouent et le bloc reste sur son loader — DÉFINITIVEMENT.
       Mesuré sur le service en ligne : vingt-huit blocs figés sur « Analyse en cours… », alors
       que le texte déterministe existait et était juste.

       On affiche donc ce texte immédiatement. Le modèle, quand il répond, le remplace par une
       version plus développée. Quand il ne répond pas, il ne manque rien d'essentiel : c'est
       le principe du projet — le déterministe établit, le modèle formule. */
    const body = txt;
    return "<div" + (efKey ? " data-ef='" + efKey + "'" : "") + " style='margin-top:14px;padding:11px 14px;background:rgba(56,209,240,.07);border-left:3px solid #38D1F0;border-radius:0 6px 6px 0'>"
      + "<div style='font:700 9px var(--sans,sans-serif);text-transform:uppercase;letter-spacing:.08em;color:#38D1F0;margin-bottom:5px'>◆ Analyse</div>"
      + "<div" + (efKey ? " data-ef-body" : "") + " style='font:500 12px/1.6 var(--sans,sans-serif);color:var(--ink,#F6F6F7)'>" + body + "</div></div>";
  };

  // Podium HTML
  // ── Données pour les 4 sections thématiques ───────────────────────────
  const pnbData    = k.pnb_data         || {};
  const margeData  = k.marge_nette_data  || {};
  const crData     = k.cout_r_pnb_data   || {};
  const roeData2   = k.roe_data          || {};
  const credData   = k.credits_data      || {};
  const depData    = k.depots_data       || {};
  const intData    = k.interets_data     || {};
  const commData   = k.commissions_data  || {};
  const autData    = k.autres_prod_data  || {};
  const rbeData    = k.rbe_data          || {};
  const reData     = k.re_data           || {};
  const sgciPNBv   = pnbData["SGCI"]     || 0;
  const totalPNB   = Object.values(pnbData).reduce((a,b)=>a+b,0);
  const sgciPNBShare = totalPNB > 0 ? +(sgciPNBv/totalPNB*100).toFixed(1) : 0;
  const pnbRankS   = Object.entries(pnbData).sort((a,b)=>b[1]-a[1]).findIndex(([b])=>b==="SGCI")+1;
  const margeTop   = Object.entries(margeData).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
  const sgciMargeV = margeData["SGCI"];
  const bestMargeV = margeTop[0]?.[1]||0, bestMargeB = margeTop[0]?.[0]||"?";
  const gainMarge  = sgciMargeV&&sgciPNBv ? Math.round((bestMargeV-sgciMargeV)/100*sgciPNBv/1000) : 0;
  const crSorted   = Object.entries(crData).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]);
  const sgciCRv    = crData["SGCI"];
  const bestCRv    = crSorted[0]?.[1]||0, bestCRb = crSorted[0]?.[0]||"?";
  const gainCR     = sgciCRv&&bestCRv&&sgciPNBv ? Math.round((sgciCRv-bestCRv)/100*sgciPNBv/1000) : 0;
  // Concurrent le plus rapide (Section ②) vs son coût du risque → connexion narrative clé
  const fastCRv    = crData[fastest[0]] || null;
  const fastCRmult = sgciCRv && fastCRv && fastCRv > 0 ? (sgciCRv / fastCRv).toFixed(1) : null;
  const gainCRfast = sgciCRv && fastCRv && sgciPNBv ? Math.round((sgciCRv-fastCRv)/100*sgciPNBv/1000) : 0;
  const roeSorted  = Object.entries(roeData2).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
  const sgciROEv2  = roeData2["SGCI"];
  const roeRankS   = roeSorted.findIndex(([b])=>b==="SGCI")+1;
  const roeLeaderB = roeSorted[0]?.[0]||"?", roeLeaderV = roeSorted[0]?.[1]||0;

  // Ratios crédits / dépôts par banque
  const sgciCred   = credData["SGCI"] || 0;
  const sgciDep    = depData["SGCI"]  || 0;
  const sgciCDRatio= sgciDep > 0 ? Math.round(sgciCred / sgciDep * 100) : null;
  const cdRatios   = Object.keys(credData).filter(b => depData[b]).map(b => ({
    b, r: Math.round((credData[b]||0) / (depData[b]||1) * 100)
  })).sort((a,b) => a.r - b.r);
  const safeCD       = cdRatios.filter(x => x.r >= 80 && x.r <= 100).map(x => x.b);
  const overCD       = cdRatios.filter(x => x.r > 100).map(x => x.b);
  const bestCDRatio  = cdRatios[cdRatios.length - 1] || null; // ratio le plus élevé
  const worstCDRatio = cdRatios[0] || null;                   // ratio le plus faible
  // 2ème PNB concurrent
  const pnbSorted2  = Object.entries(pnbData).sort((a,b)=>b[1]-a[1]);
  const pnb2b       = pnbSorted2.find(([b])=>b!=="SGCI")?.[0] || "?";
  const pnb2v       = pnbSorted2.find(([b])=>b!=="SGCI")?.[1] || 0;
  const pnb1b       = pnbSorted2[0]?.[0] || "?";   // leader PNB réel
  const pnb1v       = pnbSorted2[0]?.[1] || 0;
  const isSGCIpnb1  = pnbRankS === 1;
  // pnbGap : si SGCI est #1 → "X×" ; si SGCI n'est plus #1 → affiche le retard en %
  const pnbGap      = pnb2v > 0 && isSGCIpnb1 ? (sgciPNBv / pnb2v).toFixed(1)
                    : pnb1v > 0 && !isSGCIpnb1 ? Math.round((pnb1v - sgciPNBv) / pnb1v * 100) + "% de retard"
                    : "?";

  // Rangs dynamiques — recalculés à chaque chargement
  const margeRankSGCI   = margeTop.findIndex(([b])=>b==="SGCI")+1; // 1=meilleur
  const margeNbBanques  = margeTop.length;
  const isSGCImargeLast = margeRankSGCI === margeNbBanques;

  // ── Moteur de narration rank-relatif ──────────────────────────────────
  // Interprétation d'un multiplier vs part équitable (fonctionne pour mult > ou < 1)
  const _multTxt = (mult) => {
    const m = parseFloat(mult);
    if (m >= 1.5) return "position <b>dominante</b> (" + mult + "× la part équitable)";
    if (m >= 1.0) return "dans la <b>norme haute</b> (" + mult + "× la part équitable)";
    if (m >= 0.7) return "légèrement <b>sous-représenté</b> (" + mult + "× la part équitable)";
    return "très <b>sous-représenté</b> (" + mult + "× la part équitable) — " + Q("signal d'alerte").replace(/<[^>]+>/g,"");
  };

  // Phrase SGCI vs concurrent direct — direction dynamique (avance ou retard)
  const _vs2txt = (sgciV, rivalB, rivalV, label) => {
    if (!rivalB || rivalB==="?") return "";
    if (sgciV >= rivalV) {
      const pct = rivalV > 0 ? Math.round((sgciV-rivalV)/rivalV*100) : 0;
      return "Avance sur <b>" + rivalB + "</b> (#2) : <b>+" + pct + "%</b> en " + label + ".";
    }
    const pct = sgciV > 0 ? Math.round((rivalV-sgciV)/sgciV*100) : 0;
    return Q("⚠ <b>" + rivalB + "</b> devance SGCI de <b>+" + pct + "%</b> en " + label + " — rattraper devient prioritaire.");
  };

  // Leader dynamique en volume (premier du classement, pas forcément SGCI)
  const _volLeader = (data, label) => {
    const top = Object.entries(data).sort((a,b)=>b[1]-a[1])[0];
    if (!top) return "";
    return top[0]==="SGCI"
      ? "SGCI est la <b>plus grande banque</b> du marché en " + label
      : "La <b>plus grande banque</b> en " + label + " est désormais <b>" + top[0] + "</b> — SGCI est #" + (Object.entries(data).sort((a,b)=>b[1]-a[1]).findIndex(([b])=>b==="SGCI")+1);
  };

  // Framing du leadership général (Section ① podium + Section ④)
  const _leaderFrame = (leaderB, sgciRank, n) => {
    if (leaderB==="SGCI") return "";
    return Q("⚠ <b>" + leaderB + "</b> est le nouveau leader (#1/" + n + "). SGCI est #" + sgciRank + " — la priorité est de réduire cet écart.");
  };
  // ── Fin moteur narratif ───────────────────────────────────────────────

  // IA textes — tous conditionnels sur les données réelles
  // ── Section ② : Revenus (PNB défini ici une seule fois) ──────────────
  const ia3 = isSGCIpnb1
    ? "Le PNB (Produit Net Bancaire) représente ce que la banque gagne sur ses activités, avant de déduire ses charges.<br><br>"
      + "SGCI génère <b>" + (sgciPNBv/1000).toFixed(0) + " Mds FCFA</b> de revenus d'activité — la base la plus élevée du marché.<br><br>"
      + "Avoir les revenus les plus importants est un atout, mais ce n'est pas suffisant : l'enjeu est de transformer le maximum de ces revenus en profit réel."
    : "Le PNB (Produit Net Bancaire) représente ce que la banque gagne sur ses activités, avant de déduire ses charges.<br><br>"
      + "SGCI n'est plus en tête sur ce critère.<br>"
      + "<b>" + (pnbSorted2[0]?.[0]||"?") + "</b> génère davantage de revenus d'activité — la dynamique commerciale de SGCI est à renforcer.";

  // ── Section ③ : Efficacité (marge définie ici) ──────────────────────
  const ia4 = sgciMargeV
    ? "La marge nette mesure la part des revenus qui devient réellement du profit.<br><br>"
      + "Sur 100 F de revenus, SGCI en garde <b>" + sgciMargeV.toFixed(1) + " F</b> comme profit net — "
      + (isSGCImargeLast
        ? "la conversion la plus faible du marché, malgré les revenus les plus importants.<br><br>"
          + "La cause principale n'est pas les charges d'exploitation — elles sont bien maîtrisées.<br>"
          + "C'est le coût lié aux prêts non remboursés qui absorbe une trop grande part des revenus. La section suivante l'analyse en détail."
        : margeRankSGCI <= 3
          ? "position dans le top 3 du marché.<br><br>"
            + "<b>" + bestMargeB + "</b> convertit <b>" + bestMargeV.toFixed(1) + " F</b> pour 100 F de revenus."
            + (gainMarge > 0 ? "<br><br>Atteindre ce niveau représenterait <b>+" + gainMarge + " Mds FCFA</b> de profit supplémentaire, sans toucher aux revenus." : "")
          : "position intermédiaire — la conversion est à améliorer.<br><br>"
            + "<b>" + bestMargeB + "</b> fait mieux avec <b>" + bestMargeV.toFixed(1) + " F</b> pour 100 F de revenus."
      )
    : "Données de marge nette en cours de chargement.";

  // ── Section ④ : Risque crédit (provisions définies ici) ─────────────
  const sgciCRrank = crSorted.findIndex(([b])=>b==="SGCI")+1;
  const sgciCRisWorst = sgciCRrank === crSorted.length;
  const ia5 = sgciCRv
    ? (sgciCRisWorst
        ? "Chaque année, certains clients ne remboursent pas leurs prêts à la banque.<br><br>"
          + "Pour anticiper ces pertes, la réglementation bancaire (BCEAO) oblige les banques à réserver une partie de leurs revenus à l'avance — c'est ce qu'on appelle le coût du risque crédit.<br><br>"
          + "En pratique, SGCI a réservé <b>" + sgciCRv.toFixed(1) + " F pour chaque 100 F gagnés</b> — soit <b>" + Math.round(sgciCRv/100*(sgciPNBv||0)/1000) + " Mds FCFA</b> qui n'ont jamais atteint le profit final.<br><br>"
          + "C'est le niveau le plus élevé parmi les 7 banques, et la principale raison pour laquelle le profit de SGCI est moins élevé que ses revenus pourraient le permettre."
        : "Chaque année, certains clients ne remboursent pas leurs prêts. La banque doit réserver une partie de ses revenus pour couvrir ces pertes potentielles.<br><br>"
          + "SGCI a réservé <b>" + sgciCRv.toFixed(1) + " F pour chaque 100 F gagnés</b> — classement <b>" + sgciCRrank + " sur " + crSorted.length + "</b> (1 = le moins de réserves, donc le portefeuille de prêts le plus sain).<br><br>"
          + "La situation s'est améliorée par rapport aux années précédentes."
      )
      + (fastCRmult && fastest[0]!=="?"
        ? "<br><br><b>" + fastest[0] + "</b>, le concurrent qui a le plus progressé, ne réserve que <b>" + (fastCRv||0).toFixed(1) + " F</b> pour 100 F gagnés — <b>" + fastCRmult + "× moins</b> que SGCI.<br>"
          + "Ce n'est pas un hasard : quand on perd moins sur les prêts, il reste plus d'argent disponible pour le profit et la croissance."
        : "")
      + (gainCR > 0
        ? "<br><br>Si SGCI ramenait son niveau de réserves à celui de <b>" + bestCRb + "</b>, le gain de profit annuel serait estimé à <b>+" + gainCR + " Mds FCFA</b> — sans changer ses revenus."
        : "")
      + "<br><br>" + Q("Question ouverte : ce niveau de réserves reflète-t-il la réalité des prêts accordés, ou SGCI est-elle trop prudente par rapport au risque réel ?")
    : "Données sur le risque crédit en cours de chargement.";
  // Variables pour la recommandation stratégique
  const sgciCoeffRec  = (k.coeff_expl_data||{})["SGCI"];
  const coeffSortedR  = Object.entries(k.coeff_expl_data||{}).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]);
  const sgciCoeffRank = coeffSortedR.findIndex(([b])=>b==="SGCI")+1; // 1=meilleur (plus bas)
  const crRankSGCI    = crSorted.findIndex(([b])=>b==="SGCI")+1;
  const n = crSorted.length;

  // ── Détection dynamique du problème principal ──────────────────────
  // Score de sévérité = écart relatif au meilleur du marché (0=parfait, 1=très mauvais)
  const problems = [];
  if (sgciCRv && bestCRv > 0)
    problems.push({ type:'risk',  score:(sgciCRv-bestCRv)/bestCRv,
      decision: "Réduire le coût du risque crédit de <b>" + sgciCRv.toFixed(1) + "%</b> vers <b>" + bestCRv.toFixed(1) + "%</b> (" + bestCRb + ") — gain estimé : <b>+" + gainCR + " Mds FCFA</b> de RN sans aucune action commerciale.",
      copier: bestCRb, label:"coût du risque #" + crRankSGCI + "/" + n + " (" + sgciCRv.toFixed(1) + "% — " + (crRankSGCI===n?"le plus élevé":"élevé") + " du marché)" });
  if (sgciMargeV && bestMargeV > 0)
    problems.push({ type:'marge', score:(bestMargeV-sgciMargeV)/bestMargeV,
      decision: "Améliorer la conversion PNB→RN : marge de <b>" + (sgciMargeV||0).toFixed(1) + "%</b> vers <b>" + bestMargeV.toFixed(1) + "%</b> (" + bestMargeB + ") — gain estimé : <b>+" + gainMarge + " Mds FCFA</b>. Levier : mix de revenus et gestion du risque.",
      copier: bestMargeB, label:"marge nette #" + margeRankSGCI + "/" + margeTop.length });
  if (sgciROEv2 && roeLeaderV > 0)
    problems.push({ type:'roe',   score:(roeLeaderV-sgciROEv2)/roeLeaderV,
      decision: "Améliorer le ROE de <b>" + sgciROEv2.toFixed(1) + "%</b> vers <b>" + roeLeaderV.toFixed(1) + "%</b> (" + roeLeaderB + ") — en réduisant les fuites (risque ou charges) plutôt qu'en levant des capitaux.",
      copier: roeLeaderB, label:"ROE #" + roeRankS + "/" + roeSorted.length });
  if (sgciCoeffRank && sgciCoeffRank > 1 && coeffSortedR.length > 0)
    problems.push({ type:'coeff', score:(sgciCoeffRec - coeffSortedR[0][1]) / coeffSortedR[0][1],
      decision: "Réduire les charges d'exploitation (coeff. " + (sgciCoeffRec||"?") + "% → cible " + coeffSortedR[0][1].toFixed(1) + "% de " + coeffSortedR[0][0] + ") — levier direct sur le RBE.",
      copier: coeffSortedR[0][0], label:"coeff. exploitation #" + sgciCoeffRank });

  problems.sort((a,b)=>b.score-a.score); // tri par sévérité décroissante
  const mainProb   = problems[0] || null;
  const secondProb = problems[1] || null;

  // Qui copier : le meilleur sur le problème principal, ou le concurrent le plus rapide s'il gère mieux
  const modeleToCopy = fastest[0]!=="?" && fastCRmult && parseFloat(fastCRmult)>=5
    ? fastest[0] : (mainProb ? mainProb.copier : bestCRb);

  const crRankLabel  = crRankSGCI === crSorted.length ? "le plus élevé" : "#"+crRankSGCI;
  const ia6 = sgciROEv2 && sgciCRv ? (() => {
    // ── FORCES — dynamiques selon les rankings réels ─────────────────────
    const pnbStr   = isSGCIpnb1
      ? "<b>#1 en PNB</b> (" + (sgciPNBv/1000).toFixed(0) + " Mds — " + pnbGap + "× le #2)"
      : "<b>#" + pnbRankS + " en PNB</b> (" + (sgciPNBv/1000).toFixed(0) + " Mds)";
    const coeffStr = sgciCoeffRank === 1
      ? "<b>#1 en maîtrise des charges</b> (coefficient " + (sgciCoeffRec||"?") + "%, meilleur du marché)"
      : "coefficient d'exploitation <b>#" + sgciCoeffRank + "</b> (" + (sgciCoeffRec||"?") + "%)";
    const forces = "SGCI : " + pnbStr + ", <b>#1 en résultat net absolu</b> (" + (sgciAN3v/1000).toFixed(0) + " Mds), " + coeffStr + "."
      + (isSGCIpnb1 && sgciCoeffRank === 1 ? " Leadership confirmé sur les 2 indicateurs clés — classement stable depuis 3 ans." : " Position de leader — à consolider.");

    // ── FAIBLESSES — pilotées par mainProb (problème #1 détecté) ─────────
    let faiblesses;
    if (!mainProb) {
      faiblesses = "Performance équilibrée sur tous les indicateurs — la solidité de SGCI est globale.";
    } else if (mainProb.type === 'risk') {
      faiblesses = "Malgré ce leadership, SGCI convertit <b>le moins bien</b> ses revenus en profit : <b>"
        + (sgciMargeV||0).toFixed(1) + "% de marge nette — #" + margeRankSGCI + "/" + margeNbBanques + "</b>."
        + " Cause identifiée : coût du risque crédit à <b>" + sgciCRv.toFixed(1) + "%</b> (" + crRankLabel + " du marché) — soit <b>"
        + Math.round(sgciCRv/100*(sgciPNBv||0)/1000) + " Mds FCFA</b> de provisions annuelles qui n'atteignent jamais le résultat net."
        + " Conséquence : ROE <b>#" + roeRankS + "/" + roeSorted.length + "</b> (" + sgciROEv2.toFixed(1) + "%) — les actionnaires sont moins rémunérés que chez <b>" + roeLeaderB + "</b> (" + roeLeaderV.toFixed(1) + "%).";
    } else if (mainProb.type === 'marge') {
      faiblesses = "Malgré ce leadership en revenus, SGCI convertit seulement <b>" + (sgciMargeV||0).toFixed(1) + "% de son PNB en résultat net</b> — <b>#"
        + margeRankSGCI + "/" + margeNbBanques + " du marché</b>."
        + " Avec <b>" + (sgciPNBv/1000).toFixed(0) + " Mds de PNB (#1)</b>, cette inefficience est le principal levier inexploité."
        + " Meilleur du marché : <b>" + bestMargeB + "</b> à <b>" + bestMargeV.toFixed(1) + "%</b> — gain potentiel : <b>+" + gainMarge + " Mds FCFA</b> de RN sans aucune action commerciale.";
    } else if (mainProb.type === 'roe') {
      faiblesses = "La rentabilité actionnariale est le maillon faible : ROE <b>#" + roeRankS + "/" + roeSorted.length + "</b> à <b>"
        + sgciROEv2.toFixed(1) + "%</b>. <b>" + roeLeaderB + "</b> délivre <b>" + roeLeaderV.toFixed(1) + "%</b> de ROE avec moins de revenus."
        + " La cause : une conversion PNB→RN à <b>" + (sgciMargeV||0).toFixed(1) + "%</b> vs <b>" + bestMargeV.toFixed(1) + "%</b> pour le leader."
        + " Levier : optimiser la structure du bilan ou réduire les fuites vers les provisions.";
    } else if (mainProb.type === 'coeff') {
      faiblesses = "Le coefficient d'exploitation de <b>" + (sgciCoeffRec||"?") + "%</b> — <b>#" + sgciCoeffRank + "/" + coeffSortedR.length + " du marché</b> — pèse directement sur le RBE."
        + " Cible identifiée : <b>" + (coeffSortedR[0]?.[0]||"?") + "</b> à <b>" + (coeffSortedR[0]?.[1]||0).toFixed(1) + "%</b>."
        + " Chaque point de charges en moins = gain direct sur le résultat net, sans aucune action commerciale.";
    }

    // ── QUI SURVEILLER — adapté au problème principal détecté ────────────
    let quiSurveiller;
    if (fastest[0] === "?") {
      quiSurveiller = "Le marché est relativement stable sur la période — peu de recomposition du classement.";
    } else {
      const croissBase = "<b>" + fastest[0] + "</b> (+<b>" + Math.round(fastest[1]) + "%</b> sur 3 ans) est le concurrent à surveiller en priorité : il croît "
        + Math.round(fastest[1]/Math.max(sgciG,1)) + "× plus vite que SGCI";
      if (!mainProb || mainProb.type === 'risk') {
        quiSurveiller = croissBase + " et affiche un coût du risque de seulement <b>" + (fastCRv||0).toFixed(1) + "%</b>"
          + (fastCRmult ? " (" + fastCRmult + "× inférieur à SGCI)" : "") + ". Sa croissance est soutenable car elle repose sur une base de risque saine. En valeur absolue il reste loin — mais la trajectoire est sans ambiguïté.";
      } else if (mainProb.type === 'marge') {
        quiSurveiller = croissBase + " avec une meilleure conversion PNB→RN — sa marge finance directement sa croissance organique sans pression sur les capitaux. En valeur absolue il reste loin — mais la trajectoire est sans ambiguïté.";
      } else if (mainProb.type === 'roe') {
        quiSurveiller = croissBase + " en dégageant un ROE supérieur à SGCI — sa croissance crée davantage de valeur actionnariale à chaque exercice. En valeur absolue il reste loin — mais la trajectoire est sans ambiguïté.";
      } else {
        quiSurveiller = croissBase + " avec des charges opérationnelles maîtrisées — son efficience lui donne une avance structurelle sur la durée. En valeur absolue il reste loin — mais la trajectoire est sans ambiguïté.";
      }
    }

    // ── QUI COPIER — piloté par mainProb ─────────────────────────────────
    let quiCopier;
    if (!mainProb) {
      quiCopier = "Performance équilibrée — maintenir le cap sur tous les indicateurs.";
    } else {
      const detail = mainProb.type === 'risk'
        ? "coût du risque à <b>" + (crData[mainProb.copier]||0).toFixed(1) + "%</b> — modèle de gestion saine du portefeuille crédit et de croissance soutenable."
        : mainProb.type === 'marge'
        ? "marge nette de <b>" + bestMargeV.toFixed(1) + "%</b> — meilleure conversion PNB→RN du marché."
        : mainProb.type === 'roe'
        ? "ROE de <b>" + roeLeaderV.toFixed(1) + "%</b> — meilleure rentabilité actionnariale du marché."
        : "coefficient d'exploitation de <b>" + (coeffSortedR[0]?.[1]||0).toFixed(1) + "%</b> — meilleure maîtrise des charges opérationnelles.";
      quiCopier = "<b>" + mainProb.copier + "</b> : " + detail
        + (secondProb && mainProb.copier !== secondProb.copier ? " <b>" + secondProb.copier + "</b> pour " + secondProb.label + "." : "");
    }

    // ── SWOT HTML ─────────────────────────────────────────────────────────
    const rd2      = RESILIENCE_DATA || {};
    const sgciR2   = rd2["SGCI"] || {};
    const solvSGCI2 = sgciR2.solvabilite;
    const lev2      = sgciR2.levier_credit;
    const solvComf2 = solvSGCI2 && solvSGCI2 >= 12;

    // ── 5 nouveaux indicateurs — distribuables dans n'importe quel quadrant
    const sgciCred2   = (k.credits_data||{})["SGCI"] || 0;
    const stress10_2  = (sgciR2.capitaux_propres && sgciR2.total_actif && sgciCred2)
      ? Math.max(0,(sgciR2.capitaux_propres - sgciCred2*0.10)/sgciR2.total_actif*100).toFixed(1) : null;
    const stressOK    = stress10_2 !== null && parseFloat(stress10_2) >= 8;
    // sgciCommPct calculé ici (déclaré après ia6 dans le scope parent → temporal dead zone)
    const _sgciInt2   = (k.interets_data||{})["SGCI"]    || 0;
    const _sgciComm2  = (k.commissions_data||{})["SGCI"] || 0;
    const _sgciAut2   = (k.autres_prod_data||{})["SGCI"] || 0;
    const _sgciGross2 = _sgciInt2 + _sgciComm2 + _sgciAut2;
    const commPctNum  = _sgciGross2 > 0 ? parseFloat((_sgciComm2/_sgciGross2*100).toFixed(1)) : 0;
    const _commPctStr = commPctNum.toFixed(1);
    const cdNum       = sgciCDRatio || 0;

    const _li = (col, html) =>
      `<li style="display:flex;gap:9px;font-size:13px;line-height:1.5;color:var(--ink);margin-bottom:9px">
         <span style="width:6px;height:6px;border-radius:50%;background:${col};margin-top:6px;flex-shrink:0"></span>
         <span>${html}</span></li>`;

    // ── Distribution des 5 indicateurs selon leur valeur réelle ──────────
    // Croissance SGCI AN1→AN3
    const growF = sgciG >= medianG && sgciG > 0
      ? _li("#22c55e",`Croissance AN1→AN3 : <b style="color:#15803d">+${sgciG}%</b> — au-dessus de la médiane marché (+${medianG}%).`) : "";
    const growW = sgciG < 0
      ? _li("#ef4444",`Croissance AN1→AN3 : <b style="color:#dc2626">${sgciG}%</b> — résultat net en <b>recul absolu</b>. Signal structurel majeur.`) : "";
    const growT = sgciG >= 0 && sgciG < medianG
      ? _li("#f59e0b",`Croissance SGCI +${sgciG}% — <b>sous la médiane</b> (+${medianG}%). ${fasterN} concurrent${fasterN>1?"s croissent":"  croît"} plus vite : perte de terrain relative.`) : "";

    // Liquidité — ratio crédits/dépôts
    const cdF = cdNum>=80 && cdNum<=100
      ? _li("#22c55e",`Liquidité (crédits/dépôts) : <b style="color:#15803d">${cdNum}%</b> — zone idéale BCEAO [80%–100%] ✓`) : "";
    const cdW = cdNum>100
      ? _li("#ef4444",`Liquidité : <b style="color:#dc2626">${cdNum}%</b> — prête plus qu'elle ne collecte. <b>Risque liquidité BCEAO</b> (seuil : 100%).`) : "";
    const cdT = cdNum>0 && cdNum<80
      ? _li("#f59e0b",`Liquidité : <b style="color:#b45309">${cdNum}%</b> — sous 80%. Dépôts sous-utilisés — potentiel commercial non capturé.`) : "";

    // Mix commercial — part des commissions dans le PNB
    const mixF = commPctNum>=30
      ? _li("#22c55e",`Mix PNB diversifié : <b style="color:#15803d">${_commPctStr}%</b> de commissions — résilient aux chocs de taux.`) : "";
    const mixW = commPctNum>0 && commPctNum<20
      ? _li("#ef4444",`Mix PNB concentré sur les intérêts : <b style="color:#dc2626">${_commPctStr}%</b> de commissions — <b>vulnérable aux chocs de taux</b>.`) : "";
    const mixT = commPctNum>=20 && commPctNum<30
      ? _li("#f59e0b",`Mix PNB : <b style="color:#b45309">${_commPctStr}%</b> de commissions — dépendance aux intérêts à réduire progressivement.`) : "";

    // Levier crédit (Créances/Fonds propres)
    const levF = lev2 && lev2<=5
      ? _li("#22c55e",`Levier crédit : <b style="color:#15803d">${lev2}×</b> — exposition maîtrisée. Fonds propres bien dimensionnés.`) : "";
    const levW = lev2 && lev2>7
      ? _li("#ef4444",`Levier crédit : <b style="color:#dc2626">${lev2}×</b> — <b>exposition élevée</b>. Chaque défaut de crédit pèse lourd sur les fonds propres.`) : "";
    const levT = lev2 && lev2>5 && lev2<=7
      ? _li("#f59e0b",`Levier crédit : <b style="color:#b45309">${lev2}×</b> — exposition modérée. Surveiller la qualité du portefeuille.`) : "";

    // Test de résistance — choc 10% NPL
    const stressF = stressOK && stress10_2
      ? _li("#22c55e",`Test de résistance (choc −10% NPL) : solvabilité resterait à <b style="color:#15803d">${stress10_2}%</b> — résiste au seuil BCEAO de 8%.`) : "";
    const stressT = !stressOK && stress10_2
      ? _li("#f59e0b",`Test de résistance (choc −10% NPL) : solvabilité tomberait à <b style="color:#b45309">${stress10_2}%</b> — <b>franchit le seuil BCEAO de 8%</b>. Coussin insuffisant.`) : "";

    // ── Construction des 4 quadrants ─────────────────────────────────────
    const forcesItems = [
      _li("#22c55e", isSGCIpnb1
        ? `<b>#1 en PNB</b> — <b style="color:#15803d">${(sgciPNBv/1000).toFixed(0)} Mds</b>, soit <b style="color:#15803d">${pnbGap}×</b> le 2<sup>e</sup> du marché.`
        : `PNB <b>#${pnbRankS}/${Object.keys(pnbData).length}</b> — <b style="color:#15803d">${(sgciPNBv/1000).toFixed(0)} Mds</b>.`),
      _li("#22c55e",`<b>#${sgciR3}/${sorted.length} en résultat net absolu</b> — <b style="color:#15803d">${(sgciAN3v/1000).toFixed(0)} Mds FCFA</b>.`),
      _li("#22c55e", sgciCoeffRank===1
        ? `<b>#1 en charges</b> — coefficient <b style="color:#15803d">${(sgciCoeffRec||0).toFixed(1)}%</b>, meilleur du marché.`
        : `Coefficient <b>#${sgciCoeffRank}</b> — <b style="color:#15803d">${(sgciCoeffRec||0).toFixed(1)}%</b>.`),
      solvSGCI2 ? _li("#22c55e",`Solvabilité <b style="color:#15803d">${solvSGCI2}%</b>${solvComf2?" (confort)":""} ≥ norme BCEAO 8%.`) : "",
      growF, cdF, mixF, levF, stressF,
    ].filter(Boolean).join("");

    const faiblLItems = (() => {
      const base = (() => {
        if (!mainProb) return _li("#ef4444","Performance équilibrée — pas de faiblesse critique identifiée.");
        if (mainProb.type==='risk') return [
          _li("#ef4444",`Marge nette <b style="color:#dc2626">${(sgciMargeV||0).toFixed(1)}%</b> — #${margeRankSGCI}/${margeNbBanques} : convertit le moins bien ses revenus.`),
          _li("#ef4444",`Coût du risque <b style="color:#dc2626">${sgciCRv.toFixed(1)}%</b> — ${crRankSGCI===crSorted.length?"<b>le plus élevé du marché</b>":"#"+crRankSGCI+"/"+crSorted.length}.`),
          _li("#ef4444",`<b style="color:#dc2626">${Math.round(sgciCRv/100*(sgciPNBv||0)/1000)} Mds FCFA</b> de provisions annuelles qui n'atteignent jamais le résultat net.`),
          _li("#ef4444",`ROE <b style="color:#dc2626">${sgciROEv2.toFixed(1)}%</b> — #${roeRankS}/${roeSorted.length}, contre <b>${roeLeaderV.toFixed(1)}%</b> chez ${roeLeaderB}.`),
        ].join("");
        if (mainProb.type==='marge') return [
          _li("#ef4444",`Marge nette <b style="color:#dc2626">${(sgciMargeV||0).toFixed(1)}%</b> (#${margeRankSGCI}/${margeNbBanques}) — conversion PNB→RN insuffisante.`),
          _li("#ef4444",`Écart vs leader <b>${bestMargeB}</b> : <b style="color:#dc2626">−${(bestMargeV-(sgciMargeV||0)).toFixed(1)} pts</b> de marge.`),
          _li("#ef4444",`ROE <b style="color:#dc2626">${sgciROEv2.toFixed(1)}%</b> (#${roeRankS}) — actionnaires sous-rémunérés vs ${roeLeaderB} (${roeLeaderV.toFixed(1)}%).`),
        ].join("");
        if (mainProb.type==='roe') return [
          _li("#ef4444",`ROE <b style="color:#dc2626">${sgciROEv2.toFixed(1)}%</b> — #${roeRankS}/${roeSorted.length}. ${roeLeaderB} génère <b>${roeLeaderV.toFixed(1)}%</b> avec moins de revenus.`),
          _li("#ef4444",`Conversion PNB→RN : <b style="color:#dc2626">${(sgciMargeV||0).toFixed(1)}%</b> vs <b>${bestMargeV.toFixed(1)}%</b> pour le leader.`),
          _li("#ef4444","Capital insuffisamment optimisé — chaque franc génère moins que les meilleurs."),
        ].join("");
        return [
          _li("#ef4444",`Coefficient <b style="color:#dc2626">${(sgciCoeffRec||0).toFixed(1)}%</b> — #${sgciCoeffRank}/${coeffSortedR.length}. Cible : <b>${(coeffSortedR[0]?.[1]||0).toFixed(1)}%</b> (${coeffSortedR[0]?.[0]||"?"}).`),
          _li("#ef4444","Chaque point de charges non réduit pèse directement sur le RBE."),
        ].join("");
      })();
      return base + [growW, cdW, mixW, levW].filter(Boolean).join("");
    })();

    const opporItems = [
      mainProb ? _li("#0ea5e9",`<b style="color:#0369a1">+${gainCR>0?gainCR:gainMarge} Mds FCFA</b> de RN récupérables en résolvant : ${mainProb.label}.`) : "",
      sgciROEv2&&roeLeaderV>sgciROEv2 ? _li("#0ea5e9",`ROE : <b style="color:#0369a1">${sgciROEv2.toFixed(1)}%</b> → <b style="color:#0369a1">${roeLeaderV.toFixed(1)}%</b> — sans lever de capitaux.`) : "",
      mainProb ? _li("#0ea5e9",`Modèle à copier : <b>${mainProb.copier}</b> ${mainProb.type==='risk'?`(coût du risque ${(crData[mainProb.copier]||0).toFixed(1)}%)`:mainProb.type==='marge'?`(marge ${bestMargeV.toFixed(1)}%)`:mainProb.type==='roe'?`(ROE ${roeLeaderV.toFixed(1)}%)`:`(coeff. ${(coeffSortedR[0]?.[1]||0).toFixed(1)}%)`}.`) : "",
      cdNum>0&&cdNum<80 ? _li("#0ea5e9",`Liquidité : porter le ratio crédits/dépôts de ${cdNum}% vers 80-100% = levier direct sur le PNB.`) : "",
      commPctNum<30 ? _li("#0ea5e9",`Diversification PNB : augmenter les commissions (actuellement ${_commPctStr}%) pour réduire la dépendance aux intérêts.`) : "",
    ].filter(Boolean).join("");

    const menacItems = [
      fastest[0]!=="?" ? _li("#f59e0b",`<b>${fastest[0]} +${Math.round(fastest[1])}% en 3 ans</b> — croît ~${Math.round(fastest[1]/Math.max(sgciG,1))}× plus vite que SGCI.`) : "",
      fastest[0]!=="?"&&fastCRv ? _li("#f59e0b",`Son coût du risque (<b style="color:#b45309">${(fastCRv||0).toFixed(1)}%</b>) rend cette croissance <b>saine et soutenable</b>.`) : "",
      solvSGCI2 ? _li("#f59e0b",`Chaque année sans action sur le risque érode le matelas de solvabilité (${solvSGCI2}%).`) : "",
      _li("#f59e0b","Trajectoire concurrentielle <b>sans ambiguïté</b> malgré l'écart absolu actuel."),
      growT, cdT, mixT, levT, stressT,
    ].filter(Boolean).join("");

    const gainBig = mainProb ? (gainCR>0?gainCR:gainMarge) : 0;
    const decisText = mainProb
      ? `Réduire ${mainProb.label.split("#")[0].trim()}<span style="font-family:var(--mono,monospace);font-weight:700"> <span style="color:#dc2626">${mainProb.type==='risk'?sgciCRv.toFixed(1):mainProb.type==='marge'?(sgciMargeV||0).toFixed(1):mainProb.type==='roe'?sgciROEv2.toFixed(1):(sgciCoeffRec||0).toFixed(1)}%</span> → <span style="color:#15803d">${mainProb.type==='risk'?bestCRv.toFixed(1):mainProb.type==='marge'?bestMargeV.toFixed(1):mainProb.type==='roe'?roeLeaderV.toFixed(1):(coeffSortedR[0]?.[1]||0).toFixed(1)}%</span></span> (modèle ${mainProb.copier}) = <b>+${gainBig} Mds FCFA de résultat net, à revenus constants.</b> La marge remonte, le ROE suit, la résilience se renforce mécaniquement.`
      : "Performance équilibrée sur tous les indicateurs — maintenir le cap et consolider la position de leader.";

    const qStyle = (bg,bd) => `border:1px solid ${bd};border-radius:10px;padding:18px 20px;background:${bg};min-height:200px`;
    const qHead = (badge, bgB, label, sub) =>
      `<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
         <span style="width:28px;height:28px;border-radius:7px;background:${bgB};display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;color:#fff;flex-shrink:0">${badge}</span>
         <b style="font-size:16px;font-weight:800;letter-spacing:-0.01em">${label}</b>
         <span style="margin-left:auto;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af">${sub}</span>
       </div><ul style="list-style:none;margin:0;padding:0">`;

    return `<div style="width:100%">
      <div style="display:grid;grid-template-columns:24px 1fr;gap:0">
        <div style="display:grid;grid-template-rows:1fr 1fr">
          <span style="writing-mode:vertical-rl;transform:rotate(180deg);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#9ca3af">Interne</span>
          <span style="writing-mode:vertical-rl;transform:rotate(180deg);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#9ca3af">Externe</span>
        </div>
        <div>
          <div style="display:grid;grid-template-columns:1fr 1fr;margin-bottom:4px">
            <span style="text-align:center;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#22c55e;padding:6px 0">Positif</span>
            <span style="text-align:center;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#ef4444;padding:6px 0">Négatif</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;grid-template-rows:auto auto;gap:12px">
            <div style="${qStyle("linear-gradient(180deg,rgba(34,197,94,.06),transparent)","rgba(34,197,94,.3)")}">
              ${qHead("F","#22c55e","Forces","Atouts internes")}<ul style="list-style:none;margin:0;padding:0">${forcesItems}</ul></div>
            <div style="${qStyle("linear-gradient(180deg,rgba(239,68,68,.06),transparent)","rgba(239,68,68,.3)")}">
              ${qHead("W","#ef4444","Faiblesses","Fragilités internes")}<ul style="list-style:none;margin:0;padding:0">${faiblLItems}</ul></div>
            <div style="${qStyle("linear-gradient(180deg,rgba(56,189,248,.06),transparent)","rgba(56,189,248,.3)")}">
              ${qHead("O","#0ea5e9","Opportunités","Leviers externes")}<ul style="list-style:none;margin:0;padding:0">${opporItems}</ul></div>
            <div style="${qStyle("linear-gradient(180deg,rgba(245,158,11,.07),transparent)","rgba(245,158,11,.3)")}">
              ${qHead("T","#f59e0b","Menaces","Risques externes")}<ul style="list-style:none;margin:0;padding:0">${menacItems}</ul></div>
          </div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:center;margin-top:14px;background:linear-gradient(135deg,rgba(229,20,43,.07),transparent);border:1px solid rgba(229,20,43,.25);border-left:4px solid #E5142B;border-radius:10px;padding:16px 22px">
        <div style="font-family:var(--mono,monospace);font-size:42px;font-weight:800;color:#E5142B;letter-spacing:-0.03em;line-height:1;white-space:nowrap">${gainBig>0?"+"+gainBig:"→"}<span style="font-size:17px"> Mds</span></div>
        <div>
          <div style="font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#E5142B;margin-bottom:4px">Décision prioritaire</div>
          <div style="font-size:13.5px;line-height:1.55;color:var(--ink)">${decisText}</div>
        </div>
      </div>
    </div>`;
  })()
  : "Recommandation en cours de chargement.";
  // ── Mix commercial & Cascade P&L ────────────────────────────────────
  const sgciInt   = intData["SGCI"]  || 0;
  const sgciComm  = commData["SGCI"] || 0;
  const sgciAut   = autData["SGCI"]  || 0;
  const sgciGross = sgciInt + sgciComm + sgciAut;
  const sgciCommPct = sgciGross > 0 ? (sgciComm / sgciGross * 100).toFixed(1) : 0;
  const sgciIntPct  = sgciGross > 0 ? (sgciInt  / sgciGross * 100).toFixed(1) : 0;
  // Banque la plus diversifiée (% commissions)
  const commPcts = Object.entries(commData).map(([b,v]) => {
    const tot = (intData[b]||0) + v + (autData[b]||0);
    return [b, tot > 0 ? v/tot*100 : 0];
  }).sort((a,b) => b[1]-a[1]);
  const topCommB = commPcts[0]?.[0] || "?";
  const topCommV = commPcts[0]?.[1]?.toFixed(1) || "0";
  // Cascade P&L SGCI
  const sgciPNBv2  = pnbData["SGCI"]  || 0;
  const sgciRBEv   = rbeData["SGCI"]  || 0;
  const sgciREv    = reData["SGCI"]   || 0;
  const sgciRNv2   = (k.rn_data||{})["SGCI"] || 0;
  const sgciEffPNB = sgciPNBv2 > 0 ? (sgciRNv2 / sgciPNBv2 * 100).toFixed(1) : 0;
  const sgciChargesEst = sgciPNBv2 > 0 && sgciRBEv > 0 ? Math.round((sgciPNBv2 - sgciRBEv)/1000) : 0;
  const sgciCRcasc = sgciRBEv > 0 && sgciREv > 0 ? Math.round((sgciRBEv - sgciREv)/1000) : 0;
  // Banque la plus efficiente (eff = RN/PNB)
  const effMap = Object.entries(k.rn_data||{}).map(([b,rn]) => {
    const pnb = pnbData[b] || 0;
    return [b, pnb > 0 ? rn/pnb*100 : 0];
  }).filter(([,v]) => v > 0).sort((a,b) => b[1]-a[1]);
  const topEffB = effMap[0]?.[0] || "?";
  const topEffV = effMap[0]?.[1]?.toFixed(1) || "0";
  // ── Métriques globales pour la page Stratégie (dynamique) ───────────
  window.DERIVED_METRICS = {
    fraisRank: Object.entries(FRAIS).sort((a,b)=>a[1]-b[1]).findIndex(([b])=>b==="SGCI")+1,
    margeV: sgciMargeV, margeRank: margeRankSGCI, margeNbBanques,
    bestMargeB, bestMargeV, gainMarge,
    crV: sgciCRv, crRank: crSorted.findIndex(([b])=>b==="SGCI")+1,
    crIsWorst: crSorted.findIndex(([b])=>b==="SGCI")+1 === crSorted.length,
    bestCRb, bestCRv, gainCR,
    roeV: sgciROEv2, roeRank: roeRankS, roeLeaderB, roeLeaderV,
    pnbRank: pnbRankS,
    coeffV: (k.coeff_expl_data||{})["SGCI"],
    coeffRank: Object.entries(k.coeff_expl_data||{}).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]).findIndex(([b])=>b==="SGCI")+1,
  };

  // Textes IA
  const iaMix = sgciGross > 0
    ? "SGCI construit ses revenus à partir de deux sources principales :<br><br>"
      + "<b>Intérêts sur crédits : " + sgciIntPct + "%</b> — revenus générés par les prêts accordés aux clients. Ces revenus varient selon le volume de prêts et les taux d'intérêt.<br><br>"
      + "<b>Commissions : " + sgciCommPct + "%</b> — frais sur les services bancaires (virements, cartes, etc.). Ces revenus ne dépendent pas des taux — ils sont plus stables dans le temps.<br><br>"
      + (topCommB !== "SGCI"
        ? "<b>" + topCommB + "</b> a la part de commissions la plus élevée (" + topCommV + "%) — son modèle résiste mieux si les taux d'intérêt baissent.<br><br>"
        : "SGCI est la banque la plus diversifiée — avantage important face aux variations de taux.<br><br>")
      + "À retenir : la forte part d'intérêts de SGCI signifie un grand portefeuille de prêts. C'est une source de revenus importante, mais aussi la source principale des provisions analysées en Section ④."
    : "Composition des revenus en cours de chargement.";
  const effGap = topEffB !== "SGCI" && topEffV ? (parseFloat(topEffV) - parseFloat(sgciEffPNB)).toFixed(1) : null;
  const rnRankSGCI = Object.entries(k.rn_data||{}).sort((a,b)=>b[1].montant-a[1].montant).findIndex(([b])=>b==="SGCI")+1;
  const iaCascade = sgciPNBv2 > 0 && sgciRNv2 > 0
    ? "Ce graphique montre comment les revenus bruts se transforment en profit final, étape par étape :<br><br>"
      + "1. <b>PNB → RBE</b> : on déduit les charges d'exploitation (salaires, informatique, loyers…)<br>"
      + "2. <b>RBE → RE</b> : on déduit les provisions pour prêts douteux<br>"
      + "3. <b>RE → Résultat net</b> : on déduit l'impôt sur les bénéfices<br><br>"
      + "SGCI part de <b>" + (sgciPNBv2/1000).toFixed(0) + " Mds FCFA</b> de revenus et arrive à <b>" + (sgciRNv2/1000).toFixed(0) + " Mds</b> de profit net — soit <b>" + sgciEffPNB + "%</b> de conversion.<br><br>"
      + (topEffB !== "?" && topEffB !== "SGCI"
          ? "<b>" + topEffB + "</b> convertit mieux ses revenus en profit (<b>" + topEffV + "%</b>).<br>"
            + (effGap && parseFloat(effGap) > 5
              ? "L'écart vient principalement des pertes sur prêts — l'étape 2 (provisions) est celle qui pénalise le plus SGCI."
              : "La différence est faible — les deux modèles sont proches en efficacité.")
          : "SGCI convertit ses revenus en profit mieux que toute autre banque du marché.")
    : "Cascade des résultats en cours de chargement.";

  const S = function(num, title, sub){
    const sid = {"①":"s1","②":"s2","③":"s3","④":"s4","⑤":"s5","⑥":"s6"}[num]||"";
    return "<div id='" + sid + "' style='grid-column:span 12;padding:32px 0 12px;border-top:2px solid var(--line);margin-top:12px'>"
      + "<div style='display:flex;align-items:center;gap:16px'>"
      + "<div style='width:5px;height:44px;background:var(--accent-2);border-radius:3px;flex-shrink:0'></div>"
      + "<div><div style='font:900 26px/1.15 var(--display);color:var(--ink);letter-spacing:-.02em'>" + num + " · " + title + "</div>"
      + "<div style='font:500 13px var(--sans);color:var(--muted);margin-top:6px'>" + sub + "</div></div></div></div>";
  };

  const podArr  = sorted.length>=3 ? [sorted[1],sorted[0],sorted[2]] : sorted;
  const pcls    = ["g2","g1","g3"], ph=[120,160,96], prk=[2,1,3];
  const podHTML = podArr.map(function(e,i){
    if(!e) return "";
    var b = bankBy(e[0]);
    return "<div class='pod'><div class='lg'><img src='"+(b?b.lg:"")+"'></div>"
      +"<div class='nm'>"+e[0]+"</div><div class='amt'>"+(e[1]/1000).toFixed(1)+" Mds</div>"
      +"<div class='col "+pcls[i]+"' style='height:"+ph[i]+"px'>"+prk[i]+"</div></div>";
  }).join("");

  return `
  <div style="position:sticky;top:116px;z-index:20;margin-bottom:var(--s5);padding:6px 0;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--bg-deep) 72%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span style="font:700 9px var(--sans);color:#38D1F0;letter-spacing:.1em;text-transform:uppercase">📈 États Financiers</span>
      <div class="seg" style="margin:0">${btnAnx(1,"Année 1")}${btnAnx(2,"Année 2")}${btnAnx(3,"Année 3")}</div>
      <div class="seg" style="margin:0">${[["①","Position"],["②","Revenus"],["③","Efficience"],["④","Risque"]].map(([n,l],i)=>`<button class="sec-nav-btn" data-sec="s${i+1}" onclick="_paneShow('ef','s${i+1}')">${n} ${l}</button>`).join("")}</div>
      ${btnPDF("Santé Financière")}
    </div>
  </div>
  <div id="ef-stale-badge" style="display:none"></div>

  <div class="story" style="margin-bottom:var(--s5)">
    <div class="kicker">Santé financière · États Financiers · SGCI vs marché · ${anxKey}</div>
    <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:4px 20px;font:500 11px/1.6 var(--sans);color:var(--muted)">
      ${grps.map(g=>{
        const yrs=[1,2,3].map(n=>{const active=f.rn_anx===n;const yr=(leg[g.banks[0]]||{})["AN"+n]||"?";
          return `<span style="color:${active?"#FF3B4E":"var(--muted)"}">Année ${n} = <b style="color:${active?"var(--ink)":"var(--faint)"}">${yr}</b></span>`;
        }).join('<span style="color:var(--faint)"> · </span>');
        return `<span><b style="color:var(--ink)">${g.label}</b><span style="color:var(--faint)"> — </span>${yrs}</span>`;
      }).join('<span style="color:var(--line-2);margin:0 4px">|</span>')}
    </div>
  </div>

  <div class="bento">

    ${S("①","Position de marché","Où en est SGCI aujourd'hui par rapport aux 7 banques ivoiriennes ?")}

    <div class="tile hero c8" style="animation-delay:.05s">
      <div>
        <div class="label">SGCI · Résultat net ${anxKey} (${k.sgci_rn_annee}) · ${ord(k.sgci_rang_rn)} du marché ivoirien</div>
        <div class="big"><span data-count="${(k.sgci_rn/1000).toFixed(1)}" data-dec="1">0</span><span class="u">Mds FCFA</span></div>
      </div>
      <div class="cap">${ecartLabel} en résultat net · Part des bénéfices sectoriels : ${k.sgci_part_marche.toFixed(1)}% · Croissance AN1→AN3 : ${growthSigne}${k.sgci_growth_pct.toFixed(0)}%.</div>
      <div class="pills">
        <span class="pill">${ord(k.sgci_rang_rn)} du marché · ${anxKey}</span>
        <span class="pill">Part des bénéfices sectoriels : ${k.sgci_part_marche.toFixed(1)}%</span>
        <span class="pill g">Croissance AN1→AN3 : ${growthSigne}${k.sgci_growth_pct.toFixed(0)}%</span>
      </div>
      <div class="spark" id="ap-spark"></div>
    </div>

    <div class="tile gauge c4" style="animation-delay:.12s">
      <div class="eyebrow" style="align-self:flex-start">Rang concurrentiel — Résultat net</div>
      <div class="ring" style="margin-top:8px">
        <svg width="220" height="220" viewBox="0 0 220 220">
          <circle cx="110" cy="110" r="95" fill="none" stroke="var(--bg-raise)" stroke-width="14"/>
          <circle id="ap-arc" cx="110" cy="110" r="95" fill="none" stroke="url(#gg)" stroke-width="14" stroke-linecap="round" stroke-dasharray="597" stroke-dashoffset="597"/>
          <defs><linearGradient id="gg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#FF3B4E"/><stop offset="100%" stop-color="#9E0A18"/>
          </linearGradient></defs>
        </svg>
        <div class="ctr"><div class="rk">#${k.sgci_rang_rn}<small>/${Object.keys(k.rn_data||{}).length||CB_BANKS.length}</small></div><div class="lab">${k.sgci_rang_rn===1?"Leader":ord(k.sgci_rang_rn)}</div></div>
      </div>
      <div class="cap">${ord(k.sgci_rang_rn)} sur ${Object.keys(k.rn_data||{}).length||CB_BANKS.length} banques · ${anxKey} = ${k.sgci_rn_annee}</div>
    </div>

    <div class="tile insight c12" style="animation-delay:.14s">
      <div class="orb">✦</div>
      <div>
        <div class="e">Signal Analytique · États Financiers · ${anxKey} (${k.sgci_rn_annee})</div>
        <div class="h" data-ef="s1"><div data-ef-body><span style="opacity:.4">Analyse en cours…</span></div></div>
      </div>
      <button class="cta ml" onclick="askIA('Analyse la santé financière de SGCI par rapport au marché bancaire ivoirien')">Approfondir →</button>
    </div>

    <div style="grid-column:span 12;display:flex;gap:var(--s5)">
      ${sgciROE ? kpiTile("◈","rgba(255,176,32,.14)","#ffce7a","rgba(255,176,32,.3)",
        sgciROE,"ROE SGCI · Rendement des capitaux propres",
        "Résultat net / Capitaux propres · "+anxKey,".18","%","","","1") : ""}
      ${kpiTile("⬡","rgba(56,209,240,.13)","#7fe3f7","rgba(56,209,240,.3)",
        Math.round(k.fastest_pct),"Croissance AN1→AN3 · "+k.fastest_b,
        "Résultat net · données EF publiées",".24","%","+")}
      ${kpiTile("▦","rgba(229,20,43,.14)","#ff8a96","rgba(229,20,43,.3)",
        Math.abs(Math.round(k.ecart_pct_vs_2)),
        (k.ecart_pct_vs_2>=0?"Avance":"Retard")+" vs "+k.banque_2_nom+" (#2 RN)",
        "Résultat net comparé · "+anxKey+" = "+k.sgci_rn_annee,
        ".30","%",k.ecart_pct_vs_2>=0?"+":"-")}
      ${kpiTile("◷","rgba(34,197,94,.14)","#86efac","rgba(34,197,94,.3)",
        k.sgci_part_marche,"Part de marché · Bénéfices",
        "SGCI / total 7 banques · "+anxKey+" = "+k.sgci_rn_annee,".36","%","","","1")}
      ${sgciPNBShare > 0 ? kpiTile("◑","rgba(139,92,246,.14)","#c4b5fd","rgba(139,92,246,.3)",
        sgciPNBShare,"Part de marché · PNB",
        "PNB SGCI / total 7 banques · "+anxKey,".42","%","","","1") : ""}
    </div>

    <div class="tile c8 tpad" style="animation-delay:.44s">
      <div class="chead">
        <div><div class="tt" id="radar-title">Portrait compétitif ${RADAR_BANK||"SGCI"}</div>
        <div class="ts">5 dimensions · 50 = moyenne marché · ${anxKey}</div></div>
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">
        ${CB_BANK_ORDER.map(b =>
          `<button id="rbb-${b}" class="${b===RADAR_BANK?'on':''}"
            style="font-size:9px;padding:2px 8px;border-radius:4px"
            onclick="selectRadarBank('${b}')">${b}</button>`
        ).join("")}
      </div>
      <div id="ap-radar" style="height:260px"></div>
      <div id="radar-insight"></div>
    </div>

    <div class="tile c4 tpad" style="animation-delay:.50s;min-height:300px">
      <div class="chead"><div class="tt">Le podium · ${anxKey}</div><div class="ts">Résultat net · 7 banques · Mds FCFA</div></div>
      <div class="podium">${podHTML}</div>
      ${C((leader3!=="SGCI" ? _leaderFrame(leader3, sgciR3, sorted.length) + "<br>" : "")
        + "SGCI capte <b>" + sgciPct + "%</b> des bénéfices du secteur — " + _multTxt(sgciMult) + ".<br>"
        + "Le TOP 3 (" + sorted.slice(0,3).map(function(e){return e[0];}).join(", ") + ") concentre <b>" + top3pct + "%</b> du marché.<br>"
        + (leader3==="SGCI"
          ? "Cette position repose sur un avantage en revenus (→ Section ②) — " + Q("la rentabiliser pleinement est l'enjeu des Sections ③④.")
          : Q("Pour reprendre le leadership : améliorer la transformation des revenus en profit — Sections ③④.")), "podium")}
    </div>

    <div class="tile c7 tpad" style="animation-delay:.56s">
      <div class="chead"><div class="tt">${growTitle}</div><div class="ts">Croissance résultat net AN1→AN3 · 7 banques</div></div>
      <div id="ap-growth" style="height:310px"></div>
      ${C(
        (sgciG >= medianG
          ? "SGCI (<b>+" + sgciG + "%</b>) au-dessus de la médiane marché (+<b>" + medianG + "%</b>) — solide."
          : "SGCI (<b>+" + sgciG + "%</b>) sous la médiane (+<b>" + medianG + "%</b>).<br>Ce n'est pas une faiblesse : <b>effet de base</b> — partir de " + (sgciAN1v/1000).toFixed(0) + " Mds exige un effort absolu que personne d'autre ne peut encore égaler.")
        + "<br>"
        + (fastest[0]!=="?" && Math.round(fastest[1]) > 50
            ? Q("⚠ Alerte : " + fastest[0] + " multiplie son résultat par " + (1 + fastest[1]/100).toFixed(1) + "× sur 3 ans (+" + Math.round(fastest[1]) + "%).<br>En valeur absolue il reste loin, mais ce rythme exceptionnel signale une banque en transformation profonde — à surveiller dans 2-3 ans.")
            : (fasterN > 0 ? fasterN + " concurrent" + (fasterN>1?"s":"") + " croissent plus vite en rythme — vigilance sur la dynamique." : ""))
      , "growth")}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.60s;min-height:280px">
      <div class="chead">
        <div><div class="tt">${bumpTitle}</div><div class="ts">Classement par Résultat net · AN1 → AN2 → AN3 · 7 banques</div></div>
        <span class="chip">★ SGCI</span>
      </div>
      <div id="ap-bump" style="height:260px"></div>
      ${C(bumpAnalyse, "bump")}
    </div>

    <div class="tile c12 tpad" style="animation-delay:.62s;min-height:300px">
      <div class="chead">
        <div><div class="tt" id="ap-line-title">${lineTitle}</div><div class="ts" id="ap-line-sub">Résultat net · Mds FCFA · évolution AN1→AN3</div></div>
        <div class="seg" style="margin:0">
          <button class="line-filter-btn on" data-m="rn"  onclick="setLineMetric('rn')">Dynamique</button>
          <button class="line-filter-btn"        data-m="roe" onclick="setLineMetric('roe')">ROE</button>
          <button class="line-filter-btn"        data-m="pnb" onclick="setLineMetric('pnb')">PNB</button>
        </div>
      </div>
      <div id="ap-line" style="height:340px"></div>
      <div id="ap-line-analysis">${C(
        "SGCI passe de <b>" + (sgciAN1v/1000).toFixed(0) + " Mds</b> à <b>" + (sgciAN3v/1000).toFixed(0) + " Mds</b> de résultat net — trajectoire <b>régulière et dominante</b>.<br>Avance sur le #2 (" + second[0] + ") : <b>" + gap12 + " Mds</b>, un écart structurel.<br>"
        + (watch1[0]!=="?" && watch2[0]!=="?"
            ? "<b>Qui surveiller ?</b> <b>" + watch1[0] + "</b> (+<b>" + Math.round(watch1[1]) + "%</b>, RN " + watch1v.toFixed(0) + " Mds) et <b>" + watch2[0] + "</b> (+<b>" + Math.round(watch2[1]) + "%</b>, RN " + watch2v.toFixed(0) + " Mds) — ce sont les deux concurrents qui accélèrent le plus vite.<br>En valeur absolue ils restent loin, mais " + Q("leur vélocité est un signal précoce.") + "<br>La croissance modeste de SGCI (+<b>" + sgciG + "%</b>) s'explique par son <b>effet de base</b> : progresser sur un socle de " + (sgciAN1v/1000).toFixed(0) + " Mds exige un effort que ces banques n'ont pas encore à fournir."
            : "")
      , "line")}</div>
    </div>

    <div class="tile c7 tpad" style="animation-delay:.64s">
      <div class="chead"><div class="tt">${treeTitle}</div><div class="ts">Total résultat net · 7 banques · ${anxKey}</div></div>
      <div id="ap-tree" style="height:260px;margin-bottom:8px"></div>
      ${C((leader3!=="SGCI" ? _leaderFrame(leader3, sgciR3, sorted.length) + "<br>" : "")
        + "SGCI capte <b>" + sgciPct + "%</b> des bénéfices du secteur — " + _multTxt(sgciMult) + "."
        + (fastest[0]!=="?" && fastest[0]!=="SGCI"
          ? "<br>Mais <b>" + fastest[0] + "</b> croît à +<b>" + Math.round(fastest[1]) + "%</b> (Section ②).<br>"
            + (Math.round(fastest[1]) > 80
                ? Q("⚠ Rythme exceptionnel : à ce différentiel, l'écart se réduit structurellement — signal à surveiller sur 2-3 ans.")
                : Math.round(fastest[1]) > 40
                  ? Q("À ce rythme différentiel, la concentration se rééquilibrera progressivement — signal à surveiller sur 3-5 ans.")
                  : Q("Écart de croissance limité — la dominance de SGCI reste stable à moyen terme."))
          : "<br>SGCI domine en volume <i>et</i> en dynamique de marché — position exceptionnellement solide."), "tree")}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.66s;min-height:280px">
      <div class="chead"><div class="tt">Répartition des bénéfices · ${anxKey}</div><div class="ts">Part de chaque banque sur le total sectoriel</div></div>
      <div id="ap-share" style="height:240px"></div>
      ${C("SGCI : <b>" + sgciPct + "%</b> des bénéfices sectoriels — " + _multTxt(sgciMult) + ".<br>"
        + (leader3!=="SGCI" ? _leaderFrame(leader3, sgciR3, sorted.length) + "<br>" : "")
        + (sgciMargeV && bestMargeB!=="SGCI"
          ? (leader3==="SGCI"
              ? "Levier inexploité : si SGCI atteignait la marge de <b>" + bestMargeB + "</b> (" + bestMargeV.toFixed(1) + "% vs " + sgciMargeV.toFixed(1) + "% aujourd'hui) → part en bénéfices encore plus élevée sans crédit supplémentaire."
              : "Priorité : rattraper <b>" + leader3 + "</b> en volume ET aligner la marge sur <b>" + bestMargeB + "</b> (" + bestMargeV.toFixed(1) + "%) → double levier pour reprendre le leadership.")
          : ""), "share")}
    </div>

    ${S("②","Puissance commerciale","Qui génère le plus de revenus d'activité ?")}

    <div class="tile insight c12" style="animation-delay:.02s">
      <div class="orb">✦</div>
      <div><div class="e">Signal Analytique · Puissance commerciale</div><div class="h" data-ef="s2"><div data-ef-body><span style="opacity:.4">Analyse en cours…</span></div></div></div>
      <button class="cta ml" onclick="askIA('Analyse la puissance commerciale de SGCI : PNB et revenus comparés au marché ivoirien')">Approfondir →</button>
    </div>

    <div class="tile c6 tpad" style="animation-delay:.05s">
      <div class="chead">
        <div><div class="tt">${pnbRankS===1 ? "PNB · SGCI leader en revenus d'activité" : "PNB · qui génère le plus de revenus ?"}</div>
        <div class="ts">Produit Net Bancaire ${anxKey} · Mds FCFA · Vert = leader</div></div>
        <span class="chip">★ SGCI · Concurrents en gris</span>
      </div>
      <div id="ap-pnb" style="height:380px"></div>
      ${C("SGCI génère <b>" + (sgciPNBv/1000).toFixed(0) + " Mds</b> de PNB — <b>#" + pnbRankS + "/" + (Object.keys(pnbData).length||CB_BANKS.length) + "</b>. "
        + (isSGCIpnb1
            ? "C'est la base de revenus la plus élevée du marché (<b>" + pnbGap + "×</b> le niveau de " + pnb2b + "). Le PNB est la marge brute d'activité — chaque franc ici peut être converti en profit. "
              + (isSGCImargeLast ? Q("Paradoxe actuel : ce PNB dominant ne se traduit pas encore en marge nette supérieure — les fuites (risque crédit) en sont la cause. (→ Section ③④)")
                : "Cette avance en revenus se convertit de mieux en mieux en profit. <i>(→ Section ③)</i>")
            : Q("⚠ Signal : " + (pnbSorted2[0]?.[0]||"?") + " dépasse SGCI en PNB. La dynamique commerciale a changé — renforcer les revenus devient prioritaire."))
      , "pnb")}
    </div>

    <div class="tile c6 tpad" style="animation-delay:.08s">
      <div class="chead"><div class="tt">Transformation bancaire · Crédits vs Dépôts · ${anxKey}</div><div class="ts">Mds FCFA · Ratio crédits/dépôts = indicateur de liquidité</div></div>
      <div id="ap-cd" style="height:380px"></div>
      ${C((sgciCDRatio
        ? _volLeader(credData, "crédits") + " : <b>" + (sgciCred/1000).toFixed(0) + " Mds</b> de crédits distribués, financés par <b>" + (sgciDep/1000).toFixed(0) + " Mds</b> de dépôts collectés.<br>Ratio crédits/dépôts SGCI = <b>" + sgciCDRatio + "%</b> — pour chaque 100 F déposés, SGCI en prête " + sgciCDRatio + " à l'économie.<br>"
          + (sgciCDRatio >= 80 && sgciCDRatio <= 100 ? "C'est la <b>zone idéale</b> : ni trop prudente, ni trop risquée. <i>La BCEAO (Instruction n°016-2017 sur la liquidité) recommande que les banques maintiennent un équilibre entre transformation des dépôts et couverture des retraits — SGCI s'inscrit dans cette norme.</i> " : sgciCDRatio > 100 ? Q("Elle prête plus qu'elle ne collecte — risque de liquidité, hors des recommandations BCEAO. ") : Q("Zone sous-optimale : des dépôts 'dorment' sans être transformés en crédits — en dessous des recommandations BCEAO d'efficacité de transformation. "))
          + (bestCDRatio && bestCDRatio.b !== "SGCI"
              ? "Qui <b>transforme le mieux</b> ses dépôts en crédits ? C'est <b>" + bestCDRatio.b + "</b> avec <b>" + bestCDRatio.r + "%</b> — elle prête plus agressivement, ce qui génère plus de revenus d'intérêts par franc collecté. "
              : "SGCI est aussi la plus efficace en transformation. ")
          + (worstCDRatio && !overCD.includes(worstCDRatio.b) && worstCDRatio.b !== (bestCDRatio||{}).b
              ? "<b>" + worstCDRatio.b + "</b> transforme le moins (" + worstCDRatio.r + "%) : ses dépôts ne sont pas pleinement mobilisés — potentiel de revenus non exploité. "
              : "")
          + (overCD.length ? Q("⚠ " + overCD.join(", ") + " dépassent 100% : elles prêtent plus qu'elles ne collectent — risque de liquidité si les dépôts se retirent. ") : "")
          + "La taille du portefeuille de SGCI est à la fois la <b>source de son PNB dominant</b> et le terrain du risque crédit — " + Q("le vrai coût de cette stratégie est visible en Section ④.")
        : "Données insuffisantes."), "cd")}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.10s">
      <div class="chead">
        <div><div class="tt">Mix commercial · Comment le PNB est-il construit ?</div>
        <div class="ts">Intérêts / Commissions / Autres prod. · % · ${anxKey} · Trié par diversification</div></div>
      </div>
      <div id="ap-mix" style="height:340px"></div>
      ${C(iaMix, "mix")}
    </div>

    <div class="tile c7 tpad" style="animation-delay:.11s">
      <div class="chead">
        <div><div class="tt">Cascade P&L · PNB → RBE → RE → RN</div>
        <div class="ts">Fond clair = PNB · couches → RBE → RE · avant coloré = RN · ${anxKey} · Mds FCFA</div></div>
      </div>
      <div id="ap-cascade" style="height:340px"></div>
      ${C(iaCascade, "cascade")}
    </div>

    ${S("③","Efficacité opérationnelle","Qui transforme le mieux 1 FCFA de revenus en profit ?")}

    <div class="tile insight c12" style="animation-delay:.02s">
      <div class="orb">✦</div>
      <div><div class="e">Signal Analytique · Efficacité opérationnelle</div><div class="h" data-ef="s3"><div data-ef-body><span style="opacity:.4">Analyse en cours…</span></div></div></div>
      <button class="cta ml" onclick="askIA('Analyse l efficacité opérationnelle de SGCI : marge nette et coefficient exploitation comparés aux 7 banques CI')">Approfondir →</button>
    </div>

    <div class="tile c6 tpad" style="animation-delay:.05s">
      <div class="chead">
        <div><div class="tt">${sgciMargeV&&bestMargeB!=="SGCI" ? "Marge nette · SGCI en dessous de "+bestMargeB : "Marge nette · RN / PNB par banque"}</div>
        <div class="ts">Résultat net / PNB · % · ${anxKey} · Plus haut = plus efficient</div></div>
      </div>
      <div id="ap-marge" style="height:300px"></div>
      ${C(sgciMargeV
        ? "SGCI convertit <b>" + sgciMargeV.toFixed(1) + "%</b> de son PNB en profit net — <b>#" + margeRankSGCI + "/" + margeNbBanques + "</b>.<br>"
          + (isSGCImargeLast
            ? "C'est la conversion la plus faible du marché malgré le plus grand PNB.<br>"
            : margeRankSGCI <= 2 ? "Excellente position — SGCI est dans le TOP 2.<br>" : "Position intermédiaire — marge à améliorer.<br>")
          + (bestMargeB!=="SGCI" ? "<b>" + bestMargeB + "</b> mène avec <b>" + bestMargeV.toFixed(1) + "%</b> (+<b>" + (bestMargeV-sgciMargeV).toFixed(1) + " pts</b>).<br>" : "SGCI est en tête sur ce critère.<br>")
          + (isSGCImargeLast || margeRankSGCI > margeNbBanques/2
            ? "Regardez le coefficient d'exploitation ci-contre — SGCI a les meilleures charges du marché. Le frein n'est <b>pas</b> là.<br>" + Q("Le diagnostic pointe vers le coût du risque crédit. (→ Section ④)")
            : "SGCI progresse sur la conversion revenus→profit. Maintenir la discipline sur les charges et le risque pour consolider.")
        : "Marge nette en cours de chargement.", "marge")}
    </div>

    <div class="tile c6 tpad" style="animation-delay:.08s">
      <div class="chead">
        <div><div class="tt">Coefficient d'exploitation · ${anxKey}</div>
        <div class="ts">Charges / PNB · % · Plus bas = plus efficient</div></div>
      </div>
      <div id="ap-coeff" style="height:300px"></div>
      ${C((() => {
        const sgciCoeff = COEFF_EXPL_DATA ? COEFF_EXPL_DATA["SGCI"] : null;
        const bestCoeffE = sgciCoeff && Object.entries(COEFF_EXPL_DATA||{}).filter(([b])=>b!=="SGCI").sort((a,b)=>a[1]-b[1])[0];
        const allCoeff = Object.entries(COEFF_EXPL_DATA||{}).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]);
        const sgciCoeffRank = allCoeff.findIndex(([b])=>b==="SGCI")+1;
        const bestCoeffB = allCoeff[0]?.[0]||"?", bestCoeffV = allCoeff[0]?.[1]||0;
        const bceaoZone = sgciCoeff < 40 ? "excellence" : sgciCoeff < 50 ? "bon" : sgciCoeff < 60 ? "acceptable" : "surveillance";
        return sgciCoeff
          ? "SGCI : <b>" + sgciCoeff.toFixed(1) + "%</b> — <b>#" + sgciCoeffRank + "/" + allCoeff.length + "</b> du marché (plus bas = plus efficient).<br>"
            + (sgciCoeffRank===1
                ? "C'est <b>le meilleur coefficient du marché</b>. Pour 100 F de revenus, " + sgciCoeff.toFixed(0) + " F seulement en charges opérationnelles — excellence de gestion."
                : sgciCoeffRank<=3
                  ? "Position solide (top 3). Meilleur : <b>" + bestCoeffB + "</b> à " + bestCoeffV.toFixed(1) + "% — écart réductible."
                  : Q("⚠ Coefficient #" + sgciCoeffRank + "/" + allCoeff.length + ". Leader : <b>" + bestCoeffB + "</b> à " + bestCoeffV.toFixed(1) + "% — réduire les charges est prioritaire."))
            + "<br><i>BCEAO : < 60% acceptable · < 50% bon · < 40% excellence. SGCI en zone <b>" + bceaoZone + "</b>.</i>"
          : "Coefficient d'exploitation en cours de chargement.";
      })(), "coeff")}
    </div>

    <div class="tile c12 tpad" style="animation-delay:.10s;min-height:280px">
      <div class="chead">
        <div><div class="tt">Évolution du coefficient d'exploitation · 3 ans</div>
        <div class="ts">Charges générales / PNB · % · Plus bas = meilleure efficacité opérationnelle · BCEAO : &lt; 60% acceptable · &lt; 50% bon · &lt; 40% excellence</div></div>
      </div>
      <div id="ap-coeff-line" style="height:320px"></div>
      ${C((() => {
        const S = COEFF_SERIES || {};
        const sgciYrs = S["SGCI"] ? Object.entries(S["SGCI"]).sort((a,b)=>+a[0]-+b[0]) : [];
        if(!sgciYrs.length) return "Données en cours de chargement.";
        const sgciFirst = sgciYrs[0], sgciLast = sgciYrs[sgciYrs.length-1];
        const sgciDelta = sgciLast[1] - sgciFirst[1];

        // Rang final de chaque banque (sur sa dernière année disponible)
        const lastSnap = Object.entries(S)
          .map(([b,yv])=>{ const e=Object.entries(yv).sort((a,b)=>+a[0]-+b[0]); return [b,e.at(-1)[1]]; })
          .sort((a,b)=>a[1]-b[1]);
        const sgciRank = lastSnap.findIndex(([b])=>b==="SGCI")+1;

        // Vitesse de décroissance de chaque banque (delta sur toute la période)
        const deltas = Object.entries(S).map(([b,yv])=>{
          const yrs = Object.entries(yv).sort((a,b)=>+a[0]-+b[0]);
          if(yrs.length < 2) return null;
          const d = yrs.at(-1)[1] - yrs[0][1]; // négatif = amélioration
          return [b, d, yrs[0], yrs.at(-1)];
        }).filter(Boolean).sort((a,b)=>a[1]-b[1]); // trié du plus rapide au moins rapide

        // #1 décroissant (hors SGCI)
        const fastest = deltas.filter(([b])=>b!=="SGCI")[0];
        // #1 décroissant toutes banques confondues
        const fastestAll = deltas[0];

        const bceao = sgciLast[1] < 40 ? "excellence BCEAO (< 40%)" : sgciLast[1] < 50 ? "zone bon (< 50%)" : "zone acceptable";
        const sgciGapToFastest = fastest ? sgciLast[1] - fastest[3][1] : 0;

        // SGCI
        let txt = `SGCI : <b>${sgciFirst[1].toFixed(1)}%</b> (${sgciFirst[0]}) → <b>${sgciLast[1].toFixed(1)}%</b> (${sgciLast[0]})`;
        txt += sgciDelta < 0
          ? ` — <b>−${Math.abs(sgciDelta).toFixed(1)}pt</b>, ${bceao}, rang <b>#${sgciRank}/${lastSnap.length}</b>.`
          : ` — <b>+${sgciDelta.toFixed(1)}pt</b> (légère hausse sur la période), ${bceao}, rang <b>#${sgciRank}/${lastSnap.length}</b>.`;

        // Concurrent qui décroît le plus vite
        if(fastest){
          const [fb, fd, ff, fl] = fastest;
          const gapStart = S[fb][ff[0]] - sgciFirst[1];
          txt += `<br><br><b>${fb}</b> affiche la décroissance la plus rapide du marché : <b>${ff[1].toFixed(1)}%</b> (${ff[0]}) → <b>${fl[1].toFixed(1)}%</b> (${fl[0]}), soit <b>−${Math.abs(fd).toFixed(1)}pt</b> en ${+fl[0]-+ff[0]} an${+fl[0]-+ff[0]>1?'s':''}. `;
          if(gapStart > 0){
            txt += `L'écart avec SGCI était de <b>+${gapStart.toFixed(1)}pt</b> en ${ff[0]} ; il est tombé à <b>${sgciGapToFastest > 0 ? '+' : ''}${sgciGapToFastest.toFixed(1)}pt</b> en ${fl[0]}. `;
          }
          if(fl[1] <= sgciLast[1] + 5){
            txt += Q(`${fb} est désormais dans la même zone d'efficacité que SGCI — l'avantage opérationnel de SGCI s'est quasi-effacé sur ce concurrent.`);
          } else if(fl[1] < 50){
            txt += Q(`Si ce rythme se maintient, ${fb} rejoint SGCI/SIB dans la zone excellence d'ici 1 à 2 ans.`);
          } else {
            txt += Q(`${fb} progresse fortement mais reste au-dessus de 50% — l'écart avec SGCI est encore significatif.`);
          }
        }

        // Tableau synthèse vitesse de chaque concurrent
        const others = deltas.filter(([b])=>b!=="SGCI");
        if(others.length){
          txt += `<br><br><b>Vitesse de décroissance sur la période :</b> `
               + others.map(([b,d,f,l])=> d < 0
                  ? `<b>${b}</b> −${Math.abs(d).toFixed(1)}pt`
                  : `<b>${b}</b> +${d.toFixed(1)}pt ↑`
               ).join(' · ')
               + ` (plus négatif = plus efficace).`;
        }
        return txt;
      })(), "coeff_line")}
    </div>

    ${S("④","Qualité du risque & création de valeur","Qui prend les bons risques et crée le plus de valeur ?")}

    <div class="tile insight c12" style="animation-delay:.02s">
      <div class="orb">✦</div>
      <div><div class="e">Signal Analytique · Qualité du risque</div><div class="h" data-ef="s4"><div data-ef-body><span style="opacity:.4">Analyse en cours…</span></div></div></div>
      <button class="cta ml" onclick="askIA('Analyse le coût du risque de SGCI et la qualité de son portefeuille de crédits par rapport aux banques ivoiriennes')">Approfondir →</button>
    </div>

    <div class="tile c7 tpad" style="animation-delay:.05s">
      <div class="chead">
        <div><div class="tt">${sgciCRv&&sgciCRv>5 ? "Coût du risque / PNB · SGCI : "+sgciCRv.toFixed(1)+"% ("+anxKey+")" : "Coût du risque / PNB · "+anxKey}</div>
        <div class="ts">Provisions créances douteuses / PNB · % · Plus bas = portefeuille plus sain</div></div>
      </div>
      <div id="ap-cr" style="height:260px"></div>
      ${C(sgciCRv
        ? "· SGCI provisionne <b>" + sgciCRv.toFixed(1) + "%</b> de son PNB — soit <b>" + Math.round(sgciCRv/100*(sgciPNBv||0)/1000) + " Mds FCFA</b> qui quittent le résultat chaque année sans contribuer au profit.<br>"
          + "<i>La BCEAO (Instruction n°094-01-M-2016) impose aux banques de classer leurs créances en 4 catégories et de provisionner selon leur niveau de risque : créances incertaines (20%), douteuses (50%), litigieuses (100%). Un coût du risque de " + sgciCRv.toFixed(1) + "% révèle une proportion significative de créances dégradées dans le portefeuille SGCI.</i><br>"
          + (fastCRmult && fastest[0]!=="?" ?
            "· <b>" + fastest[0] + "</b> (le concurrent le plus dynamique, +" + Math.round(fastest[1]) + "%) n'est qu'à <b>" + (fastCRv||0).toFixed(1) + "%</b> — soit <b>" + fastCRmult + "× moins</b> que SGCI.<br>"
            + K("Ce n'est pas une coïncidence : une meilleure qualité de portefeuille libère du profit qui finance la croissance.") + "<br>" : "")
          + (bestCRb!=="SGCI" ? "· Meilleur du marché : <b>" + bestCRb + "</b> à <b>" + bestCRv.toFixed(1) + "%</b>.<br>" : "")
          + (gainCR>0 ? "· " + G("Si SGCI atteignait ce niveau → +" + gainCR + " Mds FCFA de RN supplémentaires") + " — sans aucune hausse de revenus, sans aucun nouveau crédit.<br>" : "")
          + (sgciCRisWorst
              ? Q("PNB #1 · Charges #1 · mais coût du risque qui efface l'avantage — c'est le seul levier à actionner en priorité.")
              : Q("PNB #1 · Charges #1 · coût du risque #" + sgciCRrank + "/" + crSorted.length + " — maîtrise en cours. Maintenir la trajectoire."))
        : "Coût du risque en cours de chargement.", "cnr")}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.08s">
      <div class="chead">
        <div><div class="tt">ROE · ${anxKey} · Qui rend le mieux aux actionnaires ?</div>
        <div class="ts">Résultat net / Capitaux propres · % · Plus haut = meilleur</div></div>
      </div>
      <div id="ap-roe" style="height:260px"></div>
      ${C(sgciROEv2
        ? "· SGCI est <b>#" + roeRankS + "/" + roeSorted.length + " en ROE</b> (" + sgciROEv2.toFixed(1) + "%) malgré son #1 en résultat net absolu.<br>"
          + "· <b>" + roeLeaderB + "</b> rémunère mieux ses actionnaires : <b>" + roeLeaderV.toFixed(1) + "%</b>.<br>"
          + K("Ce paradoxe confirme tout le fil conducteur : #1 en volume · #1 en charges · mais le coût du risque érode la valeur créée par franc de capital.")
          + "<br>" + (gainCR>0 ? G("L'équation de la DG : chaque Md récupéré sur le coût du risque améliore simultanément RN + marge nette + ROE — un seul levier, trois résultats.") : "")
        : "ROE en cours de chargement.", "roe")}
    </div>

    <div class="tile c12 tpad" style="animation-delay:.11s;min-height:280px">
      <div class="chead">
        <div><div class="tt">CNR / Encours de crédit · Évolution 3 ans</div>
        <div class="ts">Coût Net du Risque / Créances clientèle · points de base (pb) · Plus bas = portefeuille plus sain · BCEAO : &lt; 100pb excellent · 100–200pb acceptable · &gt; 200pb surveillance</div></div>
      </div>
      <div id="ap-cnr-line" style="height:320px"></div>
      ${C((() => {
        const S = CNR_SERIES || {};
        const sgciYrs = S["SGCI"] ? Object.entries(S["SGCI"]).sort((a,b)=>+a[0]-+b[0]) : [];
        if(!sgciYrs.length) return "Données en cours de chargement.";
        const sgciFirst = sgciYrs[0], sgciLast = sgciYrs.at(-1);
        const sgciDelta = sgciLast[1] - sgciFirst[1];
        const sgciEncours = (Object.values(S["SGCI"]||{}).at(-1)||0);

        // Snapshot dernière année dispo par banque
        const lastSnap = Object.entries(S)
          .map(([b,yv])=>{ const e=Object.entries(yv).sort((a,b)=>+a[0]-+b[0]); return [b,e.at(-1)[1],e.at(-1)[0]]; })
          .sort((a,b)=>a[1]-b[1]);
        const sgciRank = lastSnap.findIndex(([b])=>b==="SGCI")+1;
        const best = lastSnap[0];
        const mktMedian = [...lastSnap.map(([,v])=>v)].sort((a,b)=>a-b)[Math.floor(lastSnap.length/2)];

        // Coût en Mds FCFA : si SGCI avait le CNR du meilleur concurrent
        // CNR = pb × encours / 10000 → encours SGCI ≈ CNR_last / sgciLast[1] × 10000
        const encoursSGCI = sgciLast[1] > 0 ? ((Object.values(S["SGCI"]||{}).at(-1)||0)) : 0;
        // On reconstitue l'encours depuis CNR_absolu (stocké en pb) : non disponible ici
        // → on calcule le gain relatif en Mds en utilisant le CNR absolu depuis kpis
        const gainPb = best ? sgciLast[1] - best[1] : 0;

        // Concurrent qui s'est le plus amélioré sur la période
        const improvers = Object.entries(S).filter(([b])=>b!=="SGCI").map(([b,yv])=>{
          const yrs = Object.entries(yv).sort((a,b)=>+a[0]-+b[0]);
          if(yrs.length<2) return null;
          return [b, yrs.at(-1)[1]-yrs[0][1], yrs[0], yrs.at(-1)];
        }).filter(Boolean).sort((a,b)=>a[1]-b[1]);
        const topImprover = improvers[0];

        // Phrase 1 — position SGCI
        let txt = `SGCI : <b>${sgciFirst[1].toFixed(0)}pb</b> (${sgciFirst[0]}) → <b>${sgciLast[1].toFixed(0)}pb</b> (${sgciLast[0]}) — rang <b>#${sgciRank}/${lastSnap.length}</b>, dernier du marché.`;
        txt += ` Pendant ce temps, la médiane du marché est à <b>${mktMedian.toFixed(0)}pb</b>.`;

        // Phrase 2 — accélération
        if(sgciDelta > 0){
          txt += `<br><br>Le CNR de SGCI s'aggrave de <b>+${sgciDelta.toFixed(0)}pb</b> en ${+sgciLast[0]-+sgciFirst[0]} an${+sgciLast[0]-+sgciFirst[0]>1?'s':''} — soit <b>${(sgciLast[1]/mktMedian).toFixed(1)}×</b> la médiane du marché. `;
          if(sgciLast[1] > 150) txt += Q(`SGCI se rapproche de la zone de surveillance BCEAO (> 200pb) — c'est le signal de risque le plus sérieux de ce bilan.`);
        }

        // Phrase 3 — concurrent le plus représentatif (SIB si disponible, sinon bestImprover)
        if(topImprover){
          const [ib,,ifr,ila] = topImprover;
          const d = ila[1]-ifr[1];
          txt += `<br><br><b>Contre-exemple : ${ib}</b> — <b>${ifr[1].toFixed(0)}pb</b> (${ifr[0]}) → <b>${ila[1].toFixed(0)}pb</b> (${ila[0]}), soit <b>−${Math.abs(d).toFixed(0)}pb</b> sur la période. `;
          if(ila[1] < 50 && ifr[1] > 60){
            txt += `${ib} a réussi à diviser son coût du risque par plus de ${(ifr[1]/ila[1]).toFixed(1)}× — ce niveau d'amélioration est atteignable, il faut une politique de sélection crédit et de recouvrement beaucoup plus stricte.`;
          } else if(d < -20){
            txt += `Ce niveau d'amélioration démontre que la trajectoire inverse est possible avec une politique de crédit plus disciplinée.`;
          }
        }

        // Phrase 4 — classement synthèse
        txt += `<br><br><b>Classement ${sgciLast[0]} :</b> ` + lastSnap.map(([b,v])=>`<b>${b}</b> ${v.toFixed(0)}pb`).join(' · ');
        return txt;
      })(), "cnr_line")}
    </div>

  </div>`;
}

function afterApercu(){
  updateTickerLabel(); // ticker label suit l'ANx sélectionné
  runCounts(document);
  const k   = KPI_DATA;
  const arc = document.getElementById("ap-arc");
  if(arc && k){
    const nbB   = Object.keys(k.rn_data||{}).length || CB_BANKS.length;
    const score = 1 - (k.sgci_rang_rn - 1) / Math.max(nbB - 1, 1);
    requestAnimationFrame(()=>{
      arc.style.transition = "stroke-dashoffset 1.6s var(--ease)";
      arc.style.strokeDashoffset = 597 * (1 - score);
    });
  }
  // Sparkline SGCI (série complète)
  const sgci = RN_SERIES.SGCI;
  if(sgci && document.getElementById("ap-spark")){
    Plotly.newPlot("ap-spark", [{
      x: sgci.years, y: sgci.values,
      mode:"lines", fill:"tozeroy",
      line:{color:"#FF3B4E",width:2,shape:"spline"},
      fillcolor:"rgba(229,20,43,.18)", hoverinfo:"skip",
    }], {
      margin:{l:0,r:0,t:10,b:0},
      paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{visible:false}, yaxis:{visible:false}, showlegend:false,
    }, { displayModeBar:false, staticPlot:true });
  }
  // Bar chart avec double RAF pour lire la hauteur flex après layout
  requestAnimationFrame(()=>requestAnimationFrame(()=>chartRNVsMarche("ap-rn")));
  chartRadar("ap-radar");
  chartBumpRank("ap-bump", 260);
  // Section ②
  chartPNBbar("ap-pnb", 380);
  chartCreditDepot("ap-cd", 380);
  chartMixPNB("ap-mix", 340);
  chartCascadePL("ap-cascade", 340);
  // Reset filtre ligne et sauvegarde l'état RN pour restauration
  _LINE_METRIC = 'rn';
  _rnLineTitle    = (document.getElementById('ap-line-title')  || {}).textContent || '';
  _rnAnalysisHtml = (document.getElementById('ap-line-analysis') || {}).innerHTML  || '';
  _drawApLine();
  chartGrowth("ap-growth", 310);
  // Section ③
  chartMargeNette("ap-marge", 300);
  chartCoeffExpl("ap-coeff", 300);
  chartSeriesLine("ap-coeff-line", COEFF_SERIES, 320, "%", "%");
  chartTreemap("ap-tree");
  chartMarketShare("ap-share", 240);
  // Section ④
  chartCoutRisque("ap-cr", 260);
  chartROEbar("ap-roe", 260);
  chartSeriesLine("ap-cnr-line", CNR_SERIES, 320, "pb", "pb");
  const _ALL = ["ap-rn","ap-radar","ap-bump","ap-pnb","ap-cd","ap-mix","ap-cascade",
                "ap-line","ap-growth","ap-marge","ap-coeff","ap-coeff-line","ap-tree","ap-share",
                "ap-cr","ap-roe","ap-cnr-line"];
  window.__redraw = ()=>{
    _ALL.forEach(id=>{try{Plotly.purge(id);}catch(e){}});
    requestAnimationFrame(()=>requestAnimationFrame(()=>chartRNVsMarche("ap-rn")));
    chartRadar("ap-radar"); chartBumpRank("ap-bump", 260);
    chartPNBbar("ap-pnb", 380); chartCreditDepot("ap-cd", 380);
    chartMixPNB("ap-mix", 340); chartCascadePL("ap-cascade", 340);
    _drawApLine(); chartGrowth("ap-growth", 310);
    chartMargeNette("ap-marge", 300); chartCoeffExpl("ap-coeff", 300);
    chartSeriesLine("ap-coeff-line", COEFF_SERIES, 320, "%", "%");
    chartTreemap("ap-tree"); chartMarketShare("ap-share", 240);
    chartCoutRisque("ap-cr", 260); chartROEbar("ap-roe", 260);
    chartSeriesLine("ap-cnr-line", CNR_SERIES, 320, "pb", "pb");
  };

  // ── Mode ONGLETS : n'afficher que la section sélectionnée ──
  _paneInit('ef', ['s1','s2','s3','s4']);

  // ── Habillage LLM : remplace les analyses-template par des analyses rédigées
  //    par le LLM (complémentaires, non répétitives). Le template reste en fallback. ──
  _loadEFAnalysesLLM();
}

// Injecte les analyses EF rédigées par le LLM dans chaque bloc [data-ef].
// Reproductible & évolutif : le backend calcule tout depuis la BD et met en cache.
// Badge visible « analyse de secours » — affiché quand le backend indique stale:true (le
// dernier rafraîchissement a échoué et on sert la DERNIÈRE analyse réussie, pas une nouvelle).
// Sans ça, un texte restauré était indiscernable d'une génération fraîche.
/* AVERTISSEMENT D'EXPLOITATION, RÉSERVÉ À L'ADMINISTRATEUR (2026-08-11).
   « Analyse de secours — dernière génération réussie le… » décrit l'état du service de
   rédaction, pas la valeur du contenu : les CHIFFRES affichés restent exacts, ils viennent de
   la base. Un directeur du marketing ne peut ni relancer une génération ni décider d'attendre ;
   le message ne fait que le conduire à douter d'un tableau qui, lui, est juste. Seul
   l'administrateur agit dessus, seul il le voit. */
/* QUI VOIT LES AVERTISSEMENTS D'EXPLOITATION (2026-08-11).
   Quota epuise, analyse de secours, IA indisponible : tous decrivent l'etat du service de
   REDACTION, jamais la justesse des chiffres — ceux-ci viennent de la base et restent exacts.
   Un directeur metier ne peut rien y faire ; le message ne fait que le conduire a douter d'un
   tableau qui est juste. Un seul helper, pour ne pas en oublier un au prochain ajout. */
function _voitAvertissementsTechniques(){
  return !!(SB_UTILISATEUR && SB_UTILISATEUR.role === "admin");
}

function _showStaleBadge(elId, meta){
  const el = document.getElementById(elId);
  if(!el) return;
  if(!_voitAvertissementsTechniques() || !meta || !meta.stale){ el.style.display='none'; el.innerHTML=''; return; }
  let dateTxt = 'date inconnue';
  if(meta.generated_at){
    try{
      const d = new Date(meta.generated_at);
      dateTxt = d.toLocaleString('fr-FR', {day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});
    }catch(e){}
  }
  el.style.cssText = 'display:block;margin:8px 0;padding:9px 13px;background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;font:600 11.5px var(--sans);color:#92400E';
  el.innerHTML = `⚠️ Analyse de secours — dernière génération réussie le <b>${dateTxt}</b> (le dernier rafraîchissement a échoué, aucune donnée n'est perdue mais ce texte n'est pas le plus récent).`;
}

async function _loadEFAnalysesLLM(retry=0){
  const f   = (typeof APERCU_FILTERS !== "undefined") ? APERCU_FILTERS : {};
  const seg = f.frais_seg || "Particuliers";
  const anx = f.rn_anx    || 3;
  // ANTI-BLOCAGE : au 1ᵉʳ affichage d'un filtre jamais ouvert, le LLM génère (~10-20 s) puis cache.
  // Si la génération échoue (quota, réseau), on RÉESSAIE automatiquement (jusqu'à 4×, 25 s d'écart)
  // pour ne jamais laisser un « Analyse en cours… » coincé.
  const _again = () => { if(retry < 4) setTimeout(()=>_loadEFAnalysesLLM(retry+1), 25000); };
  try{
    const r = await fetch(`/api/ef_analyses_llm?segment=${encodeURIComponent(seg)}&anx=${anx}`);
    if(!r.ok){ _again(); return; }
    const j = await r.json();
    const A = (j && j.analyses) || {};
    if(!Object.keys(A).length){ _again(); return; }           // génération échouée → on retentera
    _showStaleBadge('ef-stale-badge', {stale: j.stale, generated_at: j.generated_at});
    window._EF_LLM = A;   // dispo pour la bascule ROE/PNB du graphe ligne (line_roe / line_pnb)
    document.querySelectorAll('[data-ef]').forEach(box=>{
      const key = box.getAttribute('data-ef');
      const txt = A[key];
      if(!txt) return;
      const body = box.querySelector('[data-ef-body]');
      if(body) body.innerHTML = txt;
    });
    // Ré-capture l'analyse RN (désormais LLM) pour la restauration du filtre ligne.
    const la = document.getElementById('ap-line-analysis');
    if(la) _rnAnalysisHtml = la.innerHTML;
  }catch(e){ _again(); }
}

function kpiTile(ic,ib,icc,ibd,count,label,sub,delay,suf="",pre="",tone="",dec=""){
  const dl = tone==="warning"
    ? `<span class="dl" style="background:rgba(255,176,32,.14);color:#ffce7a">▲ hausse</span>` : "";
  const decAttr = dec ? `data-dec="${dec}"` : "";
  return `<div class="tile kpi c3" style="animation-delay:${delay}s">
    <div class="ic" style="--ib:${ib};--ic:${icc};--ibd:${ibd}">${ic}</div>${dl}
    <div><div class="v"><span data-count="${count}" data-suf="${suf}" ${decAttr}>${pre}0</span></div>
    <div class="l">${label}</div>
    <div class="l" style="color:var(--faint);margin-top:3px">${sub}</div></div>
  </div>`;
}

function buildSignalIA(k, efOnly=false){
  if(!k) return "Chargement des données en cours…";
  const f   = APERCU_FILTERS;
  const anx = `Année ${f.rn_anx}`;
  const ord = n => n===1?"1ᵉʳ":n===2?"2ᵉ":n===3?"3ᵉ":`${n}ᵉ`;
  const mds = v => `${(v/1000).toFixed(0)}`;   // renvoie le NOMBRE seul ; « Mds »/« Mds FCFA » est ajouté par l'appelant

  const pts = [];
  const allRN = Object.entries(k.rn_data || {}).sort((a,b) => b[1]-a[1]);

  // ── 1. POSITION ───────────────────────────────────────────────────────
  const top3 = allRN.slice(0,3).map(([b,v],i) => `· ${ord(i+1)} <b>${b}</b> — ${mds(v)} Mds FCFA`).join("<br>");
  if(k.sgci_rang_rn === 1){
    pts.push(
      `SGCI réalise le meilleur profit annuel du marché — <b>${mds(k.sgci_rn)} Mds FCFA</b> de résultat net.<br>` +
      `Cela représente <b>${k.sgci_part_marche.toFixed(1)}%</b> de l'ensemble des bénéfices des 7 banques ivoiriennes.<br>` +
      `Son avance sur le deuxième (<b>${k.banque_2_nom}</b>, ${mds(k.banque_2_rn)} Mds) est de <b>+${k.ecart_pct_vs_2.toFixed(0)}%</b>.<br><br>` +
      `Les 3 premières banques :<br>${top3}`
    );
  } else {
    const [leaderB, leaderV] = allRN[0] || ["?",0];
    pts.push(
      `SGCI est <b>${ord(k.sgci_rang_rn)} du marché</b> avec <b>${mds(k.sgci_rn)} Mds FCFA</b> de profit annuel.<br>` +
      `La banque en tête est <b>${leaderB}</b> avec <b>${mds(leaderV)} Mds</b>.<br><br>` +
      `Les 3 premières banques :<br>${top3}`
    );
  }

  // ── 2. DYNAMIQUE ─────────────────────────────────────────────────────
  if(k.fastest_b === "SGCI"){
    pts.push(
      `<b>Croissance :</b> SGCI est aussi la <b>plus dynamique du marché</b> — <b>+${k.fastest_pct.toFixed(0)}%</b> sur 3 ans.<br>` +
      `Double leadership : volume absolu ET vitesse de progression.`
    );
  } else {
    const mult = (1 + k.fastest_pct/100).toFixed(1);
    pts.push(
      `SGCI a augmenté son profit de <b>+${k.sgci_growth_pct.toFixed(0)}%</b> sur 3 ans.<br>` +
      `Ce rythme peut sembler modeste, mais c'est normal : une banque qui génère déjà un profit élevé doit fournir un effort bien plus grand pour progresser encore — c'est ce qu'on appelle l'effet de base.<br><br>` +
      `⚠ À surveiller : <b>${k.fastest_b}</b> est le concurrent qui a le plus accéléré sur 3 ans (<b>+${k.fastest_pct.toFixed(0)}%</b>, soit ×${mult} son profit de départ).<br>` +
      `Cette croissance rapide s'explique souvent par une meilleure gestion des prêts accordés — moins de pertes = plus de profit disponible pour investir.`
    );
  }

  // ── 3. ALERTE AVANCE FRAGILE ─────────────────────────────────────────
  if(k.sgci_rang_rn === 1 && k.ecart_pct_vs_2 < 15){
    pts.push(
      `⚠ L'avance de SGCI sur son principal concurrent (<b>${k.banque_2_nom}</b>) n'est que de <b>${k.ecart_pct_vs_2.toFixed(1)}%</b>.<br>` +
      `Cet écart est faible et peut se réduire rapidement. Consolider la position de leader est une priorité avant de lancer de nouvelles initiatives.`
    );
  }

  // ── 4. CB (optionnel) ────────────────────────────────────────────────
  if(!efOnly){
    const virSGCI = k.sgci_virement;
    const virData = k.virement_data || {};
    const virVals = Object.values(virData).filter(v=>v>0).sort((a,b)=>a-b);
    if(virSGCI > 0 && virVals.length >= 2){
      const median   = virVals[Math.floor(virVals.length/2)];
      const posLabel = virSGCI < median ? "en dessous de la médiane — marge de hausse disponible"
                     : virSGCI === median ? "dans la médiane du marché"
                     : "au-dessus de la médiane — prudence avant toute hausse";
      pts.push(
        `<b>Tarif CB — Virement UEMOA :</b> SGCI à <b>${virSGCI.toLocaleString("fr-FR")} FCFA</b> — ${posLabel}.<br>` +
        `Médiane concurrents : ${median.toLocaleString("fr-FR")} FCFA. → Détail dans <b>Conditions bancaires</b>.`
      );
    }
  }

  return `<div style="display:flex;flex-direction:column;gap:10px;font:500 13px/1.65 var(--sans)">
    ${pts.map(p => `<div style="display:flex;gap:10px;align-items:flex-start">
      <span style="color:#FF3B4E;flex-shrink:0;margin-top:3px;font-size:11px">▸</span>
      <span>${p}</span>
    </div>`).join("")}
  </div>`;
}

// Met à jour le label du ticker selon l'ANx actif et l'année SGCI réelle
function updateTickerLabel(){
  const tkLabel = document.getElementById("tk-label");
  if(!tkLabel) return;
  const f   = APERCU_FILTERS;
  const anx = `Année ${f.rn_anx}`;
  const yr  = KPI_DATA ? ((KPI_DATA.rn_annees || {})["SGCI"] || "") : "";
  tkLabel.textContent = `Résultat net · ${anx}${yr ? " (" + yr + ")" : ""} · Mds FCFA (milliards)`;
}

async function setApercuFilter(key, value){
  APERCU_FILTERS[key] = value;
  await reloadKpis();
  go("apercu");
}

/* ════════════ ANALYSE (Tarifs + Performance) ════════════════════════ */
let ANALYSE_TAB = "tarifs";
function setAnalyse(t){ ANALYSE_TAB=t; go("analyse"); }

function pageAnalyse(){
  const seg = `<div class="seg" style="margin-bottom:var(--s6)">
    <button class="${ANALYSE_TAB==='tarifs'?'on':''}" onclick="setAnalyse('tarifs')">Tarifs</button>
    <button class="${ANALYSE_TAB==='perf'?'on':''}" onclick="setAnalyse('perf')">Santé financière</button>
  </div>`;
  return ANALYSE_TAB==="tarifs" ? analyseTarifs(seg) : analysePerf(seg);
}

function analyseTarifs(seg){
  // Garde-fou : on ignore les banques SANS donnée de frais (valeur null) — sinon le « moins cher »
  // tombe sur un null et plante. Tolère aussi une nouvelle banque sans données de tenue de compte.
  const _fr = Object.entries(FRAIS).filter(([,v]) => v != null && v > 0);
  const cheapest = _fr.slice().sort((a,b)=>a[1]-b[1])[0] || ["—", 0];
  const dearest  = _fr.slice().sort((a,b)=>b[1]-a[1])[0] || ["—", 0];
  const factor   = cheapest[1] > 0 ? (dearest[1]/cheapest[1]).toFixed(0) : "—";
  const savAn    = Math.max(0,(dearest[1]-cheapest[1])*12).toLocaleString("fr-FR");
  const cols     = CB_BANKS;   // DYNAMIQUE (source unique)

  // Table: placeholder si CB_DATA pas encore chargé
  const tableBody = CB_DATA ? buildCBTable(cols) : `
    <tr><td colspan="${CB_BANKS.length+1}" style="text-align:center;padding:24px;color:var(--muted);font:500 13px var(--sans)">
      Chargement des tarifs réels…
    </td></tr>`;

  return `
  <div class="story">
    <div class="kicker">Combien ça coûte vraiment ?</div>
    <h1>${cheapest[0]} est <span class="hl">${factor}× moins chère que ${dearest[0]}</span> pour tenir un compte au quotidien.</h1>
    <p>Sur les frais de tenue de compte particuliers S1 2026, l'écart va de <span class="num">à partir de ${cheapest[1].toLocaleString("fr-FR")} F</span> à <span class="num">à partir de ${dearest[1].toLocaleString("fr-FR")} F</span> par mois. En passant de ${dearest[0]} à ${cheapest[0]}, un particulier économise <b>${savAn} FCFA par an</b>.</p>
    ${btnPDF("Analyse Tarifaire")}
  </div>${seg}
  <div class="bento">
    <div class="tile c8 tpad" style="animation-delay:.05s">
      <div class="chead">
        <div class="tt">${cheapest[0]} rafle le tarif le plus bas</div>
        <div class="ts">Vert = le moins cher · Rouge = le plus cher · FCFA</div>
      </div>
      <div style="max-height:440px;overflow:auto;margin:0 -8px">
        <table class="tbl">
          <thead><tr><th>Service</th>${cols.map(c=>`<th>${c}</th>`).join("")}</tr></thead>
          <tbody id="cb-tbody">${tableBody}</tbody>
        </table>
      </div>
    </div>
    <div class="tile c4 tpad" style="animation-delay:.12s">
      <div class="chead"><div class="tt">Le classement tarifaire</div><div class="ts">Frais de tenue · FCFA/mois</div></div>
      <div id="an-frais" style="height:300px"></div>
    </div>
    <div class="tile insight c12" style="animation-delay:.2s">
      <div class="orb">✦</div>
      <div><div class="e">Économie potentielle</div>
      <div class="h">En passant de ${dearest[0]} à ${cheapest[0]}, un particulier économise <b>${savAn} FCFA par an</b> rien que sur la tenue de compte.</div></div>
      <button class="cta ml" onclick="go('strategie')">Voir la recommandation →</button>
    </div>
  </div>`;
}

function buildCBTable(cols){
  if(!CB_DATA || !CB_DATA.rows) return "";
  const grouped = {};
  CB_DATA.rows.forEach(row=>{
    grouped[row.cat] = grouped[row.cat] || [];
    grouped[row.cat].push(row);
  });
  let body = "";
  Object.entries(grouped).forEach(([cat, rows])=>{
    body += `<tr class="cat"><td colspan="${cols.length+1}">${cat}</td></tr>`;
    rows.forEach(row=>{
      const nums = cols.map(b => (row[b]||{}).num).filter(v => v != null && v > 0);
      const mn = nums.length ? Math.min(...nums) : null;
      const mx = nums.length ? Math.max(...nums) : null;
      body += `<tr><td>${row.label}</td>`;
      cols.forEach(b=>{
        const n   = (row[b]||{}).num;
        const raw = (row[b]||{}).raw || "—";
        const c   = n!=null && n===mn ? "cell-best" : n!=null && n===mx ? "cell-worst" : "";
        body += `<td class="${c}">${n != null ? n.toLocaleString("fr-FR") : raw}</td>`;
      });
      body += `</tr>`;
    });
  });
  return body;
}

function afterAnalyse(){
  if(ANALYSE_TAB==="tarifs"){
    chartFraisRanked("an-frais");
    window.__redraw = ()=>{ Plotly.purge("an-frais"); chartFraisRanked("an-frais"); };
    // Charger la table CB si elle manque OU si elle porte sur une autre période que celle
    // sélectionnée : un simple `if(!CB_DATA)` la figeait sur le premier chargement.
    const _f = APERCU_FILTERS;
    const _cle = `${_f.frais_annee}|${_f.frais_sem}|${_f.frais_seg}`;
    if(!CB_DATA || CB_DATA_CLE !== _cle){
      loadCB().then(()=>{
        const tbody = document.getElementById("cb-tbody");
        if(tbody) tbody.innerHTML = buildCBTable(CB_BANKS);
      });
    }
  } else {
    chartRNLine("an-line");
    chartGrowth("an-growth");
    chartTreemap("an-tree");
    chartBumpRank("an-bump", 240);
    chartMarketShare("an-share", 240);
    window.__redraw = ()=>{
      ["an-line","an-growth","an-tree","an-bump","an-share"].forEach(Plotly.purge);
      chartRNLine("an-line");
      chartGrowth("an-growth");
      chartTreemap("an-tree");
      chartBumpRank("an-bump", 240);
      chartMarketShare("an-share", 240);
    };
  }
}

function analysePerf(seg){
  const top    = Object.entries(RN2025).sort((a,b)=>b[1]-a[1]);
  const podium = [top[1],top[0],top[2]];
  const cls    = ["g2","g1","g3"], h=[120,160,96], rk=[2,1,3];
  const total  = Object.values(RN2025).reduce((a,b)=>a+b,0);
  const top0   = top[0];

  // ── Calculs pour critiques et titres ───────────────────────────────
  const gdata   = (KPI_DATA && KPI_DATA.growths_data) ? KPI_DATA.growths_data : {};
  const top3pct = Math.round(top.slice(0,3).reduce((a,[,v])=>a+v,0) / total * 100);
  const sgciPct = Math.round((RN2025["SGCI"]||0) / total * 100);
  const _2nd    = top.find(([b])=>b!=="SGCI") || ["#2",0];   // le #2 DYNAMIQUE (hors SGCI)
  const _2ndB   = _2nd[0];
  const ecooPct = Math.round((_2nd[1]||0) / total * 100);
  const sgciMult= ((RN2025["SGCI"]||0) / total * Object.keys(RN2025).length).toFixed(1);
  const sgciG   = gdata["SGCI"] !== undefined ? Math.round(gdata["SGCI"]) : 0;
  const gvals   = Object.values(gdata).sort((a,b)=>a-b);
  const medianG = gvals.length ? +(gvals[Math.floor(gvals.length/2)].toFixed(1)) : 0;
  const fastest = Object.entries(gdata).filter(([b])=>b!=="SGCI").sort((a,b)=>b[1]-a[1])[0] || ["?",0];
  const fasterN = Object.entries(gdata).filter(([b,v])=>b!=="SGCI"&&v>(gdata["SGCI"]||0)).length;
  const nbB2025 = Object.keys(RN2025).length;
  const avgShare= (100/nbB2025).toFixed(1);

  // Bump — rangs AN1 vs AN3
  const vBanks = Object.keys(RN_SERIES).filter(b=>RN_SERIES[b]&&RN_SERIES[b].values&&RN_SERIES[b].values.length>=3);
  const byAN1  = [...vBanks].sort((a,b)=>RN_SERIES[b].values[0]-RN_SERIES[a].values[0]);
  const byAN3  = [...vBanks].sort((a,b)=>(RN_SERIES[b].values[RN_SERIES[b].values.length-1]||0)-(RN_SERIES[a].values[RN_SERIES[a].values.length-1]||0));
  const rAN1={}, rAN3={};
  byAN1.forEach((b,i)=>{ rAN1[b]=i+1; });
  byAN3.forEach((b,i)=>{ rAN3[b]=i+1; });
  const movers     = vBanks.filter(b=>b!=="SGCI").map(b=>({b,d:(rAN1[b]||CB_BANKS.length)-(rAN3[b]||CB_BANKS.length)})).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  const topMover   = movers[0] || {b:"?",d:0};
  const sgciRankAN3= rAN3["SGCI"] || 1;

  // Titres dynamiques
  const lineTitle  = sgciRankAN3 !== 1
    ? "Résultat net · SGCI #" + sgciRankAN3 + " · évolution AN1→AN3"
    : fasterN===0 ? "SGCI · trajectoire de résultat net la plus soutenue du marché"
    : fastest[0]!=="?" ? "SGCI en tête, " + fastest[0] + " accélère plus vite (+"+Math.round(fastest[1])+"%)"
    : "Résultat net · évolution AN1→AN3";
  const growTitle  = "Qui croît, qui recule ? · médiane marché : "+(medianG>=0?"+":"")+medianG+"%";
  const treeTitle  = "SGCI = "+sgciPct+"% des bénéfices · "+sgciMult+"× la part moyenne";
  const bumpTitle  = sgciRankAN3 !== 1
    ? (byAN3[0] || "?") + " en tête du classement · SGCI #" + sgciRankAN3 + " sur 3 ans"
    : (topMover.b!=="?" && Math.abs(topMover.d)>0
      ? "Classement stable · "+topMover.b+" "+(topMover.d>0?"monte":"recule")+" de "+Math.abs(topMover.d)+" place"+(Math.abs(topMover.d)>1?"s":"")
      : "Classement concurrentiel · SGCI #1 stable sur 3 ans");

  // Critique card — clairement séparée, fond distinct
  const C = (txt) => "<div style='margin-top:14px;padding:11px 14px;background:rgba(56,209,240,.07);border-left:3px solid #38D1F0;border-radius:0 6px 6px 0'>"
    + "<div style='font:700 9px var(--sans,sans-serif);text-transform:uppercase;letter-spacing:.08em;color:#38D1F0;margin-bottom:5px'>◆ Analyse</div>"
    + "<div style='font:500 12px/1.6 var(--sans,sans-serif);color:var(--ink,#F6F6F7)'>" + txt + "</div>"
    + "</div>";

  const podHTML = podium.map((e,i)=>{
    const b = bankBy(e[0]);
    return "<div class='pod'>"
      + "<div class='lg'><img src='"+(b?b.lg:"")+"'></div>"
      + "<div class='nm'>"+e[0]+"</div>"
      + "<div class='amt'>"+(e[1]/1000).toFixed(1)+" Mds</div>"
      + "<div class='col "+cls[i]+"' style='height:"+h[i]+"px'>"+rk[i]+"</div>"
      + "</div>";
  }).join("");

  return `
  <div class="story">
    <div class="kicker">À qui faire confiance ?</div>
    <h1>${top0[0]} domine le marché avec <span class="hl">${top0[1].toLocaleString("fr-FR")} M FCFA</span> de bénéfice.</h1>
    <p>Le trio de tête concentre <span class="num">${top3pct}%</span> des bénéfices des 7 banques ivoiriennes.</p>
    ${btnPDF("Analyse Concurrentielle")}
  </div>${seg}
  <div class="bento">

    <div class="tile c5 tpad" style="animation-delay:.05s;min-height:300px">
      <div class="chead"><div class="tt">Le podium</div><div class="ts">Résultat net · Mds FCFA</div></div>
      <div class="podium">${podHTML}</div>
      ${C("TOP 3 (" + top.slice(0,3).map(([b])=>b).join(" · ") + ") = <b>" + top3pct + "%</b> des bénéfices. SGCI seul : <b>" + sgciPct + "%</b> — soit <b>" + sgciMult + "×</b> la part d'une banque moyenne (1/" + nbB2025 + " = " + avgShare + "%).")}
    </div>

    <div class="tile c7 tpad" style="animation-delay:.12s;min-height:300px">
      <div class="chead">
        <div><div class="tt">${lineTitle}</div><div class="ts">Résultat net · Mds FCFA · évolution temporelle</div></div>
        <div class="legend">
          <span><i style="background:#E5142B"></i>SGCI</span>
          <span><i style="background:#38D1F0"></i>ECOBANK</span>
          <span><i style="background:var(--faint)"></i>Autres</span>
        </div>
      </div>
      <div id="an-line" style="height:248px"></div>
      ${C("SGCI progresse de <b>" + (sgciG>=0?"+":"") + sgciG + "%</b> sur 3 ans." + (fastest[0]!=="?" ? " <b>" + fastest[0] + "</b> est le concurrent le plus rapide (<b>+" + Math.round(fastest[1]) + "%</b>)." : "") + (fasterN>0 ? " <b>" + fasterN + " banque" + (fasterN>1?"s":"") + "</b> croît" + (fasterN>1?"ssent":"") + " plus vite que SGCI — point d'attention." : " SGCI affiche la croissance la plus élevée du marché."))}
    </div>

    <div class="tile c7 tpad" style="animation-delay:.18s">
      <div class="chead"><div class="tt">${growTitle}</div><div class="ts">Croissance résultat net AN1→AN3 · 7 banques</div></div>
      <div id="an-growth" style="height:240px"></div>
      ${C((sgciG >= medianG ? "SGCI (<b>+" + sgciG + "%</b>) <b>au-dessus</b> de la médiane — position de solidité." : "SGCI (<b>+" + sgciG + "%</b>) <b>en dessous</b> de la médiane (+" + medianG + "%) — la croissance est à accélérer.") + " " + fasterN + " concurrent" + (fasterN>1?"s ont":"a") + " un rythme supérieur.")}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.24s">
      <div class="chead"><div class="tt">${treeTitle}</div><div class="ts">Total résultat net · 7 banques</div></div>
      <div id="an-tree" style="height:240px"></div>
      ${C("<b>" + top.slice(0,3).map(([b])=>b).join(" + ") + "</b> = <b>" + top3pct + "%</b> du total. SGCI : <b>" + sgciPct + "%</b> vs <b>" + _2ndB + "</b> : " + ecooPct + "% — avance de <b>" + (sgciPct-ecooPct) + " points</b> de bénéfice sectoriel.")}
    </div>

    <div class="tile c7 tpad" style="animation-delay:.30s;min-height:280px">
      <div class="chead">
        <div><div class="tt">${bumpTitle}</div><div class="ts">Rang parmi les 7 banques · #1 = leader · AN1 → AN2 → AN3</div></div>
        <span class="chip">★ SGCI en rouge</span>
      </div>
      <div id="an-bump" style="height:240px"></div>
      ${C("SGCI maintient la <b>#" + sgciRankAN3 + "</b> place sur toute la période." + (topMover.b!=="?"&&Math.abs(topMover.d)>0 ? " <b>" + topMover.b + "</b> " + (topMover.d>0?"progresse":"recule") + " de <b>" + Math.abs(topMover.d) + " place" + (Math.abs(topMover.d)>1?"s":"") + "</b> entre AN1 et AN3." : " Classements globalement stables."))}
    </div>

    <div class="tile c5 tpad" style="animation-delay:.36s;min-height:280px">
      <div class="chead"><div class="tt">Répartition des bénéfices</div><div class="ts">Part de chaque banque sur le total secteur</div></div>
      <div id="an-share" style="height:240px"></div>
      ${C("SGCI génère <b>" + sgciMult + "×</b> la part équitable (1/" + nbB2025 + " = " + avgShare + "%). Une seule banque absorbe <b>" + sgciPct + "%</b> des bénéfices — position structurellement dominante.")}
    </div>

  </div>`;
}

/* ════════════ STRATÉGIE ═════════════════════════════════════════════ */
/* ── SWOT & RECOS entièrement dynamiques ──────────────────────────────
   Calculés à partir des données réelles (KPI_DATA + FRAIS + DERIVED_METRICS)
   Chaque item reflète la situation actuelle — s'adapte si SGCI change de position.
   ─────────────────────────────────────────────────────────────────────── */

function buildSWOT(){
  if(!KPI_DATA) return {s:[],w:[],o:[],t:[]};
  const k  = KPI_DATA;
  const dm = window.DERIVED_METRICS || {};
  const ord = n => n===1?"1ᵉʳ":n===2?"2ᵉ":n===3?"3ᵉ":`${n}ᵉ`;
  const fraisSorted = Object.entries(FRAIS).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]);
  const fraisRank   = fraisSorted.findIndex(([b])=>b==="SGCI")+1;
  const nbBanques   = Object.keys(k.rn_data||{}).length || CB_BANKS.length;
  const s=[], w=[], o=[], t=[];

  // ① Position en résultat net
  if(k.sgci_rang_rn === 1){
    s.push(`Meilleur profit annuel du secteur — ${(k.sgci_rn/1000).toFixed(0)} Mds FCFA, soit ${k.sgci_part_marche.toFixed(1)}% des bénéfices des ${nbBanques} banques`);
    if(k.ecart_pct_vs_2 < 15)
      t.push(`Avance sur ${k.banque_2_nom} fragile (+${k.ecart_pct_vs_2.toFixed(1)}%) — le leadership peut être rattrapé rapidement`);
    else
      s.push(`Avance solide sur le concurrent direct ${k.banque_2_nom} (+${k.ecart_pct_vs_2.toFixed(0)}%)`);
  } else {
    w.push(`Profit annuel en dessous du leader — ${ord(k.sgci_rang_rn)} position sur ${nbBanques} banques`);
    t.push(`${Object.entries(k.rn_data||{}).sort((a,b)=>b[1]-a[1])[0]?.[0]||"?"} détient le leadership en profit — écart à réduire`);
  }

  // ② Croissance
  if(k.fastest_b === "SGCI"){
    s.push(`Croissance la plus rapide du marché (+${k.fastest_pct.toFixed(0)}% sur 3 ans) — volume ET dynamique`);
  } else {
    w.push(`Croissance plus lente que ${k.fastest_b} sur 3 ans (+${k.sgci_growth_pct.toFixed(0)}% vs +${k.fastest_pct.toFixed(0)}%)`);
    t.push(`${k.fastest_b} accélère fortement (+${k.fastest_pct.toFixed(0)}% sur 3 ans) — concurrent en transformation rapide`);
  }

  // ③ Tarifs (frais de tenue)
  if(fraisRank === 1){
    s.push(`Frais de tenue de compte les plus compétitifs du marché (${(FRAIS["SGCI"]||0).toLocaleString("fr-FR")} F/mois)`);
    o.push(`Marge tarifaire disponible — peut augmenter ses frais de +${Math.round((fraisSorted[1]?.[1]||0)-(FRAIS["SGCI"]||0))*0.4} F/mois et rester la moins chère`);
  } else {
    w.push(`Frais de tenue de compte au-dessus du concurrent le moins cher (rang #${fraisRank})`);
  }

  // ④ Risque crédit
  if(dm.crIsWorst){
    w.push(`Niveau de réserves sur prêts douteux le plus élevé du marché (${dm.crV?.toFixed(1)}% des revenus)`);
    o.push(`Réduire les pertes sur prêts = +${dm.gainCR} Mds FCFA de profit annuel sans action commerciale`);
  } else if(dm.crRank && dm.crRank <= 2){
    s.push(`Excellente qualité du portefeuille de prêts (#${dm.crRank} du marché)`);
  }

  // ⑤ Marge nette
  if(dm.margeRank && dm.margeRank <= 2){
    s.push(`Parmi les meilleures conversions revenus→profit du marché (#${dm.margeRank} sur ${dm.margeNbBanques})`);
  } else if(dm.margeRank && dm.margeV && dm.margeRank > (dm.margeNbBanques||CB_BANKS.length)/2){
    w.push(`Conversion des revenus en profit en dessous de la moitié du marché (${dm.margeV?.toFixed(1)}% de marge nette)`);
  }

  // ⑥ ROE
  if(dm.roeRank === 1){
    s.push(`Meilleur rendement des capitaux propres du secteur — ROE ${dm.roeV?.toFixed(1)}%`);
  } else if(dm.roeRank && dm.roeRank > 3){
    w.push(`Rendement des capitaux propres à améliorer (ROE ${dm.roeV?.toFixed(1)}%, rang #${dm.roeRank})`);
  }

  // ⑦ Coefficient d'exploitation
  if(dm.coeffRank === 1){
    s.push(`Meilleure efficacité opérationnelle du marché (coefficient d'exploitation ${dm.coeffV?.toFixed(1)}%)`);
  }

  // Fixes structurels
  o.push(`Segment entreprises insuffisamment couvert — opportunité face à ECOBANK sur la trésorerie corporate`);
  o.push(`Mobile banking en croissance en Côte d'Ivoire — créneau à développer`);
  t.push(`Pression réglementaire BCEAO susceptible de plafonner certains frais bancaires`);
  t.push(`Concurrents low-cost (BACI, NSIA) agressifs sur le prix d'entrée particuliers`);

  return {s, w, o, t};
}

function buildRECOS(){
  if(!KPI_DATA) return [];
  const k  = KPI_DATA;
  const dm = window.DERIVED_METRICS || {};
  const fraisSorted = Object.entries(FRAIS).filter(([,v])=>v>0).sort((a,b)=>a[1]-b[1]);
  const fraisRank   = fraisSorted.findIndex(([b])=>b==="SGCI")+1;
  const recos = [];

  // Priorité 1 : pire problème = risque crédit ?
  if(dm.crIsWorst && dm.gainCR > 0){
    recos.push([
      "Réduire les pertes sur prêts non remboursés",
      `Le niveau de réserves de SGCI (${dm.crV?.toFixed(1)}%) est le plus élevé du marché. Atteindre le niveau de ${dm.bestCRb} (${dm.bestCRv?.toFixed(1)}%) libérerait +${dm.gainCR} Mds FCFA de profit annuel — sans aucune action commerciale.`,
      `+${dm.gainCR} Mds`, "FCFA / an", "pos", "hi"
    ]);
  }

  // Priorité 2 : marge nette
  if(dm.gainMarge > 0 && dm.bestMargeB && dm.margeRank > 2){
    recos.push([
      `Améliorer la conversion des revenus en profit`,
      `${dm.bestMargeB} transforme ${dm.bestMargeV?.toFixed(1)}% de ses revenus en profit. SGCI est à ${dm.margeV?.toFixed(1)}%. Combler cet écart représenterait +${dm.gainMarge} Mds FCFA de profit supplémentaire, sans toucher aux revenus.`,
      `+${dm.gainMarge} Mds`, "FCFA / an", "pos", "md"
    ]);
  }

  // Priorité 3 : marge tarifaire si SGCI est la moins chère
  if(fraisRank === 1){
    const nextF  = fraisSorted[1]?.[1] || 0;
    const hausse = Math.round((nextF - (FRAIS["SGCI"]||0)) * 0.4);
    const gain   = hausse > 0 ? (Math.round(850000*hausse*12/1e9*10)/10).toFixed(1) : "?";
    recos.push([
      `Augmenter la tenue de compte de +${hausse} F/mois`,
      `SGCI resterait la moins chère du marché après ajustement. Avec 850 000 clients actifs, le gain annuel est estimé à +${gain} Md FCFA sans perte de compétitivité.`,
      `+${gain} Md`, "FCFA / an", "pos", "hi"
    ]);
  }

  // Priorité 4 : gap corporate (toujours pertinent)
  recos.push([
    "Lancer un service de gestion de trésorerie pour les entreprises",
    "ECOBANK est seul sur ce créneau. SGCI a la solidité financière pour y entrer. Chaque trimestre d'inaction renforce la position d'ECOBANK sur le segment PME.",
    "+0,6 Md", "potentiel / an", "pos", "md"
  ]);

  // Priorité 5 : communication si #1
  if(k.sgci_rang_rn === 1){
    recos.push([
      "Valoriser la position de leader dans la communication",
      `SGCI génère ${k.sgci_part_marche.toFixed(1)}% des bénéfices du secteur bancaire ivoirien. Cet avantage de confiance n'est pas encore pleinement exploité face aux challengers qui misent uniquement sur le prix.`,
      "Acquisition", "image de marque", "pos", "md"
    ]);
  }

  return recos;
}
// AFFIRMATIONS DE PRIX RETIRÉES DU TEXTE STATIQUE (2026-07-30).
// Ces descripteurs contenaient des jugements tarifaires écrits en dur, que les données de
// l'app CONTREDISENT aujourd'hui — vérifié en base sur 2026 S1 :
//   « SIB : la plus chère sur la tenue de compte » → FAUX. Particuliers : NSIA 5 400 F >
//      BICICI 5 200 F > SIB 4 900 F (SIB 3e). Entreprises : BICICI 22 000 F contre SIB
//      1 200 F — SIB y est la MOINS chère, l'inverse exact de ce qui était affiché.
//   « ECOBANK : tarifs élevés assumés » → contredit par le win-rate prix (ECOBANK 83,3 %,
//      meilleure compétitivité prix du panel).
//   « BICICI : tarifs particuliers bas » → contredit (BICICI 50,0 %, dernière du panel).
// Ne subsiste donc que le positionnement STRUCTUREL (actionnariat, empreinte géographique,
// cœur de métier), qui ne dépend pas d'un tarif et ne peut pas être démenti par une
// actualisation. Le positionnement PRIX est ajouté à l'affichage par _positionPrix(), à
// partir du win-rate réellement mesuré.
const COMPETS=[
  ["ECOBANK","Groupe pan-africain — investit le corporate et le digital.","Menace","var(--accent)"],
  ["BICICI","Filiale de groupe international — recherche de volume sur le retail.","Pression prix","var(--amber)"],
  ["BACI · NSIA","Challengers en conquête de parts de marché.","Volume","var(--cyan)"],
  ["SIB","Positionnement haut de gamme, clientèle de niche.","Niche","var(--muted)"],
  ["BNI","Banque publique (Banque Nationale d'Investissement) — financement de l'État et des PME.","Public","var(--cyan)"],
];

// Positionnement prix DÉRIVÉ du win-rate mesuré (part des services où la banque est au plus
// égale à la médiane du marché). Retourne '' si la mesure n'est pas disponible : on n'affiche
// alors aucun jugement tarifaire plutôt qu'un jugement faux.
function _positionPrix(nom){
  const cl = window._CB_WINRATE || [];
  if(!cl.length) return '';
  const noms = String(nom).split('·').map(x=>x.trim().toUpperCase());
  const vals = cl.filter(c=>noms.includes(String(c.banque).toUpperCase()));
  if(!vals.length) return '';
  const wr = Math.round(vals.reduce((s,c)=>s+(+c.winrate||0),0)/vals.length);
  // Seuils RELATIFS au panel, pas absolus (corrigé le 2026-07-30 : j'avais figé « 50 », ce qui
  // qualifiait BICICI de « plutôt compétitive » alors qu'elle est DERNIÈRE des sept). On situe
  // chaque banque par rapport à la médiane du marché observé : le jugement suit donc le marché
  // au lieu d'un repère arbitraire, et il reste juste si le niveau général des prix se déplace.
  const tous = cl.map(c=>+c.winrate||0).sort((a,b)=>a-b);
  const med  = tous.length % 2 ? tous[(tous.length-1)/2]
                               : (tous[tous.length/2-1]+tous[tous.length/2])/2;
  const haut = tous[Math.floor(tous.length*0.75)] ?? med;   // 3e quartile du panel
  const q = wr >= haut ? 'parmi les plus compétitives du marché'
          : wr >= med  ? 'au-dessus de la médiane du marché'
          : 'en dessous de la médiane du marché';
  return ` Win-rate prix ${wr}% — ${q}.`;
}
// Liste ÉVOLUTIVE : commentaire curé pour les banques connues + entrée neutre pour toute
// nouvelle banque suivie (dérivée de CB_BANK_ORDER) afin qu'elle ne soit jamais omise.
function _competsAll(){
  const covered = new Set();
  COMPETS.forEach(c => c[0].split("·").forEach(x => covered.add(x.trim().toUpperCase())));
  const order = (typeof CB_BANK_ORDER !== "undefined" ? CB_BANK_ORDER : []) || [];
  const extra = order
    .filter(b => b !== "SGCI" && !covered.has(String(b).toUpperCase()))
    .map(b => [b, "Concurrent suivi — positionnement à préciser au fil des données.", "À qualifier", "var(--muted)"]);
  return COMPETS.concat(extra);
}

/* ════════════ STRATÉGIE — Niveau 3 du RAG (EF + CB + RÉGL + WEB) ══════════ */
let STRAT_SEG = "Particuliers";
function setStratSeg(s){ STRAT_SEG = s; go("strategie"); }

const _SRC_COL = {EF:"#1650b0", CB:"#FF9800", REGL:"#0d7a50", WEB:"#8B5CF6"};
function _srcBadge(s){
  const parts = String(s||"").split(/[·\/]/).map(x=>x.trim()).filter(Boolean);
  return parts.map(p=>{const c=_SRC_COL[p]||"#64748B";
    return `<span title="Source : agent ${p}" style="display:inline-block;font:700 8.5px var(--sans);color:${c};background:${c}1a;border:1px solid ${c}55;border-radius:5px;padding:1px 5px;margin-left:4px">${p}</span>`;}).join("");
}
const _GRAV = {3:["#E53935","Critique"], 2:["#FF8C00","Élevé"], 1:["#64748B","À surveiller"]};

function _stratSkeleton(){
  return `
  <div class="story">
    <div class="kicker">Stratégie · vision d'ensemble SGCI · agents EF + CB + Réglementation + Web</div>
    <h1>De l'analyse à <span class="hl">la décision</span>.</h1>
    <p>Une <b>seule stratégie d'ensemble</b> pour SGCI (particuliers + entreprises réunis) : ce qui va, ce qui ne va pas, ce que les chiffres révèlent, et quoi faire — <b>en langage clair et chaque conclusion sourcée</b>.</p>
  </div>
  <div id="strat-root">
    <div style="display:flex;gap:12px;align-items:center;padding:48px 24px;color:var(--muted)">
      <div class="spin"></div>
      <span style="font:500 13px var(--sans)">Le système mobilise les agents <b>EF · CB · RÉGL · WEB</b> et construit le dossier de preuves…</span>
    </div>
  </div>`;
}

// ════════════════════════════════════════════════════════════════════════════
// Mode ONGLETS — n'afficher QUE la section sélectionnée (EF / CB / Stratégie).
// Au lieu d'empiler toutes les sections (page très longue), un clic sur la barre
// sticky masque les autres sections et n'affiche que celle choisie.
// Robuste aux 2 structures : sections-conteneurs (Stratégie/CB) ET en-têtes +
// tuiles sœurs dans une grille (EF). Pour chaque ancre, on regroupe l'ancre +
// ses frères jusqu'à l'ancre suivante.
// ════════════════════════════════════════════════════════════════════════════
const _PANE_STATE = {};
function _paneNodes(ids){
  const idset = new Set(ids), map = {};
  ids.forEach(id=>{
    const el = document.getElementById(id);
    map[id] = [];
    if(!el) return;
    map[id].push(el);
    let n = el.nextElementSibling;
    while(n && !idset.has(n.id)){ map[id].push(n); n = n.nextElementSibling; }
  });
  return map;
}
function _paneShow(group, sel){
  const st = _PANE_STATE[group]; if(!st) return;
  st.sel = sel;
  const idset = new Set(st.ids);
  const map = _paneNodes(st.ids);
  // MODE ONGLETS : on affiche UNIQUEMENT la section sélectionnée (évite les longs défilements).
  // IMPORTANT : on restaure le display INLINE d'origine (certains conteneurs ont
  // display:grid/flex en inline) — un simple '' le remplacerait par 'block' et
  // casserait la mise en page (ex. rangée de KPI qui s'empilerait verticalement).
  st.ids.forEach(id=>{ (map[id]||[]).forEach(n=>{
    if(!n||!n.style) return;
    if(n.dataset.paneOrig===undefined) n.dataset.paneOrig = n.style.display || '';
    n.style.display = (id===sel ? (n.dataset.paneOrig||'') : 'none');
  }); });
  // surligne le bon bouton (sans toucher aux sous-onglets qui n'ont pas de data-sec dans nos ids)
  document.querySelectorAll('.sec-nav-btn').forEach(b=>{ if(idset.has(b.dataset.sec)) b.classList.toggle('on', b.dataset.sec===sel); });
  try{ window.scrollTo({top:0,behavior:'auto'}); }catch(e){}
  // Les graphiques Plotly se rendent en taille 0 dans une section masquée → on les
  // redimensionne quand la section devient visible.
  requestAnimationFrame(()=>{
    if(!window.Plotly) return;
    (map[sel]||[]).forEach(n=>{
      if(!n.querySelectorAll) return;
      n.querySelectorAll('.js-plotly-plot').forEach(p=>{ if(p.offsetParent===null) return; try{ Plotly.Plots.resize(p); }catch(e){} });
    });
  });
}
function _paneInit(group, ids, opts){
  opts = opts||{};
  // Si la page est re-rendue suite à un changement de FILTRE (ex. Année AN1/AN2/AN3
  // sur Santé financière, ou segment/année/semestre sur CB), on RESTE sur la section
  // que l'utilisateur regardait au lieu de retomber sur la première.
  const prev = _PANE_STATE[group] && _PANE_STATE[group].sel;
  _PANE_STATE[group] = { ids, sel:null };
  const want = (opts.default && ids.indexOf(opts.default) >= 0) ? opts.default
             : (prev && ids.indexOf(prev) >= 0) ? prev
             : ids[0];
  _paneShow(group, want);
}

// ── Barre de navigation sticky (sections claires, façon EF/CB) ──
function _stratStickyBar(segment){
  const nav=[["①","L'essentiel","st-essentiel"],["②","Révélations","st-revel"],
             ["③","Porter","st-conc"],["④","VRIST","st-vrist"],["⑤","SWOT","st-swot"],["⑥","PESTEL","st-pestel"],["⑦","Projection","st-proj"]]
    .map(([n,l,id])=>`<button class="sec-nav-btn" data-sec="${id}" onclick="_paneShow('strat','${id}')">${n} ${l}</button>`).join("");
  return `<div style="position:sticky;top:116px;z-index:20;margin-bottom:14px;padding:6px 0;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--bg-deep) 72%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span style="font:700 9px var(--sans);color:var(--accent-2);letter-spacing:.1em;text-transform:uppercase">🎯 Stratégie SGCI</span>
      <div class="seg" style="margin:0">${nav}</div>
      ${btnPDF("Stratégie SGCI")}
    </div>
  </div>`;
}

// ── Scroll-spy : surligne la section active dans la barre ──
function _stratScrollSpy(){
  const btns=document.querySelectorAll('#strat-root .sec-nav-btn'); if(!btns.length) return;
  const ids=["st-essentiel","st-revel","st-conc","st-vrist","st-swot","st-pestel","st-proj"];
  const setOn=id=>btns.forEach(b=>b.classList.toggle('on',b.dataset.sec===id));
  setOn("st-essentiel");
  let clicking=false,t;
  btns.forEach(b=>b.addEventListener('click',()=>{setOn(b.dataset.sec);clicking=true;clearTimeout(t);t=setTimeout(()=>clicking=false,900);}));
  const obs=new IntersectionObserver(es=>{if(clicking)return;es.forEach(e=>{if(e.isIntersecting)setOn(e.target.id);});},{rootMargin:"-150px 0px -65% 0px",threshold:0});
  ids.forEach(id=>{const el=document.getElementById(id);if(el)obs.observe(el);});
}

async function _stratLoad(){
  const root = document.getElementById("strat-root");
  if(!root) return;
  try{
    const r = await fetch(`/api/strategie`);   // une seule stratégie d'ensemble (pas de segment)
    const d = await r.json();
    if(d.error) throw new Error(d.error);
    root.innerHTML = _renderStrategie(d);
    _VRIST_DATA = d.vrist || {};
    // Onglets armés DANS LA FOULÉE du rendu, pas dans le setTimeout qui suit : autrement les
    // huit sections apparaissent ensemble avant de se replier, et l'œil voit un sursaut.
    try{ _paneInit('strat',['st-essentiel','st-revel','st-conc','st-vrist','st-swot','st-pestel','st-proj']); }catch(e){}
    setTimeout(()=>{
      try{ var _vc=(_VRIST_DATA.ordre||[]).filter(b=>b!=='SGCI'); setVristComp(_vc[0]||"BICICI"); }catch(e){}
      try{ _stratCharts(d); }catch(e){}
      try{ _stratProjScenarioCharts(d); }catch(e){}
    }, 40);
    _stratLLM();
    try{ _loadStratNarr(d.segment||'Particuliers'); }catch(e){}
    try{ _firePestelLLM(); }catch(e){}
    try{ _fireVristLLM(); }catch(e){}
    try{ _fireStratDiagLLM(d.segment||'Particuliers'); }catch(e){}
    try{ _fireStratProjLLM(d.segment||'Particuliers'); }catch(e){}
    try{ _fireStratSwitchLLM(d.segment||'Particuliers'); }catch(e){}
    try{ _fireStratRoadmapLLM(d.segment||'Particuliers'); }catch(e){}
    window.__redraw = () => { try{ _stratCharts(d); }catch(e){} try{ _stratProjScenarioCharts(d); }catch(e){} };
  }catch(e){
    root.innerHTML = `<div style="padding:24px;color:#E53935;font:500 12px var(--sans)">Erreur stratégie — ${e.message}</div>`;
  }
}

function _renderStrategie(d){
  const sy = d.synthese||{}, m = d.metriques||{};
  // ── Synthèse exécutive ──
  const card = (col,tag,txt)=>`<div class="tile c4 tpad" style="border-left:3px solid ${col}">
    <div style="font:800 9px var(--sans);color:${col};text-transform:uppercase;letter-spacing:.09em;margin-bottom:6px">${tag}</div>
    <div style="font:600 13px/1.5 var(--sans);color:var(--ink)">${txt}</div></div>`;
  const synth = `${card("#1D9E75","✓ Position", sy.position||"—")}${card("#E53935","⚠ Menace n°1", sy.menace||"—")}${card("#FF8C00","➔ Levier prioritaire", sy.levier||"—")}`;

  // ── L'ESSENTIEL — verdict en français simple (compréhension en 10 secondes) ──
  const _br = s => (s||'').replace(/(?<!Ex)\.\s+(?=[A-ZÀ-Þ«→])/g,'.<br>');  // une phrase par ligne (sûr)
  const es = d.essentiel||{};
  const essentiel = es.verdict ? `<div class="tile c12 tpad" style="background:radial-gradient(120% 140% at 100% 0,#1650b015,transparent 55%),var(--bg-tile);border-top:3px solid var(--accent-2)">
    <div style="font:800 9px var(--sans);color:var(--accent-2);text-transform:uppercase;letter-spacing:.09em;margin-bottom:7px">📌 En une phrase</div>
    <div id="strat-stale-badge" style="display:none"></div>
    <div id="strat-narr-verdict" style="font:600 16px/1.6 var(--display);color:var(--ink);margin-bottom:14px">${_br(es.verdict)}</div>
    <div class="bento" style="gap:10px">
      ${(es.points||[]).map((p,i)=>`<div class="tile c4 tpad" style="padding:11px;border-left:3px solid ${p.col}">
        <div style="font:800 11px var(--sans);color:${p.col};margin-bottom:3px">${p.ic} ${p.titre}</div>
        <div data-narr="${['bien','probleme','faire'][i]||''}" style="font:500 11.5px/1.55 var(--sans);color:var(--ink)">${_br(p.txt)}</div>
      </div>`).join("")}
    </div>
    ${es.surveiller?`<div style="font:500 11px/1.5 var(--sans);color:var(--muted);margin-top:11px;padding-top:9px;border-top:1px dashed var(--line)">👁 <span id="strat-narr-surveiller">${es.surveiller}</span></div>`:''}
  </div>`:'';

  // ── Bandeau métriques RAG (groundedness / agents) — SUPPRIMÉ (demande utilisateur) ──
  const metr = '';

  // ── Révélations stratégiques (le bloc le plus fort) ──
  const _REV_STYLE = {
    paradoxe:{c:"#B45309",lbl:"Paradoxe"},
    moteur:  {c:"#6D28D9",lbl:"Moteur décodé"},
    menace:  {c:"#E53935",lbl:"Menace"},
    atout:   {c:"#12895C",lbl:"Atout"},
    signal:  {c:"#475569",lbl:"Signal faible"},
  };
  const revCard = (r,hero,ri)=>{
    const st = _REV_STYLE[r.type]||_REV_STYLE.signal;
    const preuves = (r.preuves||[]).filter(Boolean).map(p=>
      `<span style="font:600 10px var(--sans);color:var(--ink);background:var(--bg-raise);border:1px solid var(--line);border-radius:20px;padding:3px 9px">${p}</span>`).join("");
    const srcs = (r.sources||[]).map(_srcBadge).join("");
    return `<div class="tile ${hero?'c12':'c6'} tpad" style="border-left:4px solid ${st.c};background:radial-gradient(130% 150% at 0 0,${st.c}0d,transparent 55%),var(--bg-tile)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;flex-wrap:wrap">
        <span style="font-size:${hero?20:17}px;line-height:1">${r.icone}</span>
        <span style="font:800 8.5px var(--sans);color:${st.c};background:${st.c}1a;border:1px solid ${st.c}55;border-radius:5px;padding:2px 8px;text-transform:uppercase;letter-spacing:.08em">${st.lbl}</span>
        <span style="margin-left:auto">${srcs}</span>
      </div>
      <div style="font:800 ${hero?15.5:13}px/1.35 var(--sans);color:var(--ink);margin-bottom:6px"><span data-narr3="rev_titre_${ri}">${r.titre}</span></div>
      ${r.resume?`<div style="font:600 ${hero?12.5:11.5}px/1.6 var(--sans);color:var(--ink);background:${st.c}10;border-radius:7px;padding:8px 10px;margin-bottom:8px"><b style="color:${st.c}">En clair :</b> <span data-narr2="rev_${ri}">${_br(r.resume)}</span></div>`:''}
      ${r.recit?`<details open style="margin-bottom:2px"><summary style="font:700 9.5px var(--sans);color:var(--faint);cursor:pointer;text-transform:uppercase;letter-spacing:.05em;list-style:none">▸ Détail chiffré</summary>
      <div style="font:500 ${hero?12:11}px/1.65 var(--sans);color:var(--muted);margin-top:6px"><span data-narr2="rev_detail_${ri}">${_br(r.recit)}</span></div></details>`:''}
      ${preuves?`<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">${preuves}</div>`:''}
      ${r.contexte?`<div style="margin-top:10px;background:#8B5CF60f;border:1px solid #8B5CF633;border-radius:7px;padding:7px 9px">
        <div style="font:800 8px var(--sans);color:#7C3AED;text-transform:uppercase;letter-spacing:.07em;margin-bottom:2px">🌐 Recoupé par la veille web ${_srcBadge("WEB")}</div>
        <div style="font:600 10.5px/1.5 var(--sans);color:var(--ink)"><b>${r.contexte.titre} : ${r.contexte.valeur||''}</b> — ${_br(r.contexte.detail||'')}</div>
        ${r.contexte.source?`<div style="font:500 9px var(--sans);color:var(--faint);margin-top:2px">Source : ${r.contexte.source}${r.contexte.date?(' · '+r.contexte.date):''}</div>`:''}
      </div>`:''}
      ${r.action?`<div style="font:700 ${hero?11:10.5}px/1.45 var(--sans);color:${st.c};margin-top:10px;padding-top:9px;border-top:1px dashed var(--line)">➔ <span data-narr3="rev_action_${ri}">${r.action}</span></div>`:''}
    </div>`;
  };
  const REVS = d.revelations||[];
  const revs = REVS.length ? REVS.map((r,i)=>revCard(r, i===0, i)).join("") : "";
  // Boîte « Lecture stratégique » (rédigée par le LLM, ancrée sur les faits) — masquée tant que vide.
  const _narrBox = k => `<div class="tile c12" data-narr2="${k}" style="display:none;border-left:3px solid #6D28D9;background:radial-gradient(120% 140% at 0 0,#6D28D910,transparent 55%),var(--bg-tile);padding:11px 14px;font:500 12px/1.65 var(--sans);color:var(--ink)"></div>`;

  // ── Contexte de marché (faits web externes, complémentaires) ──
  const CTX = d.contexte_marche||[];
  const ctxMarche = CTX.length ? `<div class="tile c12 tpad" style="border-top:3px solid #7C3AED">
    <div class="chead"><div><div class="tt">🌐 Contexte de marché — faits externes (veille web)</div>
    <div class="ts">Faits sectoriels fiables (BCEAO, APBEF-CI, classements UMOA) qui <b>complètent</b> les données internes — chacun cité, daté, avec son lien d'analyse</div></div></div>
    <div class="bento" style="gap:10px;margin-top:4px">
      ${CTX.map(f=>`<div class="tile c4 tpad" style="padding:11px;border-left:3px solid #7C3AED">
        <div style="font:800 9px var(--sans);color:#7C3AED;text-transform:uppercase;letter-spacing:.05em">${f.titre}</div>
        <div style="font:800 17px var(--display);color:var(--ink);margin:3px 0">${f.valeur||''}</div>
        <div style="font:500 10px/1.5 var(--sans);color:var(--muted)">${f.lien_analyse||f.detail||''}</div>
        <div style="font:500 8.5px var(--sans);color:var(--faint);margin-top:5px">${f.url?`<a href="${f.url}" target="_blank" style="color:#7C3AED;text-decoration:none">↗ ${f.source}</a>`:f.source}${f.date?(' · '+f.date):''}</div>
      </div>`).join("")}
    </div>
  </div>`:'';

  // ── Diagnostic ──
  const diag = `<div class="tile c12 tpad">
    <div class="chead"><div><div class="tt">Diagnostic 360° — Problèmes détectés</div>
    <div class="ts">Détectés automatiquement par les agents EF + CB · triés par gravité · chacun sourcé</div></div></div>
    ${(d.problemes||[]).map(p=>{const g=_GRAV[p.gravite]||_GRAV[1];
      return `<div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)">
        <span style="flex-shrink:0;width:64px;font:800 8.5px var(--sans);color:${g[0]};background:${g[0]}18;border:1px solid ${g[0]}55;border-radius:5px;padding:3px 0;text-align:center;height:fit-content">${g[1]}</span>
        <div style="flex:1"><div style="font:700 12.5px var(--sans);color:var(--ink)">${p.titre} ${_srcBadge(p.source)}</div>
          <div class="diag-preuve" data-diag-titre="${(p.titre||'').replace(/"/g,'&quot;')}" style="font:400 11px/1.5 var(--sans);color:var(--muted);margin-top:2px">${p.preuve}</div></div>
      </div>`;}).join("")}
  </div>`;

  // ── SWOT ──
  const sw = d.swot||{};
  const quad = (col,ic,titre,items,qkey)=>`<div class="tile c6 tpad" style="border-top:3px solid ${col}">
    <div style="font:800 11px var(--sans);color:${col};text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">${ic} ${titre}</div>
    ${(items||[]).map((it,i)=>`<div style="font:500 11.5px/1.5 var(--sans);color:var(--ink);padding:5px 0;border-bottom:1px solid var(--line)">• <span data-narr3="swot_${qkey}_${i}">${it.txt}</span> ${_srcBadge(it.source)}</div>`).join("")||'<div style="color:var(--faint);font:italic 11px var(--sans)">—</div>'}
  </div>`;
  const swot = `<div style="grid-column:span 12;padding:20px 0 6px;border-top:2px solid var(--line);margin-top:6px"><div class="tt" style="font-size:15px">Analyse SWOT — sourcée</div></div>
  <div class="bento" style="margin-bottom:10px">
    ${quad("#1D9E75","💪","Forces",sw.forces,"forces")}
    ${quad("#E53935","⚠","Faiblesses",sw.faiblesses,"faiblesses")}
    ${quad("#1650b0","🚀","Opportunités",sw.opportunites,"opportunites")}
    ${quad("#FF8C00","🛡","Menaces",sw.menaces,"menaces")}
  </div>`;

  // ── Porter — schéma en CROIX (rivalité au centre), standard pro ──
  const P = d.porter||{}; const PF = P.forces||[];
  const _pPos = pos => PF.find(f=>f.position===pos) || {};
  const _pCol = n => n>=5?"#E53935":n>=4?"#FF8C00":n>=3?"#D97706":"#1D9E75";
  // barre d'intensité claire : n segments pleins / 5-n vides (bien plus lisible que des pastilles)
  const _pBar = n => `<span style="display:inline-flex;gap:2px;vertical-align:middle">${[1,2,3,4,5].map(i=>`<span style="width:14px;height:6px;border-radius:2px;background:${i<=n?_pCol(n):'transparent'};border:1px solid ${i<=n?_pCol(n):'var(--line)'}"></span>`).join('')}</span>`;
  const _pSrc = ag => `<span style="display:inline-flex;gap:3px">${(ag||'').split('·').filter(Boolean).map(a=>_srcBadge(a)).join('')}</span>`;
  const _pCard = (f, hero, arrow) => {
    if(!f.cle) return `<div></div>`;
    const c=_pCol(f.note);
    return `<div class="tile tpad" style="border:1px solid ${c}55;border-top:3px solid ${c};padding:10px;${hero?`background:radial-gradient(120% 150% at 50% 0,${c}16,transparent 60%),var(--bg-tile);box-shadow:0 0 0 1px ${c}33`:''}">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap">
        ${arrow?`<span style="color:${c};font-size:15px;font-weight:800">${arrow}</span>`:'<span style="font-size:13px">◎</span>'}
        <span style="font:800 ${hero?12.5:10.5}px var(--sans);color:${c}">${f.force}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span style="font:800 8px var(--sans);color:#fff;background:${c};border-radius:4px;padding:2px 7px">${f.intensite}</span>
        ${_pBar(f.note)}
      </div>
      <div style="font:600 ${hero?11:9.5}px/1.45 var(--sans);color:var(--muted);margin-top:6px"><span data-narr3="porter_${f.cle}">${f.resume}</span></div>
    </div>`;
  };
  // Analyse explicite — cartes aérées, triées par intensité décroissante (pas de pavé)
  const _pAnalyse = (P.forces||[]).slice().sort((a,b)=>b.note-a.note).map(f=>{
    const c=_pCol(f.note);
    return `<div class="tile tpad" style="border-left:4px solid ${c};padding:12px 15px;margin-bottom:9px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px">
        <span style="font:800 13px var(--sans);color:var(--ink)">${f.force}</span>
        <span style="font:800 8.5px var(--sans);color:#fff;background:${c};border-radius:5px;padding:2px 9px">${f.intensite}</span>
        ${_pBar(f.note)}
        <span style="margin-left:auto">${_pSrc(f.agents)}</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;margin-bottom:9px">
        ${(f.facteurs||[]).filter(Boolean).map(x=>`<div style="font:500 10.5px/1.45 var(--sans);color:var(--muted);display:flex;gap:7px"><span style="color:${c};font-weight:800;flex-shrink:0">•</span><span>${x}</span></div>`).join('')}
      </div>
      ${f.implication?`<div style="font:600 11px/1.5 var(--sans);color:${c};background:${c}0f;border-radius:7px;padding:8px 11px">➔ <b>Pour SGCI :</b> ${f.implication}</div>`:''}
    </div>`;
  }).join("");
  const porter = `<div class="tile c12 tpad">
    <div class="chead"><div><div class="tt">⚔️ Porter — les 5 forces concurrentielles</div><div class="ts">${P.intro||''}</div></div></div>
    <div style="display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:9px;align-items:start;margin:4px 0 6px">
      <div style="grid-column:2;grid-row:1">${_pCard(_pPos('haut'),false,'↓')}</div>
      <div style="grid-column:1;grid-row:2">${_pCard(_pPos('gauche'),false,'→')}</div>
      <div style="grid-column:2;grid-row:2">${_pCard(_pPos('centre'),true,'')}</div>
      <div style="grid-column:3;grid-row:2">${_pCard(_pPos('droite'),false,'←')}</div>
      <div style="grid-column:2;grid-row:3">${_pCard(_pPos('bas'),false,'↑')}</div>
    </div>
    <div style="font:700 9px var(--sans);color:var(--muted);text-transform:uppercase;letter-spacing:.07em;border-top:2px solid var(--line);padding-top:9px;margin-top:6px">Analyse détaillée — de la force la plus intense à la moins intense</div>
    ${_pAnalyse}
    ${P.synthese?`<div style="font:500 11px/1.6 var(--sans);color:var(--ink);background:var(--bg-raise);border-left:3px solid #6D28D9;border-radius:0 7px 7px 0;padding:10px 12px;margin-top:12px">🎯 <b>Synthèse :</b> ${P.synthese}</div>`:''}
  </div>`;

  // ── Menaces croisées ──
  const mc = (d.menaces_croisees||[]).map(x=>`<div class="tile c12 tpad" style="background:radial-gradient(120% 140% at 0 100%,#E5393511,transparent 55%),var(--bg-tile);border-left:3px solid #E53935">
    <div style="font:800 10px var(--sans);color:#E53935;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px">⚠ Croisement inter-agents — ${x.titre}</div>
    <div style="font:500 12px/1.6 var(--sans);color:var(--ink)">${x.recit.replace(/\[(EF|CB|REGL|WEB)\]/g,(_,a)=>_srcBadge(a))}</div></div>`).join("");
  const menaces = mc ? `<div class="bento" style="margin-bottom:10px">${mc}</div>` : "";

  // ── Atouts à valoriser (offensif) ──
  const atouts = (d.atouts&&d.atouts.length)?`<div style="grid-column:span 12;padding:18px 0 6px;border-top:2px solid var(--line);margin-top:6px"><div class="tt" style="font-size:15px">⚡ Atouts à valoriser — offensif (là où SGCI gagne)</div></div>
  <div class="bento" style="margin-bottom:10px">
    ${d.atouts.map(a=>`<div class="tile c6 tpad" style="border-left:3px solid #1D9E75">
      <div style="font:800 11.5px var(--sans);color:#12895C">✓ ${a.titre} ${_srcBadge(a.source)}</div>
      <div style="font:500 11px/1.5 var(--sans);color:var(--ink);margin:4px 0">${a.preuve}</div>
      <div style="font:600 10.5px/1.45 var(--sans);color:#FF8C00">➔ ${a.action}</div>
    </div>`).join("")}
  </div>`:'';

  // ── Plan d'action détaillé ──
  const plan = `<div style="grid-column:span 12;padding:20px 0 6px;border-top:2px solid var(--line);margin-top:6px"><div class="tt" style="font-size:15px">Plan d'action détaillé — solutions concrètes · benchmark des meilleurs · chiffré · ancré BCEAO</div></div>
  <div class="bento" style="margin-bottom:10px">
    ${(d.plan_action||[]).map(a=>`<div class="tile c6 tpad" style="border-top:3px solid #1650b0">
      <div style="font:800 11.5px var(--sans);color:#1650b0;text-transform:uppercase;letter-spacing:.04em">${a.levier} ${(a.sources||[]).map(_srcBadge).join("")}</div>
      ${a.constat?`<div style="font:500 11px/1.5 var(--sans);color:var(--ink);margin:5px 0">${a.constat}</div>`:''}
      ${a.benchmark?`<div style="font:600 10.5px/1.45 var(--sans);color:#6040c8;background:#6040c812;border-radius:6px;padding:6px 8px;margin-bottom:6px">🏅 ${a.benchmark}</div>`:''}
      <div style="font:700 9px var(--sans);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px">Solutions concrètes</div>
      <ul style="margin:0 0 8px 15px;padding:0;font:500 11px/1.5 var(--sans);color:var(--ink)">${(a.solutions||[]).map(x=>{const t=(typeof x==='string')?x:x.t;const dd=(typeof x==='string')?'':x.d;return `<li style="margin-bottom:5px"><b>${t}</b>${dd?`<div style="font:400 10px/1.42 var(--sans);color:var(--muted);margin-top:1px">${dd}</div>`:''}</li>`;}).join("")}</ul>
      ${a.chiffrage?`<div style="font:600 11px/1.5 var(--sans);color:#0a5e3c;background:#0d7a5014;border-radius:6px;padding:7px 9px;margin-bottom:5px">📊 Chiffrage : ${a.chiffrage}</div>`:''}
      ${a.ancrage_bceao?`<div style="font:500 10px/1.42 var(--sans);color:#0d7a50">⚖ ${a.ancrage_bceao} ${_srcBadge("REGL")}</div>`:''}
    </div>`).join("")}
  </div>`;

  // ── Plan-trajectoire (actes → résultat → justification) — 2026-07-24 : fusionné DANS
  // l'onglet Central (voir plus bas) au lieu d'une section séparée dupliquant "Central" —
  // demande explicite : « tu mets le plan Central en haut ET il y a une section en bas pour
  // les scénarios, c'est bête, ça doit se retrouver DANS Central, pas une section séparée ».
  // On garde juste les données (`rm`) ici, plus le rendu à part.
  const rm = d.roadmap||{};

  // ── Dashboard par scénario, filtrable (2026-07-24, version A validée — demande explicite :
  // « un filtre pour les 3 scénarios, un dashboard pour chacun, la section la plus pro du
  // dashboard, zéro discours inventé »). Un seul scénario affiché à la fois (cohérent avec la
  // règle "mode onglets" utilisée partout ailleurs dans l'app — évite les longs défilements),
  // mais chaque scénario est un dashboard COMPLET : canevas (Formulation/Justification/
  // Indicateurs/Certitude) + plan An1→An2→An3 au même niveau de détail que le Plan-trajectoire
  // (acte → résultat attendu → pourquoi, rien d'inventé) + son propre graphique. 100%
  // déterministe (build_projection_hypotheses) — ne peut jamais diverger des graphiques
  // comparés plus bas (mêmes chiffres `projection`).
  const _ph = d.projection_hypotheses;
  window._PROJ_HYP = _ph;
  const projHyp = (_ph && _ph.scenarios && _ph.scenarios.length) ? (()=>{
    const scs = _ph.scenarios;
    const tabs = `<div style="display:flex;gap:8px;margin:2px 0 14px;flex-wrap:wrap">
      ${scs.map(s=>{
        const col = _PROJ_SC_COL[s.cle], on = s.cle==='central';
        const style = on
          ? `background:${col};color:#fff;border:1px solid ${col};box-shadow:0 4px 12px ${col}55`
          : `background:var(--bg-raise);color:var(--muted);border:1px solid var(--line)`;
        return `<button data-projsc="${s.cle}" onclick="setProjScTab('${s.cle}')" style="cursor:pointer;padding:9px 18px;border-radius:10px;font:800 12.5px var(--sans);transition:all .15s;${style}">${s.nom} <span style="opacity:.75;font-weight:600">— ${s.pct_effet}%</span></button>`;
      }).join('')}
    </div>`;
    const blocs = scs.map(s=>{
      const col = _PROJ_SC_COL[s.cle];
      return `<div class="tile c12 tpad" id="proj-sc-${s.cle}" style="border-top:4px solid ${col};display:${s.cle==='central'?'':'none'}">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
          <div style="width:56px;height:56px;border-radius:50%;background:${col};color:#fff;display:flex;align-items:center;justify-content:center;font:900 12px/1.1 var(--sans);text-align:center;box-shadow:0 4px 12px ${col}55;flex-shrink:0">${s.pct_effet}%<br><span style="font-weight:600;font-size:7.5px">effet plan</span></div>
          <div>
            <div style="font:900 16px var(--display);color:${col}">Scénario ${s.nom}</div>
            <div style="font:600 10.5px/1.3 var(--sans);color:var(--faint)">${s.description}</div>
          </div>
        </div>

        <div style="font:900 17px/1.32 var(--display);color:var(--ink);margin-bottom:7px">${s.formulation||''}</div>
        <div style="font:500 11.5px/1.55 var(--sans);color:var(--muted);margin-bottom:13px">${s.justification||''}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:13px">
          ${(s.indicateurs||[]).map(i=>`<div style="flex:1;min-width:125px;background:var(--bg-raise);border-radius:8px;padding:8px 12px">
            <div style="font:700 8px var(--sans);color:var(--faint);text-transform:uppercase;letter-spacing:.04em">${i.label}</div>
            <div style="font:800 14.5px var(--display);color:${col}">${i.valeur}</div>
          </div>`).join('')}
        </div>
        <div style="display:flex;align-items:center;gap:11px;padding:11px 0;margin-bottom:16px;border-top:1px dashed var(--line);border-bottom:1px dashed var(--line)">
          <div style="font:900 21px var(--display);color:${col}">${s.certitude_pct}%</div>
          <div style="font:500 10px/1.4 var(--sans);color:var(--muted)">de certitude — Risque : ${s.certitude_risque}</div>
        </div>

        <div style="font:800 12px var(--sans);color:var(--ink);margin-bottom:10px">🗺️ Plan ${s.nom} — chaque acte, son résultat à ce niveau d'exécution, sa justification</div>
        <div class="bento" style="gap:10px;margin-bottom:4px">
          ${(s.annees||[]).map((a,i)=>{
            // Actions COMPLÉMENTAIRES du Plan-trajectoire (repricing tarifaire, mix commissions,
            // offensive croissance...) — 2026-07-24 : fusionnées ICI (dans l'onglet Central
            // uniquement, plus de section séparée en double au-dessus) car ce sont les actions
            // du plan de référence tel quel, non recalculées par scénario.
            const extra = (s.cle==='central' && rm.horizons && rm.horizons[i] && (rm.horizons[i].actes||[])[1]) || null;
            return `<div class="tile c4 tpad" style="padding:12px;border-top:3px solid ${col}">
            <div style="display:flex;align-items:baseline;gap:7px;margin-bottom:7px">
              <span style="font:900 15px var(--display);color:${col}">${a.an}</span>
            </div>
            <div style="font:600 11px/1.45 var(--sans);color:var(--ink);margin-bottom:8px"><span style="color:${col};font-weight:800">▸</span> ${a.acte||''}</div>
            <div style="font:700 10px/1.4 var(--sans);color:#0a5e3c;background:#0d7a5012;border-radius:5px;padding:5px 7px;margin-bottom:6px">📈 ${a.resultat||''}</div>
            <div style="font:500 9.5px/1.4 var(--sans);color:var(--muted);${extra?'margin-bottom:10px;padding-bottom:10px;border-bottom:1px dashed var(--line)':''}">⚖ ${a.pourquoi||''}</div>
            ${extra?`<div style="font:600 11px/1.45 var(--sans);color:var(--ink);margin-bottom:8px"><span style="color:${col};font-weight:800">▸</span> ${extra.acte}</div>
            <div style="font:700 10px/1.4 var(--sans);color:#0a5e3c;background:#0d7a5012;border-radius:5px;padding:5px 7px;margin-bottom:6px">📈 ${extra.resultat}</div>
            <div style="font:500 9.5px/1.4 var(--sans);color:var(--muted)">⚖ ${extra.justification} ${(extra.sources||[]).map(_srcBadge).join('')}</div>`:''}
          </div>`;}).join('')}
        </div>
        ${s.cle==='central' && rm.objectif ? `<div class="tile c12 tpad" style="background:#0B2D5B;color:#fff;margin-top:2px">
          <div style="font:800 10px var(--sans);color:#9DB8DC;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px">🎯 ${rm.objectif.titre} — cap consolidé</div>
          <div style="display:flex;flex-wrap:wrap;gap:10px">${(rm.objectif.lignes||[]).filter(Boolean).map(l=>`<div style="flex:1;min-width:200px;font:600 11.5px/1.5 var(--sans);color:#fff;background:#ffffff14;border-radius:7px;padding:8px 11px">${l}</div>`).join('')}</div>
        </div>` : ''}
        ${s.cle==='central' ? `<div id="strat-roadmap-llm" class="tile c12" style="display:none;margin-top:10px;padding:12px 15px;border-radius:10px;border:1px solid #6D28D955;background:radial-gradient(120% 140% at 0 0,#6D28D912,transparent 55%),var(--bg-tile)">
          <div style="font:800 10px var(--sans);color:#6D28D9;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px">🤖 Lecture stratégique — la logique du plan</div>
          <div id="strat-roadmap-llm-txt" style="font:500 12px/1.65 var(--sans);color:var(--ink)"></div>
        </div>` : ''}

        <div id="proj-sc-chart-${s.cle}" style="height:170px;margin-top:8px"></div>
      </div>`;
    }).join('');

    return `<div style="margin-bottom:10px">
      <div class="chead"><div><div class="tt">Logique des 3 scénarios</div>
      <div class="ts">${_ph.intro}</div></div></div>
      ${tabs}
      ${blocs}
      ${_ph.conclusion_strategique ? `<div class="tile c12 tpad" style="margin-top:12px;background:#0B2D5B;color:#fff">
        <div style="font:800 10px var(--sans);color:#9DB8DC;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px">🎯 Conclusion stratégique</div>
        <div style="font:600 12.5px/1.6 var(--sans);color:#fff">${_ph.conclusion_strategique}</div>
      </div>` : ''}
    </div>`;
  })() : '';

  // ── Projection 3 ans (graphiques lisibles + message-clé) ──
  // Bilan « bas de gamme » (2026-07-21) : 100% déterministe, calculé serveur (build_projection),
  // porte UNIQUEMENT sur le Résultat net (la ligne qui compte) — jamais lié à un levier nommé
  // (coût du risque aujourd'hui, autre chose demain) donc reste valable si la cause change.
  const _rn = (d.projection||[]).find(p=>p.nom==='Résultat net') || {};
  const projBilan = (_rn.gain_pire_cas!=null) ? `<div style="display:flex;flex-wrap:wrap;gap:10px;margin:2px 0 14px">
    ${_rn.pire_cas_bat_immobilisme?`<div class="tile c6 tpad" style="border-left:4px solid #12895C;padding:12px 15px">
      <div style="font:800 9px var(--sans);color:#12895C;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px">✅ Même le pire scénario bat l'immobilisme</div>
      <div style="font:600 12px/1.5 var(--sans);color:var(--ink)">Même en exécution partielle du plan (scénario prudent), le résultat net dépasse déjà le « sans rien changer » de <b style="color:#12895C">+${_rn.gain_pire_cas}</b> à AN3 — agir n'est pas un pari.</div>
    </div>`:''}
    <div class="tile c6 tpad" style="border-left:4px solid #B45309;padding:12px 15px">
      <div style="font:800 9px var(--sans);color:#B45309;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px">⏳ Le prix de l'attentisme, cumulé sur 3 ans</div>
      <div style="font:600 12px/1.5 var(--sans);color:var(--ink)">Pas qu'un instantané à AN3 : sur les 3 années cumulées, retarder le plan coûte <b style="color:#B45309">${_rn.cumul_attentisme_3ans}</b> de résultat net face au scénario central.</div>
    </div>
  </div>` : '';
  const _PROJ_METRIC_COL = {"PNB":"#1650b0","Coût du risque (% PNB)":"#B45309","Résultat net":"#12895C","ROE":"#6D28D9"};
  const proj = `<div class="tile c12 tpad">
    <div class="chead"><div><div class="tt">Graphiques de projection — les 3 scénarios en image</div>
    <div class="ts">Ligne grise = <b style="color:#94A3B8">sans rien changer</b> · ligne verte = <b style="color:#12895C">scénario central (plan tenu)</b> · zone verte = <b style="color:#12895C">fourchette prudent → optimiste</b> · modèle déterministe dérivé des chiffres réels</div></div></div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 10px">
      ${[["Prudent","exécution partielle du plan (~55% de l'effet)","#94A3B8"],["Central","plan tenu (100% de l'effet)","#12895C"],["Optimiste","plan + macro porteuse (~135%)","#1650b0"]].map(s=>`<div style="font:600 9.5px var(--sans);color:var(--muted);background:var(--bg-raise);border:1px solid var(--line);border-left:3px solid ${s[2]};border-radius:5px;padding:4px 9px"><b style="color:${s[2]}">${s[0]}</b> — ${s[1]}</div>`).join("")}
    </div>
    ${projBilan}
    <div class="bento" style="gap:14px">
      ${(d.projection||[]).map((p,i)=>{const mc=_PROJ_METRIC_COL[p.nom]||'#1650b0';return `<div class="tile c6 tpad" style="padding:13px;border-top:3px solid ${mc}">
        <div style="font:800 12.5px var(--sans);color:var(--ink);margin-bottom:1px">${p.nom} <span style="color:var(--faint);font-weight:500;font-size:10px">en ${p.unite}</span></div>
        <div style="font:600 9.5px/1.45 var(--sans);color:var(--muted);margin-bottom:4px">${p.takeaway||''}</div>
        <div id="strat-proj-${i}" style="height:200px"></div>
        <div style="font:italic 400 9px/1.4 var(--sans);color:var(--faint);margin-top:5px">Hypothèses : ${p.hypothese}</div>
      </div>`;}).join("")}
    </div>
    <div id="strat-proj-llm" style="display:none;margin-top:14px;padding:13px 16px;border-radius:10px;border:1px solid #6D28D955;background:radial-gradient(120% 140% at 0 0,#6D28D912,transparent 55%),var(--bg-tile)">
      <div style="font:800 10px var(--sans);color:#6D28D9;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">🤖 Lecture stratégique — ce que la projection change vraiment</div>
      <div id="strat-proj-llm-txt" style="font:500 12.5px/1.7 var(--sans);color:var(--ink)"></div>
    </div>
  </div>`;

  // ── Note méthodologique (transparence sur les limites = crédibilité) ──
  const nm = d.note_methodo;
  const methodo = (nm&&nm.points)?`<div class="tile c12 tpad" style="border-left:3px solid #B45309">
    <div class="chead"><div><div class="tt">🔬 Note méthodologique — limites assumées</div>
    <div class="ts">Ce qu'un statisticien vérifierait : robustesse, comparabilité, causalité</div></div></div>
    ${nm.points.map(p=>`<div style="font:500 11px/1.55 var(--sans);color:var(--ink);padding:5px 0;border-bottom:1px solid var(--line)">• ${p}</div>`).join("")}
  </div>`:'';

  // ── Sources ──
  const sources = `<div class="tile c12 tpad">
    <div class="chead"><div><div class="tt">Sources — transparence totale</div><div class="ts">Toute affirmation s'appuie sur l'une de ces références</div></div></div>
    ${(d.sources||[]).map(s=>`<div style="display:flex;gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line);font:500 11px var(--sans)">
      ${_srcBadge(s.type)} <span style="color:var(--ink)">${s.ref}</span>
      <span style="margin-left:auto;font:600 9px var(--sans);color:var(--faint)">${s.fiabilite}${s.date?(' · '+s.date):''}</span></div>`).join("")}
  </div>`;

  const llm = `<div id="strat-llm-card" class="tile c12 tpad" style="display:none;background:radial-gradient(120% 140% at 0 0,#6D28D915,transparent 55%),var(--bg-tile);border:1px solid #6D28D955;border-left:4px solid #6D28D9">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span style="font-size:17px">💡</span>
      <div style="font:800 12.5px var(--display);color:#6D28D9">Vision créative du Comité de Direction</div>
      <span style="font:700 8px var(--sans);color:#6D28D9;background:#6D28D91a;border:1px solid #6D28D955;border-radius:4px;padding:2px 6px">IA générative · contrainte aux preuves</span>
    </div>
    <div id="strat-llm" style="font:500 12px/1.7 var(--sans);color:var(--ink)"></div>
  </div>`;
  // ── COMITÉ DE DIRECTION — 4 regards, des décisions concrètes ──
  const _effCol={"Faible":"#12895C","Moyen":"#B45309","Élevé":"#E53935"};
  const comite = (d.comite&&d.comite.length)?d.comite.map(dir=>`<div class="tile c6 tpad" style="border-top:3px solid ${dir.couleur}">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:5px">
        <span style="font-size:21px;line-height:1">${dir.icone}</span>
        <div><div style="font:800 14px var(--display);color:${dir.couleur}">${dir.nom}</div>
        <div style="font:600 10px/1.3 var(--sans);color:var(--muted)">${dir.question}</div></div>
      </div>
      <div style="font:500 12.5px/1.65 var(--sans);color:var(--ink);background:var(--bg-raise);border-radius:6px;padding:10px 12px;margin-bottom:9px">${dir.lecture}</div>
      ${(dir.decisions||[]).map((x,i)=>`<div style="margin-bottom:9px;padding-bottom:9px;${i<dir.decisions.length-1?'border-bottom:1px solid var(--line)':''}">
        <div style="font:800 11.5px/1.4 var(--sans);color:var(--ink);display:flex;gap:6px"><span style="color:${dir.couleur}">DÉCISION ${i+1}</span><span style="margin-left:auto;font:700 8px var(--sans);color:${_effCol[x.effort]||'#64748B'};background:${(_effCol[x.effort]||'#64748B')}1a;border-radius:4px;padding:1px 6px;height:fit-content">Effort ${x.effort}</span></div>
        <div style="font:700 11.5px/1.45 var(--sans);color:var(--ink);margin:2px 0 4px">${x.titre}</div>
        <div style="font:500 10.5px/1.5 var(--sans);color:var(--muted);margin-bottom:5px">${x.detail}</div>
        <div style="font:700 10.5px/1.45 var(--sans);color:#0a5e3c;background:#0d7a5012;border-radius:5px;padding:5px 8px;margin-bottom:4px">📈 ${x.impact}</div>
        <div style="font:500 10px/1.45 var(--sans);color:var(--muted)"><b>Pourquoi :</b> ${x.pourquoi} ${(x.sources||[]).map(_srcBadge).join("")}</div>
      </div>`).join("")}
    </div>`).join(""):"";

  // ── VRIST multi-banques (filtrable) ──
  const vr=d.vrist||{};
  const _vComps=(vr.ordre||[]).filter(b=>b!=='SGCI');
  const vrist = (vr.banques)?`<div class="tile c12 tpad" style="border-top:3px solid #6D28D9">
    <div class="chead"><div><div class="tt">VRIST — l'avantage de SGCI est-il DURABLE ? (comparaison)</div>
    <div class="ts">${vr.intro}</div></div></div>
    <div id="strat-vrist-bar" style="margin:6px 0 12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="font:700 10px var(--sans);color:var(--muted)">★ SGCI comparé à :</span>
      ${_vComps.map(b=>`<button data-vb="${b}" onclick="setVristComp('${b}')" style="cursor:pointer;font:700 10px var(--sans);border-radius:6px;padding:5px 13px;border:1px solid var(--line);background:transparent;color:var(--muted)">${b}</button>`).join("")}
    </div>
    <div id="strat-vrist-body"></div>
    <div id="vrist-portee" style="margin-top:12px">
      <div style="padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--bg-raise);font:500 11px var(--sans);color:var(--muted);display:flex;gap:9px;align-items:center"><span class="spin"></span> L'IA rédige la <b>portée pour le métier</b> du VRIST…</div>
    </div>
  </div>`:'';

  // ── Décryptage des concurrents (EF + CB + WEB) ──
  const _BKC={SGCI:'#E2001A',BICICI:'#1650b0',ECOBANK:'#0AA1DD',SIB:'#12895C',NSIA:'#B45309',BNI:'#6D28D9',BACI:'#E91E63'};
  const _enjC=e=>/^MENACE FORTE/.test(e)?'#E53935':/^MENACE PRIX/.test(e)?'#FF8C00':/^MENACE EXP/.test(e)?'#6D28D9':'#64748B';
  const CC=d.concurrents||[];
  const concurrents=CC.length?`<div class="bento">${CC.map(c=>{const col=_BKC[c.banque]||'#1650b0',ec=_enjC(c.enjeu);
    return `<div class="tile c6 tpad" style="border-left:4px solid ${col};padding:13px 15px">
      <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px;flex-wrap:wrap">
        <span style="font:800 15px var(--display);color:${col}">${c.banque}</span>
        <span style="font:500 9px var(--sans);color:var(--muted)">${c.groupe||''}</span>
        <span style="margin-left:auto;display:inline-flex;gap:3px">${(c.sources||[]).map(_srcBadge).join('')}</span>
      </div>
      <div style="font:500 10px/1.55 var(--sans);color:var(--muted);margin-bottom:3px"><b style="color:var(--ink)">Finances</b> <span style="opacity:.6">(dernière année)</span> · ${(c.ef||[]).join(' · ')||'—'}</div>
      <div style="font:500 10px/1.55 var(--sans);color:var(--muted);margin-bottom:7px"><b style="color:var(--ink)">Offre</b> · ${(c.cb||[]).join(' · ')||'—'} · ${c.orientation}</div>
      <div style="font:600 11px/1.55 var(--sans);color:var(--ink);background:var(--bg-raise);border-radius:7px;padding:8px 11px;margin-bottom:6px"><span style="font:800 8px var(--sans);color:${col};text-transform:uppercase;letter-spacing:.05em">Sa stratégie</span><br>${c.strategie}</div>
      <div style="font:700 10px/1.45 var(--sans);color:${ec};background:${ec}12;border-radius:7px;padding:7px 10px">➔ Pour SGCI : ${c.enjeu}</div>
    </div>`;}).join('')}</div>`:'';

  // ── Helper : section claire (numéro + titre + « En clair ») ──
  // GARDE-FOU (2026-07-22, demande explicite du directeur — le bouton « Approfondir avec l'IA »
  // envoyait TOUJOURS les mêmes KPIs génériques (PNB/RN/marge...) peu importe la section cliquée,
  // jamais les VRAIES données déjà calculées de CETTE section (ex. Projection prudent/central/
  // optimiste) → le LLM, sommé de « détailler » une section sans ses vrais chiffres, en
  // INVENTAIT (constat concret : chiffres et calculs faux sur un clic Projection). Fix : chaque
  // section stocke ses propres faits réels dans _STRAT_FACTS[id], et le bouton ne transmet que
  // l'ID (pas un gros JSON dans l'attribut HTML) — askIA() va chercher les vrais faits au clic.
  window._STRAT_FACTS = window._STRAT_FACTS || {};
  const sect=(id,num,titre,enclair,inner,factsObj)=>{
    const _qt=String(titre).replace(/<[^>]+>/g,'').replace(/['"«»]/g,'’').replace(/\s+/g,' ').trim();
    if (factsObj!==undefined) window._STRAT_FACTS[id] = factsObj;
    return `<section id="${id}" style="scroll-margin-top:172px">
    <div style="display:flex;align-items:center;gap:10px;margin:24px 0 3px">
      <span style="font:900 21px var(--display);color:var(--accent-2)">${num}</span>
      <span style="font:800 19px var(--display);color:var(--ink)">${titre}</span>
      <button class="cta" style="margin-left:auto;font:700 9.5px var(--sans);padding:5px 13px;cursor:pointer;white-space:nowrap" onclick="askIA('Analyse stratégique approfondie pour SGCI — ${_qt} : détaille, croise les données EF, CB et Web, et propose des actions concrètes et chiffrées.','${id}')">🔍 Approfondir avec l'IA →</button>
    </div>
    <div style="font:500 13px/1.6 var(--sans);color:var(--muted);background:var(--bg-raise);border-left:3px solid var(--accent-2);border-radius:0 7px 7px 0;padding:8px 12px;margin-bottom:13px">${enclair}</div>
    ${inner}
  </section>`;};

  return _stratStickyBar(d.segment)
    + sect("st-essentiel","①","L'essentiel","<b>En clair :</b> le verdict en une phrase — ce qui va, ce qui ne va pas, quoi faire — puis le diagnostic détaillé des problèmes, du plus grave au moins grave.",
        `${essentiel}<div class="bento" style="margin-top:10px">${synth}${metr}</div><div class="bento" style="margin-top:10px">${_narrBox('diag')}${diag}</div>`,
        {essentiel: es, problemes: d.problemes})
    + sect("st-revel","②","Révélations","<b>En clair :</b> ce que personne ne voit au premier coup d'œil — découvert en croisant les chiffres des 7 banques. Chaque carte : une phrase simple, le détail caché en dessous, et la cause expliquée (recherche web).",
        `<div class="bento" style="margin-bottom:10px">${revs}${_switchHTML(d.couts_changement)}</div>`,
        {revelations: d.revelations, couts_changement: d.couts_changement})
    + sect("st-conc","③","Porter — les 5 forces","<b>En clair :</b> la pression concurrentielle que subit SGCI, via les <b>5 forces de Porter</b> — plus le décryptage de chaque concurrent. Choisis l'onglet.",
        `<div style="display:flex;gap:7px;margin:0 0 12px;flex-wrap:wrap">
           <button id="ctab-porter" class="sec-nav-btn on" onclick="setConcTab('porter')">Porter — 5 forces</button>
           <button id="ctab-conc" class="sec-nav-btn" onclick="setConcTab('conc')">Concurrents décryptés</button>
         </div>
         <div id="conc-porter"><div class="bento">${_narrBox('porter')}${porter}</div></div>
         <div id="conc-decrypt" style="display:none">${concurrents}</div>`,
        {porter: d.porter, concurrents: d.concurrents})
    + sect("st-vrist","④","VRIST — avantage durable","<b>En clair :</b> les avantages de SGCI sont-ils <b>durables</b> ? Le cadre VRIST note chaque banque sur 5 axes (Valeur, Rareté, Inimitabilité, Durabilité, Transformation). Sélectionne un concurrent pour comparer.",
        `<div class="bento">${_narrBox('vrist')}${vrist}</div>`,
        {vrist: d.vrist})
    + sect("st-swot","⑤","SWOT — la synthèse qui mène aux décisions","<b>En clair :</b> on résume Forces, Faiblesses, Opportunités, Menaces. Cette matrice <b>justifie les recommandations</b> de l'onglet Stratégie opérationnelle : chaque action y répond à une faiblesse à corriger ou une opportunité à saisir.",
        `<div class="bento">${_narrBox('swot')}</div>${swot}`,
        {swot: d.swot})
    + sect("st-pestel","⑥","PESTEL — environnement externe","<b>En clair :</b> les 6 forces EXTERNES qui pèsent sur SGCI (Politique, Économique, Social, Technologique, Environnemental, Légal). Chaque point est <b>sourcé</b> (BCEAO, APBEF-CI, GSMA…), pas une opinion.",
        _pestelHTML(d.pestel),
        {pestel: d.pestel})
    + sect("st-proj","⑦","Projection 3 ans — ce que le plan change, chiffré","<b>En clair :</b> 3 scénarios (prudent/central/optimiste) sur les métriques-clés, modèle déterministe dérivé des chiffres réels — jamais inventé par l'IA.",
        projHyp + proj,
        {projection: d.projection, projection_hypotheses: d.projection_hypotheses, roadmap: d.roadmap});
}

// ── Rendu PESTEL (6 facteurs externes, chaque point sourcé) ──────────────────────
function _pestelHTML(p){
  if(!p || !(p.axes||[]).length) return '<div style="color:var(--muted);font:500 12px var(--sans);padding:16px">PESTEL indisponible.</div>';
  const cards = p.axes.map(a=>{
    const pts = (a.points||[]).map(pt=>`<div style="display:flex;gap:7px;align-items:flex-start;margin:5px 0">
        <span style="color:${a.col};font-weight:800;flex-shrink:0">•</span>
        <span style="font:500 11px/1.55 var(--sans);color:var(--ink)">${pt.txt} ${_srcBadge(pt.source)}${pt.src_label?`<span style="font:600 8px var(--sans);color:var(--faint);margin-left:3px">${pt.src_label}</span>`:''}</span>
      </div>`).join('');
    return `<div class="tile c6 tpad" style="border-left:4px solid ${a.col};padding:13px 15px">
      <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:5px">
        <span style="font:900 17px var(--display);color:${a.col}">${a.cle}</span>
        <span style="font:800 13px var(--display);color:var(--ink)">${a.nom}</span>
      </div>
      <div style="font:600 9.5px/1.4 var(--sans);color:${a.col};background:${a.col}12;border-radius:6px;padding:4px 9px;margin-bottom:7px;display:inline-block">${a.resume||''}</div>
      ${pts}
    </div>`;}).join('');
  return `${p.intro?`<div style="font:500 11px/1.55 var(--sans);color:var(--muted);background:var(--bg-raise);border-left:3px solid var(--accent-2);border-radius:0 7px 7px 0;padding:8px 12px;margin-bottom:12px">${p.intro}</div>`:''}
    <div class="bento">${cards}</div>
    <div id="pestel-portee" style="margin-top:14px">
      <div style="padding:14px;border:1px solid var(--line);border-radius:10px;background:var(--bg-raise);font:500 11px var(--sans);color:var(--muted);display:flex;gap:9px;align-items:center"><span class="spin"></span> L'IA rédige la <b>portée pour le métier</b> de ce PESTEL…</div>
    </div>`;
}

// ── Rendu PROPRE générique d'une « portée métier » : 1 ligne par item (pastille + texte), zéro jaune ──
function _porteeHTML(raw, COL, namesAlt){
  if(!raw) return '';
  const md = s => s.replace(/\*\*([^*]+)\*\*/g,'<b style="color:#0F172A">$1</b>')
                   .replace(/\s*\n+\s*/g,' ').replace(/^[\s:–\-]+/,'').trim();
  // 1) isoler la conclusion « ce que le métier doit retenir »
  let body=raw, concl='';
  const parts=raw.split(/#+\s*Ce que le m[ée]tier doit retenir\s*/i);
  if(parts.length>1){ body=parts[0]; concl=parts.slice(1).join(' ').trim(); }
  // 2) retirer titre markdown + consigne éventuellement recopiée
  body=body.replace(/^#+[^\n]*$/gim,'').replace(/Pour CHACUNE[^*]*?(?=\*\*)/i,'');
  // 3) découper par item : **Nom →** …
  const re=new RegExp('\\*\\*\\s*('+namesAlt+')\\s*(?:→|->|:)?\\s*\\*\\*','gi');
  const hits=[]; let m;
  while((m=re.exec(body))!==null) hits.push({name:m[1], end:re.lastIndex, start:m.index});
  let rows='';
  if(hits.length){
    for(let i=0;i<hits.length;i++){
      const seg=body.slice(hits[i].end, i+1<hits.length?hits[i+1].start:body.length);
      const nom=hits[i].name.replace(/^./,c=>c.toUpperCase());
      const c=COL[nom]||COL[nom.normalize('NFD').replace(/[̀-ͯ]/g,'')]||'#475569';
      rows+=`<div style="display:flex;gap:11px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line)">
        <span style="flex-shrink:0;width:112px;font:800 10.5px var(--sans);color:${c};background:${c}14;border:1px solid ${c}44;border-radius:6px;padding:5px 0;text-align:center">${nom}</span>
        <span style="flex:1;font:500 12px/1.7 var(--sans);color:var(--ink)">${md(seg)}</span>
      </div>`;
    }
  } else {
    rows=`<div style="font:500 12px/1.75 var(--sans);color:var(--ink)">${md(body)}</div>`;
  }
  return `<div>${rows}</div>`+(concl?`<div style="margin-top:13px;padding:11px 14px;background:color-mix(in srgb,var(--accent-2) 8%,var(--bg-raise));border-left:4px solid var(--accent-2);border-radius:0 8px 8px 0">
      <div style="font:800 9.5px var(--sans);color:var(--accent-2);text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px">✅ Ce que le métier doit retenir</div>
      <div style="font:600 12px/1.75 var(--sans);color:var(--ink)">${md(concl)}</div></div>`:'');
}
function _pestelPorteeHTML(raw){
  return _porteeHTML(raw, {'Politique':'#6D28D9','Économique':'#1D9E75','Economique':'#1D9E75','Social':'#FF8C00','Technologique':'#0AA1DD','Environnemental':'#12895C','Légal':'#E53935','Legal':'#E53935'},
    'Politique|[ÉE]conomique|Social|Technologique|Environnemental|L[ée]gal');
}
function _vristPorteeHTML(raw){
  return _porteeHTML(raw, {'Valeur':'#378ADD','Rareté':'#1D9E75','Rarete':'#1D9E75','Inimitable':'#7F77DD','Durable':'#FF9800','Transformatif':'#E91E63','Transformatique':'#E91E63'},
    'Valeur|Raret[ée]|Inimitable|Durable|Transformati[fv]');
}

// ── Habillage LLM du Diagnostic 360° (2026-07-16) : la détection reste déterministe
// (seuils réels, cf. detect_problems() côté serveur), seule la prose de chaque preuve
// est reformulée/croisée par Claude. Fallback silencieux = le texte déterministe déjà affiché.
// PAS de flag "déjà fait" global : _renderStrategie() peut réinjecter le HTML déterministe
// (nouveau innerHTML de #strat-root) sans que cette fonction ne soit rappelée autrement —
// un flag figé aurait alors bloqué le patch pour de bon (bug trouvé le 2026-07-16). L'appel
// serveur est déjà caché (quasi instantané au 2e appel) donc pas de coût à re-fetcher ici.
async function _fireStratDiagLLM(segment){
  const nodes=document.querySelectorAll('.diag-preuve');
  if(!nodes.length) return;
  try{
    const r=await fetch(`/api/strategie_diag_llm?segment=${encodeURIComponent(segment||'Particuliers')}`);
    const d=await r.json();
    const preuves=d.preuves||{};
    if(!Object.keys(preuves).length) return;
    nodes.forEach(el=>{
      const t=el.dataset.diagTitre;
      if(t && preuves[t]) el.innerHTML=_brSentences(preuves[t]);
    });
  }catch(e){}
}

// ── Lecture stratégique de la Projection 3 scénarios (2026-07-16, « ajouter du WOW ») :
// le modèle chiffré reste déterministe, Claude croise les métriques déjà calculées par-dessus.
async function _fireStratProjLLM(segment){
  const box=document.getElementById('strat-proj-llm'), txt=document.getElementById('strat-proj-llm-txt');
  if(!box||!txt) return;
  try{
    const r=await fetch(`/api/strategie_projection_llm?segment=${encodeURIComponent(segment||'Particuliers')}`);
    const d=await r.json();
    const a=(d.analyse||'').trim();
    if(a){ txt.innerHTML=a; box.style.display=''; }
  }catch(e){}
}

// ── Analyse de PORTÉE du PESTEL (LLM contraint, stockée) ─────────────────────
async function _firePestelLLM(){
  const div=document.getElementById('pestel-portee');
  if(!div || div.dataset.loaded==='1') return;
  try{
    const r=await fetch('/api/pestel_analyse');
    const d=await r.json();
    const a=(d.analyse||'').trim();
    if(a){
      div.dataset.loaded='1';
      div.innerHTML=`<div style="border:1px solid var(--accent-2);border-left:4px solid var(--accent-2);border-radius:10px;background:color-mix(in srgb,var(--accent-2) 6%,var(--bg-raise));padding:13px 16px">
        <div style="font:700 10px var(--sans);color:var(--accent-2);text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px">🤖 Portée stratégique — ce que ce PESTEL signifie pour le métier</div>
        <div id="pestel-stale-badge" style="display:none"></div>
        ${_pestelPorteeHTML(a)}</div>`;
      _showStaleBadge('pestel-stale-badge', {stale: d.stale, generated_at: d.generated_at});
    } else {
      div.innerHTML='';   // pas d'analyse dispo (LLM indisponible) → on n'affiche rien plutôt qu'un faux contenu
    }
  }catch(e){ div.innerHTML=''; }
}

// ── Analyse de PORTÉE du VRIST (LLM contraint, stockée) ─────────────────────
async function _fireVristLLM(){
  const div=document.getElementById('vrist-portee');
  if(!div || div.dataset.loaded==='1') return;
  try{
    const r=await fetch('/api/vrist_analyse');
    const d=await r.json();
    const a=(d.analyse||'').trim();
    if(a){
      div.dataset.loaded='1';
      div.innerHTML=`<div style="border:1px solid #6D28D9;border-left:4px solid #6D28D9;border-radius:10px;background:color-mix(in srgb,#6D28D9 6%,var(--bg-raise));padding:13px 16px;margin-top:12px">
        <div style="font:700 10px var(--sans);color:#6D28D9;text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px">🤖 Portée stratégique — ce que le VRIST signifie pour le métier</div>
        <div id="vrist-stale-badge" style="display:none"></div>
        ${_vristPorteeHTML(a)}</div>`;
      _showStaleBadge('vrist-stale-badge', {stale: d.stale, generated_at: d.generated_at});
    } else { div.innerHTML=''; }
  }catch(e){ div.innerHTML=''; }
}

// ── Coûts de changement : économies CHIFFRÉES en venant chez SGCI (100% data CB) ──────
function _switchHTML(sw){
  if(!sw) return '';
  const gains=(sw.gains||[]), fuites=(sw.fuites||[]);
  if(!gains.length && !fuites.length) return '';
  const fmt = n => (n||0).toLocaleString('fr-FR');
  const cG='#12895C', cF='#E08600';
  // Affichage EXPLICITE (plus d'ambiguïté « X→Y ») : on nomme toujours les deux prix
  // — « SGCI 11 550 F · ECOBANK 15 500 F » — puis qui est le moins cher.
  const line=(it,sens,col)=>{
    const verdict = sens==='gain' ? 'SGCI moins cher' : `${it.banque} moins cher`;
    const ecartLbl = sens==='gain' ? "d'économie/an" : "d'écart/an";
    // Tag segment (2026-07-22, demande directeur : « pour Entreprises on néglige ??? ») — chaque
    // ligne vient de Particuliers OU Entreprises, jamais ambigu, maintenant visible ici aussi.
    const segTag = it.segment==='Entreprises'
      ? `<span style="font:700 8px var(--sans);color:#1650b0;background:#1650b01a;border-radius:4px;padding:1px 6px;margin-left:6px;text-transform:uppercase;letter-spacing:.05em">Entreprises</span>`
      : `<span style="font:700 8px var(--sans);color:#64748B;background:#64748B1a;border-radius:4px;padding:1px 6px;margin-left:6px;text-transform:uppercase;letter-spacing:.05em">Particuliers</span>`;
    return `<div style="padding:6px 0;border-bottom:1px solid var(--line)">
      <div style="display:flex;align-items:baseline;gap:8px">
        <span style="font:900 14px var(--display);color:${col};white-space:nowrap;min-width:78px;text-align:right">${fmt(it.eco)} F${it.suffixe||''}</span>
        <span style="font:700 10.5px/1.4 var(--sans);color:var(--ink)">${it.libelle}<span style="font-weight:500;color:var(--faint)"> · ${ecartLbl}</span>${segTag}</span>
      </div>
      <div style="font:600 10px var(--sans);color:var(--muted);padding-left:86px;margin-top:2px">
        SGCI <b style="color:var(--ink)">${fmt(it.sgci)} F</b> &nbsp;·&nbsp; ${it.banque} <b style="color:var(--ink)">${fmt(it.conc)} F</b>
        <span style="color:${col};font-weight:800"> — ${verdict}</span>
      </div>
    </div>`;
  };
  const caveat = `<div style="font:500 8.5px/1.4 var(--sans);color:var(--faint);margin-top:8px;padding-top:6px;border-top:1px dashed var(--line)">Prix réels CB, annualisés · services très demandés à périmètre comparable · tenue de compte & frais de dossier EXCLUS (dépendent du type de compte/crédit).</div>`;
  // ── Carte ATOUT PRIX (acquisition) ──
  const cardGain = gains.length?`<div class="tile c6 tpad" style="border-left:4px solid ${cG};background:radial-gradient(130% 150% at 0 0,${cG}0d,transparent 55%),var(--bg-tile)">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;flex-wrap:wrap">
      <span style="font-size:17px">💸</span>
      <span style="font:800 8.5px var(--sans);color:${cG};background:${cG}1a;border:1px solid ${cG}55;border-radius:5px;padding:2px 8px;text-transform:uppercase;letter-spacing:.08em">Atout prix · acquisition</span>
      ${_srcBadge('CB')}
    </div>
    <div style="font:800 13px/1.35 var(--sans);color:var(--ink);margin-bottom:6px">Venir chez SGCI fait économiser sur des services très demandés</div>
    <div style="font:600 11px/1.6 var(--sans);background:${cG}10;border-radius:7px;padding:8px 10px"><b style="color:${cG}">En clair :</b> sur le quotidien, SGCI est souvent la moins chère — jusqu'à <b>${fmt(sw.max_gain)} F/an</b> d'économie en la rejoignant.</div>
    <div style="margin-top:8px;max-height:420px;overflow-y:auto;padding-right:4px">${gains.map(it=>line(it,'gain',cG)).join('')}</div>
    <div style="font:600 8.5px var(--sans);color:var(--faint);text-align:center;margin-top:4px">${gains.length} atout${gains.length>1?'s':''} au total · fais défiler pour tout voir</div>
    ${caveat}
  </div>`:'';
  // ── Carte RISQUE PRIX (fuite) ──
  const fuiteBody = fuites.length
    ? `<div style="font:600 11px/1.6 var(--sans);background:${cF}10;border-radius:7px;padding:8px 10px"><b style="color:${cF}">En clair :</b> sur les services demandés, SGCI n'est <b>presque jamais</b> beaucoup plus chère (écart max <b>${fmt(sw.max_fuite)} F/an</b>) → risque de fuite par le prix <b>limité</b>. Le seul écart à surveiller :</div>
       <div style="margin-top:8px;max-height:420px;overflow-y:auto;padding-right:4px">${fuites.map(it=>line(it,'fuite',cF)).join('')}</div>
       <div style="font:600 8.5px var(--sans);color:var(--faint);text-align:center;margin-top:4px">${fuites.length} risque${fuites.length>1?'s':''} au total · fais défiler pour tout voir</div>`
    : `<div style="font:600 11px/1.6 var(--sans);background:${cF}10;border-radius:7px;padding:8px 10px"><b style="color:${cF}">En clair :</b> sur les services très demandés et comparables, <b>aucun écart significatif</b> en défaveur de SGCI → le prix n'est <b>pas</b> un motif de départ.</div>`;
  const cardFuite = `<div class="tile c6 tpad" style="border-left:4px solid ${cF};background:radial-gradient(130% 150% at 0 0,${cF}0d,transparent 55%),var(--bg-tile)">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;flex-wrap:wrap">
      <span style="font-size:17px">🚪</span>
      <span style="font:800 8.5px var(--sans);color:${cF};background:${cF}1a;border:1px solid ${cF}55;border-radius:5px;padding:2px 8px;text-transform:uppercase;letter-spacing:.08em">Risque prix · fuite</span>
      ${_srcBadge('CB')}
    </div>
    <div style="font:800 13px/1.35 var(--sans);color:var(--ink);margin-bottom:6px">Ce qui pourrait pousser un client à partir (par le prix)</div>
    ${fuiteBody}
  </div>`;
  const llmBox = `<div id="strat-switch-llm" class="tile c12" style="display:none;margin-bottom:10px;padding:12px 15px;border-radius:10px;border:1px solid #6D28D955;background:radial-gradient(120% 140% at 0 0,#6D28D912,transparent 55%),var(--bg-tile)">
    <div style="font:800 10px var(--sans);color:#6D28D9;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px">🤖 Lecture stratégique</div>
    <div id="strat-switch-llm-txt" style="font:500 12px/1.65 var(--sans);color:var(--ink)"></div>
  </div>`;
  return cardGain + cardFuite + llmBox;
}

// ── Lecture stratégique des coûts de changement (2026-07-16) : mêmes montants déterministes,
// Claude ajoute une lecture par-dessus (rapport de force atouts/risques, implication commerciale).
async function _fireStratSwitchLLM(segment){
  const box=document.getElementById('strat-switch-llm'), txt=document.getElementById('strat-switch-llm-txt');
  if(!box||!txt) return;
  try{
    const r=await fetch(`/api/strategie_switch_llm?segment=${encodeURIComponent(segment||'Particuliers')}`);
    const d=await r.json();
    const a=(d.analyse||'').trim();
    if(a){ txt.innerHTML=a; box.style.display=''; }
  }catch(e){}
}

// ── Lecture stratégique du plan-trajectoire 3 ans (2026-07-16) : actes/chiffrage restent
// déterministes, Claude explique la logique de séquençage par-dessus.
async function _fireStratRoadmapLLM(segment){
  const box=document.getElementById('strat-roadmap-llm'), txt=document.getElementById('strat-roadmap-llm-txt');
  if(!box||!txt) return;
  try{
    const r=await fetch(`/api/strategie_roadmap_llm?segment=${encodeURIComponent(segment||'Particuliers')}`);
    const d=await r.json();
    const a=(d.analyse||'').trim();
    if(a){ txt.innerHTML=a; box.style.display=''; }
  }catch(e){}
}

function _mdLite(s){
  // markdown léger → HTML : titres ##, propositions (-/•/💡), actes développés (▸), justif (→), gras, sources
  const esc = x=>x.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const lines = esc(String(s||"")).split(/\n/); let out="";
  const inline = t => t
    .replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')
    .replace(/_\((.+?)\)_/g,'<span style="font:700 9px var(--sans);color:#6D28D9;background:#6D28D914;border-radius:4px;padding:1px 6px;margin-left:4px">$1</span>')
    .replace(/\[(EF|CB|REGL|WEB)\]/g,(_,a)=>_srcBadge(a));
  for(let raw of lines){
    const l=raw.trim();
    if(!l) continue;
    if(/^#+\s/.test(l)){ out+=`<div style="font:800 12.5px var(--display);color:#6D28D9;margin:12px 0 4px">${inline(l.replace(/^#+\s/,''))}</div>`; continue; }
    if(/^[-•]\s*💡/.test(l)||/^💡/.test(l)){   // proposition
      out+=`<div style="font:700 11.5px/1.5 var(--sans);color:var(--ink);margin:10px 0 3px;padding-left:2px">💡 ${inline(l.replace(/^[-•]\s*💡\s*/,'').replace(/^💡\s*/,''))}</div>`; continue; }
    if(/^[-•]\s/.test(l)){   // puce simple
      out+=`<div style="position:relative;padding:3px 0 3px 16px;font:500 11px/1.55 var(--sans);color:var(--ink)"><span style="position:absolute;left:2px;color:#6D28D9">▹</span>${inline(l.replace(/^[-•]\s/,''))}</div>`; continue; }
    if(/^▸\s/.test(l)){      // acte développé
      out+=`<div style="position:relative;margin:3px 0 3px 16px;padding-left:14px;font:500 10.5px/1.55 var(--sans);color:var(--muted)"><span style="position:absolute;left:0;color:#12895C;font-weight:800">▸</span>${_brSentences(inline(l.replace(/^▸\s/,'')))}</div>`; continue; }
    if(/^→\s/.test(l)||/^Pourquoi\s*:/i.test(l)){   // justification
      out+=`<div style="font:600 10px/1.5 var(--sans);color:#0a5e3c;background:#0d7a5010;border-left:3px solid #12895C;border-radius:0 5px 5px 0;padding:5px 9px;margin:4px 0 8px 16px">${_brSentences(inline(l.replace(/^→\s/,'➔ ')))}</div>`; continue; }
    if(/^\*?Constat\s*:/i.test(l)){   // constat du directeur
      out+=`<div style="font:italic 600 10.5px/1.5 var(--sans);color:var(--muted);margin:2px 0 6px">${_brSentences(inline(l.replace(/^\*?Constat\s*:\*?/i,'<b>Constat :</b>')))}</div>`; continue; }
    out+=`<div style="font:500 11px/1.6 var(--sans);color:var(--ink);margin:3px 0">${_brSentences(inline(l))}</div>`;
  }
  return out;
}

// ── VRIST : SGCI (référence) comparé à un concurrent ──
let _VRIST_DATA = {}, _VRIST_COMP = "BICICI";
const _VSC="#1650b0", _VCC="#E91E63";   // SGCI bleu · concurrent magenta
function _vristRadar(comp){
  // Radar SVG natif — DEUX polygones superposés : SGCI + concurrent
  const el=document.getElementById('strat-vrist-radar'); if(!el) return;
  const S=(_VRIST_DATA.banques||{})['SGCI'], C=(_VRIST_DATA.banques||{})[comp];
  if(!S||!C) return;
  const dimsS=S.dimensions||[], dimsC=C.dimensions||[]; const N=dimsS.length||5;
  const W=240,H=232,cx=W/2,cy=H/2+4,R=72;
  const ang=i=>(-90+i*360/N)*Math.PI/180;
  const pt=(i,r)=>[cx+Math.cos(ang(i))*r, cy+Math.sin(ang(i))*r];
  let svg=`<svg viewBox="0 0 ${W} ${H}" width="100%" style="overflow:visible">`;
  for(let g=2;g<=10;g+=2){const r=R*g/10;svg+=`<polygon points="${dimsS.map((_,i)=>pt(i,r).join(',')).join(' ')}" fill="none" stroke="rgba(150,150,150,.16)" stroke-width="1"/>`;}
  dimsS.forEach((d,i)=>{const [x,y]=pt(i,R);svg+=`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="rgba(150,150,150,.20)"/>`;
    const [lx,ly]=pt(i,R+14);svg+=`<text x="${lx}" y="${ly}" font-size="10" font-weight="800" fill="#94A3B8" text-anchor="middle" dominant-baseline="middle">${d.cle}</text>`;});
  // concurrent (derrière, pointillé)
  svg+=`<polygon points="${dimsC.map((d,i)=>pt(i,R*d.score/10).join(',')).join(' ')}" fill="${_VCC}1e" stroke="${_VCC}" stroke-width="2" stroke-dasharray="4,2"/>`;
  // SGCI (devant, plein)
  svg+=`<polygon points="${dimsS.map((d,i)=>pt(i,R*d.score/10).join(',')).join(' ')}" fill="${_VSC}24" stroke="${_VSC}" stroke-width="2.5"/>`;
  dimsS.forEach((d,i)=>{const [x,y]=pt(i,R*d.score/10);svg+=`<circle cx="${x}" cy="${y}" r="2.6" fill="${_VSC}"/>`;});
  svg+=`</svg>`;
  el.innerHTML=svg; el.style.height="";
}
function _renderVristCompare(comp){
  const S=(_VRIST_DATA.banques||{})['SGCI'], C=(_VRIST_DATA.banques||{})[comp];
  const body=document.getElementById('strat-vrist-body'); if(!S||!C||!body) return;
  const dimsS=S.dimensions||[], dimsC=C.dimensions||[];
  const _sens={'+':['#12895C','▲'],'-':['#E53935','▼'],'~':['#94A3B8','■']};
  // barre labellisée pleine largeur (0..10) — lisible
  const bar=(label,val,col)=>`<div style="display:flex;align-items:center;gap:9px;margin:2px 0">
      <span style="width:62px;flex-shrink:0;font:700 9px var(--sans);color:${col};text-align:right">${label}</span>
      <div style="flex:1;background:var(--bg-raise);border-radius:5px;height:13px;overflow:hidden"><div style="width:${val*10}%;height:100%;background:${col};border-radius:5px"></div></div>
      <span style="width:18px;flex-shrink:0;font:800 12px var(--display);color:${col}">${val}</span></div>`;
  const mkDrv=(arr)=>(arr||[]).map(dr=>{const s=_sens[dr.sens]||_sens['~'];
      return `<span style="white-space:nowrap;margin-right:12px"><span style="color:${s[0]};font-weight:800">${s[1]}</span> ${dr.txt} ${_srcBadge(dr.source)}</span>`;}).join('');
  const rows=dimsS.map((d,i)=>{
    const dc=dimsC[i]||{};
    const sv=d.score, cv=dc.score||0, gap=Math.abs(sv-cv);
    const winner=sv>cv?'S':sv<cv?'C':'=';
    const driversS=mkDrv(d.drivers), driversC=mkDrv(dc.drivers);
    const wcol=winner==='S'?_VSC:winner==='C'?_VCC:'#94A3B8';
    const verdict=winner==='='?`${d.nom} : les deux banques à égalité (${sv}/10).`
      :`Sur ${d.nom}, <b style="color:${wcol}">${winner==='S'?'SGCI':comp}</b> mène ${sv}–${cv} (écart ${gap} pt${gap>1?'s':''}).`;
    return `<div style="padding:10px 0 9px;border-bottom:1px solid var(--line)">
      <div style="display:flex;align-items:center;margin-bottom:5px">
        <span style="font:800 12.5px var(--sans);color:var(--ink);flex:1">${d.cle} — ${d.nom}</span>
        <span style="font:800 8.5px var(--sans);color:${wcol};background:${wcol}16;border-radius:5px;padding:2px 9px">${winner==='S'?'✓ SGCI mène':winner==='C'?'▲ '+comp+' mène':'à égalité'}</span>
      </div>
      ${bar('★ SGCI',sv,_VSC)}
      ${bar(comp,cv,_VCC)}
      <div style="font:500 9.5px/1.5 var(--sans);color:var(--ink);margin-top:6px">${verdict}</div>
      <div style="font:500 9px/1.7 var(--sans);color:var(--muted);margin-top:4px"><span style="font-weight:800;color:${_VSC}">Pourquoi SGCI :</span> ${driversS}</div>
      <div style="font:500 9px/1.7 var(--sans);color:var(--muted);margin-top:2px"><span style="font-weight:800;color:${_VCC}">Pourquoi ${comp} :</span> ${driversC}</div>
    </div>`;
  }).join('');
  const leads=dimsS.filter((d,i)=>d.score>(dimsC[i]||{}).score).map(d=>d.nom);
  const trails=dimsS.filter((d,i)=>d.score<(dimsC[i]||{}).score).map(d=>d.nom);
  const gcol=g=>+g>=7?'#1D9E75':+g>=5?'#FF9800':'#E53935';
  body.innerHTML=`<div style="display:grid;grid-template-columns:235px 1fr;gap:18px;align-items:start">
    <div>
      <div style="display:flex;gap:8px;margin-bottom:6px">
        <div class="tile" style="flex:1;text-align:center;padding:11px 6px;border-top:3px solid ${_VSC}">
          <div style="font:700 8px var(--sans);color:var(--faint);text-transform:uppercase">★ SGCI</div>
          <div style="font:900 26px var(--display);color:${_VSC};line-height:1.1">${S.global}</div>
          <div style="font:700 8px var(--sans);color:${gcol(S.global)}">${S.label}</div>
        </div>
        <div class="tile" style="flex:1;text-align:center;padding:11px 6px;border-top:3px solid ${_VCC}">
          <div style="font:700 8px var(--sans);color:var(--faint);text-transform:uppercase">${comp}</div>
          <div style="font:900 26px var(--display);color:${_VCC};line-height:1.1">${C.global}</div>
          <div style="font:700 8px var(--sans);color:${gcol(C.global)}">${C.label}</div>
        </div>
      </div>
      <div id="strat-vrist-radar" style="height:232px"></div>
      <div style="display:flex;justify-content:center;gap:14px;font:700 9px var(--sans)">
        <span style="color:${_VSC}">▬ SGCI</span><span style="color:${_VCC}">┄ ${comp}</span>
      </div>
    </div>
    <div>
      <div style="font:700 9px var(--sans);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Comparaison dimension par dimension · verdict + drivers des DEUX banques (s'adapte au concurrent choisi)</div>
      ${rows}
      <div style="font:500 11px/1.65 var(--sans);color:var(--ink);background:var(--bg-raise);border-radius:8px;padding:10px 13px;margin-top:11px">
        <b style="color:${_VSC}">SGCI devance</b> sur : ${leads.join(', ')||'—'}.<br>
        <b style="color:${_VCC}">${comp} devance</b> sur : ${trails.join(', ')||'—'}.
      </div>
    </div>
  </div>`;
  setTimeout(()=>{ try{ _vristRadar(comp); }catch(e){} }, 30);
}
function setVristComp(bk){
  if(bk==='SGCI') return;
  _VRIST_COMP=bk; _renderVristCompare(bk);
  document.querySelectorAll('#strat-vrist-bar [data-vb]').forEach(b=>{
    const on=b.dataset.vb===bk;
    b.style.border=`1px solid ${on?_VCC:'var(--line)'}`;
    b.style.background=on?_VCC:'transparent';
    b.style.color=on?'#fff':'var(--muted)';
  });
}
function setConcTab(t){
  const panels={conc:'conc-decrypt',porter:'conc-porter'};
  Object.entries(panels).forEach(([k,id])=>{const el=document.getElementById(id);if(el)el.style.display=(k===t?'':'none');});
  ['conc','porter'].forEach(k=>{const b=document.getElementById('ctab-'+k);if(b)b.classList.toggle('on',k===t);});
}

// ── Projection 3 ans — dashboard filtrable par scénario (2026-07-24, version A) —
// canevas repris tel quel : Formulation chiffrée / Justification / Indicateurs chiffrés /
// Niveau de certitude, + plan An1→An2→An3 propre à chaque scénario. ─────────────────────────
const _PROJ_SC_COL = {prudent:'#94A3B8', central:'#12895C', optimiste:'#1650b0'};
// Un seul scénario affiché à la fois (cohérent avec le mode onglets utilisé partout ailleurs
// dans l'app) — bascule le bloc complet + redimensionne son graphique Plotly (rendu à taille 0
// pendant qu'il était caché, comme pour les autres graphiques de sections masquées).
function setProjScTab(cle){
  ['prudent','central','optimiste'].forEach(c=>{
    const el = document.getElementById('proj-sc-'+c); if(el) el.style.display = (c===cle ? '' : 'none');
  });
  document.querySelectorAll('[data-projsc]').forEach(b=>{
    const on = b.dataset.projsc===cle, col = _PROJ_SC_COL[b.dataset.projsc];
    if(on){ b.style.background=col; b.style.color='#fff'; b.style.border=`1px solid ${col}`; b.style.boxShadow=`0 4px 12px ${col}55`; }
    else{ b.style.background='var(--bg-raise)'; b.style.color='var(--muted)'; b.style.border='1px solid var(--line)'; b.style.boxShadow='none'; }
  });
  requestAnimationFrame(()=>{
    if(!window.Plotly) return;
    const el = document.getElementById('proj-sc-chart-'+cle);
    if(el && el.offsetParent!==null){ try{ Plotly.Plots.resize(el); }catch(e){} }
  });
}
// Graphique propre à CHAQUE scénario (1 ligne colorée = ce scénario, pointillé gris = sans
// rien changer) — remplace l'ancien graphique unique à 3 lignes superposées, jugé peu lisible
// ("je clique sur Central je vois pareil"). Appelé après insertion du DOM (cf. _stratCharts).
function _stratProjScenarioCharts(d){
  if(!window.Plotly) return;
  const ph = d.projection_hypotheses; if(!ph || !ph.scenarios) return;
  ph.scenarios.forEach(s=>{
    const el = document.getElementById('proj-sc-chart-'+s.cle); if(!el) return;
    const serie = s.serie_rn, actuel = s.serie_rn_actuel;
    if(!serie || !actuel) return;
    const col = _PROJ_SC_COL[s.cle];
    const x = ["Aujourd'hui","An 1","An 2","An 3"];
    const fmt = v => String(v).replace(".",",")+" Mds";
    const lab = arr => arr.map((v,k)=> (k===0||k===arr.length-1) ? fmt(v) : "");
    const all = [...serie, ...actuel];
    const lo = Math.min(...all), hi = Math.max(...all), pad=(hi-lo)*0.22||1;
    // Ligne "sans rien changer" en gris ATTÉNUÉ (opacité réduite) plutôt qu'un gris plein —
    // pour le scénario Prudent, dont la couleur propre EST le gris (#94A3B8), un gris plein
    // sur les deux lignes les rendait quasi indissociables. L'opacité fait reculer la ligne de
    // référence visuellement quelle que soit la couleur du scénario.
    Plotly.newPlot(el,[
      {x,y:actuel,name:"Sans rien changer",mode:"lines+markers",
       line:{color:"rgba(148,163,184,.45)",width:2,dash:"dot"},marker:{size:5,color:"rgba(148,163,184,.45)"},
       hovertemplate:"Sans rien changer<br>%{x} : %{y} Mds<extra></extra>"},
      {x,y:serie,name:"Scénario "+s.nom,mode:"lines+markers+text",
       text:lab(serie),textposition:"top center",
       textfont:{size:9.5,color:col,family:"Inter,sans-serif"},
       line:{color:col,width:3.5},marker:{size:7,color:col},
       hovertemplate:"Scénario "+s.nom+"<br>%{x} : %{y} Mds<extra></extra>"}
    ],{
      margin:{t:8,b:34,l:38,r:10},showlegend:true,
      legend:{orientation:"h",y:-0.28,x:0,font:{size:8.5}},
      font:{family:"Inter,sans-serif"},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{tickfont:{size:9},gridcolor:"rgba(150,150,150,.10)",fixedrange:true},
      yaxis:{tickfont:{size:9},gridcolor:"rgba(150,150,150,.15)",range:[lo-pad,hi+pad],fixedrange:true,zeroline:false},
    },{responsive:true,displayModeBar:false,staticPlot:_REAL_TOUCH});
  });
}

// ── Propositions IA par directeur + filtres ──
let _PROP_DIR = "";
const _DIRMAP = [
  {re:/financ/i, id:'fin',  label:'Financier',  icon:'💰', col:'#0a5e3c'},
  {re:/commerc/i,id:'com',  label:'Commercial', icon:'🤝', col:'#1650b0'},
  {re:/marketing/i,id:'mkt',label:'Marketing',  icon:'📣', col:'#B45309'},
  {re:/innov/i,  id:'inno', label:'Innovation', icon:'🚀', col:'#6D28D9'},
];
function setPropDir(id){
  _PROP_DIR=id;
  document.querySelectorAll('#strat-props [data-dir]').forEach(c=>{ c.style.display=(id==="all"||c.dataset.dir===id)?"":"none"; });
  document.querySelectorAll('#strat-props-bar [data-chip]').forEach(b=>{ b.classList.toggle('on', b.dataset.chip===id); });
}
const _inlineProp = t => _brSentences(String(t||"").replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/\*\*(.+?)\*\*/g,'<b style="color:var(--ink)">$1</b>')
  .replace(/\[(EF|CB|REGL|WEB)(?:\s*:\s*([^\]]+))?\]/g,(_,a,art)=>_srcBadge(a)+(art?` <span style="font:600 8.5px var(--sans);color:var(--muted);font-style:italic">${art.trim()}</span>`:'')));
function _parseProps(md){
  const dirs=[];
  String(md||"").split(/\n(?=#+\s)/).forEach(sec=>{
    sec=sec.trim(); if(!sec) return;
    const lines=sec.split(/\n/);
    const title=lines[0].replace(/^#+\s*/,'').trim();
    const dm=_DIRMAP.find(d=>d.re.test(title))||{id:'autre',label:title.replace(/[^A-Za-zÀ-ÿ ]/g,'').trim()||'Autre',col:'#64748B'};
    let constat='', props=[], cur=null;
    for(let i=1;i<lines.length;i++){
      const l=lines[i].trim(); if(!l) continue;
      if(/^\*?Constat\s*:/i.test(l)){ constat=l.replace(/^\*?Constat\s*:\*?\s*/i,'').replace(/\*+$/,''); continue; }
      if(/^[-•]\s/.test(l)){
        let t=l.replace(/^[-•]\s*💡?\s*/,'');
        const nm=t.match(/\*\*(.+?)\*\*/), sg=t.match(/_\((.+?)\)_/);
        const but=t.replace(/\*\*.+?\*\*/,'').replace(/_\(.+?\)_/,'').replace(/^[\s—:–-]+/,'').trim();
        cur={name:nm?nm[1]:t.slice(0,40),seg:sg?sg[1]:'',but:but,actes:[],justif:''}; props.push(cur); continue;
      }
      if(/^▸\s/.test(l)&&cur){ cur.actes.push(l.replace(/^▸\s*/,'')); continue; }
      if((/^→\s/.test(l)||/^Pourquoi\s*:/i.test(l))&&cur){ cur.justif=l.replace(/^→\s*/,'').replace(/^Pourquoi\s*:?\s*/i,''); continue; }
      if(cur&&cur.actes.length) cur.actes[cur.actes.length-1]+=' '+l; else if(cur&&!cur.justif) cur.but+=' '+l;
    }
    dirs.push(Object.assign({},dm,{constat,props:props.slice(0,4)}));  // EXACTEMENT 4 recos/direction (les plus pertinentes, le LLM les classe en premier)
  });
  return dirs;
}
function _propCard(p, dm){
  const segCol={Entreprises:'#1650b0',Particuliers:'#B45309'}[p.seg]||'#64748B';
  const acts=(p.actes||[]).map((a,i)=>`<div style="display:flex;gap:8px;padding:3px 0">
      <span style="flex-shrink:0;font:800 8.5px var(--sans);color:${dm.col};background:${dm.col}14;border-radius:4px;min-width:16px;height:16px;display:inline-flex;align-items:center;justify-content:center;margin-top:1px">${i+1}</span>
      <span style="font:500 10.5px/1.5 var(--sans);color:var(--muted)">${_inlineProp(a)}</span></div>`).join('');
  return `<div class="tile c6 tpad" data-dir="${dm.id}" style="border-left:3px solid ${dm.col};padding:12px 14px">
    <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;flex-wrap:wrap">
      <span style="font:800 12.5px var(--sans);color:var(--ink)">${p.name||'—'}</span>
      ${p.seg?`<span style="font:700 8px var(--sans);color:${segCol};background:${segCol}16;border-radius:4px;padding:1px 7px">${p.seg}</span>`:''}
    </div>
    ${p.but?`<div style="font:600 10.5px/1.5 var(--sans);color:var(--ink);margin-bottom:6px">${_inlineProp(p.but)}</div>`:''}
    ${acts}
    ${p.justif?`<div style="font:500 9.5px/1.45 var(--sans);color:var(--muted);margin-top:8px;padding-top:7px;border-top:1px solid var(--line)"><span style="font:800 8px var(--sans);color:${dm.col};text-transform:uppercase;letter-spacing:.05em">Pourquoi</span> ${_inlineProp(p.justif)}</div>`:''}
  </div>`;
}

// « L'essentiel » rédigé par le LLM (ancré sur les faits calculés) → remplace le déterministe.
// Reproductible & évolutif : le backend calcule tout depuis strategie.build() et met en cache.
// Un seul badge partagé pour toute la couche narrative Stratégie (narr/narr2/narr3) : dès QU'UN
// SEUL des 3 appels revient stale, on prévient — pas la peine de multiplier les badges.
window._stratStaleAny = false;
function _stratStaleReport(j){
  if(j && j.stale) window._stratStaleAny = true;
  _showStaleBadge('strat-stale-badge', {stale: window._stratStaleAny, generated_at: j && j.generated_at});
}

async function _loadStratNarr(segment){
  window._stratStaleAny = false;   // repart de zéro à chaque (re)chargement de segment
  try{
    const r = await fetch(`/api/strategie_narr?segment=${encodeURIComponent(segment||'Particuliers')}`);
    if(!r.ok) return;
    const j = (await r.json()) || {};
    const nr = j.narr || {};
    _stratStaleReport(j);
    if(!nr.verdict) return;                                   // pas de LLM → on garde le déterministe
    const v = document.getElementById('strat-narr-verdict');  if(v) v.innerHTML = nr.verdict;
    const s = document.getElementById('strat-narr-surveiller'); if(s && nr.surveiller) s.innerHTML = nr.surveiller;
    document.querySelectorAll('[data-narr]').forEach(el=>{
      const k = el.getAttribute('data-narr');
      if(k && nr[k]) el.innerHTML = nr[k];
    });
  }catch(e){ /* silencieux : le déterministe reste affiché */ }
  _loadStratNarr2(segment);
}

// Lectures stratégiques par section (diag/swot/porter/vrist/plan) + récits des révélations —
// rédigées par le LLM, ancrées sur les faits (clé de cache = hash des faits → ÉVOLUTIF).
async function _loadStratNarr2(segment){
  try{
    const r = await fetch(`/api/strategie_narr2?segment=${encodeURIComponent(segment||'Particuliers')}`);
    if(!r.ok) return;
    const j = (await r.json()) || {};
    const nr = j.narr || {};
    _stratStaleReport(j);
    document.querySelectorAll('[data-narr2]').forEach(el=>{
      const k = el.getAttribute('data-narr2');
      if(!k || !nr[k]) return;                                 // pas de LLM → fallback déterministe
      if(el.tagName==='SPAN'){ el.innerHTML = nr[k]; return; } // récit d'une révélation
      el.innerHTML = `<div style="font:800 8.5px var(--sans);color:#6D28D9;text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px">◆ Lecture stratégique</div>${nr[k]}`;
      el.style.display = '';
    });
  }catch(e){ /* silencieux */ }
  _loadStratNarr3(segment);
}

// Reformulation LLM de la couche structurelle (puces SWOT, résumés Porter, thèmes du plan,
// titres/actions des révélations) — remplace le texte fixe en place, ancré sur les mêmes faits.
async function _loadStratNarr3(segment){
  try{
    const r = await fetch(`/api/strategie_narr3?segment=${encodeURIComponent(segment||'Particuliers')}`);
    if(!r.ok) return;
    const j = (await r.json()) || {};
    const nr = j.narr || {};
    _stratStaleReport(j);
    document.querySelectorAll('[data-narr3]').forEach(el=>{
      const k = el.getAttribute('data-narr3');
      if(!k || !nr[k]) return;                                  // pas de LLM → fallback déterministe
      el.innerHTML = nr[k];
    });
  }catch(e){ /* silencieux */ }
}

function _renderProps(md, verif){
  const bar=document.getElementById('strat-props-bar'), box=document.getElementById('strat-props');
  if(!box) return;
  const dirs=_parseProps(md);
  const counts={}; let html='';
  dirs.forEach(dm=>{
    counts[dm.id]=(counts[dm.id]||0)+dm.props.length;
    html+=`<div class="tile c12" data-dir="${dm.id}" style="background:none;border:none;box-shadow:none;padding:16px 2px 2px">
      <div style="display:flex;align-items:center;gap:9px">
        <span style="width:11px;height:11px;border-radius:3px;background:${dm.col};flex-shrink:0"></span>
        <span style="font:800 14px var(--display);color:${dm.col}">${dm.label}</span>
        <span style="font:600 9.5px var(--sans);color:var(--faint)">— ${dm.props.length} actions à mener</span>
      </div>
      ${dm.constat?`<div style="font:italic 500 10.5px/1.5 var(--sans);color:var(--muted);margin:4px 0 0 20px">${_inlineProp(dm.constat)}</div>`:''}
    </div>`;
    dm.props.forEach(p=>{ html+=_propCard(p, dm); });
  });
  let chips='', firstDir=null;
  _DIRMAP.forEach(d=>{ if(counts[d.id]){ if(!firstDir) firstDir=d.id;
    chips+=`<button data-chip="${d.id}" class="sec-nav-btn${(_PROP_DIR===d.id||(!_PROP_DIR&&d.id===firstDir))?' on':''}" onclick="setPropDir('${d.id}')">${d.label} (${counts[d.id]})</button>`; } });
  if(bar) bar.innerHTML=`<div class="seg" style="margin:0;display:flex;flex-wrap:wrap;gap:6px;align-items:center">${chips}</div>`;
  box.className="bento"; box.style.display="";
  // 2026-07-27 (demande explicite du directeur) : le footer de transparence technique
  // (taux de chiffres retrouvés, liste "à vérifier"...) a été retiré — ce type d'information
  // interne au processus de génération ne doit pas apparaître dans l'app.
  box.innerHTML=html;
  setPropDir((_PROP_DIR && counts[_PROP_DIR]) ? _PROP_DIR : firstDir);
}
async function _stratLLM(){
  const box=document.getElementById("strat-props"), fb=document.getElementById("strat-comite-fallback");
  const partial=document.getElementById("strat-props-partial-banner");
  // Les cibles ont quitté cet onglet (cf. section ⑦). Sans ce garde-fou, la fonction lèverait
  // une erreur sur un élément absent ET déclencherait un appel LLM pour un contenu que plus
  // personne n'affiche — du quota consommé pour rien.
  if(!box || !fb) return;
  try{
    const r=await fetch(`/api/strategie_llm`);
    const d=await r.json();
    if(d.analyse && d.source && d.source!=="fallback"){
      _renderProps(d.analyse, d.verif);
      if(fb) fb.style.display="none";
      if(partial){
        if(_voitAvertissementsTechniques() && Array.isArray(d.missing_directeurs) && d.missing_directeurs.length){
          partial.style.display="flex";
          partial.textContent=`⚠️ IA indisponible pour ${d.missing_directeurs.join(', ')} — les autres directions affichées ci-dessous sont à jour.`;
        } else {
          partial.style.display="none";
        }
      }
    } else {                              // LLM indisponible → socle déterministe en secours
      if(box) box.style.display="none";
      const bar=document.getElementById('strat-props-bar'); if(bar) bar.innerHTML="";
      if(fb) fb.style.display="";
      if(partial) partial.style.display="none";
    }
  }catch(e){
    if(box) box.style.display="none";
    if(fb) fb.style.display="";
    if(partial) partial.style.display="none";
  }
}

function _stratCharts(d){
  if(!window.Plotly) return;
  (d.projection||[]).forEach((p,i)=>{
    const el=document.getElementById("strat-proj-"+i); if(!el) return;
    const x=["Aujourd'hui","An 1","An 2","An 3"];
    const u=p.unite||"";
    const G="#12895C";                       // scénario central (vert)
    const fmt = v => (u==="%") ? (String(v).replace(".",",")+"%") : (String(v).replace(".",",")+" "+u);
    const lab = arr => arr.map((v,k)=> (k===0||k===arr.length-1) ? fmt(v) : "");
    const pru=p.prudent||p.avec_actions, cen=p.central||p.avec_actions, opt=p.optimiste||p.avec_actions;
    // bornes de la bande (haute/basse), indépendamment du sens
    const up = x.map((_,k)=>Math.max(pru[k],opt[k]));
    const dn = x.map((_,k)=>Math.min(pru[k],opt[k]));
    const all=[...p.actuel,...up,...dn];
    const lo=Math.min(...all), hi=Math.max(...all), pad=(hi-lo)*0.18||1;
    Plotly.newPlot(el,[
      // bande prudent–optimiste (fourchette)
      {x,y:dn,mode:"lines",line:{width:0,color:"rgba(18,137,92,0)"},showlegend:false,hoverinfo:"skip"},
      {x,y:up,mode:"lines",line:{width:0,color:"rgba(18,137,92,0)"},fill:"tonexty",
       fillcolor:"rgba(18,137,92,.13)",name:"Fourchette prudent–optimiste",hoverinfo:"skip"},
      // sans rien faire
      {x,y:p.actuel,name:"Sans rien changer",mode:"lines+markers",
       line:{color:"#94A3B8",width:2,dash:"dot"},marker:{size:5,color:"#94A3B8"},
       hovertemplate:"Sans rien changer<br>%{x} : %{y}"+(u==="%"?"%":" "+u)+"<extra></extra>"},
      // scénario central
      {x,y:cen,name:"Scénario central",mode:"lines+markers+text",
       text:lab(cen),textposition:p.sens==="bas"?"bottom center":"top center",
       textfont:{size:9.5,color:G,family:"Inter,sans-serif"},
       line:{color:G,width:3.5},marker:{size:7,color:G},
       hovertemplate:"Central<br>%{x} : %{y}"+(u==="%"?"%":" "+u)+"<extra></extra>"}
    ],{
      margin:{t:8,b:42,l:42,r:14},showlegend:true,
      legend:{orientation:"h",y:-0.24,x:0,font:{size:9}},
      font:{family:"Inter,sans-serif"},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{tickfont:{size:9.5},gridcolor:"rgba(150,150,150,.10)",fixedrange:true},
      yaxis:{tickfont:{size:9},gridcolor:"rgba(150,150,150,.15)",range:[lo-pad,hi+pad],
             ticksuffix:(u==="%"?"%":""),fixedrange:true,zeroline:false},
      annotations:[{
        x:x[3],y:cen[3],ax:0,ay:p.sens==="bas"?26:-26,
        text:"<b>cible "+fmt(cen[3])+"</b>",font:{size:9.5,color:G},
        showarrow:true,arrowhead:3,arrowcolor:G,arrowwidth:1.3,bgcolor:"rgba(255,255,255,.04)"
      }]
    },{responsive:true,displayModeBar:false,staticPlot:_REAL_TOUCH});
  });
}

function pageStrategie(){
  // Le contenu de l'onglet Stratégie est injecté après coup par _renderStrategie(d), une fois
  // les données chargées ; cette fonction ne rend que le squelette.
  //
  // 181 lignes mortes supprimées le 2026-07-30 : elles suivaient ce `return` derrière un
  // commentaire `eslint-disable-next-line no-unreachable`, donc inaccessibles depuis leur
  // introduction. Elles contenaient encore des jugements concurrentiels écrits en dur que les
  // données contredisent aujourd'hui — « SIB la plus chère sur la tenue de compte » est faux
  // sur les deux segments. Du code mort porteur d'affirmations fausses est un piège pour le
  // prochain lecteur, qui le croira actif. Sauvegarde avant suppression conservée hors dépôt.
  return _stratSkeleton();
}

// simCompute() (24 lignes) supprimé le 2026-07-30 : plus aucun appelant depuis le retrait des
// simulateurs. Il modélisait l'attrition par une formule inventée (churn = élasticité × hausse)
// et repliait sur un tarif SGCI écrit en dur. Le repositionnement tarifaire est désormais traité
// par /api/cb_repricing, à partir des grilles réellement publiées.
function afterStrategie(){
  // _stratLoad() appelle /api/strategie puis rend la page entière : tout ce qui suivait ce
  // `return` — 22 lignes, quatre graphiques de résilience et le simulateur — visait des
  // conteneurs (#st-solv, #st-couv, #st-lev, #st-cp) que la page ne crée plus depuis le retrait
  // des simulateurs. Supprimé le 2026-07-30.
  _stratLoad();
}

/* ════════════ RAPPORTS ══════════════════════════════════════════════ */
const REPORTS=[
  ["exec","📑","Rapport exécutif — Q2 2026","Synthèse marché, position SGCI, KPIs clés et recommandation prioritaire."],
  ["swot","◆","Analyse SWOT — SGCI","Forces, faiblesses, opportunités, menaces + lecture concurrentielle."],
  ["bench","▤","Benchmark tarifaire complet","Comparatif des 7 banques par service, gagnants et perdants."],
  ["reco","✦","Note de recommandations stratégiques","Leviers chiffrés avec justification et impact estimé sur le CA."],
];

function pageRapports(){
  const regl=[
    ["BCEAO · Instruction N°2011-01","Les établissements de crédit <mark>publient</mark> leurs conditions de banque et les affichent à la clientèle."],
    ["Loi Conso CI · Art. 42","Information <mark>claire et lisible</mark> des frais avant la conclusion du contrat."],
    ["BCEAO · Dispositif tarifaire","Dix-neuf services bancaires offerts <mark>gratuitement</mark> aux titulaires de comptes."],
  ];
  return `
  <div class="story">
    <div class="kicker">Décider, puis partager</div>
    <h1>Quatre rapports prêts à <span class="hl">télécharger et présenter</span> en comité.</h1>
    <p>Chaque rapport compile automatiquement les données et l'analyse de l'agence — formaté pour la Direction Générale.</p>
    ${btnPDF("Rapports SGCI")}
  </div>
  <div class="reports" style="margin-bottom:var(--s8)">
    ${REPORTS.map(r=>`<div class="report">
      <div class="cover">${r[1]}</div>
      <div class="meta"><h4>${r[2]}</h4><p>${r[3]}</p>
      <button class="dl" onclick="downloadReport('${r[0]}')">⤓ Télécharger</button></div>
    </div>`).join("")}
  </div>
  <div class="tile tpad" style="animation-delay:.2s">
    <div class="chead"><div class="tt">Conformité réglementaire</div><div class="ts">Transparence tarifaire — obligations BCEAO &amp; Loi Conso</div></div>
    <div style="display:flex;flex-direction:column;gap:12px;margin-top:8px">
      ${regl.map(([s,t])=>`<div style="display:flex;justify-content:space-between;align-items:center;gap:16px;padding:14px 0;border-top:1px solid var(--line)">
        <div><div class="eyebrow" style="color:var(--accent-2);margin-bottom:5px">${s}</div>
        <div style="font:500 13px/1.5 var(--sans)">${t}</div></div>
        <button class="chip" onclick="askIA('Explique : ${s}')">Demander à l'IA →</button>
      </div>`).join("")}
    </div>
  </div>`;
}
function afterRapports(){ window.__redraw=null; }

/* ── Génération de rapports HTML téléchargeables ──────────────────── */
function downloadReport(kind){
  const cheapest = Object.entries(FRAIS).sort((a,b)=>a[1]-b[1])[0];
  const dearest  = Object.entries(FRAIS).sort((a,b)=>b[1]-a[1])[0];
  const maps = {
    exec:  ["Rapport exécutif — SpyBusiness Q2 2026", execReport(cheapest, dearest)],
    swot:  ["Analyse SWOT — SGCI",                    swotReport()],
    bench: ["Benchmark tarifaire — 7 banques CI",      benchReport()],
    reco:  ["Recommandations stratégiques — SGCI",     recoReport()],
  };
  const [title,bodyHtml] = maps[kind];
  const html=`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${title}</title>
  <style>body{font-family:Inter,Arial,sans-serif;max-width:820px;margin:40px auto;padding:0 24px;color:#14161B;line-height:1.6}
  h1{font-size:26px;border-bottom:3px solid #E5142B;padding-bottom:10px}h2{color:#E5142B;margin-top:28px;font-size:17px}
  table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13px}th,td{border:1px solid #ddd;padding:8px 10px;text-align:left}
  th{background:#f5f5f5}.brand{color:#E5142B;font-weight:800;letter-spacing:-.5px}.muted{color:#777;font-size:12px}
  .pos{color:#1B7A33;font-weight:700}.neg{color:#C0202E;font-weight:700}ul{margin:8px 0}li{margin:5px 0}</style></head>
  <body><div class="brand">SpyBusiness · Intelligence bancaire ivoirienne</div>
  <h1>${title}</h1><div class="muted">Généré le ${new Date().toLocaleDateString("fr-FR")} · 7 banques · Côte d'Ivoire</div>
  ${bodyHtml}
  <p class="muted" style="margin-top:40px;border-top:1px solid #eee;padding-top:12px">Document généré automatiquement par SpyBusiness.</p>
  </body></html>`;
  const blob=new Blob([html],{type:"text/html;charset=utf-8"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=title.replace(/[^a-z0-9]+/gi,"_")+".html";
  document.body.appendChild(a); a.click(); a.remove();
}
function execReport(cheapest, dearest){
  return `<h2>1. Position de marché</h2>
  <p>SGCI est <b>n°1 du marché bancaire ivoirien</b> sur le résultat net (<b>${(RN2025.SGCI||101228).toLocaleString("fr-FR")} M FCFA</b>). Elle est également parmi les banques les <b>moins chères</b> sur la tenue de compte (à partir de ${(FRAIS.SGCI||2350).toLocaleString("fr-FR")} F/mois).</p>
  <h2>2. Indicateurs clés</h2>
  <table><tr><th>Indicateur</th><th>SGCI</th><th>Référence marché</th></tr>
  <tr><td>Résultat net</td><td>${(RN2025.SGCI||101228).toLocaleString("fr-FR")} M</td><td>${Object.values(RN2025).map(v=>v/1000).reduce((a,b)=>a+b,0).toFixed(0)} Mds total</td></tr>
  <tr><td>Frais tenue compte</td><td class="pos">à partir de ${(FRAIS.SGCI||2350).toLocaleString("fr-FR")} F</td><td>Moy. ${Math.round(Object.values(FRAIS).reduce((a,b)=>a+b,0)/Object.values(FRAIS).length).toLocaleString("fr-FR")} F</td></tr>
  <tr><td>Banque la moins chère</td><td colspan="2">${cheapest[0]} (${cheapest[1].toLocaleString("fr-FR")} F)</td></tr></table>
  <h2>3. Recommandation prioritaire</h2>
  <p>Hausser les frais de tenue de <b>+100 F/mois</b> (gain estimé <span class="pos">+1,02 Md FCFA/an</span>) pour financer le lancement d'un <b>wallet trésorerie corporate</b>.</p>`;
}
function swotReport(){
  const sw=buildSWOT(); const li=a=>a.map(x=>`<li>${x}</li>`).join("");
  return `<h2>Forces</h2><ul>${li(sw.s)}</ul><h2>Faiblesses</h2><ul>${li(sw.w)}</ul>
  <h2>Opportunités</h2><ul>${li(sw.o)}</ul><h2>Menaces</h2><ul>${li(sw.t)}</ul>
  <h2>Lecture concurrentielle</h2>
  <table><tr><th>Banque</th><th>Stratégie</th><th>Pour SGCI</th></tr>
  ${_competsAll().map(c=>`<tr><td>${c[0]}</td><td>${c[1]}${_positionPrix(c[0])}</td><td>${c[2]}</td></tr>`).join("")}</table>`;
}
function benchReport(){
  const cols=CB_BANKS;   // DYNAMIQUE (source unique)
  if(CB_DATA && CB_DATA.rows){
    const rows=CB_DATA.rows.slice(0,6);
    return `<h2>Comparatif tarifaire (FCFA)</h2>
    <table><tr><th>Service</th>${cols.map(c=>`<th>${c}</th>`).join("")}</tr>
    ${rows.map(row=>{
      const nums=cols.map(b=>(row[b]||{}).num).filter(v=>v!=null&&v>0);
      const mn=Math.min(...nums),mx=Math.max(...nums);
      return `<tr><td>${row.label}</td>${cols.map(b=>{const n=(row[b]||{}).num;const raw=(row[b]||{}).raw||"—";return `<td class="${n===mn?'pos':n===mx?'neg':''}">${n!=null?n.toLocaleString("fr-FR"):raw}</td>`}).join("")}</tr>`;
    }).join("")}</table>
    <p class="muted">Vert = le moins cher · Rouge = le plus cher.</p>`;
  }
  return `<h2>Comparatif tarifaire (FCFA)</h2>
  <table><tr><th>Banque</th><th>Frais tenue / mois</th></tr>
  ${Object.entries(FRAIS).sort((a,b)=>a[1]-b[1]).map(([b,v])=>`<tr><td>${b}</td><td>à partir de ${v.toLocaleString("fr-FR")}</td></tr>`).join("")}</table>`;
}
function recoReport(){
  return `<h2>Leviers stratégiques</h2>
  <table><tr><th>#</th><th>Recommandation</th><th>Justification</th><th>Impact</th><th>Confiance</th></tr>
  ${buildRECOS().map((r,i)=>`<tr><td>${i+1}</td><td>${r[0]}</td><td>${r[1]}</td><td class="pos">${r[2]} ${r[3]}</td><td>${r[5]==='hi'?'Élevée':'Moyenne'}</td></tr>`).join("")}</table>`;
}

/* ════════════ CHAT — RAG réel ═══════════════════════════════════════ */
let CHAT = [];
let CONVOS = [];          // historique persistant des conversations (localStorage)
let CUR_CONV = null;      // id de la conversation active
const SUGG = [
  ["📊","Comparer les frais de tenue de compte en 2026"],
  ["💰","Quelle banque choisir pour mon salaire ?"],
  ["📈","Quel est le résultat net de SGCI en 2025 ?"],
  ["⚖️","Quelles sont les obligations légales des banques CI ?"],
];

function pageChat(){
  return `
  <div class="chat">
    <div class="convs">
      <div class="top">
        <button class="cta" style="width:100%;justify-content:center" onclick="newChat()">＋ Nouvelle conversation</button>
        <div class="search" style="width:auto;margin-top:13px"><span>⌕</span><input id="conv-search" placeholder="Rechercher…" oninput="_renderConvList(this.value)"></div>
      </div>
      <div id="conv-list" style="flex:1;overflow-y:auto;padding-bottom:10px"></div>
    </div>
    <div class="chatmain">
      <div class="msgs" id="msgs"></div>
      <div class="composer">
        <div class="chips">${SUGG.slice(0,4).map(s=>`<button class="chip" onclick="askIA('${s[1].replace(/'/g,"\\'")}')">${s[0]} ${s[1].split(' ').slice(0,3).join(' ')}…</button>`).join("")}</div>
        <div class="row"><textarea id="ci" rows="1" placeholder="Demandez-moi ce que vous voulez savoir…"></textarea><button class="send" onclick="sendChat()">➤</button></div>
      </div>
    </div>
  </div>`;
}

function _mesurerChrome(){
  // On MESURE l'en-tête et le bandeau plutôt que d'additionner des pixels a priori : toute
  // barre ajoutée demain décalerait de nouveau la barre d'écriture hors de l'écran.
  const h = document.querySelector("header.hdr");
  const b = document.querySelector(".ticker");
  const total = (h ? h.getBoundingClientRect().height : 72)
              + (b && b.offsetParent !== null ? b.getBoundingClientRect().height : 0);
  document.documentElement.style.setProperty("--chrome", Math.round(total) + "px");
}
window.addEventListener("resize", _mesurerChrome);

function afterChat(){
  _mesurerChrome();
  _convLoad();
  renderMsgs();
  _renderConvList("");
  const ci = document.getElementById("ci");
  if(ci){
    ci.focus();
    ci.addEventListener("keydown", e=>{
      if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); sendChat(); }
    });
  }
}

function renderMsgs(){
  const box = document.getElementById("msgs");
  if(!box) return;
  if(!CHAT.length){
    box.innerHTML=`<div class="empty">
      <div class="hologram-orb lg"></div>
      <h2 style="margin-top:18px">Bonjour. Je suis l'intelligence bancaire ivoirienne.</h2>
      <p>Posez-moi n'importe quelle question sur les 7 banques de Côte d'Ivoire — tarifs, performance, réglementation.</p>
      <div class="sugg">${SUGG.map(s=>`<button onclick="askIA('${s[1].replace(/'/g,"\\'")}')"><span class="si">${s[0]}</span><span class="st">${s[1]}</span></button>`).join("")}</div>
    </div>`;
    return;
  }
  box.innerHTML = CHAT.map((m,i)=>{
    const enCours = m.role==="a" && /en cours/i.test(m.content||"");
    const ava   = m.role==="u" ? `<div class="ava">DG</div>` : `<div class="ava"><div class="hologram-orb sm${enCours?' speaking':''}"></div></div>`;
    const chart = m.chart ? `<div id="cm-${i}" style="height:240px;margin-top:11px"></div>` : "";
    // Le message de l'IA passe par mdToHtml (qui échappe déjà) ; celui de l'utilisateur
    // partait BRUT dans innerHTML — taper « <img onerror=...> » dans le chat exécutait le
    // code. Vu en corrigeant le rendu Markdown le 2026-07-28. Portée limitée (on ne peut
    // s'attaquer que soi-même), mais c'est une ligne à écrire.
    const body  = m.role==="a" ? mdToHtml(m.content)
                               : String(m.content||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const heure = m.ts ? new Date(m.ts).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '';
    return `<div class="msg ${m.role==="u"?"u":"a"}">${ava}<div><div class="bubble">${body}</div>${chart}${heure?`<div class="msg-time">${heure}</div>`:''}</div></div>`;
  }).join("");
  CHAT.forEach((m,i)=>{ if(m.chart) autoChart(`cm-${i}`, m.chart); });
  box.scrollTop = box.scrollHeight;
}

/* ════════════════════════════════════════════════════════════════════════
   mdToHtml — rendu Markdown des messages du chat
   ────────────────────────────────────────────────────────────────────────
   BUG SIGNALÉ le 2026-07-28 par le directeur (« LES DIESES LA TCHAI ») : les
   réponses de l'IA s'affichaient avec leurs « ### » en clair — « ### Explication »,
   « ### Chiffres » — au lieu de titres de section. L'ancienne version ne gérait que
   DEUX choses : le gras **…** et les tableaux. Tout le reste tombait tel quel dans un
   <p> : titres ###, listes à puces « - », listes numérotées, italique, séparateurs.
   Le LLM produit pourtant du Markdown standard (on le lui demande explicitement, cf.
   server.py « format markdown structuré ») — il était donc rendu à moitié, ce qui
   donnait des blocs de texte lourds parsemés de dièses.

   Deuxième défaut, invisible mais plus grave : AUCUN échappement HTML. Le contenu part
   directement dans innerHTML (renderMsgs). Une réponse contenant du texte issu des
   documents indexés pouvait donc injecter du balisage arbitraire dans la page. On
   échappe désormais tout, puis on ré-autorise une LISTE BLANCHE de balises inline
   (<b>, <i>, <br>…) car plusieurs prompts serveur demandent explicitement au LLM
   d'écrire « <b> pour les chiffres » — les casser aurait dégradé l'affichage.
   ════════════════════════════════════════════════════════════════════════ */
function mdToHtml(t){
  if(!t) return "";
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  // Échappement global, puis réhabilitation des seules balises inline sûres.
  let src = esc(t).replace(/&lt;(\/?)(b|strong|i|em|u|br)\s*\/?&gt;/gi,
                           (m, slash, tag) => `<${slash}${tag.toLowerCase()}>`);

  // Marques inline : gras, italique, code. L'italique exige un * non collé à un autre *
  // pour ne pas manger la moitié d'un **gras**.
  const inl = s => s
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<i>$2</i>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  const lignes = src.split("\n");
  let out = "", mode = null;          // null | "ul" | "ol" | "table"
  const fermer = () => {
    if(mode === "ul")    out += "</ul>";
    else if(mode === "ol") out += "</ol>";
    else if(mode === "table") out += "</tbody></table>";
    mode = null;
  };

  for(const brute of lignes){
    const ln = brute.trim();
    if(!ln){ fermer(); continue; }

    // ── Tableau : | a | b | … (la ligne de séparation |---|---| est ignorée) ──
    if(ln.startsWith("|")){
      if(/^\|[\s:|-]+\|?$/.test(ln)) continue;
      const cells = ln.replace(/^\|/,"").replace(/\|$/,"").split("|").map(c => inl(c.trim()));
      if(mode !== "table"){
        fermer();
        out += "<table><thead><tr>" + cells.map(c => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
        mode = "table";
      } else {
        out += "<tr>" + cells.map(c => `<td>${c}</td>`).join("") + "</tr>";
      }
      continue;
    }
    if(mode === "table") fermer();

    // ── Titres : #, ##, ### … (tous rendus en h4 — un message de chat n'a pas
    //    besoin d'une échelle de titres, il a besoin d'étiquettes de section lisibles) ──
    const mTitre = ln.match(/^(#{1,6})\s+(.+)$/);
    if(mTitre){ fermer(); out += `<h4>${inl(mTitre[2].replace(/[:\s]+$/,""))}</h4>`; continue; }

    // ── Séparateur horizontal ──
    if(/^(-{3,}|_{3,}|\*{3,})$/.test(ln)){ fermer(); out += "<hr>"; continue; }

    // ── Liste numérotée : « 1. » / « 1) » ──
    const mNum = ln.match(/^(\d{1,2})[.)]\s+(.+)$/);
    if(mNum){
      if(mode !== "ol"){ fermer(); out += "<ol>"; mode = "ol"; }
      out += `<li>${inl(mNum[2])}</li>`;
      continue;
    }

    // ── Liste à puces : «- », «* », «• » ──
    const mPuce = ln.match(/^[-*•·]\s+(.+)$/);
    if(mPuce){
      if(mode !== "ul"){ fermer(); out += "<ul>"; mode = "ul"; }
      out += `<li>${inl(mPuce[1])}</li>`;
      continue;
    }

    // ── Paragraphe ordinaire ──
    fermer();
    out += `<p>${inl(ln)}</p>`;
  }
  fermer();
  return out;
}

/* RAG réel — appel API /chat */
async function askRAG(q){
  try{
    // conv_id (2026-07-22) : isole la mémoire de conversation côté serveur — sans ça, toutes
    // les conversations partageaient le même historique global (jamais réinitialisé).
    const res = await fetch("/api/chat", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({question:q, conv_id: CUR_CONV}),
    });
    // UN REFUS DE DROITS N'EST PAS UNE PANNE (2026-08-10, signalé par le directeur).
    // Un compte sans accès à l'assistant recevait « Erreur de connexion au RAG » — un message
    // qui décrit une avarie technique là où le serveur a simplement, et correctement, refusé.
    // L'utilisateur croyait l'application cassée ; l'administrateur aussi.
    if(res.status === 403){
      return "**Vous n'avez pas accès à ce service.**\n\nL'assistant conversationnel n'est pas "
           + "activé sur votre compte. Adressez-vous à l'administrateur si vous en avez besoin.";
    }
    if(res.status === 401){
      return "**Votre session a expiré.** Reconnectez-vous pour continuer.";
    }
    const data = await res.json();
    return data.reponse || "Erreur de connexion au RAG.";
  } catch(e){
    return "Impossible de joindre le serveur. Vérifiez que server.py tourne.";
  }
}

// Collecte les données KPI actuelles pour enrichir le contexte de l'IA
function getKPIContext(){
  return {
    pnb:         PNB_DATA         || {},
    rn:          Object.fromEntries(Object.entries(KPI_DATA?.rn_data||{}).map(([b,v])=>[b, typeof v==='object'?v.montant:v])),
    marge:       KPI_DATA?.marge_nette_data  || {},
    cout_risque: KPI_DATA?.cout_r_pnb_data   || {},
    coeff:       KPI_DATA?.coeff_expl_data    || {},
    roe:         KPI_DATA?.roe_data           || {},
    growths:     KPI_DATA?.growths_data       || {},
  };
}

async function askApprofondir(q, sectionFacts){
  try{
    const res = await fetch("/api/approfondir", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      // section_facts (2026-07-22) : les VRAIS chiffres déjà calculés de LA section cliquée
      // (ex. Projection prudent/central/optimiste) — sans ça, le LLM n'avait que les KPIs
      // génériques et inventait sa propre projection quand on lui demandait de la détailler.
      // conv_id (2026-07-23) : verse cet échange dans la mémoire serveur du chat, pour
      // qu'une question de suivi tapée juste après ("Quelles sont les hypothèses ?") ne
      // soit plus rejetée à tort "hors périmètre" faute de contexte connu côté RAG.
      body: JSON.stringify({ question:q, kpis: getKPIContext(), section_facts: sectionFacts || null, conv_id: CUR_CONV }),
    });
    const data = await res.json();
    return data.reponse || "Aucune réponse reçue.";
  } catch(e){
    return "⚠️ Analyse indisponible — service temporairement inaccessible.";
  }
}

async function askIA(q, sectionId){
  go("chat");
  const sectionFacts = sectionId ? (window._STRAT_FACTS||{})[sectionId] : null;
  setTimeout(async ()=>{
    pushChat("u", q);
    _convPersist();
    pushChat("a", "⏳ Analyse en cours avec les données réelles du marché…");
    // Utilise le nouvel endpoint contextualisé qui inclut les KPIs live + les faits de section
    const r = await askApprofondir(q, sectionFacts);
    CHAT[CHAT.length-1] = { role:"a", content:r, ts:Date.now() };
    renderMsgs();
    _convPersist();
  }, 120);
}

async function sendChat(){
  const ci = document.getElementById("ci");
  const v  = ci.value.trim();
  if(!v) return;
  ci.value = "";
  pushChat("u", v);
  _convPersist();
  pushChat("a", "…analyse en cours…"); // placeholder
  const r = await askRAG(v);
  CHAT[CHAT.length-1] = { role:"a", content:r };
  renderMsgs();
  _convPersist();
}

function pushChat(role, content, chart){ CHAT.push({role,content,chart,ts:Date.now()}); renderMsgs(); }

/* ════════════════════════════════════════════════════════════════════════
   HISTORIQUE DYNAMIQUE DES CONVERSATIONS — persistant via localStorage.
   Chaque conversation = {id, title, msgs:[{role,content}], ts}. Le panneau de
   gauche liste les VRAIES conversations de l'utilisateur (groupées par date),
   avec reprise au clic, recherche et suppression. Remplace la liste statique.
   ════════════════════════════════════════════════════════════════════════ */
const _CONV_KEY = "sb-convos-v1";
function _convLoad(){
  try{ CONVOS = JSON.parse(localStorage.getItem(_CONV_KEY) || "[]"); }
  catch(e){ CONVOS = []; }
  if(!Array.isArray(CONVOS)) CONVOS = [];
  _convSyncFromServer();   // fusionne avec l'historique côté serveur (voir plus bas)
}
function _convStore(){
  try{ localStorage.setItem(_CONV_KEY, JSON.stringify(CONVOS.slice(0,100))); }catch(e){}
  // Copie aussi côté serveur : localStorage est isolé PAR ORIGINE (localhost / 127.0.0.1 /
  // IP LAN = 3 stockages différents pour le même serveur) → l'historique semble
  // « disparaître » selon l'URL utilisée pour accéder à l'app. Le serveur, lui, est unique
  // quelle que soit l'URL d'accès. Fire-and-forget : jamais bloquant pour l'utilisateur.
  fetch("/api/conv_history", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(CONVOS.slice(0,100)),
  }).catch(()=>{});
}
// Fusionne l'historique local avec celui du serveur (le plus récent par conversation gagne),
// pour retrouver ses conversations même en changeant d'URL d'accès (localhost/IP LAN/...).
async function _convSyncFromServer(){
  try{
    const r = await fetch("/api/conv_history");
    const remote = await r.json();
    if(!Array.isArray(remote) || !remote.length) return;
    const byId = {};
    CONVOS.forEach(c=>{ byId[c.id]=c; });
    remote.forEach(c=>{
      const cur = byId[c.id];
      if(!cur || (c.ts||0) > (cur.ts||0)) byId[c.id] = c;
    });
    CONVOS = Object.values(byId);
    try{ localStorage.setItem(_CONV_KEY, JSON.stringify(CONVOS.slice(0,100))); }catch(e){}
    _renderConvList((document.getElementById("conv-search")||{}).value || "");
  }catch(e){ /* serveur indisponible → on garde le localStorage local tel quel */ }
}
function _convEsc(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function _convTitle(msgs){
  const u = (msgs||[]).find(m=>m.role==="u");
  let t = (u && u.content || "").replace(/\s+/g," ").trim();
  if(!t) return "Nouvelle conversation";
  return t.length>46 ? t.slice(0,46)+"…" : t;
}
function _convIcon(msgs){
  const u = ((msgs||[]).find(m=>m.role==="u")||{}).content || "";
  const s = u.toLowerCase();
  if(/frais|tarif|co[uû]t|prix|commission|gratuit/.test(s)) return "📊";
  if(/r[ée]sultat|pnb|roe|marge|b[ée]n[ée]fice|performance|bilan|d[ée]p[oô]t/.test(s)) return "📈";
  if(/r[ée]glement|l[ée]gal|obligation|plafond|\bloi\b|bceao|uemoa|norme/.test(s)) return "⚖️";
  if(/choisir|quelle banque|recommand|\bpme\b|salaire|meilleur/.test(s)) return "🔀";
  return "💬";
}
function _dateGroup(ts){
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86400000;
  if(ts >= startToday) return "Aujourd'hui";
  if(ts >= startToday - day) return "Hier";
  if(ts >= startToday - 6*day) return "Cette semaine";
  return "Plus ancien";
}
function _relTime(ts){
  const diff = (Date.now() - ts)/1000, d = new Date(ts);
  if(diff < 60) return "à l'instant";
  if(diff < 3600) return "il y a " + Math.floor(diff/60) + " min";
  if(_dateGroup(ts) === "Aujourd'hui")
    return String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0");
  return d.toLocaleDateString("fr-FR",{day:"2-digit",month:"short"});
}
function _convCur(){ return CONVOS.find(c=>c.id===CUR_CONV); }

/* Sauvegarde l'état courant de CHAT dans la conversation active (la crée au
   premier message), la remonte en tête, persiste et rafraîchit la liste. */
function _convPersist(){
  if(!CHAT.length) return;
  let c = _convCur();
  if(!c){
    c = { id:"c"+Date.now().toString(36)+Math.random().toString(36).slice(2,6), msgs:[], ts:Date.now() };
    CONVOS.unshift(c); CUR_CONV = c.id;
  }
  c.msgs  = CHAT.map(m=>({role:m.role, content:m.content}));
  c.title = _convTitle(c.msgs);
  c.ts    = Date.now();
  CONVOS  = [c, ...CONVOS.filter(x=>x.id!==c.id)];
  _convStore();
  _renderConvList((document.getElementById("conv-search")||{}).value || "");
}

function _renderConvList(filter){
  const box = document.getElementById("conv-list");
  if(!box) return;
  const f = (filter||"").toLowerCase().trim();
  let list = CONVOS.slice().sort((a,b)=>b.ts-a.ts);
  if(f) list = list.filter(c =>
    (c.title||"").toLowerCase().includes(f) ||
    (c.msgs||[]).some(m=>(m.content||"").toLowerCase().includes(f)));
  if(!list.length){
    box.innerHTML = `<div style="padding:26px 18px;text-align:center;color:var(--muted);font:500 12px var(--sans);line-height:1.6">${
      f ? "Aucune conversation trouvée." : "Aucune conversation pour l'instant.<br>Posez une question pour démarrer."}</div>`;
    return;
  }
  const groups = {};
  list.forEach(c=>{ const g=_dateGroup(c.ts); (groups[g]=groups[g]||[]).push(c); });
  let html = "";
  ["Aujourd'hui","Hier","Cette semaine","Plus ancien"].forEach(g=>{
    if(!groups[g]) return;
    html += `<div class="conv-grp">${g}</div>`;
    groups[g].forEach(c=>{
      const nmsg = (c.msgs||[]).filter(m=>m.role==="u").length;
      html += `<div class="conv ${c.id===CUR_CONV?'active':''}" onclick="loadConv('${c.id}')">
        <div class="ct"><span>${_convIcon(c.msgs)}</span><span class="conv-t">${_convEsc(c.title)}</span>
          <button class="conv-del" title="Supprimer cette conversation" onclick="deleteConv('${c.id}',event)">✕</button></div>
        <div class="cm">${_relTime(c.ts)} · ${nmsg} question${nmsg>1?'s':''}</div>
      </div>`;
    });
  });
  box.innerHTML = html;
}

function loadConv(id){
  const c = CONVOS.find(x=>x.id===id);
  if(!c) return;
  CUR_CONV = id;
  CHAT = (c.msgs||[]).map(m=>({role:m.role, content:m.content}));
  renderMsgs();
  _renderConvList((document.getElementById("conv-search")||{}).value || "");
  const ci = document.getElementById("ci"); if(ci) ci.focus();
}

function deleteConv(id, ev){
  if(ev) ev.stopPropagation();
  CONVOS = CONVOS.filter(c=>c.id!==id);
  _convStore();
  if(CUR_CONV===id){ CUR_CONV=null; CHAT=[]; renderMsgs(); }
  _renderConvList((document.getElementById("conv-search")||{}).value || "");
}

function newChat(){
  CUR_CONV = null; CHAT = []; renderMsgs();
  _renderConvList((document.getElementById("conv-search")||{}).value || "");
  const ci = document.getElementById("ci"); if(ci) ci.focus();
}

/* ─── router ──────────────────────────────────────────────────────── */
/* ════════════ CONDITIONS BANCAIRES ════════════════════════════════ */
let CB_SEG="Particuliers", CB_YEAR="2026", CB_SEM="S1", CB_CONCURRENT="BICICI", _CB_SIM_LIB="";
// Token de rendu CB : incrémenté à chaque (re)chargement. Tout callback async vérifie
// _cbAlive(tok) avant d'écrire dans le DOM → empêche les écritures périmées et les
// erreurs en cascade lors d'un changement rapide de filtre (Particuliers↔Entreprises).
let _cbToken=0;
function _cbAlive(tok){return tok===_cbToken;}
function _resetCBState(){
  /* L'ÉCRAN DE CHARGEMENT DOIT REPARAÎTRE AU CHANGEMENT DE FILTRE (2026-08-11).
     Le compteur n'était remis à neuf que dans go(), or changer de segment, d'année ou de
     semestre ne passe pas toujours par là — setCBSem() recharge la vue directement. Le taux
     restait donc à 100 % de la navigation précédente et l'écran ne se montrait plus : la page
     semblait se figer sans rien annoncer, alors même que le calcul pouvait durer des minutes
     sur une combinaison non encore mise en cache. Ce reset est appelé par les trois filtres,
     c'est le seul endroit qui les couvre tous. */
  try{ chargementNouvelleVue(); }catch(e){}
  _cbToken++;_CB_EXHAUS_CACHE={};_CB_SUBSECTION_CACHE={};_conclusionFired=false;window._CB_Q3_DATA=null;window._CB_Q5_SUMMARY={};
}
function setCBSeg(s){CB_SEG=s;_resetCBState();go("cb");}
// Semestres réellement disponibles pour une année (2026-07-30). Le sélecteur proposait S1 et S2
// en dur : « 2026 S2 » n'existe pas en base, et le sélectionner produisait un écran incohérent —
// agrégats par section renvoyés via l'imputation S2→S1, comparatif détaillé vide. On ne propose
// plus que ce qui existe ; l'ajout de données fera apparaître le bouton tout seul.
function _cbSemsDispo(annee){
  const p = (typeof CB_PERIODES !== "undefined" ? CB_PERIODES : null) || {};
  const l = p[String(annee)];
  return (Array.isArray(l) && l.length) ? l : ["S1", "S2"];   // filet avant chargement
}
function setCBYear(y){
  CB_YEAR=y;
  // Si le semestre courant n'existe pas pour cette année, basculer sur le premier disponible
  // au lieu de laisser l'écran sur une période sans données.
  const dispo=_cbSemsDispo(y);
  if(!dispo.includes(CB_SEM)) CB_SEM=dispo[0];
  _resetCBState();go("cb");
}
function setCBSem(s){
  if(!_cbSemsDispo(CB_YEAR).includes(s)) return;   // période absente : ne rien faire
  CB_SEM=s;_resetCBState();reloadCB();
}
function setCBConcurrent(b){CB_CONCURRENT=b;go("cb");}

/* ── Structuration des données exhaustives ─────────────────────── */
function _buildByLibelle(rows){
  /* byLib[cat][lib][banque] = {montant, val, type, gratuit}
     cat = SECTION CANONIQUE BCEAO (section_roman·section_titre), pas le
     texte brut de `contexte` : ce dernier varie d'une banque à l'autre
     pour un même service (ex. SGCI range ses attestations sous "Conditions
     générales des comptes" quand BACI/BICICI/BNI ont un en-tête littéral
     "Attestations bancaires") et fabriquait de fausses "absences" — un
     service réellement proposé par SGCI, mais classé sous un intitulé
     différent, ressortait comme "ABSENT du catalogue SGCI". La section
     canonique (déjà validée et utilisée par /api/cb_par_section) regroupe
     les services équivalents indépendamment de l'intitulé de la brochure
     d'origine. */
  const byLib={};
  rows.forEach(r=>{
    const cat=r.section_roman?`${r.section_roman} · ${r.section_titre}`:(r.contexte||"—").split("|")[0].trim();
    const lib=r.libelle;
    if(!byLib[cat])byLib[cat]={};
    if(!byLib[cat][lib])byLib[cat][lib]={};
    byLib[cat][lib][r.banque]={
      montant:r.montant,
      val:r.est_gratuit?"GRATUIT":r.type_valeur==="SUR_DEMANDE"?"Sur dem.":
          r.valeur_propre||(r.montant!=null?r.montant.toLocaleString("fr-FR")+(r.unite?" "+r.unite:" F"):"—"),
      type:r.type_valeur, gratuit:r.est_gratuit
    };
  });
  _mergeLibellesPucesParasites(byLib);
  return byLib;
}

/* Fusionne les libellés jumeaux qui ne diffèrent que par une puce de mise en
   forme collée en tête — artefact d'extraction PDF répandu (ex. SGCI publie
   son tarif "Tenue de compte" sous le libellé brut "•Frais de tenue de compte"
   = 2350F, tandis que BACI écrit proprement "Frais de tenue de compte" =
   5000F : MÊME service, deux graphies, donc deux groupes qui ne se
   rencontrent jamais — la table affichait alors BACI=5000F et SGCI="—",
   donnant la fausse impression que SGCI ne propose pas ce tarif, alors qu'il
   est en réalité moins cher).
   On NE fusionne QUE si les deux libellés ne partagent AUCUNE banque : sinon
   ce sont deux tarifs réellement distincts que la puce permet justement de
   distinguer (ex. SGCI a "Commission de change" à 0,1% ET "• Commission de
   change" GRATUIT — fusionner écraserait l'un des deux). Règle strictement
   conservatrice, sans perte de donnée : zéro risque de collision. */
const _RE_PUCE_TETE=/^[•▪●·*\-–—]+\s*/;
function _mergeLibellesPucesParasites(byLib){
  Object.values(byLib).forEach(libs=>{
    Object.keys(libs).forEach(lib=>{
      if(!libs[lib])return;
      const propre=lib.replace(_RE_PUCE_TETE,"").trim();
      if(!propre||propre===lib)return;
      const jumeau=Object.keys(libs).find(k=>k!==lib&&k.toLowerCase()===propre.toLowerCase());
      if(!jumeau||!libs[jumeau])return;
      const banquesPuce=Object.keys(libs[lib]),banquesPropre=Object.keys(libs[jumeau]);
      if(banquesPuce.some(b=>banquesPropre.includes(b)))return;
      Object.assign(libs[jumeau],libs[lib]);
      delete libs[lib];
    });
  });
}

/* Regroupement ITEMISÉ section → sous-section → libellé → banque, pour le
   face-à-face produit par produit demandé par la DG ("on doit voir TOUS
   les types de comptes avec leurs tarifs d'ouverture, SGCI vs un
   concurrent à côté" — pas une médiane qui efface les produits).
   Même squelette que _buildByLibelle (groupement par section canonique +
   nettoyage des puces parasites), un niveau de plus : la sous-section,
   déjà classée côté serveur (cb_subsections.classify_subsection — même
   mécanisme déterministe que /api/cb_par_sous_section) et exposée ligne
   par ligne via `sous_section_libelle` dans /api/cb_exhaustif.
   _mergeLibellesPucesParasites s'applique ici sans modification : pour
   chaque catégorie `out[cat]` = {sous_section: {libellé: {banque: ...}}}
   a exactement la forme {clé: {libellé: {banque: ...}}} qu'elle attend,
   que la clé soit un libellé (cas _buildByLibelle) ou une sous-section
   (cas présent) ne change rien à la logique de fusion. */
function _buildBySousSection(rows){
  const out={};
  rows.forEach(r=>{
    const cat=r.section_roman?`${r.section_roman} · ${r.section_titre}`:(r.contexte||"—").split("|")[0].trim();
    const sub=r.sous_section_libelle||"Autres";
    const lib=r.libelle;
    if(!out[cat])out[cat]={};
    if(!out[cat][sub])out[cat][sub]={};
    if(!out[cat][sub][lib])out[cat][sub][lib]={};
    // Extract immediate parent context (level just above the product libellé)
    const _ctxSegs=(r.contexte||"").split("|").map(s=>s.trim()).filter(s=>s.length>1);
    let _par="";
    for(let _i=_ctxSegs.length-1;_i>=0;_i--){
      const _s=_ctxSegs[_i];
      // Skip: Roman-numeral headers, too long, same as libellé,
      //        truncated words (first "word" ≤ 2 chars), date artifacts (4-digit year)
      if(_s.length<=50&&!/^[IVX]+[\s\.]/.test(_s)&&_s!==r.libelle
         &&!/^\w{1,2}\s/.test(_s)&&!/\b\d{4}\b/.test(_s)){_par=_s;break;}
    }
    out[cat][sub][lib][r.banque]={
      montant:r.montant,
      val:r.est_gratuit?"GRATUIT":r.type_valeur==="SUR_DEMANDE"?"Sur dem.":
          r.valeur_propre||(r.montant!=null?r.montant.toLocaleString("fr-FR")+(r.unite?" "+r.unite:" F"):"—"),
      type:r.type_valeur, gratuit:r.est_gratuit, par:_par
    };
  });
  Object.values(out).forEach(_mergeLibellesPucesParasites);
  return out;
}

/* ── Règle UNIQUE de comparabilité d'un montant CB ───────────────────
   Un `montant` n'est comparable entre banques QUE s'il représente un
   vrai prix fixe en F CFA. Trois cas le rendent NON comparable bruts :
     - GRATUIT       → 0 logique, mais ce n'est pas "le moins cher d'un
                        prix" : c'est une absence de prix
     - TAUX_%        → ex. "0,2% mini 10 000" est stocké en montant=0.2
                        (la partie numérique du taux). Le comparer tel
                        quel à un montant F CFA (16 500) produit un
                        écart absurde ("+8 249 900%") — types différents,
                        unités différentes, rien à voir.
     - SUR_DEMANDE   → négocié au cas par cas, non chiffré publiquement
   Toute fonction qui calcule un écart de prix DOIT passer par cette
   fonction unique — c'est la garantie que ce type d'erreur ne peut
   plus se reproduire ailleurs dans le code. */
function _cbComparable(d){
  return d&&d.montant!=null&&!d.gratuit&&d.type!=="TAUX_%"&&d.type!=="SUR_DEMANDE"?d.montant:null;
}

/* ── Comparatif hiérarchique Section → Sous-section → Synthèse ──────────
   Refonte demandée par la DG : comparer SGCI au niveau des 9 grandes
   sections BCEAO mélange des sous-services hétérogènes dans une même
   médiane (ex. la section I confond "Ouverture de compte" — souvent
   gratuite — et "Clôture de compte" — souvent payante autour de 25-30k F
   — ce qui produit un agrégat qui ne représente NI l'une NI l'autre,
   exactement le type de problème structurel que le bug "% vs F CFA" avait
   déjà révélé ailleurs : un agrégat qui efface une distinction réellement
   présente dans la donnée source). Les documents sources, eux, séparent
   clairement ces sous-familles (1.1 / 1.2…) : c'est donc à CE niveau qu'il
   faut comparer.

   La sous-section est déterminée PAR CONTENU (regex déterministe sur texte
   normalisé, cf. dash_app/cb_subsections.py — AUCUN appel LLM, mêmes
   garanties que la classification de section déjà en place), un niveau
   sous `cb_par_section`. Données depuis /api/cb_par_sous_section. */

/* Détail ITEMISÉ d'une sous-famille — DEUX CATALOGUES INDÉPENDANTS, un par
   banque, chacun listant SES PROPRES produits avec SES PROPRES tarifs réels,
   exactement le pattern .bank-col / .line de la maquette de référence fournie
   par la DG (benchmark_cb_sgci_bicici.html). PAS un alignement ligne-à-ligne
   par libellé : "SGCI N'A PAS LES MÊMES SERVICES QUE LES AUTRES" (citation DG)
   — forcer un appariement produit par produit fabriquerait des correspondances
   qui n'existent pas dans les catalogues réels (ex. SGCI "Visa Infinite"
   n'a pas d'équivalent BICICI ; "Carte Salaire" est une exclusivité BICICI).
   Chaque catalogue est listé tel quel, dans l'ordre des documents sources —
   au lecteur de juger lui-même la comparabilité, exactement le choix éditorial
   de la maquette de référence (où "Clôture" et "Clôture (DAT : pénalité)"
   restent deux lignes distinctes plutôt que d'être artificiellement fusionnées).

   La colonne de droite suit le filtre concurrent existant (CB_CONCURRENT,
   conservé tel quel — "TU AS MIS UN FILTRE […] C'ÉTAIT BON"). L'option
   "Moyenne" qu'elle ajoute resynthétise, pour chaque libellé publié par au
   moins un concurrent, la MÉDIANE des montants F CFA réellement comparables
   parmi les 6 (jamais % mêlé à un montant — _cbComparable, même garde-fou
   que partout ailleurs ; médiane et non moyenne arithmétique, même convention
   que montant_median — cf. sa justification dans cb_par_section : la médiane
   résiste aux montants exceptionnels qui écrasent une moyenne). "(n/6)" donne
   toujours la mesure de robustesse du chiffre affiché — jamais une illusion
   de précision sur un échantillon faible. */
function _cleanLib(s){
  if(!s)return"";
  return s
    .replace(/(\w)-\s+(\w)/g,"$1$2")                                          // "ouvertu- res"   → "ouvertures"
    .replace(/([a-zàâçéèêëîïôùûü])([A-ZÀÂÇÉÈÊËÎÏÔÙÛÜ][a-z])/g,"$1 $2")    // "compteSalariés" → "compte Salariés"
    .replace(/([A-Z])([A-Z][a-z]{2,})/g,"$1 $2");                             // "FLEXICARDPrix"  → "FLEXICARD Prix"
}
function _truncLib(s,max){
  const c=_cleanLib(s);
  return c.length>max?`<span title="${c.replace(/"/g,'&quot;')}">${c.slice(0,max)}&hellip;</span>`:c;
}

function _subSectionDetail(subLabel,subItems,totalLignes){
  const CONCS=CB_BANK_ORDER.filter(b=>b!=="SGCI");
  const isMoyenne=CB_CONCURRENT==="Moyenne";
  const fmt=v=>Math.round(v).toLocaleString("fr-FR")+" F";
  const rightLabel=isMoyenne?"Moyenne marché":CB_CONCURRENT;
  const median=arr=>{const s=[...arr].sort((a,b)=>a-b),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;};
  const valColor=d=>d.gratuit?"#22C55E":d.type==="SUR_DEMANDE"||d.val==="—"?"var(--faint)":"var(--ink)";

  const _normPar=s=>(s||"").toLowerCase().replace(/[^a-z0-9]/g,"").substring(0,12);
  const _showPar=(par,subLbl)=>par&&_normPar(par)!==_normPar(subLbl)&&par.length<=50;

  const sgciItems=Object.keys(subItems).filter(lib=>subItems[lib]["SGCI"]).map(lib=>{
    const d=subItems[lib]["SGCI"];return{lib,val:d.val,color:valColor(d),par:d.par||""};
  }).sort((a,b)=>a.par.localeCompare(b.par)||a.lib.localeCompare(b.lib));

  let rightItems;
  if(isMoyenne){
    rightItems=Object.keys(subItems).map(lib=>{
      const entries=CONCS.map(b=>subItems[lib][b]).filter(Boolean);
      if(!entries.length)return null;
      const vals=entries.map(_cbComparable).filter(v=>v!=null&&v>0);
      const par=(entries.find(e=>e.par)||{par:""}).par||"";
      if(vals.length)return{lib,val:`${fmt(median(vals))} <span style="opacity:.6;font-weight:500">(méd. ${vals.length}/6)</span>`,color:"var(--ink)",par};
      const g=entries.filter(e=>e.gratuit).length;
      if(g)return{lib,val:`Gratuit <span style="opacity:.6;font-weight:500">(${g}/6)</span>`,color:"#22C55E",par};
      return{lib,val:`${entries[0].val} <span style="opacity:.6;font-weight:500">(${entries.length}/6)</span>`,color:"var(--faint)",par};
    }).filter(Boolean).sort((a,b)=>a.par.localeCompare(b.par)||a.lib.localeCompare(b.lib));
  }else{
    rightItems=Object.keys(subItems).filter(lib=>subItems[lib][CB_CONCURRENT]).map(lib=>{
      const d=subItems[lib][CB_CONCURRENT];return{lib,val:d.val,color:valColor(d),par:d.par||""};
    }).sort((a,b)=>a.par.localeCompare(b.par)||a.lib.localeCompare(b.lib));
  }

  if(!sgciItems.length&&!rightItems.length)return"";

  /* Tableau 4 colonnes : [Produit SGCI | Prix SGCI] | [Produit concurrent | Prix concurrent].
     Les lignes sont alignées par indice (zip) : la ligne i montre sgciItems[i] à gauche
     et rightItems[i] à droite. Items triés par (parent contexte, libellé) pour regrouper
     les produits d'une même famille. */
  const nRows=Math.max(sgciItems.length,rightItems.length);
  const tdName=(it,border,prevPar)=>{
    if(!it)return`<td style="padding:5px 8px 5px 0${border?';border-left:1.5px solid var(--line)':''}"></td>`;
    const raw=_cleanLib(it.lib||"");
    const showP=_showPar(it.par,subLabel)&&it.par!==prevPar;
    const parLine=showP?`<div style="font:600 9px/1.3 var(--mono);color:var(--faint);letter-spacing:.04em;text-transform:uppercase;margin-bottom:2px">${_cleanLib(it.par)}</div>`:"";
    return`<td style="font:500 11px/1.5 var(--sans);color:var(--muted);padding:5px ${border?'10px':'8px'} 5px ${border?'10px':'0'};word-break:break-word${border?';border-left:1.5px solid var(--line)':''}">${parLine}${raw}</td>`;
  };
  const tdVal=(it)=>{
    if(!it)return`<td style="padding:5px 10px 5px 4px"></td>`;
    return`<td style="font:600 11px var(--mono);color:${it.color};word-break:break-word;padding:5px 10px 5px 4px;text-align:right">${it.val}</td>`;
  };
  let prevSPar="",prevRPar="";
  const bodyRows=Array.from({length:nRows},(_,i)=>{
    const s=sgciItems[i]||null,r=rightItems[i]||null;
    const sCol=tdName(s,false,prevSPar);
    const rCol=tdName(r,true,prevRPar);
    if(s)prevSPar=s.par;
    if(r)prevRPar=r.par;
    return`<tr style="border-top:1px solid var(--line)">${sCol}${tdVal(s)}${rCol}${tdVal(r)}</tr>`;
  }).join("");

  const empty=`<tr><td colspan="4" style="font:500 11px var(--sans);color:var(--faint);padding:6px 0">Aucun tarif publié sur cette sous-famille.</td></tr>`;

  return`<div style="padding:10px 0 4px;border-top:1px solid var(--line)">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px">
      <div style="font:700 12.5px/1.3 var(--sans);color:var(--ink)">${subLabel}</div>
      <div style="font:500 9px var(--mono);color:var(--faint);white-space:nowrap">${sgciItems.length} chez SGCI · ${rightItems.length} chez ${rightLabel}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup>
        <col style="width:38%"><col style="width:12%"><col style="width:38%"><col style="width:12%">
      </colgroup>
      <thead>
        <tr>
          <th colspan="2" style="font:700 9px var(--mono);color:var(--accent-2);letter-spacing:.08em;text-transform:uppercase;padding:0 0 5px;text-align:left">★ SGCI</th>
          <th colspan="2" style="font:700 9px var(--mono);color:var(--faint);letter-spacing:.08em;text-transform:uppercase;padding:0 0 5px 10px;text-align:left;border-left:1.5px solid var(--line)">${rightLabel}</th>
        </tr>
      </thead>
      <tbody>${bodyRows||empty}</tbody>
    </table>
  </div>`;
}

/* Synthèse PAR SECTION : agrège ses sous-familles pour répondre, une seule
   fois et sans répétition, aux deux questions posées par la DG — "SGCI
   plus cher ou moins cher ?" et "qu'est-ce que les concurrents ont que
   SGCI n'a pas ?" — avec les MÊMES garde-fous que l'ancienne vue par
   section (échantillon minimal CB_SECTION_MIN_ECHANTILLON, ratio plausible
   CB_SECTION_RATIO_MAX) pour ne jamais fabriquer un écart qui ne reflète
   qu'une composition de catalogue hétérogène. */
function _buildSectionSynthesis(sec,bySub){
  const CONCS=CB_BANK_ORDER.filter(b=>b!=="SGCI");
  const isMoy=CB_CONCURRENT==="Moyenne";
  let cheaperSGCI=0,cheaperConc=0,comparable=0;
  const gaps=[];    // sous-familles entièrement absentes chez SGCI
  const exclusifs=[];// produits du concurrent absents chez SGCI (par libellé exact)
  (sec.sous_sections||[]).forEach(sub=>{
    const sgci=sub.banques["SGCI"];
    const sgciM=(sgci&&sgci.n_montants>=CB_SECTION_MIN_ECHANTILLON)?sgci.montant_median:null;
    const concs=CONCS.map(b=>({b,v:sub.banques[b]?.montant_median,n:sub.banques[b]?.n_montants||0}))
      .filter(x=>x.v!=null&&x.v>0&&x.n>=CB_SECTION_MIN_ECHANTILLON);
    if(sgciM!=null&&concs.length){
      const minC=Math.min(...concs.map(x=>x.v));
      const ratio=Math.max(sgciM,minC)/Math.min(sgciM,minC);
      if(ratio<=CB_SECTION_RATIO_MAX){
        comparable++;
        if(sgciM<minC)cheaperSGCI++;
        else if(sgciM>minC)cheaperConc++;
      }
    }
    // Gap niveau sous-famille : SGCI a 0 produit, le concurrent en a
    // Ancien bug : exigeait 2+ concurrents → jamais déclenché en mode 1 concurrent
    if(!sgci||!sgci.n_lignes){
      if(isMoy){
        const present=CONCS.filter(b=>(sub.banques[b]?.n_lignes||0)>=1);
        if(present.length>=2)gaps.push({libelle:sub.libelle,banques:present});
      }else if((sub.banques[CB_CONCURRENT]?.n_lignes||0)>=1){
        gaps.push({libelle:sub.libelle,banques:[CB_CONCURRENT]});
      }
    }
    // Gap niveau produit : le concurrent a des produits que SGCI ne publie pas
    if(!isMoy&&bySub){
      const subItems=bySub[sub.libelle]||{};
      const sgciLibs=new Set(Object.keys(subItems).filter(lib=>subItems[lib]["SGCI"]));
      const concOnly=Object.keys(subItems).filter(lib=>subItems[lib][CB_CONCURRENT]&&!sgciLibs.has(lib));
      if(concOnly.length>0)exclusifs.push({subsection:sub.libelle,products:concOnly});
    }
  });
  return{cheaperSGCI,cheaperConc,comparable,gaps,exclusifs};
}

function _sectionSynthesisText(sec,syn){
  const{cheaperSGCI,cheaperConc,comparable,gaps,exclusifs}=syn;
  const desc=CB_SECTION_DESC[sec.roman]||"";
  const descLow=desc?desc.charAt(0).toLowerCase()+desc.slice(1):"";
  let verdict;
  if(comparable===0){
    verdict=`impossible de comparer objectivement les prix sur cette famille — la plupart des tarifs sont <b>gratuits</b> des deux côtés, ou dépendent des <b>conditions du client</b> (taux, packages, négociations). Il n'y a pas assez de montants fixes publiés pour dire qui est moins cher.`;
  }else if(cheaperSGCI>cheaperConc){
    verdict=`<b style="color:#22C55E">SGCI ressort globalement moins chère</b> sur cette famille : sur les <b>${comparable} sous-famille${comparable>1?"s":""} comparables</b> (échantillon suffisant des deux côtés, écart plausible), SGCI est moins chère sur <b style="color:#22C55E">${cheaperSGCI}</b> et plus chère sur <b style="color:#FF4D4D">${cheaperConc}</b>.`;
  }else if(cheaperConc>cheaperSGCI){
    verdict=`<b style="color:#FF4D4D">SGCI ressort globalement plus chère</b> sur cette famille : sur les <b>${comparable} sous-famille${comparable>1?"s":""} comparables</b> (échantillon suffisant des deux côtés, écart plausible), SGCI est plus chère sur <b style="color:#FF4D4D">${cheaperConc}</b> et moins chère sur <b style="color:#22C55E">${cheaperSGCI}</b> — l'écart se loge précisément dans ces sous-familles, pas dans la famille entière.`;
  }else{
    verdict=`<b>parité</b> sur cette famille : sur les <b>${comparable} sous-famille${comparable>1?"s":""} comparables</b>, SGCI est aussi souvent moins chère (${cheaperSGCI}) que plus chère (${cheaperConc}) — aucun camp ne domine.`;
  }
  const hasGaps=(gaps&&gaps.length>0);
  const hasExcl=(exclusifs&&exclusifs.length>0);
  let gapTxt;
  if(!hasGaps&&!hasExcl){
    gapTxt=`Aucune. SGCI propose les mêmes services que ses concurrents sur cette famille. Les différences éventuelles sont des <b>écarts de prix</b>, pas des <b>services manquants</b>.`;
  }else{
    const parts=[];
    if(hasGaps){
      const list=gaps.slice(0,3).map(g=>`<b>${g.libelle}</b>`).join(" · ");
      parts.push(`<b style="color:#FFB020">${gaps.length} sous-famille${gaps.length>1?"s":""} entièrement absente${gaps.length>1?"s":""} chez SGCI</b> : ${list}${gaps.length>3?` … +${gaps.length-3} autres`:""}.`);
    }
    if(hasExcl){
      const exList=exclusifs.slice(0,3).map(e=>{
        const prods=e.products.slice(0,2).map(p=>`"${_cleanLib(p)}"`).join(", ");
        const more=e.products.length>2?` +${e.products.length-2} autres`:"";
        return`<b>${e.subsection}</b> (${prods}${more})`;
      }).join(" · ");
      parts.push(`${CB_CONCURRENT} propose des produits sans équivalent publié chez SGCI : ${exList}${exclusifs.length>3?` … +${exclusifs.length-3} autres sous-familles`:""}.`);
    }
    gapTxt=parts.join(" — ")+` <span style="color:var(--muted)">À qualifier auprès de la Direction Commerciale : choix d'offre assumé, ou simple absence de la grille publique ?</span>`;
  }
  return`<b>${sec.roman} · ${sec.titre}</b>${descLow?` — cette famille couvre ${descLow}`:""}<br><br>`
    +`<b>SGCI plus chère ou moins chère ?</b> ${verdict}<br><br>`
    +`<b>Qu'est-ce que les concurrents ont que SGCI n'a pas ?</b> ${gapTxt}`;
}

function _renderHierarchicalComparison(secSubData,bySousSection){
  if(!secSubData||!secSubData.length)return`<div style="padding:30px;text-align:center;color:var(--muted)">Aucune donnée disponible pour cette période.</div>`;
  return`<div style="display:flex;flex-direction:column;gap:12px">
  ${secSubData.map((sec,i)=>{
    const cat=`${sec.roman} · ${sec.titre}`;
    const bySub=(bySousSection&&bySousSection[cat])||{};
    const syn=_buildSectionSynthesis(sec,bySub);
    const totalLignes=(sec.sous_sections||[]).reduce((a,sub)=>a+CB_BANK_ORDER.reduce((x,b)=>x+(sub.banques[b]?.n_lignes||0),0),0);
    return`<div style="border:1px solid var(--line);border-radius:12px;overflow:hidden">
      <div onclick="var b=this.nextElementSibling;var open=b.style.display!=='none';b.style.display=open?'none':'block';this.querySelector('.chev').style.transform=open?'rotate(0deg)':'rotate(180deg)'"
           style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;background:var(--bg-raise);cursor:pointer">
        <div style="display:flex;align-items:baseline;gap:9px;min-width:0">
          <span style="font:800 15px var(--mono);color:var(--accent-2);flex-shrink:0">${sec.roman}</span>
          <span style="font:700 13px var(--sans);color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${sec.titre}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
          <span style="font:600 9px var(--mono);color:var(--faint);letter-spacing:.05em;white-space:nowrap">${totalLignes} TARIFS · ${sec.sous_sections.length} SOUS-FAMILLES</span>
          <span class="chev" style="display:inline-block;color:var(--faint);transition:transform .2s;transform:rotate(${i<2?"180":"0"}deg)">▾</span>
        </div>
      </div>
      <div style="display:${i<2?"block":"none"};padding:6px 16px 16px">
        <div style="font:500 11.5px/1.5 var(--sans);color:var(--muted);padding:8px 0 2px">${CB_SECTION_DESC[sec.roman]||""}</div>
        ${sec.sous_sections.map(sub=>{
          const tl=CB_BANK_ORDER.reduce((x,b)=>x+(sub.banques[b]?.n_lignes||0),0);
          return _subSectionDetail(sub.libelle,bySub[sub.libelle]||{},tl);
        }).join("")}
        ${_cbAnalyse(_sectionSynthesisText(sec,syn))}
      </div>
    </div>`;
  }).join("")}
  </div>
  <div style="margin-top:12px;font:500 10.5px/1.6 var(--sans);color:var(--faint)">Lecture : chaque sous-famille reprend la <b>numérotation réelle des documents sources</b> (ex. section I "Conditions générales du compte" → "Ouverture de compte" / "Clôture de compte" séparées, plutôt qu'une médiane unique qui les confondrait) · à droite, deux <b>catalogues indépendants</b> — <b>★ SGCI</b> et le concurrent choisi dans le filtre ci-dessus (ou la <b>médiane du marché</b> sur les 6 concurrents avec l'option "Moyenne") — chacun listant SES propres produits et SES propres tarifs réels, dans l'ordre des documents sources : SGCI ne propose pas toujours les mêmes services que ses concurrents (ex. "Visa Infinite" sans équivalent ailleurs, "Carte Salaire" exclusive à un concurrent), un alignement ligne à ligne forcé fabriquerait des correspondances qui n'existent pas · vert = gratuit, gris = sur conditions/négocié, blanc = montant fixe publié.</div>`;
}

/* ── Simulateur Pro — plafond = min concurrent ──────────────────── */
let _cbSimServices=[];
window._cbSimCurrentOld=0; window._cbSimCurrentCeil=0;

function _renderSimulatorPro(byLib){
  const CONCS=CB_BANKS.filter(b=>b!=="SGCI");   // concurrents DYNAMIQUES
  _cbSimServices=[];
  Object.entries(byLib).forEach(([cat,libs])=>{
    Object.entries(libs).forEach(([lib,prices])=>{
      const sgciV=_cbComparable(prices["SGCI"]);
      if(sgciV==null||sgciV<=0)return;
      const concV=CONCS.map(b=>_cbComparable(prices[b])).filter(v=>v!=null&&v>0);
      if(!concV.length)return;
      const minConc=Math.min(...concV);
      _cbSimServices.push({
        cat,lib,sgciPrice:sgciV,minConc,
        allPrices:[{b:"SGCI",v:sgciV},...CONCS.map(b=>({b,v:_cbComparable(prices[b])})).filter(x=>x.v!=null)].sort((a,b2)=>a.v-b2.v)
      });
    });
  });
  _cbSimServices.sort((a,b)=>a.cat.localeCompare(b.cat)||a.lib.localeCompare(b.lib));
  if(!_cbSimServices.length)return`<div style="padding:20px;color:var(--muted)">Données insuffisantes pour le simulateur.</div>`;

  const sel=_cbSimServices.find(s=>s.lib===_CB_SIM_LIB)||_cbSimServices[0];
  if(!_CB_SIM_LIB)_CB_SIM_LIB=sel.lib;
  window._cbSimCurrentOld=sel.sgciPrice;
  window._cbSimCurrentCeil=sel.minConc;

  const opts=_cbSimServices.map(s=>`<option value="${s.lib}"${s.lib===sel.lib?" selected":""}>[${s.cat.slice(0,28)}…] ${s.lib}</option>`).join("");
  const maxDelta=Math.max(0,sel.minConc-sel.sgciPrice);
  const upsidePct=sel.sgciPrice>0?Math.round(maxDelta/sel.sgciPrice*100):0;
  const cl0=CB_SEG==="Particuliers"?850:25;
  const maxFee=Math.max(sel.minConc,Math.round(sel.sgciPrice*2));
  const step=Math.max(50,Math.round(maxFee/80));

  const barHtml=sel.allPrices.map(x=>{
    const w=Math.round(x.v/maxFee*100);
    const isSGCI=x.b==="SGCI";
    const col=isSGCI?"#FF3B4E":x.v===sel.allPrices[0].v?"#22C55E":"var(--accent)";
    return`<div style="display:flex;align-items:center;gap:10px;margin:4px 0">
      <span style="font:${isSGCI?800:600} 10px var(--mono);width:68px;color:${col};flex-shrink:0">${x.b}</span>
      <div style="flex:1;background:var(--bg-raise);border-radius:4px;height:22px;position:relative;overflow:hidden">
        <div style="width:${w}%;background:${col};height:100%;opacity:.8"></div>
        <span style="position:absolute;right:8px;top:50%;transform:translateY(-50%);font:700 11px var(--mono);color:var(--ink)">${x.v.toLocaleString("fr-FR")} F</span>
      </div>
      ${x.v===sel.allPrices[0].v?`<span style="font:700 8px var(--mono);color:#22C55E;flex-shrink:0">MIN</span>`:""}
    </div>`;
  }).join("");

  return`<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
    <div>
      <div style="font:700 11px var(--mono);color:var(--muted);letter-spacing:.06em;margin-bottom:10px">TARIFS RÉELS DU MARCHÉ</div>
      <select id="sim-lib-sel" onchange="_onSimLibChange(this.value)" style="width:100%;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink);font:500 11.5px var(--sans);margin-bottom:14px">${opts}</select>
      ${barHtml}
      <div style="margin-top:14px;padding:12px;background:color-mix(in srgb,#22C55E 8%,transparent);border-radius:10px;border-left:3px solid #22C55E">
        <div style="font:700 10px var(--mono);color:#22C55E;margin-bottom:4px">PLAFOND STRATÉGIQUE — SGCI NE DOIT JAMAIS DÉPASSER</div>
        <div style="font:800 28px/1 var(--display);color:#22C55E">${sel.minConc.toLocaleString("fr-FR")} F</div>
        <div style="font:500 11px var(--sans);color:var(--muted);margin-top:4px">Prix du concurrent le moins cher · dépasser ce seuil = perte de compétitivité</div>
        ${upsidePct>0?`<div style="margin-top:6px;font:600 12px var(--sans);color:#22C55E">↑ Potentiel : SGCI peut augmenter jusqu'à +${upsidePct}% (+${maxDelta.toLocaleString("fr-FR")} F) sans perdre le leadership</div>`:`<div style="margin-top:6px;font:600 12px var(--sans);color:#FFB020">⚠ SGCI (${sel.sgciPrice.toLocaleString("fr-FR")} F) est déjà au-dessus du concurrent le moins cher (${sel.minConc.toLocaleString("fr-FR")} F)</div>`}
      </div>
    </div>
    <div>
      <div style="font:700 11px var(--mono);color:var(--muted);letter-spacing:.06em;margin-bottom:14px">PARAMÈTRES DU SCÉNARIO</div>
      <div class="field"><label>Nouveau tarif SGCI · <b><span id="sim-new-price">${sel.sgciPrice.toLocaleString("fr-FR")}</span> F</b>
        <span style="font:500 10px var(--sans);color:var(--faint)"> (actuel : ${sel.sgciPrice.toLocaleString("fr-FR")} · plafond : ${sel.minConc.toLocaleString("fr-FR")} F)</span>
      </label>
      <input type="range" id="sim-fee-range" min="${Math.round(sel.sgciPrice*0.4)}" max="${maxFee}" step="${step}" value="${sel.sgciPrice}" oninput="cbSimProCompute()">
      <div id="sim-ceiling-warn" style="display:${sel.sgciPrice>sel.minConc?"":"none"};margin-top:4px;font:600 11px var(--sans);color:#FF4D4D">⚠ Tarif actuel > plafond concurrent</div>
      </div>
      <div class="field"><label>Comptes actifs · <b><span id="sim-cl">${cl0}</span> k</b></label>
      <input type="range" id="sim-cl-range" min="${CB_SEG==="Particuliers"?100:5}" max="${CB_SEG==="Particuliers"?2000:200}" step="${CB_SEG==="Particuliers"?50:5}" value="${cl0}" oninput="cbSimProCompute()"></div>
      <div class="field"><label>Élasticité · % comptes perdus par tranche +100 F · <b><span id="sim-el">0,8</span> %</b></label>
      <input type="range" id="sim-el-range" min="0" max="5" step="0.1" value="0.8" oninput="cbSimProCompute()"></div>
      <div class="out" style="margin-top:16px">
        <div class="lab">Impact annuel sur le CA · service sélectionné</div>
        <div class="big pos" id="sim-pro-big">—</div>
        <div class="verdict" id="sim-pro-v">Ajustez le tarif ci-dessus</div>
        <div class="sub" id="sim-pro-s" style="margin-top:6px">—</div>
        <div id="sim-pro-warn" style="margin-top:8px;display:none;padding:8px 12px;background:color-mix(in srgb,#FF4D4D 10%,transparent);border-radius:8px;color:#FF4D4D;font:600 12px var(--sans)">⚠ Au-dessus du plafond concurrent — perte de compétitivité prix</div>
      </div>
    </div>
  </div>`;
}

function _onSimLibChange(lib){
  _CB_SIM_LIB=lib;
  const key=`${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
  const rows=_CB_EXHAUS_CACHE[key];if(!rows)return;
  const box=document.getElementById("cb-sim-box");if(!box)return;
  box.innerHTML=_renderSimulatorPro(_buildByLibelle(rows));
  cbSimProCompute();
}

function cbSimProCompute(){
  const fR=document.getElementById("sim-fee-range");if(!fR)return;
  const cR=document.getElementById("sim-cl-range");
  const eR=document.getElementById("sim-el-range");
  const newFee=+fR.value;
  const cl=(+(cR?.value||850))*1000;
  const el=+(eR?.value||0.8);
  const oldFee=window._cbSimCurrentOld||newFee;
  const ceil=window._cbSimCurrentCeil||newFee;

  const np=document.getElementById("sim-new-price");if(np)np.textContent=newFee.toLocaleString("fr-FR");
  const clEl=document.getElementById("sim-cl");if(clEl)clEl.textContent=(cl/1000).toFixed(0);
  const elEl=document.getElementById("sim-el");if(elEl)elEl.textContent=el.toFixed(1).replace(".",",");
  const warnC=document.getElementById("sim-ceiling-warn");if(warnC)warnC.style.display=newFee>ceil?"":"none";
  const warnP=document.getElementById("sim-pro-warn");if(warnP)warnP.style.display=newFee>ceil?"":"none";

  const delta=newFee-oldFee;
  const bigEl=document.getElementById("sim-pro-big");
  const vEl=document.getElementById("sim-pro-v");
  const sEl=document.getElementById("sim-pro-s");
  if(delta===0){
    if(bigEl){bigEl.textContent="0 F";bigEl.className="big";}
    if(vEl)vEl.textContent="Aucune modification tarifaire.";
    if(sEl)sEl.textContent="—";
    return;
  }
  const churn=delta>0?(el/100)*(Math.abs(delta)/100):0;
  const lost=Math.round(cl*churn);
  const remain=cl-lost;
  const impact=(remain*newFee-cl*oldFee)*12;
  const fmt=v=>(v>=0?"+":"−")+Math.abs(Math.round(v/1e6)).toLocaleString("fr-FR")+" M FCFA";
  if(bigEl){bigEl.textContent=fmt(impact);bigEl.className="big "+(impact>=0?"pos":"neg");}
  if(vEl)vEl.textContent=impact>=0?"✓ Scénario favorable — gain net positif":"✗ Scénario risqué — départs effacent le gain";
  if(sEl)sEl.innerHTML=`Comptes perdus estimés : <b>${lost.toLocaleString("fr-FR")}</b> · Restants : <b>${remain.toLocaleString("fr-FR")}</b> · Impact : <b>${fmt(impact)}</b>`;
}
let _CB_EXHAUS_CACHE={};
let _CB_SUBSECTION_CACHE={};

function _axeHead(n,q,sub){
  return`<div id="cb-axe-${n}" style="grid-column:1/-1;display:flex;align-items:baseline;gap:12px;margin:8px 0 2px;scroll-margin-top:130px">
    <span style="font:800 11px/1 var(--mono);color:var(--accent);letter-spacing:.14em">AXE ${n}</span>
    <span style="font:700 14px/1 var(--display);color:var(--ink)">${q}</span>
    <span style="font:500 11.5px/1 var(--sans);color:var(--muted);margin-left:4px">${sub}</span></div>`;
}

/* ══════════════════════════════════════════════════════════════════
   TABLEAU DE BORD STRATÉGIQUE CB — 6 questions marketing
   ══════════════════════════════════════════════════════════════════ */

// ════════════════════════════════════════════════════════════════════════════
// DASHBOARD CB — 6 AXES STRATÉGIQUES (données SQL pures, sans LLM)
// Les templates sont générés 100% depuis cb_tarifs via /api/cb_strat_data.
// L'IA (Groq) n'intervient QUE si l'utilisateur clique "Approfondir IA".
// ════════════════════════════════════════════════════════════════════════════

const _CB_DATA_CACHE={};
const _CB_IA_CACHE={};

const _AX_COLS=["#38D1F0","#22C55E","#FFB020","#A78BFA","#FF4D4D","#FB923C"];
const _AX_TITLES=["Évolution 2024 → 2026","Innovations SGCI","Exclusifs SGCI","Facteur différenciant","Gaps à combler","Classement du marché"];
const _AX_DESC=[
  "Ce qui a changé globalement chez SGCI et ses 6 concurrents sur 3 ans",
  "Nouveaux produits et services apparus chez SGCI depuis 2024",
  "Ce que SGCI propose que ses 6 concurrents n'ont pas",
  "SGCI a-t-il un avantage concurrentiel fort et défendable ?",
  "Services présents chez les concurrents mais absents de l'offre SGCI",
  "Qui est le plus cher, le moins cher — et de combien ?",
];

// ═══════════════════════════════════════════════════════════════════════════
// CB DASHBOARD — Rebuild complet · Design system natif · Plotly · Zero LLM
// ═══════════════════════════════════════════════════════════════════════════

let _cbPid=0;
const _cid=()=>'cbch-'+(++_cbPid);

// Inline colored tag
function _tag(txt,col){
  const c={g:'var(--green)',r:'var(--red)',a:'var(--amber)',b:'var(--cyan)',p:'#A78BFA'}[col]||col;
  const bg={g:'rgba(34,197,94,.13)',r:'rgba(255,77,77,.13)',a:'rgba(255,176,32,.13)',b:'rgba(56,209,240,.13)',p:'rgba(167,139,250,.13)'}[col]||'var(--bg-raise)';
  return`<span style="display:inline-block;font-size:12px;padding:3px 10px;border-radius:7px;font-weight:700;font-family:var(--mono);background:${bg};color:${c};border:1px solid ${c}30;white-space:nowrap;line-height:1.7">${txt}</span>`;
}

// Insight / callout box
function _ins(txt,col){
  const c=col||'var(--cyan)';
  return`<div style="background:color-mix(in srgb,${c} 7%,transparent);border-left:3px solid ${c};border-radius:0 10px 10px 0;padding:13px 17px;margin-top:18px;font:500 13px/1.7 var(--sans);color:var(--muted)">${txt}</div>`;
}

// Compact row — list item
function _ri(lbl,badge,sub){
  return`<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);gap:10px">
    <span style="font:500 13.5px var(--sans);color:var(--muted);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${lbl}</span>
    <span style="flex-shrink:0">${badge}</span>
    ${sub?`<span style="font:600 11px var(--mono);color:var(--faint);flex-shrink:0">${sub}</span>`:''}
  </div>`;
}

// KPI metric tile
function _kpiCb(val,lbl,col){
  const c=col||'var(--ink)';
  return`<div style="background:var(--bg-raise);border:1px solid var(--line);border-radius:var(--r-card);padding:16px 18px;text-align:center">
    <div style="font:800 32px/1 var(--display);color:${c};letter-spacing:-.03em">${val}</div>
    <div style="font:500 12.5px var(--sans);color:var(--muted);margin-top:7px;line-height:1.4">${lbl}</div>
  </div>`;
}

// CSS horizontal bar
function _cbar(pct,col,h){
  const hpx=h||7;
  return`<div style="height:${hpx}px;background:var(--bg-raise);border-radius:${hpx}px;overflow:hidden;margin-top:5px">
    <div style="height:100%;width:${Math.min(pct,100)}%;background:${col};border-radius:${hpx}px;transition:width 1.2s ease"></div>
  </div>`;
}

// Axis header for Qn
function _qHead(n,col,q,sub){
  const c=col||'var(--cyan)';
  return`<div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:20px">
    <div style="width:40px;height:40px;min-width:40px;border-radius:50%;background:color-mix(in srgb,${c} 15%,transparent);border:1px solid color-mix(in srgb,${c} 30%,transparent);display:flex;align-items:center;justify-content:center;font:700 14px var(--mono);color:${c};flex-shrink:0">${n}</div>
    <div>
      <div style="font:700 22px/1.25 var(--sans);color:var(--ink);letter-spacing:-.01em">${q}</div>
      <div style="font:500 13px var(--sans);color:var(--faint);margin-top:5px">${sub}</div>
    </div>
  </div>`;
}

// ── MD helpers (used by IA analysis) ───────────────────────────────────────
function _inlineMd(t){
  return(t||"")
    .replace(/\*\*(.+?)\*\*/g,'<strong style="color:var(--ink)">$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`(.+?)`/g,'<code style="font:500 11px var(--mono);background:rgba(255,255,255,.08);padding:1px 5px;border-radius:3px">$1</code>');
}
function _mdToHtml(md){
  if(!md)return"";
  const lines=md.split("\n"),out=[];
  let tRows=[],inT=false;
  const _flushT=()=>{
    if(!tRows.length){inT=false;return;}
    const[hdr,...body]=tRows;
    const ths=hdr.map(h=>`<th style="text-align:left;padding:5px 8px;border-bottom:2px solid var(--line);font:700 9px var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);white-space:nowrap">${_inlineMd(h)}</th>`).join("");
    const tds=body.map(r=>`<tr style="border-bottom:1px solid var(--line)">${r.map(c=>`<td style="padding:4px 8px;font:500 11.5px var(--sans);color:var(--muted)">${_inlineMd(c)}</td>`).join("")}</tr>`).join("");
    out.push(`<div style="overflow-x:auto;margin:10px 0"><table style="width:100%;border-collapse:collapse"><thead><tr>${ths}</tr></thead><tbody>${tds}</tbody></table></div>`);
    tRows=[];inT=false;
  };
  for(const raw of lines){
    const line=raw.trimEnd();
    if(/^\s*\|/.test(line)&&line.includes("|")){
      const cells=line.replace(/^\s*\|/,"").replace(/\|\s*$/,"").split("|").map(c=>c.trim());
      if(cells.every(c=>/^[-:]+$/.test(c)))continue;
      inT=true;tRows.push(cells);continue;
    }
    if(inT)_flushT();
    const tr=line.trim();
    if(!tr){out.push(`<div style="height:6px"></div>`);continue;}
    if(tr.startsWith("### "))
      out.push(`<div style="font:700 10px var(--mono);color:var(--accent-2);text-transform:uppercase;letter-spacing:.08em;margin:14px 0 5px">${_inlineMd(tr.slice(4))}</div>`);
    else if(tr.startsWith("## "))
      out.push(`<div style="font:700 12.5px var(--sans);color:var(--ink);border-bottom:1px solid var(--line);padding-bottom:4px;margin:16px 0 7px">${_inlineMd(tr.slice(3))}</div>`);
    else if(tr.startsWith("# "))
      out.push(`<div style="font:700 13px var(--sans);color:var(--ink);margin:16px 0 8px">${_inlineMd(tr.slice(2))}</div>`);
    else if(/^[-•·*] /.test(tr))
      out.push(`<div style="display:flex;gap:7px;margin:3px 0;align-items:baseline"><span style="color:var(--accent-2);flex-shrink:0;font-size:9px">▸</span><span style="font:500 12px/1.55 var(--sans);color:var(--muted)">${_inlineMd(tr.replace(/^[-•·*] /,""))}</span></div>`);
    else if(/^\d+\. /.test(tr))
      out.push(`<div style="display:flex;gap:7px;margin:3px 0;align-items:baseline"><span style="color:var(--accent-2);flex-shrink:0;font:700 10px var(--mono)">${(tr.match(/^(\d+)\./)||["",""])[1]}.</span><span style="font:500 12px/1.55 var(--sans);color:var(--muted)">${_inlineMd(tr.replace(/^\d+\. /,""))}</span></div>`);
    else
      out.push(`<div style="font:500 12px/1.65 var(--sans);color:var(--muted);margin:3px 0">${_inlineMd(tr)}</div>`);
  }
  if(inT)_flushT();
  return out.join("");
}

// ── v3 light-theme helpers (CB dashboard) ────────────────────────────────
function _v3tag(t,c){return`<span class="tag ${c}">${t}</span>`;}
function _v3ins(txt,typ){return`<div class="insight${typ?' '+typ:''}">${txt}</div>`;}
function _v3sec(n,col,title,sub){
  return`<div class="sec-hdr">
    <div class="sec-badge" style="background:${col};box-shadow:0 0 12px ${col}44"></div>
    <div>
      <div style="font:700 10px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:${col};margin-bottom:6px">${title.split('—')[0].trim()}</div>
      <div class="sec-title">${title}</div>
      <div class="sec-sub">${sub}</div>
    </div>
  </div>`;
}
function _v3bar(lbl,pct,col,val,extra){return`<div class="bar-row"><span class="bar-lbl">${lbl}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.min(Math.max(pct,2),100)}%;background:${col}"></div></div><span class="bar-val">${val}${extra?' '+extra:''}</span></div>`;}
// Symbole de devise depuis la colonne `unite` de cb_tarifs. Jamais d'invention :
// si l'unité est inconnue on retombe sur FCFA (devise dominante des CB ivoiriennes).
const _curSym=u=>{u=(u||'').toString().toUpperCase();return u==='%'?'%':(u==='EUR'||u==='€')?'€':(u==='USD'||u==='$')?'$':'F';};
const _v3f=(v,u)=>{const s=_curSym(u);if(s==='%')return (Math.round((v||0)*100)/100).toString().replace('.',',')+' %';return v>=1e6?(v/1e6).toFixed(1).replace('.',',')+' M '+s:Math.round(v||0).toLocaleString('fr-FR')+' '+s;};

// ── Q1 : Évolution globale du catalogue 2024 → 2026 ────────────────────────
let _q1ConcBank='BICICI';

async function _loadQ1Conc(banque){
  _q1ConcBank=banque;
  document.querySelectorAll('.q1cb-btn').forEach(btn=>{
    const active=btn.dataset.b===banque;
    btn.style.background=active?'color-mix(in srgb,var(--accent) 15%,var(--bg-raise))':'var(--bg-raise)';
    btn.style.color=active?'var(--ink)':'var(--muted)';
    btn.style.borderColor=active?'var(--accent)':'var(--line)';
    btn.style.fontWeight=active?'700':'500';
  });
  const box=document.getElementById('q1-conc-list');
  const ttl=document.getElementById('q1-conc-title');
  if(!box)return;
  if(ttl)ttl.textContent=(banque==='SGCI'?'Nouveaux services SGCI (vs 2024)':'Nouveaux services — '+banque);
  box.innerHTML='<div style="padding:8px 0;color:var(--muted);font:500 12px var(--sans)">Chargement…</div>';
  try{
    let app;
    if(banque==='SGCI'){
      app=window._q1SgciApp||[];
    }else{
    const qs=`q=1&annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}&banque=${encodeURIComponent(banque)}`;
    const resp=await fetch(`/api/cb_strat_data?${qs}`);
    const d=await resp.json();
    app=d.evolution?.apparus||[];
    }
    if(!app.length){
      box.innerHTML=`<p style="font:400 12px var(--sans);color:var(--faint);padding:8px 0">Aucun nouveau service pour ${banque}.</p>`;
      return;
    }
    // Regroupement par AXE BCEAO (même taxonomie que Q3/Q5 : Packages, Cartes,
    // Épargne, Crédits, Assurances, Digital, Marchés, Autres) — fourni par le serveur.
    const sm={};
    app.forEach(r=>{
      const sk=r.axe_id!=null?(''+r.axe_id):'8';
      if(!sm[sk])sm[sk]={n:0,nGrat:0,rows:[],label:r.axe_label||'Autres Services Distinctifs',icon:r.axe_icon||'🔧',color:r.axe_color||'#6B7280'};
      sm[sk].n++;
      if(r.est_gratuit)sm[sk].nGrat++;
      sm[sk].rows.push(r);
    });
    // Pertinence : gratuit (signal concurrentiel fort) > tarif précis > taux > sans tarif.
    // On NE masque RIEN : les services sans tarif sont juste classés après (avec leur contexte).
    const _innovScore=r=>{
      if(r.est_gratuit||r.type_valeur==='GRATUIT')return 3;
      if(r.montant!=null&&r.montant>0&&r.type_valeur!=='TAUX_%')return 2;
      if(r.type_valeur==='TAUX_%'&&r.montant!=null)return 1.5;
      return 0;
    };
    Object.values(sm).forEach(v=>v.rows.sort((a,b)=>(_innovScore(b)-_innovScore(a))||((b.montant||0)-(a.montant||0))));
    const sa=Object.entries(sm).sort((a,b)=>b[1].n-a[1].n);
    if(!sa.length){
      box.innerHTML=`<p style="font:400 12px var(--sans);color:var(--faint);padding:8px 0"><b>${app.length}</b> nouvelles entrées pour ${banque} (sections non classifiées).</p>`;
      return;
    }
    const bnk=banque.replace(/\W/g,'');
    const period=`${CB_YEAR} ${CB_SEM}`;
    window._q1Toggle=(uid,btn)=>{
      const el=document.getElementById(uid);if(!el)return;
      const open=el.style.display!=='none';
      el.style.display=open?'none':'block';
      btn.textContent=open?'+':'−';
    };
    const fmtT=(r)=>{
      if(r.est_gratuit||r.type_valeur==='GRATUIT')return _v3tag('Gratuit','tg');
      if(r.type_valeur==='SUR_DEMANDE')return`<span style="font:500 10px var(--sans);color:var(--muted)">Sur demande</span>`;
      // valeur_propre prioritaire si elle contient un qualificateur de sens ("/", "par ", "du ")
      // Ex: "1% du montant de la transaction" ≠ "1%" — le qualificateur change la signification
      const vp=(r.valeur_propre||'').trim();
      const vpOk=vp&&!vp.includes('|')&&!vp.includes('##')&&!/\d\.\d\.\d/.test(vp)&&vp.length<=80;
      if(vpOk&&(vp.includes('/')||/\bpar\b/i.test(vp)||/\bdu\b/i.test(vp)||/\bde la\b/i.test(vp)))
        return`<span style="font:600 11px var(--mono);color:var(--muted)">${vp}</span>`;
      if(r.type_valeur==='TAUX_%'&&r.montant!=null){
        if(+r.montant>100)return`<span style="font:500 10px var(--sans);color:var(--muted)">Sur demande</span>`; // taux > 100% impossible = brute mixte
        return`<span style="font:600 11px var(--mono);color:var(--muted)">${_v3f(r.montant,'%')}</span>`;
      }
      // Montant numérique : on affiche la devise réelle (unite), jamais un % inventé.
      if(r.montant!=null&&r.montant>0)return _v3f(r.montant,r.unite);
      if(vpOk&&isNaN(vp))return`<span style="font:600 11px var(--mono);color:var(--muted)">${vp}</span>`;
      return'—';
    };
    // Analyse relative : compare chaque banque aux autres du même marché, pas contre seuils fixes
    const _analyseNew=(bnq,items,sections)=>{
      const tot=items.length;
      const nGr=items.filter(r=>r.est_gratuit).length;
      const isSGCI=bnq==='SGCI';
      const top3=sections.slice(0,3).map(([s,v])=>`<b>${snC[s]||'Section '+s}</b> (+${v.n})`);
      const _fact=t=>`<div style="font:400 12px var(--sans);color:var(--muted);line-height:1.6;padding:5px 0 4px;border-bottom:1px solid var(--line)">${t}</div>`;
      const _warn=t=>`<div style="font:600 12px var(--sans);color:#b91c1c;line-height:1.6;padding:5px 0 4px;border-bottom:1px solid var(--line)">⚠ ${t}</div>`;
      const _alert=t=>`<div style="font:600 12px var(--sans);color:#92400e;line-height:1.6;padding:5px 0 4px;border-bottom:1px solid var(--line)">⚡ ${t}</div>`;
      const _good=t=>`<div style="font:600 12px var(--sans);color:#166534;line-height:1.6;padding:5px 0 4px;border-bottom:1px solid var(--line)">✓ ${t}</div>`;

      // Contexte marché depuis rankRows (toutes banques) — comparaisons relatives
      const rr=window._q1RankRows||[];
      const rrWithData=rr.filter(r=>r.app!=null); // seulement les banques dont evAll est chargé
      const myRow=rr.find(r=>r.b===bnq);
      const catalogSize=myRow?.n1||1;
      const totPct=Math.round(tot/catalogSize*100);
      const hasContext=rrWithData.length>=Math.ceil(rr.length/2); // contexte fiable si ≥ moitié chargée
      const allApps=rrWithData.map(r=>r.app??0);
      const rank=hasContext?rrWithData.filter(r=>(r.app??0)>tot).length+1:null;
      const gratRatio=tot>0?Math.round(nGr/tot*100):0;

      const blocks=[];
      if(isSGCI){
        if(tot===0)return'';
        blocks.push(_fact(`SGCI a introduit <b>${tot} nouveau${tot>1?'x':''} service${tot>1?'s':''}</b> sur la période (soit <b>${totPct}%</b> du catalogue actuel), principalement en ${top3.join(', ')}.`));
        if(nGr>0)blocks.push(_good(`<b>${nGr} service${nGr>1?'s':''} gratuit${nGr>1?'s':''}</b> parmi les nouveautés (<b>${gratRatio}%</b>) — argument de différenciation à mettre en avant systématiquement dans les communications commerciales.`));
        // Positionnement relatif (seulement si contexte fiable)
        if(rank!=null){
          const ahead=rrWithData.filter(r=>r.b!=='SGCI'&&(r.app??0)>tot).map(r=>r.b);
          if(rank===1)blocks.push(_good(`<b>SGCI est la banque la plus active en innovation sur cette période</b> — avantage à capitaliser dans la communication marketing.`));
          else if(rank<=Math.ceil(rrWithData.length/2))blocks.push(_alert(`SGCI se classe <b>${rank}ème sur ${rrWithData.length}</b> en volume d'innovation. ${ahead.length?`Les banques qui innovent plus vite : <b>${ahead.join(', ')}</b>` : ''} — <b>surveiller si elles attaquent les mêmes segments.</b>`));
          else blocks.push(_warn(`SGCI se classe <b>${rank}ème sur ${rrWithData.length}</b> en volume d'innovation — parmi les moins actifs du marché. <b>Les banques les plus dynamiques (${rrWithData.sort((a,b)=>(b.app??0)-(a.app??0)).slice(0,2).map(r=>r.b).join(', ')}) creusent l'écart : SGCI doit identifier les segments prioritaires à enrichir.</b>`));
        }
      }else{
        // Positionnement relatif de ce concurrent
        const relPos=rank==null?`actif sur la période`:
          rank===1?`le concurrent <b>le plus actif</b> en innovation sur ce marché`:
          rank<=Math.ceil(rrWithData.length/2)?`dans le <b>top ${rank} des banques les plus innovantes</b> (sur ${rrWithData.length})`:`l'un des <b>moins actifs</b> en innovation (rang ${rank}/${rrWithData.length})`;
        blocks.push(_fact(`<b>${bnq}</b> a lancé <b>${tot} nouveau${tot>1?'x':''} service${tot>1?'s':''}</b> (<b>${totPct}%</b> de son catalogue), concentrés sur ${top3.join(', ')}. C'est ${relPos} sur cette période.`));

        // Gratuits — proportionnel au ratio, pas au nombre brut
        if(nGr>0){
          if(gratRatio===100)blocks.push(_warn(`<b>100% des nouveaux services sont gratuits</b> — ${bnq} a choisi une stratégie purement orientée recrutement client, sans revenus immédiats sur ces nouvelles offres. <b>Les clients SGCI attirés par la gratuité représentent un risque de fuite réel.</b>`));
          else if(gratRatio>=50)blocks.push(_warn(`<b>${nGr}/${tot} nouveaux services gratuits (${gratRatio}%)</b> — stratégie agressive d'acquisition. <b>${bnq} sacrifie une part importante de ses revenus potentiels pour capter des clients — surveiller si ces offres ciblent des segments SGCI.</b>`));
          else blocks.push(_alert(`<b>${nGr} service${nGr>1?'s':''} gratuit${nGr>1?'s':''} parmi les ${tot} nouveautés (${gratRatio}%)</b> — signal ponctuel de recrutement client ciblé sur ces domaines spécifiques.`));
        }

        // Chevauchement avec SGCI — proportionnel au poids réel de l'overlap
        const sgciCore=new Set(['1','2','3','4','5']);
        const overlap=sections.filter(([s])=>sgciCore.has(s));
        const overlapTot=overlap.reduce((s,[,v])=>s+v.n,0);
        if(overlapTot>0){
          const overlapPct=Math.round(overlapTot/tot*100);
          const ov=overlap.map(([s,v])=>`${snC[s]||s} (<b>+${v.n}</b>)`).join(', ');
          if(overlapPct>=60)blocks.push(_warn(`<b>${overlapPct}% des innovations de ${bnq} sont sur des segments SGCI</b> (${ov}) — pression concurrentielle directe et significative. <b>Comparer ces services avec l'offre SGCI pour mesurer le risque de substitution.</b>`));
          else if(overlapPct>=30)blocks.push(_alert(`<b>${overlapPct}% des innovations de ${bnq}</b> recoupent des domaines SGCI (${ov}) — chevauchement partiel. Surveiller l'évolution.`));
          else blocks.push(_fact(`${bnq} touche marginalement des domaines SGCI (${ov} — <b>${overlapPct}%</b> de ses nouvelles offres). Pas de pression concurrentielle directe notable à ce stade.`));
        }

        // Zones spécifiques
        const digitalZone=sections.find(([s])=>s==='7');
        const intlZone=sections.find(([s])=>s==='8');
        const corpZone=sections.find(([s])=>s==='9');
        if(digitalZone)blocks.push(_warn(`<b>${digitalZone[1].n} nouvelle${digitalZone[1].n>1?'s':''} offre${digitalZone[1].n>1?'s':''} Digital/Mobile</b> — le digital est le principal vecteur de fidélisation aujourd'hui. <b>Si SGCI n'accélère pas sur ce segment, ${bnq} peut attirer les clients les plus mobiles.</b>`));
        if(intlZone)blocks.push(_alert(`<b>${intlZone[1].n} service${intlZone[1].n>1?'s':''} international${intlZone[1].n>1?'aux':''}</b> — les clients SGCI ayant des besoins transfrontaliers ont désormais une alternative chez ${bnq}.`));
        if(corpZone)blocks.push(_alert(`<b>${corpZone[1].n} service${corpZone[1].n>1?'s':''} Corporate/Entreprises</b> — si SGCI adresse ce segment, surveiller les migrations de comptes vers ${bnq}.`));
        if(!overlap.length&&!digitalZone&&!intlZone&&!corpZone)blocks.push(_good(`Les innovations de ${bnq} portent sur des segments éloignés du cœur de métier SGCI — <b>pas de pression concurrentielle directe à court terme.</b>`));
      }
      return`<div style="margin-top:14px;padding:12px 14px 8px;background:var(--bg-raise);border-radius:8px;border-left:3px solid #378ADD">
        ${blocks.join('')}
      </div>`;
    };

    box.innerHTML=sa.slice(0,6).map(([s,v])=>{
      const uid=`q1dv_${bnk}_s${s}`;
      // On affiche TOUT (rien masqué) — trié par pertinence, le contexte donne du sens
      // même aux services sans tarif. Cap à 10 pour rester lisible (reste en "+N autres").
      const shown=v.rows.slice(0,10);
      const rest=v.rows.length-shown.length;
      const rows=shown.map(r=>{
        const ctx=r.contexte?r.contexte.replace(/\s*\|\s*/g,' › '):'';
        const ctxH=ctx?`<div style="font-size:9.5px;color:var(--faint);margin-top:1px">${ctx.length>70?ctx.slice(0,68)+'…':ctx}</div>`:'';
        // Badge "depuis XXXX SX" si le service a été introduit AVANT la période courante
        const depuisAn=r.depuis_annee,depuisSem=r.depuis_semestre;
        const depuisBadge=(depuisAn&&depuisAn<CB_YEAR)
          ?`<span style="background:color-mix(in srgb,var(--gold) 14%,transparent);color:var(--gold);border-radius:3px;padding:1px 6px;font:600 9px var(--sans);white-space:nowrap;flex-shrink:0">depuis ${depuisAn} ${depuisSem||''}</span>`
          :(depuisAn&&depuisAn==CB_YEAR)
            ?`<span style="background:color-mix(in srgb,var(--green) 14%,transparent);color:var(--green);border-radius:3px;padding:1px 6px;font:600 9px var(--sans);white-space:nowrap;flex-shrink:0">nouveau ${depuisAn} ${depuisSem||''}</span>`
            :'';
        return`<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid #faf8f4">
          <div style="flex:1;min-width:0;font:500 11.5px var(--sans);color:var(--ink);word-break:break-word">${r.libelle||''}${ctxH}</div>
          ${depuisBadge}
          <div style="flex-shrink:0;font:600 11px var(--mono)">${fmtT(r)}</div>
        </div>`;
      }).join('');
      return`<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f0ede6">
        <span style="font-size:13px;flex-shrink:0">${v.icon}</span>
        <span style="font:700 12px var(--sans);color:${v.color};flex:1">${v.label}</span>
        ${_v3tag('+'+v.n,'tb')}
        ${v.nGrat>0?_v3tag(v.nGrat+' grat.','tg'):''}
        <button onclick="_q1Toggle('${uid}',this)" style="width:24px;height:24px;border-radius:50%;border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;font:700 15px/24px sans-serif;cursor:pointer;flex-shrink:0;text-align:center;transition:all .15s">+</button>
      </div>
      <div id="${uid}" style="display:none;padding:6px 0 10px">
        <div style="font-size:9.5px;color:var(--faint);font-style:italic;margin-bottom:7px">Axe BCEAO ${v.icon} ${v.label} · ${v.n} service${v.n>1?'s':''} · le badge indique la date d'introduction réelle</div>
        ${rows}
        ${rest>0?`<div style="font-size:10px;color:var(--faint);padding-top:5px">… et ${rest} autre${rest>1?'s':''} dans ce domaine</div>`:''}
      </div>`;
    }).join('');
    // Appel LLM — remplace intégralement _analyseNew (plus de code-généré)
    const tot=app.length;
    const nGr=app.filter(r=>r.est_gratuit).length;
    // Axes BCEAO du cœur de métier retail SGCI (Packages, Cartes, Épargne, Crédits, Digital)
    const snCoreKeys=new Set(['1','2','3','4','6']);
    const overlapSecs=sa.filter(([s])=>snCoreKeys.has(s));
    const overlapTot=overlapSecs.reduce((s,[,v])=>s+v.n,0);
    const overlapPct=tot?Math.round(overlapTot/tot*100):0;
    const overlapTxt=overlapSecs.map(([s,v])=>`${v.label} (+${v.n})`).join(', ');
    const myRow=(window._q1RankRows||[]).find(r=>r.b===banque);
    const bankRate=myRow?.n1?Math.round(tot/myRow.n1*100):null;
    const sgciRow=(window._q1RankRows||[]).find(r=>r.b==='SGCI');
    const sgciRate=sgciRow?.n1?Math.round((sgciRow.app||0)/sgciRow.n1*100):null;
    const allRatesArr=(window._q1RankRows||[]).filter(r=>r.n1&&r.app!=null)
      .map(r=>`${r.b} ${Math.round(r.app/r.n1*100)}%`).join(', ');
    const llmPayload={
      banque,segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM, period:`${CB_YEAR} ${CB_SEM}`,
      nTotal:tot,nGrat:nGr,
      topDomains:sa.slice(0,5).map(([s,v])=>({domaine:v.label,n:v.n,nGrat:v.nGrat})),
      overlapPct,overlapTxt,bankRate,sgciRate,allRates:allRatesArr
    };
    box.innerHTML+=`<div id="q1-conc-llm-${bnk}" style="font:400 13px var(--sans);color:var(--ink);line-height:1.7;padding:14px 16px;background:var(--bg-raise);border-radius:8px;border:1px solid var(--line);margin-top:14px"><span style="color:var(--faint);font-style:italic">Analyse stratégique en cours…</span></div>`;
    // Déclencher l'appel LLM immédiatement après injection du div
    setTimeout(async()=>{
      const d=document.getElementById(`q1-conc-llm-${bnk}`);
      if(!d||d.dataset.loaded==='1')return;
      try{
        const res=await fetch('/api/cb_q1_conc_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(llmPayload)});
        if(!res.ok)throw new Error('HTTP '+res.status);
        const j=await res.json();
        const cur=document.getElementById(`q1-conc-llm-${bnk}`);
        if(j.analyse&&cur){cur.dataset.loaded='1';cur.innerHTML=_llmPfx+_fmtAnalyse(j.analyse);}
        else if(cur)cur.innerHTML='';
      }catch(e){const cur=document.getElementById(`q1-conc-llm-${bnk}`);if(cur)cur.innerHTML='';}
    },0);
  }catch(e){
    box.innerHTML=`<p style="color:#dc2626;font:500 12px var(--sans)">Erreur: ${e.message}</p>`;
  }
}

function _renderQ1(payload){
  const rows=(payload&&payload.banques)?payload.banques:(Array.isArray(payload)?payload:[]);
  const ev=(payload&&payload.evolution)||{apparus:[],disparus:[],reprices:[],debut:'',fin:''};
  const evAll=(payload&&payload.evolutions_all)||{};
  const fP=ev.debut||'2024 S1', lP=ev.fin||'2026 S1';
  const [fa,fs]=fP.split(' '), [la,ls]=lP.split(' ');
  const nApp=(ev.apparus||[]).length, nDis=(ev.disparus||[]).length;

  const lk={};rows.forEach(r=>{lk[`${r.banque}_${r.annee}_${r.semestre}`]=r;});
  const bankGrowth=CB_BANK_ORDER.filter(b=>{
    const r0=lk[`${b}_${fa}_${fs}`], r1=lk[`${b}_${la}_${ls}`];
    return r0&&r1&&b!=='SGCI'&&r1.n_services>r0.n_services;
  });

  // app/dis : ajouts et retraits sémantiques par banque
  // SGCI : depuis ev (déjà dans le payload) — cohérent avec "Nouveaux services" Q1
  // Autres : depuis evAll si disponible (background), sinon null
  const rankRows=CB_BANK_ORDER.map(b=>{
    const r1=lk[`${b}_${la}_${ls}`];
    if(!r1)return null;
    const evB=evAll[b];
    const app=b==='SGCI'?nApp:(evB?.nApp??null);
    const dis=b==='SGCI'?nDis:(evB?.nDis??null);
    // n0 métier : déduit depuis n1 et les mouvements sémantiques réels (n1 - ajouts + retraits)
    // Cohérent : n0 + app - dis = n1 ✓
    const n0business=(app!=null&&dis!=null)?r1.n_services-app+dis:null;
    return{b, n0:n0business, n1:r1.n_services, app, dis};
  }).filter(r=>r&&r.n1).sort((a,b2)=>(b2.n1||0)-(a.n1||0));
  const maxN1=Math.max(...rankRows.map(r=>r.n1||0),1);
  const bkCols={SGCI:'#FF9800',SIB:'#4CAF50',NSIA:'#66BB6A',BICICI:'#42A5F5',BNI:'#78909C',ECOBANK:'#FF7043',BACI:'#ccc'};

  const maxN_all=Math.max(...rankRows.map(r=>r.n1),1);
  const rankBars=rankRows.map(r=>{
    const isSGCI=r.b==='SGCI';
    const col=bkCols[r.b]||'#78909C';
    const pct=Math.round(r.n1/maxN_all*100);
    // Delta sémantique (matching label par label)
    const sem=r.d; // null si evolutions_all non chargé
    const grew=sem!=null?sem>0:null;
    const dColor=grew===true?'#166534':grew===false?'#991b1b':'#555';
    const dBg=grew===true?'#dcfce7':grew===false?'#fee2e2':'#f1f5f9';
    const hasEv=r.app!=null&&r.dis!=null;
    const appTxt=hasEv?`+${r.app}`:'—';
    const disTxt=hasEv&&r.dis>0?`-${r.dis}`:(hasEv?'=':'—');
    const n0Txt=r.n0!=null?String(r.n0):'—';
    return`<div style="display:grid;grid-template-columns:80px 1fr 56px 80px;align-items:center;gap:10px;padding:${isSGCI?'8px 12px':'6px 12px'};margin:3px -12px;border-radius:8px;background:${isSGCI?'color-mix(in srgb,var(--amber) 10%,var(--bg-raise))':'transparent'};border-left:${isSGCI?'3px solid var(--amber)':'3px solid transparent'}">
      <div>
        <div style="font:${isSGCI?'700':'600'} 12.5px var(--sans);color:${isSGCI?'var(--amber)':'var(--ink)'}">${isSGCI?'★ SGCI':r.b}</div>
        <div style="font:400 10px var(--sans);color:var(--faint);margin-top:1px">${fP} : ${n0Txt}</div>
      </div>
      <div style="background:var(--bg-raise);border-radius:6px;height:28px;overflow:hidden;border:1px solid var(--line)">
        <div style="height:100%;width:${pct}%;background:${col};border-radius:6px;opacity:${isSGCI?1:0.8}"></div>
      </div>
      <div style="text-align:right">
        <div style="font:700 15px var(--sans);color:${isSGCI?'var(--amber)':'var(--ink)'}">${r.n1}</div>
        <div style="font:400 10px var(--sans);color:var(--faint)">${lP}</div>
      </div>
      <div style="display:flex;gap:3px;justify-content:center">
        <div style="background:${hasEv?'color-mix(in srgb,var(--green) 14%,transparent)':'var(--bg-raise)'};border-radius:5px;padding:3px 6px">
          <div style="font:700 11px var(--mono);color:${hasEv?'var(--green)':'var(--faint)'}">${appTxt}</div>
        </div>
        <div style="background:${hasEv&&r.dis>0?'color-mix(in srgb,var(--red) 14%,transparent)':'var(--bg-raise)'};border-radius:5px;padding:3px 6px">
          <div style="font:700 11px var(--mono);color:${hasEv&&r.dis>0?'var(--red)':'var(--faint)'}">${disTxt}</div>
        </div>
      </div>
    </div>`;
  }).join('');

  // Clé de dédoublonnage : (libelle + contexte + section) — évite les faux changements
  const seenH=new Set();
  const haussesList=(ev.reprices||[])
    .filter(r=>(r.delta_pct||0)>0&&Math.abs(r.delta_pct||0)<=9999)
    .filter(r=>{const k=((r.libelle||'')+'|'+(r.contexte||'')+'|'+(r.section||'')).toLowerCase().trim();if(seenH.has(k))return false;seenH.add(k);return true;})
    .slice(0,8);
  const seenB=new Set();
  const baissesList=(ev.reprices||[])
    .filter(r=>(r.delta_pct||0)<0)
    .filter(r=>{const k=((r.libelle||'')+'|'+(r.contexte||'')+'|'+(r.section||'')).toLowerCase().trim();if(seenB.has(k))return false;seenB.add(k);return true;})
    .slice(0,6);

  // Badge Min/Max : rang=2 → Max, rang=1 → Min SEULEMENT si un rang=2 existe
  // pour le même libellé ET la même section (clé composite libelle|section).
  // Sans la section, "Frais d'envoi DHL" 11.1.1 (valeur unique) recevrait faussement
  // "Min" à cause de "Frais d'envoi DHL" 11.1.2 (vrai intervalle Min/Max).
  const _libsAvecMax=new Set((ev.reprices||[]).filter(r=>r.rang===2).map(r=>`${(r.libelle||'').toLowerCase().trim()}|${r.section||''}`));
  const _rangBadge=(r)=>{
    const _rk=`${(r.libelle||'').toLowerCase().trim()}|${r.section||''}`;
    if(r.rang===2)return'<span style="font:700 9px var(--sans);background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);border-radius:3px;padding:1px 6px;margin-right:5px;vertical-align:middle;letter-spacing:.02em">Max</span>';
    if(r.rang===1&&_libsAvecMax.has(_rk))return'<span style="font:700 9px var(--sans);background:color-mix(in srgb,var(--green) 12%,transparent);color:var(--green);border-radius:3px;padding:1px 6px;margin-right:5px;vertical-align:middle;letter-spacing:.02em">Min</span>';
    return'';
  };

  // Construit l'affichage du chemin hiérarchique complet
  // section_actuelle = numéro 2026 (document courant), section = numéro 2024 (référence)
  const _ctx=(r)=>{
    const parts=[];
    const secDisp=r.section_actuelle||r.section||'';
    if(secDisp)parts.push(secDisp);
    if(r.contexte&&r.contexte!==''){
      const c=r.contexte.replace(/\s*\|\s*/g,' › ');
      parts.push(c.length>60?c.slice(0,58)+'…':c);
    }
    return parts.length?`<div style="font-size:10px;color:var(--faint);margin-top:1px">${parts.join(' · ')}</div>`:'';
  };

  const haussesTbl=haussesList.length?`<table class="t">
    <tr><th>Service &amp; contexte</th><th>Avant</th><th>Après</th><th>Écart</th></tr>
    ${haussesList.map(r=>`<tr>
      <td>${_rangBadge(r)}<span style="font-weight:500;word-break:break-word">${r.libelle||''}</span>${_ctx(r)}</td>
      <td style="white-space:nowrap">${r.montant_avant!=null?_v3f(r.montant_avant):'—'}</td>
      <td style="white-space:nowrap">${r.montant_apres!=null?_v3f(r.montant_apres):'—'}</td>
      <td>${_v3tag('+'+(r.delta_pct||0).toFixed(0)+'%','tr')}</td>
    </tr>`).join('')}
  </table>`:'<p style="font-size:12px;color:var(--muted);margin:0">Aucune hausse tarifaire détectée.</p>';

  const baissesTbl=baissesList.length?`<table class="t">
    <tr><th>Service &amp; contexte</th><th>Avant</th><th>Après</th><th>Signal</th></tr>
    ${baissesList.map(r=>{const p=Math.abs(r.delta_pct||0);return`<tr>
      <td>${_rangBadge(r)}<span style="font-weight:500;word-break:break-word">${r.libelle||''}</span>${_ctx(r)}</td>
      <td style="white-space:nowrap">${r.montant_avant!=null?_v3f(r.montant_avant):'Payant'}</td>
      <td style="white-space:nowrap">${r.montant_apres!=null&&r.montant_apres>0?_v3f(r.montant_apres):'Gratuit'}</td>
      <td>${p>=99?_v3tag('Gratuit','tg'):_v3tag('-'+p.toFixed(0)+'%','tg')}</td>
    </tr>`;}).join('')}
  </table>`:'<p style="font-size:12px;color:var(--muted);margin:0">Aucune baisse tarifaire détectée.</p>';

  window._q1SgciApp=ev.apparus||[];
  // Expose rankRows pour que _loadQ1Conc puisse faire des comparaisons relatives
  window._q1RankRows=rankRows;
  const allQ1Banks=['SGCI',...CB_BANK_ORDER.filter(b=>b!=='SGCI')];
  const concBtns=allQ1Banks.map(b=>{const isSel=b===_q1ConcBank;const isSGCI=b==='SGCI';return`<button class="q1cb-btn" data-b="${b}" onclick="_loadQ1Conc('${b}')" style="font:${isSel||isSGCI?700:500} 12px var(--sans);padding:4px 11px;border-radius:7px;border:1px solid ${isSel?'var(--accent)':'var(--line)'};background:${isSel?'color-mix(in srgb,var(--accent) 15%,var(--bg-raise))':'var(--bg-raise)'};color:${isSel?'var(--ink)':isSGCI?'var(--amber)':'var(--muted)'};cursor:pointer">${isSGCI?'★ SGCI':b}</button>`;}).join('');

  const sgciRow=rankRows.find(r=>r.b==='SGCI');
  // Tout est calculé depuis les deltas bruts (n1-n0) — cohérent avec les barres affichées
  const _rdelta=r=>r.n0?r.n1-r.n0:0;
  const _rpct=r=>r.n0?Math.round((r.n1-r.n0)/r.n0*100):0;
  const sgciDelta=sgciRow?_rdelta(sgciRow):0;
  const sgciPct=sgciRow?_rpct(sgciRow):0;
  const othersRanked=rankRows.filter(r=>r.b!=='SGCI');
  const growthBanks=othersRanked.filter(r=>_rdelta(r)>0).sort((a,b)=>_rdelta(b)-_rdelta(a));
  const shrinkBanks=othersRanked.filter(r=>_rdelta(r)<0).sort((a,b)=>_rdelta(a)-_rdelta(b));
  const topGrower=growthBanks[0]||null;
  const topGrowerDelta=topGrower?_rdelta(topGrower):0;
  const topGrowerPct=topGrower?_rpct(topGrower):0;
  const mktAvgDelta=othersRanked.length?Math.round(othersRanked.reduce((s,r)=>s+_rdelta(r),0)/othersRanked.length):0;
  // Verdict : retard marqué si SGCI croît <50% du rythme du top concurrent et ce dernier a >20%
  const retardMarque=topGrowerPct>20&&sgciPct<topGrowerPct*0.5;
  const vigilance=sgciDelta<0&&topGrowerDelta>5;
  const alerte=sgciDelta>=0&&retardMarque;
  const opportunite=sgciDelta>0&&sgciPct>=mktAvgDelta&&shrinkBanks.length>=2;
  // Données pour le LLM — pas de texte généré par code
  // Classement par AJOUTS BRUTS (apparus) = exactement le badge "+N" affiché sur chaque barre.
  const _topAjouts=[...othersRanked].filter(r=>(r.app||0)>0).sort((a,b2)=>(b2.app||0)-(a.app||0))[0]||null;
  window._q1RankLlmPayload={
    segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM, period:`${fP} → ${lP}`,
    sgci:{n0:sgciRow?.n0||0, n1:sgciRow?.n1||0, ajouts:sgciRow?.app||0, retraits:sgciRow?.dis||0, delta:sgciDelta, pct:sgciPct},
    // ajouts = nouveaux services (badge vert +N) · retraits = services retirés (badge rouge −N) · n1 = catalogue actuel
    allBanks:rankRows.map(r=>({b:r.b,catalogue:r.n1||0,ajouts:r.app||0,retraits:r.dis||0,net:_rdelta(r)})).sort((a,b2)=>(b2.ajouts||0)-(a.ajouts||0)),
    topGrower:_topAjouts?{b:_topAjouts.b, ajouts:_topAjouts.app||0, retraits:_topAjouts.dis||0, catalogue:_topAjouts.n1||0}:null,
    mktAvgDelta, vigilance, alerte, opportunite
  };

  setTimeout(()=>_loadQ1Conc(_q1ConcBank), 300);

  const _q1Html=`
${_v3sec('1','#378ADD',"Qu'est-ce qui a globalement changé sur 3 ans ?","Catalogues tarifaires · "+fP+" → "+lP+" · 7 banques")}
<div class="row r2">
  <div class="panel">
    <div class="panel-title">Évolution des catalogues ${_v3tag(fP,'tb')} → ${_v3tag(lP,'tb')}</div>
    <div style="display:grid;grid-template-columns:80px 1fr 56px 80px;gap:10px;padding:0 12px;margin:0 -12px 8px;align-items:center">
      <span style="font:600 10px var(--sans);color:var(--faint);text-transform:uppercase;letter-spacing:.05em">Banque</span>
      <span style="font:600 10px var(--sans);color:var(--faint);text-transform:uppercase;letter-spacing:.05em">Catalogue ${lP}</span>
      <span style="font:600 10px var(--sans);color:var(--faint);text-align:right">Offres</span>
      <span style="font:600 10px var(--sans);color:var(--faint);text-align:center">+ajouts / -retraits</span>
    </div>
    ${rankBars}
    <div id="cb-q1-rank-llm" style="font:400 13px var(--sans);color:var(--ink);line-height:1.7;padding:14px 16px;background:var(--bg-raise);border-radius:8px;margin-top:16px;border:1px solid var(--line)"><span style="color:var(--faint);font-style:italic">Analyse stratégique en cours…</span></div>
    <div id="cb-q1-rank-llm-stale-badge" style="display:none"></div>
  </div>
  <div class="panel">
    <div class="panel-title">Mouvements tarifaires SGCI ${fP} → ${lP}</div>
    <div style="margin-bottom:10px">
      <div style="font-size:11px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:7px">Hausses tarifaires</div>
      ${haussesTbl}
    </div>
    <div class="divider"></div>
    <div>
      <div style="font-size:11px;font-weight:700;color:#166534;text-transform:uppercase;letter-spacing:.05em;margin-bottom:7px">Baisses / Nouvelles gratuités</div>
      ${baissesTbl}
    </div>
    ${(()=>{
      const secNmRep={'1':'comptes courants','2':'épargne','3':'crédits','4':'paiements','5':'services aux clients','6':'produits spéciaux','7':'digital/mobile','8':'international','9':'entreprises'};
      const allHausses=(ev.reprices||[]).filter(r=>(r.delta_pct||0)>0);
      const allBaisses=(ev.reprices||[]).filter(r=>(r.delta_pct||0)<0);
      if(!allHausses.length&&!allBaisses.length)return _v3ins('Aucun mouvement tarifaire SGCI sur la période — positionnement prix stable.');
      window._q1RepricingPayload={
        segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM, period:`${fP} → ${lP}`,
        nHausses:allHausses.length,nBaisses:allBaisses.length,
        hausses:allHausses.slice(0,8).map(r=>({libelle:(r.libelle||'').slice(0,50),avant:r.montant_avant,apres:r.montant_apres,pct:Math.round(r.delta_pct||0)})),
        baisses:allBaisses.slice(0,5).map(r=>({libelle:(r.libelle||'').slice(0,50),avant:r.montant_avant,apres:r.montant_apres,pct:Math.round(r.delta_pct||0)}))
      };
      return`<div id="cb-q1-repricing-llm" style="font:400 13px var(--sans);color:var(--ink);line-height:1.7;padding:14px 16px;background:var(--bg-raise);border-radius:8px;border:1px solid var(--line);margin-top:14px"><span style="color:var(--faint);font-style:italic">Analyse stratégique en cours…</span></div><div id="cb-q1-repricing-llm-stale-badge" style="display:none"></div>`;
    })()}
  </div>
</div>
<div class="panel" style="margin-bottom:4px">
  <div class="panel-title">Services retirés du catalogue SGCI — ${fP} → ${lP}</div>
  ${(()=>{
    const dis=ev.disparus||[];
    if(!dis.length)return`<p style="font-size:12px;color:var(--muted);margin:0">Aucun service retiré sur la période.</p>`;
    const withC=dis.filter(d=>(d.concurrent_ont||[]).length>0);
    const sorted=[...withC,...dis.filter(d=>!(d.concurrent_ont||[]).length)];
    const items=sorted.slice(0,25).map(d=>{
      const mnt=(()=>{
        if(d.est_gratuit||d.type_valeur==='GRATUIT')return'<span style="color:#16a34a">Gratuit</span>';
        if(d.type_valeur==='TAUX_%'&&d.montant!=null)return`<span style="font:600 11px var(--mono);color:var(--muted)">${d.montant}%</span>`;
        if(d.type_valeur==='SUR_DEMANDE')return'<span style="color:var(--faint);font-size:10px">Sur demande</span>';
        if(d.montant)return _v3f(d.montant);
        const vp=(d.valeur_propre||'').trim();
        return(vp&&!vp.includes('|')&&!vp.includes('##'))?`<span style="font:600 11px var(--mono);color:var(--muted)">${vp}</span>`:'—';
      })();
      const conc=(d.concurrent_ont||[]);
      const badge=conc.length?`<span style="background:#fef3c7;color:#b45309;border-radius:4px;padding:1px 8px;font-size:9.5px;font-weight:700;white-space:nowrap">⚠ ${conc.join(' · ')}</span>`:'';
      const ctxParts=(d.contexte||'').split('|').map(s=>s.trim()).filter(Boolean);
      const ctxBread=ctxParts.length>1?ctxParts.slice(1).join(' › '):(ctxParts[0]||'');
      const ctxL=ctxBread?`<div style="font-size:10px;color:var(--faint);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:340px">${ctxBread.slice(0,90)}${ctxBread.length>90?'…':''}</div>`:'';
      const strategic=(()=>{
        if(conc.length>=3)return`<div style="font-size:10px;color:#b45309;margin-top:4px;padding:3px 6px;background:color-mix(in srgb,var(--amber) 8%,var(--bg-raise));border-left:2px solid var(--amber);border-radius:0 3px 3px 0">⚠ Risque élevé — ${conc.length} concurrents proposent encore ce service (${conc.join(', ')}). Un client cherchant ce produit ira directement chez eux.</div>`;
        if(conc.length>0)return`<div style="font-size:10px;color:#92400e;margin-top:4px;padding:3px 6px;background:color-mix(in srgb,var(--gold) 8%,var(--bg-raise));border-left:2px solid var(--gold);border-radius:0 3px 3px 0">À surveiller — encore proposé par ${conc.join(', ')}. Vérifier l'usage client avant de confirmer le retrait.</div>`;
        return`<div style="font-size:10px;color:var(--muted);margin-top:4px;padding:3px 6px;background:var(--bg-raise);border-left:2px solid var(--line);border-radius:0 3px 3px 0">Retrait non-différenciant — aucun concurrent ne propose ce service. Impact client attendu : faible.</div>`;
      })();
      return`<div style="padding:7px 0;border-bottom:1px solid var(--line)">
        <div style="display:flex;align-items:flex-start;gap:10px">
          <div style="flex:0 0 56px;font-size:9.5px;color:var(--faint);padding-top:2px">${d.section||'—'}</div>
          <div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;color:var(--ink)">${d.libelle}</div>${ctxL}</div>
          <div style="flex:0 0 auto;font-size:12px;font-weight:700;color:var(--muted);white-space:nowrap;padding-top:1px">${mnt}</div>
          <div style="flex:0 0 auto;padding-top:1px">${badge}</div>
        </div>
        ${strategic}
      </div>`;
    }).join('');
    const rest=sorted.length-25;
    const restL=rest>0?`<div style="font-size:10px;color:var(--faint);padding-top:6px">… et ${rest} autre${rest>1?'s':''} service${rest>1?'s':''} retiré${rest>1?'s':''}</div>`:'';
    window._q1RetraitPayload={
      segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM, period:`${fP} → ${lP}`,
      nRetraits:sorted.length,avecConcurrence:withC.length,
      services:sorted.slice(0,10).map(d=>({libelle:d.libelle,concurrents:d.concurrent_ont||[]}))
    };
    return`<div style="max-height:300px;overflow-y:auto;margin-bottom:8px">${items}${restL}</div><div id="cb-q1-retrait-llm" style="font:400 10.5px var(--sans);color:var(--ink);line-height:1.6;padding:8px 12px;background:var(--bg-raise);border-radius:7px;border:1px solid var(--line);margin-top:4px"><span style="color:var(--faint);font-style:italic">Analyse stratégique en cours…</span></div><div id="cb-q1-retrait-llm-stale-badge" style="display:none"></div>`;
  })()}
</div>
<div class="panel" style="margin-bottom:4px">
  <div class="panel-title">Nouveaux services concurrents — par domaine</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">${concBtns}</div>
  <div id="q1-conc-title" style="font-size:11px;font-weight:700;color:#378ADD;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Nouveaux services — ${_q1ConcBank}</div>
  <div id="q1-conc-list"><div style="padding:8px 0;color:var(--muted);font:500 12px var(--sans)">Chargement…</div></div>
  <details id="cb-evo-panel" open style="margin-top:14px;border:1px solid var(--line);border-radius:8px;background:var(--bg-raise)" ontoggle="if(this.open)_renderEvolutionTemporelle()">
    <summary style="cursor:pointer;padding:9px 13px;font:700 11px var(--sans);color:var(--ink);list-style:none;display:flex;align-items:center;gap:7px">
      <span style="color:var(--accent-2)">📈 Évolution sur 3 ans</span>
      <span style="font:500 10px var(--sans);color:var(--faint)">— classement catalogue & taux de gratuité SGCI · ${fP} → ${lP}</span>
    </summary>
    <div id="cb-evo-content" style="padding:4px 13px 13px"><div style="color:var(--faint);font:500 11px var(--sans);padding:8px 0">Chargement…</div></div>
  </details>
</div>
<div class="panel" style="margin-bottom:4px">
  <div class="panel-title">Synthèse stratégique SGCI — direction sur 3 ans</div>
  <div style="font:500 10px var(--sans);color:var(--faint);margin:-4px 0 8px">Lecture des mouvements propres à SGCI (nouvelles offres, retraits, hausses/baisses) face au rythme du marché — conclusion de la section 1.</div>
  <div id="cb-q1-llm" style="font:400 11px var(--sans);color:var(--ink);line-height:1.7;padding:2px 0">
    <span style="color:var(--faint);font-style:italic">Analyse en cours…</span>
  </div>
  <div id="cb-q1-llm-stale-badge" style="display:none"></div>
</div>`;
  // Payload pour l'appel LLM async — calculé depuis les données déjà traitées
  window._q1LlmPayload={
    segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM,
    nApp:(ev.apparus||[]).length,
    nDis:(ev.disparus||[]).length,
    nBaisses:(ev.reprices||[]).filter(r=>(r.delta_pct||0)<0).length,
    nHausses:(ev.reprices||[]).filter(r=>(r.delta_pct||0)>0).length,
    apparus:(ev.apparus||[]).slice(0,15).map(a=>({libelle:a.libelle,est_gratuit:a.est_gratuit,section:a.section})),
    period:`${ev.debut||'2024 S1'} → ${ev.fin||'2026 S1'}`,
    mktContext:rankRows.filter(r=>r.b!=='SGCI').map(r=>({b:r.b,delta:r.app||0})).sort((a,b2)=>b2.delta-a.delta)
  };
  return _q1Html;
}

// ── Formatage riche des analyses LLM ────────────────────────────────────────
const _BANKS_RE=new RegExp('\\b(BICICI|SIB|ECOBANK|BNI|NSIA|BACI|SGCI)\\b','g');
const _llmPfx='';

/* MENTION D'UNE RÉDACTION DE SECOURS (2026-08-10).
   Quand le quota du modèle est épuisé, le serveur rédige lui-même à partir des données. Le
   texte est juste — il est calculé sur les mêmes chiffres — mais plus sec. On le dit au
   lecteur : faire passer une rédaction de secours pour l'analyse complète serait le tromper
   sur ce qu'il lit, et c'est le genre de silence qui se paie en soutenance. */
function _mentionSecours(d){
  // Même raison que le badge ci-dessus : c'est l'état du service de rédaction qui est
  // décrit, pas la justesse du contenu. Le texte de secours est CALCULÉ sur les mêmes
  // chiffres — il est plus sec, pas moins exact. Inutile d'en avertir qui n'y peut rien.
  if(!_voitAvertissementsTechniques() || !d || d.source !== 'deterministe') return '';
  return `<div style="margin-bottom:7px;padding:5px 9px;border-left:2px solid #B45309;
    background:#B4530914;border-radius:0 5px 5px 0;font:600 10.5px/1.45 var(--sans);
    color:var(--muted)">${_soEsc(d.mention || 'Rédaction automatique à partir des données.')}</div>`;
}
// Un montant brut (10 625 000 F) n'est pas toujours un prix ferme — la grille tarifaire porte
// parfois un plafond/plancher (« <= 10 625 000 Fcfa Forfait ») que la seule colonne `montant`
// ne montre pas. Repéré le 2026-07-28 (directeur) : le badge affichait "10 625 000 F" à côté
// d'une analyse qui, elle, disait bien "plafonné à" — incohérent d'un endroit à l'autre de
// la même carte. On préfixe donc le badge dès que `valeur_propre` porte un tel qualificatif.
function _prixQualif(item){
  const brute=(item.valeur_propre||item.valeur_brute||'').toLowerCase();
  if(!brute)return'';
  if(/<=|≤|\bmax\b|\bmaximum\b|plafond|jusqu/.test(brute))return'≤ ';
  if(/>=|≥|\bmin\b|\bminimum\b|a partir|à partir/.test(brute))return'dès ';
  return'';
}
// Formate le prix d'un item enrichi (libelle/contexte/montant/est_gratuit/type_valeur)
function _prixTag(item){
  if(!item||typeof item==='string')return'';
  if(item.est_gratuit)return'<span style="padding:1px 6px;border-radius:10px;background:#D1FAE5;color:#065F46;font:700 9px var(--sans)">GRATUIT</span>';
  if(!item.montant)return'';
  if((item.type_valeur||'').includes('TAUX')){
    if(+item.montant>100)return`<span style="padding:1px 6px;border-radius:10px;background:#F1F5F9;color:#64748B;font:600 9px var(--sans)">Sur dem.</span>`;
    return`<span style="padding:1px 6px;border-radius:10px;background:#FEF3C7;color:#92400E;font:700 9px var(--sans)">${_prixQualif(item)}${item.montant}%</span>`;
  }
  return`<span style="padding:1px 6px;border-radius:10px;background:#F1F5F9;color:#475569;font:600 9px var(--sans)">${_prixQualif(item)}${Number(item.montant).toLocaleString('fr-FR')} ${_curSym(item.unite)}</span>`;
}
// Retourne le libellé d'un item (objet enrichi ou string legacy)
function _itemLib(item){return(typeof item==='string'?item:item.libelle)||'';}
// Retourne le contexte court d'un item (max 80 chars)
function _itemCtx(item){
  if(!item||typeof item==='string')return'';
  const c=(item.contexte||'').trim();
  if(!c)return'';
  const parts=c.split('|');
  const last=parts[parts.length-1].trim();
  return last.length>4?last.slice(0,80)+(last.length>80?'…':''):'';
}
// Extrait la section SYNTHÈSE d'une réponse LLM; retourne '' si absente ou trop courte
function _extractSynthese(analyse){
  if(!analyse)return'';
  const _HEADER=/^(SYNTH[ÈE]SE|GAPS\s+CONFIRM|EXCLUSIFS?\s+CONFIRM|FORMAT|MISSION|R[ÈE]GLES?|AXE\s*:)/i;
  const idx=analyse.search(/SYNTH[ÈE]SE/i);
  if(idx>=0){
    const raw=analyse.slice(idx).replace(/^SYNTH[ÈE]SE\s*\(?\d*\s*\w*\s*\)?\s*[:—\-]?\s*/i,'');
    const lines=raw.split('\n').filter(l=>l.trim()&&!l.trimStart().startsWith('•')&&!l.trimStart().startsWith('-')&&!_HEADER.test(l.trim()));
    const text=lines.join(' ').trim();
    return text.length>=20?text:'';
  }
  // Fallback : lignes non-bullet non-entête
  const lines=analyse.split('\n').filter(l=>{
    const t=l.trim();
    return t&&!t.startsWith('•')&&!t.startsWith('-')&&!_HEADER.test(t)&&t.length>20;
  });
  const text=lines.join(' ').trim();
  return text.length>=20?text:'';
}
// ── Conclusion stratégique globale ────────────────────────────────────────────
let _conclusionFired=false;
async function _tryFireConclusion(){
  // Bloc « Conclusion stratégique » RETIRÉ de CB (demande directeur, doublon) : le diagnostic chiffré,
  // SWOT, forces de Porter, plan d'action et projection 3 ans sont dans l'onglet Stratégie. Le
  // positionnement prix actionnable est dans le Récap (onglet Prix). On ne rend plus rien ici.
  const _cc=document.getElementById('cb-conclusion-content'); if(_cc)_cc.innerHTML='';
  return;
  if(_conclusionFired)return;
  const q3ok=!!window._CB_Q3_DATA;
  const q5ok=window._CB_Q5_SUMMARY&&Object.keys(window._CB_Q5_SUMMARY).length>0;
  if(!q3ok||!q5ok)return;
  _conclusionFired=true;
  const div=document.getElementById('cb-conclusion-content');
  if(!div||div.dataset.loaded==='1')return;
  // Construire résumés
  const excl_by_axe={};
  Object.values(window._CB_Q3_DATA.axes||{}).forEach(a=>{
    if(a.exclusifs?.length)excl_by_axe[a.axe_label]=a.exclusifs.length;
  });
  const gaps_by_bank=window._CB_Q5_SUMMARY||{};
  // Table visuelle
  const totalExcl=Object.values(excl_by_axe).reduce((a,b)=>a+b,0);
  const maxGaps=Math.max(...Object.values(gaps_by_bank),1);
  const banksRanked=Object.entries(gaps_by_bank).sort((a,b)=>b[1]-a[1]);
  const threatRows=banksRanked.map(([bank,n],i)=>{
    const pct=Math.round(n/maxGaps*100);
    const col=i===0?'var(--red)':i===1?'var(--amber)':i<=3?'var(--gold)':'var(--muted)';
    return`<div class="bar-row">
      <span class="bar-lbl" style="color:${col};font-weight:700">${bank}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${col}"></div></div>
      <span class="bar-val">${n}</span>
      <span style="font:400 9px var(--sans);color:var(--faint);margin-left:2px">gaps</span>
    </div>`;
  }).join('');
  const exclRows=Object.entries(excl_by_axe).sort((a,b)=>b[1]-a[1]).map(([axe,n])=>{
    const pct=Math.round(n/totalExcl*100);
    return`<div class="bar-row">
      <span class="bar-lbl">${axe}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:var(--green)"></div></div>
      <span class="bar-val" style="color:var(--green)">${n}</span>
    </div>`;
  }).join('');
  div.innerHTML=`<div id="cb-ax-conclusion" style="scroll-margin-top:160px">
  ${_v3sec('★','var(--gold)',"Conclusion stratégique","Forces SGCI & Menaces concurrentielles · "+CB_SEG+" "+CB_YEAR+" "+CB_SEM)}
  <div class="row r2" style="margin-bottom:18px">
    <div class="panel" style="border-top:3px solid var(--green)">
      <div class="panel-title" style="color:var(--green)">✅ Forces SGCI — ${totalExcl} exclusivités par domaine</div>
      ${exclRows}
    </div>
    <div class="panel" style="border-top:3px solid var(--red)">
      <div class="panel-title" style="color:var(--red)">⚠ Menaces — Qui surveiller en priorité</div>
      ${threatRows}
    </div>
  </div>
  <div class="panel" style="border-left:4px solid var(--accent-2)">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font:500 12px var(--sans);color:var(--muted)">
      <span style="font:800 13px var(--mono);color:var(--accent-2)">◆</span>
      <span>L'<b>analyse stratégique complète</b> (diagnostic chiffré, SWOT, forces de Porter, plan d'action, projection 3 ans) est dans l'onglet</span>
      <button onclick="go('strategie')" style="font:700 11px var(--sans);padding:5px 12px;border-radius:7px;border:1px solid var(--accent-2);background:var(--accent-2);color:#fff;cursor:pointer">Stratégie →</button>
      <span style="color:var(--faint)">— évite le doublon.</span>
    </div>
  </div>
</div>`;
  // SWOT / analyse stratégique globale : centralisée dans l'onglet Stratégie (anti-redondance).
  div.dataset.loaded='1';
}

// Aère la prose LLM : un retour à la ligne après chaque fin de phrase (. ! ?).
// Sûr pour le HTML déjà injecté (spans) et les décimales (1,84 / 1.9 restent intactes).
function _brSentences(s){
  if(!s) return s;
  // Coupe après chaque fin de phrase. Le lookahead inclut « < » car les mots de début de phrase
  // (noms de banques, chiffres) sont souvent déjà enveloppés dans un <span>/<b> par le formateur.
  return String(s).replace(/([.!?])\s+(?=[«"'‹A-ZÀ-ÖØ-Þ0-9]|<(?:span|b|i)\b)/g, '$1<br>');
}

function _fmtAnalyse(raw){
  if(!raw)return '';
  // Protège les segments **...** pour éviter les doubles remplacements
  const _boldSegs=[];
  let t=raw.replace(/\*\*([^*\n]+)\*\*/g,(_,inner)=>{
    _boldSegs.push(inner);
    return`\x00BOLD${_boldSegs.length-1}\x00`;
  });
  // ── Emphase UNIFORME : une seule couleur/graisse pour TOUT ce qui est mis en avant
  // (noms de banques, %, FCFA, rangs, gras du LLM) — avant : 4 couleurs différentes selon le
  // type de token (indigo/orange/vert-bleu/gras neutre), lu comme "parfois violet, parfois
  // juste gras" (incohérent). Seuls les badges de STATUT (⚠ à vérifier / ✓ validé, plus bas)
  // gardent une couleur distincte : ils portent un sens (alerte/validation), pas une simple emphase.
  const _EMPH='font-weight:700;color:#3730A3';
  t=t.replace(_BANKS_RE, `<span style="${_EMPH}">$1</span>`);
  t=t.replace(/([\+\-]?\d+(?:[,\.]\d+)?\s*%)/g, `<span style="${_EMPH}">$1</span>`);
  t=t.replace(/\b(\d[\d\s]*)\s*(FCFA|F CFA)\b/gi, `<span style="${_EMPH}">$1 $2</span>`);
  t=t.replace(/(#\d+\/\d+)/g, `<span style="${_EMPH}">$1</span>`);
  // ⚠ À VÉRIFIER → rouge signalement faux positif
  t=t.replace(/(\[⚠[^\]]*\])/g,
    '<span style="font-weight:700;color:#DC2626;background:#FEF2F2;padding:1px 5px;border-radius:4px">$1</span>');
  // ✓ VALIDÉ → vert confirmation
  t=t.replace(/(\[(?:VALIDÉ|EXCLUSIF|✓)[^\]]*\])/g,
    '<span style="font-weight:700;color:#15803D;background:#F0FDF4;padding:1px 5px;border-radius:4px">$1</span>');
  // Restaure les **...** du LLM dans la MÊME emphase uniforme (pas de surlignement, pas de couleur à part)
  t=t.replace(/\x00BOLD(\d+)\x00/g,(_,i)=>`<span style="${_EMPH}">${_boldSegs[parseInt(i)]}</span>`);
  // Découpage en paragraphes
  let segs=t.split(/\n+/).map(s=>s.trim()).filter(Boolean);
  if(segs.length<=1){
    const m=t.split(/(?=\d\.\s)/);
    if(m.length>1)segs=m.map(s=>s.trim()).filter(Boolean);
  }
  return segs.map(s=>{
    const isQ=s.includes('?')&&!s.startsWith('<span');
    if(isQ)return`<div style="margin:16px 0 6px;padding:11px 15px;background:#EEF2FF;border-left:4px solid #6366F1;border-radius:0 8px 8px 0;color:#312E81;font-weight:600;font-size:13px;line-height:1.65">${_brSentences(s)}</div>`;
    // prose : paragraphe AUTO-SUFFISANT (fond clair + texte foncé) → lisible quel que
    // soit le conteneur (fond sombre var(--bg-raise) OU fond clair codé en dur) et quel
    // que soit le thème. Avant : couleur seule (#1E293B) → invisible sur fond sombre.
    return`<div style="margin:9px 0 0;padding:9px 13px;background:#F8FAFC;border:1px solid #E8EDF3;border-radius:8px;line-height:1.7;color:#1E293B;font-size:13px">${_brSentences(s)}</div>`;
  }).join('');
}

// ── Lookup descriptions produits SGCI (enrichissement cartes innovations) ──
const _SGCI_PRODUCT_DESC={
  'via mybusiness':'Accès aux services PME de SGCI via la plateforme MyBusiness — gestion des flux, paiements entreprise et services bancaires intégrés. Argument commercial fort sur le segment Entreprises.',
  'mybusiness':'Solution digitale corporate pour PME/TPE — tableau de bord financier, paiements en lot, gestion de trésorerie. Différenciateur clé face à BICICI et SIB sur le corporate.',
  'sgconnect':'Plateforme de connectivité bancaire API/EDI — synchronisation des comptes SGCI avec les ERP et outils de gestion d\'entreprise. Innovation structurante pour le corporate banking.',
  'sg connect':'Connectivité bancaire — synchronisation des comptes SGCI avec les outils de gestion d\'entreprise via API.',
  'sogeconnect':'Connectivité API Société Générale — accès programmatique aux comptes et flux bancaires pour les entreprises.',
  'atd':'Avis à Tiers Détenteur — procédure légale forçant un tiers (employeur, banque) à bloquer et verser les fonds du débiteur. Lié aux créances contentieuses.',
  'saisie-attribution':'Saisie-attribution judiciaire — blocage et attribution immédiate des fonds du compte débiteur sur décision de justice.',
  'saisie':'Procédure d\'exécution forcée permettant le recouvrement de créances impayées par voie légale.',
  'frais de traitement':'Tarification des opérations de traitement administratif ou contentieux liées à des services bancaires spécifiques.',
};

// ── Filtre banque panneau innovations (global, appelé par onclick) ──────────
function _q2InnoFilter(b){
  document.querySelectorAll('[data-inno-bank]').forEach(el=>el.style.display='none');
  const el=document.getElementById('cb-q2-inno-'+b.replace(/\s+/g,'_'));
  if(el)el.style.display='block';
  document.querySelectorAll('[data-inno-btn-bank]').forEach(btn=>{
    const on=btn.dataset.innoBtnBank===b;
    btn.style.background=on?'#1D9E75':'#fff';
    btn.style.color=on?'#fff':'var(--ink)';
    btn.style.borderColor=on?'#1D9E75':'#CBD5E1';
    btn.style.fontWeight=on?'700':'500';
  });
}

// ── Q1 : enrichissement LLM async ────────────────────────────────────────────
async function _fireQ1LLM(){
  // Appel 1 : ranking panel
  const rankPayload=window._q1RankLlmPayload;
  const rankDiv=document.getElementById('cb-q1-rank-llm');
  if(rankPayload&&rankDiv&&rankDiv.dataset.loaded!=='1'){
    try{
      const res=await fetch('/api/cb_q1_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...rankPayload,scope:'ranking'})});
      if(!res.ok)throw new Error('HTTP '+res.status);
      const d=await res.json();
      if(d.analyse){rankDiv.dataset.loaded='1';rankDiv.innerHTML=_mentionSecours(d)+_llmPfx+_fmtAnalyse(d.analyse);}
      else{rankDiv.innerHTML='';}
      _showStaleBadge('cb-q1-rank-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
    }catch(e){rankDiv.innerHTML='';}
  }
  // Appel 2 : repricing
  _fireQ1RepricingLLM();
  // Appel 3 : services retirés
  _fireQ1RetraitLLM();
  // Appel 4 : synthèse stratégique (panel bas)
  const payload=window._q1LlmPayload;
  const div=document.getElementById('cb-q1-llm');
  if(!payload||!div||div.dataset.loaded==='1')return;
  try{
    const res=await fetch('/api/cb_q1_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,scope:'synthesis'})});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    if(d.analyse){div.dataset.loaded='1';div.innerHTML=_mentionSecours(d)+_llmPfx+_fmtAnalyse(d.analyse);}
    else{div.innerHTML='';}
    _showStaleBadge('cb-q1-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){div.innerHTML='';}
}

async function _fireQ1RepricingLLM(){
  const payload=window._q1RepricingPayload;
  const div=document.getElementById('cb-q1-repricing-llm');
  if(!payload||!div||div.dataset.loaded==='1')return;
  try{
    const res=await fetch('/api/cb_q1_repricing_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    if(d.analyse){div.dataset.loaded='1';div.innerHTML=_mentionSecours(d)+_llmPfx+_fmtAnalyse(d.analyse);}
    else{div.innerHTML='';}
    _showStaleBadge('cb-q1-repricing-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){div.innerHTML='';}
}

async function _fireQ1RetraitLLM(){
  const payload=window._q1RetraitPayload;
  const div=document.getElementById('cb-q1-retrait-llm');
  if(!payload||!div||div.dataset.loaded==='1')return;
  try{
    const res=await fetch('/api/cb_q1_retrait_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    if(d.analyse){div.dataset.loaded='1';div.innerHTML=_mentionSecours(d)+_llmPfx+_fmtAnalyse(d.analyse);}
    else{div.innerHTML='';}
    _showStaleBadge('cb-q1-retrait-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){div.innerHTML='';}
}

// ── Q2 : synthèse marché LLM async ───────────────────────────────────────────
// NOTE : re-capture la div APRÈS await pour toujours injecter dans la div courante
// (Q2 peut être re-rendu 2× pendant que Groq répond : evAll puis evCross)
async function _fireQ2MarketLLM(){
  const payload=window._q2MarketPayload;
  if(!payload)return;
  const divCheck=document.getElementById('cb-q2-market-llm');
  if(!divCheck||divCheck.dataset.loaded==='1')return;
  divCheck.dataset.loading='1';
  try{
    const res=await fetch('/api/cb_q2_market_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    // Re-trouver la div après l'await (elle a pu être remplacée par un re-render)
    const cur=document.getElementById('cb-q2-market-llm');
    if(d.analyse&&cur){cur.dataset.loaded='1';cur.innerHTML=_llmPfx+_fmtAnalyse(d.analyse);}
    else if(cur){cur.innerHTML='';}
    _showStaleBadge('cb-q2-market-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){
    const cur=document.getElementById('cb-q2-market-llm');
    if(cur)cur.innerHTML='';
  }
}

// ── Q2 : analyse LLM panneau innovations ─────────────────────────────────────
async function _fireQ2InnoLLM(){
  const payload=window._q2InnoLlmPayload;
  const div=document.getElementById('cb-q2-inno-llm');
  if(!payload||!div||div.dataset.loaded==='1')return;
  try{
    const res=await fetch('/api/cb_q2_inno_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    const cur=document.getElementById('cb-q2-inno-llm');
    if(d.analyse&&cur){cur.dataset.loaded='1';cur.innerHTML=_llmPfx+_fmtAnalyse(d.analyse);}
    else if(cur){cur.innerHTML='';}
    _showStaleBadge('cb-q2-inno-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){
    const cur=document.getElementById('cb-q2-inno-llm');
    if(cur)cur.innerHTML='';
  }
}

// ── Q2 : enrichissement LLM async après render ───────────────────────────────
// Appelé une seule fois après chaque re-render de Q2 (quand cross-segment est dispo)
async function _fireQ2LLM(){
  const targets=window._q2LlmTargets||[];
  for(const t of targets){
    const safeId=t.bankName.replace(/\s+/g,'_');
    const div=document.getElementById(`cb-q2-llm-${safeId}`);
    if(!div||div.dataset.loaded==='1')continue;
    div.style.display='block';
    div.innerHTML=`<span style="color:var(--faint);font-style:italic">Analyse stratégique en cours…</span>`;
    try{
      const res=await fetch('/api/cb_q2_llm',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(t)
      });
      if(!res.ok)throw new Error('HTTP '+res.status);
      const d=await res.json();
      if(d.analyse){
        div.dataset.loaded='1';
        div.innerHTML=_llmPfx+_fmtAnalyse(d.analyse);
      } else {
        div.style.display='none';
      }
      _showStaleBadge(`cb-q2-llm-${safeId}-stale-badge`, {stale:d.stale, generated_at:d.generated_at});
    }catch(e){
      div.style.display='none';
    }
  }
}
// Détecte un libellé OCR CORROMPU PAR ESPACEMENT (lettres éclatées : « D ty é p li e v ) rance de
// carte ») — motif que le filtre existant (longueur/regex de tête) ne capte pas. On compte la part
// de « mots » suspicieusement courts (≤2 caractères) en EXCLUANT les mots courts légitimes du
// français (de, à, par, pour…) pour ne pas pénaliser un libellé normal ("Frais de tenue de compte").
const _FR_STOP=new Set(['de','du','des','le','la','les','un','une','et','ou','à','a','en','au','aux','ce','se','sa','son','ses','pour','par','sur','sous','dans','avec','sans','ne','pas','qui','que','dont','ces','cette','tout','tous','y']);
const _ocrSpacingCorrupt=text=>{
  const toks=(text||'').trim().split(/\s+/).map(t=>t.replace(/^[('"«]+|[)'"».,;:]+$/g,'')).filter(Boolean);
  if(toks.length<5)return false;
  const suspicious=toks.filter(t=>t.length<=2 && !_FR_STOP.has(t.toLowerCase())).length;
  return (suspicious/toks.length)>0.3;
};

// ── Justifications PRÉCALCULÉES (exclusif/inimitable/transformatif) — cache, jamais de LLM live ──
window._CB_JUSTIF=window._CB_JUSTIF||null;
async function _loadJustif(){
  if(window._CB_JUSTIF)return window._CB_JUSTIF;
  try{const r=await fetch('/api/cb_justifications');window._CB_JUSTIF=await r.json();}
  catch(e){window._CB_JUSTIF={produits:[]};}
  return window._CB_JUSTIF;
}
function _justifFor(lib){
  const J=window._CB_JUSTIF;if(!J||!J.produits)return null;
  const low=(lib||'').toLowerCase();
  return J.produits.find(p=>(p.match||[]).some(k=>low.includes(k)))||null;
}
function _justifBox(j){
  if(!j)return '';
  const niv=j.inimitabilite||'—';
  const nivCol=/élev|elev/i.test(niv)?'#1D9E75':/moyen/i.test(niv)?'#D97706':'#9CA3AF';
  return `<details style="margin:3px 0 2px 17px">
    <summary style="cursor:pointer;font:600 9.5px var(--sans);color:var(--accent-2);list-style:none">ℹ pourquoi exclusif / inimitable ?</summary>
    <div style="margin-top:4px;padding:7px 9px;background:var(--bg-raise);border-radius:6px;border:1px solid var(--line);font:400 10px/1.5 var(--sans);color:var(--ink)">
      <div><b>Exclusif :</b> ${j.exclusif||'—'}</div>
      <div style="margin-top:3px"><b>Inimitable :</b> <span style="color:${nivCol};font-weight:700">${niv}</span> — ${j.pourquoi_inimitable||'—'}</div>
      <div style="margin-top:3px"><b>Transformatif :</b> ${j.transformatif||'—'}</div>
      ${j.source?`<div style="margin-top:4px"><a href="${j.source}" target="_blank" style="color:var(--accent-2);font-size:9px">source publique ↗</a></div>`:''}
    </div>
  </details>`;
}

// ── Q3 : enrichissement LLM async ────────────────────────────────────────────
async function _fireQ3LLM(){
  const div=document.getElementById('cb-q3-axes-content');
  if(!div||div.dataset.loaded==='1')return;
  try{
    // Cette carte est « Ce que SGCI a seul » — TOUJOURS SGCI, pas de filtre banque (une
    // exclusivité SGCI ne peut pas varier selon une autre banque sélectionnée, aucun sens).
    const res=await fetch('/api/cb_exclusivites_axes',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({segment:CB_SEG,annee:CB_YEAR,semestre:CB_SEM,banque:'SGCI'})
    });
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    await _loadJustif();
    div.dataset.loaded='1';
    div.innerHTML=_buildQ3AxesHTML(d);
    // Stocker pour la conclusion
    window._CB_Q3_DATA=d;
    _tryFireConclusion();
  }catch(e){
    div.innerHTML=`<div style="padding:16px;color:var(--red);font-size:12px">Erreur analyse : ${e.message}</div>`;
  }
}

function _buildQ3AxesHTML(d){
  const axes=d.axes||{};
  const AXE_C={'1':'#7F77DD','2':'#378ADD','3':'#1D9E75','4':'#FF9800','5':'#E91E63','6':'#06B6D4','7':'#8B5CF6','8':'#6B7280'};
  const AXE_I={'1':'📦','2':'💳','3':'💰','4':'🏦','5':'🛡','6':'📱','7':'📈','8':'🔧'};
  const active=Object.entries(axes).filter(([,v])=>v.exclusifs&&v.exclusifs.length>0)
    .sort((a,b)=>b[1].exclusifs.length-a[1].exclusifs.length);
  const empty=Object.entries(axes).filter(([,v])=>!v.exclusifs||!v.exclusifs.length);
  if(!active.length)return`<div style="padding:20px;text-align:center;color:var(--muted);font-size:12px">Aucune exclusivité confirmée après validation sémantique.</div>`;

  // ── Aplatir tous les exclusifs avec leur axe pour le Top 10 ──
  const allItems=[];
  active.forEach(([id,axe])=>{
    axe.exclusifs.forEach(it=>allItems.push({...it,name:_itemLib(it),axe_id:id,axe_label:axe.axe_label}));
  });
  // SCORE DE DISTINCTION (pas juste le prix) :
  //  1) on écarte le bruit OCR / fragments non parlants ("Titulaire", "Pour tout montant", "Par série…")
  //  2) on fait remonter les services VRAIMENT distinctifs : digital nommé (CONNECT…) > produit nommé (PACK, SOGE, YACONFORT, Bourse…) > autre, le prix départageant à l'intérieur de chaque catégorie.
  const _JUNK_EXCL=/^(titulaire|pour tout montant|par s[ée]rie|montant (compris|sup|inf)|de \d|co[uû]t|autres? types?|frais$|pour les|y compris)/i;
  const _isJunkExcl=it=>{const l=(_itemLib(it)||'').trim();
    return l.length<14 || _JUNK_EXCL.test(l) || /^[a-zàâçéèêëîïôùû(]/.test(l) || _ocrSpacingCorrupt(l);};   // fragment = commence en minuscule / trop court / générique / OCR éclaté
  const _distScore=it=>{
    const l=(_itemLib(it)||'').toLowerCase(); const m=+(it.montant||0);
    const px=m>0?Math.log10(m+1):0;                                   // prix compressé (0..7) = départage interne
    if(/connect|mobile|en ligne|application|sans carte|digital|e-?cnps|mybusiness|web/.test(l)) return 400+px; // digital distinctif
    if(/\b(pack|soge|yaconfort|quietis|zenith|diaspora|prestibad|horizon|elite|infinite|bourse|opcvm|titres|assurance|sogeprimo)\b/.test(l)) return 300+px; // produit nommé
    if((it.type_valeur||'').includes('TAUX')) return 100+px;
    return 200+px;                                                    // autre service tarifé réel
  };
  const _allRanked=allItems.filter(it=>!_isJunkExcl(it)).sort((a,b)=>_distScore(b)-_distScore(a));
  const TOP=15;
  // 2026-07-17 (demande explicite) : SÉPARER strictement les deux natures, jamais les mélanger
  // dans une même liste « Top exclusivités » — un produit marqué « pas une exclusivité » n'a rien
  // à faire dans une liste appelée Exclusivités, même avec un badge. Deux listes distinctes :
  //   _ranked      = VRAIES exclusivités (aucun concurrent trouvé) → seule liste qui garde ce nom.
  //   _marqueOnly  = noms de marque seulement → section séparée, jamais numérotée comme un "Top".
  const _ranked=_allRanked.filter(it=>it.verdict!=='differenciant');
  const _marqueOnly=_allRanked.filter(it=>it.verdict==='differenciant');
  const top10=_ranked.slice(0,TOP);
  const rest=_ranked.slice(TOP);
  // Le compteur affiché DOIT correspondre exactement à ce qui est listé (top10+rest) — sinon on
  // annonce un total qui inclut des fragments de bruit OCR écartés par _isJunkExcl, jamais montrés.
  const total=_ranked.length;

  const _why=it=>{ const n=(it.verdict_note||'').trim();
    return n||"Aucun équivalent trouvé chez les 6 concurrents (grille publiée + recherche web) — plausible, non certifié."; };
  const _exclRow=(item,i)=>{
    const clr=AXE_C[item.axe_id]||'#6B7280'; const ico=AXE_I[item.axe_id]||'◆';
    const ctx=_itemCtx(item); const prix=_prixTag(item); const lib=_itemLib(item);
    return`<div style="padding:7px 10px;margin-bottom:4px;background:#fff;border-radius:8px;border:1px solid #F1F5F9">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font:700 13px var(--sans);color:#CBD5E1;min-width:20px;text-align:right">${i+1}</span>
        <span style="flex:1;font:600 12px var(--sans);color:#1E293B">${item.name||lib}</span>
        <span style="font:700 8px var(--sans);background:#16A34A22;color:#15803D;border-radius:10px;padding:2px 7px;white-space:nowrap;flex-shrink:0">✅ sans équivalent</span>${prix}
        <span style="font:500 10px var(--sans);padding:2px 8px;background:${clr}18;color:${clr};border-radius:12px;white-space:nowrap">${ico} ${item.axe_label}</span>
      </div>
      <div style="margin-top:3px;padding-left:30px;font:400 10px var(--sans);color:#64748B;line-height:1.5">
        ${ctx?ctx+' · ':''}<b style="color:#15803D">✅ Pourquoi aucun concurrent équivalent :</b> ${_why(item)}
      </div>
      ${_justifBox(_justifFor(lib))}
    </div>`;
  };
  // Ligne compacte pour la section « noms de marque » (pas une exclusivité) — volontairement SANS
  // numérotation de classement (1,2,3…) pour ne jamais donner l'impression d'un "Top" à valoriser.
  const _marqueRow=item=>{
    const clr=AXE_C[item.axe_id]||'#6B7280'; const ico=AXE_I[item.axe_id]||'◆';
    const ctx=_itemCtx(item); const prix=_prixTag(item); const lib=_itemLib(item);
    return`<div style="padding:7px 10px;margin-bottom:4px;background:#fff;border-radius:8px;border:1px solid #F1F5F9">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="flex:1;font:600 12px var(--sans);color:#1E293B">${item.name||lib}</span>
        <span style="font:700 8px var(--sans);background:#FB923C22;color:#C2410C;border-radius:10px;padding:2px 7px;white-space:nowrap;flex-shrink:0">🏷️ nom de marque</span>${prix}
        <span style="font:500 10px var(--sans);padding:2px 8px;background:${clr}18;color:${clr};border-radius:12px;white-space:nowrap">${ico} ${item.axe_label}</span>
      </div>
      <div style="margin-top:3px;padding-left:2px;font:400 10px var(--sans);color:#64748B;line-height:1.5">
        ${ctx?ctx+' · ':''}<b style="color:#C2410C">🏷️ Pourquoi ce n'est pas une exclusivité :</b> ${_why(item)}
      </div>
    </div>`;
  };

  const summary=`<div style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:#F3F0FF;border-radius:10px;border:1px solid #C4B5FD;margin-bottom:14px">
    <div style="font:800 40px var(--sans);color:var(--accent-2);line-height:1">${total}</div>
    <div>
      <div style="font:700 13px var(--sans);color:#1E293B">${total?'exclusivités SGCI validées':'aucune exclusivité de fonction validée'}</div>
      <div style="font:400 10.5px var(--sans);color:var(--faint);margin-top:2px">Absentes de BICICI, SIB, BACI, NSIA, ECOBANK, BNI — vérifié web</div>
      <div style="font:400 9.5px var(--sans);color:var(--faint);margin-top:3px;font-style:italic">Ce nombre peut légèrement varier d'une période à l'autre selon la qualité d'extraction des grilles tarifaires concurrentes (pas nécessairement un changement réel de catalogue).</div>
    </div>
  </div>`;

  // ── Top (jusqu'à 15) — UNIQUEMENT les vraies exclusivités, jamais les noms de marque ──
  const top10html=total?`<div style="margin-bottom:10px">
    <div style="font:700 11px var(--sans);color:var(--accent-2);letter-spacing:.05em;text-transform:uppercase;margin-bottom:8px">Top ${Math.min(TOP,_ranked.length)} — Exclusivités les plus distinctives</div>
    ${top10.map((it,i)=>_exclRow(it,i)).join('')}
  </div>`:'';
  // ── Section séparée, distincte visuellement : produits à nom de marque (PAS des exclusivités) ──
  const marqueHtml=_marqueOnly.length?`<div style="margin:14px 0 10px;padding-top:12px;border-top:1px dashed var(--line)">
    <div style="font:700 11px var(--sans);color:#C2410C;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px">Produits à nom de marque — PAS des exclusivités (${_marqueOnly.length})</div>
    <div style="font:400 10.5px/1.6 var(--sans);color:var(--faint);margin-bottom:8px">Des produits SGCI qui ONT l'air uniques à cause de leur nom (ex. PACK DIASPORA), mais dont la fonction existe déjà chez un concurrent sous un autre nom (BICICI : « Offre Diaspora », Ecobank : « Ecobank Diaspora »). Même service, nom différent — donc pas un vrai avantage : à ne jamais présenter comme une exclusivité.</div>
    ${_marqueOnly.slice(0,10).map(it=>_marqueRow(it)).join('')}
  </div>`:'';

  // ── Analyse GROUNDED (la route renvoie analyse vide → synthèse depuis les verdicts validés web) ──
  // Dérivés de _ranked (pas des totaux bruts du backend) pour que la somme colle EXACTEMENT
  // au nombre affiché et à la liste visible (le bruit OCR déjà écarté ne doit pas être compté).
  const _nse=_ranked.length;
  const _ndiff=_marqueOnly.length;
  const _seNames=_ranked.slice(0,3).map(it=>it.name||_itemLib(it));
  const _llmTxt=(d.analyse_llm||'').trim();
  const iaCommentary=_llmTxt
    ? `<div style="margin-bottom:14px;padding:11px 13px;background:#F8F7FF;border-radius:10px;border:1px solid #E0E7FF">
    <div style="font:700 10px var(--sans);color:var(--accent-2);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px">🤖 Analyse — pourquoi ces services sont distinctifs</div>
    <div style="font:400 11px/1.65 var(--sans);color:var(--ink)">${_fmtAnalyse(_llmTxt)}</div>
  </div>`
    : `<div style="margin-bottom:14px;padding:11px 13px;background:#F8F7FF;border-radius:10px;border:1px solid #E0E7FF">
    <div style="font:700 10px var(--sans);color:var(--accent-2);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px">◆ Analyse — pourquoi ces services sont distinctifs <span style="opacity:.6;text-transform:none;letter-spacing:0">(calcul automatique, pas IA)</span></div>
    <div style="font:400 11px/1.65 var(--sans);color:var(--ink)">
      ${total?`<b style="color:#15803D">${total} vraie${total>1?'s':''} exclusivité${total>1?'s':''}</b> validée${total>1?'s':''} par l'Agent Web (aucun concurrent trouvé, grille publiée <b>+ recherche web</b> ; plausible, non certifié).`
        :`<b style="color:#C2410C">Aucune vraie exclusivité de fonction</b> trouvée pour SGCI sur ce marché.`}
      ${_ndiff?` Par ailleurs, <b style="color:#C2410C">${_ndiff} produit${_ndiff>1?'s':''} SGCI</b> porte${_ndiff>1?'nt':''} un nom de marque propre mais existe${_ndiff>1?'nt':''} déjà chez un concurrent sous un autre nom (ex. PACK DIASPORA) — à ne jamais présenter comme un avantage.`:''}
      ${_seNames.length?`<br>Les plus parlants : <b>${_seNames.join('</b>, <b>')}</b>.`:''}
      <br><span style="color:var(--faint)">La raison précise de chaque service est indiquée sous son nom (verdict + source web).</span>
    </div>
  </div>`;
  // (ancien rendu redondant « par axe » retiré — le Top + « voir les autres » suffisent, sans répétition)
  const emptySection=empty.length?`<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:5px">${empty.map(([id,axe])=>`<span style="padding:2px 8px;border-radius:12px;background:var(--bg-raise);font:400 10px var(--sans);color:var(--faint)">${AXE_I[id]||'◆'} ${axe.axe_label}</span>`).join('')}</div>`:'';

  // « Voir les autres » UNIQUEMENT s'il y a plus que le Top (sinon tout est déjà affiché → zéro redondance)
  const detailSection=`${rest.length?`<details style="margin-top:6px">
      <summary style="cursor:pointer;font:700 11px var(--sans);color:var(--accent-2);padding:8px 4px;list-style:none">▸ Voir les ${rest.length} autres exclusivités</summary>
      <div style="margin-top:8px">${rest.map((it,i)=>_exclRow(it,TOP+i)).join('')}</div>
    </details>`:''}
    ${empty.length?`<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font:400 10.5px var(--sans);color:var(--faint)">Axes BCEAO sans exclusivité SGCI (couverts par les concurrents) : ${emptySection}</div>`:''}`;

  // Méthodo « 🏷️ marque / ✅ sans équivalent » → déplacée dans le Glossaire CB (plus claire, plus concise).
  // PAS de sélecteur de banque ICI : cette carte est « Ce que SGCI a seul » — une exclusivité
  // SGCI ne peut pas varier selon une autre banque choisie, le filtre n'avait aucun sens (retiré
  // le 2026-07-08, les libellés étaient d'ailleurs restés figés sur « SGCI » quoi qu'on sélectionne).
  // Ordre : compteur · ANALYSE (pourquoi) · Top 15 (avec raison par item) · voir les autres si >15.
  return summary+iaCommentary+top10html+detailSection+marqueHtml;
}

// ── Q4 : enrichissement LLM async ────────────────────────────────────────────
async function _fireQ4LLM(){
  const payload=window._q4LlmPayload;
  const div=document.getElementById('cb-q4-llm');
  if(!payload||!div||div.dataset.loaded==='1')return;
  const pfx=_llmPfx;
  try{
    const res=await fetch('/api/cb_q4_llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    if(d.analyse){div.dataset.loaded='1';div.innerHTML=pfx+_fmtAnalyse(d.analyse);}
    else{div.innerHTML='';}
    _showStaleBadge('cb-q4-llm-stale-badge', {stale:d.stale, generated_at:d.generated_at});
  }catch(e){div.innerHTML='';}
}

// ── Q5 : enrichissement LLM async ────────────────────────────────────────────
async function _fireQ5LLM(){
  // Auto-charge la première banque concurrente
  const firstBank=CB_BANK_ORDER.find(b=>b!=='SGCI');
  if(firstBank)_q5BankFilter(firstBank);
}

function _buildQ5AxesHTML(d,banque){
  const axes=d.axes||{};
  const AXE_C={'1':'#7F77DD','2':'#378ADD','3':'#1D9E75','4':'#FF9800','5':'#E91E63','6':'#06B6D4','7':'#8B5CF6','8':'#6B7280'};
  const AXE_I={'1':'📦','2':'💳','3':'💰','4':'🏦','5':'🛡','6':'📱','7':'📈','8':'🔧'};
  const active=Object.entries(axes).filter(([,v])=>v.gaps&&v.gaps.length>0)
    .sort((a,b)=>b[1].gaps.length-a[1].gaps.length);
  if(!active.length)return`<div style="padding:20px;text-align:center;color:var(--muted);font-size:12px">Aucun gap confirmé — SGCI couvre l'essentiel de l'offre de ${banque}.</div>`;

  // ── Aplatir pour le Top 10 ──
  const allItems=[];
  active.forEach(([id,axe])=>{
    axe.gaps.forEach(it=>allItems.push({...it,name:_itemLib(it),axe_id:id,axe_label:axe.axe_label}));
  });
  // PRIORITÉ (les "meilleurs"/plus stratégiques d'abord), bruit OCR exclu :
  //  1) gratuit chez le concurrent (fuite clients = urgent) · 2) digital nommé · 3) produit nommé · 4) prix.
  const _JUNK_GAP=/^(titulaire|pour tout montant|par s[ée]rie|montant (compris|sup|inf)|de \d|co[uû]t|autres? types?|frais$|pour les|y compris)/i;
  // Garde-fou en plus côté front (défense en profondeur, cf. fix backend 2026-07-17, renforcé
  // 2026-07-20 pour le bruit d'extraction PDF SIB : numérotation de section, guillemets coupés,
  // paliers de prix tronqués, bavures de pied de page/colonne d'en-tête).
  const _JUNK_GAP_LEAK=/→|\*\*|⚠|occurrence|param[eè]tre technique|inf[ée]rieur\s*[àa]|sup[ée]rieur\s*(ou\s*[ée]gal)?\s*[àa]|^\d[\d\s]*(fcfa)?\s*(à|-|—)\s*\d|^\d+[.,:]\s*\d|^[«»"']|\d[\d\s]*\s*(à|-|—)\s*\d+\s*$|\bwww\.|\.ci\b|actualis[ée]e? au|\s(taux|frais|tarif)$|\d\s*\/\s*$|\bmontants?\s+indiqu[ée]s?\b|^client\s+\w+$|:\s*\d[\d.,\s]*\d\s*$|:\s*\d\s*$|&lt;|&gt;/i;
  // Texte OCR éclaté lettre par lettre (ex. « C au o t m o m ris is ») : si plus d'un tiers des
  // mots font 1-2 caractères sur au moins 4 mots, ce n'est pas du texte lisible.
  const _isScrambled=l=>{const t=l.split(/\s+/).filter(Boolean); return t.length>=4 && (t.filter(w=>w.length<=2).length/t.length)>0.35;};
  const _isJunkGap=it=>{const l=(_itemLib(it)||'').trim(); return l.length<14 || _JUNK_GAP.test(l) || _JUNK_GAP_LEAK.test(l) || _isScrambled(l) || /^[a-zàâçéèêëîïôùû(]/.test(l) || _ocrSpacingCorrupt(l);};
  const _prioScore=it=>{
    const l=(_itemLib(it)||'').toLowerCase(); const m=+(it.montant||0); const px=m>0?Math.log10(m+1):0;
    if(it.est_gratuit) return 500+px;                                                       // gratuit concurrent = priorité absolue
    if(/connect|mobile|en ligne|application|sans carte|digital|web|mybusiness/.test(l)) return 400+px; // digital nommé
    if(/\b(pack|soge|yaconfort|quietis|zenith|diaspora|prestibad|elite|infinite|bourse|opcvm|assurance|carte)\b/.test(l)) return 300+px;
    if((it.type_valeur||'').includes('TAUX')) return 100+px;
    return 200+px;
  };
  const _ranked=allItems.filter(it=>!_isJunkGap(it)).sort((a,b)=>_prioScore(b)-_prioScore(a));
  const TOP=10;
  const top10=_ranked.slice(0,TOP);
  const rest=_ranked.slice(TOP);
  // Le compteur affiché DOIT correspondre à ce qui est réellement listé (idem fix Exclusivités).
  const total=_ranked.length;

  // Raison GROUNDED du manque — VARIÉE (plus de phrase unique répétée) : on s'appuie sur
  // l'axe BCEAO réel, le prix réel, le caractère gratuit, le canal digital. Aucune invention.
  const _AXE_WHY={
    '1':`pack / offre groupée non proposé par SGCI`,
    '2':`gamme de carte non couverte par SGCI`,
    '3':`produit d'épargne absent du catalogue SGCI`,
    '4':`solution de financement absente chez SGCI`,
    '5':`assurance / bancassurance non proposée par SGCI`,
    '6':`service digital / canal à distance absent chez SGCI`,
    '7':`produit de marché (bourse, OPCVM) absent chez SGCI`,
    '8':`service annexe non couvert par SGCI`,
  };
  const _whyGap=it=>{
    // Si l'AGENT WEB a validé ce manque : on montre À QUOI ÇA SERT (rôle réel, recherché en
    // ligne) + le fait que SGCI ne le propose pas (vérifié). C'est le vrai « manque ».
    if(it.web_role){
      return `<b style="color:var(--red)">À quoi ça sert :</b> ${it.web_role} `
           + `<span style="color:#15803D;font-weight:700">✓ vérifié web — SGCI ne le propose pas.</span>`;
    }
    const m=+(it.montant||0), px=m>0?`${m.toLocaleString('fr-FR')} F`:'';
    if(it.est_gratuit)
      return `${banque} le propose <b style="color:var(--red)">gratuitement</b> — atout prix que SGCI n'a pas (fuite possible des clients sensibles au tarif).`;
    const lib=(_itemLib(it)||'').toLowerCase();
    if(m>=50000)
      return `Segment <b>haut de gamme</b> (${px} chez ${banque}) absent du catalogue SGCI — clientèle premium à capter.`;
    if(/connect|mobile|en ligne|application|digital|web|sans carte|mybusiness/.test(lib))
      return `Canal <b>digital</b> proposé par ${banque}${px?` (${px})`:''}, absent chez SGCI — enjeu d'expérience client.`;
    const base=_AXE_WHY[it.axe_id]||`service absent du catalogue SGCI`;
    return `${base}${px?` — ${px} chez ${banque}`:` — proposé par ${banque}`}.`;
  };
  const _gapRow=(item,i)=>{
    const clr=AXE_C[item.axe_id]||'#6B7280'; const ico=AXE_I[item.axe_id]||'◆';
    const ctx=_itemCtx(item); const prix=_prixTag(item); const lib=_itemLib(item);
    return`<div style="padding:7px 10px;margin-bottom:4px;background:#fff;border-radius:8px;border:1px solid #FEE2E2">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font:700 13px var(--sans);color:#CBD5E1;min-width:20px;text-align:right">${i+1}</span>
        <span style="flex:1;font:600 12px var(--sans);color:#1E293B">${item.name||lib}</span>
        ${prix}
        <span style="font:500 10px var(--sans);padding:2px 8px;background:${clr}18;color:${clr};border-radius:12px;white-space:nowrap">${ico} ${item.axe_label}</span>
      </div>
      <div style="margin-top:3px;padding-left:30px;font:400 10px var(--sans);color:#64748B;line-height:1.5">
        ${ctx?ctx+' · ':''}<b style="color:var(--red)">Pourquoi un manque :</b> ${_whyGap(item)}
      </div>
      ${_justifBox(_justifFor(lib))}
    </div>`;
  };

  const summary=`<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:#FFF1F2;border-radius:8px;border:1px solid #FECACA;margin-bottom:14px">
    <div style="font:800 36px var(--sans);color:var(--red);line-height:1">${total}</div>
    <div>
      <div style="font:600 12.5px var(--sans);color:#1E293B">services de ${banque} absents chez SGCI</div>
      <div style="font:400 10px var(--sans);color:var(--faint);margin-top:2px">Validés sémantiquement — vrais manques, pas des variantes de nommage</div>
    </div>
  </div>`;

  // ── Top (jusqu'à 15) — chaque ligne porte sa RAISON (grounded) ──
  const top10html=`<div style="margin-bottom:10px">
    <div style="font:700 11px var(--sans);color:var(--red);letter-spacing:.05em;text-transform:uppercase;margin-bottom:8px">Top ${Math.min(TOP,_ranked.length)} — Priorités stratégiques pour SGCI <span style="font-weight:500;text-transform:none;color:var(--faint)">· gratuit & services nommés priorisés · bruit OCR exclu</span></div>
    ${top10.map((it,i)=>_gapRow(it,i)).join('')}
  </div>`;

  // ── Analyse GROUNDED (synthèse depuis les données, sans LLM) ──
  const _nGrat=_ranked.filter(it=>it.est_gratuit).length;
  const iaCommentary5=`<div style="margin-bottom:14px;padding:11px 13px;background:#FFF5F5;border-radius:10px;border:1px solid #FECACA">
    <div style="font:700 10px var(--sans);color:var(--red);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px">◆ Analyse — pourquoi ce sont des manques <span style="opacity:.6;text-transform:none;letter-spacing:0">(calcul automatique, pas IA)</span></div>
    <div style="font:400 11px/1.65 var(--sans);color:#1E293B">
      <b>${total}</b> services proposés par <b>${banque}</b> et <b>absents</b> du catalogue SGCI (validés sémantiquement — pas des variantes de nommage).
      ${_nGrat?` Dont <b style="color:var(--red)">${_nGrat} GRATUITS</b> chez ${banque} : les plus urgents (fuite des clients sensibles au prix).`:''}
      Les autres sont des <b>pistes d'enrichissement de l'offre</b>. La raison de chaque service figure sous son nom.
    </div>
  </div>`;

  // « Voir les autres » UNIQUEMENT s'il y a plus que le Top (sinon tout est déjà affiché → zéro redondance)
  const detailSection=`${rest.length?`<details style="margin-top:6px">
      <summary style="cursor:pointer;font:700 11px var(--sans);color:var(--red);padding:8px 4px;list-style:none">▸ Voir les ${rest.length} autres manques</summary>
      <div style="margin-top:8px">${rest.map((it,i)=>_gapRow(it,TOP+i)).join('')}</div>
    </details>`:''}`;

  return summary+iaCommentary5+top10html+detailSection;
}

// ── Q6 : enrichissement LLM async ────────────────────────────────────────────
function _fireQ6LLM(){
  // BLOC1/BLOC2/VERDICT (ancienne analyse LLM « où SGCI est compétitive/vulnérable ») SUPPRIMÉ :
  // il était NAÏF (classait les barrières de sortie comme « vulnérables », les frais punitifs comme
  // « compétitifs ») et se basait sur des médianes polluées par des valeurs aberrantes. L'analyse prix
  // ACTIONNABLE et fiable est désormais le RÉCAP ACTIONS (garde-fous anti-aberrations, barrières de
  // sortie, PNB, sources web). On remplace le bloc par un renvoi — plus de double analyse contradictoire.
  const priceDiv=document.getElementById('cb-q6-price-llm');
  if(priceDiv){
    priceDiv.innerHTML=`<div style="font:500 12px/1.6 var(--sans);color:#1E293B;padding:10px 12px;background:#F8FAFC;border-radius:8px;border:1px solid var(--line)">
      <b style="color:var(--accent-2,#FF9800)">Positionnement prix actionnable →</b> l'analyse « <b>où augmenter / baisser / ne pas toucher</b> » — avec garde-fous contre les valeurs aberrantes, protection des barrières de sortie et du PNB, et <b>sources web</b> par décision — est dans le tableau ci-dessus, onglet <b>« Recommandation »</b>. Une seule source de vérité, cohérente.
    </div>`;
  }
}

// ── Q2 : Dynamique d'innovation marché 2024–2026 ──────────────────────────────
// ── Innovation (CB) × Moyens financiers (EF) — classement à double barre, lisible ──
async function _renderInnovFinanceMatrix(){
  const el=document.getElementById('cb-q2-matrix');
  if(!el||el.dataset.done==='1')return;
  try{
    const r=await fetch(`/api/cb_innovation_vs_finance?segment=${encodeURIComponent(CB_SEG)}`);
    const all=await r.json();
    const rows=(Array.isArray(all)?all:[]).filter(d=>d.resultat_net!=null);
    if(rows.length<2)return;
    const maxI=Math.max(...rows.map(d=>d.innovation),1);
    const maxR=Math.max(...rows.map(d=>d.resultat_net),1);
    const sgci=rows.find(d=>d.banque==='SGCI');
    const refY=sgci?sgci.innovation:0;
    const sorted=[...rows].sort((a,b)=>b.innovation-a.innovation);
    const fmtR=v=>v>=1000?Math.round(v/1000)+'k':Math.round(v);
    const bar=(pct,c)=>`<div style="flex:1;height:11px;background:#eef2f7;border-radius:6px;overflow:hidden;min-width:40px"><div style="height:100%;width:${Math.max(pct,2)}%;background:${c};border-radius:6px"></div></div>`;
    const profil=d=>{
      if(d.banque==='SGCI')return{t:'★ Référence',c:'#FF9800'};
      if(d.innovation>refY)return{t:'⚡ Plus offensif que SGCI',c:'#dc2626'};
      if(d.innovation>0)return{t:'≈ comparable',c:'#64748B'};
      return{t:'○ En retrait',c:'#94A3B8'};
    };
    const GC='1fr', cols=`22px 86px ${GC} ${GC} 158px`;
    const head=`<div style="display:grid;grid-template-columns:${cols};gap:10px;padding:0 8px 6px;font:700 9px var(--sans);color:var(--faint);text-transform:uppercase;letter-spacing:.05em">
      <span>#</span><span>Banque</span><span>🟢 Nouveautés depuis 2024</span><span>🔵 Moyens — Résultat Net</span><span style="text-align:right">Profil vs SGCI</span></div>`;
    const body=sorted.map((d,i)=>{
      const isS=d.banque==='SGCI', p=profil(d);
      return`<div style="display:grid;grid-template-columns:${cols};align-items:center;gap:10px;padding:8px;border-radius:9px;margin-bottom:3px;background:${isS?'color-mix(in srgb,#FF9800 10%,transparent)':'var(--bg-raise,#f8fafc)'};border-left:${isS?'3px solid #FF9800':'3px solid transparent'}">
        <span style="font:700 11px var(--mono);color:var(--faint)">${i+1}</span>
        <span style="font:${isS?800:600} 12.5px var(--sans);color:${isS?'#FF9800':'var(--ink)'}">${isS?'★ SGCI':d.banque}</span>
        <div style="display:flex;align-items:center;gap:8px">${bar(d.innovation/maxI*100,'#1D9E75')}<span style="font:700 12px var(--mono);color:#159e6b;min-width:30px">+${d.innovation}</span></div>
        <div style="display:flex;align-items:center;gap:8px">${bar(d.resultat_net/maxR*100,'#378ADD')}<span style="font:700 12px var(--mono);color:#2f74c0;min-width:38px">${fmtR(d.resultat_net)}</span></div>
        <span style="font:700 10.5px var(--sans);color:${p.c};text-align:right">${p.t}</span>
      </div>`;
    }).join('');
    el.innerHTML=head+body;
    // Note dynamique — relative à SGCI
    const rnSorted=[...rows].sort((a,b)=>b.resultat_net-a.resultat_net);
    const sgciRnRank=sgci?rnSorted.findIndex(d=>d.banque==='SGCI')+1:0;
    const plusInnov=rows.filter(d=>d.banque!=='SGCI'&&d.innovation>refY).sort((a,b)=>b.innovation-a.innovation);
    const note=document.getElementById('cb-q2-matrix-note');
    if(note&&sgci){
      const rnTxt=sgciRnRank===1?'le <b>plus haut Résultat Net du marché</b>':`<b>#${sgciRnRank}/${rows.length}</b> en Résultat Net`;
      note.innerHTML=`<div style="font:500 12px/1.6 var(--sans);color:#1E293B;padding:8px 10px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">`
        +`<span style="color:var(--accent-2,#FF9800);font-weight:700">Lecture :</span> SGCI = +${sgci.innovation} nouveautés pour ${rnTxt} (${Math.round(sgci.resultat_net).toLocaleString('fr-FR')}).`
        +(plusInnov.length
            ?` <span style="color:#dc2626;font-weight:700">${plusInnov.map(d=>d.banque).join(', ')} innovent plus que SGCI</span> avec des moyens financiers <b>inférieurs</b> → SGCI a les moyens, pas le rythme.`
            :` Aucun concurrent n'innove plus vite que SGCI.`)
        +`</div>`;
    }
    el.dataset.done='1';
  }catch(e){}
}

// ── Rattrapage vs Dépassement : les concurrents copient-ils SGCI ou la dépassent-ils ? ──
async function _renderRattrapage(){
  const el=document.getElementById('cb-q2-rattrapage');
  if(!el||el.dataset.done==='1')return;
  const tk=_cbToken;
  try{
    const r=await fetch(`/api/cb_rattrapage_depassement?segment=${encodeURIComponent(CB_SEG)}`);
    const data=(await r.json()).filter(d=>d.total>0);
    if(!_cbAlive(tk))return;
    if(!data.length){el.innerHTML='<div style="color:var(--faint);font:500 11px var(--sans);padding:6px 0">Aucune nouveauté concurrente sur la période.</div>';el.dataset.done='1';return;}
    const maxT=Math.max(...data.map(d=>d.total),1);
    const body=data.map(d=>{
      const rW=d.rattrapage/maxT*100, dW=d.depassement/maxT*100;
      return`<div style="display:grid;grid-template-columns:118px 1fr 132px;align-items:center;gap:10px;padding:6px 4px">
        <span><span style="font:700 12px var(--sans);color:var(--ink)">${d.banque}</span> <span style="font:600 10px var(--mono);color:var(--faint)">${d.taux}%</span></span>
        <div style="display:flex;height:17px;border-radius:5px;overflow:hidden;background:#eef2f7" title="${d.total} nouveautés">
          <div style="width:${rW}%;background:#94A3B8"></div><div style="width:${dW}%;background:#dc2626"></div>
        </div>
        <span style="font:600 11px var(--mono);text-align:right"><b style="color:#dc2626">${d.depassement} dépass.</b> · <span style="color:#64748B">${d.rattrapage} rattr.</span></span>
      </div>`;
    }).join('');
    const totR=data.reduce((s,d)=>s+d.rattrapage,0), totD=data.reduce((s,d)=>s+d.depassement,0);
    const topD=[...data].sort((a,b)=>b.depassement-a.depassement)[0];
    el.innerHTML=body+`<div style="margin-top:10px;font:500 12px/1.55 var(--sans);color:var(--ink);padding:8px 10px;background:var(--bg-raise,#f8fafc);border-radius:8px;border:1px solid var(--line)">
      <span style="font-weight:700">Lecture :</span> sur les nouveautés concurrentes, <b style="color:#64748B">${totR}</b> ne font que <b>rattraper</b> des services déjà offerts par SGCI, contre <b style="color:#dc2626">${totD}</b> qui <b>dépassent</b> SGCI (services qu'elle n'a pas).${topD&&topD.depassement>0?` <b>${topD.banque}</b> creuse le plus d'avance (<b style="color:#dc2626">+${topD.depassement}</b> services absents chez SGCI).`:''}</div>`;
    el.dataset.done='1';
  }catch(e){}
}

function _renderQ2(data){
  // data = payload Q1 : {banques, evolution, evolutions_all?}
  // Innovation = nouveaux produits + repricing + nouveaux segments + écosystème
  const ev=(data&&data.evolution)||{};
  const sgciApp=ev.apparus||[];
  const sgciDis=ev.disparus||[];
  const sgciRep=ev.reprices||[];
  const evAll=data&&data.evolutions_all?data.evolutions_all:null;
  const evCross=data&&data.evolutions_cross?data.evolutions_cross:null;
  const evOther=evCross?evCross.data:null;
  const otherSeg=evCross?evCross.segment:null;

  const nApp=sgciApp.length,nDis=sgciDis.length,nRep=sgciRep.length;

  if(!nApp&&!evAll&&!nRep)
    return _v3sec('2','#1D9E75',"Innovation marché 2024–2026",'Données Q1 requises…')+
           _v3ins('Rechargez si ce message persiste.');

  // ── Classifiers (partagés A→D) ─────────────────────────────────────────────
  const _iSec=r=>((r.section||'')+'').split('.')[0];
  const _iLib=r=>(r.libelle||'').toLowerCase();
  const _isDig=r=>_iSec(r)==='7'||['connect','mobile','digital','e-','mybank','sogecommerce','banque en ligne'].some(k=>_iLib(r).includes(k));
  const _isIntl=r=>_iSec(r)==='8'||['international','communautaire','swift','moneygram'].some(k=>_iLib(r).includes(k));
  const _isCorp=r=>_iSec(r)==='9'||['entreprise','corporate','pme','cnps','salaire','mybusiness'].some(k=>_iLib(r).includes(k));
  const _isEco=r=>['sogeprimo','package','mybusiness','my business','bundle','vie domes'].some(k=>_iLib(r).includes(k));
  const _isEp=r=>_iSec(r)==='2'||['épargne','placement','livret','terme'].some(k=>_iLib(r).includes(k));
  const _isPmt=r=>_iSec(r)==='4'||['paiement','virement','carte','monétique'].some(k=>_iLib(r).includes(k));

  const _typeOf=r=>{
    if(r.est_gratuit&&_isDig(r))return{t:'Différenciation digitale gratuite',c:'#1D9E75',i:'★'};
    if(r.est_gratuit)return{t:'Pricing libre — gratuit',c:'#1D9E75',i:'★'};
    if(_isEco(r))return{t:'Innovation écosystème',c:'#FF9800',i:'◈'};
    if(_isDig(r))return{t:'Accélération digitale',c:'#378ADD',i:'◆'};
    if(_isIntl(r))return{t:'International',c:'#7F77DD',i:'◉'};
    if(_isCorp(r))return{t:'Corporate/PME',c:'#FF9800',i:'▲'};
    if(_isEp(r))return{t:'Épargne',c:'#5C6BC0',i:'●'};
    if(_isPmt(r))return{t:'Paiements',c:'#E91E63',i:'■'};
    return{t:'Extension catalogue',c:'#78909C',i:'○'};
  };


  // ── A : TAUX D'INNOVATION — barre normalisée par catalogue ────────────────
  // Taux = nouveaux services ÷ catalogue total → comparable entre banques
  const _n1=b=>(window._q1RankRows||[]).find(r=>r.b===b)?.n1||null;
  const sgciN1=_n1('SGCI')||Math.max(nApp+100,210);
  const sgciRate=Math.round(nApp/sgciN1*100);

  const allRanks=[
    {b:'SGCI',nApp,nDis,apparus:sgciApp,n1:sgciN1},
    ...(evAll?CB_BANK_ORDER.filter(b=>b!=='SGCI').map(b=>{
      const n1=_n1(b); const na=evAll[b]?.nApp||0;
      return{b,nApp:na,nDis:evAll[b]?.nDis||0,apparus:evAll[b]?.apparus||[],n1,rate:n1?Math.round(na/n1*100):null};
    }):[])
  ].map(r=>({...r,rate:r.rate!==undefined?r.rate:(r.n1?Math.round(r.nApp/r.n1*100):null)}))
   .sort((a,b2)=>(b2.rate??-1)-(a.rate??-1));

  const mktAvg=allRanks.filter(r=>r.rate!=null).length
    ?Math.round(allRanks.filter(r=>r.rate!=null).reduce((s,r)=>s+r.rate,0)/allRanks.filter(r=>r.rate!=null).length):0;
  const maxRate=Math.max(...allRanks.map(r=>r.rate||0),1);
  const sgciRankByRate=allRanks.findIndex(r=>r.b==='SGCI')+1;
  const topBankRate=allRanks[0];

  const rateHtml=allRanks.map(r=>{
    const isSG=r.b==='SGCI';
    const rate=r.rate;
    const pct=rate!=null?Math.round(rate/maxRate*100):0;
    const col=isSG?'#1D9E75':rate!=null&&rate>mktAvg?'#FF9800':'#94A3B8';
    const tag=!isSG&&rate!=null&&rate>mktAvg?_v3tag('▲ dessus moyenne','tgr'):'';
    return`<div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
        <span style="font:${isSG?700:500} 11px var(--sans);color:${isSG?'#1D9E75':'var(--ink)'}">${isSG?'★ SGCI':r.b} ${tag}</span>
        <span style="font:700 11px JetBrains Mono,monospace;color:${isSG?'#1D9E75':'#6B7280'}">${rate!=null?rate+'%':'—'}</span>
      </div>
      <div style="height:7px;background:#F1F5F9;border-radius:4px">
        <div style="height:100%;width:${Math.max(pct,1)}%;background:${col};border-radius:4px;transition:width .4s"></div>
      </div>
    </div>`;
  }).join('');

  // ── B : INNOVATIONS MULTI-BANQUES — panneau avec filtre banque ──────────
  const _mkInnoCard=(r,forBank)=>{
    const tp=_typeOf(r);
    const lib=r.libelle||'';
    const ctx=(r.contexte||'').replace(/\s*\|\s*/g,' › ');
    const breadcrumb=[r.section,ctx].filter(Boolean).join(' · ');
    const dk=lib.toLowerCase();
    const desc=Object.entries(_SGCI_PRODUCT_DESC).find(([k])=>dk.includes(k))?.[1]||'';
    return`<div style="padding:12px 14px;border-radius:8px;border-left:3px solid ${tp.c};background:${r.est_gratuit?'#F0FDF9':'#F8FAFC'};margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:5px">
        <div style="font:${r.est_gratuit?700:600} 12.5px var(--sans);color:#1E293B;flex:1;line-height:1.4">${tp.i} ${lib}</div>
        ${_v3tag(tp.t,r.est_gratuit?'tg':'tb')}
      </div>
      ${breadcrumb?`<div style="font:400 10.5px var(--sans);color:var(--faint);line-height:1.5;margin-bottom:${desc?5:0}px">${breadcrumb}</div>`:''}
      ${desc?`<div style="font:400 11.5px var(--sans);color:var(--ink);line-height:1.55;border-top:1px solid rgba(0,0,0,.06);padding-top:6px;margin-top:4px">${desc}</div>`:''}
    </div>`;
  };
  const _mkInnoList=(appList,bankName)=>{
    if(!appList.length)return`<div style="color:var(--faint);font-size:12px;padding:8px">Aucune innovation ${bankName} détectée sur la période.</div>`;
    // Regroupement par axe BCEAO (cohérent avec Q1) : icône + label + couleur, contexte conservé.
    const g={};
    appList.forEach(r=>{
      const k=r.axe_id!=null?(''+r.axe_id):'8';
      if(!g[k])g[k]={label:r.axe_label||'Autres Services Distinctifs',icon:r.axe_icon||'🔧',color:r.axe_color||'#6B7280',rows:[]};
      g[k].rows.push(r);
    });
    const _sc=r=>r.est_gratuit?3:(r.montant>0&&r.type_valeur!=='TAUX_%')?2:(r.type_valeur==='TAUX_%'&&r.montant!=null)?1.5:0;
    Object.values(g).forEach(v=>v.rows.sort((a,b)=>(_sc(b)-_sc(a))||((b.montant||0)-(a.montant||0))));
    const order=Object.entries(g).sort((a,b)=>b[1].rows.length-a[1].rows.length);
    // Typologie d'innovation (nature de la nouveauté) — réutilise _typeOf, 100% dynamique
    const tc={};
    appList.forEach(r=>{const t=_typeOf(r);if(!tc[t.t])tc[t.t]={n:0,c:t.c,i:t.i};tc[t.t].n++;});
    const typoChips=Object.entries(tc).sort((a,b)=>b[1].n-a[1].n).map(([t,v])=>
      `<span style="display:inline-block;padding:2px 9px;border-radius:12px;background:${v.c}1a;color:${v.c};font:700 10px var(--sans);margin:0 5px 5px 0">${v.i} ${t} · ${v.n}</span>`).join('');
    const typoStrip=`<div style="margin-bottom:10px"><div style="font:600 9px var(--sans);color:var(--faint);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Nature des nouveautés</div>${typoChips}</div>`;
    let totalRest=0;
    const html=order.map(([k,v])=>{
      const shown=v.rows.slice(0,6); const rest=v.rows.length-shown.length; totalRest+=Math.max(rest,0);
      const head=`<div style="margin:10px 0 4px;display:flex;align-items:center;gap:7px;border-bottom:1px solid var(--line);padding-bottom:3px">
        <span style="font-size:13px">${v.icon}</span>
        <span style="flex:1;font:700 11.5px var(--sans);color:${v.color}">${v.label}</span>
        <span style="font:600 9.5px var(--sans);color:var(--faint)">${v.rows.length} offre${v.rows.length>1?'s':''}</span>
      </div>`;
      const cards=shown.map(r=>_mkInnoCard(r,bankName)).join('');
      const more=rest>0?`<div style="font-size:10px;color:var(--faint);padding:1px 0 4px">… +${rest} dans ce domaine</div>`:'';
      return head+cards+more;
    }).join('');
    const moreBtn=totalRest>0?`<button onclick="document.getElementById('cb-q2-copilot-btn')?.click()" style="width:100%;margin-top:8px;padding:9px;border-radius:8px;border:1px dashed #CBD5E1;background:#F8FAFC;color:#6366F1;font:600 12px var(--sans);cursor:pointer">⊕ Approfondir — voir toutes les innovations par l'IA</button>`:'';
    return typoStrip+html+moreBtn;
  };
  const activeInno=window._q2InnoBankFilter||'SGCI';
  const allInnoBanks=[{b:'SGCI',list:sgciApp},
    ...(evAll?CB_BANK_ORDER.filter(b=>b!=='SGCI').map(b=>({b,list:evAll[b]?.apparus||[]})).filter(x=>x.list.length):[]
  )];
  const filterBtns=allInnoBanks.map(({b,list})=>`<button data-inno-btn-bank="${b}" onclick="window._q2InnoBankFilter='${b}';_q2InnoFilter('${b}')" style="padding:4px 11px;border-radius:20px;font:${b===activeInno?700:500} 11px var(--sans);cursor:pointer;transition:.15s;border:1px solid ${b===activeInno?'#1D9E75':'var(--line)'};background:${b===activeInno?'#1D9E75':'var(--bg-raise)'};color:${b===activeInno?'#fff':'var(--ink)'}">${b==='SGCI'?'★ SGCI':b} (${list.length})</button>`).join('');
  const innoPanels=allInnoBanks.map(({b,list})=>`<div id="cb-q2-inno-${b.replace(/\s+/g,'_')}" data-inno-bank="${b}" style="display:${b===activeInno?'block':'none'}">${_mkInnoList(list,b)}</div>`).join('');
  // Payload pour l'analyse LLM du panneau innovations
  window._q2InnoLlmPayload={
    segment:CB_SEG, year:CB_YEAR, sem:CB_SEM,
    sgciCount:sgciApp.length,
    banks:allInnoBanks.map(({b,list})=>({
      banque:b,
      nInno:list.length,
      nGrat:list.filter(r=>r.est_gratuit).length,
      topDomains:[...new Set(list.map(r=>r.axe_label||'').filter(Boolean))].slice(0,4)
    }))
  };

  // ── C : VEILLE CONCURRENTIELLE — 100% factuel, cross-segment ─────────────
  // Toutes les phrases sont dérivées de valeurs numériques réelles — aucune spéculation.
  const _diagnose=(bankName,appList,bankRate)=>{
    const na=appList.length;
    // Fact 1 — Focus stratégique cross-segment (calculé même si na=0)
    const crossPart=(()=>{
      if(!evOther||!otherSeg)return'';
      const nO=(evOther[bankName]||{}).nApp||0;
      const total=na+nO;
      if(total===0)return'';
      if(na===0&&nO>=3)
        return`<b>Innovation concentrée sur ${otherSeg}</b> : 0 offre nouvelle ici · ${nO} sur ${otherSeg}. Pas de menace directe sur ce segment.`;
      if(nO>na*1.5&&nO>=3)
        return`<b>Stratégie prioritairement axée sur ${otherSeg}</b> : ${nO} innovations là-bas vs ${na} ici (${Math.round(nO/total*100)}% de l'effort sur ${otherSeg}).`;
      if(na>nO*1.5&&na>=3)
        return`<b>Foyer d'innovation principalement sur ${CB_SEG}</b> : ${na} ici vs ${nO} sur ${otherSeg}.`;
      if(nO>0)
        return`Effort équilibré entre les deux segments : ${na} ${CB_SEG} · ${nO} ${otherSeg}.`;
      return'';
    })();
    if(!na)return crossPart||'Aucune innovation détectée sur ce segment.';
    // Fact 2 — Cadence vs SGCI (en points de taux, pas une conclusion)
    const rateGap=bankRate!=null&&sgciRate!=null?bankRate-sgciRate:null;
    const ratePart=rateGap!=null&&Math.abs(rateGap)>=3
      ?(rateGap>0?`Cadence d'innovation <b>${rateGap}pts au-dessus de SGCI</b> (${bankRate}% vs ${sgciRate}%).`
                :`Cadence ${Math.abs(rateGap)}pts en-dessous de SGCI (${bankRate}% vs ${sgciRate}%).`)
      :(rateGap!=null?`Cadence comparable à SGCI (${bankRate||'—'}% vs ${sgciRate||'—'}%).`:'');
    // Fact 3 — Composition observée des innovations (comptages bruts)
    const ng=appList.filter(r=>r.est_gratuit).length;
    const nd=appList.filter(r=>_isDig(r)).length;
    const nc=appList.filter(r=>_isCorp(r)).length;
    const ni=appList.filter(r=>_isIntl(r)).length;
    const ne=appList.filter(r=>_isEco(r)).length;
    const compArr=[];
    if(ng>=1)compArr.push(`${ng}/${na} gratuit${ng>1?'s':''} (${Math.round(ng/na*100)}%)`);
    if(nd>=1)compArr.push(`${nd} digital${nd>1?'es':''}`);
    if(nc>=1)compArr.push(`${nc} Corporate/PME`);
    if(ni>=1)compArr.push(`${ni} international${ni>1?'aux':''}`);
    if(ne>=1)compArr.push(`${ne} bundle${ne>1?'s':''}/éco`);
    const compPart=compArr.length?`Composition : ${compArr.join(' · ')}.`:'';
    return[crossPart,ratePart,compPart].filter(Boolean).join(' ');
  };

  const _threatLevel=appList=>{
    const ng=appList.filter(r=>r.est_gratuit).length;
    const nd=appList.filter(r=>_isDig(r)).length;
    if(!appList.length)return{lvl:'Stable',col:'#94A3B8',icon:'○'};
    if(ng>=2||(appList.length&&ng/appList.length>=0.3))return{lvl:'Menace concurrentielle',col:'#EF4444',icon:'⚠'};
    if(nd>=3||appList.length>=8)return{lvl:'Surveillance active',col:'#FF9800',icon:'▲'};
    if(appList.length>=3)return{lvl:'Surveillance légère',col:'#FF9800',icon:'●'};
    return{lvl:'Faible',col:'#1D9E75',icon:'○'};
  };

  const _activeRanks=evAll?allRanks.filter(r=>r.b!=='SGCI'&&r.nApp>0).sort((a,b2)=>(b2.rate||0)-(a.rate||0)).slice(0,5):[];
  // Stockage pour appels LLM async déclenchés après render
  window._q2LlmTargets=_activeRanks.map(r=>({
    bankName:r.b, segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM,
    period:`2024 → ${CB_YEAR} ${CB_SEM}`,
    nApp:r.nApp, rate:r.rate, sgciRate:sgciRate,
    nOther:evOther?((evOther[r.b]||{}).nApp||0):0, otherSeg:otherSeg||'',
    apparus:(r.apparus||[]).slice(0,20).map(a=>({libelle:a.libelle,section:a.section,est_gratuit:a.est_gratuit}))
  }));
  const threatsHtml=evAll
    ?_activeRanks.map(r=>{
      const th=_threatLevel(r.apparus);
      const topNames=r.apparus.slice(0,2).map(a=>{const tp=_typeOf(a);return`<span style="color:${tp.c}">${tp.i} ${a.libelle||''}</span>`;}).join('<br>');
      const diag=_diagnose(r.b,r.apparus,r.rate);
      const safeId=r.b.replace(/\s+/g,'_');
      return`<div style="padding:10px 13px;border-radius:8px;border-left:3px solid ${th.col};background:#F8FAFC;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
          <span style="font:700 12px var(--sans);color:#1E293B">${r.b}</span>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font:500 10px var(--sans);color:#64748B">taux ${r.rate!=null?r.rate+'%':'—'} · +${r.nApp} innovations</span>
            <span style="font:700 10px var(--sans);color:${th.col}">${th.icon} ${th.lvl}</span>
          </div>
        </div>
        ${topNames?`<div style="font:400 10.5px var(--sans);line-height:1.8;margin-bottom:6px">${topNames}</div>`:''}
        <div style="font:400 10.5px var(--sans);color:#64748B;line-height:1.5">${diag}</div>
        <div id="cb-q2-llm-${safeId}" style="margin-top:12px;font:400 13px var(--sans);color:var(--ink);line-height:1.7;border-top:1px solid #E2E8F0;padding-top:10px;display:none"></div>
        <div id="cb-q2-llm-${safeId}-stale-badge" style="display:none"></div>
      </div>`;
    }).join('')||'<div style="color:var(--faint);font-size:12px">Aucun concurrent actif sur la période.</div>'
    :_v3ins('Données concurrentes en chargement (~13s après démarrage).');

  // ── Verdict final — 100% calculé depuis les données réelles ───────────────
  const nGratSGCI=sgciApp.filter(r=>r.est_gratuit).length;
  const nDigSGCI=sgciApp.filter(r=>_isDig(r)).length;
  const aboveAvgBanks=evAll?allRanks.filter(r=>r.b!=='SGCI'&&(r.rate||0)>sgciRate):[];
  const gratuitThreats=evAll?allRanks.filter(r=>r.b!=='SGCI'&&r.apparus.filter(a=>a.est_gratuit).length>=2):[];

  // Données pour le LLM marché Q2 — stockées ici, déclenchées DEPUIS LE CALLER après innerHTML
  if(evAll){
    window._q2MarketPayload={
      segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM,
      sgciRank:sgciRankByRate, totalBanks:allRanks.length,
      sgciRate, mktAvg, sgciNApp:nApp, sgciNGrat:nGratSGCI,
      allBanks:allRanks.map(r=>({b:r.b,rate:r.rate,nApp:r.nApp})),
      gratuitBanks:gratuitThreats.map(r=>r.b)
    };
    // NE PAS appeler _fireQ2MarketLLM() ici — la div n'existe pas encore dans le DOM
  }

  const hdrSub=evAll
    ?`SGCI rang ${sgciRankByRate}/${allRanks.length} · taux ${sgciRate}% · ${nApp} innovations`
    :`${nApp} innovations · Comparaison marché en chargement…`;

  return`
${_v3sec('2','#1D9E75',"Innovation marché 2024–2026",hdrSub)}

<div class="row r2" style="margin-bottom:12px">
  <div class="panel">
    <div class="panel-title">
      Rythme d'innovation — rattrapage vs dépassement de SGCI${!evAll?' '+_v3tag('Chargement…','tgr'):''}
    </div>
    <div style="font:400 10.5px var(--sans);color:#64748B;line-height:1.5;margin-bottom:10px;padding:8px 10px;background:#fff7ed;border-radius:8px;border:1px solid #fed7aa">
      Chaque nouveauté concurrente est-elle <b style="color:#64748B">déjà chez SGCI</b> (gris = rattrapage) ou <b style="color:#dc2626">absente de SGCI</b> (rouge = dépassement = vraie menace) ? Classé par dépassement.
    </div>
    <div id="cb-q2-rattrapage"></div>
    <div id="cb-q2-market-llm" style="font:400 13px var(--sans);color:var(--ink);line-height:1.7;padding:14px 16px;background:var(--bg-raise);border-radius:8px;margin-top:14px;border:1px solid var(--line)"><span style="color:var(--faint);font-style:italic">${evAll?'Analyse stratégique en cours…':'Chargement des données concurrentes…'}</span></div>
    <div id="cb-q2-market-llm-stale-badge" style="display:none"></div>
  </div>
  <div class="panel">
    <div class="panel-title">Innovations par banque — catalogue comparé</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">${filterBtns}</div>
    ${innoPanels}
    <div id="cb-q2-inno-llm" style="font:400 13px var(--sans);color:#1E293B;line-height:1.7;padding:14px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #86efac;margin-top:16px"><span style="color:var(--faint);font-style:italic">${evAll?'Analyse comparative en cours…':'Chargement des données concurrentes…'}</span></div>
    <div id="cb-q2-inno-llm-stale-badge" style="display:none"></div>
  </div>
</div>

${evAll?`<div class="panel" style="margin-bottom:12px">
  <div class="panel-title">Veille concurrentielle — diagnostic par banque ${_v3tag('Analyse stratégique','tgr')}</div>
  ${threatsHtml}
</div>`:_v3ins('Données concurrentes en chargement (~13s après démarrage).')}`;

}

// ── Q3 : Exclusivités SGCI — vue par axe BCEAO ───────────────────────────────
function _renderQ3(data){
  // data = résultat SQL ; affichage rendu par _fireQ3LLM via les axes BCEAO
  return`
${_v3sec('3','#7F77DD',"Ce que SGCI a seul — Exclusivités concurrentielles","8 axes BCEAO · Validation sémantique · Segment "+CB_SEG)}
<div class="panel">
  <div class="panel-title">Exclusivités SGCI par axe BCEAO ${_v3tag('8 axes BCEAO','tpur')}</div>
  <div style="font:400 11px var(--sans);color:#64748B;line-height:1.65;margin-bottom:14px;padding:10px 12px;background:#F8F7FF;border-radius:8px;border:1px solid #C4B5FD">
    Les 8 grandes familles de services bancaires (Packages, Cartes, Épargne, Crédits, Assurances, Digital, Marchés, Autres) sont passées au crible pour ne garder que les VRAIES exclusivités SGCI — un service qui existe déjà chez un concurrent sous un autre nom n'est pas compté.
  </div>
  <div id="cb-q3-axes-content">
    <div style="padding:32px;text-align:center">
      <div style="font:400 13px var(--sans);color:var(--faint);font-style:italic">Analyse des 8 axes BCEAO en cours…</div>
      <div style="margin-top:6px;font:400 10px var(--sans);color:#CBD5E1">Première analyse : ~15 secondes · Mise en cache ensuite</div>
    </div>
  </div>
</div>`;
}

// ── Q4 : Facteur différenciant VRIST ────────────────────────────────────────
function _renderQ4(data){
  if(!Array.isArray(data)||!data.length)
    return _v3sec('4','#E91E63','Avantage concurrentiel durable — Analyse VRIST','Données insuffisantes.')+_v3ins('Données insuffisantes pour le score VRIST.');
  const n=data.length;
  const nGrat=data.filter(r=>r.est_gratuit).length;
  const secMap={};data.forEach(r=>{const s=((r.section||'0')+'').split('.')[0];secMap[s]=(secMap[s]||0)+1;});
  const nSec=Object.keys(secMap).length;
  const topSec=Object.entries(secMap).sort((a,b)=>b[1]-a[1])[0];
  const secNm={'0':'Autres','1':'Comptes','2':'Épargne','3':'Crédit','4':'Paiements','5':'Services','6':'Spéciaux','7':'Digital','8':'International','9':'Entreprises'};
  // ── SCORES VRIST — index qualitatif, chaque axe ∈ [1..10], RÈGLES LINÉAIRES TRANSPARENTES
  //    (chaque score est une fonction explicite et documentée des données réelles ; aucune
  //     constante "magique"). Les financiers peuvent reproduire chaque calcul ci-dessous.
  const q3axes=window._CB_Q3_DATA?Object.values(window._CB_Q3_DATA.axes||{}).filter(a=>a.exclusifs?.length>0):[];
  const nAxesCoverts=q3axes.length||nSec;
  const hasRegulatory=q3axes.some(a=>a.axe_label&&/assurance|march|bourse/i.test(a.axe_label));
  const _clampV=x=>Math.max(1,Math.min(10,Math.round(x)));
  // V — VALEUR : volume d'exclusivités, saturé à 50 (socle 2 + jusqu'à 8 selon le nombre).
  const V=_clampV(2 + 8*Math.min(n,50)/50);
  // R — RARETÉ : exclusivités absentes des 6 concurrents (socle 5) + bonus volume (saturé à 40).
  const R=_clampV(5 + 5*Math.min(n,40)/40);
  // I — INIMITABLE : barrière réglementaire (Assurances/Marchés = agréments AMF-UMOA → 7, sinon 4)
  //     + diversité de domaines couverts (jusqu'à +3 sur 8 axes BCEAO).
  const I=_clampV((hasRegulatory?7:4) + 3*Math.min(nAxesCoverts,8)/8);
  // S — DURABLE : étendue des sections BCEAO couvertes (nSec sur 9).
  const S=_clampV(10*nSec/9);
  // T — TRANSFORMATIF : part de gratuité dans l'offre exclusive (proxy orientation client/digital).
  const T=_clampV(3 + 7*nGrat/Math.max(n,1));
  const global=(Math.round((V+R+I+S+T)/5*10)/10).toFixed(1);
  const gcol=+global>=7?'#1D9E75':+global>=5?'#FF9800':'#E53935';
  const glabel=+global>=7?'Fort différenciateur':+global>=5?'Modéré':'Faible';
  // Top exclusivités pour le payload LLM
  const topExclusifs=q3axes.flatMap(a=>(a.exclusifs||[]).slice(0,3).map(it=>typeof it==='string'?it:it.libelle)).filter(Boolean).slice(0,10);
  // Gaps par banque depuis Q5 summary
  const q5summary=window._CB_Q5_SUMMARY||{};
  const vDefs=[
    {l:'V',nm:'Valeur',sc:V,col:'#378ADD',
     question:'Ces services créent-ils de la valeur réelle pour le client ?',
     fact:`${n} services exclusifs couvrant ${nAxesCoverts} domaines BCEAO${topExclusifs.length?` — dont ${topExclusifs.slice(0,3).join(', ')}`:''}. Offre multi-verticale unique sur le marché ivoirien.`},
    {l:'R',nm:'Rareté',sc:R,col:'#1D9E75',
     question:'Ces services sont-ils introuvables chez les 6 autres banques ?',
     fact:`${n} services absents de BICICI, SIB, BACI, NSIA, ECOBANK et BNI + ${nGrat} gratuités exclusives. Rareté confirmée par comparaison sémantique des catalogues.`},
    {l:'I',nm:'Inimitable',sc:I,col:'#7F77DD',
     question:'Ces avantages peuvent-ils être facilement copiés ?',
     fact:`${nAxesCoverts} axes BCEAO couverts${hasRegulatory?' dont Assurances et Marchés Financiers (agréments AMF-UMOA requis)':''} + réseau SG Group international = barrières réglementaires et relationnelles fortes.`},
    {l:'S',nm:'Durable',sc:S,col:'#FF9800',
     question:`Cet avantage tient-il sur 5 ans ?`,
     fact:`${nSec}/9 sections BCEAO couvertes. Produits à coûts de sortie élevés (CONNECT, MYBUSINESS, E-CNPS) créent de la fidélité structurelle.`},
    {l:'T',nm:'Transformatif',sc:T,col:'#E91E63',
     question:`Ces services transforment-ils l'expérience client ?`,
     fact:`${nGrat} gratuités exclusives + services digitaux distinctifs. Score ${T}/10 = axe d'amélioration prioritaire face à la montée des fintechs.`},
  ];
  // ── VRIST concurrents (estimation depuis Q6 — n_services + n_gratuit par banque) ──
  const k6q4=`6_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
  const d6q4=_CB_DATA_CACHE&&_CB_DATA_CACHE[k6q4];
  const concVrist=Array.isArray(d6q4)?d6q4.filter(r=>r.banque&&r.banque!=='SGCI'&&(r.n_services||0)>0)
    .sort((a,b)=>(b.n_services||0)-(a.n_services||0))
    .map((r,i,arr)=>{
      const ns=+(r.n_services||0),ng=+(r.n_gratuit||0);
      const cV=Math.min(10,Math.round(Math.sqrt(ns)*0.85));
      const cR=Math.max(1,Math.min(8,arr.length-i));
      const cI=7;
      const cS=Math.min(10,2+Math.round(ns/30));
      const cT=Math.min(10,3+Math.round(ng/Math.max(ns,1)*10));
      const cG=+((cV+cR+cI+cS+cT)/5).toFixed(1);
      return{b:r.banque,V:cV,R:cR,I:cI,S:cS,T:cT,global:cG,n_services:ns,n_gratuit:ng};
    }):[];
  window._vristBankFilter=window._vristBankFilter||'SGCI';
  window._vristSGCI={V,R,I,S,T,global:+global};
  window._vristConc=concVrist;

  const _CONC_COLS=['#378ADD','#FF9800','#1D9E75','#8B5CF6','#06B6D4','#F59E0B','#EC4899'];
  function _vristPlot(bank){
    const el=document.getElementById('cb-q4-radar');
    if(!el||!window.Plotly)return;
    const lbls=['V','R','I','S','T'];
    const traces=[{
      type:'scatterpolar',fill:'toself',name:'★ SGCI',
      mode:'markers+lines+text',
      r:[V,R,I,S,T,V],theta:[...lbls,lbls[0]],
      text:[V,R,I,S,T,''],textposition:'top center',
      textfont:{size:11,color:'#E91E63',family:'Inter,sans-serif'},
      line:{color:'#E91E63',width:2.5},fillcolor:'rgba(233,30,99,.15)',
      hovertemplate:'%{theta} : <b>%{r}</b>/10<extra>★ SGCI</extra>'
    }];
    if(bank==='TOUTES'){
      concVrist.forEach((cc,idx)=>{
        const col=_CONC_COLS[idx%_CONC_COLS.length];
        traces.push({
          type:'scatterpolar',fill:'none',name:cc.b,
          mode:'markers+lines+text',
          r:[cc.V,cc.R,cc.I,cc.S,cc.T,cc.V],theta:[...lbls,lbls[0]],
          text:[cc.V,cc.R,cc.I,cc.S,cc.T,''],textposition:'top center',
          textfont:{size:9,color:col,family:'Inter,sans-serif'},
          line:{color:col,width:1.5,dash:'dot'},
          hovertemplate:'%{theta} : <b>%{r}</b>/10<extra>'+cc.b+'</extra>'
        });
      });
    }else if(bank!=='SGCI'){
      const cc=concVrist.find(c=>c.b===bank);
      const col=_CONC_COLS[concVrist.indexOf(cc)%_CONC_COLS.length];
      if(cc)traces.push({
        type:'scatterpolar',fill:'toself',name:bank,
        mode:'markers+lines+text',
        r:[cc.V,cc.R,cc.I,cc.S,cc.T,cc.V],theta:[...lbls,lbls[0]],
        text:[cc.V,cc.R,cc.I,cc.S,cc.T,''],textposition:'top center',
        textfont:{size:10,color:col,family:'Inter,sans-serif'},
        line:{color:col,width:2},fillcolor:col.replace(')',',').replace('rgb','rgba')+'0.08)',
        hovertemplate:'%{theta} : <b>%{r}</b>/10<extra>'+bank+'</extra>'
      });
    }
    traces.push({
      type:'scatterpolar',fill:'none',name:'Seuil 5',
      r:[5,5,5,5,5,5],theta:[...lbls,lbls[0]],
      line:{color:'rgba(200,50,50,.35)',width:1.5,dash:'dot'},hoverinfo:'skip',showlegend:false
    });
    Plotly.react(el,traces,{
      polar:{
        radialaxis:{visible:true,range:[0,10],tickvals:[2,4,6,8,10],
          tickfont:{size:9,color:'#94A3B8'},gridcolor:'#E2E8F0',linecolor:'#E2E8F0',tickcolor:'#CBD5E1',fixedrange:_IS_TOUCH},
        angularaxis:{tickfont:{size:13,color:'#374151',family:'Inter,sans-serif'},linecolor:'#E2E8F0',fixedrange:_IS_TOUCH}
      },
      paper_bgcolor:'transparent',font:{family:'Inter,sans-serif',size:11,color:'#555'},
      margin:{t:20,b:20,l:28,r:28},
      legend:{font:{size:10,color:'#666'},bgcolor:'transparent',orientation:'h',y:-0.16}
    },{responsive:true,displayModeBar:false,scrollZoom:!_IS_TOUCH,staticPlot:_REAL_TOUCH});
  }
  window._vristSelectBank=b=>{
    window._vristBankFilter=b;
    _vristPlot(b);
    document.querySelectorAll('[data-vrist-btn]').forEach(btn=>{
      const on=btn.dataset.vristBtn===b;
      btn.style.background=on?'#E91E63':'#fff';
      btn.style.color=on?'#fff':'var(--ink)';
      btn.style.borderColor=on?'#E91E63':'#CBD5E1';
      btn.style.fontWeight=on?'700':'500';
    });
    // Mettre à jour le score box
    const scoreBox=document.getElementById('cb-q4-score-box');
    const dimsBox=document.getElementById('cb-q4-vdims');
    const dimsTitle=document.getElementById('cb-q4-vdims-title');
    if(scoreBox&&b==='TOUTES'){
      const rows=concVrist.map((cc,idx)=>{
        const col=_CONC_COLS[idx%_CONC_COLS.length];
        const bar=Math.round(cc.global/10*100);
        return`<div class="bar-row">
          <span class="bar-lbl" style="color:${col}">${cc.b}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${bar}%;background:${col}"></div></div>
          <span class="bar-val" style="color:${col}">${cc.global}</span>
        </div>`;
      }).join('');
      const sgciBar=Math.round(+global/10*100);
      scoreBox.innerHTML=`<div class="panel-title" style="color:#E91E63">Comparatif VRIST — Toutes banques</div>
        <div class="bar-row" style="padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:8px">
          <span class="bar-lbl" style="color:#E91E63;font-weight:800">★ SGCI</span>
          <div class="bar-track"><div class="bar-fill" style="width:${sgciBar}%;background:#E91E63"></div></div>
          <span class="bar-val" style="color:#E91E63">${global}</span>
        </div>
        ${rows}
        <div style="font:400 9px var(--sans);color:var(--faint);margin-top:8px;font-style:italic">Scores concurrents estimés depuis catalogue (indicatifs)</div>`;
      if(dimsTitle)dimsTitle.textContent='Les 5 dimensions VRIST — Vue marché';
      if(dimsBox)dimsBox.innerHTML=_renderVCards(vDefs);
    }else if(scoreBox&&b!=='SGCI'){
      const cc=concVrist.find(c=>c.b===b);
      if(cc){
        const gcol2=cc.global>=7?'var(--green)':cc.global>=5?'var(--amber)':'var(--red)';
        const glab2=cc.global>=7?'Fort différenciateur':cc.global>=5?'Modéré':'Faible';
        scoreBox.innerHTML=`<div class="panel-title">Score VRIST — ${b}</div>
          <div style="font:900 50px/1 var(--display);color:${gcol2}">${cc.global}</div>
          <div style="font:700 10px var(--sans);color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.08em">${glab2}</div>
          <div style="font:400 9.5px var(--sans);color:var(--faint);margin-top:8px">Estimé depuis catalogue (${cc.n_services} services · ${cc.n_gratuit} gratuits)</div>
          <div style="font:400 9px var(--sans);color:var(--faint);margin-top:4px;font-style:italic">Score indicatif — basé sur données catalogue</div>`;
        // Générer des dimensions pour le concurrent sélectionné
        if(dimsTitle)dimsTitle.textContent=`Les 5 dimensions VRIST — ${b}`;
        const concDefs=[
          {l:'V',nm:'Valeur',sc:cc.V,col:'#378ADD',question:'Ces services créent-ils de la valeur réelle pour le client ?',
           fact:`${cc.n_services} services au catalogue. Offre ${cc.n_services>150?'très large':'standard'} vs ${n} exclusivités SGCI.`},
          {l:'R',nm:'Rareté',sc:cc.R,col:'#1D9E75',question:'Ces services sont-ils introuvables chez les autres banques ?',
           fact:`Rang estimé #${concVrist.indexOf(cc)+1}/${concVrist.length} sur la largeur d'offre. Profil moins spécialisé que SGCI.`},
          {l:'I',nm:'Inimitable',sc:cc.I,col:'#7F77DD',question:'Ces avantages peuvent-ils être facilement copiés ?',
           fact:`Score indicatif 7/10. Capacité de réplication des avantages SGCI non documentée publiquement.`},
          {l:'S',nm:'Durable',sc:cc.S,col:'#FF9800',question:`Cet avantage tient-il sur 5 ans ?`,
           fact:`${cc.n_services} services couvrant plusieurs domaines. Présence établie sur le marché ivoirien.`},
          {l:'T',nm:'Transformatif',sc:cc.T,col:'#E91E63',question:`Ces services transforment-ils l'expérience client ?`,
           fact:`${cc.n_gratuit} services gratuits (${Math.round(cc.n_gratuit/Math.max(cc.n_services,1)*100)}% du catalogue) vs ${Math.round(nGrat/Math.max(n,1)*100)}% chez SGCI.`},
        ];
        if(dimsBox)dimsBox.innerHTML=_renderVCards(concDefs);
      }
    }else if(scoreBox){
      scoreBox.innerHTML=`<div class="panel-title">Score VRIST Global</div>
        <div style="font:900 50px/1 var(--display);color:${gcol}">${global}</div>
        <div style="font:700 10px var(--sans);color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.08em">${glabel}</div>
        <div style="font:400 9.5px var(--sans);color:var(--faint);margin-top:8px">Basé sur ${n} exclusivités · ${nSec} domaines couverts</div>`;
      if(dimsTitle)dimsTitle.textContent='Les 5 dimensions VRIST — ★ SGCI';
      if(dimsBox)dimsBox.innerHTML=_renderVCards(vDefs);
    }
  };
  setTimeout(()=>_vristPlot(window._vristBankFilter||'SGCI'),80);
  const vristBanks=['SGCI',...concVrist.map(c=>c.b),'TOUTES'];
  const vristBtns=vristBanks.map(b=>{
    const isSGCI=b==='SGCI';const isAll=b==='TOUTES';
    const bg=isSGCI?'#E91E63':isAll?'var(--ink)':'var(--bg-raise)';
    const clr=isSGCI||isAll?'#fff':'var(--muted)';
    const border=isSGCI?'#E91E63':isAll?'var(--ink)':'var(--line)';
    const fw=isSGCI||isAll?700:500;
    const lbl=isSGCI?'★ SGCI':isAll?'⊕ Toutes':b;
    return`<button data-vrist-btn="${b}" onclick="_vristSelectBank('${b}')" style="padding:3px 10px;border-radius:20px;font:${fw} 11px var(--sans);cursor:pointer;border:1px solid ${border};background:${bg};color:${clr};transition:.15s">${lbl}</button>`;
  }).join('');
  function _renderVCards(defs){
    return defs.map(d=>{
      const isWeak=d.sc<=5;const isStrong=d.sc>=8;
      return`<div style="padding:11px 12px;border-radius:8px;background:${isWeak?'color-mix(in srgb,var(--red) 6%,var(--bg-raise))':isStrong?'color-mix(in srgb,var(--green) 6%,var(--bg-raise))':'var(--bg-raise)'};border-left:4px solid ${d.col};margin-bottom:7px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px">
          <div style="flex:1">
            <div style="font:700 11px var(--sans);color:${d.col}">${d.l} — ${d.nm}</div>
            <div style="font:400 9.5px var(--sans);color:var(--muted);margin-top:2px;font-style:italic">${d.question}</div>
            <div style="font:400 10px var(--sans);color:var(--ink);margin-top:5px;line-height:1.5">${d.fact}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <span style="font:800 22px var(--display);color:${d.col}">${d.sc}</span><span style="font:400 10px var(--sans);color:var(--faint)">/10</span>
            ${isWeak?`<div style="font:600 8.5px var(--sans);color:var(--red);text-transform:uppercase;margin-top:2px">⚠ Point faible</div>`:isStrong?`<div style="font:600 8.5px var(--sans);color:var(--green);text-transform:uppercase;margin-top:2px">✓ Fort</div>`:''}
          </div>
        </div>
      </div>`;
    }).join('');
  }
  const vCards=_renderVCards(vDefs);
  window._q4LlmPayload={
    segment:CB_SEG, annee:CB_YEAR, semestre:CB_SEM,
    scores:{V,R,I,S,T},global:+global,label:glabel,
    nExclusifs:n,nGrat,nSec,
    topDomain:topSec?(secNm[topSec[0]]||'—'):'—',
    pointFaible:vDefs.slice().sort((a,b)=>a.sc-b.sc)[0].nm,
    topExclusifs,
    topGaps:q5summary
  };
  return`
${_v3sec('4','#E91E63','Avantage concurrentiel durable — Analyse VRIST','Index qualitatif '+global+'/10 (cadre VRIST, basé sur les données réelles) · Valuable · Rare · Inimitable · Sustainable · Transformative')}
<div class="row r13">
  <div class="panel" style="display:flex;flex-direction:column;align-items:center">
    <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px;justify-content:center">${vristBtns}</div>
    <div id="cb-q4-score-box" style="text-align:center;padding:18px;background:var(--bg-raise);border:1px solid var(--line);border-radius:12px;width:100%;box-sizing:border-box;margin-bottom:12px">
      <div class="panel-title" style="text-align:center;border:none;padding:0;margin-bottom:6px">Score VRIST Global</div>
      <div style="font:900 50px/1 var(--display);color:${gcol}">${global}</div>
      <div style="font:700 10px var(--sans);color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.08em">${glabel}</div>
      <div style="font:400 9.5px var(--sans);color:var(--faint);margin-top:8px">Basé sur ${n} exclusivités · ${nSec} domaines couverts</div>
    </div>
    <div id="cb-q4-radar" style="width:100%;height:230px"></div>
  </div>
  <div class="panel">
    <div class="panel-title" id="cb-q4-vdims-title">Les 5 dimensions VRIST — ★ SGCI</div>
    <div id="cb-q4-vdims">${vCards}</div>
  </div>
</div>
<div class="panel">
  <div class="panel-title">Analyse stratégique</div>
  <div id="cb-q4-llm" class="insight" style="margin-top:14px"><span style="font:400 12.5px var(--sans);color:var(--faint);font-style:italic">Analyse stratégique en cours…</span></div>
  <div id="cb-q4-llm-stale-badge" style="display:none"></div>
</div>`;
}
// ── Q5 : filtre banque — chargement lazy axe BCEAO par banque ────────────────
async function _q5BankFilter(b){
  document.querySelectorAll('[data-q5-btn]').forEach(btn=>{
    const on=btn.dataset.q5Btn===b;
    btn.style.background=on?'#E53935':'#fff';
    btn.style.color=on?'#fff':'var(--ink)';
    btn.style.borderColor=on?'#E53935':'#CBD5E1';
    btn.style.fontWeight=on?'700':'500';
  });
  document.querySelectorAll('[data-q5-panel]').forEach(el=>el.style.display='none');
  const panel=document.getElementById('cb-q5-panel-'+b);
  if(panel)panel.style.display='block';
  const div=document.getElementById('cb-q5-axes-'+b);
  if(!div||div.dataset.loaded==='1')return;
  div.innerHTML=`<div style="padding:24px;text-align:center;color:var(--faint);font-style:italic;font-size:12px">Analyse des gaps de ${b} vs SGCI par axe BCEAO…<br><span style="font-size:10px">~15 s · Mise en cache ensuite</span></div>`;
  try{
    const res=await fetch('/api/cb_gaps_axes',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({segment:CB_SEG,annee:CB_YEAR,semestre:CB_SEM,banque:b})
    });
    if(!res.ok)throw new Error('HTTP '+res.status);
    const d=await res.json();
    div.dataset.loaded='1';
    div.innerHTML=_buildQ5AxesHTML(d,b);
    // Stocker le résumé Q5 pour la conclusion et Q6/Q4 payloads
    if(!window._CB_Q5_SUMMARY)window._CB_Q5_SUMMARY={};
    window._CB_Q5_SUMMARY[b]=d.total_gaps||0;
    _tryFireConclusion();
  }catch(e){
    div.innerHTML=`<div style="padding:16px;color:var(--red);font-size:12px">Erreur : ${e.message}</div>`;
  }
}
window._q5BankFilter=_q5BankFilter;

// ── Q5 : Gaps concurrentiels — vue par banque (axes BCEAO, validée par IA) ────
function _renderQ5(data){
  const banks=CB_BANK_ORDER.filter(b=>b!=='SGCI');
  const bankBtns=banks.map((b,i)=>`<button data-q5-btn="${b}" onclick="_q5BankFilter('${b}')" style="padding:5px 14px;border-radius:20px;font:${i===0?700:500} 11px var(--sans);cursor:pointer;transition:.15s;border:1px solid ${i===0?'var(--red)':'var(--line)'};background:${i===0?'var(--red)':'var(--bg-raise)'};color:${i===0?'#fff':'var(--ink)'}">${b}</button>`).join('');
  const panels=banks.map((b,i)=>`<div id="cb-q5-panel-${b}" data-q5-panel="${b}" style="display:${i===0?'block':'none'}">
    <div id="cb-q5-axes-${b}" data-bank="${b}">
      ${i===0?`<div style="padding:28px;text-align:center;color:var(--faint);font-style:italic;font-size:12px">Analyse des gaps de ${b} vs SGCI par axe BCEAO…<br><span style="font-size:10px">~15 s · Mise en cache ensuite</span></div>`:`<div style="padding:16px;text-align:center;color:var(--faint);font-size:11px">Cliquez <strong>${b}</strong> pour charger.</div>`}
    </div>
  </div>`).join('');
  return`
${_v3sec('5','#E53935',"Ce que les concurrents ont que SGCI n'a pas","Comparaison sémantique · 8 axes BCEAO · Segment "+CB_SEG)}
<div class="panel">
  <div class="panel-title">Gaps par banque concurrente ${_v3tag('8 axes BCEAO','tr')}</div>
  <div style="font:400 11px var(--sans);color:#64748B;line-height:1.6;margin-bottom:12px;padding:10px 12px;background:#FFF5F5;border-radius:8px;border:1px solid #FECACA">
    Chaque service concurrent est comparé sémantiquement au catalogue SGCI. Les variantes de nommage sont éliminées. Seuls les vrais manques — services absents chez SGCI et présents chez au moins un concurrent — sont affichés.
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">${bankBtns}</div>
  ${panels}
</div>`;
}

// ── Q6 : Benchmark marché — comparaison sur services communs ─────────────────
function _renderQ6(data){
  if(!Array.isArray(data)||!data.length)
    return _v3sec('6','#FF9800',"Analyse prix — comparatif sur services communs","Aucune donnée.")+_v3ins('Données insuffisantes pour le benchmark prix.');

  // Catalogue stats (toutes banques, tri par nombre de services)
  const bySize=[...data].sort((a,b)=>+(b.n_services||0)-+(a.n_services||0));
  const sgci=data.find(r=>r.banque==='SGCI');
  const sgciNSvc=+(sgci?.n_services||0);
  const sgciPctGrat=sgci?Math.max(0,Math.round(Math.abs(+(sgci.pct_gratuit||0)))):0;
  const maxN=Math.max(...bySize.map(r=>+(r.n_services||0)),1);

  const catalogRows=bySize.map(r=>{
    const isSGCI=r.banque==='SGCI';
    const col=isSGCI?'#FF9800':'var(--muted)';
    const barW=Math.round((+(r.n_services||0)/maxN)*100);
    const pctG=Math.max(0,Math.round(Math.abs(+(r.pct_gratuit||0))));
    return`<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)">
      <span style="font:${isSGCI?'800':'500'} 12px var(--sans);color:${isSGCI?'#FF9800':'var(--muted)'};width:66px">${isSGCI?'★ SGCI':r.banque}</span>
      <div style="flex:1;height:8px;background:var(--bg-raise);border-radius:4px;overflow:hidden">
        <div style="height:100%;width:${barW}%;background:${isSGCI?'#FF9800':'var(--line)'};border-radius:4px"></div>
      </div>
      <span style="font:700 12px var(--mono);color:${isSGCI?'#FF9800':'var(--ink)'};min-width:36px;text-align:right">${r.n_services||0}</span>
      <span style="font:500 11px var(--sans);color:var(--faint);min-width:44px;text-align:right">${pctG}% grat.</span>
    </div>`;
  }).join('');

  // Payload LLM Q6 (enrichi avec Q3/Q5 si disponibles)
  const _q6excl=window._CB_Q3_DATA?Object.values(window._CB_Q3_DATA.axes||{}).flatMap(a=>(a.exclusifs||[]).slice(0,2).map(it=>typeof it==='string'?it:it.libelle)).filter(Boolean).slice(0,6):[];
  const _q6gaps=window._CB_Q5_SUMMARY?Object.entries(window._CB_Q5_SUMMARY).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([b,n])=>`${b}(${n})`):[];
  // Rang SGCI dans le classement catalogue (par n_services)
  const _sgciRangIdx=bySize.findIndex(r=>r.banque==='SGCI');
  // 2026-07-30 : plus de rang 4 par défaut — un rang non calculable reste null, et le
  // serveur omet alors la phrase de rang au lieu d'en inventer un.
  const _sgciRang=_sgciRangIdx>=0?_sgciRangIdx+1:null;
  // Banque la moins chère (plus grand catalogue = pas forcément la moins chère, mais proxy)
  // 2026-07-30 : ne JAMAIS retomber sur un nom de banque en dur. L'ancien repli 'SIB'
  // envoyait au LLM « SIB est la moins chère » alors que rien ne l'établissait — un fait
  // concurrentiel fabriqué par un défaut de données. Vide = le serveur omet la phrase.
  const _cheapestBank=(bySize.length>0&&bySize[bySize.length-1].banque!=='SGCI')?bySize[bySize.length-1].banque:'';
  window._q6LlmPayload={
    segment:CB_SEG,year:CB_YEAR,sem:CB_SEM,
    banks:bySize.map((r,i)=>({banque:r.banque,n_services:r.n_services||0,pct_gratuit:+(r.pct_gratuit||0),rang:i+1})),
    sgciPctGrat,sgciNSvc,
    sgciRang:_sgciRang,
    nBanks:bySize.length||null,   // effectif réel du panel, jamais figé à 7
    cheapestBank:_cheapestBank,
    excl_txt:_q6excl.join(', '),
    gaps_txt:_q6gaps.join(' | ')
  };

  return`
${_v3sec('6','#FF9800',"Analyse prix — comparatif sur services communs","Appariement sémantique · "+data.length+" banques · "+CB_YEAR+" "+CB_SEM)}
<div class="row r2">
  <div class="panel">
    <div class="panel-title">Profondeur de catalogue — nombre de services par banque</div>
    <div style="font:400 11px var(--sans);color:#64748B;line-height:1.5;margin-bottom:12px;padding:8px 10px;background:#FFF7ED;border-radius:8px;border:1px solid #FED7AA">
      Le nombre de services et le taux de gratuité reflètent le positionnement commercial de chaque banque — non pas leur cherté.
    </div>
    ${catalogRows}
    ${_v3ins('SGCI propose <b>'+sgciNSvc+' services</b> dont <b>'+sgciPctGrat+'%</b> gratuits. Un catalogue large reflète une offre complète, pas nécessairement des prix plus élevés.')}
  </div>
  <div class="panel">
    <div class="panel-title">Indice de compétitivité tarifaire — qui est le plus souvent le moins cher ?</div>
    <div style="font:400 11px var(--sans);color:#64748B;line-height:1.5;margin-bottom:10px;padding:8px 10px;background:#ECFDF5;border-radius:8px;border:1px solid #A7F3D0">
      Méthode « win-rate » : sur les services <b>réellement comparables</b> (présents chez ≥ 3 banques), une banque « gagne » si son prix est <b>≤ à la médiane du marché</b> (gratuit gagne toujours). <b>Complète le rang catalogue</b> : ici on classe la <b>cherté</b>.
    </div>
    <div id="cb-q6-winrate">
      <div style="display:flex;align-items:center;gap:10px;padding:18px 0;color:var(--muted)"><div class="spin"></div><span style="font:500 12px var(--sans)">Calcul de l'indice de compétitivité prix…</span></div>
    </div>
  </div>
</div>
<div class="panel" style="margin-bottom:14px">
  <div class="panel-title">Comparatif tarifaire service par service — 9 familles BCEAO</div>
  <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font:600 10.5px var(--sans);color:#475569;margin-bottom:10px;padding:8px 10px;background:#F8FAFC;border-radius:8px;border:1px solid var(--line)">
    <span>Lecture immédiate par ligne :</span>
    <span style="display:inline-flex;align-items:center;gap:5px"><span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:#D1FAE5;border:1px solid #6EE7B7"></span>moins cher / gratuit</span>
    <span style="display:inline-flex;align-items:center;gap:5px"><span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:#FEE2E2;border:1px solid #FCA5A5"></span>plus cher</span>
    <span style="display:inline-flex;align-items:center;gap:5px"><span style="color:#FF9800;font-weight:800">★</span>colonne SGCI</span>
    <span style="display:inline-flex;align-items:center;gap:5px"><span style="font-style:italic;color:var(--faint)">réf. CB</span>= valeur douteuse → voir grille source</span>
  </div>
  <div id="cb-q6-paired-content">
    <div style="display:flex;align-items:center;gap:10px;padding:20px 0;color:var(--muted)"><div class="spin"></div><span style="font:500 12px var(--sans)">Chargement du comparatif par famille de service…</span></div>
  </div>
</div>
<div id="cb-q6-price-llm" class="insight" style="margin-bottom:16px"><span style="font:400 12.5px var(--sans);color:var(--faint);font-style:italic">Analyse stratégique du positionnement prix en cours…</span></div>
<div class="panel" style="margin-bottom:14px;border-left:4px solid var(--accent-2)">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font:500 12px var(--sans);color:var(--muted)">
    <span style="font:800 13px var(--mono);color:var(--accent-2)">◆</span>
    <span>Les <b>recommandations marketing</b> et le <b>plan d'action chiffré</b> (diagnostic, SWOT, Porter, projection 3 ans) sont centralisés dans l'onglet</span>
    <button onclick="go('strategie')" style="font:700 11px var(--sans);padding:5px 12px;border-radius:7px;border:1px solid var(--accent-2);background:var(--accent-2);color:#fff;cursor:pointer">Stratégie →</button>
    <span style="color:var(--faint)">— évite le doublon.</span>
  </div>
</div>`;
}

// ── Q6 : Comparatif prix libellé par libellé ─────────────────────────────────
const _CONC_BANKS=['BACI','BICICI','BNI','ECOBANK','NSIA','SIB'];  // fallback si données absentes
const _BK_COL={SGCI:'#FF9800',BACI:'#4A90D9',BICICI:'#E53935',BNI:'#78909C',ECOBANK:'#66BB6A',NSIA:'#38D1F0',SIB:'#A78BFA'};
// Palette de secours : couleur STABLE dérivée du nom pour toute banque inconnue (nouvelle banque ajoutée).
const _BK_PALETTE=['#4A90D9','#E53935','#78909C','#66BB6A','#38D1F0','#A78BFA','#F59E0B','#EC4899','#10B981','#8B5CF6','#F43F5E','#14B8A6'];
function _bkCol(b){
  if(_BK_COL[b])return _BK_COL[b];
  let h=0; for(let i=0;i<(b||'').length;i++)h=(h*31+b.charCodeAt(i))>>>0;
  return _BK_PALETTE[h%_BK_PALETTE.length];
}
// Banques concurrentes RÉELLEMENT présentes dans les données (auto-sync avec le backend dynamique).
function _concBanksFromData(sections){
  const s=new Set();
  (sections||[]).forEach(sec=>(sec.sous_sections||[]).forEach(ss=>(ss.services||[]).forEach(svc=>{
    Object.keys(svc.concurrents||{}).forEach(b=>{ if(b&&b!=='SGCI')s.add(b); });
  })));
  return s.size?[...s].sort():_CONC_BANKS.slice();
}

// ── REPRICING : action tarifaire stratégique par service (flèche + colonne Action + récap) ──
const _RP_CACHE={};   // {period_seg: {sections, recap, engine, n_actions}}
const _RP_META={
  up:['▲','#059669','#D1FAE5','#047857','Augmenter'],
  down:['▼','#DC2626','#FEE2E2','#B91C1C','Baisser'],
  // 2026-07-17 : NE_PAS_TOUCHER et MAINTENIR affichaient 2 étiquettes différentes pour une
  // nuance trop fine pour l'utilisateur (raison stratégique de ne pas toucher vs prix juste
  // déjà bien placé) — fusionnées à l'affichage sur un seul verdict « Maintenir » (la raison
  // reste visible dans la justification en dessous). Backend inchangé (garde-fous intacts).
  lock:['=','#94A3B8','#F1F5F9','#475569','Maintenir'],
  flat:['=','#94A3B8','#F1F5F9','#475569','Maintenir'],
};
// Petite flèche collée au prix SGCI (injectée dans la cellule SGCI)
function _rpArrowInline(a){
  if(!a||!a.fleche)return'';
  const m=_RP_META[a.fleche]; if(!m||!m[0])return'';
  const amt=a.montant?` ${a.verdict==='AUGMENTER'?'+':'−'}${a.montant.toLocaleString('fr-FR')} F`:'';
  return `<span title="${m[4]}${amt}" style="font:800 10px var(--mono);color:${m[1]};margin-left:3px;vertical-align:top">${m[0]}</span>`;
}
// Validation web sourcée (agent Tavily) d'une décision de hausse/baisse
function _rpWebBadge(w){
  if(!w||(!w.contexte&&!(w.sources&&w.sources.length)))return'';
  const ok=w.ok?['#047857','#D1FAE5','conforté web']:['#B45309','#FEF3C7','prudence web'];
  const src=(w.sources||[]).slice(0,3).map((u,i)=>`<a href="${u}" target="_blank" rel="noopener" style="color:#2563EB;text-decoration:none">[${i+1}]</a>`).join(' ');
  return `<div style="margin-top:4px;padding-top:4px;border-top:1px dashed var(--line)">
    <span style="background:${ok[1]};color:${ok[0]};font:700 8.5px var(--sans);padding:1px 5px;border-radius:3px;white-space:nowrap">🌐 ${ok[2]}</span>
    ${w.contexte?`<span style="font:400 9px var(--sans);color:var(--muted);margin-left:4px">${w.contexte}</span>`:''}
    ${(w.nuance||src)?`<div style="font:400 8.5px var(--sans);color:var(--faint);margin-top:2px;font-style:italic">${w.nuance||''}${(w.nuance&&src)?' · ':''}${src}</div>`:''}
  </div>`;
}
// Cellule de la colonne « Action »
function _rpActionCell(a,unreliable){
  // Transparence : marque les comparaisons dont les prix concurrents sont trop dispersés (non fiables).
  const warn=unreliable?`<div title="Prix concurrents trop dispersés (probable appariement hétérogène / valeur aberrante) — comparaison à ne pas exploiter." style="font:600 8.5px var(--sans);color:#B45309;margin-top:2px">⚠ comparaison peu fiable</div>`:'';
  if(!a||!a.verdict)return`<td style="text-align:center;color:var(--faint);font:500 11px var(--sans)">—${warn}</td>`;
  const key={AUGMENTER:'up',BAISSER:'down',NE_PAS_TOUCHER:'lock',MAINTENIR:'flat'}[a.verdict]||'flat';
  const m=_RP_META[key];
  let amt='';
  if(a.montant&&(a.verdict==='AUGMENTER'||a.verdict==='BAISSER')){
    const sign=a.verdict==='AUGMENTER'?'+':'−';
    amt=` ${sign}${a.montant.toLocaleString('fr-FR')} F`+(a.cible?` → ${a.cible.toLocaleString('fr-FR')} F`:'');
  }
  // Justification affichée EN ENTIER dans la cellule (2026-07-20 : plus de troncature/survol —
  // le directeur veut tout lire directement, pas seulement au hover).
  const jFull=(a.justif||'').replace(/"/g,'&quot;');
  return `<td style="padding:5px 8px;vertical-align:top;min-width:150px;max-width:220px">
    <span style="display:inline-block;background:${m[2]};color:${m[3]};font:700 10px var(--sans);padding:2px 7px;border-radius:4px;white-space:nowrap">${m[0]} ${m[4]}${amt}</span>
    ${a.justif?`<div style="font:400 9px var(--sans);color:var(--muted);margin-top:2px;line-height:1.3">${jFull}</div>`:''}
    ${warn}
  </td>`;
}
// Tableau RÉCAP des actions menables (par grand titre + libellé, trié par marge)
function _rpRecapHTML(recap){
  if(!recap||!recap.length)return`<p style="font:500 12px var(--sans);color:var(--muted);padding:14px 4px">Aucune action tarifaire prioritaire détectée sur ce filtre.</p>`;
  const totA=recap.reduce((t,s)=>t+s.items.filter(i=>i.verdict==='AUGMENTER').length,0);
  const totB=recap.reduce((t,s)=>t+s.items.filter(i=>i.verdict==='BAISSER').length,0);
  const gain=recap.reduce((t,s)=>t+s.items.reduce((u,i)=>u+(i.verdict==='AUGMENTER'?(i.montant||0):0),0),0);
  let h=`<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px">
    <div style="flex:1;min-width:110px;background:#D1FAE5;border-radius:8px;padding:10px 12px"><div style="font:800 20px var(--mono);color:#047857">${totA}</div><div style="font:600 10px var(--sans);color:#065F46">hausses possibles</div></div>
    <div style="flex:1;min-width:110px;background:#FEE2E2;border-radius:8px;padding:10px 12px"><div style="font:800 20px var(--mono);color:#B91C1C">${totB}</div><div style="font:600 10px var(--sans);color:#7F1D1D">baisses conseillées</div></div>
    <div style="flex:1;min-width:110px;background:#EEF2FF;border-radius:8px;padding:10px 12px"><div style="font:800 20px var(--mono);color:#3730A3">+${gain.toLocaleString('fr-FR')} F</div><div style="font:600 10px var(--sans);color:#3730A3">marge cumulée / unité</div></div>
  </div>
  <div style="max-height:70vh;overflow:auto;border:1px solid var(--line);border-radius:8px;position:relative"><table style="width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;font-size:11px">
  <colgroup><col style="width:34%"><col style="width:13%"><col style="width:13%"><col style="width:40%"></colgroup>
  <thead><tr>
   <th style="position:sticky;top:0;z-index:3;background:var(--bg-tile,#fff);text-align:left;font:700 10px var(--sans);color:var(--muted);padding:8px 10px;border-bottom:2px solid var(--line);border-right:1px solid var(--line);box-shadow:0 2px 0 var(--line)">Service</th>
   <th style="position:sticky;top:0;z-index:3;background:var(--bg-tile,#fff);text-align:right;font:700 10px var(--sans);color:#FF9800;padding:8px 10px;border-bottom:2px solid var(--line);border-right:1px solid var(--line);box-shadow:0 2px 0 var(--line)">SGCI</th>
   <th style="position:sticky;top:0;z-index:3;background:var(--bg-tile,#fff);text-align:right;font:700 10px var(--sans);color:var(--muted);padding:8px 10px;border-bottom:2px solid var(--line);border-right:1px solid var(--line);box-shadow:0 2px 0 var(--line)">Médiane</th>
   <th style="position:sticky;top:0;z-index:3;background:var(--bg-tile,#fff);text-align:left;font:700 10px var(--sans);color:var(--muted);padding:8px 10px;border-bottom:2px solid var(--line);box-shadow:0 2px 0 var(--line)">Action &amp; justification</th>
  </tr></thead><tbody>`;
  recap.forEach(sec=>{
    h+=`<tr><td colspan="4" style="padding:10px 10px 4px;font:700 11px var(--sans);color:var(--accent-2);text-transform:uppercase;letter-spacing:.05em;background:var(--bg-tile,#fff)">${sec.roman}. ${sec.titre} <span style="font:600 9.5px var(--sans);color:var(--faint);text-transform:none">· ${sec.items.length} action${sec.items.length>1?'s':''}</span></td></tr>`;
    sec.items.forEach((it,i)=>{
      const lib=it.libelle.replace(/^[^\wÀ-ɏ]+/u,'').replace(/\s*T\d+\s*$/,'').trim();
      const up=it.verdict==='AUGMENTER';
      const sign=up?'+':'−', bg=up?'#D1FAE5':'#FEE2E2', tc=up?'#047857':'#B91C1C', ar=up?'▲':'▼';
      const badge=`<span style="background:${bg};color:${tc};font:700 10px var(--sans);padding:2px 7px;border-radius:4px;white-space:nowrap;display:inline-block">${ar} ${sign}${(it.montant||0).toLocaleString('fr-FR')} F${it.cible?` → ${it.cible.toLocaleString('fr-FR')} F`:''}</span>`;
      const rowBg=i%2?'var(--bg-tile,#fff)':'rgba(127,127,127,.035)';
      h+=`<tr style="border-bottom:1px solid var(--line);background:${rowBg}">
        <td style="padding:6px 10px;font:500 11px var(--sans);color:var(--ink);line-height:1.3;border-right:1px solid var(--line);overflow-wrap:break-word">${lib}${it.sous_section?`<div style="font:400 9px var(--sans);color:var(--faint)">${it.sous_section}</div>`:''}</td>
        <td style="padding:6px 10px;text-align:right;font:700 11px var(--mono);color:var(--ink);white-space:nowrap;border-right:1px solid var(--line)">${it.sgci_prix?it.sgci_prix.toLocaleString('fr-FR')+' F':'gratuit'}</td>
        <td style="padding:6px 10px;text-align:right;font:600 11px var(--mono);color:var(--muted);white-space:nowrap;border-right:1px solid var(--line)">${it.mkt_median?it.mkt_median.toLocaleString('fr-FR')+' F':'—'}</td>
        <td style="padding:6px 10px;vertical-align:top;overflow-wrap:break-word">${badge}${it.justif?`<div style="font:400 9.5px var(--sans);color:var(--muted);margin-top:3px;line-height:1.35">${it.justif}</div>`:''}${it.web?_rpWebBadge(it.web):''}</td>
      </tr>`;
    });
  });
  return h+`</tbody></table></div>`;
}
// Bascule Catalogue complet ⇄ Recommandation (une seule vue à la fois)
window._rpSwitchView=(v)=>{
  const cat=document.getElementById('rp-view-cat'), rec=document.getElementById('rp-view-recap');
  const tc=document.getElementById('rp-tab-cat'), tr=document.getElementById('rp-tab-recap');
  if(!cat||!rec)return;
  const isCat=(v==='cat');
  cat.style.display=isCat?'':'none'; rec.style.display=isCat?'none':'';
  [tc,tr].forEach(b=>{if(b){b.style.background='var(--bg-raise,#f1f5f9)';b.style.color='var(--muted)';b.style.borderColor='var(--line)';}});
  const on=isCat?tc:tr;
  if(on){on.style.background='var(--accent-2)';on.style.color='#fff';on.style.borderColor='var(--accent-2)';}
};

function _prixCell(info, isSGCI, mktMedian){
  if(!info) return`<td style="text-align:center;padding:3px 5px;color:var(--faint);font-size:10px">—</td>`;
  if(info.grat&&(!info.montant||info.tv==='GRATUIT'))
    return`<td style="text-align:center;padding:3px 5px"><span style="font:700 9.5px var(--sans);color:var(--green)">GRATUIT</span></td>`;
  if(info.tv==='SUR_DEMANDE'||info.tv==='NUMERIQUE')
    return`<td style="text-align:center;padding:3px 5px;font:500 10px var(--sans);color:var(--faint)">Sur dem.</td>`;
  if(info.tv==='TAUX_%'||info.tv==='TAUX_%%'){
    if(info.montant!=null&&+info.montant>100)
      return`<td style="text-align:center;padding:3px 5px;font:500 10px var(--sans);color:var(--faint)">Sur dem.</td>`;
    return`<td style="text-align:center;padding:3px 5px;font:500 10px var(--mono);color:var(--ink)">${info.montant??'—'}%</td>`;
  }
  if(info.montant==null)
    return`<td style="text-align:center;padding:3px 5px;color:var(--faint);font-size:10px">—</td>`;
  const m=+info.montant;
  let badge='';
  if(isSGCI&&mktMedian&&mktMedian>0){
    const pct=Math.round((m-mktMedian)/mktMedian*100);
    // Écarts > 500% = quasi toujours un artefact (fourchette Min/Max, OCR) → pas de badge trompeur
    if(Math.abs(pct)<=500){
      if(pct<=-10) badge=`<br><span style="font:700 9px var(--sans);color:var(--green)">↓${Math.abs(pct)}%</span>`;
      else if(pct>=10) badge=`<br><span style="font:700 9px var(--sans);color:var(--red)">↑${pct}%</span>`;
    }
  }
  return`<td style="text-align:center;padding:3px 5px;vertical-align:top${isSGCI?';background:rgba(255,152,0,.06)':''}">
    <span style="font:${isSGCI?'700':'500'} 11px var(--mono);color:${isSGCI?_BK_COL.SGCI:'var(--ink)'}">${_v3f(m,info.unite)}</span>${badge}
  </td>`;
}

// Cellule v2 : code couleur par ligne (vert = moins cher/gratuit · rouge = plus cher)
// + garde-fou « réf. CB » sur les valeurs aberrantes. ctx = stats de la ligne.
function _cellV2(info, isSGCI, ctx){
  const pad='padding:5px 5px';
  const sgbg=isSGCI?';background:rgba(255,152,0,.06)':'';
  if(!info) return`<td style="text-align:center;${pad};color:var(--faint);font-size:10px${sgbg}">—</td>`;
  if(info.grat&&(!info.montant||info.tv==='GRATUIT'))
    return`<td style="text-align:center;${pad};background:#D1FAE5"><span style="font:800 9.5px var(--sans);color:#047857">GRATUIT</span></td>`;
  if(info.tv==='SUR_DEMANDE'||info.tv==='NUMERIQUE')
    return`<td style="text-align:center;${pad};font:500 10px var(--sans);color:var(--faint)${sgbg}">Sur dem.</td>`;
  if(info.tv==='TAUX_%'||info.tv==='TAUX_%%'){
    // Ligne de FRAIS : un taux n'a rien à y faire (ce n'est pas un prix) → « — ».
    if(ctx.rowKind==='fee')
      return`<td title="Taux (%) — non comparable à un frais : voir la ligne de taux dédiée" style="text-align:center;${pad};color:var(--faint);font-size:10px${sgbg}">—</td>`;
    // Taux ABERRANT vs marché (ex. « 5% » de commission de mouvement au lieu de « 0,05% ») → réf. CB.
    if(info.suspect)
      return`<td title="Taux incohérent par rapport au marché (probable erreur d'extraction) — se référer à la grille tarifaire source" style="text-align:center;${pad};font:italic 600 9.5px var(--sans);color:#B45309;background:#FEF3C7">réf. CB</td>`;
    if(info.montant!=null&&+info.montant>100)
      return`<td style="text-align:center;${pad};font:500 10px var(--sans);color:var(--faint)${sgbg}">Sur dem.</td>`;
    return`<td style="text-align:center;${pad};font:600 10.5px var(--mono);color:var(--ink)${sgbg}">${info.montant??'—'}%</td>`;
  }
  if(info.montant==null)
    return`<td style="text-align:center;${pad};color:var(--faint);font-size:10px${sgbg}">—</td>`;
  const m=+info.montant;
  // Ligne de TAUX : un frais en FCFA n'y est pas comparable → « — ».
  if(ctx.rowKind==='rate'&&!info.grat)
    return`<td title="Frais (FCFA) — non comparable à un taux : voir la ligne de frais dédiée" style="text-align:center;${pad};color:var(--faint);font-size:10px${sgbg}">—</td>`;
  // Garde-fou ABSOLU : montant FCFA anormalement bas (< 20 F, ex. « 0,003 F », « 2,4 F »,
  // « 3 F ») = artefact d'extraction (un % ou un OCR pris pour un prix). On n'affiche
  // jamais un faux prix → « réf. CB ». (Ne masque pas un vrai petit frais ≥ 20 F.)
  if(m>0&&m<20||info.suspect)
    return`<td title="Montant douteux — se référer à la grille tarifaire source" style="text-align:center;${pad};font:italic 600 9.5px var(--sans);color:#B45309;background:#FEF3C7">réf. CB</td>`;
  // Garde-fou : valeur aberrante vs marché → ne pas afficher un faux prix
  if(ctx.isAber(m))
    return`<td title="Valeur incohérente par rapport au marché — se référer à la grille tarifaire source" style="text-align:center;${pad};font:italic 600 9.5px var(--sans);color:#B45309;background:#FEF3C7">réf. CB</td>`;
  let bg=sgbg;
  if(ctx.showCol){
    if(!ctx.hasGrat && m===ctx.rmin) bg=';background:#D1FAE5';
    else if(m===ctx.rmax) bg=';background:#FEE2E2';
  }
  return`<td style="text-align:center;${pad}${bg}">
    <span style="font:${isSGCI?'800':'600'} 10.5px var(--mono);color:${isSGCI?'#E67E00':'var(--ink)'}">${_v3f(m,info.unite)}</span>
  </td>`;
}

window._q6ToggleSec=(si)=>{
  const rows=document.querySelectorAll('.q6s'+si);
  const hdr=document.querySelector('.q6hdr[data-sec="'+si+'"] .q6arrow');
  if(!rows.length)return;
  const open=rows[0].style.display!=='none';
  rows.forEach(r=>r.style.display=open?'none':'');
  if(hdr)hdr.textContent=open?'▶':'▼';
};

async function _fireQ6PrixCompetitivite(){
  const box=document.getElementById('cb-q6-winrate');
  if(!box)return;
  const tk=_cbToken;
  try{
    const q=`annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}`;
    const r=await fetch(`/api/cb_prix_competitivite?${q}`);
    const d=await r.json();
    if(!_cbAlive(tk))return;
    const cl=(d&&d.classement)||[];
    // 2026-07-30 : exposé en global pour que le positionnement prix des concurrents (bloc
    // COMPETS) soit DÉRIVÉ de cette mesure au lieu d'être écrit en dur (cf. _positionPrix).
    window._CB_WINRATE = cl;
    if(!cl.length){box.innerHTML=`<div style="font:500 11px var(--sans);color:var(--faint);padding:10px 0">Pas assez de services comparables pour ce filtre.</div>`;return;}
    const maxW=Math.max(...cl.map(c=>c.winrate),1);
    const rows=cl.map((c,i)=>{
      const isSGCI=c.banque==='SGCI';
      const w=Math.round(c.winrate/maxW*100);
      const col=isSGCI?'#FF9800':(i===0?'var(--green)':'var(--line)');
      const txtc=isSGCI?'#FF9800':(i===0?'var(--green)':'var(--ink)');
      return`<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)">
        <span style="font:700 11px var(--mono);color:var(--faint);width:20px">#${i+1}</span>
        <span style="font:${isSGCI?'800':'500'} 12px var(--sans);color:${isSGCI?'#FF9800':'var(--muted)'};width:66px">${isSGCI?'★ SGCI':c.banque}</span>
        <div style="flex:1;height:8px;background:var(--bg-raise);border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${w}%;background:${col};border-radius:4px"></div>
        </div>
        <span style="font:700 12px var(--mono);color:${txtc};min-width:46px;text-align:right">${c.winrate}%</span>
        <span style="font:500 10px var(--sans);color:var(--faint);min-width:54px;text-align:right">${c.wins}/${c.n} svc</span>
      </div>`;
    }).join('');
    const sg=d.sgci, rg=d.rang_sgci;
    const ins=sg?`SGCI est <b>moins chère ou égale à la médiane</b> du marché sur <b>${sg.winrate}%</b> de ses ${sg.n} services comparables → <b>#${rg}/${d.n_classees}</b> en compétitivité prix. Panier de référence : <b>${d.n_services_panier} services</b> communs.`:'Indice indisponible pour ce filtre.';
    box.innerHTML=rows+_v3ins(ins);
  }catch(e){
    box.innerHTML=`<div style="font:500 11px var(--sans);color:#FF4D4D;padding:10px 0">Erreur indice prix — ${e.message}</div>`;
  }
}

async function _fireQ6SubSectionComparison(){
  const box=document.getElementById('cb-q6-paired-content');
  if(!box)return;
  const tk=_cbToken;
  try{
    const cacheKey=`rp_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
    let sections, recap=[];
    let rp=_RP_CACHE[cacheKey];
    if(!rp){
      // Endpoint repricing : sections (+ action par service) + récap. Génère l'IA au 1er appel puis cache.
      const q=`annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}`;
      const r=await fetch(`/api/cb_repricing?${q}`);
      if(r.ok){
        rp=await r.json();
        if(!_cbAlive(tk))return;
        if(rp&&!rp.error){ _RP_CACHE[cacheKey]=rp; }
      }
      // Secours : ancien endpoint sans actions si le repricing échoue
      if(!rp||rp.error){
        const r2=await fetch(`/api/cb_prix_par_libelle?${q}`);
        if(!r2.ok)throw new Error(`HTTP ${r2.status}`);
        rp={sections:await r2.json(), recap:[]};
        if(!_cbAlive(tk))return;
      }
    }
    sections=rp.sections; recap=rp.recap||[];
    if(!Array.isArray(sections)||!sections.length){
      box.innerHTML=`<p style="font:500 12px var(--sans);color:var(--muted)">Données de comparaison indisponibles.</p>`;
      return;
    }

    // Banques concurrentes DYNAMIQUES (dérivées des données → une nouvelle banque apparaît toute seule).
    const CB=_concBanksFromData(sections);
    // Entête banques — FIGÉ (sticky) en haut du conteneur défilant
    const allCols=['SGCI',...CB];

    // Une ligne n'a de sens QUE s'il existe au moins UN concurrent COMPARABLE (même nature :
    // taux vs taux, frais vs frais). n_conc_presents>0 seul NE SUFFIT PAS : un concurrent peut être
    // "apparié" sémantiquement mais de type incompatible (SGCI en %, concurrent en F) — la ligne
    // affiche alors des tirets partout quand même (bug vérifié : « Remise d'effet à l'escompte »,
    // n_conc_presents=1 mais le seul concurrent apparié est en MONTANT_FCFA face à un taux SGCI).
    const _isTauxV=c=>c&&(c.tv==='TAUX_%'||c.tv==='TAUX_%%');
    const _isFeeV=c=>c&&(c.grat||c.tv==='GRATUIT'||c.tv==='MONTANT_FCFA');
    const _hasComparable=svc=>{
      const sg=svc.sgci;
      let kind=_isTauxV(sg)?'rate':(_isFeeV(sg)?'fee':null);
      if(!kind){
        const nT=CB.filter(b=>_isTauxV(svc.concurrents[b])).length;
        const nF=CB.filter(b=>_isFeeV(svc.concurrents[b])).length;
        kind=nT>nF?'rate':(nF>0?'fee':null);
      }
      if(!kind)return false;
      const match=kind==='rate'?_isTauxV:_isFeeV;
      return CB.some(b=>match(svc.concurrents[b]));
    };
    const thCells=allCols.map(b=>`<th style="position:sticky;top:0;z-index:3;background:var(--bg-tile,#fff);font:700 10px var(--sans);color:${_bkCol(b)};text-align:center;padding:7px 5px;white-space:nowrap;min-width:70px;border-bottom:2px solid var(--line);box-shadow:0 2px 0 var(--line)">${b==='SGCI'?'★ SGCI':b}</th>`).join('');

    // Collecte des insights pour LLM (top écarts)
    const insights_plus=[], insights_moins=[];

    const _nAct=recap.reduce((t,s)=>t+s.items.length,0);
    // Transparence : quand l'IA (Groq/Claude) a échoué et que les verdicts viennent du
    // repli déterministe (règles de marge, pas de raisonnement IA), le prévenir une fois
    // en tête plutôt que de laisser croire que CHAQUE verdict est un raisonnement IA.
    const _estimBanner = (rp.engine==='estimation' && _voitAvertissementsTechniques())
      ? `<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;font:600 11px var(--sans);color:#92400E">⚠️ IA indisponible pour cette génération — verdicts ci-dessous calculés par règle déterministe (marge/écart marché), pas par raisonnement IA.</div>`
      : '';
    let html=_estimBanner+`<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
  <button id="rp-tab-cat" onclick="_rpSwitchView('cat')" style="font:700 11px var(--sans);padding:7px 14px;border-radius:8px;border:1px solid var(--accent-2);background:var(--accent-2);color:#fff;cursor:pointer">Détail par service</button>
  <button id="rp-tab-recap" onclick="_rpSwitchView('recap')" style="font:700 11px var(--sans);padding:7px 14px;border-radius:8px;border:1px solid var(--line);background:var(--bg-raise,#f1f5f9);color:var(--muted);cursor:pointer">Recommandation${_nAct?` (${_nAct})`:''}</button>
</div>
<div id="rp-view-cat">
<div style="font:500 10px var(--sans);color:var(--faint);margin-bottom:6px">▶ Cliquez une famille pour déplier/replier · 1ʳᵉ famille ouverte · <b>entête figé au défilement</b> · colonne <b style="color:var(--accent-2)">Recommandations</b> = recommandation tarifaire IA</div>
<div style="max-height:70vh;overflow:auto;border:1px solid var(--line);border-radius:8px">
<table style="width:100%;border-collapse:separate;border-spacing:0;font-size:11px">
<thead><tr>
  <th style="position:sticky;top:0;z-index:4;background:var(--bg-tile,#fff);font:700 10px var(--sans);color:var(--muted);text-align:left;padding:7px 6px 7px 10px;border-bottom:2px solid var(--line);min-width:180px;box-shadow:0 2px 0 var(--line)">Service</th>
  ${thCells}
  <th style="position:sticky;top:0;z-index:4;background:var(--bg-tile,#fff);font:700 10px var(--sans);color:var(--accent-2);text-align:left;padding:7px 8px;border-bottom:2px solid var(--line);min-width:165px;box-shadow:0 2px 0 var(--line)">Recommandations</th>
</tr></thead>
<tbody>`;

    let _si=-1;
    sections.forEach(sec=>{
      // Sauter sections sans données pertinentes
      const hasSvc=sec.sous_sections.some(ss=>ss.services.some(_hasComparable));
      if(!hasSvc)return;
      _si++;
      const _open=_si<1;  // 1re famille ouverte, les autres repliées (anti-encombrement)
      const _disp=_open?'':'display:none';
      const secCount=sec.sous_sections.reduce((t,ss)=>t+ss.services.filter(_hasComparable).length,0);

      html+=`<tr class="q6hdr" data-sec="${_si}" onclick="_q6ToggleSec(${_si})" style="cursor:pointer"><td colspan="${allCols.length+2}" style="padding:10px 0 2px;font:700 11px var(--sans);color:var(--accent-2);letter-spacing:.06em;text-transform:uppercase"><span class="q6arrow" style="display:inline-block;width:14px;color:var(--muted)">${_open?'▼':'▶'}</span>${sec.roman}. ${sec.titre} <span style="font:600 9.5px var(--sans);color:var(--faint);text-transform:none">· ${secCount} service${secCount>1?'s':''}</span></td></tr>`;

      sec.sous_sections.forEach(ss=>{
        // Une ligne n'a de sens QUE s'il y a au moins un concurrent COMPARABLE (même nature) —
        // sinon on affiche un prix SGCI seul face à des tirets partout, ce qui n'est rien à comparer.
        const filteredSvcs=ss.services.filter(_hasComparable);
        if(!filteredSvcs.length)return;

        // En-tête sous-section si >1 service dans cette sous-section
        if(filteredSvcs.length>1){
          html+=`<tr class="q6s${_si}" style="${_disp}"><td colspan="${allCols.length+2}" style="padding:5px 0 1px 8px;font:600 10px var(--sans);color:var(--muted);font-style:italic;border-top:1px solid var(--line)">${ss.libelle}</td></tr>`;
        }

        filteredSvcs.forEach(svc=>{
          // Libellé complet du service SGCI (tronqué si trop long)
          // Nettoyage OCR : préfixes non-alphanumériques (•) et suffixes T1/T2
          const libClean=svc.libelle.replace(/^[^\wÀ-ɏ]+/u,'').replace(/\s*T\d+\s*$/,'').trim();
          const lbl=libClean.length>55?libClean.slice(0,53)+'…':libClean;
          // mkt_median n'est fiable qu'avec ≥2 concurrents (filtré côté Python)
          const mkt=(svc.n_conc_presents>=2)?svc.mkt_median:null;

          const sgciInfo=svc.sgci;

          // ── Stats de ligne pour le code couleur + garde-fou prix aberrant ──
          const _rowInfos=[sgciInfo, ...CB.map(b=>svc.concurrents[b])];
          const _fc=_rowInfos.filter(c=>c&&c.tv==='MONTANT_FCFA'&&+c.montant>0).map(c=>+c.montant).sort((a,b)=>a-b);
          const _med=_fc.length?_fc[Math.floor(_fc.length/2)]:0;
          const _ABER=12;   // un prix > 12× (ou < 1/12) la médiane de la ligne = suspect
          const _isAber=m=>_fc.length>=3&&_med>0&&(m/_med>_ABER||_med/m>_ABER);
          const _clean=_fc.filter(m=>!_isAber(m));
          const _hasGrat=_rowInfos.some(c=>c&&c.grat&&(!c.montant||c.tv==='GRATUIT'));
          const _rmin=_clean.length?Math.min(..._clean):null;
          const _rmax=_clean.length?Math.max(..._clean):null;
          // Nature de la ligne (d'après la référence SGCI) : 'fee' (gratuit/FCFA) ou
          // 'rate' (taux %). On ne mélange JAMAIS frais et taux dans une même ligne :
          // dans une ligne de frais, une cellule taux s'affiche « — » (et inversement).
          const _isTaux=c=>c&&(c.tv==='TAUX_%'||c.tv==='TAUX_%%');
          const _isFee=c=>c&&(c.grat||c.tv==='GRATUIT'||c.tv==='MONTANT_FCFA');
          let _rowKind=_isTaux(sgciInfo)?'rate':(_isFee(sgciInfo)?'fee':null);
          if(!_rowKind){ // SGCI absent → déduire de la majorité des concurrents
            const nT=CB.filter(b=>_isTaux(svc.concurrents[b])).length;
            const nF=CB.filter(b=>_isFee(svc.concurrents[b])).length;
            _rowKind=nT>nF?'rate':(nF>0?'fee':null);
          }
          const _ctx={rmin:_rmin,rmax:_rmax,hasGrat:_hasGrat,isAber:_isAber,
                      showCol:_clean.length>=3&&_rmin!==_rmax,rowKind:_rowKind};

          // Flèche stratégique collée au prix SGCI (↑ peut augmenter · ↓ baisser · ◆ ne pas toucher)
          const _act=svc.action||null;
          let sgciCell=_cellV2(sgciInfo||null,true,_ctx);
          const _arrow=_rpArrowInline(_act);
          if(_arrow)sgciCell=sgciCell.replace(/<\/td>\s*$/,_arrow+'</td>');
          const concCells=CB.map(b=>_cellV2(svc.concurrents[b]||null,false,_ctx)).join('');
          // Pas de ⚠ « comparaison non fiable » sur un service GRATUIT chez SGCI : la dispersion
          // des prix concurrents n'a aucune incidence (SGCI est gratuit, la décision ne dépend pas d'eux).
          const actionCell=_rpActionCell(_act, svc.unreliable && !(sgciInfo&&sgciInfo.grat));

          html+=`<tr class="q6s${_si}" style="border-bottom:1px solid var(--line);${_disp}">
            <td style="padding:4px 6px 4px ${filteredSvcs.length>1?'18px':'6px'};font:500 11px var(--sans);color:var(--ink);line-height:1.3">${lbl}</td>
            ${sgciCell}${concCells}${actionCell}
          </tr>`;

          // Insights LLM : ≥3 concurrents + écart ≤500% pour éviter les faux positifs.
          // GARDE-FOU UNITÉ : la médiane marché est en FCFA — ne comparer que des
          // montants FCFA SGCI (jamais un TAUX_% comme '2,4%' contre 70 754 F).
          // PLANCHER ABSOLU 100 F : un vrai frais bancaire ≥ ~100 F. On exclut les
          // valeurs aberrantes (« 0,003 F », « 3 F », « 2,4 F ») qui produisaient des
          // « -100% / économie » absurdes dans l'analyse IA.
          const _sgM=+sgciInfo?.montant;
          // FIABILITÉ : si les prix de la ligne sont trop dispersés (max > 6× min = appariement
          // hétérogène / valeur aberrante, ex. « Port lettre » 1000 vs 20000), la médiane est
          // trompeuse → on EXCLUT ce service des insights (pas de « 90% moins cher » bidon).
          const _rowUnreliable=_fc.length>=2 && _fc[_fc.length-1] > _fc[0]*6;
          if(sgciInfo?.montant&&sgciInfo.tv==='MONTANT_FCFA'&&!sgciInfo.suspect
             &&_sgM>=100&&mkt&&mkt>=100&&svc.n_conc_presents>=3&&!_isAber(_sgM)&&!_rowUnreliable){
            const pct=Math.round((_sgM-mkt)/mkt*100);
            if(pct>=25&&pct<=500)insights_plus.push({lib:svc.libelle,pct,sgci:_sgM,mkt});
            else if(pct<=-20)insights_moins.push({lib:svc.libelle,pct:Math.abs(pct),sgci:_sgM,mkt});
          }
        });
      });
    });

    html+=`</tbody></table></div>
<div style="margin-top:8px;font:400 10px var(--sans);color:var(--faint)">
  Prix en FCFA · <span style="background:#D1FAE5;color:#047857;padding:1px 5px;border-radius:3px;font-weight:700">vert</span> = le moins cher de la ligne (ou gratuit) · <span style="background:#FEE2E2;color:#B91C1C;padding:1px 5px;border-radius:3px;font-weight:700">rouge</span> = le plus cher · <span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-weight:700;font-style:italic">réf. CB</span> = valeur douteuse (se référer à la grille source) · — = service absent · le code couleur n'apparaît que sur les lignes à ≥ 3 prix comparables.
</div>
</div>
<div id="rp-view-recap" style="display:none">${_rpRecapHTML(recap)}</div>`;

    // Enrichir payload LLM avec les insights les plus frappants
    insights_plus.sort((a,b)=>b.pct-a.pct);
    insights_moins.sort((a,b)=>b.pct-a.pct);
    if(window._q6LlmPayload){
      window._q6LlmPayload.sgci_plus_cher=insights_plus.slice(0,5).map(i=>`${i.lib} (+${i.pct}% : ${i.sgci.toLocaleString('fr-FR')} F vs moy. marché ${i.mkt.toLocaleString('fr-FR')} F)`).join(' | ');
      window._q6LlmPayload.sgci_moins_cher=insights_moins.slice(0,5).map(i=>`${i.lib} (−${i.pct}% : ${i.sgci.toLocaleString('fr-FR')} F vs moy. marché ${i.mkt.toLocaleString('fr-FR')} F)`).join(' | ');
      window._q6LlmPayload.n_services_compares=sections.reduce((t,sec)=>t+sec.sous_sections.reduce((t2,ss)=>t2+ss.services.filter(_hasComparable).length,0),0);
    }
    box.innerHTML=html;
    _fireQ6LLM();
  }catch(e){
    box.innerHTML=`<p style="font:500 12px var(--sans);color:#FF4D4D">Erreur comparatif prix : ${e.message}</p>`;
  }
}


// ── Bouton "Approfondir IA" (LLM optionnel, zéro token si non cliqué) ───────
async function _cbApprofondirIA(qId){
  const col=_AX_COLS[qId-1];
  const k=`${qId}_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
  const btn=document.getElementById(`cb-ia-btn-${qId}`);
  const box=document.getElementById(`cb-ia-box-${qId}`);
  if(!btn||!box)return;
  if(_CB_IA_CACHE[k]){
    const vis=box.style.display!=="none";
    box.style.display=vis?"none":"block";
    btn.textContent=vis?"◆ Approfondir →":"▲ Masquer l'analyse";
    return;
  }
  btn.disabled=true;btn.textContent="Analyse stratégique en cours…";
  box.style.display="block";
  box.innerHTML=`<div style="display:flex;gap:10px;align-items:center;padding:12px 0;color:var(--muted)"><div class="spin"></div><span style="font:500 11px var(--sans)">Analyse en cours…</span></div>`;
  try{
    const qs=`q=${qId}&annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}`;
    const r=await fetch(`/api/analyse_strategique?${qs}`);
    if(!r.ok)throw new Error(`HTTP ${r.status}`);
    const d=await r.json();
    const html=_mdToHtml(d.reponse||d.error||"Aucune réponse.");
    _CB_IA_CACHE[k]=html;
    box.innerHTML=`<div style="padding:12px 0;border-top:1px solid var(--line)">${html}</div>`;
    btn.textContent="▲ Masquer l'analyse";btn.disabled=false;
  }catch(e){
    box.innerHTML=`<div style="padding:10px 0;font:500 11px var(--sans);color:#FF4D4D">⚠️ Analyse indisponible — ${e.message}</div>`;
    btn.textContent="◆ Approfondir →";btn.disabled=false;
  }
}
function _cbIAButton(qId){
  const col=_AX_COLS[qId-1];
  return`<div style="margin-top:18px;border-top:1px solid var(--line);padding-top:12px">
    <button id="cb-ia-btn-${qId}" onclick="_cbApprofondirIA(${qId})" style="font:600 10px var(--sans);color:${col};border:1px solid ${col}40;background:${col}0d;border-radius:6px;padding:7px 15px;cursor:pointer;letter-spacing:.04em;transition:background .15s" onmouseover="this.style.background='${col}22'" onmouseout="this.style.background='${col}0d'">◆ Approfondir →</button>
    <div id="cb-ia-box-${qId}" style="display:none;margin-top:4px"></div>
  </div>`;
}

// ── Barre sticky ──────────────────────────────────────────────────────────────
function _cbStickyBar(){
  const seg=(s,lbl,icon)=>`<button class="${CB_SEG===s?'on':''}" onclick="setCBSeg('${s}')" style="display:inline-flex;align-items:center;gap:5px"><span style="font:800 12px var(--mono)">${icon}</span>${lbl}</button>`;
  // Onglets de navigation par section — MÊME design/disposition que Santé Financière
  const _cbNav=[["①","Catalogue","cb-ax-1"],["②","Innovations","cb-ax-2"],["③","Exclusivités","cb-ax-3"],
                ["④","Manques","cb-ax-5"],["⑤","Prix","cb-ax-6"]]
    .map(([n,l,id],i)=>`<button class="sec-nav-btn" data-sec="${id}" onclick="_paneShow('cb','${id}')">${n} ${l}</button>`).join("");
  return`<div style="position:sticky;top:116px;z-index:20;margin-bottom:var(--s5,16px);padding:6px 0;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--bg-deep) 72%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span style="font:700 9px var(--sans);color:var(--accent-2);letter-spacing:.1em;text-transform:uppercase">🏦 Conditions de Banques</span>
      <div class="seg" style="margin:0">${seg("Particuliers","Particuliers","◐")}${seg("Entreprises","Entreprises","◆")}</div>
      <div class="seg" style="margin:0">${CB_ANNEES.map(String).map(y=>`<button class="${CB_YEAR===y?'on':''}" onclick="setCBYear('${y}')">${y}</button>`).join("")}</div>
      <div class="seg" style="margin:0">${_cbSemsDispo(CB_YEAR).map(sm=>`<button class="${CB_SEM===sm?'on':''}" onclick="setCBSem('${sm}')">${sm}</button>`).join("")}</div>
      <div class="seg" style="margin:0">${_cbNav}</div>
      ${btnPDF("Benchmark Concurrentiel")}
    </div>
  </div>`;
}

/* ── Glossaire CB (mêmes styles que Santé Financière) ─────────────────────── */
const GLOSSAIRE_CB = [
  {cat:"Catalogue & offre"},
  {acronym:"Rang catalogue", name:"Position SGCI par nombre de services publiés", tag:"perf",
   def:"<b>Définition :</b> classement des 7 banques par <b>nombre de services tarifés distincts</b> publiés.<br><br><b>Comment on l'obtient :</b> <code>COUNT(DISTINCT libellé)</code> sur les vraies lignes de service (en-têtes exclus, libellé 8–110 caractères, types MONTANT/GRATUIT/TAUX/SUR_DEMANDE), pour le filtre (année, semestre, segment) choisi. On classe par ce nombre décroissant.<br><br><b>Comment lire :</b> ex. SGCI #4/7 en 2026 S1 Particuliers (184 services). C'est la <b>largeur de l'offre</b>, PAS la cherté.<br><br><b>Limite :</b> dépend de la complétude d'extraction de la plaquette."},
  {acronym:"Taux de gratuité", name:"Part des services gratuits", tag:"perf",
   def:"<b>Définition :</b> % de services facturés 0 F.<br><br><b>Comment on l'obtient :</b> (nb lignes gratuites ÷ nb lignes totales) × 100, sur les vraies lignes de service.<br><br><b>Comment lire :</b> SGCI 19,7% vs médiane marché ~31% → SGCI offre moins de gratuités que le marché."},
  {cat:"Prix"},
  {acronym:"Médiane marché", name:"Prix médian des concurrents par service", tag:"prix",
   def:"<b>Définition :</b> pour un service donné, la <b>médiane</b> des prix FCFA des banques concurrentes qui le proposent.<br><br><b>Comment on l'obtient :</b> appariement sémantique du libellé SGCI ↔ libellé concurrent, puis médiane des montants FCFA (≥ 2 concurrents requis, plancher 100 F pour exclure les artefacts).<br><br><b>Pourquoi médiane :</b> robuste aux valeurs extrêmes. On ne mélange jamais % et FCFA."},
  {acronym:"Compétitivité prix", name:"Win-rate : qui est le plus souvent le moins cher", tag:"prix",
   def:"<b>Définition :</b> % de services où une banque est ≤ à la médiane marché (un service gratuit gagne toujours).<br><br><b>Comment on l'obtient :</b> panier de services <b>réellement comparables</b> (présents chez ≥ 3 banques) ; pour chacun, la banque « gagne » si son prix ≤ médiane ; win-rate = victoires ÷ présences. Classement décroissant.<br><br><b>Comment lire :</b> ex. SGCI #3 (68,8%) en 2026 S1 Particuliers → moins chère que la médiane sur ~69% de ses services comparables. Complète le rang catalogue (largeur), ici on mesure la <b>cherté</b>."},
  {acronym:"réf. CB", name:"Valeur douteuse → se référer à la grille source", tag:"prix",
   def:"<b>Définition :</b> badge affiché quand un montant est <b>aberrant</b> (ex. « 0,003 F », « 3 F », ou > 12× la médiane de la ligne) — presque toujours un artefact d'extraction (un % ou un OCR pris pour un prix).<br><br><b>Pourquoi :</b> on préfère signaler « réf. CB » plutôt que d'afficher un faux chiffre. Ces valeurs sont aussi exclues des médianes et des analyses IA."},
  {cat:"Différenciation"},
  {acronym:"Exclusivités SGCI", name:"Services que SGCI seule propose", tag:"excl",
   def:"<b>Définition :</b> service SGCI <b>sans équivalent</b> chez les 6 concurrents.<br><br><b>Comment on l'obtient :</b> 1) normalisation <b>canonique</b> des libellés (synonymes unifiés : « tenue » = « gestion de compte », « virement » = « transfert » ; pluriels) ; 2) pré-filtre : on garde les services SGCI sans correspondant canonique/textuel chez un concurrent ; 3) garde-fou final (similarité ≥ 0,72 ⇒ rejeté) ; 4) filtre anti-bruit OCR. <b>Dans les deux sens</b> (un « manque » = service concurrent absent chez SGCI).<br><br><b>Comment lire :</b> ex. PACK DIASPORA, retrait sans carte (CONNECT). « Exclusif » est vérifié sur les données ; « inimitable » reste un jugement (voir fiches ℹ)."},
  {acronym:"🏷️ marque / ✅ sans équivalent", name:"Comment on juge une exclusivité (validation Agent Web)", tag:"excl",
   def:"<b>On ne se fie pas qu'à la grille tarifaire</b> : « absent de la plaquette d'un concurrent » ≠ « il ne l'offre pas ». Chaque candidat est confronté au web, d'où deux verdicts :<br><br>🏷️ <b>marque</b> = la <b>fonction</b> existe ailleurs sous un autre nom ; seul le produit/nom SGCI diffère (ex. <i>retrait sans carte</i> → aussi chez BNI/UBA/Ecobank).<br>✅ <b>sans équivalent</b> = aucun concurrent trouvé (grille <b>+ web</b>) → exclusivité <b>plausible, non certifiée</b> (l'absence de preuve n'est pas une preuve d'absence).<br><br><b>Inimitable</b> = jugement argumenté (barrière réglementaire, marque, réseau), pas une preuve — presque jamais absolu."},
  {acronym:"Manques (gaps)", name:"Services concurrents absents chez SGCI", tag:"excl",
   def:"<b>Définition :</b> service présent chez un concurrent et <b>absent</b> du catalogue SGCI (même logique canonique que les exclusivités, inversée).<br><br><b>Comment lire :</b> ce sont les pistes d'enrichissement de l'offre SGCI."},
  {acronym:"VRIST", name:"Indice qualitatif d'avantage concurrentiel (5 axes)", tag:"vrist",
   def:"<b>Définition :</b> note /10 par axe — <b>V</b>aleur · <b>R</b>areté · <b>I</b>nimitable · <b>S</b>ustainable (durable) · <b>T</b>ransformatif. Index de positionnement, PAS une mesure comptable.<br><br><b>Comment on l'obtient (règles linéaires transparentes, ∈ 1..10) :</b><br>• V = 2 + 8·min(n,50)/50 (n = nb d'exclusivités)<br>• R = 5 + 5·min(n,40)/40<br>• I = (7 si axe régulé, sinon 4) + 3·min(nAxes,8)/8<br>• S = 10·nSec/9 (sections BCEAO couvertes)<br>• T = 3 + 7·nGrat/n (intensité de gratuité)<br>Global = moyenne des 5.<br><br><b>Comment lire :</b> radar de forces/faiblesses. L'axe <b>Inimitable</b> est un jugement argumenté (barrière réglementaire / partenariat / réseau / marque) — rarement absolu."},
  {cat:"Cadre"},
  {acronym:"Axes BCEAO", name:"8 familles de classement des services", tag:"struct",
   def:"<b>Définition :</b> Packages · Cartes · Épargne · Crédits · Assurances · Digital/Paiements · Marchés · Autres.<br><br><b>Comment on l'obtient :</b> chaque service est rattaché à un axe par règles de mots-clés (déterministe). Permet d'organiser exclusivités, manques et analyses par domaine."},
  {acronym:"Médiane vs moyenne", name:"Pourquoi on privilégie la médiane", tag:"prix",
   def:"<b>Médiane</b> = valeur centrale, insensible aux extrêmes ; <b>moyenne</b> = sensible aux valeurs aberrantes. En tarifaire bancaire (quelques prix très élevés), la médiane reflète mieux « le marché »."},
];

function _injectGlossaireCB(){
  if(document.getElementById("gloss-drawer-cb")) return;
  const overlay=document.createElement("div");
  overlay.id="gloss-overlay-cb"; overlay.className="gloss-overlay";
  overlay.onclick=()=>toggleGlossCB(false);
  document.body.appendChild(overlay);
  const tagLabel={perf:"Catalogue",prix:"Prix",excl:"Différenciation",vrist:"VRIST",struct:"Cadre"};
  const body=GLOSSAIRE_CB.map(t=>{
    if(t.cat) return `<div class="gloss-cat">${t.cat}</div>`;
    return `<div class="gloss-term" onclick="this.classList.toggle('expanded')">
      <div class="gloss-term-hdr">
        <span class="gloss-acronym">${t.acronym}</span>
        <span class="gloss-name">${t.name}</span>
        <span class="gloss-chev">›</span>
      </div>
      <div class="gloss-term-body"><div class="gloss-tag ${t.tag||''}">${tagLabel[t.tag]||t.tag}</div>${t.def}</div>
    </div>`;
  }).join("");
  const drawer=document.createElement("div");
  drawer.id="gloss-drawer-cb"; drawer.className="gloss-drawer";
  drawer.innerHTML=`
    <div class="gloss-head">
      <div>
        <div style="font:700 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent-2);margin-bottom:6px">SpyBusiness</div>
        <h2>Glossaire — Conditions de banque</h2>
        <div style="font:500 12px var(--sans);color:var(--muted);margin-top:4px">Chaque indicateur CB expliqué + comment on l'obtient</div>
      </div>
      <button class="close-btn" onclick="toggleGlossCB(false)">✕</button>
    </div>
    <div class="gloss-body">${body}</div>`;
  document.body.appendChild(drawer);
}

function toggleGlossCB(force){
  _injectGlossaireCB();
  const drawer=document.getElementById("gloss-drawer-cb");
  const overlay=document.getElementById("gloss-overlay-cb");
  const open=force!==undefined?force:!drawer.classList.contains("open");
  drawer.classList.toggle("open",open);
  overlay.classList.toggle("open",open);
  document.body.style.overflow=open?"hidden":"";
}

/* ── Glossaire STRATÉGIE (mêmes styles que EF/CB) ─────────────────────────── */
const GLOSSAIRE_STRAT = [
  {cat:"Performance financière (EF)"},
  {acronym:"PNB", name:"Produit Net Bancaire", tag:"perf",
   def:"<b>Définition :</b> le « chiffre d'affaires » d'une banque = intérêts nets + commissions nettes + autres produits.<br><br><b>Comment lire :</b> plus il est élevé, plus la banque génère de revenus d'activité. SGCI a le PNB le plus élevé du marché."},
  {acronym:"Résultat net (RN)", name:"Le profit final", tag:"perf",
   def:"<b>Définition :</b> ce qui reste APRÈS toutes les charges, provisions et impôts. C'est le PROFIT, pas la taille (≠ total bilan).<br><br><b>Comment lire :</b> SGCI est #1 en RN (le plus gros profit du marché)."},
  {acronym:"ROE", name:"Rentabilité des capitaux propres", tag:"perf",
   def:"<b>Définition :</b> Résultat net ÷ capitaux propres. « Pour 100 F mis par les actionnaires, combien de profit ? »<br><br><b>Comment lire :</b> ROE élevé = capital bien rentabilisé. SGCI a un ROE moyen MALGRÉ sa taille → c'est le paradoxe (frein = coût du risque)."},
  {acronym:"Coût du risque (% PNB)", name:"Pertes sur crédits", tag:"perf",
   def:"<b>Définition :</b> part du PNB absorbée par les créances douteuses / impayés.<br><br><b>Comment lire :</b> PLUS BAS = mieux. SGCI ~17% = le PIRE du marché → son frein n°1. À ne JAMAIS comparer avec la marge nette (indicateurs différents)."},
  {acronym:"Coefficient d'exploitation", name:"Efficacité de gestion", tag:"perf",
   def:"<b>Définition :</b> charges d'exploitation ÷ PNB.<br><br><b>Comment lire :</b> PLUS BAS = PLUS efficient. Une banque à 38% est mieux gérée qu'une à 51%. SGCI est très efficiente sur ce plan (d'où le paradoxe du ROE)."},
  {acronym:"Marge nette", name:"Profit / revenus", tag:"perf",
   def:"<b>Définition :</b> Résultat net ÷ PNB = combien de profit pour 100 F de revenus.<br><br><b>Comment lire :</b> SIB a la meilleure marge nette du marché (modèle Attijariwafa : sélection prudente du risque)."},
  {acronym:"Ratio crédits/dépôts", name:"Transformation des dépôts", tag:"perf",
   def:"<b>Définition :</b> crédits accordés ÷ dépôts collectés.<br><br><b>Comment lire :</b> ~80-100% = équilibre sain (BCEAO). Trop bas (ex. 55%) = la banque prête peu (très prudente, ex. BICICI) ; trop haut = liquidité tendue. SGCI ~88% = zone idéale."},
  {acronym:"Croissance / parts de marché", name:"Rythme de progression", tag:"perf",
   def:"<b>Définition :</b> vitesse à laquelle le résultat net augmente sur 3 ans (AN1→AN3).<br><br><b>Comment lire :</b> être #1 en taille MAIS grandir moins vite que les concurrents (« en queue de peloton » = parmi les plus lents) → on PERD lentement des parts de marché, l'avance se réduit."},
  {cat:"Concurrence & prix (CB)"},
  {acronym:"Médiane marché", name:"Prix central des concurrents", tag:"prix",
   def:"<b>Définition :</b> pour un service donné, le prix médian des banques concurrentes (robuste aux valeurs extrêmes).<br><br><b>Comment lire :</b> on compare le prix SGCI à cette médiane pour savoir si SGCI est chère ou non sur ce service."},
  {acronym:"Win-rate prix", name:"% de services où SGCI est la moins chère", tag:"prix",
   def:"<b>Définition :</b> sur le panier de services comparables, la PART où SGCI est ≤ à la médiane marché (elle « gagne le duel de prix »).<br><br><b>Comment lire :</b> ex. #5/7 (56,8%) = SGCI n'est la moins chère que dans 56,8% des cas → compétitivité prix perfectible."},
  {acronym:"Exclusivités", name:"Services que SGCI seule propose", tag:"excl",
   def:"<b>Définition :</b> service SGCI sans équivalent chez les 6 concurrents (ex. PACK DIASPORA).<br><br><b>Comment lire :</b> arguments d'acquisition uniques à mettre en avant (Marketing)."},
  {acronym:"Manques (gaps)", name:"Services concurrents absents chez SGCI", tag:"excl",
   def:"<b>Définition :</b> service présent chez ≥3 concurrents mais PAS chez SGCI.<br><br><b>Comment lire :</b> pistes d'enrichissement de l'offre (Innovation)."},
  {acronym:"Repricing", name:"Ajustement ciblé des prix/taux", tag:"prix",
   def:"<b>Définition :</b> revoir un tarif ou un taux de façon CIBLÉE (jamais en bloc).<br><br><b>Règle DG :</b> sur les segments PEU sensibles au prix, toujours accompagné d'un gain de service. JAMAIS doubler un prix ni casser une barrière de sortie."},
  {acronym:"Élasticité-prix", name:"Sensibilité du client au prix", tag:"prix",
   def:"<b>Définition :</b> à quel point un client change de comportement si le prix bouge.<br><br><b>Comment lire :</b> FAIBLE élasticité = on peut ajuster le prix sans perdre le client → cible idéale d'un repricing."},
  {acronym:"Barrière de sortie", name:"Frein au départ du client", tag:"prix",
   def:"<b>Définition :</b> coût/friction qui retient un client (ex. attestation de non-redevance chère, frais de clôture/transfert).<br><br><b>Comment lire :</b> ces prix élevés sont VOULUS — on ne les baisse pas, ils protègent la base de clients."},
  {acronym:"Tarification différenciée", name:"Gratuit digital / payant agence", tag:"prix",
   def:"<b>Définition :</b> rendre un service gratuit sur l'appli et payant en agence.<br><br><b>Pourquoi :</b> on capte de la marge en réduisant le coût de délivrance, SANS augmenter le prix perçu par le client (modèle DG « Repricing & Valeur Digitale »)."},
  {cat:"Cadres d'analyse"},
  {acronym:"5 forces de Porter", name:"Pression concurrentielle", tag:"struct",
   def:"<b>Définition :</b> les 5 pressions sur une banque : rivalité entre banques (centre), pouvoir des clients, pouvoir des fournisseurs (ressources/BCEAO), menace de nouveaux entrants, produits de substitution (mobile money).<br><br><b>Comment lire :</b> le schéma en croix montre où la pression est la plus forte → où concentrer la stratégie."},
  {acronym:"VRIST", name:"Avantage durable (5 axes /10)", tag:"vrist",
   def:"<b>Définition :</b> note /10 par axe — <b>V</b>aleur, <b>R</b>areté, <b>I</b>nimitable, <b>S</b>ustainable (durable), <b>T</b>ransformatif.<br><br><b>Comment lire :</b> mesure si un avantage TIENDRA dans le temps. On compare SGCI à un concurrent, dimension par dimension, avec les « drivers » (preuves chiffrées) qui expliquent chaque note."},
  {acronym:"SWOT", name:"Forces / Faiblesses / Opportunités / Menaces", tag:"struct",
   def:"<b>Définition :</b> synthèse en 4 cases qui JUSTIFIE les décisions : chaque décision répond à une faiblesse à corriger ou une opportunité à saisir."},
  {cat:"Sources (chaque chiffre est tracé)"},
  {acronym:"EF", name:"États financiers", tag:"vrist",
   def:"Données comptables réelles publiées : PNB, RN, ROE, coût du risque, coefficient, marge, croissance."},
  {acronym:"CB", name:"Conditions de banque", tag:"vrist",
   def:"Grilles tarifaires publiées : prix des services, gratuités, exclusivités, manques, win-rate prix."},
  {acronym:"REGL", name:"Réglementation BCEAO", tag:"vrist",
   def:"Textes réglementaires UMOA/BCEAO : gratuités obligatoires, ratios prudentiels…"},
  {acronym:"WEB", name:"Faits externes sourcés", tag:"vrist",
   def:"Faits sectoriels fiables (BCEAO, APBEF-CI, classements UMOA, rapports annuels) — chacun daté et cité."},
];

function _injectGlossaireStrat(){
  if(document.getElementById("gloss-drawer-strat")) return;
  const overlay=document.createElement("div");
  overlay.id="gloss-overlay-strat"; overlay.className="gloss-overlay";
  overlay.onclick=()=>toggleGlossStrat(false);
  document.body.appendChild(overlay);
  const tagLabel={perf:"Finances",prix:"Prix",excl:"Différenciation",vrist:"Cadre/Source",struct:"Cadre"};
  const body=GLOSSAIRE_STRAT.map(t=>{
    if(t.cat) return `<div class="gloss-cat">${t.cat}</div>`;
    return `<div class="gloss-term" onclick="this.classList.toggle('expanded')">
      <div class="gloss-term-hdr">
        <span class="gloss-acronym">${t.acronym}</span>
        <span class="gloss-name">${t.name}</span>
        <span class="gloss-chev">›</span>
      </div>
      <div class="gloss-term-body"><div class="gloss-tag ${t.tag||''}">${tagLabel[t.tag]||t.tag}</div>${t.def}</div>
    </div>`;
  }).join("");
  const drawer=document.createElement("div");
  drawer.id="gloss-drawer-strat"; drawer.className="gloss-drawer";
  drawer.innerHTML=`
    <div class="gloss-head">
      <div>
        <div style="font:700 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent-2);margin-bottom:6px">SpyBusiness</div>
        <h2>Glossaire — Stratégie</h2>
        <div style="font:500 12px var(--sans);color:var(--muted);margin-top:4px">Chaque terme de l'analyse stratégique, expliqué simplement</div>
      </div>
      <button class="close-btn" onclick="toggleGlossStrat(false)">✕</button>
    </div>
    <div class="gloss-body">${body}</div>`;
  document.body.appendChild(drawer);
}

function toggleGlossStrat(force){
  _injectGlossaireStrat();
  const drawer=document.getElementById("gloss-drawer-strat");
  const overlay=document.getElementById("gloss-overlay-strat");
  const open=force!==undefined?force:!drawer.classList.contains("open");
  drawer.classList.toggle("open",open);
  overlay.classList.toggle("open",open);
  document.body.style.overflow=open?"hidden":"";
}

/* ── Onglet GLOSSAIRE CONTEXTUEL (sidebar) : ouvre le glossaire de la PAGE active ──
   CB → glossaire CB · Stratégie → glossaire Stratégie · Santé financière/Analyse/Rapports → glossaire SF. */
function toggleGlossContext(){
  let p = "apercu";
  try{ p = localStorage.getItem("sb-page") || "apercu"; }catch(e){}
  if(p==="cb") toggleGlossCB();
  else if(p==="strategie") toggleGlossStrat();
  else toggleGloss();
}

/* Encadré "◆ Analyse" — même codes visuels que la page Santé financière
   (texte explicatif en langage clair, pas un empilement de chiffres bruts).
   TRANSPARENCE : ce texte est un calcul déterministe (comptage/comparaison des
   tarifs), PAS une génération LLM — contrairement aux autres blocs "Analyse"
   du dashboard qui, eux, viennent d'un vrai appel Groq/Gemini. Précisé
   explicitement pour ne pas laisser croire à une analyse IA (trouvé le
   2026-07-14 lors d'un audit de transparence demandé par l'utilisateur). */
function _cbAnalyse(txt){
  return`<div style="margin-top:12px;padding:13px 16px;background:rgba(56,209,240,.06);border-left:3px solid #38D1F0;border-radius:0 8px 8px 0">
    <div style="font:700 9px var(--sans);text-transform:uppercase;letter-spacing:.08em;color:#38D1F0;margin-bottom:6px">◆ Analyse — en clair <span style="opacity:.6;text-transform:none;letter-spacing:0">(calcul automatique, pas IA)</span></div>
    <div style="font:500 12.5px/1.65 var(--sans);color:var(--ink)">${txt}</div></div>`;
}
function pageCB(){return CB_SEG==="Particuliers"?pageCBPar():pageCBEnt();}

function pageCBPar(){
  return`${_cbStickyBar()}
  <div id="cb-main-content" style="padding-top:8px">
    <div style="display:flex;gap:12px;align-items:center;padding:50px;justify-content:center;color:var(--muted)">
      <div class="spin"></div><span>Chargement des tarifs publiés…</span>
    </div>
  </div>`;
}

function pageCBEnt(){
  return`${_cbStickyBar()}
  <div id="cb-main-content" style="padding-top:8px">
    <div style="display:flex;gap:12px;align-items:center;padding:50px;justify-content:center;color:var(--muted)">
      <div class="spin"></div><span>Chargement des tarifs publiés…</span>
    </div>
  </div>`;
}


/* ── Comparaison par SECTIONS et SOUS-SECTIONS BCEAO (I-IX) ─────────────
   Axe central de l'analyse demandée par la DG : les grilles tarifaires
   des banques utilisent des libellés et découpages différents pour des
   services équivalents (ex. SGCI "Conditions générales des comptes" vs
   BACI "Conditions générales du compte") — une comparaison libellé à
   libellé est mécaniquement bancale et produit des trous "Non disponible".
   Les 9 sections canoniques du référentiel BCEAO (I à IX), elles, sont
   communes aux 7 banques (cf. dash_app/cb_sections.py) — et leurs
   sous-sections, déterminées par contenu (cf. dash_app/cb_subsections.py),
   respectent la granularité réelle des documents sources : c'est l'axe de
   rapprochement retenu. Ordre d'affichage des banques dans les classements
   ci-dessous. Données depuis /api/cb_par_sous_section. */
let CB_BANK_ORDER=["SGCI","BACI","BICICI","BNI","ECOBANK","NSIA","SIB"];   // fallback — SYNCHRONISÉ depuis CB_BANKS (dynamique)
// Recompose l'ordre d'affichage CB (SGCI d'abord, puis concurrents alpha) depuis la liste DYNAMIQUE
// CB_BANKS. Appelé par app.data.js/loadAll() une fois CB_BANKS chargé → nouvelle banque propagée partout.
function _syncBankOrder(){
  try{
    if(typeof CB_BANKS!=='undefined' && Array.isArray(CB_BANKS) && CB_BANKS.length){
      CB_BANK_ORDER = ["SGCI", ...CB_BANKS.filter(b=>b!=="SGCI")];
    }
  }catch(e){}
}

/* Description en français courant de chaque section canonique — pour
   qu'un lecteur non-spécialiste comprenne IMMÉDIATEMENT ce que la
   section recouvre, sans avoir à deviner depuis le titre officiel BCEAO. */
const CB_SECTION_DESC={
  "I":"Les frais de base pour ouvrir et faire vivre un compte au quotidien : tenue de compte, carte bancaire, RIB, relevés.",
  "II":"Les opérations courantes les plus fréquentes : virements, prélèvements, chéquiers, alertes SMS.",
  "III":"Les services et démarches bancaires ponctuelles : attestations, recherches de documents, copies, certifications.",
  "IV":"La banque à distance : abonnement internet/mobile, notifications SMS, relevés électroniques, applications.",
  "V":"Les frais appliqués en cas d'incident : chèque rejeté, découvert non autorisé, mise en demeure, opposition.",
  "VI":"L'achat et la vente de devises étrangères (opérations de change).",
  "VII":"Les prêts et crédits : frais de dossier, garanties, assurances emprunteur, gestion du crédit.",
  "VIII":"Les opérations avec l'étranger : virements internationaux, SWIFT, transferts UEMOA.",
  "IX":"Tous les autres services qui ne rentrent dans aucune des huit familles précédentes.",
};

/* ── Lecture correcte d'une médiane de section absente ─────────────────
   "montant_median = null" NE VEUT PAS DIRE "donnée manquante" : le plus
   souvent, cela signifie que toutes les lignes tarifées de cette section
   sont GRATUITES (pct_gratuit proche de 100) — une information réelle et
   souvent FAVORABLE à SGCI, pas un trou. Afficher un simple "—" dans ce
   cas masque l'info et fabrique une fausse impression de "données man-
   quantes" (cf. retour DG : "BCP DE VALEURS MANQUANTES"). On distingue
   donc 3 cas bien réels :
     1. Banque absente de la section (n_lignes=0)      → "Absent du catalogue"
     2. Toutes les lignes sont gratuites (pct_gratuit≈100, sans montant)
                                                          → "100% gratuit" (positif, vert)
     3. Des lignes existent, payantes, mais sans montant capté à l'extraction
                                                          → "Tarif sur conditions"      */
function _cbSectionValue(info){
  if(!info||!info.n_lignes)return{kind:"absent",label:"Absent du catalogue",color:"var(--faint)"};
  if(info.montant_median!=null)return{kind:"montant",label:Math.round(info.montant_median).toLocaleString("fr-FR")+" F",color:null};
  if((info.pct_gratuit||0)>=80)return{kind:"gratuit",label:(info.pct_gratuit===100?"100% gratuit":Math.round(info.pct_gratuit)+"% gratuit"),color:"#22C55E"};
  return{kind:"inconnu",label:"Tarif sur conditions",color:"var(--faint)"};
}

/* En-dessous de ce nombre de lignes tarifées (MONTANT_FCFA), une moyenne
   par section n'est pas représentative — elle mélange des montants de
   nature différente (frais fixes, plafonds de crédit, commissions...)
   et produit des écarts artificiels (ex. 2 lignes "frais de dossier crédit"
   à 500k/1M F vs des commissions à 0-15k F : +34000% qui ne reflète aucun
   positionnement réel). On exclut ces cas du calcul de risques/leviers —
   la table de comparaison brute, elle, reste affichée intégralement. */
const CB_SECTION_MIN_ECHANTILLON=3;
/* Au-delà d'un facteur ~20x entre deux médianes de section, l'écart ne
   reflète plus un positionnement prix réel mais une composition de
   catalogue hétérogène (ex. BACI classe quelques frais administratifs
   ponctuels à 10-50 F dans une section où SGCI ne publie que des
   tarifs de service à 13 200 F : "+87900%" ne veut rien dire pour la
   décision). On exclut ces paires du calcul de risques/leviers — la
   table de comparaison brute reste, elle, affichée intégralement. */
const CB_SECTION_RATIO_MAX=20;

async function _loadAndRenderCB(){
  const box=document.getElementById("cb-main-content");
  if(!box)return;
  const myTok=++_cbToken;   // ce rendu devient le rendu courant

  // Squelette immédiat avec spinners
  box.innerHTML=`
  <div class="story" style="padding-bottom:8px">
    <div class="kicker">SpyBusiness · Benchmark Concurrentiel · ${CB_YEAR} ${CB_SEM} · ${CB_SEG}</div>
    <h1>7 banques. <span class="hl">Données réelles.</span></h1>
    <p>Comparaison exhaustive des grilles tarifaires publiées — 9 sections BCEAO, validation sémantique, mis à jour à chaque semestre.</p>
  </div>

  <div class="bento" style="margin-bottom:8px">
    <div class="tile c3 tpad" style="text-align:center">
      <div style="font:800 32px/1 var(--display);letter-spacing:-.04em;color:var(--green);font-variant-numeric:tabular-nums" id="cb-hkpi-excl">—</div>
      <div style="font:700 9px/1.4 var(--sans);color:var(--muted);margin-top:8px;text-transform:uppercase;letter-spacing:.09em">Exclusivités<br>SGCI</div>
    </div>
    <div class="tile c3 tpad" style="text-align:center">
      <div style="font:800 32px/1 var(--display);letter-spacing:-.04em;color:var(--gold);font-variant-numeric:tabular-nums" id="cb-hkpi-rang">—</div>
      <div style="font:700 9px/1.4 var(--sans);color:var(--muted);margin-top:8px;text-transform:uppercase;letter-spacing:.09em">Rang<br>catalogue</div>
    </div>
    <div class="tile c3 tpad" style="text-align:center">
      <div style="font:800 32px/1 var(--display);letter-spacing:-.04em;color:var(--accent-2);font-variant-numeric:tabular-nums" id="cb-hkpi-vrist">—</div>
      <div style="font:700 9px/1.4 var(--sans);color:var(--muted);margin-top:8px;text-transform:uppercase;letter-spacing:.09em">Taux<br>gratuité</div>
    </div>
    <div class="tile c3 tpad" style="text-align:center">
      <div style="font:800 32px/1 var(--display);letter-spacing:-.04em;color:var(--cyan);font-variant-numeric:tabular-nums" id="cb-hkpi-grat">—</div>
      <div style="font:700 9px/1.4 var(--sans);color:var(--muted);margin-top:8px;text-transform:uppercase;letter-spacing:.09em">Services<br>gratuits</div>
    </div>
  </div>

  <div id="cb-synthese" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px"></div>

  <div class="cb3">
  ${[1,2,3,5,6].map(i=>`<div id="cb-ax-${i}" style="margin-bottom:4px">
    <div style="min-height:80px;display:flex;align-items:center;justify-content:center;gap:12px;color:var(--muted)">
      <div class="spin"></div><span style="font:500 13px var(--sans)">Chargement…</span>
    </div>
  </div>`).join('')}
  <div id="cb-conclusion-content" style="margin-top:8px"></div>
  </div>`;

  /* MODE ONGLETS ARMÉ TOUT DE SUITE (2026-08-10, signalé par le directeur : « au chargement
     tous les onglets sont affichés sur une page »).

     _paneInit était appelé APRÈS le chargement des cinq sections. Pendant toute la durée des
     requêtes — plusieurs secondes, davantage sur l'instance hébergée — les cinq sections
     restaient donc visibles l'une sous l'autre, chacune avec son « Chargement… ». On voyait
     une longue page qui se remplissait par morceaux, puis qui se repliait brutalement sur un
     seul onglet. D'où l'impression d'une navigation lente et d'un affichage désordonné.

     Armé AVANT les requêtes, on ne voit qu'une section, celle du premier onglet, et son
     chargement. C'est la même durée, mais elle se lit. */
  _paneInit('cb', ['cb-ax-1','cb-ax-2','cb-ax-3','cb-ax-5','cb-ax-6']);

  // Fetch données SQL (sans LLM) en parallèle
  const fetchData=async(qId)=>{
    const key=qId<=2?`${qId}_${CB_SEG}`:`${qId}_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
    if(_CB_DATA_CACHE[key])return _CB_DATA_CACHE[key];
    const qs=`q=${qId}&annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}`;
    const r=await fetch(`/api/cb_strat_data?${qs}`);
    if(!r.ok){const t=await r.text();throw new Error(`HTTP ${r.status} — ${t.slice(0,80)}`);}
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    _CB_DATA_CACHE[key]=d;
    return d;
  };

  const renderers=[_renderQ1,_renderQ2,_renderQ3,_renderQ4,_renderQ5,_renderQ6];

  // Onglet VRIST (Q4) retiré — 1,2,3,5,6 seulement (les noms internes _renderQ4/cb-ax-4 restent
  // utilisés ailleurs, on saute juste ce numéro dans les boucles pour ne rien casser).
  await Promise.all([1,2,3,5,6].map(async qId=>{
    const el=document.getElementById(`cb-ax-${qId}`);
    if(!el)return;
    try{
      const srcId=qId===2?1:qId;
      const data=await fetchData(srcId);
      if(!_cbAlive(myTok))return;           // filtre changé entre-temps → on abandonne
      // ON NE PEUT PLUS EFFACER TOUT LE STYLE ICI. Le mode onglets est désormais armé AVANT
      // les requêtes : chaque section masquée porte un « display:none » posé par _paneShow.
      // Un removeAttribute('style') l'emportait avec le reste, et la section réapparaissait
      // au moment précis où elle finissait de charger — les cinq se rallumaient donc une à
      // une, ce qui annulait exactement ce qu'on venait de corriger.
      const _garde = el.style.display;
      el.removeAttribute("style");
      if(_garde) el.style.display = _garde;
      el.innerHTML=renderers[qId-1](data)+_cbIAButton(qId);
      if(qId===1){_fireQ1LLM();setTimeout(()=>{try{_renderEvolutionTemporelle();}catch(e){}},30);}
      if(qId===2)setTimeout(()=>{try{_renderRattrapage();}catch(e){}},40);
      if(qId===3)_fireQ3LLM();
      if(qId===5)_fireQ5LLM();
      if(qId===6){_fireQ6SubSectionComparison();_fireQ6PrixCompetitivite();}
    }catch(e){
      if(el)el.innerHTML=`<div style="color:#FF4D4D;font:500 11px var(--sans);padding:20px">Erreur Q${qId} — ${e.message}</div>`;
    }
  }));

  // ── Mode ONGLETS : n'afficher que la section sélectionnée ──
  _paneInit('cb', ['cb-ax-1','cb-ax-2','cb-ax-3','cb-ax-5','cb-ax-6']);

  // Background : deltas sémantiques des 6 banques concurrentes (SGCI déjà dans ev)
  // Le serveur préchauffe ce cache au démarrage (~13s) → quasi-instantané dès la 1ère requête
  (async()=>{
    try{
      const seg=encodeURIComponent(CB_SEG);
      const r=await fetch(`/api/cb_evolutions_all?segment=${seg}`);
      if(!r.ok||!_cbAlive(myTok))return;
      const evAll=await r.json();
      if(evAll.error||!_cbAlive(myTok))return;
      const k1=`1_${CB_SEG}`;
      if(_CB_DATA_CACHE[k1]){
        _CB_DATA_CACHE[k1].evolutions_all=evAll;
        const el1=document.getElementById('cb-ax-1');
        if(el1){el1.innerHTML=renderers[0](_CB_DATA_CACHE[k1])+_cbIAButton(1);_fireQ1LLM();setTimeout(()=>{try{_renderEvolutionTemporelle();}catch(e){}},30);}
        const el2=document.getElementById('cb-ax-2');
        if(el2){el2.innerHTML=renderers[1](_CB_DATA_CACHE[k1])+_cbIAButton(2);_fireQ2MarketLLM();_fireQ2InnoLLM();setTimeout(()=>{try{_renderRattrapage();}catch(e){}},40);}
      }
      // Cross-segment : l'autre segment est déjà dans le cache serveur (préchauffe démarrage)
      const otherSegCross=CB_SEG==='Particuliers'?'Entreprises':'Particuliers';
      const r2=await fetch(`/api/cb_evolutions_all?segment=${encodeURIComponent(otherSegCross)}`);
      if(!r2.ok||!_cbAlive(myTok))return;
      const evOtherData=await r2.json();
      if(evOtherData.error||!_cbAlive(myTok))return;
      const k1b=`1_${CB_SEG}`;
      if(_CB_DATA_CACHE[k1b]){
        _CB_DATA_CACHE[k1b].evolutions_cross={segment:otherSegCross,data:evOtherData};
        const el2b=document.getElementById('cb-ax-2');
        if(el2b){el2b.innerHTML=renderers[1](_CB_DATA_CACHE[k1b])+_cbIAButton(2);_fireQ2MarketLLM();_fireQ2InnoLLM();setTimeout(()=>{try{_renderRattrapage();}catch(e){}},40);}
        // Déclencher l'analyse LLM des concurrents maintenant que toutes les données sont prêtes
        _fireQ2LLM();
      }
    }catch(e){}
  })();

  // Mise à jour des KPIs du header depuis les données cachées
  try{
    if(!_cbAlive(myTok))return;           // filtre changé → ne pas écraser les KPIs du nouveau rendu
    // Q3 = services exclusifs SGCI (pas de champ banque, tous les rows sont SGCI)
    const k3=`3_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
    const d3=_CB_DATA_CACHE[k3];
    const nExcl=Array.isArray(d3)?d3.length:0;
    const nGratExcl=Array.isArray(d3)?d3.filter(r=>r.est_gratuit).length:0;
    const nSecExcl=Array.isArray(d3)?new Set(d3.map(r=>(r.section||'').charAt(0)).filter(Boolean)).size:0;

    // Q6 = benchmark marché (a un champ banque + n_services + n_gratuit)
    const k6=`6_${CB_YEAR}_${CB_SEM}_${CB_SEG}`;
    const d6=_CB_DATA_CACHE[k6];
    const sgci6=Array.isArray(d6)?d6.find(r=>r.banque==='SGCI'):null;
    const nAll=+(sgci6?.n_services||0);
    const nGrat=+(sgci6?.n_gratuit||nGratExcl||0);

    // KPI4 = Taux de gratuité SGCI — 100% vérifiable depuis cb_tarifs (n_gratuit / n_services).
    // Remplace l'ancien "Score VRIST" qui était une formule arbitraire (√nAll·1,05…) sans
    // fondement, donc trompeuse pour la DG. Le % de gratuité est une donnée réelle et actionnable.
    const pctGrat = (sgci6 && +sgci6.n_services>0)
      ? (sgci6.pct_gratuit!=null ? +sgci6.pct_gratuit : +(nGrat/nAll*100).toFixed(1))
      : null;

    const exclEl=document.getElementById('cb-hkpi-excl');
    const gratEl=document.getElementById('cb-hkpi-grat');
    const vristEl=document.getElementById('cb-hkpi-vrist');
    if(exclEl)exclEl.textContent=nExcl||'—';
    if(gratEl)gratEl.textContent=nGrat||'—';
    if(vristEl)vristEl.textContent=pctGrat!=null?(pctGrat.toFixed(1).replace('.',',')+'%'):'—';

    let rangCatG=0,byCatG=[];
    if(d6&&Array.isArray(d6)){
      // Rang catalogue : position SGCI par nombre de services (plus grand = rang 1)
      byCatG=[...d6].filter(r=>+(r.n_services||0)>0).sort((a,b)=>+(b.n_services||0)-+(a.n_services||0));
      rangCatG=byCatG.findIndex(r=>r.banque==='SGCI')+1;
      const rangEl=document.getElementById('cb-hkpi-rang');
      if(rangEl&&rangCatG>0)rangEl.textContent='#'+rangCatG+'/'+byCatG.length;
    }

    // ── Cockpit DG — synthèse exécutive (100% dérivée des données, varie par filtre) ──
    _renderCockpitDG({nExcl,nGratExcl,pctGrat,d6,rangCat:rangCatG,byCat:byCatG});
  }catch(e){}
}

// Synthèse exécutive compacte : Atout #1 · Menace #1 · Action prioritaire.
function _renderCockpitDG({nExcl,nGratExcl,pctGrat,d6,rangCat,byCat}){
  const host=document.getElementById('cb-synthese');
  if(!host)return;
  const card=(col,tag,txt)=>`<div style="background:var(--bg-tile,#fff);border:1px solid var(--line);border-left:3px solid ${col};border-radius:8px;padding:9px 12px">
    <div style="font:700 9px var(--sans);color:${col};text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px">${tag}</div>
    <div style="font:500 11.5px/1.45 var(--sans);color:var(--ink)">${txt}</div></div>`;
  // Atout #1 : exclusivités SGCI
  const atout=`<b>${nExcl||0}</b> services exclusifs absents des 6 concurrents${nGratExcl?` · dont <b>${nGratExcl}</b> gratuits`:''}.`;
  // Menace #1 : concurrent le plus offensif sur la gratuité (offres gratuites = capture clients)
  let menace='Pas de menace concurrentielle saillante sur cette période.';
  if(Array.isArray(d6)){
    const conc=d6.filter(r=>r.banque!=='SGCI'&&+(r.n_services||0)>0);
    const topGrat=[...conc].sort((a,b)=>+(b.pct_gratuit||0)-+(a.pct_gratuit||0))[0];
    const topCat=[...conc].sort((a,b)=>+(b.n_services||0)-+(a.n_services||0))[0];
    if(topGrat&&+(topGrat.pct_gratuit||0)>(pctGrat||0))
      menace=`<b>${topGrat.banque}</b> pousse <b>${(+topGrat.pct_gratuit).toFixed(0)}%</b> d'offres gratuites (vs ${(pctGrat||0).toFixed(0)}% SGCI) — pression sur les clients sensibles au prix.`;
    else if(topCat)
      menace=`<b>${topCat.banque}</b> a le catalogue le plus large (<b>${topCat.n_services}</b> services) — couverture de besoins supérieure.`;
  }
  // Action prioritaire : déduite du positionnement réel
  let action='Capitaliser sur les exclusivités en communication clients.';
  const meds=Array.isArray(d6)?d6.map(r=>+(r.pct_gratuit||0)).filter(v=>v>0).sort((a,b)=>a-b):[];
  const medGrat=meds.length?meds[Math.floor(meds.length/2)]:0;
  if(pctGrat!=null&&medGrat&&pctGrat<medGrat-2)
    action=`Relever le taux de gratuité : <b>${pctGrat.toFixed(0)}%</b> vs médiane marché <b>${medGrat.toFixed(0)}%</b>.`;
  else if(rangCat>3)
    action=`Élargir le catalogue : SGCI <b>#${rangCat}/${byCat.length}</b> en profondeur d'offre.`;
  else if(nExcl)
    action=`Valoriser les <b>${nExcl}</b> exclusivités (atout différenciant) auprès des cibles patrimoniales/entreprises.`;
  host.innerHTML=card('var(--green,#1D9E75)','✓ Atout #1',atout)
    +card('var(--red,#E53935)','⚠ Menace #1',menace)
    +card('var(--gold,#FF9800)','➔ Action prioritaire',action);
}

// Vue évolution temporelle SGCI 2024 → 2026 (rendue à l'ouverture du panneau, compacte).
let _evoRendered=null;
async function _renderEvolutionTemporelle(){
  const host=document.getElementById('cb-evo-content');
  if(!host||host.dataset.done==='1')return;
  const tk=_cbToken;
  try{
    const r=await fetch(`/api/cb_serie_temporelle?segment=${encodeURIComponent(CB_SEG)}`);
    const data=await r.json();
    if(!_cbAlive(tk))return;
    if(!Array.isArray(data)||data.length<2){host.innerHTML='<div style="color:var(--faint);font:500 11px var(--sans);padding:6px 0">Données temporelles insuffisantes.</div>';return;}
    const x=data.map(d=>d.periode), rang=data.map(d=>d.sgci_rang);
    const grat=data.map(d=>d.sgci_pct_grat), gratM=data.map(d=>d.marche_pct_grat);
    const nb=data[data.length-1].nb_banques;
    // 2 graphes SÉPARÉS = lisibilité humaine (ne jamais mélanger rang 1-7 et % sur un même axe)
    host.innerHTML=`
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px">
        <div style="border:1px solid var(--line);border-radius:8px;padding:8px 10px">
          <div style="font:700 11.5px var(--sans);color:#E67E00;margin-bottom:1px">📉 Classement catalogue SGCI</div>
          <div style="font:500 9.5px var(--sans);color:var(--faint);margin-bottom:4px">Position parmi 7 banques · plus la ligne est HAUTE, mieux c'est (#1 = leader)</div>
          <div id="cb-evo-rang" style="height:195px"></div>
        </div>
        <div style="border:1px solid var(--line);border-radius:8px;padding:8px 10px">
          <div style="font:700 11.5px var(--sans);color:#12895C;margin-bottom:1px">💚 Taux de gratuité : SGCI vs marché</div>
          <div style="font:500 9.5px var(--sans);color:var(--faint);margin-bottom:4px">% de services gratuits · ligne verte = SGCI · pointillés = médiane des 7 banques</div>
          <div id="cb-evo-grat" style="height:195px"></div>
        </div>
      </div>
      <div id="cb-evo-note" style="margin-top:12px"></div>`;
    const _baseLayout={paper_bgcolor:'transparent',plot_bgcolor:'transparent',height:195,
      font:{family:'Inter,sans-serif',size:11,color:'#888'},xaxis:{tickfont:{size:10.5},fixedrange:_IS_TOUCH}};
    if(window.Plotly){
      // Graphe 1 — Rang (échelle 1→7 inversée, # sur l'axe)
      Plotly.newPlot('cb-evo-rang',[
        {x,y:rang,mode:'lines+markers+text',text:rang.map(v=>'#'+v),textposition:'top center',cliponaxis:false,
         textfont:{size:15,color:'#E67E00',family:'Inter,sans-serif'},
         line:{color:'#FF8C00',width:4},marker:{size:12,color:'#FF8C00'},
         hovertemplate:'%{x} : rang %{text}/'+nb+'<extra></extra>'}
      ],{...structuredClone(_baseLayout),margin:{t:16,b:26,l:34,r:12},showlegend:false,
        yaxis:{range:[nb+0.6,0.4],dtick:1,tickprefix:'#',tickfont:{size:11},gridcolor:'rgba(150,150,150,.18)',zeroline:false,fixedrange:_IS_TOUCH}
      },{responsive:true,displayModeBar:false,scrollZoom:!_IS_TOUCH,staticPlot:_REAL_TOUCH});
      // Graphe 2 — Gratuité SGCI vs médiane marché (même axe %)
      Plotly.newPlot('cb-evo-grat',[
        {x,y:grat,name:'SGCI',mode:'lines+markers+text',text:grat.map(v=>Math.round(v)+'%'),textposition:'bottom center',cliponaxis:false,
         textfont:{size:13,color:'#12895C',family:'Inter,sans-serif'},
         line:{color:'#1D9E75',width:4},marker:{size:10,color:'#1D9E75'}},
        {x,y:gratM,name:'Médiane marché',mode:'lines+markers+text',text:gratM.map(v=>Math.round(v)+'%'),textposition:'top center',cliponaxis:false,
         textfont:{size:12,color:'#7E8CA0',family:'Inter,sans-serif'},
         line:{color:'#94A3B8',width:2.2,dash:'dot'},marker:{size:7,color:'#94A3B8'}}
      ],{...structuredClone(_baseLayout),margin:{t:16,b:38,l:34,r:12},
        legend:{orientation:'h',y:-0.24,font:{size:10.5}},
        yaxis:{ticksuffix:'%',range:[0,Math.max(...gratM,...grat)*1.35],tickfont:{size:11},gridcolor:'rgba(150,150,150,.18)',zeroline:false,fixedrange:_IS_TOUCH}
      },{responsive:true,displayModeBar:false,scrollZoom:!_IS_TOUCH,staticPlot:_REAL_TOUCH});
    }
    // ── Analyse dynamique métier (aide à la décision) ──
    const f=data[0],l=data[data.length-1],dR=f.sgci_rang-l.sgci_rang;
    const worst=data.reduce((a,b)=>b.sgci_rang>a.sgci_rang?b:a);
    const gap=Math.round(l.sgci_pct_grat-l.marche_pct_grat);
    const li=(c,t)=>`<li style="margin-bottom:4px;padding-left:2px"><span style="color:${c};font-size:13px;vertical-align:middle">●</span> ${t}</li>`;
    const rangTxt=dR>0?`<b style="color:var(--green)">progression de ${dR} place${dR>1?'s':''}</b>`:dR<0?`<b style="color:var(--red)">recul de ${-dR} place${-dR>1?'s':''}</b>`:'<b>stabilité</b>';
    const decision=gap<-3
      ? `Renforcer la gratuité sur les services à fort volume (chèques, virements, cartes) pour combler l'écart de <b>${Math.abs(gap)} pts</b> et retenir les clients sensibles au prix.`
      : (l.sgci_rang>3
         ? `Élargir le catalogue pour remonter au classement (actuellement <b>#${l.sgci_rang}/${l.nb_banques}</b>), en priorité sur les axes où les concurrents sont plus complets.`
         : `Maintenir la position et capitaliser sur les exclusivités SGCI en communication clients.`);
    document.getElementById('cb-evo-note').innerHTML=`
      <div style="font:700 10px var(--sans);color:var(--accent-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">📊 Analyse — aide à la décision DG</div>
      <ul style="margin:0;padding-left:6px;list-style:none;font:500 12.5px/1.6 var(--sans);color:var(--ink)">
        ${li('#FF8C00',`<b>Rang catalogue</b> : ${rangTxt} sur la période — de #${f.sgci_rang} à <b>#${l.sgci_rang}/${l.nb_banques}</b>${worst.sgci_rang!==l.sgci_rang?` (creux à #${worst.sgci_rang} en ${worst.periode})`:''}.`)}
        ${li('#1D9E75',`<b>Gratuité</b> : SGCI à <b>${Math.round(l.sgci_pct_grat)}%</b> contre une médiane marché de <b>${Math.round(l.marche_pct_grat)}%</b> → ${gap<0?`<b style="color:var(--red)">${Math.abs(gap)} pts sous le marché</b> : les concurrents offrent davantage de services gratuits`:`<b style="color:var(--green)">au niveau ou au-dessus du marché</b>`}.`)}
        ${li('#E53935',`<b>Décision prioritaire</b> : ${decision}`)}
      </ul>`;
    _evoRendered=CB_SEG; host.dataset.done='1';
  }catch(e){host.innerHTML='<div style="color:#FF4D4D;font:500 11px var(--sans)">Erreur évolution : '+e.message+'</div>';}
}

function afterCB(){
  window.__redraw=()=>go("cb");
  _loadAndRenderCB();
}


/* ════════════ STRATÉGIE OPÉRATIONNELLE ═══════════════════════════════════
   VEILLE STRATÉGIQUE AUGMENTÉE — les six questions d'un comité de direction.

   Trois versions ont été rejetées avant celle-ci. Ce qui manquait à la dernière,
   selon le cadrage du directeur : « la vraie question d'un DG n'est pas *que dois-je
   faire* mais *quel sera le retour sur investissement* ». D'où, sur chaque carte :
   l'enjeu, le business case chiffré, les risques, le coût de l'inaction, la fenêtre
   de tir et une synthèse — en plus des décisions.

   Markup repris de l'onglet Stratégie (tuile `c6` à liseré, « DÉCISION n » avec badge
   d'effort) pour que les deux onglets se lisent comme un seul produit.
   ═════════════════════════════════════════════════════════════════════════ */
const _SO_EFFCOL  = {"Faible":"#12895C","Moyen":"#B45309","Élevé":"#E53935"};
const _SO_PRIOCOL = {"Très élevée":"#E53935","Élevée":"#B45309","Moyenne":"#0AA1DD","Faible":"#64748B"};
// Les clés « cacao » et « anacarde » ont fusionné en « agro » le 2026-07-30 (elles produisaient
// deux fois la même décision de crédit de campagne). Quatre secteurs non agricoles les ont
// rejointes : la liste ne comptait que des filières agricoles, du numérique et deux transverses,
// et ne disait rien des commerçants — pourtant le cœur du segment CLIPRO de la grille SGCI.
const _SO_ICONES  = {agro:"🌱", commerce:"🏪", transport:"🚛", import_export:"🚢", btp:"🏗️",
                     numerique:"📱", pme:"🏭", conformite:"🛡️"};
// DIRECTION AFFICHÉE PAR DÉFAUT (2026-08-07) : la première de la liste, soit la Direction
// Financière. L'onglet s'ouvrait auparavant sur « toutes directions », c'est-à-dire sur rien
// en particulier — le lecteur devait d'abord choisir avant de voir quoi que ce soit.
let _SO_DATA = null, _SO_DIR = null;

function pageStratOp(){
  // EN-TÊTE COMPACT — la classe .hero impose min-height:290px et justify-content:space-between,
  // conçus pour une page à gros chiffre, pills et sparkline. Ici il n'y a qu'un titre : l'espace
  // se répartissait dans le vide et donnait un large bandeau à moitié rempli. On écrit donc un
  // en-tête sobre, à la hauteur de son contenu.
  return `
  <div style="padding:20px 0 4px">
    <div style="font:800 11px var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--accent-2)">
      Directives opérationnelles</div>
    <h1 style="font:900 30px/1.15 var(--display);margin:8px 0 5px;color:var(--ink)">Ce que chaque direction doit faire</h1>
    <p style="font:400 14.5px/1.6 var(--sans);color:var(--muted);max-width:700px;margin:0">
      La stratégie globale fixe le but ; cette page dit <b>comment</b> l'atteindre, direction par direction.
      Quatre directives chacune, chiffrées sur les grilles tarifaires publiées et les états financiers,
      et rattachées à un <b>signal de marché</b> — indicateur sectoriel, politique ou réglementaire, ou
      événement relevé par la veille.
      <span id="so-periode" style="color:var(--faint)"></span></p>
  </div>
  <div id="so-body"><div style="font:500 13px var(--sans);color:var(--muted);padding:22px 0;display:flex;gap:10px;align-items:center">
    <span class="spin"></span> Analyse des signaux de marché…</div></div>`;
}

async function afterStratOp(){
  // PORTÉE (2026-08-07). L'en-tête annonçait « Veille stratégique · 2026 S1 · Particuliers »,
  // ce qui laissait croire que l'analyse ne valait que pour ce découpage — alors qu'elle
  // mobilise tout l'historique chargé et que la période affichée n'est qu'un repère de
  // fraîcheur. Le libellé est désormais rempli par le serveur, à partir de ce qu'il a
  // réellement utilisé, et se lit comme une note de bas de page et non comme un filtre.
  const per = document.getElementById("so-periode");
  if(per) per.textContent = "";
  const box = document.getElementById("so-body");
  if(!box) return;
  try{ _SO_DATA = await (await fetch(`/api/strategie_operationnelle?annee=${CB_YEAR}&semestre=${CB_SEM}&segment=${encodeURIComponent(CB_SEG)}`)).json(); }
  catch(e){ _SO_DATA = null; }
  _soRender();
}

function setSoDir(d){ _SO_DIR = d; _soRender(); }

/* ── DIRECTIVES PAR DIRECTION ────────────────────────────────────────────────────────
   Le cœur de la page depuis le 2026-08-07. Elles viennent de dash_app/directives.py, qui
   les compose à partir des données sans passer par le modèle de langage : elles sont donc
   TOUJOURS là, au complet, même quand le budget de jetons est fermé.

   Un onglet par direction, quatre cartes dans chacun. Pas de vue « toutes directions » :
   un directeur vient chercher ce qui le concerne, pas un inventaire. */
// `sect` est un helper LOCAL à _soRender ; il est passé en paramètre plutôt que dupliqué,
// pour que les trois sections de la page gardent exactement la même présentation.
/* ── L'ÉCART MESURÉ, EN TÊTE DE CARTE ────────────────────────────────────────────────
   Ajouté le 2026-08-09. Reproche du directeur : « les recommandations sont ambiguës, je ne
   vois en rien le lien avec la stratégie et les problèmes de la SGCI ». Les cartes ouvraient
   sur un constat descriptif — « 3 services sont facturés sous la médiane » — qui décrit sans
   situer : le lecteur voyait une observation, jamais un problème, et n'avait donc aucune
   raison d'agir. La première ligne porte désormais le RANG de la banque et son écart à celui
   qui fait mieux.

   Cinq natures, cinq couleurs, parce qu'un retard et une avance ne se lisent pas de la même
   façon et qu'un aplat unique les aurait confondus. « avance » est volontairement présent :
   sur le coefficient d'exploitation, la SGCI est PREMIÈRE, et présenter cela comme un retard
   serait faux. */
const _SO_ENJEU = {
  retard:      {c:"#B45309", f:"Écart au marché"},
  alerte:      {c:"#B91C1C", f:"Risque mesuré"},
  avance:      {c:"#15803D", f:"Avantage mesuré"},
  opportunite: {c:"#1565C0", f:"Gisement mesuré"},
  masse:       {c:"#4338CA", f:"Masse en jeu"}
};
function _soEnjeu(e){
  if(!e || !e.texte) return "";
  const s = _SO_ENJEU[e.nature] || _SO_ENJEU.retard;
  return `<div style="display:flex;align-items:baseline;gap:8px;margin:0 0 7px;padding:7px 11px;
    background:${s.c}14;border-left:3px solid ${s.c};border-radius:0 6px 6px 0">
    <span style="font:800 9.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;
      color:${s.c};white-space:nowrap">${s.f}</span>
    <span style="font:700 12px/1.5 var(--sans);color:var(--ink)">${_soEsc(e.texte)}</span></div>`;
}

/* ── LE PLAN, ANNÉE PAR ANNÉE ────────────────────────────────────────────────────────
   Ajouté le 2026-08-10, sur une remarque du directeur : « la globale c'est sur 3 ans hein.
   Je me demande si on ne doit pas faire aussi sur 3 ans l'opérationnelle ».

   Il avait raison, et le manque était plus profond qu'un affichage : la Stratégie globale
   porte DÉJÀ une feuille de route An 1 / An 2 / An 3, avec un thème et des actes chiffrés
   pour chacune, et l'opérationnelle recommandait vingt directives sans jamais dire à quelle
   année elles servaient. Trois d'entre elles font pourtant exactement ce que la globale
   demande. Le lien existait ; il n'était écrit nulle part.

   Rien n'est réparti à la main : chaque directive porte un horizon d'exécution réel (3 à
   24 mois), on ne fait que le lire. Le thème vient de la globale, il n'est pas recopié.

   CE QUE LE TABLEAU MONTRE, ET QU'IL NE FAUT PAS ADOUCIR : le plan est déséquilibré. L'An 1
   concentre seize directives pour un dixième de la valeur ; quatre directives d'An 2 en
   portent près de la moitié ; l'An 3 est VIDE, aucune directive n'allant au-delà de 24 mois.
   Un tableau qui masquerait cela serait plus flatteur et sans usage. */
function _soPhasage(b){
  const ph = (b && b.phasage) || [];
  if(!ph.length) return "";
  const fr = v => String(v).replace(".", ",");
  const vide = (b.annees_sans_directive||[]).length;
  const lignes = ph.map(p=>{
    const creux = !p.n_directives;
    const large = Math.max(0, Math.min(100, p.part_pct||0));
    return `<div style="display:grid;grid-template-columns:74px 1fr 128px;gap:11px;align-items:center;
        padding:8px 0;border-top:1px solid var(--line)">
      <div>
        <div style="font:800 13px var(--display);color:${creux?'#B45309':'var(--ink)'}">${p.libelle}</div>
        <div style="font:500 9.5px var(--sans);color:var(--faint)">${_soEsc(p.intervalle)}</div>
      </div>
      <div>
        <div style="font:600 11.5px/1.5 var(--sans);color:${creux?'#B45309':'var(--ink)'}">
          ${creux ? "Aucune directive — le plan ne va pas jusque-là"
                  : `${p.n_directives} directive(s) · ${_soEsc((p.directions||[]).map(x=>x.replace("Direction ","")).join(", "))}`}</div>
        ${p.theme_globale?`<div style="font:500 10.5px/1.45 var(--sans);color:var(--faint);margin-top:2px">
          <b style="color:var(--accent-2)">Stratégie globale</b> · ${_soEsc(p.theme_globale)}</div>`:""}
        <div style="height:5px;border-radius:3px;background:var(--line);overflow:hidden;margin-top:5px">
          <div style="height:100%;width:${large}%;background:${creux?'#B45309':'var(--accent-2)'}"></div></div>
      </div>
      <div style="text-align:right">
        <div style="font:800 13px var(--mono);color:${creux?'#B45309':'var(--ink)'}">${fr(p.somme_mds)} Mds</div>
        <div style="font:600 10px var(--mono);color:var(--faint)">${fr((p.part_pct||0).toFixed(1))} % de l'écart</div>
      </div>
    </div>`;
  }).join("");
  return `<div style="margin-top:12px;padding-top:4px">
    <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:2px">
      Répartition sur la trajectoire à 3 ans</div>
    ${lignes}
    ${vide?`<div style="margin-top:9px;padding:8px 11px;background:#B4530914;border-left:3px solid #B45309;
      border-radius:0 6px 6px 0;font:500 11.5px/1.6 var(--sans);color:var(--ink)">
      <b>La troisième année ne reçoit aucune directive.</b> L'horizon le plus lointain est de
      24 mois : le plan opérationnel s'arrête avant le terme de la trajectoire qu'il sert.
      C'est un constat sur le plan, pas un défaut d'affichage.</div>`:""}</div>`;
}


/* BOUCLAGE DU PLAN — RENDU EN TETE DE PAGE (2026-08-11, demande du directeur).
   Il vivait au milieu de la section des directives, apres les onglets de direction. Or il ne
   parle d aucune direction en particulier : il dit si LE PLAN TIENT. Sa place est sous
   l objectif global, dont il est la reponse chiffree — on lit l ambition, puis aussitot ce
   qui la couvre et ce qui manque. Le lecteur n a plus a descendre pour savoir ou l on en est. */
function _soBouclage(d){
  const b = ((d||{}).directives||{}).bilan || {};
  if(!(b.ecart_mds && b.n_chiffrees)) return "";
  const couv = Math.max(0, Math.min(100, b.couverture_pct||0));
  const col = couv >= 90 ? "#15803D" : (couv >= 50 ? "#B45309" : "#B91C1C");
  const fr = v => String(v).replace(".", ",");
  return `<div class="tile c12 tpad" style="padding:13px 16px;margin-bottom:11px;border-left:3px solid ${col}">
      <div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:5px">
        <span style="font:800 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:${col}">Bouclage du plan</span>
        <span style="font:800 15px var(--display);color:var(--ink)">${fr(b.somme_mds)} Mds FCFA
          <span style="font-weight:600;color:var(--muted)">sur ${fr(b.ecart_mds)} Mds à combler</span></span>
        <span style="font:800 13px var(--mono);color:${col}">${fr(couv.toFixed(1))} %</span>
      </div>
      <div style="height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin-bottom:6px">
        <div style="height:100%;width:${couv}%;background:${col}"></div></div>
      <div style="font:500 11.5px/1.6 var(--sans);color:var(--muted)">
        ${b.n_chiffrees} des ${b.n_total} directives portent un apport chiffré <b>en ${_soEsc(b.unite||"PNB")}</b> ;
        les autres sont des conditions ou des défenses d'acquis, qui ne s'additionnent pas.
        <b style="color:var(--ink)">${fr(b.reste_mds)} Mds restent sans source identifiée</b> —
        c'est l'objet de la directive de bouclage de la Direction Financière.</div>
      ${_soPhasage(b)}</div>`;
}

function _soDirectives(d, sect, dossiersHtml){
  const D = (d.directives && d.directives.directives) || [];
  if(!D.length) return "";
  // Repli identique au helper de _soRender : la section des directives doit pouvoir se rendre
  // seule quand les dossiers sectoriels manquent, c'est-à-dire avant que ce helper n'existe.
  sect = sect || ((num,titre,enclair,inner)=>`<section style="scroll-margin-top:172px">
    <div style="display:flex;align-items:center;gap:10px;margin:22px 0 3px">
      <span style="font:900 21px var(--display);color:var(--accent-2)">${num}</span>
      <span style="font:800 19px var(--display);color:var(--ink)">${titre}</span></div>
    <div style="font:500 13px/1.6 var(--sans);color:var(--muted);background:var(--bg-raise);border-left:3px solid var(--accent-2);border-radius:0 7px 7px 0;padding:8px 12px;margin-bottom:13px">${enclair}</div>
    ${inner}</section>`);
  const dirs = (d.directives.directions) || [...new Set(D.map(x=>x.direction))];
  if(!_SO_DIR || !dirs.includes(_SO_DIR)) _SO_DIR = dirs[0];   // par défaut : la première

  const onglets = dirs.map(nom=>{
    const on = _SO_DIR===nom;
    const n = D.filter(x=>x.direction===nom).length;
    return `<button onclick="setSoDir('${nom.replace(/'/g,"\\'")}')" style="cursor:pointer;font:700 12px var(--sans);
      border-radius:9px;padding:9px 15px;margin:0 7px 7px 0;border:1px solid ${on?'var(--accent-2)':'var(--line)'};
      background:${on?'var(--accent-2)':'transparent'};color:${on?'#fff':'var(--muted)'}">
      ${nom.replace("Direction ","")} <span style="opacity:.65;font-weight:600">${n}</span></button>`;
  }).join("");

  const lot = D.filter(x=>x.direction===_SO_DIR);
  const ligne = (etiq, txt, gras) => txt ? `<div style="margin-top:7px">
      <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:2px">${etiq}</div>
      <div style="font:${gras?'600':'500'} 12.5px/1.62 var(--sans);color:var(--${gras?'ink':'muted'})">${_soEsc(txt)}</div></div>` : "";

  const cartes = lot.map(x=>`
    <div class="tile c6 tpad" style="border-top:3px solid ${x.lacune?'#B45309':'var(--accent-2)'};padding:15px 17px">
      <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:6px">
        <span style="font:900 20px var(--mono);color:${x.lacune?'#B45309':'var(--accent-2)'};line-height:1">${x.rang}</span>
        <div style="font:800 15px/1.32 var(--display);color:var(--ink);flex:1">${_soEsc(x.titre)}</div>
        ${x.annee_plan?`<span style="font:800 9.5px var(--sans);color:#fff;background:var(--accent-2);
          border-radius:5px;padding:2px 7px;white-space:nowrap" title="Année de la trajectoire à 3 ans que cette directive sert">An ${x.annee_plan}</span>`:""}
        <span style="font:700 9.5px var(--sans);color:${_SO_EFFCOL[x.effort]||'#64748B'};background:${(_SO_EFFCOL[x.effort]||'#64748B')}1a;
          border-radius:5px;padding:2px 7px;white-space:nowrap">${_soEsc(x.effort)} · ${_soEsc(x.horizon)}</span>
      </div>
      ${_soEnjeu(x.enjeu)}
      <div style="font:500 12.5px/1.65 var(--sans);color:var(--ink);background:var(--bg-raise);border-radius:7px;padding:10px 12px">
        ${_soEsc(x.constat)}</div>
      ${_soSignal(x.signal)}
      ${_soTerrain(x.terrain)}
      ${ligne("Ce qu'il faut faire", x.action, true)}
      ${x.premier_pas?`<div style="margin-top:7px;padding:7px 10px;background:var(--bg-raise);border-radius:6px;
        font:600 12px/1.5 var(--sans);color:var(--ink)">
        <span style="color:var(--accent-2);font-weight:800">▸ Sous 30 jours</span> ${_soEsc(x.premier_pas)}</div>`:""}
      ${ligne("Cible", x.cible)}
      ${ligne("Indicateur de suivi", x.indicateur)}
      <div style="margin-top:9px;padding-top:8px;border-top:1px solid var(--line)">
        <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:2px">Apport à l'objectif</div>
        <div style="font:600 12px/1.6 var(--sans);color:var(--ink)">${_soEsc(x.contribution)}</div></div>
      ${_soChatBtn(x)}
    </div>`).join("");

  /* LE PLAN S'ADDITIONNE-T-IL ? Une note qui recommande vingt actions sans jamais les
     totaliser laisse au lecteur le soin de vérifier qu'elle tient — et personne ne le fait.
     On affiche donc la somme des directives chiffrées face à l'objectif, et le reste À
     DÉCOUVERT. Le chiffre n'est pas flatteur, et c'est précisément l'information utile :
     il justifie la directive de bouclage de la Direction Financière. */

  const per = (d.directives.perimetre)||{};
  const pied = `<div class="tile c12 tpad" style="padding:11px 15px">
      <div style="font:500 11.5px/1.6 var(--sans);color:var(--faint)">
        ${per.n_services_comparables||0} services réellement comparables sur ${per.n_banques||7} banques,
        ${per.n_par_segment ? Object.entries(per.n_par_segment).map(([s,n])=>`${n} en ${_soEsc(s)}`).join(" et ") : ""} ·
        période de référence ${_soEsc(per.periode_reference||"")}.
        Directives calculées à partir des données, sans rédaction par modèle de langage : à données
        inchangées, le texte est identique.</div></div>`;

  // FUSION DES DEUX SECTIONS (2026-08-07, demande du directeur : « c'est un peu désorganisé,
  // on peut tout combiner de manière à avoir une section pour orienter chaque direction »).
  // Les directives et les dossiers de marché vivaient dans deux sections séparées, chacune
  // avec sa propre barre de filtres : un directeur devait choisir sa direction deux fois, à
  // deux endroits de la page, et faire lui-même le rapprochement entre ce qu'on lui demande
  // et la matière qui le justifie. Une seule barre commande désormais les deux.
  // Le bloc « dossiers de marché » a disparu (2026-08-07) : son contenu est maintenant DANS
  // chaque directive, via _soTerrain(). Le paramètre dossiersHtml est conservé pour ne pas
  // casser l'appelant, mais n'est plus rendu — deux blocs côte à côte obligeaient le lecteur
  // à faire lui-même le lien entre la décision et ce qui la justifie.
  return sect("①","Ce que chaque direction doit faire",
    "<b>Quatre directives par direction.</b> Chacune part d'un fait mesuré, dit sur quel terrain elle s'exerce et ce qu'il peut rapporter, puis quoi faire, sur quelle cible, et ce qui sera suivi.",
    `<div style="margin-bottom:11px">${onglets}</div><div class="bento">${cartes}</div>${pied}`);
}

function _soRender(){
  const box = document.getElementById("so-body"); if(!box) return;
  const d = _SO_DATA;
  if(!d){
    box.innerHTML = `<div class="tile c12 tpad"><div style="font:500 12.5px var(--sans);color:var(--muted)">
      Données indisponibles. Vérifier que le serveur répond, puis recharger.</div></div>`;
    return;
  }
  // Les directives ne dépendent pas des dossiers sectoriels : elles s'affichent même quand
  // la veille n'a rien remonté. C'est tout l'intérêt de les avoir rendues déterministes.
  if(!d.secteurs || !d.secteurs.length){
    box.innerHTML = _soDirectives(d) + `<div class="tile c12 tpad" style="margin-top:10px">
      <div style="font:500 12.5px var(--sans);color:var(--muted)">
      Aucun dossier sectoriel exploitable pour l'instant : relancer la veille sectorielle pour
      alimenter les signaux de marché. Les directives ci-dessus restent valides — elles sont
      calculées sur les grilles tarifaires et les états financiers.</div></div>`;
    return;
  }
  const eco = d.economie || {};
  const fM = v => v==null ? "—" : (Math.abs(v)>=1e9 ? (v/1e9).toFixed(1).replace(".",",")+" Md"
                : Math.abs(v)>=1e6 ? Math.round(v/1e6)+" M" : Math.round(v).toLocaleString("fr-FR"));

  // Les dossiers sectoriels sont désormais présentés en entier, sans filtre par direction :
  // ce filtre a migré vers les onglets de la section ①, qui portent les directives. Le
  // dédoubler ici obligeait à comprendre que deux commandes différentes agissaient sur deux
  // contenus différents — les dossiers documentent le marché, ils ne s'adressent pas à une
  // direction en particulier.
  // DOSSIERS RATTACHÉS À LA DIRECTION SÉLECTIONNÉE (2026-08-07). Les sept dossiers
  // s'affichaient sous chaque direction, ce qui vidait le filtre de son sens : le directeur
  // du Marketing voyait les mêmes dossiers que celui des Risques.
  //
  // Le rattachement s'appuie sur `directions_imposees`, décidé côté serveur à partir de la
  // NATURE du secteur — et non sur les décisions rédigées par le modèle, qui varient d'une
  // génération à l'autre et disparaissent quand le quota tombe. Un filtre ne peut pas
  // dépendre d'un texte qui peut ne pas exister.
  const visibles = d.secteurs.filter(s =>
    (s.directions_imposees || []).includes(_SO_DIR) || s.direction === _SO_DIR);
  const chips = "";

  // ①bis LES 4 DÉCISIONS PRIORITAIRES DE LA DIRECTION SÉLECTIONNÉE (2026-07-30)
  // Demande du directeur : « les 4 plus pertinentes toujours ». Filtrer une direction laissait
  // ses décisions éparpillées dans les cartes sectorielles, sans hiérarchie : le directeur
  // voyait six actions de poids apparemment égal et devait trier lui-même. Le classement est
  // CALCULÉ, jamais rédigé — trois critères dans cet ordre :
  //   1. l'opportunité du secteur (note déjà établie et exposée dans l'arbitrage) ;
  //   2. l'effort à fournir, à opportunité comparable — un effort faible se lance plus vite ;
  //   3. les commissions attendues, qui départagent le reste.
  // Le directeur peut donc contester le classement en contestant l'un des trois, plutôt que
  // d'avoir à croire un ordre décidé ailleurs.
  const _RANG_EFFORT = {"Faible":0, "Moyen":1, "Élevé":2};
  // Le panneau « 4 decisions prioritaires » (2026-07-30) a ete retire le 2026-08-07 : les
  // onglets par direction de la section 1 rendent le meme service, de facon exhaustive et
  // sans dependre du modele de langage. Garder les deux aurait affiche deux listes de
  // quatre elements, differentes, pour la meme direction.
  const priorisees = "";

  const lignes = d.secteurs.map(s=>{
    const col = _SO_PRIOCOL[s.priorite] || "#64748B";
    const bc = s.business_case;
    return `<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)">
      <span style="font:700 13.5px var(--sans);color:var(--ink);width:230px;flex-shrink:0">${_SO_ICONES[s.cle]||"◆"} ${s.nom}</span>
      <span style="font:700 15px var(--mono);color:#B45309;width:76px">${s.roi_libelle||""}</span>
      <span style="font:600 12.5px var(--sans);color:var(--muted);width:70px">${s.delai_libelle||"—"}</span>
      <span style="font:600 12.5px var(--sans);color:var(--muted);width:80px">${s.difficulte||"—"}</span>
      <span style="font:600 12.5px var(--mono);color:#12895C;width:118px;text-align:right">${bc?("+"+fM(bc.commissions_min_fcfa)+" à "+fM(bc.commissions_max_fcfa)):"—"}</span>
      <span style="font:800 11.5px var(--sans);color:${col};width:92px;text-align:right">${s.priorite}</span>
    </div>`;}).join("");

  // ② Les dossiers — une carte par secteur, six questions.
  const cartes = visibles.map(s=>{
    const col = _SO_PRIOCOL[s.priorite] || "#64748B";
    const bc = s.business_case;
    const bloc = (titre, txt, coul) => txt ? `<div style="margin-top:8px">
      <div style="font:700 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:${coul||'var(--faint)'};margin-bottom:3px">${titre}</div>
      <div style="font:500 12px/1.6 var(--sans);color:var(--muted)">${_soEsc(txt)}</div></div>` : "";

    // Les décisions rédigées par le modèle restent affichées EN ENTIER dans le dossier de
    // marché : elles documentent le secteur. Le filtrage par direction appartient désormais
    // aux directives de la section ①, qui sont exhaustives et toujours disponibles.
    const decisions = (s.decisions||[])
      .map((x,i)=>`
      <div style="margin-bottom:9px;padding-bottom:9px;border-bottom:1px solid var(--line)">
        <div style="font:800 12.5px/1.4 var(--sans);color:var(--ink);display:flex;gap:6px;flex-wrap:wrap">
          <span style="color:${col}">DÉCISION ${i+1}</span>
          <span style="font:700 9.5px var(--sans);color:var(--muted);background:var(--bg-raise);border-radius:4px;padding:2px 7px">${_soEsc(x.direction||"")}</span>
          <span style="margin-left:auto;font:700 9.5px var(--sans);color:${_SO_EFFCOL[x.effort]||'#64748B'};background:${(_SO_EFFCOL[x.effort]||'#64748B')}1a;border-radius:4px;padding:1px 6px;height:fit-content">Effort ${x.effort}</span></div>
        <div style="font:700 13px/1.5 var(--sans);color:var(--ink);margin:4px 0 5px">${_soEsc(x.titre)}</div>
        <div style="font:500 12px/1.6 var(--sans);color:var(--muted)">${_soEsc(x.detail)}</div>
        ${x.premier_pas?`<div style="margin-top:5px;padding:5px 8px;background:var(--bg-raise);border-radius:5px;font:600 11.5px/1.5 var(--sans);color:var(--ink)">
          <span style="color:${col};font-weight:800">▸ Premier pas (30 jours)</span> ${_soEsc(x.premier_pas)}</div>`:""}
      </div>`).join("") ||
      `<div style="font:500 10.5px var(--sans);color:var(--faint);padding:6px 0">Aucune décision pour cette direction.</div>`;

    // Business case — le chiffre ET ses hypothèses, faute de quoi il n'est pas arbitrable.
    const hyp = bc ? (bc.hypotheses||[]).map(h=>`<div style="display:flex;gap:7px;font:400 11px/1.7 var(--sans);color:var(--faint)">
        <span style="color:${h.nature==='calculé'?'#12895C':'#B45309'};font-weight:700">${h.nature==='calculé'?'calculé':'hypothèse'}</span>
        <span style="flex:1">${h.libelle}</span><span style="font-weight:600;color:var(--muted)">${h.valeur}</span></div>`).join("") : "";
    // HYPOTHÈSE AJUSTABLE EN SÉANCE (2026-07-30). Un business case dont on ne peut pas
    // contester l'hypothèse n'est pas un outil d'arbitrage : le comité subit le chiffre au
    // lieu de le discuter. Le curseur laisse chacun substituer sa propre estimation de
    // captation ; les montants se recalculent à l'écran, sans aller-retour serveur, puisque
    // le calcul est trivial (clients × commission moyenne réelle).
    const caseBloc = bc ? `<div style="margin-top:9px;padding:9px 11px;background:#0d7a500e;border:1px solid #12895C33;border-radius:7px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
          <span style="font:700 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:#0a5e3c">Impact estimé</span>
          <span style="margin-left:auto;font:700 10.5px var(--sans);color:var(--muted)">Confiance ${bc.confiance} %</span></div>
        <div id="so-mt-${s.cle}" style="font:800 15px/1.4 var(--sans);color:#0a5e3c">+${fM(bc.commissions_min_fcfa)} à +${fM(bc.commissions_max_fcfa)} FCFA de commissions/an</div>
        <div id="so-sub-${s.cle}" style="font:500 11.5px var(--sans);color:var(--muted);margin:2px 0 7px">
          ${bc.clients_min} à ${bc.clients_max} nouveaux clients · contribution au PNB ${bc.contribution_pnb_pct?("+"+bc.contribution_pnb_pct[0]+" à +"+bc.contribution_pnb_pct[1]+" %"):"—"} · horizon ${s.delai_libelle}</div>
        ${hyp}</div>` : "";

    // Événements de marché — la matière que le catalogue tarifaire ne peut pas donner :
    // un accord signé, un programme public lancé, une instruction publiée.
    const evts = (s.evenements||[]).length
      ? `<div style="margin-top:8px"><div style="font:700 8.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin-bottom:3px">Signaux récents du marché</div>
         ${s.evenements.map((e,i)=>`<div style="font:500 10.5px/1.5 var(--sans);color:var(--muted);margin-bottom:3px">
           <span style="color:${e.portee==='menace'?'#E53935':e.portee==='contrainte'?'#B45309':'#12895C'}">●</span>
           <b>${_soEsc(e.acteur)}</b> ${_soEsc(e.fait)}${e.montant?` <b>${_soEsc(e.montant)}</b>`:""}${e.date_citee?` <span style="color:var(--faint)">· ${_soEsc(e.date_citee)}</span>`:""}
           <b style="color:var(--accent-2)">[${(s.faits_sources||[]).length+i+1}]</b></div>`).join("")}</div>`
      : "";

    const conc = (s.concurrence||[]).length
      ? `<div style="margin-top:8px"><div style="font:700 8.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin-bottom:2px">Concurrence déjà en place</div>
         <div style="font:500 10.5px/1.5 var(--sans);color:var(--muted)">${s.concurrence.map(c=>`<b>${c.banque}</b> (${c.n_services} services)`).join(" · ")}</div></div>` : "";

    const indics = (s.indicateurs||[]).map(x=>
      `<span style="display:inline-block;font:500 11px var(--sans);color:var(--muted);background:var(--bg-raise);border-radius:5px;padding:3px 8px;margin:0 4px 4px 0">${x}</span>`).join("");
    // RÉFÉRENCES NUMÉROTÉES — faits de marché puis signaux de veille, dans l'ordre où les [n]
    // apparaissent dans la carte. Une note de comité doit se remonter à sa source en un clic.
    const refs = [].concat(
      (s.faits_sources||[]).map(f=>({lib:`${f.valeur}${f.source?" — "+f.source:""}`, url:f.url})),
      (s.evenements||[]).map(e=>({lib:`${e.acteur} — ${(e.fait||"").slice(0,64)}`, url:e.url}))
    ).filter(r=>r.lib);
    const src = refs.map((r,i)=>
      `<div style="font:400 11px/1.75 var(--sans);color:var(--faint)"><b style="color:var(--accent-2)">[${i+1}]</b> ${_soEsc(r.lib)}${r.url?` <a href="${r.url}" target="_blank" rel="noopener" style="color:var(--accent-2)">↗</a>`:""}</div>`).join("");

    return `<div class="tile c6 tpad" style="border-top:3px solid ${col}">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:5px">
        <span style="font-size:21px;line-height:1">${_SO_ICONES[s.cle]||"◆"}</span>
        <div style="flex:1"><div style="font:800 16px var(--display);color:${col}">${s.nom}</div>
        <div style="font:600 11.5px/1.4 var(--sans);color:var(--muted)">${s.cibles} · ${s.segment}</div></div>
        <div style="text-align:right"><div style="font:700 13px var(--mono);color:#B45309">${s.roi_libelle||""}</div>
        <div style="font:600 10.5px var(--sans);color:var(--faint)">${s.delai_libelle} · ${s.difficulte}</div></div>
      </div>
      ${s.justification&&s.justification.texte?`<div style="font:500 11px/1.5 var(--sans);color:var(--faint);border-left:2px solid var(--line);padding-left:8px;margin-bottom:7px">${_soEsc(s.justification.texte)}</div>`:""}
      <div style="font:500 12.5px/1.65 var(--sans);color:var(--ink);background:var(--bg-raise);border-radius:6px;padding:10px 12px;margin-bottom:8px">${_soEsc(s.lecture||"Lecture de marché indisponible.")}</div>
      ${bloc("Pourquoi c'est important", s.enjeu)}
      ${caseBloc}
      <div style="margin-top:10px">${decisions}</div>
      ${bloc("Risques et conditions de succès", s.risques)}
      ${bloc("Si la banque ne fait rien", s.si_rien, "#E53935")}
      ${bloc("Pourquoi maintenant", s.maintenant, "#B45309")}
      ${conc}
      ${evts}
      ${s.synthese?`<div style="margin-top:9px;padding:8px 10px;background:var(--bg-raise);border-left:3px solid var(--accent-2);border-radius:0 6px 6px 0">
        <div style="font:700 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--accent-2);margin-bottom:3px">🤖 Lecture IA</div>
        <div style="font:500 12px/1.6 var(--sans);color:var(--ink)">${_soEsc(s.synthese)}</div></div>`:""}
      <div style="margin-top:9px;padding-top:7px;border-top:1px solid var(--line)">
        <div style="font:700 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin-bottom:5px">Indicateurs à suivre</div>
        ${indics}
        <div style="font:700 8.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin:6px 0 3px">Sources</div>
        ${src}
      </div>
    </div>`;
  }).join("") || `<div class="tile c12 tpad"><div style="font:500 12px var(--sans);color:var(--muted)">Aucun dossier pour cette direction.</div></div>`;

  const sect=(num,titre,enclair,inner)=>`<section style="scroll-margin-top:172px">
    <div style="display:flex;align-items:center;gap:10px;margin:22px 0 3px">
      <span style="font:900 21px var(--display);color:var(--accent-2)">${num}</span>
      <span style="font:800 19px var(--display);color:var(--ink)">${titre}</span></div>
    <div style="font:500 13px/1.6 var(--sans);color:var(--muted);background:var(--bg-raise);border-left:3px solid var(--accent-2);border-radius:0 7px 7px 0;padding:8px 12px;margin-bottom:13px">${enclair}</div>
    ${inner}</section>`;

  // SEGMENTATION CLIENTÈLE (2026-07-30) — la grille transmise par la Direction. Elle donne au
  // lecteur la clé des segments cités dans chaque dossier (CLIPRO, GP, Patrimoniaux…), qui
  // resteraient sinon des sigles opaques pour qui ne les manipule pas tous les jours.
  const segments = `<div style="margin-top:10px;padding-top:9px;border-top:1px solid var(--line);font:500 12.5px/1.85 var(--sans);color:var(--muted)">
      <b style="color:var(--ink)">Segmentation SGCI</b> —
      <b>GP</b> mass market &lt; 450 k · <b>BG</b> bonne gamme 450 k – 2 M · <b>PATRIMONIAUX</b> ≥ 2 M
      <span style="color:var(--faint)">(revenu mensuel)</span> ·
      <b>CLIPRO</b> ≤ 750 M · <b>CLICOM</b> &gt; 750 M <span style="color:var(--faint)">(CA annuel)</span></div>`;
  const repere = eco.commission_moyenne ? `<div style="font:400 12.5px/1.65 var(--sans);color:var(--muted);margin-top:11px">
      Impacts calculés sur la commission moyenne réelle de <b>${eco.commission_moyenne.toLocaleString("fr-FR")} FCFA par client et par an</b>
      (${eco.commissions_m?Math.round(eco.commissions_m).toLocaleString("fr-FR"):"—"} M FCFA de commissions ÷ ${eco.clients?eco.clients.toLocaleString("fr-FR"):"—"} clients).
      Les commissions pèsent ${eco.part_commissions_pnb} % du PNB de SGCI contre ${eco.meilleur_ratio} % chez ${eco.meilleur_ratio_banque}.</div>` : "";

  // COHÉRENCE AVEC LA STRATÉGIE GLOBALE — placé en tête : c'est le cadre dans lequel toutes les
  // décisions qui suivent prennent leur sens. Sans lui, l'onglet propose des actions sans dire
  // à quel objectif elles servent.
  const og = d.objectif_global;
  const bandeau = og ? `<div class="tile c12 tpad" style="border-left:4px solid var(--accent-2);margin-bottom:4px">
      <div style="font:700 10.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--accent-2);margin-bottom:5px">Objectif de la stratégie globale</div>
      <div style="font:500 13.5px/1.65 var(--sans);color:var(--ink)">
        Porter le PNB à <b>${String(og.cible_centrale).replace(".",",")} ${og.unite} FCFA</b> en ${og.horizon_ans} ans (scénario central),
        contre <b>${String(og.trajectoire_naturelle).replace(".",",")} ${og.unite}</b> en trajectoire naturelle —
        soit <b style="color:var(--accent-2)">${String(og.ecart_a_combler).replace(".",",")} ${og.unite} FCFA à aller chercher</b>.</div>
      ${og.couverture_pct!=null?`<div style="margin-top:7px;padding-top:7px;border-top:1px solid var(--line);font:500 12.5px/1.6 var(--sans);color:var(--muted)">
        La <b>conquête sectorielle</b> seule en couvre <b style="color:var(--ink)">${String(og.couvert_par_secteurs_mds).replace(".",",")} ${og.unite}</b>,
        soit <b style="color:${og.couverture_pct<10?'#E53935':'#12895C'}">${String(og.couverture_pct).replace(".",",")} %</b> de l'écart.
        Le reste vient du portefeuille existant — structure du PNB, tarification, volumes, coût du risque — et se lit
        dans le bouclage du plan ci-dessous.</div>`:""}
    </div>` : "";

  // ORDRE DE LECTURE (2026-08-07) : l'objectif global, puis CE QUE CHAQUE DIRECTION DOIT
  // FAIRE, puis seulement ensuite l'arbitrage sectoriel et les dossiers qui l'étayent.
  // L'inverse obligeait un directeur à traverser une analyse de marché avant d'atteindre
  // ce qui le concerne.
  box.innerHTML = bandeau + _soBouclage(d) + _soDirectives(d, sect, cartes) +
    sect("②","Arbitrage — où concentrer la conquête",
      "<b>Rendement · Délai · Difficulté.</b> Le ROI est en étoiles, pas en pourcentage : c'est un ordre de priorité, pas une prévision.",
      `<div class="tile c12 tpad">
         <div style="display:flex;gap:10px;padding-bottom:6px;border-bottom:1px solid var(--line);font:700 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)">
           <span style="width:230px">Secteur</span><span style="width:70px">ROI</span><span style="width:64px">Délai</span>
           <span style="width:74px">Difficulté</span><span style="width:110px;text-align:right">Commissions/an</span>
           <span style="width:86px;text-align:right">Priorité</span></div>
         ${lignes}${repere}${segments}
       </div>`)
    // La section « Les dossiers de marché » a été absorbée dans la section ① : ses cartes
    // s'affichent désormais sous les directives de la direction sélectionnée, commandées par
    // la même barre d'onglets. Le panneau des décisions prioritaires reste ici, car il porte
    // sur l'ensemble des secteurs et non sur une direction.
    + (priorisees ? sect("③","Décisions sectorielles prioritaires",
      "<b>Les quatre décisions les plus pertinentes</b> pour la direction sélectionnée, tirées des dossiers de marché.",
      priorisees) : "");
}

// SIGNAL DE MARCHÉ D'UNE DIRECTIVE (2026-08-07) — ce qui, à l'extérieur de la banque, rend
// la décision pertinente maintenant : un indicateur sectoriel ou politique, ou un événement
// daté relevé par la veille. Sans lui, la carte n'exposait que des mesures internes (tarifs,
// états financiers) et ressemblait à un audit plutôt qu'à une directive.
// Le lien renvoie à la source : une affirmation qu'on ne peut pas remonter ne vaut rien en
// comité. Rendu vide si aucun signal — jamais un encadré « non disponible » qui prend la
// place sans rien apporter.
function _soSignal(s){
  if(!s || !s.texte) return "";
  const evt = s.nature === "événement";
  const col = evt ? "#B45309" : "var(--accent-2)";
  const src = s.source ? _soEsc(s.source) : "";
  const lien = s.url
    ? `<a href="${_soEsc(s.url)}" target="_blank" rel="noopener" style="color:${col};text-decoration:none;border-bottom:1px dotted ${col}">${src||"source"}</a>`
    : src;
  return `<div style="margin-top:8px;padding:8px 11px;border-left:3px solid ${col};background:var(--bg-raise);border-radius:0 6px 6px 0">
    <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:${col};margin-bottom:3px">
      Signal de marché · ${_soEsc(s.nature||"")}</div>
    <div style="font:500 12px/1.55 var(--sans);color:var(--muted)">${_soEsc(s.texte)}${lien?` <span style="color:var(--faint)">— ${lien}</span>`:""}</div>
  </div>`;
}

// TERRAIN D'APPLICATION (2026-08-07) — le secteur sur lequel la directive s'exerce, avec ce
// qu'il peut rapporter et qui y est déjà installé. Il occupait auparavant une section à part,
// sous les directives : le lecteur devait rapprocher lui-même « augmenter les commissions »
// et « la campagne cacao ouvre le 1er septembre ». Les deux ne se lisent que ensemble.
function _soTerrain(t){
  // Directive transversale : elle ne vise aucun secteur en particulier (coefficient
  // d'exploitation, cohérence de la grille publiée). Lui coller un secteur produirait le
  // faux lien qu'on cherche justement à éviter — on le dit, en une ligne.
  if(!t || !t.nom){
    return `<div style="margin-top:8px;font:500 11.5px/1.5 var(--sans);color:var(--faint)">
      <b style="color:var(--muted)">Portée</b> — transversale : s'applique à l'ensemble du
      portefeuille, sans secteur cible.</div>`;
  }
  const M = v => v==null ? null : (Math.abs(v)>=1e9 ? (v/1e9).toFixed(1).replace(".",",")+" Md"
              : Math.abs(v)>=1e6 ? Math.round(v/1e6)+" M" : Math.round(v).toLocaleString("fr-FR"));
  const gain = (t.commissions_min!=null && t.commissions_max!=null)
    ? `<b style="color:#0a5e3c">+${M(t.commissions_min)} à +${M(t.commissions_max)} FCFA/an</b>` : "";
  const clients = (t.clients_min!=null)
    ? `${t.clients_min} à ${t.clients_max} clients visés` : "";
  const conc = (t.concurrents||[]).length
    ? `déjà occupé par ${_soEsc(t.concurrents.join(", "))}` : "aucun concurrent identifié";
  const bribes = [clients, gain ? null : "", conc].filter(Boolean);
  return `<div style="margin-top:8px;padding:8px 11px;background:#0d7a500e;border:1px solid #12895C33;border-radius:6px">
    <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:#0a5e3c;margin-bottom:3px">
      ${t.recommande ? "Terrain à privilégier" : "Terrain d'application"}</div>
    ${t.recommande ? `<div style="font:500 11px/1.45 var(--sans);color:var(--faint);margin-bottom:3px">
      La directive vaut pour tout le portefeuille ; c'est ici qu'il y a le plus à prendre.</div>` : ""}
    <div style="font:600 12.5px/1.5 var(--sans);color:var(--ink)">
      ${_SO_ICONES[t.cle]||"◆"} ${_soEsc(t.nom)}${t.segment?` <span style="font-weight:500;color:var(--muted)">· ${_soEsc(t.segment)}</span>`:""}</div>
    ${gain?`<div style="font:500 12px/1.5 var(--sans);color:var(--muted);margin-top:2px">${gain}${clients?` · ${clients}`:""}${t.delai?` · ${_soEsc(t.delai)}`:""}</div>`:""}
    <div style="font:500 11.5px/1.5 var(--sans);color:var(--faint);margin-top:2px">${_soEsc(t.cibles||"")} — ${conc}.</div>
  </div>`;
}

// APPROFONDIR AU CHAT (2026-08-07, demande du directeur : « il faut mettre des boutons,
// demander au chat pour avoir beaucoup plus d'informations »). La carte tient en trente
// secondes de lecture ; tout le détail — comment s'y prendre, sur quels clients, avec quels
// précédents — vit dans le chat, qui a accès à l'ensemble de la base. Le bouton compose la
// question à partir de la directive elle-même, pour que le chat parte du bon contexte.
function _soChatBtn(x){
  const q = `Direction ${String(x.direction||"").replace("Direction ","")} — directive « ${x.titre} ». `
    + (x.terrain && x.terrain.nom ? `Terrain : ${x.terrain.nom}. ` : "")
    + `Détaille comment l'exécuter : les étapes concrètes, les clients à viser en priorité, `
    + `les tarifs et services SGCI concernés, ce que font les concurrents, et les risques.`;
  return `<button onclick="_soDemanderChat(${JSON.stringify(q).replace(/"/g,"&quot;")})"
     style="margin-top:9px;cursor:pointer;font:700 11px var(--sans);color:var(--accent-2);
            background:transparent;border:1px solid var(--accent-2);border-radius:7px;padding:6px 12px">
     Approfondir avec l'assistant →</button>`;
}

function _soDemanderChat(question){
  go("chat");
  // Le rendu de la page chat est synchrone, mais le champ n'existe qu'après : on laisse un
  // tour de boucle avant de le remplir, sinon getElementById renvoie null.
  setTimeout(() => {
    const ci = document.getElementById("ci");
    if(!ci) return;
    ci.value = question;
    if(typeof sendChat === "function") sendChat();
  }, 60);
}

function _soEsc(t){
  return String(t==null?"":t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

const AFTER = {
  apercu:    afterApercu,
  analyse:   afterAnalyse,
  strategie: afterStrategie,
  rapports:  afterRapports,
  cb:        afterCB,
  chat:      afterChat,
  stratop:   afterStratOp,
  admin:     afterAdmin,
};

function go(key){
  const p = PAGES[key]; if(!p) return;
  // L'écran de chargement N'EST PLUS réarmé ici : il couvre le seul premier chargement de
  // l'application. Une fois les caches chauds, un changement d'onglet répond en une à trois
  // secondes, et un voile qui clignote à chaque filtre inquiète plus qu'il ne rassure.
  closeNav();                       // ferme le tiroir mobile à la navigation
  window.__redraw = null;
  document.querySelectorAll(".nav-item").forEach(n =>
    n.classList.toggle("active", n.dataset.go===key)
  );
  document.getElementById("htitle").textContent = p.title;
  const el = document.getElementById("view");
  el.className = p.full ? "" : "page page-enter";
  el.innerHTML = p.render();
  if(AFTER[key]) AFTER[key]();
  if(key !== "chat") localStorage.setItem("sb-page", key);
  // BUG TROUVÉ (2026-07-27, signalé par le directeur, capture à l'appui) : le bouton flottant
  // (orbe hologramme) reste affiché même sur la page Chat elle-même, où il se superpose au
  // bouton d'envoi du composer (les deux sont en bas à droite) — inutile en plus d'être gênant
  // puisqu'il sert justement à OUVRIR le chat. On le masque quand on y est déjà.
  const fab = document.querySelector(".fab");
  if(fab) fab.style.display = (key === "chat") ? "none" : "";
}

/* ─── ticker + horloge ───────────────────────────────────────────── */
function initChrome(){
  const tk   = document.getElementById("tk");
  const html = TICKER.map(t =>
    `<span class="tk-item">
      <span class="lg"><img src="${bankBy(t.s).lg}"></span>
      <b>${t.s}</b> ${t.v}
      <span class="${t.up?'up':'dn'}">${t.up?'▲':'▼'} ${t.d}</span>
    </span>`
  ).join("");
  tk.innerHTML = html + html; // duplication pour l'animation infinie

  updateTickerLabel(); // label initial
  // Horloge
  const clk = document.getElementById("clk");
  if(clk){
    function tick(){ clk.textContent = new Date().toLocaleTimeString("fr-FR",{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
    tick(); setInterval(tick, 1000);
  }
}

/* ════════════════════════════════════════════════════════════════════════
   GATE — Disclaimer + Login (two-step access guard)
   ════════════════════════════════════════════════════════════════════════ */

function _gateDisclaimer(){
  /* Build dynamic bank pills */
  const banks = (typeof CB_BANK_ORDER !== 'undefined' && CB_BANK_ORDER.length)
    ? CB_BANK_ORDER
    : ["SGCI","BACI","BICICI","BNI","ECOBANK","NSIA","SIB"];

  const bankPills = banks.map(b => {
    const bk = (typeof bankBy==='function') ? bankBy(b) : null;
    const logo = bk ? bk.lg : `assets/logos/${b}.png`;
    return `<span class="gate-bank-pill"><img src="${logo}" alt="${b}">${b}</span>`;
  }).join("");

  return `<div class="gate-card">
  <div class="gate-header">
    <div class="gate-logo"><img src="assets/logos/SGCI.png" alt="SGCI"></div>
    <div class="gate-titles">
      <h1>Conformité &amp; Transparence</h1>
      <small>SpyBusiness · Intelligence Bancaire Ivoirienne</small>
    </div>
    <button class="theme-tog" style="margin-left:auto" onclick="toggleTheme()" title="Thème clair / sombre"><span class="theme-ic">☀</span></button>
  </div>
  <div class="gate-body">

    <!-- MISSION -->
    <div class="gate-section sec-mission">
      <div class="sec-title">◎ Cadre &amp; Mission</div>
      <div class="sec-text">
        Consciente des enjeux liés à la prise de décision stratégique et à la maîtrise des risques informationnels, la <strong>Société Générale Côte d'Ivoire (SGCI)</strong> a mis en place un système de veille stratégique, de benchmarking concurrentiel et d'aide à la décision reposant sur une approche RAG (Retrieval-Augmented Generation).<br><br>
        Cette solution vise à permettre à la banque d'évaluer son positionnement sur le marché bancaire ivoirien en comparaison avec ses principaux concurrents. En s'appuyant sur l'analyse des données financières, des conditions tarifaires et du cadre réglementaire applicable, elle contribue à l'identification des opportunités, des axes d'amélioration et des leviers de performance, afin de soutenir une prise de décision éclairée, fondée sur des données fiables, actualisées et conformes aux exigences réglementaires.
      </div>
    </div>

    <!-- SOURCES -->
    <div class="gate-section sec-sources">
      <div class="sec-title">◈ Origine et fiabilité des données</div>
      <div class="sec-text">
        Les données exploitées par le système proviennent exclusivement de sources officielles des établissements bancaires, notamment leurs sites internet, plaquettes tarifaires, conditions générales de banque, rapports publics ainsi que les référentiels réglementaires applicables.<br><br>
        Les informations collectées font l'objet de contrôles de cohérence au regard du cadre juridique et réglementaire en vigueur afin de garantir la fiabilité, la traçabilité et la pertinence des analyses produites.
      </div>
    </div>

    <!-- AI ACT -->
    <div class="gate-section sec-ai">
      <div class="sec-title">⚖ Transparence Algorithmique</div>
      <div class="sec-text">
        Dans une démarche alignée avec les principes de transparence définis par l'<strong>Article 50 du Règlement européen sur l'intelligence artificielle (AI Act – Règlement (UE) 2024/1689)</strong>, les utilisateurs sont informés que le système intègre des technologies d'intelligence artificielle générative destinées à assister l'analyse des données.<br><br>
        Les indicateurs, tableaux de bord et visualisations reposent sur les données collectées et structurées dans la base de données. Les synthèses financières, interprétations, commentaires stratégiques et propositions de repricing sont, quant à eux, générés avec l'assistance de modèles de langage (LLM), intégrés dans une architecture RAG.<br><br>
        Ces éléments constituent des analyses d'aide à la décision et ne remplacent pas l'expertise humaine. Les résultats générés dépendent des données disponibles au moment de l'analyse et peuvent nécessiter une vérification complémentaire avant toute utilisation opérationnelle.
      </div>
    </div>

    <!-- HUMAN VALIDATION -->
    <div class="gate-section sec-human">
      <div class="sec-title">👥 Validation &amp; Expertise Humaine</div>
      <div class="sec-text">
        Les recommandations, analyses stratégiques et propositions générées par l'intelligence artificielle ont pour objectif d'accompagner les utilisateurs dans leur processus de décision, sans se substituer au jugement des experts métiers.<br><br>
        Toute décision commerciale, tarifaire ou stratégique demeure soumise à une analyse critique et à une validation par les experts et décideurs de la <strong>SGCI</strong>, afin d'assurer son alignement avec la politique commerciale, les orientations stratégiques et les exigences réglementaires de la banque.
      </div>
    </div>

    <!-- CONSENT -->
    <div class="gate-consent">
      <label>
        <input type="checkbox" class="gate-chk" id="gate-chk" onchange="_gateChkToggle()">
        J'ai pris connaissance de ces informations
      </label>
      <button class="gate-btn" id="gate-btn" onclick="_gateAccept()">
        Continuer →
      </button>
    </div>

  </div>
</div>`;
}

function _gateLogin(){
  return `<div class="gate-login">
  <button class="theme-tog" onclick="toggleTheme()" title="Thème clair / sombre"><span class="theme-ic">☀</span></button>
  <div class="login-logo"><img src="assets/logos/SGCI.png" alt="SGCI"></div>
  <h2>Connexion</h2>
  <p class="login-sub">Veuillez vous authentifier pour accéder au cockpit d'intelligence bancaire.</p>
  <div class="login-fields">
    <div class="field-group">
      <label for="gate-user">Identifiant</label>
      <input type="text" id="gate-user" placeholder="Entrez votre identifiant" autocomplete="username">
    </div>
    <div class="field-group">
      <label for="gate-pass">Code d'accès</label>
      <input type="password" id="gate-pass" placeholder="Entrez votre code d'accès" autocomplete="current-password"
             onkeydown="if(event.key==='Enter') _gateLoginSubmit()">
    </div>
    <div class="login-error" id="gate-err">⚠ Identifiant ou code d'accès incorrect.</div>
    <button class="login-btn" onclick="_gateLoginSubmit()">Se connecter →</button>
  </div>
</div>`;
}

function _gateChkToggle(){
  const chk = document.getElementById("gate-chk");
  const btn = document.getElementById("gate-btn");
  if(chk && btn) btn.classList.toggle("enabled", chk.checked);
}

function _gateAccept(){
  sessionStorage.setItem("sb-disclaimer-read","1");
  const gate = document.getElementById("gate");
  const card = gate.querySelector(".gate-card");
  if(card) card.classList.add("gate-fadeout");
  setTimeout(()=>{ _gateShowLogin(); }, 500);
}

function _gateShowLogin(){
  const gate = document.getElementById("gate");
  gate.innerHTML = _gateLogin();
  setTheme(localStorage.getItem("sb-theme") || "dark");   // ré-applique l'icône sur l'écran injecté
  /* Focus first input */
  const u = document.getElementById("gate-user");
  if(u) setTimeout(()=> u.focus(), 100);
}

// AUTHENTIFICATION CÔTÉ SERVEUR (2026-08-07).
//
// Cette fonction comparait le mot de passe à une chaîne littérale écrite ICI même, du type
//     const validPass = (pass === "<le mot de passe, en clair>");
// Autrement dit, le mot de passe était livré à chaque visiteur avec la page, et la porte se
// franchissait depuis la console en appelant _gateUnlock(). Rien côté serveur ne s'y opposait :
// les vingt-et-un endpoints répondaient sans identifiant.
//
// La vérification appartient désormais au serveur, contre une empreinte scrypt salée stockée
// en base (cf. dash_app/securite.py). Le navigateur ne connaît plus aucun secret : il envoie
// ce que l'utilisateur a tapé et reçoit un cookie de session signé, inaccessible au JavaScript.
async function _gateLoginSubmit(){
  const user = (document.getElementById("gate-user").value||"").trim().toLowerCase();
  const pass = (document.getElementById("gate-pass").value||"").trim();
  const err  = document.getElementById("gate-err");
  // .login-btn et non « .gate-login button » : ce dernier attrapait le sélecteur de thème,
  // placé plus haut dans le même conteneur. Le bouton de connexion n'était jamais désactivé,
  // et c'est l'icône du thème qui affichait « Vérification… ».
  const btn  = document.querySelector(".login-btn");
  if(btn){ btn.disabled = true; btn.textContent = "Vérification…"; }

  let ok = false, motif = "Identifiant ou mot de passe incorrect.";
  try{
    const r = await fetch("/api/login", {
      method:"POST", headers:{"Content-Type":"application/json"},
      credentials:"same-origin",
      body: JSON.stringify({ identifiant:user, mot_de_passe:pass })
    });
    const d = await r.json().catch(()=>({}));
    ok = !!(r.ok && d.ok);
    if(!ok && d.error) motif = d.error;   // ex. temporisation après trop de tentatives
    if(ok) SB_UTILISATEUR = d.utilisateur || null;
  }catch(e){
    motif = "Serveur injoignable.";
  }
  if(btn){ btn.disabled = false; btn.textContent = "Se connecter →"; }

  if(ok){
    const gate = document.getElementById("gate");
    const card = gate.querySelector(".gate-login");
    if(card) card.classList.add("gate-fadeout");
    setTimeout(()=> _gateUnlock(), 500);
  } else {
    if(err){ err.textContent = motif; err.classList.add("show"); }
    const card = document.querySelector(".gate-login");
    if(card){ card.style.animation="none"; card.offsetHeight; card.style.animation="gateIn .4s var(--ease)"; }
  }
}

// Utilisateur courant, renseigné à la connexion ou au retour d'une session encore valide.
// Sert notamment à masquer « Ajouter des données » pour un compte en lecture seule : le
// serveur refuserait de toute façon (403), mais proposer un bouton qui échoue est une
// mauvaise manière de faire respecter un droit.
let SB_UTILISATEUR = null;

function _gateUnlock(){
  _gateVerrouAffiche = false;   // une nouvelle session peut de nouveau déclencher un rappel
  document.body.classList.remove("gated");
  const gate = document.getElementById("gate");
  gate.classList.add("hidden");
  /* Now boot the real app */
  _bootApp();
}

/* PAGE D'ARRIVÉE = UNE PAGE AUTORISÉE (2026-08-10, signalé par le directeur : « si je dis
   marketing a accès uniquement à conditions de banques, dès que je me connecte je dois être
   sur conditions de banque »).

   L'application ouvrait sur « apercu », ou sur la dernière page mémorisée, sans jamais
   vérifier que le compte y avait droit. Un profil restreint atterrissait donc sur un écran
   absent de son menu : il voyait une page vide, ou — vu en production — la page Chat, qui
   affichait « Erreur de connexion au RAG » parce que le serveur refusait l'appel. Le premier
   contact avec l'application était un message d'erreur, pour un refus de droits parfaitement
   normal.

   On choisit donc la première page à laquelle le compte a droit, dans l'ordre du menu. */
function _pageDArrivee(){
  const memorisee = localStorage.getItem("sb-page");
  const u = SB_UTILISATEUR;
  const permise = (p) => {
    if(!PAGES[p]) return false;
    if(!u || u.role === "admin") return true;
    const section = SECTION_DE_PAGE[p];
    return !section || (u.droits || []).includes(section);
  };
  if(memorisee && permise(memorisee)) return memorisee;
  // Ordre du menu, pour que l'arrivée corresponde à ce que l'utilisateur voit en premier.
  return ["apercu","cb","strategie","stratop","analyse","chat"].find(permise) || "apercu";
}

function _bootApp(){
  const demarrer = ()=>{
    _appliquerDroits();
    initChrome();
    document.getElementById("burger").onclick = toggleNav;
    // Le démarrage se fait en deux temps : loadAll() charge les référentiels communs, puis la
    // première page demande SES données. Sans prolonger la fenêtre ici, ces secondes demandes
    // ne sont plus comptées et l'écran de chargement se retire sur une page encore vide.
    try{ chargementProlonger(); }catch(e){}
    go(_pageDArrivee());
  };
  loadAll()
    .then(demarrer)
    // Les droits s'appliquent aussi quand le chargement échoue : un menu complet sur une
    // application en panne laisserait croire que tout est accessible.
    .catch(demarrer);
  _checkLlmStatus();
  setInterval(_checkLlmStatus, 90000);   // ré-affiche/masque le bandeau si l'état change en cours de session
  // Masque "Ajouter des données" sur les environnements où le pipeline d'extraction n'est pas embarqué (ex. cloud allégé).
  fetch("/api/features").then(r=>r.json()).then(f=>{
    if(f && f.ingest_available===false){
      const nav = document.getElementById("nav-ajout");
      if(nav) nav.style.display = "none";
    }
  }).catch(()=>{});
  // Tampon discret de traçabilité (filigrane) — date/heure de la session en cours.
  const _wmStamp = document.getElementById("app-watermark-stamp");
  if(_wmStamp) _wmStamp.textContent = "Direction Innovation SGCI · " + new Date().toLocaleString("fr-FR", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"});
}

// Bandeau visible si le LLM est indisponible (quota épuisé / panne) — pour ne JAMAIS laisser
// l'utilisateur croire qu'une analyse silencieusement obsolète est fraîche.
async function _checkLlmStatus(){
  /* RÉSERVÉ À L'ADMINISTRATEUR (2026-08-11). Ce bandeau annonce l'épuisement du quota du
     modèle de langage : c'est une information d'exploitation, pas de lecture. Un directeur
     du marketing n'a rien à en faire — il ne peut ni recharger le quota ni décider d'attendre,
     et le message le conduit surtout à douter de chiffres qui, eux, restent exacts puisqu'ils
     viennent de la base. Seul l'administrateur agit dessus, seul il le voit. */
  if(!_voitAvertissementsTechniques()){
    const b0 = document.getElementById("llm-status-banner");
    if(b0) b0.style.display = "none";
    return;
  }
  try{
    const d = await (await fetch("/api/llm_status")).json();
    const b = document.getElementById("llm-status-banner");
    if(!b) return;
    if(d && d.ok===false){
      b.textContent = d.reason==="quota"
        ? "⚠️ Quota d'analyse IA journalier épuisé — les analyses affichées peuvent ne pas être à jour tant que le quota n'est pas renouvelé."
        : "⚠️ Service d'analyse IA momentanément indisponible — les analyses affichées peuvent ne pas être à jour.";
      b.style.cssText = "display:block;padding:8px 18px;font:600 11.5px/1.4 var(--sans);text-align:center;background:color-mix(in srgb,#E53935 15%,transparent);color:#E53935;border-bottom:1px solid color-mix(in srgb,#E53935 35%,transparent)";
    } else {
      b.style.display = "none";
    }
  }catch(e){ /* silencieux — pas de bandeau si l'endpoint est injoignable */ }
}

// ── Rafraîchir les analyses (bouton dédié) ─────────────────────────────────────────────────
// « Ajouter des données » ne fait QUE stocker. Ce bouton est le SEUL déclencheur de la
// régénération LLM. Flux en 3 temps :
//   1) l'utilisateur choisit QUELLE partie rafraîchir (SF / CB / Stratégie)
//   2) on vérifie s'il y a RÉELLEMENT de nouvelles données pour cette partie — si non, on le
//      dit clairement et on s'arrête là (jamais de régénération pour rien)
//   3) si oui, confirmation EXPLICITE (bouton rouge) puis génération avec barre de progression.
// Non destructif : en cas d'échec LLM (quota/panne), les DERNIÈRES analyses valides sont
// conservées côté serveur (jamais de régression visible) — cf. _refresh_analyses_job.
const _RF_SECTIONS = [
  {k:"ef",        ic:"◎", label:"Santé financière",   detail:"Analyses EF (résultat net, ROE, coût du risque…)"},
  {k:"cb",        ic:"◈", label:"Conditions bancaires", detail:"Analyses des tarifs et positionnement concurrentiel"},
  {k:"strategie", ic:"◆", label:"Stratégie",           detail:"Diagnostic, SWOT, révélations, plan d'action, PESTEL/VRIST"},
];
function confirmRafraichirAnalyses(){
  closeNav();
  _ajInjectStyle();
  let ov=document.getElementById("aj-ov");
  if(!ov){
    ov=document.createElement("div"); ov.id="aj-ov";
    ov.innerHTML=`<div id="aj-card"></div>`;
    document.body.appendChild(ov);
  }
  document.body.style.overflow="hidden";
  requestAnimationFrame(()=>ov.classList.add("open"));
  _ajShell(`
    <div style="display:flex;flex-direction:column;gap:10px">
      ${_RF_SECTIONS.map(s=>`
        <button class="aj-btn" style="width:100%;text-align:left;display:flex;align-items:center;gap:12px;padding:14px 16px"
                onclick="_refreshCheck('${s.k}')">
          <span style="font-size:20px">${s.ic}</span>
          <span>
            <div style="font:700 13px var(--sans);color:var(--ink)">${s.label}</div>
            <div style="font:500 10.5px var(--sans);color:var(--muted);margin-top:2px">${s.detail}</div>
          </span>
        </button>`).join("")}
    </div>`,
    "Rafraîchir les analyses", "Quelle partie voulez-vous rafraîchir ?");
}

async function _refreshCheck(section){
  const s = _RF_SECTIONS.find(x=>x.k===section);
  _ajShell(`<div class="aj-prog"><div class="aj-stage">Vérification des données…</div></div>`,
            "Rafraîchir les analyses", s.label);
  try{
    const d = await (await fetch(`/api/rafraichir_check?section=${section}`)).json();
    if(!d.has_new_data){
      _ajShell(`<div class="aj-ok">
          <div class="ic">ℹ️</div>
          <h3>Aucune nouvelle donnée</h3>
          <p>Rien n'a changé pour « ${s.label} » depuis le dernier rafraîchissement — inutile de relancer l'IA.</p>
        </div>
        <div class="aj-foot" style="justify-content:center">
          <button class="aj-btn" onclick="confirmRafraichirAnalyses()">← Retour</button>
          <button class="aj-btn pri" onclick="closeAjout()">Fermer</button>
        </div>`, "Rafraîchir les analyses", s.label);
      return;
    }
    _ajShell(`<div class="aj-ok">
        <div class="ic">⚠️</div>
        <h3>Nouvelles données détectées</h3>
        <p>Des données ont changé pour « ${s.label} ». Confirmer relance l'IA sur cette partie — cela prend
        1 à 3 minutes. En cas d'échec (quota IA), les analyses actuelles sont conservées, rien n'est perdu.</p>
      </div>
      <div class="aj-foot" style="justify-content:center">
        <button class="aj-btn" onclick="confirmRafraichirAnalyses()">← Retour</button>
        <button class="aj-btn pri" style="background:#E5142B;border-color:#E5142B" onclick="_refreshStart('${section}')">Rafraîchir maintenant</button>
      </div>`, "Rafraîchir les analyses", s.label);
  }catch(e){
    _refreshFail("Impossible de vérifier les données (connexion au serveur).");
  }
}

function _refreshStart(section){
  const s = _RF_SECTIONS.find(x=>x.k===section);
  _ajShell(`<div class="aj-prog">
      <div class="aj-stage" id="rf-stage">Démarrage…</div>
      <div class="aj-bar"><i id="rf-fill" style="width:8%"></i></div>
      <div class="aj-sub" style="text-align:center">Régénération IA de « ${s.label} » — ne fermez pas cette fenêtre.</div>
    </div>`, "Rafraîchir les analyses", s.label);
  fetch(`/api/rafraichir_analyses?section=${section}`, {method:"POST"}).then(r=>r.json()).then(j=>{
    if(!j.ok || !j.job) return _refreshFail("Impossible de démarrer le rafraîchissement.");
    _refreshPoll(j.job, s.label);
  }).catch(()=>_refreshFail("Impossible de démarrer le rafraîchissement."));
}

function _refreshPoll(job, label){
  let n = 0;
  const tick = async () => {
    n++;
    try{
      const d = await (await fetch(`/api/ajout/statut?job=${job}`)).json();
      const st = document.getElementById("rf-stage"), fill = document.getElementById("rf-fill");
      if(st && d.stage) st.textContent = d.stage;
      if(fill) fill.style.width = Math.min(92, 8 + n * 4) + "%";
      if(d.status === "done"){ if(fill) fill.style.width = "100%"; return _refreshDone(d.result, label); }
      if(d.status === "error") return _refreshFail((d.result && d.result.message) || "Le rafraîchissement a échoué.");
    }catch(e){}
    setTimeout(tick, 1500);
  };
  setTimeout(tick, 900);
}

function _refreshDone(res, label){
  const n = (res && res.warmed) || 0;
  const failed = (res && res.failed) || [];
  _ajShell(`<div class="aj-ok">
      <div class="ic">✅</div>
      <h3>« ${label} » rafraîchi</h3>
      <p>${n} analyse(s) régénérée(s) par l'IA à partir des données actuellement stockées.</p>
      ${failed.length ? `<p style="margin-top:6px;color:var(--muted)">${failed.length} élément(s) n'ont pas pu être régénérés (quota/service IA indisponible) — les analyses précédentes ont été conservées, rien n'a été perdu.</p>` : ''}
    </div>
    <div class="aj-foot" style="justify-content:center">
      <button class="aj-btn pri" onclick="location.reload()">Recharger la page</button>
    </div>`, "Rafraîchir les analyses");
  _checkLlmStatus();
}

function _refreshFail(msg){
  _ajShell(`<div class="aj-ok">
      <div class="ic">⚠️</div>
      <h3>Rafraîchissement impossible</h3>
      <p>${msg}</p>
    </div>
    <div class="aj-foot" style="justify-content:center">
      <button class="aj-btn pri" onclick="closeAjout()">Fermer</button>
    </div>`, "Rafraîchir les analyses");
}

/* ─── démarrage ──────────────────────────────────────────────────── */
window.addEventListener("load", ()=>{
  setTheme(localStorage.getItem("sb-theme") || "dark");

  const disclaimerRead = sessionStorage.getItem("sb-disclaimer-read") === "1";

  // C'EST LE SERVEUR QUI DIT SI LA SESSION EST VALIDE (2026-08-07).
  // Auparavant, un simple sessionStorage « sb-logged-in = 1 » suffisait à ouvrir
  // l'application — une valeur que n'importe qui peut écrire depuis la console. Elle ne
  // prouvait rien : elle enregistrait seulement que le navigateur avait déjà affiché la
  // page. On interroge donc /api/moi, qui répond d'après le cookie de session signé.
  fetch("/api/moi", { credentials:"same-origin" })
    .then(r => r.json())
    .then(d => {
      if(d && d.authentifie){
        SB_UTILISATEUR = d.utilisateur || null;
        if(disclaimerRead){ _gateUnlock(); return; }
      }
      _gateStart(disclaimerRead);
    })
    .catch(() => _gateStart(disclaimerRead));
  return;
});

// Session expirée en cours d'usage : on remet la porte plutôt que de laisser l'écran se vider
// sans explication. Appelée par apiFetch() sur un 401.
let _gateVerrouAffiche = false;
function _gateRelock(){
  if(_gateVerrouAffiche) return;        // un seul rappel, même si dix appels échouent d'un coup
  _gateVerrouAffiche = true;
  SB_UTILISATEUR = null;
  document.body.classList.add("gated");
  const gate = document.getElementById("gate");
  if(gate) gate.classList.remove("hidden");
  _gateShowLogin();
  const err = document.getElementById("gate-err");
  if(err){ err.textContent = "Session expirée. Reconnectez-vous."; err.classList.add("show"); }
}

/* ════════════ ADMINISTRATION ═══════════════════════════════════════════════════════
   Écran demandé le 2026-08-07 : « une interface admin où on pourra voir qui se connecte,
   créer les accès, voir chacune des actions ; l'admin choisit qui a accès à quoi. »

   Trois blocs, dans l'ordre où l'on s'en sert : les comptes (avec leurs droits, cochés
   section par section), la création d'un compte, puis le journal d'accès.

   Rien n'est décidé ici : l'écran ne fait qu'appeler /api/admin/*, qui revérifie le rôle.
   Un écran d'administration n'est pas un contrôle de sécurité — c'est une commodité posée
   par-dessus un contrôle qui, lui, vit sur le serveur. */
let _ADMIN_DATA = null;

function pageAdmin(){
  return `<div class="story">
      <div class="kicker">Sécurité</div>
      <h1>Qui accède à quoi, et <span class="hl">qui a fait quoi</span>.</h1>
      <p>Comptes, droits par section et journal d'accès. Chaque modification est elle-même tracée.</p>
    </div>
    <div id="admin-body"><div class="tile c12 tpad"><div style="color:var(--muted);font:500 12.5px var(--sans)">Chargement…</div></div></div>`;
}

async function afterAdmin(){
  const box = document.getElementById("admin-body"); if(!box) return;
  const d = await apiFetch("/api/admin/utilisateurs");
  if(!d || !d.utilisateurs){
    box.innerHTML = `<div class="tile c12 tpad"><div style="color:var(--muted);font:500 12.5px var(--sans)">
      Administration inaccessible : ce compte n'a pas le rôle administrateur.</div></div>`;
    return;
  }
  _ADMIN_DATA = d;
  _adminRender();
  _adminJournal();
}

function _adminRender(){
  const box = document.getElementById("admin-body"); if(!box || !_ADMIN_DATA) return;
  const S = _ADMIN_DATA.sections || {};
  const E = _soEsc;

  /* LES DIRECTIONS SE COCHENT SOUS LA STRATEGIE OPERATIONNELLE (2026-08-11).
     Elles etaient melees aux sections, sur la meme ligne : « Direction Commerciale » voisinait
     avec « Administration » sans rien qui dise qu elles n ont pas la meme portee. On voyait
     douze cases equivalentes, alors qu il y a sept acces et cinq VUES d un seul d entre eux.
     Elles sont donc retirees de la liste principale et presentees en retrait, sous leur
     parent — la mise en page dit alors ce que le libelle ne disait pas. */
  const DIRS = _ADMIN_DATA.directions_stratop || {};
  const lignes = (_ADMIN_DATA.utilisateurs||[]).map(u=>{
    const admin = u.role === "admin";
    const aDroit = c => (u.droits||[]).includes(c);
    const boite = (cle, nom, retrait) => `<label title="${E(nom)}" style="display:inline-flex;align-items:center;gap:4px;margin:0 9px 5px 0;
                font:500 11.5px var(--sans);color:${aDroit(cle)?'var(--ink)':'var(--faint)'};cursor:${admin?'not-allowed':'pointer'}">
        <input type="checkbox" ${aDroit(cle)?"checked":""} ${admin?"disabled":""}
               onchange="_adminDroit('${E(u.identifiant)}','${cle}',this.checked)"> ${E(nom)}</label>`;
    const principales = Object.entries(S).filter(([c])=>!DIRS[c])
                              .map(([c,n])=>boite(c,n)).join("");
    const vues = Object.entries(DIRS).map(([c,n])=>boite(c, n.replace(/^Direction /,""))).join("");
    /* Aucune vue cochee = toutes visibles. On l ECRIT, car l inverse se devine mal : un
       administrateur qui ne coche rien croirait avoir tout ferme alors qu il a tout ouvert. */
    const aucuneVue = !Object.keys(DIRS).some(aDroit);
    const cases = principales + (aDroit("stratop") ? `
      <div style="margin:4px 0 2px 16px;padding-left:11px;border-left:2px solid var(--line)">
        <div style="font:700 9.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin-bottom:3px">
          Vues de la Stratégie opérationnelle${aucuneVue?" — aucune cochée : toutes visibles":""}</div>
        ${vues}
      </div>` : "");
    const jamais = !u.derniere_connexion;
    return `<div class="tile c12 tpad" style="border-left:3px solid ${u.actif?'var(--accent-2)':'#94a3b8'};margin-bottom:9px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="font:800 15px var(--display);color:var(--ink)">${E(u.identifiant)}</span>
        <select onchange="_adminRole('${E(u.identifiant)}',this.value)"
                style="font:700 11px var(--sans);padding:3px 7px;border-radius:6px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink)">
          ${(_ADMIN_DATA.roles||[]).map(r=>`<option value="${r}" ${u.role===r?"selected":""}>${r}</option>`).join("")}
        </select>
        <span style="font:500 11.5px var(--sans);color:var(--faint)">
          ${jamais?"jamais connecté":"dernière connexion "+new Date(u.derniere_connexion).toLocaleString("fr-FR")}</span>
        <span style="margin-left:auto;display:flex;gap:6px">
          <button onclick="_adminActif('${E(u.identifiant)}',${!u.actif})" style="cursor:pointer;font:700 11px var(--sans);
            border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:6px;padding:4px 10px">
            ${u.actif?"Désactiver":"Réactiver"}</button>
          <button onclick="_adminMotDePasse('${E(u.identifiant)}')" style="cursor:pointer;font:700 11px var(--sans);
            border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:6px;padding:4px 10px">
            Réinitialiser le mot de passe</button>
          <button onclick="_adminSupprimer('${E(u.identifiant)}')" style="cursor:pointer;font:700 11px var(--sans);
            border:1px solid #E5393533;background:transparent;color:#E53935;border-radius:6px;padding:4px 10px">
            Supprimer</button>
        </span>
      </div>
      <div style="margin-top:8px;padding-top:7px;border-top:1px solid var(--line)">
        <div style="font:700 9.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:5px">
          Accès autorisés${u.role==="admin"?" — un administrateur voit tout, par définition":""}</div>
        ${cases}
      </div>
    </div>`;
  }).join("");

  const creation = `<div class="tile c12 tpad" style="border:1px dashed var(--line)">
      <div style="font:700 10.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--accent-2);margin-bottom:8px">
        Créer un accès</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <input id="adm-id" placeholder="identifiant" style="font:500 12.5px var(--sans);padding:7px 10px;border-radius:7px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink)">
        <input id="adm-mp" type="text" placeholder="mot de passe (${_ADMIN_DATA.longueur_min||8} car. min.)" style="font:500 12.5px var(--sans);padding:7px 10px;border-radius:7px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink);min-width:230px">
        <select id="adm-role" style="font:700 11.5px var(--sans);padding:7px 9px;border-radius:7px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink)">
          ${(_ADMIN_DATA.roles||[]).map(r=>`<option value="${r}">${r}</option>`).join("")}</select>
        <select id="adm-profil" title="Profil metier — coche les acces d'un coup" style="font:700 11.5px var(--sans);padding:7px 9px;border-radius:7px;border:1px solid var(--line);background:var(--bg-raise);color:var(--ink)">
          <option value="">profil… (facultatif)</option>
          ${Object.entries(_ADMIN_DATA.profils||{}).map(([k,v])=>`<option value="${k}">${_soEsc(v.libelle)}</option>`).join("")}</select>
        <button onclick="_adminCreer()" style="cursor:pointer;font:700 12px var(--sans);border:none;background:var(--accent-2);color:#fff;border-radius:7px;padding:8px 16px">Créer</button>
      </div>
      <div id="adm-msg" style="font:500 11.5px var(--sans);margin-top:7px;color:var(--muted)"></div>
      <div style="font:500 11px/1.5 var(--sans);color:var(--faint);margin-top:5px">
        Choisissez un profil pour cocher les accès d'une direction d'un coup, ou laissez vide pour les droits par défaut du rôle. Tout reste ajustable case par case ensuite.</div>
    </div>`;

  box.innerHTML = `<div class="bento">${lignes}${creation}</div>
    <div id="admin-journal" style="margin-top:14px"></div>`;
}

async function _adminRecharger(){
  const d = await apiFetch("/api/admin/utilisateurs");
  if(d && d.utilisateurs){ _ADMIN_DATA = d; _adminRender(); _adminJournal(); }
}

async function _adminEnvoyer(methode, corps){
  const r = await fetch("/api/admin/utilisateur", {
    method: methode, headers:{"Content-Type":"application/json"},
    credentials:"same-origin", body: JSON.stringify(corps)
  });
  const d = await r.json().catch(()=>({}));
  if(!d.ok && d.error){ alert(d.error); return false; }
  return !!d.ok;
}

async function _adminDroit(identifiant, section, actif){
  const u = (_ADMIN_DATA.utilisateurs||[]).find(x=>x.identifiant===identifiant); if(!u) return;
  const lot = new Set(u.droits||[]);
  actif ? lot.add(section) : lot.delete(section);
  if(await _adminEnvoyer("PATCH", {identifiant, droits:[...lot]})) _adminRecharger();
}
async function _adminRole(identifiant, role){
  if(await _adminEnvoyer("PATCH", {identifiant, role})) _adminRecharger();
}
async function _adminActif(identifiant, actif){
  if(await _adminEnvoyer("PATCH", {identifiant, actif})) _adminRecharger();
}
async function _adminMotDePasse(identifiant){
  const mp = prompt(`Nouveau mot de passe pour « ${identifiant} » (${(_ADMIN_DATA&&_ADMIN_DATA.longueur_min)||8} caractères minimum) :`);
  if(!mp) return;
  if(await _adminEnvoyer("PATCH", {identifiant, mot_de_passe:mp})) alert("Mot de passe remplacé.");
}
async function _adminSupprimer(identifiant){
  if(!confirm(`Supprimer définitivement le compte « ${identifiant} » ?`)) return;
  if(await _adminEnvoyer("DELETE", {identifiant})) _adminRecharger();
}
async function _adminCreer(){
  const id = (document.getElementById("adm-id").value||"").trim();
  const mp = (document.getElementById("adm-mp").value||"").trim();
  const role = document.getElementById("adm-role").value;
  const msg = document.getElementById("adm-msg");
  if(!id || !mp){ if(msg) msg.textContent = "Identifiant et mot de passe sont requis."; return; }
  /* PROFIL METIER : il coche d'un coup les acces d'une direction. Sans lui, l'administrateur
     doit cocher huit cases sans se tromper pour chaque arrivant — et une case de travers
     ouvre un ecran qu'on ne voulait pas ouvrir. Laisse vide, on retombe sur les droits par
     defaut du role, comme avant. */
  const profil = (document.getElementById("adm-profil")||{}).value || "";
  const corps = {identifiant:id, mot_de_passe:mp, role};
  const p = (_ADMIN_DATA.profils||{})[profil];
  if(p) corps.droits = p.droits;
  const r = await fetch("/api/admin/utilisateur", {
    method:"POST", headers:{"Content-Type":"application/json"},
    credentials:"same-origin", body: JSON.stringify(corps)
  });
  const d = await r.json().catch(()=>({}));
  if(msg) msg.textContent = d.ok ? `Compte « ${id} » créé.` : (d.error||"Création impossible.");
  if(d.ok) _adminRecharger();
}

async function _adminJournal(){
  const box = document.getElementById("admin-journal"); if(!box) return;
  const d = await apiFetch("/api/journal_acces");
  const E = _soEsc;
  const entrees = (d && d.entrees) || [];
  box.innerHTML = `<div class="tile c12 tpad">
    <div style="font:700 10.5px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:3px">
      Journal d'accès</div>
    <div style="font:500 12px/1.6 var(--sans);color:var(--muted);margin-bottom:9px">
      Connexions, refus, écritures et modifications de comptes — les ${entrees.length} plus récents.</div>
    <div style="max-height:420px;overflow:auto">
    ${entrees.length ? entrees.map(e=>`
      <div style="display:flex;gap:9px;align-items:baseline;padding:5px 0;border-bottom:1px solid var(--line);font:500 11.5px var(--sans)">
        <span style="color:var(--faint);width:132px;flex-shrink:0;font-family:var(--mono)">${new Date(e.horodatage).toLocaleString("fr-FR")}</span>
        <span style="color:${e.succes?'#12895C':'#E53935'};width:12px;flex-shrink:0">${e.succes?"●":"✕"}</span>
        <span style="color:var(--ink);font-weight:700;width:96px;flex-shrink:0">${E(e.identifiant||"—")}</span>
        <span style="color:var(--muted);width:150px;flex-shrink:0">${E(e.action||"")}</span>
        <span style="color:var(--faint);flex:1;min-width:0">${E(e.ressource||"")} ${E(e.detail||"")}</span>
        <span style="color:var(--faint);font-family:var(--mono);flex-shrink:0">${E(e.adresse_ip||"")}</span>
      </div>`).join("")
      : `<div style="color:var(--faint);font:500 12px var(--sans)">Aucune entrée.</div>`}
    </div></div>`;
}

// Masque les onglets auxquels le compte n'a pas droit. Purement cosmétique : c'est le serveur
// qui refuse. Mais laisser dans le menu une porte qui répond 403 fait passer une règle de
// sécurité pour une panne.
function _appliquerDroits(){
  const u = SB_UTILISATEUR;
  const admin = u && u.role === "admin";
  const el = document.getElementById("nav-admin");
  if(el) el.style.display = admin ? "" : "none";
  if(!u || admin) return;
  const droits = u.droits || [];
  document.querySelectorAll(".nav-item[data-go]").forEach(a=>{
    const section = SECTION_DE_PAGE[a.dataset.go];
    if(section && !droits.includes(section)) a.style.display = "none";
  });
  ["nav-ajout","nav-refresh"].forEach(id=>{
    const n = document.getElementById(id);
    if(n && !droits.includes("ajout")) n.style.display = "none";
  });
  // Le bouton flottant et la barre de recherche mènent tous deux à l'assistant. Les laisser
  // visibles à un compte qui n'y a pas droit, c'est proposer une porte qui se ferme au nez :
  // le serveur refuse (403), et l'utilisateur ne comprend pas pourquoi on la lui montrait.
  if(!droits.includes("chat")){
    const fab = document.querySelector(".fab");
    if(fab) fab.style.display = "none";
    const rech = document.querySelector(".search");
    if(rech) rech.style.display = "none";
  }
  // Le bandeau défilant montre le résultat net de chaque banque : c'est de la santé
  // financière, et il est présent sur TOUS les écrans. Le laisser à un compte qui n'a pas ce
  // droit reviendrait à lui montrer par la bande ce qu'on lui refuse par la porte.
  if(!droits.includes("apercu")){
    const tk = document.querySelector(".ticker");
    if(tk) tk.style.display = "none";
  }
}

async function _deconnexion(){
  try{ await fetch("/api/logout", {method:"POST", credentials:"same-origin"}); }catch(e){}
  location.reload();
}

function _gateStart(disclaimerRead){
  const gate = document.getElementById("gate");
  if(!disclaimerRead){
    gate.innerHTML = _gateDisclaimer();
  } else {
    _gateShowLogin();
  }
  setTheme(localStorage.getItem("sb-theme") || "dark");   // ré-applique l'icône sur le gate injecté
}


window.addEventListener("resize", ()=>{
  document.querySelectorAll(".js-plotly-plot").forEach(p=>{
    // offsetParent===null → élément caché (display:none, dans un onglet non sélectionné, etc.).
    // Sur mobile, l'événement "resize" se déclenche très souvent (barre d'adresse, clavier virtuel,
    // rotation) : appeler resize() sur un graphique caché fait planter Plotly en interne et peut
    // laisser le graphique vide/cassé au moment où son onglet redevient visible.
    if(p.offsetParent===null) return;
    try{ Plotly.Plots.resize(p); }catch(e){}
  });
});

/* ════════════════════════════════════════════════════════════════════════
   AJOUTER DES DONNÉES — upload d'un document → pipeline (extraction → aperçu
   → stockage). Remplace l'ancien bouton « Paramètres ». Gère l'ajout d'une
   NOUVELLE banque (au-delà des 7). Flux : formulaire → progression → aperçu
   contrôlé → confirmation. Async via /api/ajout/* (jobs + polling).
   ════════════════════════════════════════════════════════════════════════ */
const _AJ = { type:"CB", banque:"", annee:"", semestre:"S1", segment:"Particuliers",
              file:null, stem:"", res:null, newBank:false };

// Seules CB et EF : données structurées par banque. La réglementation et les
// documents supplémentaires sont récupérés automatiquement par l'agent web.
const AJ_TYPES = [
  {k:"CB", t:"Conditions bancaires", d:"Tarifs par banque — semestriel", bank:true, sem:true },
  {k:"EF", t:"États financiers",     d:"Indicateurs par banque — annuel", bank:true, sem:false},
];

function _ajInjectStyle(){
  if(document.getElementById("aj-style")) return;
  const s=document.createElement("style"); s.id="aj-style";
  s.textContent=`
  #aj-ov{position:fixed;inset:0;z-index:100000;background:rgba(4,5,8,.62);backdrop-filter:blur(8px);
    -webkit-backdrop-filter:blur(8px);display:flex;align-items:flex-start;justify-content:center;
    padding:48px 16px;overflow:auto;opacity:0;transition:opacity .18s}
  #aj-ov.open{opacity:1}
  #aj-card{width:min(680px,96vw);background:var(--bg-surf);border:1px solid var(--line-2);
    border-radius:var(--r-card);box-shadow:0 24px 80px rgba(0,0,0,.45);overflow:hidden;
    transform:translateY(8px);transition:transform .2s;font-family:var(--sans)}
  #aj-ov.open #aj-card{transform:none}
  .aj-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
    padding:20px 24px 16px;border-bottom:1px solid var(--line)}
  .aj-head h2{margin:0;font:800 19px var(--display,inherit);color:var(--ink)}
  .aj-eyebrow{font:800 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;
    color:var(--accent-2);margin-bottom:6px}
  .aj-sub{font:500 12px var(--sans);color:var(--muted);margin-top:4px}
  .aj-x{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;line-height:1;padding:4px}
  .aj-x:hover{color:var(--ink)}
  .aj-body{padding:20px 24px 24px}
  .aj-lbl{font:700 11px var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
    margin:0 0 8px}
  .aj-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px}
  .aj-type{text-align:left;padding:12px 14px;border:1.5px solid var(--line-2);border-radius:12px;
    background:var(--bg-tile);cursor:pointer;transition:.14s}
  .aj-type:hover{border-color:var(--accent-2)}
  .aj-type.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 9%,transparent)}
  .aj-type b{display:block;font:800 13px var(--sans);color:var(--ink)}
  .aj-type span{display:block;font:500 11px var(--sans);color:var(--muted);margin-top:2px}
  .aj-row{margin-bottom:16px}
  .aj-in,.aj-sel{width:100%;padding:10px 12px;border:1.5px solid var(--line-2);border-radius:10px;
    background:var(--bg-tile);color:var(--ink);font:600 13px var(--sans);box-sizing:border-box}
  .aj-in:focus,.aj-sel:focus{outline:none;border-color:var(--accent-2)}
  .aj-lock{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;
    border:1.5px solid var(--line);border-radius:10px;background:color-mix(in srgb,var(--bg-tile) 55%,transparent);
    color:var(--ink);font:800 13px var(--sans);box-sizing:border-box;opacity:.9}
  .aj-lock::after{content:"🔒";font-size:10px;opacity:.45;margin-left:8px}
  .aj-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .aj-seg{display:flex;gap:6px}
  .aj-seg button{flex:1;padding:9px;border:1.5px solid var(--line-2);border-radius:9px;background:var(--bg-tile);
    color:var(--muted);font:700 12px var(--sans);cursor:pointer}
  .aj-seg button.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 9%,transparent);color:var(--ink)}
  .aj-hint{font:600 11.5px var(--sans);color:var(--accent-2);margin-top:7px}
  .aj-drop{display:block;border:1.5px dashed var(--line-2);border-radius:12px;padding:20px;text-align:center;
    cursor:pointer;transition:.14s;background:var(--bg-tile)}
  .aj-drop:hover{border-color:var(--accent-2)}
  .aj-drop.has{border-style:solid;border-color:var(--accent)}
  .aj-drop .ic{font-size:26px;display:block;margin-bottom:6px;line-height:1}
  .aj-drop .fn{display:block;font:700 13px var(--sans);color:var(--ink);word-break:break-all}
  .aj-drop .hint{display:block;font:500 11px var(--sans);color:var(--muted);margin-top:4px}
  .aj-foot{display:flex;gap:10px;justify-content:flex-end;margin-top:22px}
  .aj-btn{padding:11px 20px;border-radius:10px;border:1px solid var(--line-2);background:var(--bg-tile);
    color:var(--ink);font:800 12.5px var(--sans);cursor:pointer;transition:.14s}
  .aj-btn:hover{border-color:var(--muted)}
  .aj-btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}
  .aj-btn.pri:hover{background:var(--accent-deep)}
  .aj-btn:disabled{opacity:.5;cursor:not-allowed}
  .aj-err{background:color-mix(in srgb,var(--accent) 8%,transparent);border:1px solid var(--accent);
    border-radius:10px;padding:11px 14px;font:600 12px var(--sans);color:var(--accent-2);margin-bottom:14px}
  .aj-prog{padding:20px 4px}
  .aj-bar{height:8px;border-radius:6px;background:var(--line-2);overflow:hidden;margin:14px 0}
  .aj-bar > i{display:block;height:100%;width:30%;background:var(--accent);border-radius:6px;
    transition:width .3s}
  .aj-stage{font:700 13px var(--sans);color:var(--ink);text-align:center}
  .aj-stages{margin-top:16px;display:flex;flex-direction:column;gap:6px}
  .aj-step{font:600 12px var(--sans);color:var(--muted);display:flex;gap:8px;align-items:center}
  .aj-step.done{color:var(--ink)} .aj-step .dot{width:7px;height:7px;border-radius:50%;background:var(--line-2)}
  .aj-step.done .dot{background:var(--accent)}
  .aj-sum{display:flex;gap:18px;margin-bottom:14px}
  .aj-sum div b{display:block;font:800 22px var(--display,inherit);color:var(--ink)}
  .aj-sum div span{font:600 11px var(--sans);color:var(--muted)}
  .aj-prev{max-height:280px;overflow:auto;border:1px solid var(--line);border-radius:10px}
  .aj-prev table{width:100%;border-collapse:collapse;font:500 12px var(--sans)}
  .aj-prev th{position:sticky;top:0;background:var(--bg-raise);color:var(--muted);font:700 10px var(--sans);
    text-transform:uppercase;letter-spacing:.05em;text-align:left;padding:8px 10px}
  .aj-prev td{padding:7px 10px;border-top:1px solid var(--line);color:var(--ink)}
  .aj-prev td.v{text-align:right;font-weight:700;white-space:nowrap}
  .aj-ok{text-align:center;padding:18px 0}
  .aj-ok .ic{font-size:44px}
  .aj-ok h3{margin:10px 0 4px;font:800 17px var(--sans);color:var(--ink)}
  .aj-ok p{font:600 12.5px var(--sans);color:var(--muted);margin:0}`;
  document.head.appendChild(s);
}

function openAjout(){
  closeNav();
  _ajInjectStyle();
  let ov=document.getElementById("aj-ov");
  if(!ov){
    ov=document.createElement("div"); ov.id="aj-ov";
    ov.onclick=e=>{ if(e.target===ov) closeAjout(); };
    ov.innerHTML=`<div id="aj-card"></div>`;
    document.body.appendChild(ov);
  }
  document.body.style.overflow="hidden";
  requestAnimationFrame(()=>ov.classList.add("open"));
  _ajForm();
}
function closeAjout(){
  const ov=document.getElementById("aj-ov"); if(!ov) return;
  ov.classList.remove("open"); document.body.style.overflow="";
  setTimeout(()=>ov.remove(), 200);
}

function _ajShell(inner, title, subtitle, onClose){
  document.getElementById("aj-card").innerHTML=`
    <div class="aj-head">
      <div><div class="aj-eyebrow">SpyBusiness</div>
        <h2>${title||"Ajouter des données"}</h2>
        <div class="aj-sub">${subtitle||"Importez un document — extraction et stockage automatiques"}</div></div>
      <button class="aj-x" onclick="${onClose||"closeAjout()"}">✕</button>
    </div>
    <div class="aj-body">${inner}</div>`;
}

function _ajForm(err){
  const T=AJ_TYPES.find(x=>x.k===_AJ.type)||AJ_TYPES[0];
  const types=AJ_TYPES.map(x=>`<button class="aj-type ${x.k===_AJ.type?'on':''}" onclick="_ajSetType('${x.k}')">
      <b>${x.t}</b><span>${x.d}</span></button>`).join("");
  const bankRow = T.bank ? `
    <div class="aj-row">
      <p class="aj-lbl">Banque</p>
      <select class="aj-sel" id="aj-bank" onchange="_ajBankChange()"><option>Chargement…</option></select>
      <div id="aj-newbank" style="display:none;margin-top:10px">
        <select class="aj-sel" id="aj-bnew" onchange="_ajNewBankPick()"><option value="">— Choisir une banque UEMOA —</option></select>
        <div class="aj-hint" id="aj-bcode-hint" style="color:var(--muted)">Banques de Côte d'Ivoire (registre UEMOA) non encore suivies.</div>
        <label class="aj-drop ${_AJ.logo?'has':''}" id="aj-logo-drop" style="margin-top:10px;min-height:auto;padding:12px 14px">
          <input type="file" id="aj-logo" accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif" style="display:none" onchange="_ajLogoFile(this)">
          <span class="ic">${_AJ.logo?'🖼️':'⬆'}</span>
          <span class="fn">${_AJ.logo? _AJ.logo.name : 'Logo de la banque (optionnel)'}</span>
          <span class="hint">${_AJ.logo? (Math.round(_AJ.logo.size/1024)+' Ko') : 'PNG / JPG / SVG — sinon un badge initiales sera généré'}</span>
        </label>
      </div>
    </div>` : "";
  const perRow = (T.bank) ? `
    <div class="aj-row">
      <p class="aj-lbl">Période <span style="font-weight:500;color:var(--faint);text-transform:none;letter-spacing:0">— déterminée automatiquement</span></p>
      <div class="aj-2">
        <div class="aj-lock" id="aj-annee-disp">${_AJ.annee||'—'}</div>
        ${T.sem ? `<div class="aj-lock" id="aj-sem-disp">${_AJ.semestre||'—'}</div>` : `<div></div>`}
      </div>
      ${T.sem ? `<div class="aj-row" style="margin:12px 0 0">
        <p class="aj-lbl">Segment</p>
        <div class="aj-seg" id="aj-seg">
          <button class="${_AJ.segment==='Particuliers'?'on':''}" onclick="_ajSeg('Particuliers')">Particuliers</button>
          <button class="${_AJ.segment==='Entreprises'?'on':''}" onclick="_ajSeg('Entreprises')">Entreprises</button>
        </div></div>` : ``}
      <div class="aj-hint" id="aj-hint"></div>
    </div>` : "";
  _ajShell(`
    ${err?`<div class="aj-err">${err}</div>`:""}
    <p class="aj-lbl">Type de document</p>
    <div class="aj-grid">${types}</div>
    ${bankRow}${perRow}
    <div class="aj-row">
      <p class="aj-lbl">Document</p>
      <label class="aj-drop ${_AJ.file?'has':''}" id="aj-drop">
        <input type="file" id="aj-file" accept=".pdf,.jpg,.jpeg,.png,.xlsx" style="display:none" onchange="_ajFile(this)">
        <span class="ic">${_AJ.file?'📄':'⬆'}</span>
        <span class="fn">${_AJ.file? _AJ.file.name : 'Choisir un fichier'}</span>
        <span class="hint">${_AJ.file? (Math.round(_AJ.file.size/1024)+' Ko') : 'PDF, image (JPG/PNG) ou Excel'}</span>
      </label>
    </div>
    <div class="aj-foot">
      <button class="aj-btn" onclick="closeAjout()">Annuler</button>
      <button class="aj-btn pri" onclick="_ajAnalyser()">Analyser le document →</button>
    </div>`);
  if(T.bank) _ajLoadBanks();
}

async function _ajLoadBanks(){
  const sel=document.getElementById("aj-bank"); if(!sel) return;
  let list=[], nouv=[];
  try{ const r=await fetch("/api/ajout/banques"); const j=await r.json(); list=j.banques||[]; nouv=j.nouvelles||[]; }catch(e){}
  const opts=list.map(b=>`<option value="${b.code}" ${b.code===_AJ.banque?'selected':''}>${b.code} — ${b.nom_complet||''}</option>`).join("");
  sel.innerHTML=`<option value="">— Choisir —</option>${opts}<option value="__new__">➕ Nouvelle banque…</option>`;
  const ns=document.getElementById("aj-bnew");
  if(ns) ns.innerHTML=`<option value="">— Choisir une banque UEMOA —</option>`
        + nouv.map(b=>`<option value="${b.code}" ${b.code===_AJ.banque?'selected':''}>${b.nom_complet}</option>`).join("");
  if(_AJ.newBank) sel.value="__new__";
  _ajBankChange();
}

function _ajSetType(k){ _AJ.type=k; _AJ.annee=""; _AJ.semestre="S1"; _ajForm(); }
function _ajSeg(s){ _AJ.segment=s; _ajForm(); _ajNextPeriod(); }

// Affichage VERROUILLÉ de la période (année + semestre, non éditables — dynamiques)
function _ajUpdatePeriod(){
  const a=document.getElementById("aj-annee-disp"); if(a) a.textContent=_AJ.annee||"—";
  const s=document.getElementById("aj-sem-disp");   if(s) s.textContent=_AJ.semestre||"—";
}

function _ajBankChange(){
  const sel=document.getElementById("aj-bank"); if(!sel) return;
  const nb=document.getElementById("aj-newbank");
  if(sel.value==="__new__"){
    _AJ.newBank=true; _AJ.banque=""; _AJ.banque_nom="";
    if(nb) nb.style.display="block";
  }else{
    _AJ.newBank=false; _AJ.banque=sel.value; _AJ.banque_nom=""; _AJ.logo=null;
    if(nb) nb.style.display="none";
  }
  _ajNextPeriod();
}

// Choix d'une NOUVELLE banque dans la liste UEMOA → code + nom officiels ; période figée 2024 S1.
function _ajNewBankPick(){
  const s=document.getElementById("aj-bnew"); if(!s) return;
  _AJ.banque = s.value;
  _AJ.banque_nom = ((s.options[s.selectedIndex]||{}).textContent || "").trim();
  _ajNextPeriod();
}

async function _ajNextPeriod(){
  const hint=document.getElementById("aj-hint");
  // NOUVELLE banque → l'analyse démarre TOUJOURS à 2024 S1 (2024 pour EF). Non modifiable.
  if(_AJ.newBank){
    _AJ.annee=2024; _AJ.semestre="S1"; _ajUpdatePeriod();
    if(hint) hint.innerHTML = _AJ.banque
      ? `⮞ Nouvelle banque — l'analyse démarre à <b>2024${_AJ.type==="CB"?" S1":""}</b> (période figée : on a commencé à 2024).`
      : `⮞ Choisissez la banque — la période démarrera à <b>2024${_AJ.type==="CB"?" S1":""}</b>.`;
    return;
  }
  if(!_AJ.banque){ _AJ.annee=""; _AJ.semestre="S1"; _ajUpdatePeriod(); if(hint) hint.textContent=""; return; }
  try{
    const u=`/api/ajout/prochaine_periode?type=${_AJ.type}&banque=${encodeURIComponent(_AJ.banque)}&segment=${encodeURIComponent(_AJ.segment)}`;
    const d=await (await fetch(u)).json();
    _AJ.annee=d.annee; if(d.semestre) _AJ.semestre=d.semestre;
    _ajUpdatePeriod();
    const next = d.semestre ? `${d.annee} ${d.semestre}` : `${d.annee}`;
    if(hint) hint.innerHTML = d.existant
      ? `⮞ Dernier en base : <b>${d.existant}</b> — prochain (auto) : <b>${next}</b>`
      : `⮞ Aucune donnée — démarre à <b>${next}</b>`;
  }catch(e){ if(hint) hint.textContent=""; }
}

function _ajFile(inp){ _AJ.file = inp.files[0]||null; _ajForm(); }
function _ajLogoFile(inp){ _AJ.logo = inp.files[0]||null; _ajForm(); }

function _ajAnalyser(){
  const T=AJ_TYPES.find(x=>x.k===_AJ.type);
  if(!_AJ.file) return _ajForm("Veuillez choisir un fichier.");
  if(T.bank){
    if(_AJ.newBank && !_AJ.banque)
      return _ajForm("Choisissez la nouvelle banque dans la liste UEMOA.");
    if(!_AJ.banque) return _ajForm("Veuillez choisir une banque.");
    if(!_AJ.annee)  return _ajForm("Période non déterminée — réessayez.");
  }
  const fd=new FormData();
  fd.append("type",_AJ.type); fd.append("fichier",_AJ.file);
  if(T.bank){ fd.append("banque",_AJ.banque); fd.append("annee",_AJ.annee); }
  if(T.sem){ fd.append("semestre",_AJ.semestre); fd.append("segment",_AJ.segment); }
  if(_AJ.newBank){ fd.append("banque_nom",_AJ.banque_nom||""); }
  _ajProgress("Analyse du document");
  fetch("/api/ajout/extraire",{method:"POST",body:fd})
    .then(r=>r.json()).then(j=>{
      if(!j.ok||!j.job) return _ajForm(j.message||"Échec du lancement.");
      _ajPoll(j.job, res=>{ _AJ.res=res; _AJ.stem=res.stem||""; _ajPreview(res); });
    }).catch(e=>_ajForm("Erreur réseau : "+e.message));
}

const _AJ_STEPS=["Sauvegarde du document","Extraction","Nettoyage","Aperçu prêt"];
function _ajProgress(stage){
  _ajShell(`<div class="aj-prog">
    <div class="aj-stage" id="aj-stage">${stage}…</div>
    <div class="aj-bar"><i id="aj-fill" style="width:18%"></i></div>
    <div class="aj-sub" style="text-align:center">Extraction OCR / coordonnées puis normalisation — cela peut prendre un moment.</div>
  </div>`);
}

function _ajPoll(job, onDone){
  let n=0;
  const tick=async()=>{
    n++;
    try{
      const d=await (await fetch(`/api/ajout/statut?job=${job}`)).json();
      const st=document.getElementById("aj-stage"); const fill=document.getElementById("aj-fill");
      if(st && d.stage) st.textContent=d.stage+"…";
      if(fill){ const idx=_AJ_STEPS.findIndex(s=>(d.stage||"").startsWith(s.slice(0,8)));
        fill.style.width=Math.min(92, 18+(idx>=0?idx:n)*22)+"%"; }
      if(d.status==="done"){ if(fill) fill.style.width="100%"; return onDone(d.result); }
      if(d.status==="error"){ return _ajForm((d.result&&d.result.message)||"Le traitement a échoué."); }
    }catch(e){}
    setTimeout(tick, 1300);
  };
  setTimeout(tick, 900);
}

function _ajPreview(res){
  if(!res || !res.ok) return _ajForm((res&&res.message)||"Aucune donnée exploitable extraite.");
  const rows=(res.preview||[]).map(r=>`<tr><td>${r.section||''}</td><td>${(r.libelle||'').slice(0,80)}</td>
      <td class="v">${(r.valeur||'').toString().slice(0,40)}</td></tr>`).join("");
  const meta = res.type==="CB" ? `${res.banque} · ${res.annee} ${res.semestre} · ${res.segment}`
             : res.type==="EF" ? `${res.banque} · ${res.annee}`
             : (res.fichier||"");
  _ajShell(`
    <div class="aj-err" style="background:color-mix(in srgb,#1a9d4b 10%,transparent);border-color:#1a9d4b;color:#1a9d4b">
      ✓ Document analysé — vérifiez l'aperçu avant de stocker.</div>
    <p class="aj-lbl">${meta}</p>
    <div class="aj-sum">
      <div><b>${res.lignes||0}</b><span>lignes extraites</span></div>
      <div><b>${res.avec_valeur||0}</b><span>avec valeur</span></div>
    </div>
    <div class="aj-prev"><table>
      <thead><tr><th>Section</th><th>Libellé</th><th>Valeur</th></tr></thead>
      <tbody>${rows||'<tr><td colspan=3 style="color:var(--muted)">Aperçu indisponible</td></tr>'}</tbody>
    </table></div>
    <div class="aj-sub" style="margin-top:10px">Aperçu des 20 premières lignes — l'ensemble sera stocké.</div>
    <div class="aj-foot">
      <button class="aj-btn" onclick="_ajForm()">← Modifier</button>
      <button class="aj-btn pri" onclick="_ajStocker()">Confirmer et stocker en base →</button>
    </div>`);
}

function _ajStocker(){
  _ajProgress("Stockage en base");
  const body={ type:_AJ.type, banque:_AJ.banque, annee:_AJ.annee, semestre:_AJ.semestre,
               segment:_AJ.segment, stem:_AJ.stem,
               banque_nom:_AJ.banque_nom||"", banque_groupe:_AJ.banque_groupe||"" };
  fetch("/api/ajout/stocker",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(j=>{
      if(!j.ok||!j.job) return _ajPreview(_AJ.res);
      _ajPoll(j.job, res=>_ajUploadLogoThenDone(res));
    }).catch(e=>_ajPreview(_AJ.res));
}

// Après un stockage réussi : si une NOUVELLE banque avec logo, on téléverse le logo
// (assets/logos/<CODE>.<ext>) puis on affiche l'écran de succès. Sans logo → badge initiales.
function _ajUploadLogoThenDone(res){
  if(res && res.ok && _AJ.newBank && _AJ.logo && _AJ.banque){
    const lf=new FormData(); lf.append("logo",_AJ.logo); lf.append("banque",_AJ.banque);
    fetch("/api/ajout/logo",{method:"POST",body:lf})
      .then(r=>r.json()).catch(()=>{}).finally(()=>_ajDone(res));
  } else {
    _ajDone(res);
  }
}

function _ajDone(res){
  if(!res||!res.ok) return _ajPreview(_AJ.res);
  _ajShell(`
    <div class="aj-ok">
      <div class="ic">✅</div>
      <h3>Données ajoutées</h3>
      <p>${res.message||((res.stockees||0)+" enregistrements stockés.")}</p>
      <p style="margin-top:6px">Les tableaux de bord se rafraîchiront au prochain chargement.</p>
    </div>
    <div class="aj-foot" style="justify-content:center">
      <button class="aj-btn" onclick="_ajReset()">Ajouter un autre</button>
      <button class="aj-btn pri" onclick="closeAjout()">Terminer</button>
    </div>`);
}
function _ajReset(){ _AJ.file=null; _AJ.res=null; _AJ.stem=""; _AJ.logo=null; _ajForm(); }
