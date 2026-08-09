/* ══════════════════════════════════════════════════════════════════════════════════════
   CONSOLE D'ADMINISTRATION — logique (2026-08-09)

   Autonome : ne charge rien du bundle de l'application. Elle parle aux mêmes endpoints, qui
   sont déjà gardés côté serveur — /api/admin/* exige le rôle administrateur, /api/* exige une
   session. Ce fichier ne décide donc RIEN en matière de sécurité ; il rend l'accès lisible.

   Quatre vues, pas une de plus :
     comptes   créer, modifier, désactiver, supprimer les accès — c'est ici que naît le droit
               d'entrer dans l'application
     ajout     dépôt d'un document et stockage ciblé en base
     refresh   régénération des analyses rédigées
     journal   qui s'est connecté, qui s'est vu refuser quoi
   ══════════════════════════════════════════════════════════════════════════════════════ */

let MOI = null;         // le compte connecté
let META = null;        // sections, rôles, droits par défaut — servis par le serveur
let VUE = "comptes";

const $ = (s, r) => (r || document).querySelector(s);
const esc = t => String(t == null ? "" : t)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

async function api(chemin, options) {
  const r = await fetch(chemin, Object.assign({ credentials: "same-origin" }, options || {}));
  let corps = null;
  try { corps = await r.json(); } catch (e) { corps = null; }
  return { statut: r.status, ok: r.ok, corps: corps || {} };
}

function annonce(cible, texte, bon) {
  const e = $(cible);
  if (!e) return;
  e.className = "msg " + (bon ? "ok" : "err");
  e.textContent = texte;
  if (bon) setTimeout(() => { e.className = "msg"; }, 4000);
}

/* ── PORTE ────────────────────────────────────────────────────────────────────────────
   Un compte non administrateur qui donne des identifiants valides est déconnecté aussitôt.
   Le laisser avec une session ouverte sur une console qu'il ne peut pas utiliser produirait
   une page d'erreurs 403 en cascade, ce qui ressemble à une panne plus qu'à un refus. */
async function entrer() {
  const u = ($("#u").value || "").trim().toLowerCase();
  const p = $("#p").value || "";
  if (!u || !p) return annonce("#porte-msg", "Renseignez l'identifiant et le mot de passe.", false);

  const r = await api("/api/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifiant: u, mot_de_passe: p })
  });
  if (!r.ok) return annonce("#porte-msg", r.corps.error || "Identifiants refusés.", false);

  const moi = await api("/api/moi");
  if ((moi.corps.role || moi.corps.utilisateur?.role) !== "admin") {
    await api("/api/logout", { method: "POST" });
    return annonce("#porte-msg",
      "Ce compte n'est pas administrateur. La console lui est fermée ; " +
      "l'application d'analyse reste accessible.", false);
  }
  MOI = moi.corps.utilisateur || moi.corps;
  ouvrir();
}

async function sortir() {
  await api("/api/logout", { method: "POST" });
  location.reload();
}

function ouvrir() {
  $("#porte").style.display = "none";
  $("#coquille").style.display = "grid";
  $("#qui").textContent = `Connecté : ${MOI.identifiant} · administrateur`;
  aller("comptes");
}

/* Session déjà ouverte ? On évite de redemander le mot de passe à chaque rechargement. */
(async function reprise() {
  const moi = await api("/api/moi");
  const u = moi.corps.utilisateur || moi.corps;
  if (moi.ok && u && u.role === "admin") { MOI = u; ouvrir(); }
})();

/* ── NAVIGATION ─────────────────────────────────────────────────────────────────────── */
const TITRES = {
  comptes: "Accès et comptes",
  ajout: "Ajouter des données",
  refresh: "Rafraîchir les analyses",
  journal: "Journal des accès"
};

function aller(v) {
  VUE = v;
  $("#titre").textContent = TITRES[v] || "";
  document.querySelectorAll(".item[data-vue]").forEach(e =>
    e.classList.toggle("on", e.dataset.vue === v));
  ({ comptes: vueComptes, ajout: vueAjout, refresh: vueRefresh, journal: vueJournal }[v] || (() => {}))();
}

/* ══ VUE 1 — ACCÈS ET COMPTES ═════════════════════════════════════════════════════════
   Le cœur de la demande : « l'admin va créer les accès lui-même ». Sans compte créé ici,
   l'application est fermée — le serveur répond 401 à tout endpoint sans session. */
async function vueComptes() {
  $("#vue").innerHTML = `<div class="panneau"><div class="vide">Chargement…</div></div>`;
  const r = await api("/api/admin/utilisateurs");
  if (!r.ok) {
    $("#vue").innerHTML = `<div class="panneau"><div class="vide">
      Accès refusé (${r.statut}). ${esc(r.corps.error || "")}</div></div>`;
    return;
  }
  META = r.corps;
  const sections = META.sections || {};
  const roles = META.roles || ["lecture", "edition", "admin"];

  const cases = (prefixe, coches) => Object.entries(sections).map(([cle, nom]) => `
    <label class="case"><input type="checkbox" id="${prefixe}-${cle}" value="${cle}"
      ${(coches || []).includes(cle) ? "checked" : ""}> ${esc(nom)}</label>`).join("");

  const lignes = (META.utilisateurs || []).map(u => {
    const dr = (u.droits || []).map(d => sections[d] || d).join(", ") || "—";
    const soi = u.identifiant === MOI.identifiant;
    return `<tr>
      <td><b>${esc(u.identifiant)}</b>${soi ? ` <span class="puce lecture">vous</span>` : ""}</td>
      <td><span class="puce ${esc(u.role)}">${esc(u.role)}</span></td>
      <td><span class="puce ${u.actif === false ? "off" : "on"}">${u.actif === false ? "désactivé" : "actif"}</span></td>
      <td style="font-size:11.5px;color:var(--muted)">${esc(dr)}</td>
      <td style="font-size:11.5px;color:var(--faint)">${esc(u.derniere_connexion || "jamais")}</td>
      <td style="white-space:nowrap">
        <button class="btn sec min" onclick="ouvrirEdition('${esc(u.identifiant)}')">Modifier</button>
        ${soi ? "" : `<button class="btn dgr min" onclick="supprimer('${esc(u.identifiant)}')">Supprimer</button>`}
      </td></tr>`;
  }).join("");

  $("#vue").innerHTML = `
  <div class="panneau">
    <h3>Comptes existants</h3>
    <div class="expl">Un compte créé ici, et lui seul, ouvre l'application d'analyse.
      Sans compte, le serveur refuse toute requête.</div>
    <div style="overflow-x:auto">
      <table><thead><tr>
        <th>Identifiant</th><th>Rôle</th><th>État</th><th>Sections autorisées</th>
        <th>Dernière connexion</th><th></th>
      </tr></thead><tbody>${lignes || `<tr><td colspan="6" class="vide">Aucun compte.</td></tr>`}</tbody></table>
    </div>
  </div>

  <div class="panneau">
    <h3>Créer un accès</h3>
    <div class="expl">Cochez les sections auxquelles cette personne aura droit. Ce qui n'est pas
      coché lui est refusé par le serveur, pas seulement masqué à l'écran.</div>
    <div class="grille" style="margin-bottom:15px">
      <div class="champ" style="margin:0">
        <label for="n-id">Identifiant</label>
        <input type="text" id="n-id" placeholder="prenom.nom" autocomplete="off">
      </div>
      <div class="champ" style="margin:0">
        <label for="n-mp">Mot de passe (${META.longueur_min || 8} caractères minimum)</label>
        <input type="text" id="n-mp" placeholder="mot de passe initial" autocomplete="off">
      </div>
      <div class="champ" style="margin:0">
        <label for="n-role">Rôle</label>
        <select id="n-role" onchange="defautsRole()"
          style="width:100%;background:var(--bg2);border:1px solid var(--line);border-radius:9px;
                 padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          ${roles.map(x => `<option value="${x}">${x}</option>`).join("")}
        </select>
      </div>
    </div>
    <label style="font:700 10.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint)">Sections autorisées</label>
    <div class="cases" id="n-cases">${cases("n", META.droits_par_defaut?.lecture)}</div>
    <div style="margin-top:16px"><button class="btn" style="width:auto" onclick="creer()">Créer l'accès</button></div>
    <div id="creer-msg" class="msg"></div>
  </div>

  <div class="panneau" id="edition" style="display:none">
    <h3>Modifier <span id="e-qui" style="color:var(--accent2)"></span></h3>
    <div class="expl">Laissez le mot de passe vide pour ne pas le changer.</div>
    <div class="grille" style="margin-bottom:15px">
      <div class="champ" style="margin:0">
        <label for="e-mp">Nouveau mot de passe</label>
        <input type="text" id="e-mp" placeholder="(inchangé)" autocomplete="off">
      </div>
      <div class="champ" style="margin:0">
        <label for="e-role">Rôle</label>
        <select id="e-role" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          ${roles.map(x => `<option value="${x}">${x}</option>`).join("")}
        </select>
      </div>
      <div class="champ" style="margin:0">
        <label for="e-actif">État</label>
        <select id="e-actif" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          <option value="true">actif</option><option value="false">désactivé</option>
        </select>
      </div>
    </div>
    <label style="font:700 10.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint)">Sections autorisées</label>
    <div class="cases" id="e-cases">${cases("e", [])}</div>
    <div style="margin-top:16px;display:flex;gap:9px">
      <button class="btn" style="width:auto" onclick="enregistrer()">Enregistrer</button>
      <button class="btn sec" onclick="document.getElementById('edition').style.display='none'">Annuler</button>
    </div>
    <div id="edit-msg" class="msg"></div>
  </div>`;
}

function coches(prefixe) {
  return Object.keys(META.sections || {}).filter(c => $(`#${prefixe}-${c}`)?.checked);
}

function defautsRole() {
  const d = (META.droits_par_defaut || {})[$("#n-role").value] || [];
  Object.keys(META.sections || {}).forEach(c => {
    const e = $(`#n-${c}`); if (e) e.checked = d.includes(c);
  });
}

async function creer() {
  const corps = {
    identifiant: ($("#n-id").value || "").trim(),
    mot_de_passe: $("#n-mp").value || "",
    role: $("#n-role").value,
    droits: coches("n")
  };
  if (!corps.identifiant || !corps.mot_de_passe)
    return annonce("#creer-msg", "Identifiant et mot de passe sont requis.", false);
  const r = await api("/api/admin/utilisateur", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps)
  });
  if (!r.ok || r.corps.ok === false)
    return annonce("#creer-msg", r.corps.error || "Création impossible.", false);
  annonce("#creer-msg", `Accès créé pour « ${corps.identifiant} ».`, true);
  setTimeout(vueComptes, 900);
}

function ouvrirEdition(identifiant) {
  const u = (META.utilisateurs || []).find(x => x.identifiant === identifiant);
  if (!u) return;
  $("#edition").style.display = "";
  $("#edition").dataset.cible = identifiant;
  $("#e-qui").textContent = identifiant;
  $("#e-mp").value = "";
  $("#e-role").value = u.role;
  $("#e-actif").value = u.actif === false ? "false" : "true";
  Object.keys(META.sections || {}).forEach(c => {
    const e = $(`#e-${c}`); if (e) e.checked = (u.droits || []).includes(c);
  });
  $("#edition").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function enregistrer() {
  const cible = $("#edition").dataset.cible;
  const corps = { identifiant: cible, role: $("#e-role").value,
                  actif: $("#e-actif").value === "true", droits: coches("e") };
  if ($("#e-mp").value) corps.mot_de_passe = $("#e-mp").value;
  const r = await api("/api/admin/utilisateur", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps)
  });
  if (!r.ok || r.corps.ok === false)
    return annonce("#edit-msg", r.corps.error || "Modification impossible.", false);
  annonce("#edit-msg", "Enregistré.", true);
  setTimeout(vueComptes, 900);
}

async function supprimer(identifiant) {
  if (!confirm(`Supprimer définitivement l'accès de « ${identifiant} » ?\n\n`
             + `Cette personne ne pourra plus ouvrir l'application.`)) return;
  const r = await api("/api/admin/utilisateur", {
    method: "DELETE", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifiant })
  });
  if (!r.ok || r.corps.ok === false) return alert(r.corps.error || "Suppression impossible.");
  vueComptes();
}

/* ══ VUE 2 — AJOUTER DES DONNÉES ══════════════════════════════════════════════════════
   Deux temps, volontairement séparés : on EXTRAIT et on montre un aperçu, puis seulement on
   STOCKE si l'aperçu est juste. Écrire en base sans avoir regardé ce qu'on écrit est la
   façon la plus sûre d'y introduire une valeur fausse. */
async function vueAjout() {
  $("#vue").innerHTML = `<div class="panneau"><div class="vide">Chargement…</div></div>`;
  const b = await api("/api/ajout/banques");
  const banques = b.corps.banques || b.corps.existantes || [];
  const liste = (Array.isArray(banques) ? banques : []).map(x =>
    typeof x === "string" ? { code: x, nom: x } : x);

  $("#vue").innerHTML = `
  <div class="panneau">
    <h3>Déposer un document</h3>
    <div class="expl">Grille tarifaire, états financiers ou texte réglementaire. Le document est
      d'abord extrait et affiché ; rien n'entre en base avant votre validation.</div>
    <div class="grille" style="margin-bottom:14px">
      <div class="champ" style="margin:0">
        <label for="a-type">Type</label>
        <select id="a-type" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          <option value="CB">Conditions bancaires (tarifs)</option>
          <option value="EF">États financiers</option>
          <option value="REGL">Texte réglementaire</option>
        </select>
      </div>
      <div class="champ" style="margin:0">
        <label for="a-banque">Banque</label>
        <select id="a-banque" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          ${liste.map(x => `<option value="${esc(x.code)}">${esc(x.code)}${x.nom && x.nom !== x.code ? " — " + esc(x.nom) : ""}</option>`).join("")}
        </select>
      </div>
      <div class="champ" style="margin:0">
        <label for="a-annee">Année</label>
        <input type="number" id="a-annee" value="${new Date().getFullYear()}" min="2015" max="2100">
      </div>
      <div class="champ" style="margin:0">
        <label for="a-sem">Semestre</label>
        <select id="a-sem" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          <option value="S1">S1</option><option value="S2">S2</option>
        </select>
      </div>
      <div class="champ" style="margin:0">
        <label for="a-seg">Segment</label>
        <select id="a-seg" style="width:100%;background:var(--bg2);border:1px solid var(--line);
          border-radius:9px;padding:11px 13px;color:var(--ink);font:500 14px var(--sans)">
          <option value="Particuliers">Particuliers</option>
          <option value="Entreprises">Entreprises</option>
        </select>
      </div>
      <div class="champ" style="margin:0">
        <label for="a-fichier">Fichier (PDF)</label>
        <input type="file" id="a-fichier" accept=".pdf" style="width:100%;background:var(--bg2);
          border:1px solid var(--line);border-radius:9px;padding:9px 11px;color:var(--ink);font:500 12.5px var(--sans)">
      </div>
    </div>
    <button class="btn" style="width:auto" onclick="extraire()">Extraire et prévisualiser</button>
    <div id="ajout-msg" class="msg"></div>
    <div id="ajout-suivi" style="margin-top:15px"></div>
  </div>`;
}

async function extraire() {
  const f = $("#a-fichier").files[0];
  if (!f) return annonce("#ajout-msg", "Choisissez un fichier.", false);
  const d = new FormData();
  d.append("fichier", f);
  d.append("type", $("#a-type").value);
  d.append("banque", $("#a-banque").value);
  d.append("annee", $("#a-annee").value);
  d.append("semestre", $("#a-sem").value);
  d.append("segment", $("#a-seg").value);

  annonce("#ajout-msg", "Extraction lancée…", true);
  const r = await api("/api/ajout/extraire", { method: "POST", body: d });
  if (!r.ok || !r.corps.job)
    return annonce("#ajout-msg", r.corps.message || r.corps.error || "Extraction impossible.", false);
  suivre(r.corps.job, "ajout-suivi", res => {
    $("#ajout-suivi").innerHTML += `
      <div style="margin-top:13px;padding:13px;background:var(--bg2);border:1px solid var(--line);border-radius:9px">
        <div style="font:700 12.5px var(--sans);margin-bottom:7px">Aperçu extrait — vérifiez avant de stocker</div>
        <pre style="font:500 11.5px/1.6 var(--mono);color:var(--muted);max-height:280px;overflow:auto;white-space:pre-wrap">${esc(JSON.stringify(res, null, 2)).slice(0, 4000)}</pre>
        <button class="btn" style="width:auto;margin-top:11px" onclick="stocker('${esc(res?.stem || "")}')">Confirmer et stocker en base</button>
      </div>`;
  });
}

async function stocker(stem) {
  const r = await api("/api/ajout/stocker", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: $("#a-type").value, banque: $("#a-banque").value, annee: $("#a-annee").value,
      semestre: $("#a-sem").value, segment: $("#a-seg").value, stem
    })
  });
  if (!r.ok || !r.corps.job)
    return annonce("#ajout-msg", r.corps.message || r.corps.error || "Stockage impossible.", false);
  suivre(r.corps.job, "ajout-suivi", () =>
    annonce("#ajout-msg", "Données stockées. Pensez à rafraîchir les analyses.", true));
}

/* ── Suivi d'un travail long ────────────────────────────────────────────────────────── */
function suivre(job, cible, fini) {
  const zone = $("#" + cible);
  zone.innerHTML = `<div style="padding:11px 13px;background:var(--bg2);border:1px solid var(--line);
    border-radius:9px;font:600 12.5px var(--sans)"><span id="et-${job}">En cours…</span></div>`;
  const t = setInterval(async () => {
    const r = await api(`/api/ajout/statut?job=${encodeURIComponent(job)}`);
    const s = r.corps || {};
    const e = $(`#et-${job}`);
    if (e) e.textContent = (s.stage || s.status || "…") + (s.log ? ` — ${String(s.log).slice(-140)}` : "");
    if (s.status === "done" || s.status === "ok") {
      clearInterval(t);
      if (e) e.textContent = "Terminé.";
      fini && fini(s.result);
    } else if (s.status === "error" || s.status === "unknown") {
      clearInterval(t);
      if (e) e.innerHTML = `<span class="echec">Échec : ${esc(s.log || s.status)}</span>`;
    }
  }, 2000);
}

/* ══ VUE 3 — RAFRAÎCHIR LES ANALYSES ══════════════════════════════════════════════════
   Séparé de l'ajout à dessein : ajouter des données ne fait que STOCKER. Les textes rédigés
   ne changent que lorsqu'on le demande ici, et l'opération consomme des jetons — la déclencher
   sans y penser est un coût, pas un service. */
function vueRefresh() {
  const sections = [
    ["ef", "Santé financière", "Analyses des états financiers : podium, signaux, commentaires chiffrés."],
    ["cb", "Conditions bancaires", "Lectures des grilles tarifaires et propositions de repositionnement."],
    ["strategie", "Stratégie", "Diagnostic, SWOT, Porter, plan et projection à trois ans."]
  ];
  $("#vue").innerHTML = `
  <div class="panneau">
    <h3>Régénérer les textes d'analyse</h3>
    <div class="expl">Les chiffres viennent toujours de la base et n'attendent rien d'ici. Ce sont
      les <b>textes rédigés</b> qui sont refaits. L'opération dure plusieurs minutes et consomme
      des jetons : elle ne se déclenche que sur demande.</div>
    <div class="grille">
      ${sections.map(([cle, nom, quoi]) => `
        <div style="background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:15px">
          <div style="font:800 14px var(--sans);margin-bottom:5px">${esc(nom)}</div>
          <div style="font:500 12px/1.55 var(--sans);color:var(--muted);margin-bottom:12px">${esc(quoi)}</div>
          <button class="btn sec min" onclick="rafraichir('${cle}','${esc(nom)}')">Rafraîchir</button>
          <div id="rf-${cle}" style="margin-top:9px"></div>
        </div>`).join("")}
    </div>
    <div id="refresh-msg" class="msg"></div>
  </div>`;
}

async function rafraichir(section, nom) {
  if (!confirm(`Régénérer les analyses « ${nom} » ?\n\n`
             + `L'opération dure plusieurs minutes et consomme des jetons.`)) return;
  const r = await api(`/api/rafraichir_analyses?section=${encodeURIComponent(section)}`, { method: "POST" });
  if (!r.ok || !r.corps.job)
    return annonce("#refresh-msg", r.corps.error || "Lancement impossible.", false);
  suivre(r.corps.job, `rf-${section}`, () =>
    annonce("#refresh-msg", `Analyses « ${nom} » régénérées.`, true));
}

/* ══ VUE 4 — JOURNAL DES ACCÈS ════════════════════════════════════════════════════════
   Le monitoring demandé. On montre les échecs en rouge : c'est la seule ligne qu'on lit
   vraiment dans un journal, et la noyer dans le reste revient à ne pas la publier. */
async function vueJournal() {
  $("#vue").innerHTML = `<div class="panneau"><div class="vide">Chargement…</div></div>`;
  const r = await api("/api/journal_acces");
  if (!r.ok) {
    $("#vue").innerHTML = `<div class="panneau"><div class="vide">Journal inaccessible (${r.statut}).</div></div>`;
    return;
  }
  const lignes = r.corps.journal || r.corps.entrees || [];
  const echecs = lignes.filter(l => l.succes === false).length;
  $("#vue").innerHTML = `
  <div class="panneau">
    <h3>Journal des accès</h3>
    <div class="expl">${lignes.length} entrée(s) — dont <b style="color:${echecs ? "#FCA5A5" : "var(--muted)"}">${echecs} refus ou échec(s)</b>.
      Connexions, refus de section, écritures en base : chaque événement est daté et attribué.</div>
    <div class="jrn">
      <div class="l" style="font:700 10px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)">
        <div>Horodatage</div><div>Compte</div><div>Action</div><div>Ressource</div></div>
      ${lignes.length ? lignes.map(l => `
        <div class="l${l.succes === false ? " echec" : ""}">
          <div>${esc(l.horodatage || l.date || "")}</div>
          <div>${esc(l.identifiant || "—")}</div>
          <div>${esc(l.action || "")}</div>
          <div>${esc(l.ressource || "")}${l.detail ? " · " + esc(l.detail) : ""}</div>
        </div>`).join("") : `<div class="vide">Aucun événement enregistré.</div>`}
    </div>
  </div>`;
}
