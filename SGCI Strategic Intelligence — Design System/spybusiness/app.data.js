/* SpyBusiness — data + Plotly chart factory (theme-aware + API réelle). */

/* ── Helpers mise en forme analyses ────────────────────────────────────
   Q()  = question / supposition     → amber gras italic   🟡
   G()  = gain / potentiel chiffré   → vert gras            🟢
   K()  = affirmation clé / insight  → gras, ligne propre   ⬜
   Toutes les analyses doivent utiliser ces helpers pour cohérence.
──────────────────────────────────────────────────────────────────────── */
const Q = t => `<span style="color:#E8A020;font-weight:700;font-style:italic">${t}</span>`;
const G = t => `<b>${t}</b>`;
const K = t => `<b>${t}</b>`;


const L = b => `assets/logos/${b}`;
const BANKS = [
  { id:"sgci",    s:"SGCI",    lg:L("SGCI.png"),    focus:1 },
  { id:"ecobank", s:"ECOBANK", lg:L("ECOBANK.png") },
  { id:"baci",    s:"BACI",    lg:L("BACI.png") },
  { id:"sib",     s:"SIB",     lg:L("SIB.png") },
  { id:"bicici",  s:"BICICI",  lg:L("BICICI.png") },
  { id:"nsia",    s:"NSIA",    lg:L("NSIA.png") },
  { id:"bni",     s:"BNI",     lg:L("BNI.jpg") },
];
const bankBy = s => BANKS.find(b => b.s === s) || BANKS.find(b => b.s === String(s||"").toUpperCase());

// Badge initiales (SVG data-URI) quand une banque n'a pas de logo image (fallback évolutif).
function _initialsLogo(name){
  const init = String(name||"?").replace(/[^A-Za-z0-9]/g,"").slice(0,3).toUpperCase() || "?";
  const col  = (typeof _bkCol === "function") ? _bkCol(String(name||"").toUpperCase()) : "#4A90D9";
  const fs   = init.length > 2 ? 19 : 26;
  const svg  = "<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'>"
    + "<rect width='64' height='64' rx='13' fill='" + col + "'/>"
    + "<text x='32' y='33' dy='.35em' text-anchor='middle' font-family='Arial,Helvetica,sans-serif' font-weight='700' font-size='" + fs + "' fill='#ffffff'>" + init + "</text></svg>";
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// Fusionne la carte des logos (fichiers présents sur disque) + la liste dynamique des banques
// dans BANKS → bankBy(x).lg renvoie TOUJOURS un rendu (logo réel ou badge initiales).
function _mergeBankLogos(logoMap, bankList){
  const map   = logoMap || {};
  const banks = (bankList && bankList.length) ? bankList : CB_BANKS;
  (banks || []).forEach(code => {
    const CODE = String(code).toUpperCase();
    const real = map[CODE];
    let e = BANKS.find(b => b.s.toUpperCase() === CODE);
    if(e){ if(real) e.lg = real; else if(!e.lg) e.lg = _initialsLogo(CODE); }
    else { BANKS.push({ id: CODE.toLowerCase(), s: CODE, lg: real || _initialsLogo(CODE) }); }
  });
}

/* ── Données initiales (mock) — remplacées par l'API au chargement ── */
// NOTE: let (pas const) pour que loadAll() puisse les mettre à jour

let FRAIS = {
  SGCI:2350, NSIA:1800, BNI:2000,
  BACI:5000, SIB:4900,  BICICI:5200, ECOBANK:4900,
};

let RN2025 = {
  SGCI:101228, ECOBANK:57477, BACI:38229,
  SIB:50234,   BICICI:26226,  NSIA:38112, BNI:34932,
};

// Format {years:[...], values:[...]} pour compatibilité API + charts
let RN_SERIES = {
  SGCI:    { years:[2021,2022,2023,2024,2025], values:[72000,80500,88200,94100,101228] },
  ECOBANK: { years:[2021,2022,2023,2024,2025], values:[41000,46500,50200,54100,57477]  },
  BACI:    { years:[2021,2022,2023,2024,2025], values:[26000,29500,32800,35600,38229]  },
  SIB:     { years:[2021,2022,2023,2024,2025], values:[22000,24800,27200,29400,50234]  },
  BICICI:  { years:[2021,2022,2023,2024,2025], values:[20500,22900,25100,26800,26226]  },
  NSIA:    { years:[2021,2022,2023,2024,2025], values:[15200,17600,19400,20900,38112]  },
  BNI:     { years:[2021,2022,2023,2024,2025], values:[12800,14500,15900,17300,34932]  },
};

let TICKER = [
  { s:"SGCI",    v:"101,2 Mds", d:"+7,6%", up:1 },
  { s:"ECOBANK", v:"57,5 Mds",  d:"+5,2%", up:1 },
  { s:"BACI",    v:"38,2 Mds",  d:"+3,1%", up:1 },
  { s:"SIB",     v:"50,2 Mds",  d:"+2,4%", up:1 },
  { s:"BICICI",  v:"26,2 Mds",  d:"-1,4%", up:0 },
  { s:"NSIA",    v:"38,1 Mds",  d:"+2,3%", up:1 },
  { s:"BNI",     v:"34,9 Mds",  d:"-0,8%", up:0 },
];

let CB_DATA          = null;
let KPI_DATA         = null;
let FRAIS_MOY        = {};
let PNB_DATA         = {};
let ROE_DATA         = {};
let MARGE_NETTE_DATA = {};  // RN/PNB %
let COEFF_EXPL_DATA  = {};  // Charges/PNB %
let COUT_R_PNB_DATA  = {};  // Coût risque/PNB %
let ROA_DATA         = {};  // RN/Total actif %
let CREDITS_DATA     = {};  // Crédits clientèle M FCFA
let DEPOTS_DATA      = {};  // Dépôts clientèle M FCFA
let INTERETS_DATA    = {};  // Intérêts et produits assimilés M FCFA
let COMMISSIONS_DATA = {};  // Commissions (produits) M FCFA
let AUTRES_PROD_DATA = {};  // Autres produits d'exploitation M FCFA
let RBE_DATA         = {};  // Résultat Brut d'Exploitation M FCFA
let RE_DATA          = {};  // Résultat d'Exploitation M FCFA
let RESILIENCE_DATA  = {};  // Ratios résilience Section ⑤
let PNB_SERIES       = {};  // Série PNB par banque {bank:{year:val}}
let ROE_SERIES       = {};  // Série ROE par banque {bank:{year:val}}
let COEFF_SERIES     = {};  // Série coeff exploitation {bank:{year:val}}
let CNR_SERIES       = {};  // Ratio CNR/Encours en points de base {bank:{year:val}}
let CB_ANNEES   = [2024, 2025, 2026]; // années CB disponibles — chargées depuis /api/cb_annees
// Semestres réellement disponibles PAR ANNÉE — chargés depuis /api/cb_periodes (2026-07-30).
// Le sélecteur proposait S1 et S2 en dur pour toute année ; or 2026 n'a que S1, et cliquer
// « 2026 S2 » plaçait l'écran dans un état incohérent. Valeur initiale = simple filet le
// temps du chargement, remplacée par la vérité de la base.
let CB_PERIODES = {};
let RADAR_BANK  = "SGCI";            // banque affichée dans le Portrait compétitif

// Filtres Vue d'ensemble — deux groupes INDÉPENDANTS
let APERCU_FILTERS = {
  // Groupe A : Conditions Bancaires (CB) — n'affecte PAS les États Financiers
  frais_annee: 2026,
  frais_sem:   "S1",
  frais_seg:   "Particuliers",
  // Groupe B : États Financiers (EF) — n'affecte PAS les CB
  rn_anx:      3,   // 1=AN1, 2=AN2, 3=AN3
};

/* ══════════════════════════════════════════════════════════════════════════════════════
   ÉCRAN DE CHARGEMENT (2026-08-10)
   ══════════════════════════════════════════════════════════════════════════════════════
   Demandé par le directeur, référence visuelle à l'appui : un cercle de progression posé
   SUR la page, celle-ci restant devinée en arrière-plan, avec le pourcentage au centre. Il
   s'affiche à CHAQUE changement d'onglet et ne se retire qu'une fois toutes les données
   arrivées — plus de contenu qui se remplit par morceaux sous les yeux.

   POURQUOI UN POURCENTAGE RÉEL, ET COMMENT. Un pourcentage inventé qui avance tout seul est
   un mensonge que l'utilisateur repère au premier écran lent. Celui-ci compte les requêtes :
   dénominateur = tout ce qui est parti depuis le début de la navigation, numérateur = ce qui
   est revenu. Le total GRANDIT en cours de route, puisqu'une réponse en déclenche d'autres —
   la barre reculerait donc naturellement. On l'en empêche : un taux ne redescend jamais, sans
   quoi il donne l'impression que le travail se défait.

   CE QUI N'EST PAS COMPTÉ : le chat et les textes rédigés par le modèle de langage. Ils
   mettent des dizaines de secondes et ne portent AUCUN chiffre — les tableaux sont déjà à
   l'écran quand ils arrivent. Les attendre retiendrait l'écran longtemps après que tout soit
   lisible, exactement l'inverse du but recherché.

   FILET DE SÉCURITÉ. Au-delà de vingt-cinq secondes, l'écran se retire quoi qu'il reste en
   vol. Un écran de chargement qui ne part jamais est une panne pire que celle qu'il masque ;
   mesuré une fois à quarante-deux secondes parce que les requêtes s'enchaînent sans fin.
   ══════════════════════════════════════════════════════════════════════════════════════ */
const _CHARGEMENT = {
  total: 0,        // requêtes parties depuis le début de la navigation
  faites: 0,       // requêtes revenues
  taux: 0,         // pourcentage affiché — ne redescend jamais
  apparition: null,
  filet: null,
  veilleur: null,      // surveille l'arrêt de la progression
  dernierMouvement: 0, // horodatage du dernier départ ou retour
  clos: false,         // l'écran a déjà été montré ET retiré pour cette vue
  // Horodaté DÈS LE CHARGEMENT DU SCRIPT, pas à zéro : au tout premier affichage, `go()`
  // n'a pas encore été appelé, et une fenêtre ouverte à l'époque 0 serait déjà refermée —
  // aucune requête ne compterait, et l'écran ne paraîtrait jamais au démarrage.
  debutVue: Date.now(),
  demarrage: false // vrai quand l'hébergeur répond une page d'attente (service au réveil)
};

/* RÈGLE D'ARRÊT : ON FERME QUAND PLUS RIEN NE PROGRESSE, PAS QUAND TOUT EST FINI.

   Énumérer les appels d'arrière-plan dans une liste était sans fin — à peine `cb_repricing`
   écarté, `cb_rattrapage_depassement` prenait sa place, puis un autre. Chaque écran a ses
   traînards, et la liste aurait vieilli au premier endpoint ajouté.

   La progression, elle, est observable sans rien savoir des endpoints : tant que des réponses
   arrivent, l'écran a une raison d'être ; dès que plus rien ne bouge pendant deux secondes,
   c'est que ce qui reste en vol est lent — et le contenu déjà rendu est lisible. Mesuré : le
   compteur stagnait à 82 % dès la 8ᵉ seconde et ne bougeait plus jusqu'au filet de 25 s. */
const _STAGNATION = 2000;

const _DELAI_AVANT_ECRAN = 300;    // en dessous, une donnée en cache ferait clignoter l'écran
const _FILET_ECRAN = 25000;

/* CE QUE L'ÉCRAN DE CHARGEMENT N'ATTEND PAS.
   Mesuré sur le service en ligne, écran « Conditions bancaires » : le compteur restait bloqué
   à 18 sur 20 et l'écran ne partait qu'au filet de 25 secondes — alors que le contenu était
   lisible dès la quatrième. Deux appels ne revenaient pas dans l'intervalle : `cb_repricing`
   et `cb_evolutions_all`.

   Ni l'un ni l'autre ne porte le contenu principal de l'écran : ce sont des enrichissements
   déclenchés en arrière-plan, qui complètent des encarts déjà affichés. Les attendre revenait
   à cacher une page prête pendant vingt secondes.

   Même raison pour le chat et les textes rédigés par le modèle de langage : dizaines de
   secondes, aucun chiffre, et chacun affiche déjà sa propre attente à sa place.

   RÈGLE : l'écran attend la donnée SANS LAQUELLE la page n'a pas de sens — pas celle qui la
   rend meilleure. */
const _ARRIERE_PLAN = /\/api\/(chat|approfondir|conv_history|[a-z_0-9]*_llm)/;

/* FENÊTRE DE CHARGEMENT INITIAL — trois secondes après le changement d'onglet.

   C'est la règle qui a fini par marcher, après deux qui ont échoué :

     — la LISTE d'endpoints d'arrière-plan était sans fin : à peine `cb_repricing` écarté,
       `cb_rattrapage_depassement` prenait sa place, puis un autre. Elle aurait vieilli au
       premier endpoint ajouté ;
     — la STAGNATION (fermer quand rien ne bouge) fermait sur une requête longue, qui produit
       légitimement un long silence : l'écran partait à 4 s en découvrant une page vide.

   Ce qui distingue vraiment les deux familles n'est ni leur nom ni leur durée, c'est LE MOMENT
   OÙ ELLES PARTENT. Le contenu principal se demande immédiatement, dans la foulée du rendu ;
   les enrichissements sont déclenchés ensuite, par le code qui vient d'afficher la page.
   Trois secondes séparent les deux sans jamais avoir à les nommer.

   Mesuré sur « Conditions bancaires » : contenu complet à 10 s, écran retenu jusqu'à 26 s par
   un appel d'arrière-plan parti bien après. */
const _FENETRE_INITIALE = 3000;

function _ecranCreer(){
  if(document.getElementById("sb-chargement")) return;
  const d = document.createElement("div");
  d.id = "sb-chargement";
  d.style.cssText =
    "position:fixed;inset:0;z-index:9998;display:flex;flex-direction:column;align-items:center;"
  + "justify-content:center;gap:18px;pointer-events:all;"
  + "background:color-mix(in srgb, var(--bg-deep, #0B1220) 55%, transparent);"
  + "backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);"
  + "animation:sbApparait .18s ease-out";
  // Deux cercles superposés : un anneau clair immobile qui donne l'échelle, et par-dessus
  // l'arc de progression, dont la longueur suit le taux. Le tout tourne lentement pour que
  // l'écran reste vivant même quand une requête longue fige le pourcentage.
  d.innerHTML = `
    <div style="position:relative;width:104px;height:104px">
      <svg width="104" height="104" viewBox="0 0 104 104"
           style="transform:rotate(-90deg);animation:sbTourne 2.4s linear infinite">
        <circle cx="52" cy="52" r="46" fill="none" stroke-width="7"
                stroke="color-mix(in srgb, var(--accent-2, #E31C23) 18%, transparent)"></circle>
        <circle id="sb-arc" cx="52" cy="52" r="46" fill="none" stroke-width="7"
                stroke="var(--accent-2, #E31C23)" stroke-linecap="round"
                stroke-dasharray="289" stroke-dashoffset="289"
                style="transition:stroke-dashoffset .35s ease-out"></circle>
      </svg>
      <div id="sb-taux" style="position:absolute;inset:0;display:flex;align-items:center;
           justify-content:center;font:800 22px var(--mono, ui-monospace);
           color:var(--ink, #EAF1FB)">0 %</div>
    </div>
    <div style="font:700 14px var(--sans, system-ui);color:var(--ink, #EAF1FB);letter-spacing:.01em">
      Chargement des données…</div>
    <div id="sb-sous" style="font:500 12px var(--sans, system-ui);color:var(--muted, #93A6C0);
         text-align:center;max-width:320px;line-height:1.5"></div>`;
  document.body.appendChild(d);
  if(!document.getElementById("sb-chargement-css")){
    const st = document.createElement("style");
    st.id = "sb-chargement-css";
    st.textContent = "@keyframes sbTourne{to{transform:rotate(270deg)}}"
                   + "@keyframes sbApparait{from{opacity:0}to{opacity:1}}";
    document.head.appendChild(st);
  }
}

function _ecranMaj(){
  const d = document.getElementById("sb-chargement");
  if(!d) return;
  const arc = document.getElementById("sb-arc");
  const txt = document.getElementById("sb-taux");
  const sous = document.getElementById("sb-sous");
  // 289 ≈ 2πr pour r = 46. L'offset décroît quand le taux monte.
  if(arc) arc.setAttribute("stroke-dashoffset", String(289 - 289 * _CHARGEMENT.taux / 100));
  if(txt) txt.textContent = Math.round(_CHARGEMENT.taux) + " %";
  if(sous) sous.textContent = _CHARGEMENT.demarrage
    ? "Le service démarre — cela peut prendre une minute la première fois."
    : (_CHARGEMENT.total ? `${_CHARGEMENT.faites} bloc(s) sur ${_CHARGEMENT.total}` : "");
}

function _ecranRetirer(){
  clearTimeout(_CHARGEMENT.apparition); _CHARGEMENT.apparition = null;
  clearTimeout(_CHARGEMENT.filet); _CHARGEMENT.filet = null;
  clearInterval(_CHARGEMENT.veilleur); _CHARGEMENT.veilleur = null;
  const d = document.getElementById("sb-chargement");
  if(!d) return;
  _CHARGEMENT.clos = true;      // il ne reviendra pas avant le prochain changement d'onglet
  // On termine à 100 % avant de disparaître : un écran qui s'efface à 78 % laisse penser
  // qu'il manque quelque chose.
  _CHARGEMENT.taux = 100; _ecranMaj();
  d.style.transition = "opacity .22s ease-in";
  d.style.opacity = "0";
  setTimeout(()=>{ if(d.parentNode) d.remove(); }, 230);
}

function _ecranEtat(){
  /* UN SEUL ÉCRAN PAR NAVIGATION. Mesuré : l'écran se retirait bien à 6 secondes, puis
     REVENAIT à 8, 10 et 22 secondes. Les enrichissements d'arrière-plan continuent en effet
     de partir longtemps après que la page est lisible, et chaque départ replaçait le compteur
     en situation « inachevé ». L'utilisateur voyait donc sa page clignoter sous un voile
     alors qu'elle était complète — une impression de fragilité pire que l'attente initiale.
     Une fois l'écran retiré pour une vue, il ne revient qu'au prochain changement d'onglet. */
  if(_CHARGEMENT.clos) return;
  if(_CHARGEMENT.total > 0 && _CHARGEMENT.faites < _CHARGEMENT.total){
    const brut = 100 * _CHARGEMENT.faites / _CHARGEMENT.total;
    // Jamais en arrière : le total grandit quand une réponse en déclenche d'autres, et un
    // taux qui recule donne l'impression que le travail se défait.
    _CHARGEMENT.taux = Math.max(_CHARGEMENT.taux, Math.min(brut, 97));
    if(!document.getElementById("sb-chargement") && !_CHARGEMENT.apparition){
      _CHARGEMENT.apparition = setTimeout(()=>{
        _CHARGEMENT.apparition = null;
        if(_CHARGEMENT.faites >= _CHARGEMENT.total) return;   // tout est déjà revenu
        _ecranCreer(); _ecranMaj();
        clearTimeout(_CHARGEMENT.filet);
        _CHARGEMENT.filet = setTimeout(_ecranRetirer, _FILET_ECRAN);
        // Veilleur de stagnation : il ferme l'écran dès que plus rien n'avance, sans avoir
        // besoin de savoir QUELS appels traînent.
        clearInterval(_CHARGEMENT.veilleur);
        _CHARGEMENT.veilleur = setInterval(()=>{
          // Le veilleur ne ferme QUE si rien n'est en vol. Une requête longue produit
          // légitimement un long silence : la fermer dessus découvrirait une page vide —
          // mesuré, l'écran partait à 4 s alors que le contenu arrivait à 24 s.
          const enVol = _CHARGEMENT.total - _CHARGEMENT.faites;
          if(enVol <= 0 && Date.now() - _CHARGEMENT.dernierMouvement > _STAGNATION){
            _ecranRetirer();
          }
        }, 400);
      }, _DELAI_AVANT_ECRAN);
    }
    _ecranMaj();
  } else {
    _ecranRetirer();
  }
}

/* Appelé par go() à chaque changement d'onglet : on repart d'un compteur neuf, sinon le taux
   resterait bloqué à 100 % de la navigation précédente et l'écran ne reparaîtrait jamais. */
function chargementNouvelleVue(){
  _CHARGEMENT.total = 0;
  _CHARGEMENT.faites = 0;
  _CHARGEMENT.taux = 0;
  _CHARGEMENT.demarrage = false;
  _CHARGEMENT.clos = false;                  // le prochain écran est de nouveau autorisé
  _CHARGEMENT.dernierMouvement = Date.now(); // sinon le veilleur fermerait aussitôt
  _CHARGEMENT.debutVue = Date.now();         // ouvre la fenêtre de chargement initial
}

(function installerReprise(){
  const vraiFetch = window.fetch.bind(window);
  // Réveil du service : l'hébergement gratuit s'endort après quinze minutes et répond alors
  // une page d'attente HTML en 502/503. Les appels feraient .json() dessus et afficheraient
  // « Unexpected token '<' » — un message de programmeur pour une situation normale.
  const ATTENTES = [1500, 3000, 6000, 10000, 15000];

  window.fetch = async function(ressource, options){
    const url = typeof ressource === "string" ? ressource : (ressource && ressource.url) || "";
    if(!url.includes("/api/")) return vraiFetch(ressource, options);

    const dansLaFenetre = (Date.now() - _CHARGEMENT.debutVue) < _FENETRE_INITIALE;
    const compte = !_ARRIERE_PLAN.test(url) && dansLaFenetre;
    if(compte){ _CHARGEMENT.total++; _CHARGEMENT.dernierMouvement = Date.now(); _ecranEtat(); }
    try{
      let reponse = await vraiFetch(ressource, options);
      /* On ne réessaie que si c'est L'HÉBERGEUR qui parle, pas l'application. Le code seul
         ne les distingue pas : l'application répond elle aussi 503 quand le quota du modèle
         de langage est épuisé — réponse définitive, insister serait faire attendre pour rien.
         La page d'attente de l'hébergeur est du HTML ; le type de contenu tranche. */
      const deLHebergeur = (r) => {
        if(![502,503,504].includes(r.status)) return false;
        const t = (r.headers.get("content-type") || "").toLowerCase();
        return !t.includes("json");
      };
      for(let i = 0; i < ATTENTES.length && deLHebergeur(reponse); i++){
        _CHARGEMENT.demarrage = true; _ecranMaj();
        await new Promise(r => setTimeout(r, ATTENTES[i]));
        try{ reponse = await vraiFetch(ressource, options); }catch(e){ /* on retente */ }
      }
      _CHARGEMENT.demarrage = false;
      return reponse;
    } finally {
      // `finally` et non la ligne d'après : une requête qui échoue doit compter elle aussi,
      // sans quoi le total n'est jamais atteint et l'écran ne part plus.
      if(compte){ _CHARGEMENT.faites++; _CHARGEMENT.dernierMouvement = Date.now(); _ecranEtat(); }
    }
  };
})();

/* ── API helpers ─────────────────────────────────────────────────────── */
async function apiFetch(path){
  try{
    // credentials explicite : le cookie de session doit accompagner chaque appel. Le défaut
    // « same-origin » suffirait ici, mais l'écrire évite qu'un déplacement de l'API sur un
    // sous-domaine casse silencieusement l'authentification.
    const r = await fetch(path, { credentials:"same-origin" });
    // 401 : la session a expiré (12 h) ou le serveur a redémarré sans APP_SECRET_KEY fixe.
    // Rendre la main à la page de connexion vaut mieux qu'afficher un tableau de bord vide
    // dont l'utilisateur ne comprendrait pas pourquoi il ne se remplit pas.
    if(r.status === 401){
      if(typeof _gateRelock === "function") _gateRelock();
      return null;
    }
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch(e){
    console.warn("[API]", path, e.message);
    return null;
  }
}

// Liste DYNAMIQUE des banques (SOURCE UNIQUE côté front) — chargée depuis /api/cb_banks dans loadAll().
// Fallback = les 7 banques actuelles. Une nouvelle banque en base se propage partout via cette liste.
let CB_BANKS = ["BACI","BICICI","BNI","ECOBANK","NSIA","SGCI","SIB"];

async function loadAll(){
  const f = APERCU_FILTERS;
  const kpiUrl = `/api/kpis?frais_annee=${f.frais_annee}&frais_sem=${f.frais_sem}&frais_seg=${f.frais_seg}&rn_anx=${f.rn_anx}`;

  const [frais, rn, series, kpis, annees, periodes, resil, efSeries,
         cbPar24, cbPar25, cbPar26, cbEnt24, cbEnt25, cbEnt26, cbBanks, logos] = await Promise.all([
    apiFetch("/api/frais"),
    apiFetch("/api/rn"),
    apiFetch("/api/rn_series"),
    apiFetch(kpiUrl),
    apiFetch("/api/cb_annees"),
    apiFetch("/api/cb_periodes"),
    apiFetch(`/api/resilience?anx=${f.rn_anx}`),
    apiFetch("/api/ef_series"),
    apiFetch("/api/cb_bd?annee=2024&semestre=S1&segment=Particuliers"),
    apiFetch("/api/cb_bd?annee=2025&semestre=S1&segment=Particuliers"),
    apiFetch("/api/cb_bd?annee=2026&semestre=S1&segment=Particuliers"),
    apiFetch("/api/cb_bd?annee=2024&semestre=S1&segment=Entreprises"),
    apiFetch("/api/cb_bd?annee=2025&semestre=S1&segment=Entreprises"),
    apiFetch("/api/cb_bd?annee=2026&semestre=S1&segment=Entreprises"),
    apiFetch("/api/cb_banks"),
    apiFetch("/api/bank_logos"),
  ]);

  // Banques DYNAMIQUES (source unique) + synchro de l'ordre d'affichage CB (fonction dans app.main.js).
  if(Array.isArray(cbBanks) && cbBanks.length) CB_BANKS = cbBanks;
  // Logos DYNAMIQUES : logo réel si le fichier existe, sinon badge initiales (nouvelle banque).
  _mergeBankLogos(logos, CB_BANKS);
  if(typeof _syncBankOrder === "function") _syncBankOrder();

  if(frais)  FRAIS     = frais;
  if(rn)     RN2025    = rn.data;
  if(series) RN_SERIES = series;
  if(kpis){
    KPI_DATA  = kpis;
    FRAIS     = kpis.frais_min  || FRAIS;
    FRAIS_MOY = kpis.frais_data || {};
    RN2025    = kpis.rn_data    || RN2025;
    PNB_DATA         = kpis.pnb_data        || {};
    ROE_DATA         = kpis.roe_data        || {};
    MARGE_NETTE_DATA = kpis.marge_nette_data || {};
    COEFF_EXPL_DATA  = kpis.coeff_expl_data  || {};
    COUT_R_PNB_DATA  = kpis.cout_r_pnb_data  || {};
    ROA_DATA         = kpis.roa_data         || {};
    CREDITS_DATA     = kpis.credits_data     || {};
    DEPOTS_DATA      = kpis.depots_data      || {};
    INTERETS_DATA    = kpis.interets_data    || {};
    COMMISSIONS_DATA = kpis.commissions_data || {};
    AUTRES_PROD_DATA = kpis.autres_prod_data || {};
    RBE_DATA         = kpis.rbe_data         || {};
    RE_DATA          = kpis.re_data          || {};
  }
  if(annees && Array.isArray(annees) && annees.length) CB_ANNEES = annees;
  if(periodes && typeof periodes === 'object' && Object.keys(periodes).length) CB_PERIODES = periodes;
  if(resil) RESILIENCE_DATA = resil;
  if(efSeries){ PNB_SERIES = efSeries.pnb || {}; ROE_SERIES = efSeries.roe || {}; COEFF_SERIES = efSeries.coeff || {}; CNR_SERIES = efSeries.cnr || {}; }

  // Données CB réelles depuis PostgreSQL
  if(cbPar24) CB_PAR["2024"] = cbPar24;
  if(cbPar25) CB_PAR["2025"] = cbPar25;
  if(cbPar26) CB_PAR["2026"] = cbPar26;
  if(cbEnt24) CB_ENT["2024"] = cbEnt24;
  if(cbEnt25) CB_ENT["2025"] = cbEnt25;
  if(cbEnt26) CB_ENT["2026"] = cbEnt26;

  buildTicker();
}

async function reloadCB(){
  const sem = (typeof CB_SEM !== "undefined") ? CB_SEM : "S1";
  const [p24,p25,p26,e24,e25,e26] = await Promise.all([
    apiFetch(`/api/cb_bd?annee=2024&semestre=${sem}&segment=Particuliers`),
    apiFetch(`/api/cb_bd?annee=2025&semestre=${sem}&segment=Particuliers`),
    apiFetch(`/api/cb_bd?annee=2026&semestre=${sem}&segment=Particuliers`),
    apiFetch(`/api/cb_bd?annee=2024&semestre=${sem}&segment=Entreprises`),
    apiFetch(`/api/cb_bd?annee=2025&semestre=${sem}&segment=Entreprises`),
    apiFetch(`/api/cb_bd?annee=2026&semestre=${sem}&segment=Entreprises`),
  ]);
  if(p24) CB_PAR["2024"]=p24; if(p25) CB_PAR["2025"]=p25; if(p26) CB_PAR["2026"]=p26;
  if(e24) CB_ENT["2024"]=e24; if(e25) CB_ENT["2025"]=e25; if(e26) CB_ENT["2026"]=e26;
  if(typeof go === "function") go("cb");
}

// Reconstruit TICKER depuis RN2025 courant (appelé après chaque rechargement ANx)
function buildTicker(){
  TICKER = Object.entries(RN2025)
    .sort((a,b) => b[1]-a[1])
    .map(([s,v]) => {
      let d = "▲", up = 1;
      const ser = RN_SERIES[s];
      if(ser && ser.values && ser.values.length >= 2){
        const vals = ser.values;
        const prev = vals[vals.length-2];
        const curr = vals[vals.length-1];
        const pct  = prev > 0 ? (curr-prev)/prev*100 : 0;
        d  = (pct>=0?"+":"") + pct.toFixed(1).replace(".",",") + "%";
        up = pct >= 0 ? 1 : 0;
      }
      return { s, v:`${(v/1000).toFixed(1)} Mds`, d, up };
    });
  // Met à jour le DOM du ticker si déjà rendu
  refreshTickerDOM();
}

// Met à jour le DOM du ticker sans appeler initChrome()
function refreshTickerDOM(){
  const tk = document.getElementById("tk");
  if(!tk) return;
  const html = TICKER.map(t => {
    const b = BANKS.find(x => x.s === t.s);
    return `<span class="tk-item">
      <span class="lg"><img src="${b ? b.lg : ''}"></span>
      <b>${t.s}</b> ${t.v}
      <span class="${t.up?'up':'dn'}">${t.up?'▲':'▼'} ${t.d}</span>
    </span>`;
  }).join("");
  tk.innerHTML = html + html;
}

async function reloadKpis(){
  const f = APERCU_FILTERS;
  const kpis = await apiFetch(
    `/api/kpis?frais_annee=${f.frais_annee}&frais_sem=${f.frais_sem}&frais_seg=${f.frais_seg}&rn_anx=${f.rn_anx}`
  );
  if(kpis){
    KPI_DATA  = kpis;
    FRAIS     = kpis.frais_min  || FRAIS;
    FRAIS_MOY = kpis.frais_data || {};
    RN2025    = kpis.rn_data    || RN2025;
    PNB_DATA         = kpis.pnb_data        || {};
    ROE_DATA         = kpis.roe_data        || {};
    MARGE_NETTE_DATA = kpis.marge_nette_data || {};
    COEFF_EXPL_DATA  = kpis.coeff_expl_data  || {};
    COUT_R_PNB_DATA  = kpis.cout_r_pnb_data  || {};
    ROA_DATA         = kpis.roa_data         || {};
    CREDITS_DATA     = kpis.credits_data     || {};
    DEPOTS_DATA      = kpis.depots_data      || {};
    INTERETS_DATA    = kpis.interets_data    || {};
    COMMISSIONS_DATA = kpis.commissions_data || {};
    AUTRES_PROD_DATA = kpis.autres_prod_data || {};
    RBE_DATA         = kpis.rbe_data         || {};
    RE_DATA          = kpis.re_data          || {};
    buildTicker();
  }
}

// Clé de la période actuellement chargée dans CB_DATA. Sans elle, l'appelant se contentait de
// `if(!CB_DATA)` : la table était chargée une seule fois, puis figée sur la période initiale même
// après un changement de filtre. On mémorise donc CE QUI est chargé, pas seulement QUE ça l'est.
let CB_DATA_CLE = "";

async function loadCB(annee, semestre, segment){
  // Par défaut, la période choisie par l'utilisateur — et non 2026/S1/Particuliers en dur.
  const f = APERCU_FILTERS;
  annee    = annee    ?? f.frais_annee;
  semestre = semestre ?? f.frais_sem;
  segment  = segment  ?? f.frais_seg;
  CB_DATA = await apiFetch(`/api/cb?annee=${annee}&semestre=${semestre}&segment=${segment}`);
  CB_DATA_CLE = `${annee}|${semestre}|${segment}`;
  return CB_DATA;
}

/* ── Garde de navigation sur les tracés ────────────────────────────────
   Une vingtaine de fonctions dessinent un graphique par `Plotly.newPlot(id, …)`, après un appel
   réseau de plusieurs secondes. Si l'utilisateur change d'onglet entre-temps, go() a remplacé le
   contenu de #view : l'élément visé n'existe plus et Plotly lève « No DOM element with id 'x'
   exists on the page ». L'exception remontait jusqu'à l'appelant et interrompait le rendu de la
   page suivante — un simple changement d'onglet un peu rapide suffisait à laisser un écran
   incomplet.

   Plutôt que de répéter la même vérification dans chaque fonction (et de l'oublier dans la
   prochaine), on la pose UNE fois, ici. Dessiner dans un conteneur disparu n'a aucun sens : la
   demande est simplement abandonnée. Quand l'élément est là, le comportement est inchangé.

   Même raisonnement pour purge/relayout/react, appelés par les redessins au changement de thème
   ou de taille de fenêtre, qui visent eux aussi des conteneurs pouvant avoir disparu. */
if (window.Plotly) {
  ["newPlot", "purge", "relayout", "react"].forEach(nom => {
    if (typeof Plotly[nom] !== "function") return;
    const _origine = Plotly[nom].bind(Plotly);
    Plotly[nom] = function(cible, ...reste){
      if (typeof cible === "string" && !document.getElementById(cible)) {
        return Promise.resolve(null);  // page quittée pendant le chargement : ce n'est pas une panne
      }
      return _origine(cible, ...reste);
    };
  });
}

/* ── Theme helpers ─────────────────────────────────────────────────── */
function pk(name){ return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
// Zoom/pan interactif de Plotly (pincer sur tactile, cliquer-glisser à la souris) bloqué
// PARTOUT (mobile ET desktop) via fixedrange/scrollZoom ci-dessous — plus gênant qu'utile
// sur ce dashboard de lecture. Nom conservé (_IS_TOUCH) pour ne pas toucher tous les points
// d'usage, mais s'applique désormais à tous les appareils.
const _IS_TOUCH = true;
// Détection RÉELLE du tactile (contrairement à _IS_TOUCH ci-dessus) — utilisée UNIQUEMENT
// pour staticPlot (survol + clic légende). staticPlot:true désactive TOUT (zoom, survol,
// légende), pas seulement le zoom — le forcer partout cassait le clic légende même sur
// desktop (signalé le 2026-07-13). Restauré ici pour desktop, en gardant la protection
// d'origine sur mobile (staticPlot évitait un graphique vide/cassé au pincer-zoomer tactile).
const _REAL_TOUCH = ("ontouchstart" in window) || (navigator.maxTouchPoints > 0);
function baseLayout(extra={}){
  const grid = pk("--plot-grid") || "#26262b";
  const font = pk("--plot-font") || "#9A9AA2";
  return Object.assign({
    paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
    font:{ family:"Inter, sans-serif", size:11.5, color:font },
    margin:{ l:46, r:16, t:10, b:30 },
    xaxis:{ gridcolor:grid, zeroline:false, linecolor:grid, tickfont:{ family:"JetBrains Mono" }, fixedrange:_IS_TOUCH },
    yaxis:{ gridcolor:grid, zeroline:false, linecolor:grid, tickfont:{ family:"JetBrains Mono" }, fixedrange:_IS_TOUCH },
    hoverlabel:{
      bgcolor: pk("--bg-raise") || "#1F1F22",
      bordercolor: pk("--line-2") || "rgba(255,255,255,.14)",
      font:{ family:"JetBrains Mono", color:pk("--ink")||"#F6F6F7" },
    },
    showlegend:false, transition:{ duration:400, easing:"cubic-in-out" },
  }, extra);
}
const CFG = { displayModeBar:false, responsive:true, scrollZoom:!_IS_TOUCH, staticPlot:_REAL_TOUCH };

function redGreenScale(values){
  // bas = vert (bon/pas cher), haut = rouge (mauvais/cher)
  const lo=Math.min(...values), hi=Math.max(...values);
  return values.map(v=>{
    const t=(v-lo)/(hi-lo||1);
    let r,g,b;
    if(t<.5){ const k=t/.5; r=34+(245-34)*k; g=197+(176-197)*k; b=94+(32-94)*k; }
    else     { const k=(t-.5)/.5; r=245+(229-245)*k; g=176+(20-176)*k; b=32+(43-32)*k; }
    return `rgb(${r|0},${g|0},${b|0})`;
  });
}

/* ── Chart builders ──────────────────────────────────────────────────── */

// mode="min" → frais minimum (Analyse/Stratégie) · mode="avg" → moyenne (Vue d'ensemble)
function chartFraisRanked(id, height=240, mode="min"){
  const src    = (mode==="avg" && Object.keys(FRAIS_MOY).length) ? FRAIS_MOY : FRAIS;
  const pfx    = mode==="avg" ? "Moy. " : "À partir de ";
  const e      = Object.entries(src).sort((a,b)=>a[1]-b[1]);
  const labels = e.map(x=>x[0]), vals = e.map(x=>x[1]);
  const base   = redGreenScale(vals);
  const colors = labels.map((b,i) => b==="SGCI" ? "#E5142B" : base[i]);
  const texts  = vals.map((v,i) => {
    const tag = labels[i]==="SGCI" ? "★ SGCI · " : "";
    return tag + pfx + Math.round(v).toLocaleString("fr-FR") + " F";
  });
  const maxVal = Math.max(...vals);
  Plotly.newPlot(id, [{
    type:"bar", orientation:"h", x:vals, y:labels,
    marker:{ color:colors, line:{width:0} },
    text: texts, textposition:"outside",
    cliponaxis: false,
    textfont:{ family:"JetBrains Mono", size:11.5, color:pk("--ink")||"#F6F6F7" },
    hovertemplate:`%{y} · ${pfx.toLowerCase()}%{x:,} FCFA/mois<extra></extra>`,
  }], baseLayout({
    height, margin:{l:74, r:220, t:8, b:26},
    xaxis:{ showticklabels:false, gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, range:[0, maxVal*1.45] },
  }), CFG);
}

// RN comparatif — labels ANx (pas années réelles) — SGCI rouge, concurrents gris
function chartRNVsMarche(id, height){
  const el = document.getElementById(id);
  if(!el) return;
  const anx    = `Année ${APERCU_FILTERS.rn_anx}`;
  const sorted = Object.entries(RN2025).sort((a,b)=>b[1]-a[1]);
  const h = height || Math.max(el.clientHeight, 200);
  const labels = sorted.map(x=>x[0]);
  const vals   = sorted.map(x=>x[1]);
  const colors = labels.map(b => b==="SGCI" ? "#E5142B" : "rgba(120,120,140,0.45)");
  const texts  = sorted.map(([b,v]) => {
    const tag = b==="SGCI" ? "★ " : "";
    return `${tag}${b} · ${(v/1000).toFixed(1)} Mds`;
  });
  const maxVal = Math.max(...vals);
  Plotly.newPlot(id, [{
    type:"bar", orientation:"h",
    x: vals.slice().reverse(),
    y: labels.slice().reverse(),
    marker:{ color:colors.slice().reverse(), line:{width:0} },
    text:  texts.slice().reverse(),
    textposition:"outside",
    cliponaxis: false,
    textfont:{ family:"JetBrains Mono", size:11, color:pk("--ink")||"#F6F6F7" },
    hovertemplate:"%{y} : %{x:,} M FCFA<extra></extra>",
  }], baseLayout({
    height:h, margin:{l:74, r:220, t:8, b:26},
    xaxis:{ showticklabels:false, gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, range:[0, maxVal*1.45] },
  }), CFG);
}

// ── Calcul scores radar pour n'importe quelle banque ──────────────────────────
function computeRadarScores(k, bank) {
  if (!k) return null;
  const rn_data   = k.rn_data || {};
  const sorted_rn = Object.entries(rn_data).sort((a, b) => b[1] - a[1]);
  const n         = Math.max(sorted_rn.length, 1);

  // 1. Résultat net — rang parmi N banques
  const rank_rn = (sorted_rn.findIndex(([b]) => b === bank) + 1) || Math.ceil(n / 2);
  const s_rn    = Math.round((n - rank_rn + 1) / n * 100);

  // 2. Part de marché parmi les N banques suivies
  //    50 = part égale (1/N), 100 = double de la part égale
  const total_rn = Object.values(rn_data).reduce((a, v) => a + v, 0);
  const bank_rn  = rn_data[bank] || 0;
  const share    = total_rn > 0 ? bank_rn / total_rn * 100 : 0;
  const s_pdm    = Math.min(100, Math.round(share * n / 2));

  // 3. Position vs concurrent direct
  //    Si #1 : avance sur #2 (positif) — Sinon : retard sur #1 (négatif)
  const bank_idx = sorted_rn.findIndex(([b]) => b === bank);
  let ecart_direct = 0, direct_nom = "";
  if (bank_idx === 0 && sorted_rn.length > 1) {
    const v2 = sorted_rn[1][1];
    ecart_direct = v2 > 0 ? (bank_rn - v2) / v2 * 100 : 0;
    direct_nom   = sorted_rn[1][0];
  } else if (bank_idx > 0) {
    const v1 = sorted_rn[0][1];
    ecart_direct = v1 > 0 ? (bank_rn - v1) / v1 * 100 : 0;
    direct_nom   = sorted_rn[0][0];
  }
  const s_av = Math.min(100, Math.max(0, Math.round(50 + ecart_direct / 2)));

  // 4. Dynamique — rang croissance Année 1→3 parmi toutes les banques
  const gdata     = k.growths_data || {};
  const sorted_gr = Object.entries(gdata).sort((a, b) => b[1] - a[1]);
  const rank_gr   = (sorted_gr.findIndex(([b]) => b === bank) + 1) || Math.ceil(n / 2);
  const n_gr      = Math.max(sorted_gr.length, 1);
  const s_dyn     = Math.round((n_gr - rank_gr + 1) / n_gr * 100);

  // 5. Compétitivité CB — composite rang frais moyen + rang virement UEMOA
  const frais_data = k.frais_data || {};
  const sorted_fr  = Object.entries(frais_data).sort((a, b) => a[1] - b[1]); // moins cher = meilleur
  const rank_fr    = (sorted_fr.findIndex(([b]) => b === bank) + 1) || Math.ceil(n / 2);
  const n_fr       = Math.max(sorted_fr.length, 1);
  const s_fr       = Math.round((n_fr - rank_fr + 1) / n_fr * 100);

  const vir_data  = k.virement_data || {};
  const sorted_vir = Object.entries(vir_data).filter(([, v]) => v > 0).sort((a, b) => a[1] - b[1]);
  const rank_vir  = sorted_vir.findIndex(([b]) => b === bank) + 1;
  const n_vir     = sorted_vir.length;
  const s_vir     = (n_vir >= 2 && rank_vir > 0) ? Math.round((n_vir - rank_vir + 1) / n_vir * 100) : null;
  const s_cb      = s_vir !== null ? Math.round((s_fr + s_vir) / 2) : s_fr;

  const scoreGlobal = Math.round((s_rn + s_pdm + s_av + s_dyn + s_cb) / 5);

  return {
    s_rn, s_pdm, s_av, s_dyn, s_cb, scoreGlobal,
    rank_rn, share, ecart_direct, direct_nom, rank_gr, rank_fr,
    bank_idx, n, n_vir, rank_vir, n_gr,
    bank_rn, total_rn,
    bank_growth:  gdata[bank] || 0,
    fastest_b:    sorted_gr[0]  ? sorted_gr[0][0]  : "?",
    fastest_pct:  sorted_gr[0]  ? sorted_gr[0][1]  : 0,
  };
}

// ── Portrait compétitif radar — piloté par agent IA ──────────────────────────
let __radarAgentCache = {}; // cache {cacheKey: agentData}

function _radarCacheKey() {
  const f = APERCU_FILTERS;
  return `${RADAR_BANK||"SGCI"}|${f.frais_annee}|${f.frais_sem}|${f.frais_seg}|${f.rn_anx}`;
}

function _drawRadarFromData(id, bank, dims) {
  const labels    = dims.map(d => d.label);
  const scores    = dims.map(d => d.score);
  const market    = scores.map(() => 50);
  const isHero    = bank === "SGCI";
  const col       = isHero ? "#FF3B4E" : "#38D1F0";
  const fill      = isHero ? "rgba(229,20,43,.26)" : "rgba(56,209,240,.18)";
  // Numéros sur chaque sommet — "" pour le point de fermeture (doublon du 1er)
  const scoreText = [...scores.map(s => String(s)), ""];

  Plotly.newPlot(id, [
    { type:"scatterpolar", r:[...market,market[0]], theta:[...labels,labels[0]], fill:"toself",
      name:"Moy. marché", fillcolor:"rgba(150,150,160,.12)",
      line:{color:pk("--muted")||"#9A9AA2", width:1.4},
      mode:"lines+markers", marker:{size:4, color:pk("--muted")||"#9A9AA2"} },
    { type:"scatterpolar", r:[...scores,scores[0]], theta:[...labels,labels[0]], fill:"toself",
      name:bank, fillcolor:fill,
      line:{color:col, width:2.4},
      mode:"lines+markers+text",
      text:scoreText, textposition:"top center",
      textfont:{size:9.5, color:col, family:"JetBrains Mono"},
      marker:{size:5, color:col} },
  ], baseLayout({
    height:230, margin:{l:66,r:66,t:20,b:44}, showlegend:true,
    legend:{ orientation:"h", y:-0.22, font:{size:11} },
    polar:{
      bgcolor:"rgba(0,0,0,0)",
      radialaxis:{ visible:true, range:[0,110],
        gridcolor:pk("--plot-grid")||"#26262b",
        tickvals:[25,50,75,100],
        tickfont:{size:7,color:pk("--faint")||"#5E5E66"}, fixedrange:_IS_TOUCH },
      angularaxis:{ gridcolor:pk("--plot-grid")||"#26262b",
        tickfont:{size:9,color:pk("--muted")||"#9A9AA2"}, fixedrange:_IS_TOUCH },
    },
  }), CFG);
}

async function chartRadar(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const bank = RADAR_BANK || "SGCI";
  const f    = APERCU_FILTERS;

  // Vérifier le cache
  const ckey = _radarCacheKey();
  if (__radarAgentCache[ckey]) {
    const cached = __radarAgentCache[ckey];
    _drawRadarFromData(id, bank, cached.dimensions);
    if (typeof updateRadarInsight === "function") updateRadarInsight(cached);
    return;
  }

  // Loading state
  el.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:230px;gap:10px;color:var(--muted);font:500 12px var(--sans)">
    <div style="width:32px;height:32px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin 0.9s linear infinite"></div>
    <span>Agent IA en cours d'analyse…</span>
  </div>`;
  const ins = document.getElementById("radar-insight");
  if (ins) ins.innerHTML = "";

  try {
    const url = `/api/radar_agent?bank=${encodeURIComponent(bank)}&annee=${f.frais_annee}&sem=${f.frais_sem}&seg=${encodeURIComponent(f.frais_seg)}&anx=${f.rn_anx}`;
    const res  = await fetch(url);
    const json = await res.json();

    if (!json.ok || !json.data || !json.data.dimensions) {
      throw new Error(json.error || "Réponse invalide");
    }

    const agd = json.data;
    __radarAgentCache[ckey] = agd; // mettre en cache

    // COURSE DE NAVIGATION (2026-07-30). L'élément est vérifié à l'entrée, mais l'appel réseau
    // qui précède dure plusieurs secondes : l'utilisateur a le temps de changer d'onglet, et
    // `go()` remplace alors tout le contenu de #view. Plexiste alors plus, Plotly lève
    // « No DOM element with id 'ap-radar' exists on the page », et le bloc catch écrivait un
    // message d'erreur trompeur — « Analyse IA indisponible » — pour une page déjà quittée.
    // On revérifie donc la présence de l'élément APRÈS l'attente.
    if (!document.getElementById(id)) return;

    el.innerHTML = ""; // effacer le spinner
    _drawRadarFromData(id, bank, agd.dimensions);
    if (typeof updateRadarInsight === "function") updateRadarInsight(agd);

  } catch(e) {
    // Page quittée pendant le chargement : ce n'est pas une panne, on sort en silence.
    if (!document.getElementById(id)) return;
    console.error("[chartRadar agent]", e);
    el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:230px;color:var(--muted);font:500 12px var(--sans);text-align:center;padding:20px">
      ⚠ Analyse IA indisponible<br><span style="font-size:10px;color:var(--faint)">${e.message||"vérifiez les clés API"}</span>
    </div>`;
  }
}

function selectRadarBank(b) {
  RADAR_BANK = b;
  Plotly.purge("ap-radar");
  chartRadar("ap-radar"); // async — met à jour le radar + insight automatiquement
  document.querySelectorAll("[id^='rbb-']").forEach(el =>
    el.classList.toggle("on", el.id === `rbb-${b}`)
  );
}

function chartRNLine(id, h){
  // Palette distincte par banque
  const PALETTE = {
    SGCI:    { color:"#E5142B",              width:3.5, dash:"solid",   size:8 },
    ECOBANK: { color:"rgba(56,209,240,.9)",  width:2.5, dash:"solid",   size:6 },
    BNI:     { color:"rgba(34,197,94,.9)",   width:2,   dash:"solid",   size:6 },
    BACI:    { color:"rgba(251,146,60,.9)",  width:2,   dash:"dash",    size:6 },
    NSIA:    { color:"rgba(168,85,247,.9)",  width:2,   dash:"dot",     size:6 },
    BICICI:  { color:"rgba(251,113,133,.9)", width:2,   dash:"dashdot", size:6 },
    SIB:     { color:"rgba(148,163,184,.9)", width:2,   dash:"dash",    size:7 },
  };
  const p = s => PALETTE[s] || { color:"rgba(150,150,170,.8)", width:1.5, dash:"solid", size:5 };
  // Axe = vraies années calendaires : chaque banque affichée sur ses années réelles
  const toAN = years => years.map(y => String(y));

  const traces = [];

  // Axe des années DYNAMIQUE (dérivé des données → une nouvelle année apparaît toute seule).
  const _rnYears = [...new Set(Object.values(RN_SERIES||{}).flatMap(v => (v.years||[]).map(String)))].sort();

  // Halo SGCI
  const sgciS = RN_SERIES.SGCI;
  if(sgciS && sgciS.years.length >= 2){
    traces.push({
      x: toAN(sgciS.years), y: sgciS.values.map(x=>+(x/1000).toFixed(1)),
      mode:"lines", line:{color:"#E5142B",width:10,shape:"spline"},
      opacity:.12, hoverinfo:"skip", showlegend:false,
    });
  }

  Object.entries(RN_SERIES).forEach(([k, v]) => {
    const years = v.years || [];
    const xs    = toAN(years);
    const ys    = (v.values||[]).map(x => +(x/1000).toFixed(1));
    const labels = years.map((y,i) => y + " : " + (ys[i]||0).toFixed(1) + " Mds");
    const pp = p(k);
    // SIB ou banque avec 1 seul point → mode markers uniquement
    const mode = xs.length < 2 ? "markers" : "lines+markers";
    traces.push({
      x: xs, y: ys, customdata: labels,
      mode, name: k,
      line:{ color:pp.color, width:pp.width, shape:"spline", dash:pp.dash },
      marker:{ size:pp.size, color:pp.color,
               symbol: xs.length < 2 ? "diamond" : "circle",
               line:{ width:1.5, color:"rgba(255,255,255,.5)" } },
      hovertemplate:`<b>${k}</b> %{customdata}<extra></extra>`,
    });
  });

  Plotly.newPlot(id, traces, baseLayout({
    height:h||310, margin:{l:42,r:16,t:8,b:52},
    xaxis:{ type:"category", categoryorder:"array",
            categoryarray:(_rnYears.length?_rnYears:["2021","2022","2023","2024","2025"]),
            gridcolor:pk("--plot-grid")||"#26262b",
            tickfont:{family:"JetBrains Mono",size:11} },
    yaxis:{ gridcolor:pk("--plot-grid")||"#26262b", zeroline:false,
            ticksuffix:" ", tickfont:{family:"JetBrains Mono"}, rangemode:"tozero" },
    showlegend:true,
    legend:{ orientation:"h", y:-0.18, x:0.5, xanchor:"center",
             font:{size:10.5, family:"JetBrains Mono"},
             bgcolor:"rgba(0,0,0,0)", itemsizing:"constant" },
  }), CFG);
}

/* Generic multi-bank line chart. series = {bank: {year: value}} */
function chartSeriesLine(id, series, h, unit, suffix){
  const PALETTE = {
    SGCI:    { color:"#E5142B",              width:3.5, dash:"solid",   size:8 },
    ECOBANK: { color:"rgba(56,209,240,.9)",  width:2.5, dash:"solid",   size:6 },
    BNI:     { color:"rgba(34,197,94,.9)",   width:2,   dash:"solid",   size:6 },
    BACI:    { color:"rgba(251,146,60,.9)",  width:2,   dash:"dash",    size:6 },
    NSIA:    { color:"rgba(168,85,247,.9)",  width:2,   dash:"dot",     size:6 },
    BICICI:  { color:"rgba(251,113,133,.9)", width:2,   dash:"dashdot", size:6 },
    SIB:     { color:"rgba(148,163,184,.9)", width:2,   dash:"dash",    size:7 },
  };
  const p = s => PALETTE[s] || { color:"rgba(150,150,170,.8)", width:1.5, dash:"solid", size:5 };
  const suf = suffix || "";
  const allYears = [...new Set(Object.values(series).flatMap(yv => Object.keys(yv).map(Number)))].sort();
  const cats     = allYears.map(String);
  const traces   = [];

  // Halo SGCI
  if(series.SGCI){
    const ys = allYears.map(y => series.SGCI[y] ?? null);
    traces.push({
      x: cats, y: ys,
      mode:"lines", line:{color:"#E5142B",width:10,shape:"spline"},
      opacity:.12, hoverinfo:"skip", showlegend:false,
    });
  }

  Object.entries(series).forEach(([k, yv]) => {
    const xs = cats;
    const ys = allYears.map(y => yv[y] != null ? +yv[y].toFixed(2) : null);
    const pp = p(k);
    const mode = xs.filter((_,i)=>ys[i]!=null).length < 2 ? "markers" : "lines+markers";
    traces.push({
      x: xs, y: ys, connectgaps: false,
      mode, name: k,
      line:{ color:pp.color, width:pp.width, shape:"spline", dash:pp.dash },
      marker:{ size:pp.size, color:pp.color, symbol:"circle",
               line:{ width:1.5, color:"rgba(255,255,255,.5)" } },
      hovertemplate:`<b>${k}</b> %{x} : %{y}${suf}<extra></extra>`,
    });
  });

  Plotly.newPlot(id, traces, baseLayout({
    height:h||310, margin:{l:48,r:16,t:8,b:52},
    xaxis:{ type:"category", categoryorder:"array", categoryarray:cats,
            gridcolor:pk("--plot-grid")||"#26262b",
            tickfont:{family:"JetBrains Mono",size:11} },
    yaxis:{ gridcolor:pk("--plot-grid")||"#26262b", zeroline:false,
            ticksuffix:suf+" ", tickfont:{family:"JetBrains Mono"}, rangemode:"tozero" },
    showlegend:true,
    legend:{ orientation:"h", y:-0.18, x:0.5, xanchor:"center",
             font:{size:10.5, family:"JetBrains Mono"},
             bgcolor:"rgba(0,0,0,0)", itemsizing:"constant" },
  }), CFG);
}

function chartTreemap(id){
  const labels = Object.keys(RN2025), vals = Object.values(RN2025);
  Plotly.newPlot(id, [{
    type:"treemap", labels, parents:labels.map(()=>""), values:vals,
    marker:{
      colors: labels.map((l,i) => l==="SGCI" ? "#E5142B" : redGreenScale(vals)[i]),
      line:{ color:pk("--bg-deep")||"#08080A", width:2 },
    },
    textfont:{ family:"Inter", size:12, color:"#fff" },
    texttemplate:"<b>%{label}</b><br>%{value:,} M",
    hovertemplate:"<b>%{label}</b><br>%{value:,} M FCFA<extra></extra>",
    textposition:"middle center",
  }], baseLayout({ height:260, margin:{l:4,r:4,t:4,b:20} }), CFG);
}

function chartGrowth(id, h){
  // Utilise growths_data du backend — même source que l'analyse texte
  const gdata = (KPI_DATA && KPI_DATA.growths_data) || {};
  const g = Object.entries(gdata)
    .map(([k,v]) => ({ k, y: Math.round(v * 10) / 10 }))
    .sort((a,b) => b.y-a.y);

  const maxY  = Math.max(...g.map(d=>d.y));
  const minY  = Math.min(...g.map(d=>d.y), 0);
  const yRange = [minY - 8, maxY * 1.25]; // espace pour labels "outside"

  const sorted  = [...g.map(d=>d.y)].sort((a,b)=>a-b);
  const mediane = sorted.length ? sorted[Math.floor(sorted.length/2)] : 0;

  const colBar = d => d.k==="SGCI" ? "#E5142B" : d.y >= 0 ? "rgba(34,197,94,.85)" : "rgba(255,77,77,.85)";

  const shapes = [{
    type:"line", xref:"paper", yref:"y",
    x0:0, x1:1, y0:mediane, y1:mediane,
    line:{ color:"rgba(56,209,240,.75)", width:2, dash:"dash" },
  }];

  const annotations = [{
    xref:"paper", yref:"y", x:1.01, y:mediane,
    xanchor:"left", yanchor:"middle",
    text:"<b>médiane<br>" + (mediane>=0?"+":"") + mediane.toFixed(1) + "%</b>",
    showarrow:false,
    font:{ family:"JetBrains Mono", size:9.5, color:"rgba(56,209,240,.95)" },
  }];

  Plotly.newPlot(id, [{
    type:"bar", x:g.map(d=>d.k), y:g.map(d=>d.y),
    marker:{ color:g.map(colBar), line:{width:0} },
    text: g.map(d => (d.y>=0?"+":"") + d.y.toFixed(1) + "%"), textposition:"outside",
    textfont:{ family:"JetBrains Mono", color:pk("--ink")||"#F6F6F7", size:10.5 },
    hovertemplate:"<b>%{x}</b> : %{y:.1f}%<extra></extra>",
    cliponaxis:false,
  }], baseLayout({
    height:h||310, margin:{l:36,r:72,t:8,b:28},
    yaxis:{ ticksuffix:"%", range:yRange,
            gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:true, zerolinecolor:pk("--line-2")||"rgba(255,255,255,.14)" },
    shapes, annotations,
  }), CFG);
}

// Virement UEMOA — service standardisé BCEAO, directement comparable entre banques
function chartVirementUemoa(id, height=240){
  const src = (KPI_DATA && KPI_DATA.virement_data) ? KPI_DATA.virement_data : {};
  if(!Object.keys(src).length){
    const el = document.getElementById(id);
    if(el) el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:${height}px;color:var(--muted);font:500 13px var(--sans)">Données virement UEMOA non disponibles pour cette période</div>`;
    return;
  }
  const e      = Object.entries(src).sort((a,b) => a[1]-b[1]);
  const labels = e.map(x => x[0]);
  const vals   = e.map(x => x[1]);
  const base   = redGreenScale(vals);
  const colors = labels.map((b,i) => b==="SGCI" ? "#E5142B" : base[i]);
  const texts  = vals.map((v,i) => {
    const tag = labels[i]==="SGCI" ? "★ SGCI · " : "";
    return tag + Math.round(v).toLocaleString("fr-FR") + " F";
  });
  const maxVal = Math.max(...vals);
  Plotly.newPlot(id, [{
    type:"bar", orientation:"h", x:vals, y:labels,
    marker:{ color:colors, line:{width:0} },
    text: texts, textposition:"outside",
    cliponaxis: false,
    textfont:{ family:"JetBrains Mono", size:11.5, color:pk("--ink")||"#F6F6F7" },
    hovertemplate:"%{y} · %{x:,} FCFA par virement<extra></extra>",
  }], baseLayout({
    height, margin:{l:74, r:220, t:8, b:26},
    xaxis:{ showticklabels:false, gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, range:[0, maxVal*1.45] },
  }), CFG);
}

// PNB comparatif — Produit Net Bancaire par banque · SGCI rouge
function chartPNBvsMarche(id, height=264){
  const anx    = `Année ${APERCU_FILTERS.rn_anx}`;
  const src    = Object.keys(PNB_DATA).length ? PNB_DATA : {};
  if(!Object.keys(src).length){
    const el = document.getElementById(id);
    if(el) el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:${height}px;color:var(--muted);font:500 12px var(--sans)">Données PNB non disponibles pour cette période</div>`;
    return;
  }
  const sorted = Object.entries(src).sort((a,b)=>b[1]-a[1]);
  const labels = sorted.map(x=>x[0]);
  const vals   = sorted.map(x=>x[1]);
  const colors = labels.map(b => b==="SGCI" ? "#E5142B" : "rgba(120,120,140,0.45)");
  const texts  = sorted.map(([b,v]) => {
    const tag = b==="SGCI" ? "★ " : "";
    return `${tag}${b} · ${(v/1000).toFixed(1)} Mds`;
  });
  const maxVal = Math.max(...vals);
  Plotly.newPlot(id, [{
    type:"bar", orientation:"h",
    x: vals.slice().reverse(),
    y: labels.slice().reverse(),
    marker:{ color:colors.slice().reverse(), line:{width:0} },
    text: texts.slice().reverse(),
    textposition:"outside",
    cliponaxis: false,
    textfont:{ family:"JetBrains Mono", size:11, color:pk("--ink")||"#F6F6F7" },
    hovertemplate:"%{y} : %{x:,} M FCFA<extra></extra>",
  }], baseLayout({
    height, margin:{l:74, r:220, t:8, b:26},
    xaxis:{ showticklabels:false, gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, range:[0, maxVal*1.45] },
  }), CFG);
}

// Sélecteur banque pour le radar dans Analyse > Santé financière
function selectAnRadarBank(b){
  RADAR_BANK = b;
  Plotly.purge("an-radar");
  chartRadar("an-radar");
  document.querySelectorAll("[id^='anrbb-']").forEach(el =>
    el.classList.toggle("on", el.id === `anrbb-${b}`)
  );
  const lbl = document.getElementById("an-radar-bank-lbl");
  if(lbl) lbl.textContent = b;
}

// Bump chart — évolution des rangs AN1→AN3 par banque
function chartBumpRank(id, height=240){
  const validBanks = Object.keys(RN_SERIES).filter(b =>
    RN_SERIES[b] && RN_SERIES[b].values && RN_SERIES[b].values.length >= 1
  );
  const xLabels = ["Année 1","Année 2","Année 3"];

  // Pour chaque période, si la banque n'a pas encore cette année (ex: SIB AN3 absent),
  // on utilise sa dernière valeur connue — évite le fallback à 0 qui la classe artificiellement dernière
  const ranksByPeriod = [0,1,2].map(i => {
    const vals = validBanks.map(b => {
      const arr = RN_SERIES[b].values;
      const v   = i < arr.length ? arr[i] : arr[arr.length - 1];
      return { b, v: v || 0 };
    });
    vals.sort((a, b) => b.v - a.v);
    const r = {};
    vals.forEach(({ b }, rank) => { r[b] = rank + 1; });
    return r;
  });

  // Traces : lignes + marqueurs SANS texte (texte = annotations non clipées)
  const traces = validBanks.map(bank => {
    const isSGCI = bank === "SGCI";
    const ranks  = ranksByPeriod.map(r => r[bank] || validBanks.length);
    return {
      type:"scatter", mode:"lines+markers",
      x: xLabels, y: ranks,
      name: bank, showlegend: false,
      line:{ color: isSGCI ? "#E5142B" : "rgba(120,120,140,0.42)",
             width: isSGCI ? 2.8 : 1.3, shape:"spline" },
      marker:{ color: isSGCI ? "#E5142B" : "rgba(120,120,140,0.65)",
               size: isSGCI ? 9 : 5 },
      hovertemplate:`<b>${bank}</b><br>%{x} — Rang #%{y:d}<extra></extra>`,
    };
  });

  // Annotations — toujours à droite (Année 3) pour cohérence visuelle, non clipées
  const annotations = validBanks.map(bank => {
    const isSGCI = bank === "SGCI";
    const rank   = ranksByPeriod[2][bank] || validBanks.length;  // rang à AN3 (valeur réelle ou dernière connue)
    return {
      x: xLabels[2], y: rank,
      xref:"x", yref:"y",
      xanchor:"left", yanchor:"middle",
      text: "  " + bank + " <b>#" + rank + "</b>",
      showarrow: false,
      font:{ family:"JetBrains Mono", size: isSGCI ? 11 : 9.5,
             color: isSGCI ? "#E5142B" : (pk("--ink")||"#F6F6F7") },
    };
  });

  Plotly.newPlot(id, traces, baseLayout({
    height, margin:{ l:32, r:110, t:10, b:30 },
    annotations,
    xaxis:{ showgrid:false, zeroline:false,
            linecolor:pk("--line-2")||"rgba(255,255,255,.14)",
            tickfont:{ family:"JetBrains Mono", size:11 } },
    yaxis:{ autorange:"reversed",
            tickvals:validBanks.map((_,i)=>i+1),          // rangs DYNAMIQUES (s'adapte au nb de banques)
            ticktext:validBanks.map((_,i)=>"#"+(i+1)),
            gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, tickfont:{ family:"JetBrains Mono" } },
  }), CFG);
}

// Donut — répartition des bénéfices entre les 7 banques
function chartMarketShare(id, height=240){
  const sorted  = Object.entries(RN2025).sort((a,b) => b[1]-a[1]);
  const labels  = sorted.map(([b]) => b);
  const values  = sorted.map(([,v]) => v);
  const palette = ["#E5142B","#38D1F0","#22C55E","#FFB020","#9E77ED","#F97316","#64748B"];
  const colors  = labels.map((l,i) => l==="SGCI" ? "#E5142B" : palette[i % palette.length]);

  Plotly.newPlot(id, [{
    type:"pie", labels, values, hole:0.52, sort:false,
    marker:{ colors, line:{ color:pk("--bg-deep")||"#08080A", width:2 } },
    texttemplate:"%{label}<br><b>%{percent:.1%}</b>",
    textfont:{ family:"JetBrains Mono", size:10.5 },
    hovertemplate:"%{label} : %{value:,} M FCFA (%{percent:.1%})<extra></extra>",
  }], baseLayout({
    height, margin:{ l:10, r:10, t:10, b:10 }, showlegend:false,
  }), CFG);
}

// ── Graphique EF générique — SGCI rouge, meilleur vert, texte visible ──────
function chartEFBar(id, data, height, opts){
  const el = document.getElementById(id);
  if(!el) return;
  if(!data || !Object.keys(data).length){
    el.innerHTML = "<div style='display:flex;align-items:center;justify-content:center;height:200px;color:var(--muted);font:500 12px var(--sans)'>Données insuffisantes pour cette période</div>";
    return;
  }
  const lb  = !!(opts && opts.lower);    // true = plus bas = meilleur
  const dec = (opts && opts.dec != null) ? opts.dec : 1;
  const sfx = (opts && opts.unit) || "";
  const mdsFmt = !!(opts && opts.mds);  // afficher en Mds si vrai

  const entries = Object.entries(data).filter(([,v]) => v != null && isFinite(v));
  const sorted  = entries.sort((a,b) => lb ? a[1]-b[1] : b[1]-a[1]);
  const labels  = sorted.map(x=>x[0]);
  const vals    = sorted.map(x=>Math.abs(x[1]));
  const best    = lb ? Math.min(...vals) : Math.max(...vals);

  const colors = labels.map((b,i)=>{
    if(b==="SGCI") return "#E5142B";
    if(Math.abs(vals[i]-best)<0.01) return "#22C55E";
    return "rgba(120,120,140,0.45)";
  });
  const texts = sorted.map(([b],i)=>{
    const star = b==="SGCI" ? "★ " : "";
    const v    = mdsFmt ? (vals[i]/1000).toFixed(dec) : vals[i].toFixed(dec);
    const u    = mdsFmt ? " Mds" : sfx;
    return star + b + " · " + v + u;
  });
  const maxVal = Math.max(...vals);

  Plotly.newPlot(id, [{
    type:"bar", orientation:"h",
    x: vals.slice().reverse(),
    y: labels.slice().reverse(),
    marker:{ color:colors.slice().reverse(), line:{width:0} },
    text:  texts.slice().reverse(),
    textposition:"outside",
    cliponaxis: false,
    textfont:{ family:"JetBrains Mono", size:11, color:pk("--ink")||"#F6F6F7" },
    hovertemplate:"%{y}: %{x:,.1f}" + sfx + "<extra></extra>",
  }], baseLayout({
    height: height||300,
    bargap: 0.08,
    margin:{ l:74, r:220, t:8, b:26 },
    xaxis:{ showticklabels:false, gridcolor:pk("--plot-grid")||"#26262b",
            zeroline:false, range:[0, maxVal*1.45] },
  }), CFG);
}

// Wrappers spécifiques
function chartPNBbar(id, h)       { chartEFBar(id, PNB_DATA,         h, {dec:1, mds:true}); }
function chartMargeNette(id, h)   { chartEFBar(id, MARGE_NETTE_DATA, h, {dec:1, unit:"%"}); }
function chartCoeffExpl(id, h)    { chartEFBar(id, COEFF_EXPL_DATA,  h, {dec:1, unit:"%", lower:true}); }
function chartCoutRisque(id, h)   { chartEFBar(id, COUT_R_PNB_DATA,  h, {dec:1, unit:"%", lower:true}); }
function chartROEbar(id, h)       { chartEFBar(id, ROE_DATA,         h, {dec:1, unit:"%"}); }

// ── Section ⑤ — Résilience ──────────────────────────────────────────────

function _resilField(field){
  const out = {};
  Object.entries(RESILIENCE_DATA||{}).forEach(([b,d])=>{ if(d[field]!=null) out[b]=d[field]; });
  return out;
}

function chartSolvabilite(id, h){
  const data = _resilField("solvabilite");
  chartEFBar(id, data, h, {dec:1, unit:"%"});
  if(document.getElementById(id) && Object.keys(data).length){
    Plotly.relayout(id, {
      'margin.t': 30,
      shapes:[{ type:"line", xref:"x", yref:"paper", x0:8, x1:8, y0:0, y1:1,
        line:{ color:"rgba(56,209,240,.8)", width:1.5, dash:"dash" } }],
      annotations:[{ xref:"x", yref:"paper", x:8.3, y:1.0, yanchor:"bottom", xanchor:"left",
        text:"Norme BCEAO 8%", showarrow:false,
        font:{family:"JetBrains Mono",size:9.5,color:"rgba(56,209,240,.95)"} }]
    });
  }
}

function chartLevierCredit(id, h){
  // Plage de valeurs serrée → on démarre à 2 pour mieux voir les différences
  const data = _resilField("levier_credit");
  const el = document.getElementById(id);
  if(!el || !Object.keys(data).length) return;
  const vals  = Object.values(data);
  const minV  = Math.min(...vals);
  const maxV  = Math.max(...vals);
  const el2 = document.getElementById(id);
  chartEFBar(id, data, h, {dec:2, unit:"×", lower:true});
  // Réduire la plage pour mieux voir les différences
  if(el2) Plotly.relayout(id, { "xaxis.range":[Math.max(0, minV*0.7), maxV*1.4] });
}

function chartCouvertureDepots(id, h){ chartEFBar(id, _resilField("couverture_depots"), h, {dec:1, unit:"%"}); }

function chartCreditDepot(id, h){
  // Grouped bar: crédits + dépôts côte à côte par banque
  const el = document.getElementById(id);
  if(!el) return;
  const banks = [...new Set([...Object.keys(CREDITS_DATA), ...Object.keys(DEPOTS_DATA)])];
  if(!banks.length){
    el.innerHTML = "<div style='display:flex;align-items:center;justify-content:center;height:200px;color:var(--muted);font:500 12px var(--sans)'>Données insuffisantes</div>";
    return;
  }
  banks.sort((a,b)=>(CREDITS_DATA[b]||0)-(CREDITS_DATA[a]||0));
  const others = banks.filter(b => b !== "SGCI");

  // 4 traces : légende cyan/gris pour concurrents, SGCI rouge sans légende
  const oCredV = others.map(b => (CREDITS_DATA[b]||0)/1000);
  const oDepV  = others.map(b => (DEPOTS_DATA[b]||0)/1000);
  const sCredV = [(CREDITS_DATA["SGCI"]||0)/1000];
  const sDepV  = [(DEPOTS_DATA["SGCI"]||0)/1000];

  Plotly.newPlot(id, [
    { type:"bar", name:"Crédits",  x:oCredV, y:others, orientation:"h",
      marker:{ color:"rgba(56,209,240,.6)", line:{width:0} },
      hovertemplate:"<b>%{y}</b> · Crédits: %{x:.0f} Mds<extra></extra>" },
    { type:"bar", name:"Dépôts",   x:oDepV,  y:others, orientation:"h",
      marker:{ color:"rgba(120,120,140,.35)", line:{width:0} },
      hovertemplate:"<b>%{y}</b> · Dépôts: %{x:.0f} Mds<extra></extra>" },
    { type:"bar", name:"SGCI Crédits", showlegend:false,
      x:sCredV, y:["SGCI"], orientation:"h",
      marker:{ color:"#E5142B", line:{width:0} },
      hovertemplate:"<b>SGCI</b> · Crédits: %{x:.0f} Mds<extra></extra>" },
    { type:"bar", name:"SGCI Dépôts", showlegend:false,
      x:sDepV, y:["SGCI"], orientation:"h",
      marker:{ color:"rgba(229,20,43,.3)", line:{width:0} },
      hovertemplate:"<b>SGCI</b> · Dépôts: %{x:.0f} Mds<extra></extra>" },
  ], baseLayout({
    height:h||380, barmode:"group", bargap:0.05, bargroupgap:0.02,
    margin:{ l:74, r:20, t:8, b:30 },
    showlegend:true,
    legend:{ orientation:"h", y:-0.15, font:{size:11} },
    xaxis:{ ticksuffix:" Mds", gridcolor:pk("--plot-grid")||"#26262b", zeroline:false },
  }), CFG);
}

/* ── Mix commercial PNB — 100% stacked bar (intérêts / commissions / autres) ── */
function chartMixPNB(id, h){
  const el = document.getElementById(id);
  if(!el) return;
  const intD  = INTERETS_DATA    || {};
  const commD = COMMISSIONS_DATA || {};
  const autD  = AUTRES_PROD_DATA || {};
  const banks = Object.keys(intD).filter(b => intD[b]);
  if(!banks.length){
    el.innerHTML = "<div style='display:flex;align-items:center;justify-content:center;height:200px;color:var(--muted);font:500 12px var(--sans)'>Données insuffisantes</div>";
    return;
  }
  const tots   = banks.map(b => (intD[b]||0) + (commD[b]||0) + (autD[b]||0));
  const pInt   = banks.map((b,i) => tots[i] > 0 ? intD[b]/tots[i]*100   : 0);
  const pComm  = banks.map((b,i) => tots[i] > 0 ? (commD[b]||0)/tots[i]*100 : 0);
  const pAut   = banks.map((b,i) => tots[i] > 0 ? (autD[b]||0)/tots[i]*100  : 0);
  // Trier par % commissions croissant (plus diversifié en haut)
  const idx    = banks.map((_,i)=>i).sort((a,b) => pComm[a]-pComm[b]);
  const bks    = idx.map(i => banks[i]);
  const sInt   = idx.map(i => +pInt[i].toFixed(1));
  const sComm  = idx.map(i => +pComm[i].toFixed(1));
  const sAut   = idx.map(i => +pAut[i].toFixed(1));
  const sTot   = idx.map(i => tots[i]);
  const txComm = bks.map((b,i) => (b==="SGCI"?"★ ":"") + b + " · " + sComm[i].toFixed(1) + "%");

  const txInt  = bks.map((b,i) => sInt[i].toFixed(0)  + "%");
  const txAut  = bks.map((b,i) => sAut[i] >= 5 ? sAut[i].toFixed(0) + "%" : "");

  Plotly.newPlot(id, [
    { type:"bar", orientation:"h", name:"Intérêts",
      x:sInt, y:bks,
      marker:{ color:"rgba(56,209,240,.6)", line:{width:0} },
      text:txInt, textposition:"inside",
      textfont:{ family:"JetBrains Mono", size:10.5, color:"rgba(10,15,25,.85)" },
      hovertemplate:"%{y} · Intérêts: %{x:.1f}%<extra></extra>" },
    { type:"bar", orientation:"h", name:"Commissions",
      x:sComm, y:bks,
      marker:{ color:"rgba(229,20,43,.72)", line:{width:0} },
      text:txComm, textposition:"inside",
      textfont:{ family:"JetBrains Mono", size:10, color:"rgba(245,245,248,.92)" },
      hovertemplate:"%{y} · Commissions: %{x:.1f}%<extra></extra>" },
    { type:"bar", orientation:"h", name:"Autres prod.",
      x:sAut, y:bks,
      marker:{ color:"rgba(120,120,140,.5)", line:{width:0} },
      text:txAut, textposition:"inside",
      textfont:{ family:"JetBrains Mono", size:9.5, color:"rgba(240,240,245,.8)" },
      hovertemplate:"%{y} · Autres: %{x:.1f}%<extra></extra>" },
  ], baseLayout({
    height: h||340, barmode:"stack",
    margin:{ l:74, r:16, t:8, b:44 },
    showlegend:true,
    legend:{ orientation:"h", y:-0.16, font:{size:11}, itemsizing:"constant",
             bgcolor:"rgba(0,0,0,0)" },
    xaxis:{ ticksuffix:"%", range:[0,100],
            gridcolor:pk("--plot-grid")||"#26262b", zeroline:false },
  }), CFG);
}

/* ── Cascade P&L — PNB → RBE → RE → RN en overlay par banque ──────── */
function chartCascadePL(id, h){
  const el = document.getElementById(id);
  if(!el) return;
  const pnbD = PNB_DATA || {};
  const rbeD = RBE_DATA || {};
  const reD  = RE_DATA  || {};
  const rnD  = (KPI_DATA && KPI_DATA.rn_data) || {};
  const banks = Object.keys(pnbD).filter(b => pnbD[b] && rnD[b]);
  if(!banks.length){
    el.innerHTML = "<div style='display:flex;align-items:center;justify-content:center;height:200px;color:var(--muted);font:500 12px var(--sans)'>Données insuffisantes</div>";
    return;
  }
  // Trier par PNB croissant → SGCI (le plus grand) tout en haut
  banks.sort((a,b) => (pnbD[a]||0)-(pnbD[b]||0));
  const toMds = v => v ? +(v/1000).toFixed(1) : 0;
  const pnbV = banks.map(b => toMds(pnbD[b]));
  const rbeV = banks.map(b => toMds(rbeD[b]));
  const reV  = banks.map(b => toMds(reD[b]));
  const rnV  = banks.map(b => toMds(rnD[b]));
  const maxV = Math.max(...pnbV);
  const colRN = "#88E3F6";
  Plotly.newPlot(id, [
    { type:"bar", orientation:"h", name:"PNB",
      x:pnbV, y:banks, marker:{ color:"rgba(99,102,241,.16)", line:{width:0} },
      hovertemplate:"<b>%{y}</b> · PNB : %{x:.1f} Mds<extra></extra>" },
    { type:"bar", orientation:"h", name:"RBE",
      x:rbeV, y:banks, marker:{ color:"rgba(99,102,241,.42)", line:{width:0} },
      hovertemplate:"<b>%{y}</b> · RBE : %{x:.1f} Mds<extra></extra>" },
    { type:"bar", orientation:"h", name:"RE",
      x:reV,  y:banks, marker:{ color:"rgba(99,102,241,.68)", line:{width:0} },
      hovertemplate:"<b>%{y}</b> · RE : %{x:.1f} Mds<extra></extra>" },
    { type:"bar", orientation:"h", name:"RN",
      x:rnV,  y:banks, marker:{ color:colRN, line:{width:0} },
      hovertemplate:"<b>%{y}</b> · RN : %{x:.1f} Mds<extra></extra>" },
  ], baseLayout({
    height: h||340, barmode:"overlay", bargap:0.22,
    margin:{ l:74, r:12, t:8, b:44 },
    showlegend:true,
    legend:{ orientation:"h", y:-0.16, x:0, font:{size:11}, itemsizing:"constant",
             bgcolor:"rgba(0,0,0,0)" },
    xaxis:{ showticklabels:true, ticksuffix:" Mds", dtick:50,
            gridcolor:pk("--plot-grid")||"#26262b", zeroline:false,
            range:[0, maxV*1.1] },
  }), CFG);
}

/* ================================================================
   CONDITIONS BANCAIRES — données représentatives 2024-2026
   ================================================================ */
const COLS_CB = ["BACI","BICICI","BNI","ECOBANK","NSIA","SGCI","SIB"];

// Noms de services réels depuis PostgreSQL — écrasés au chargement par /api/cb_bd
let CB_PAR = {
  "2024": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
  "2025": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
  "2026": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
};

let CB_ENT = {
  "2024": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
  "2025": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
  "2026": { "Tenue de compte":{BACI:null,BICICI:null,BNI:null,ECOBANK:null,NSIA:null,SGCI:null,SIB:null} },
};

/* 9 anciens graphes CB de maquette (chartCBRanked..chartCBScatter3D) supprimes — code mort, jamais appeles */

/* auto-chart pour les réponses chat */
function autoChart(id, kind){
  if(kind==="frais") return chartFraisRanked(id);
  if(kind==="rn")    return chartTreemap(id);
}
