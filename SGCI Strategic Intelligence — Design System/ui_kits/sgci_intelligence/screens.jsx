// SGCI Strategic Intelligence — v2 dashboard.
// Single dense executive home screen that demonstrates the full visual language.

const { useState: useS, useRef: useR, useEffect: useE } = React;
const D = window.SGCI_DATA;

const VIZ = ["#E4002B","#38BDF8","#34D399","#FBBF24","#A78BFA","#F472B6","#14B8A6"];
const colorFor = (id, i) => id === "sgci" ? "#E4002B" : VIZ[(i % (VIZ.length - 1)) + 1];

/* =========================================================================
   DASHBOARD — the v2 hero screen. Replaces Positionnement as the default view.
   ========================================================================= */
const DashboardScreen = () => {
  const banks = D.banks;
  const pnbBars = banks.map((b, i) => {
    const v = D.pnbSeries[b.id][2];
    return { label: b.short, value: v, focus: b.focus };
  }).sort((a, b) => b.value - a.value);

  // Donut: market share by PNB (AN3)
  const totalPnb = banks.reduce((s, b) => s + D.pnbSeries[b.id][2], 0);
  const donut = banks.map((b, i) => ({
    label: b.short, value: D.pnbSeries[b.id][2],
    color: colorFor(b.id, i), focus: b.focus,
  })).sort((a, b) => b.value - a.value);
  const sgciShare = (D.pnbSeries.sgci[2] / totalPnb * 100).toFixed(1).replace(".", ",");

  // ROE ranking
  const roeRanking = banks.map((b, i) => ({
    bank: b,
    segment: b.focus ? "Banque universelle · Focus" : (i % 2 === 0 ? "Banque pan-africaine" : "Banque universelle"),
    roe: parseFloat((15 + i * 0.8 + (b.focus ? 4 : 0)).toFixed(1)),
    sparkline: [10 + i, 12 + i, 14 + i, 13 + i + (b.focus ? 4 : 0), 15 + i + (b.focus ? 4 : 0)],
  })).sort((a, b) => b.roe - a.roe).map((r, idx) => ({
    ...r, rank: idx + 1,
    status: idx === 0 ? { kind: "leader", label: "Leader" }
          : idx === 1 ? { kind: "follower", label: "Challenger" }
          : idx === 2 ? { kind: "follower", label: "Suiveur" }
          : idx === 3 ? { kind: "pressure", label: "Sous pression" }
          : idx === 4 ? { kind: "pressure", label: "Marge réduite" }
          : { kind: "risk", label: "À surveiller" },
  }));
  const maxRoe = Math.max(...roeRanking.map(r => r.roe));

  // Signals feed
  const signals = [
    { icon: "trending-up", tone: "green", title: "PNB SGCI franchit 180 Mds FCFA (AN3)", meta: "il y a 2 h · Rapport financier consolidé", status: { kind: "gain", label: "Validé" } },
    { icon: "alert",       tone: "gold",  title: "Écart capital ratio NSIA → seuil régulateur",  meta: "il y a 5 h · BCEAO · Cellule Conformité", status: { kind: "pressure", label: "À arbitrer" } },
    { icon: "credit-card", tone: "sky",   title: "ECOBANK lance wallet trésorerie corporate",     meta: "Hier · Veille concurrentielle", status: { kind: "risk", label: "Gap produit" } },
    { icon: "file-text",   tone: "red",   title: "BICICI publie rapport activité 2025",           meta: "Hier · 247 pages · indexé RAG", status: { kind: "follower", label: "Indexé" } },
    { icon: "percent",     tone: "violet",title: "Taux directeur BCEAO inchangé · révision T3",   meta: "20 mai · Note réglementaire", status: { kind: "neutral", label: "Note" } },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <HeroStrip
        user="Direction Générale"
        date="Mardi 20 mai 2026"
        summary="SGCI consolide son leadership ROE (21,4 %) et maintient un coefficient d'exploitation sous 50 %. Deux signaux à arbitrer cette semaine — wallet trésorerie corporate (ECOBANK) et capital ratio NSIA."
        metric={[
          { label: "PNB AN3",       value: "182,4", unit: "Mds FCFA", delta: "▲ +8,1 %" },
          { label: "ROE",            value: "21,4",  unit: "%",        delta: "▲ +3,2 pts vs peer" },
          { label: "Part de marché", value: sgciShare, unit: "%",      delta: "▲ +0,6 pt" },
          { label: "Coef. expl.",    value: "47,9",  unit: "%",        delta: "▼ -2,1 pts" },
        ]}
      />

      {/* KPI strip with colored backgrounds + icon badges + sparklines */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <KpiCard label="Produit Net Bancaire · AN3" value="182,4" unit="Mds FCFA"
          sub="vs AN2 · panel SGCI"
          icon="trending-up" tone="red"
          delta={{ tone: "gain", text: "▲ +8,1 %" }}
          sparkline={D.pnbSeries.sgci}/>
        <KpiCard label="Résultat Net · AN3" value="47,1" unit="Mds FCFA"
          sub="vs AN2 · 39,9 Mds"
          icon="wallet" tone="green"
          delta={{ tone: "gain", text: "▲ +18,0 %" }}
          sparkline={[28, 32, 36, 40, 47]}/>
        <KpiCard label="ROE · AN3" value="21,4" unit="%"
          sub="Peer avg 18,2 %"
          icon="percent" tone="gold"
          delta={{ tone: "warn", text: "● +3,2 pts" }}
          sparkline={[17, 18, 19, 20, 21]}/>
        <KpiCard label="NPL · ratio créances" value="3,8" unit="%"
          sub="vs avg 4,2 % · vigilance"
          icon="alert" tone="sky"
          delta={{ tone: "loss", text: "▼ -0,4 pt" }}
          sparkline={[4.6, 4.4, 4.2, 4.0, 3.8]}/>
      </div>

      {/* Chart row: PNB bars (focused) + donut market share */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16 }}>
        <Card eyebrow="Performance comparée"
              title="Produit Net Bancaire · AN3"
              subtitle="Mds FCFA — SGCI en focus, peers en slate"
              action={
                <div style={{ display: "inline-flex", padding: 3, background: "var(--bg-3)", border: "1px solid var(--border-1)", borderRadius: 8 }}>
                  {["PNB", "RN", "ROE", "Coef."].map((t, i) => (
                    <button key={t} style={{
                      padding: "6px 12px", borderRadius: 5, border: 0,
                      font: "700 11.5px var(--font-sans)",
                      background: i === 0 ? "linear-gradient(180deg, #FF1E45, #E4002B)" : "transparent",
                      color: i === 0 ? "#fff" : "var(--fg-3)",
                      boxShadow: i === 0 ? "0 4px 12px -4px rgba(228,0,43,0.4)" : "none",
                      cursor: "pointer",
                    }}>{t}</button>
                  ))}
                </div>
              }>
          <div style={{ height: 280 }}>
            <MixedBarChart data={pnbBars} height={280}/>
          </div>
        </Card>

        <Card eyebrow="Parts de marché PNB"
              title="Position concurrentielle"
              subtitle="Panel 7 banques · AN3"
              action={<Chip tone="brand">SGCI</Chip>}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingTop: 12 }}>
            <DonutChart data={donut} centerLabel={sgciShare + "%"} centerSub="SGCI · part PNB"/>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 14 }}>
            {donut.slice(0, 6).map(d => (
              <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: d.color, flexShrink: 0, boxShadow: d.focus ? "0 0 8px " + d.color : "none" }}/>
                <span style={{ font: "500 11.5px var(--font-sans)", color: d.focus ? "var(--sg-red-400)" : "var(--fg-3)", flex: 1 }}>{d.label}</span>
                <span className="t-num" style={{ font: "700 11px var(--font-mono)", color: d.focus ? "var(--sg-red-400)" : "var(--fg-1)" }}>
                  {(d.value / totalPnb * 100).toFixed(1).replace(".", ",")}%
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Ranking + Signals */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16 }}>
        <Card eyebrow="Classement"
              title="ROE par banque · AN3"
              subtitle="SGCI première du panel · 21,4 %"
              action={
                <div style={{ display: "flex", gap: 6 }}>
                  <button style={{ padding: "6px 11px", borderRadius: 6, border: "1px solid var(--border-2)", background: "var(--bg-3)", color: "var(--fg-2)", font: "600 11px var(--font-sans)", cursor: "pointer" }}>ROE ↓</button>
                  <button style={{ padding: "6px 11px", borderRadius: 6, border: "1px solid var(--border-1)", background: "transparent", color: "var(--fg-4)", font: "600 11px var(--font-sans)", cursor: "pointer" }}>PNB</button>
                  <button style={{ padding: "6px 11px", borderRadius: 6, border: "1px solid var(--border-1)", background: "transparent", color: "var(--fg-4)", font: "600 11px var(--font-sans)", cursor: "pointer" }}>Coût</button>
                </div>
              }
              padded={false}>
          <div style={{ padding: "0 18px 14px" }}>
            {/* Headers */}
            <div style={{
              display: "grid", gridTemplateColumns: "32px 36px 1fr 100px 100px", gap: 14,
              padding: "10px 4px",
              font: "700 9.5px/1 var(--font-sans)", letterSpacing: "0.12em", textTransform: "uppercase",
              color: "var(--fg-4)",
              borderBottom: "1px solid var(--border-1)",
            }}>
              <span style={{ textAlign: "center" }}>#</span>
              <span/>
              <span>Banque · Progression vs leader</span>
              <span style={{ textAlign: "right" }}>ROE</span>
              <span style={{ textAlign: "right" }}>Statut</span>
            </div>
            {roeRanking.map(r => (
              <RankingRow key={r.bank.id} rank={r.rank} bank={r.bank} segment={r.segment}
                value={r.roe.toFixed(1).replace(".", ",")} unit="%"
                valueRaw={r.roe} max={maxRoe}
                status={r.status} sparkline={r.sparkline}/>
            ))}
          </div>
        </Card>

        <Card eyebrow="Veille & Signaux"
              title="À l'attention de la DG"
              subtitle="Détectés sur les 48 dernières heures"
              action={<Chip dot tone="info">{signals.length} nouveaux</Chip>}
              padded={false}>
          <div style={{ padding: "0 18px 14px" }}>
            {signals.map((s, i) => <SignalRow key={i} {...s}/>)}
          </div>
        </Card>
      </div>

      {/* Assistant teaser */}
      <div style={{
        position: "relative",
        background: "linear-gradient(135deg, #0F1A2E 0%, #0B1220 100%)",
        border: "1px solid var(--border-1)",
        borderRadius: 16,
        padding: "22px 26px",
        overflow: "hidden",
      }}>
        <div style={{ position: "absolute", top: -10, right: -20, width: 280, height: 200, opacity: 0.12, pointerEvents: "none" }}>
          <HexPattern color="#E4002B" opacity={1} size={50}/>
        </div>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 22 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 14,
            background: "linear-gradient(135deg, var(--sg-red-500), var(--sg-red-700))",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 12px 32px -8px rgba(228,0,43,0.55)",
            color: "#fff",
          }}><Icon name="sparkles" size={26}/></div>
          <div style={{ flex: 1 }}>
            <div className="kit-eyebrow" style={{ color: "#FCA5A5" }}>Assistant IA · RAG sur 248 documents</div>
            <div style={{ font: "700 18px/1.3 var(--font-display)", color: "var(--fg-1)", marginTop: 4, letterSpacing: "-0.01em" }}>Posez votre question à l'IA. Citations + chiffres sourcés en direct.</div>
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              {["Pourquoi ECOBANK est-elle plus chère ?", "Comparer SGCI et BICICI", "Détecter les gaps produit", "Analyser la performance de NSIA"].map(q => (
                <button key={q} style={{
                  padding: "7px 12px", borderRadius: 999,
                  background: "rgba(255,255,255,0.06)", border: "1px solid var(--border-2)",
                  color: "var(--fg-2)", font: "600 12px var(--font-sans)",
                  cursor: "pointer",
                }}>{q}</button>
              ))}
            </div>
          </div>
          <Button kind="primary" icon="send">Ouvrir l'assistant</Button>
        </div>
      </div>
    </div>
  );
};

/* =========================================================================
   POSITIONNEMENT — visually upgraded
   ========================================================================= */
const PositionnementScreen = () => {
  const banks = D.banks;
  const costData = banks.map(b => {
    const p = D.pricing.find(r => r.bank.toLowerCase() === b.id);
    return { label: b.short, value: p.monthlyCost, focus: b.focus };
  }).sort((a, b) => a.value - b.value);
  const cardData = banks.map(b => {
    const p = D.pricing.find(r => r.bank.toLowerCase() === b.id);
    return { label: b.short, value: p.cardClassic, focus: b.focus };
  }).sort((a, b) => a.value - b.value);

  const maxCost = Math.max(...costData.map(d => d.value));
  const costRanking = costData.map((d, i) => {
    const bank = banks.find(b => b.short === d.label);
    const p = D.pricing.find(r => r.bank.toLowerCase() === bank.id);
    return {
      rank: i + 1, bank,
      segment: i === 0 ? "Low-cost · particuliers" : i < 3 ? "Tarif compétitif" : "Premium",
      value: p.monthlyCost.toLocaleString("fr-FR"), unit: "FCFA",
      valueRaw: p.monthlyCost, max: maxCost,
      status: i === 0 ? { kind: "leader", label: "Plus compétitif" }
            : i < 3 ? { kind: "follower", label: "Compétitif" }
            : i < 5 ? { kind: "pressure", label: "Marge réduite" }
            : { kind: "risk", label: "Cher" },
    };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14 }}>
        {D.kpis.positionnement.slice(0, 5).map((k, i) => (
          <KpiCard key={k.id} label={k.label}
            value={k.value} sub={k.sub} delta={k.delta}
            icon={k.ic} tone={["red","gold","sky","green","red"][i]}/>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card eyebrow="Coût mensuel" title="Panier modèle · Particuliers"
              subtitle="FCFA / mois — SGCI vs concurrents"
              action={<Chip tone="brand">2026</Chip>}>
          <div style={{ height: 260 }}><MixedBarChart data={costData} height={260}/></div>
        </Card>
        <Card eyebrow="Cartes bancaires" title="Carte classique · annuel"
              subtitle="FCFA / an — gamme entrée"
              action={<Chip>FCFA</Chip>}>
          <div style={{ height: 260 }}><MixedBarChart data={cardData} height={260}/></div>
        </Card>
      </div>

      <Card eyebrow="Classement tarifaire"
            title="Coût mensuel · ranking complet"
            subtitle="Du moins cher au plus cher · panier modèle particuliers"
            action={<Button kind="secondary" size="sm" icon="download">Exporter</Button>}
            padded={false}>
        <div style={{ padding: "0 18px 14px" }}>
          <div style={{
            display: "grid", gridTemplateColumns: "32px 36px 1fr 100px 100px", gap: 14,
            padding: "10px 4px",
            font: "700 9.5px/1 var(--font-sans)", letterSpacing: "0.12em", textTransform: "uppercase",
            color: "var(--fg-4)", borderBottom: "1px solid var(--border-1)",
          }}>
            <span style={{ textAlign: "center" }}>#</span>
            <span/>
            <span>Banque · positionnement</span>
            <span style={{ textAlign: "right" }}>Coût</span>
            <span style={{ textAlign: "right" }}>Statut</span>
          </div>
          {costRanking.map(r => <RankingRow key={r.bank.id} {...r}/>)}
        </div>
      </Card>
    </div>
  );
};

/* =========================================================================
   PERFORMANCE — line chart focused on SGCI trend
   ========================================================================= */
const PerformanceScreen = () => {
  const banks = D.banks;
  const series = banks.map((b, i) => ({
    id: b.id, color: colorFor(b.id, i), focus: b.focus,
    values: D.pnbSeries[b.id] || [0, 0, 0],
  }));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14 }}>
        {D.kpis.performance.map((k, i) => (
          <KpiCard key={k.id} label={k.label} value={k.value} unit={k.unit} sub={k.sub} delta={k.delta}
            icon={["trending-up","wallet","percent","trending-down","alert"][i]}
            tone={["red","green","gold","sky","red"][i]}
            sparkline={[i + 1, i + 2, i + 4, i + 3, i + 5 + (i === 0 ? 2 : 0)]}/>
        ))}
      </div>

      <Card eyebrow="Trajectoire 3 exercices"
            title="Produit Net Bancaire — AN1 → AN3"
            subtitle="Mds FCFA · panel 7 banques · SGCI focus"
            action={<Chip tone="brand">SGCI</Chip>}>
        <div style={{ height: 300 }}>
          <LineChart series={series} xLabels={["AN1", "AN2", "AN3"]} height={300}/>
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12, justifyContent: "center" }}>
          {banks.map((b, i) => (
            <span key={b.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, font: "500 12px var(--font-sans)", color: b.focus ? "var(--fg-1)" : "var(--fg-3)" }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: colorFor(b.id, i), boxShadow: b.focus ? "0 0 8px " + colorFor(b.id, i) : "none" }}/>
              {b.short}
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
};

/* =========================================================================
   SYNTHÈSE — strategic summary
   ========================================================================= */
const SyntheseScreen = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
    <HeroStrip user="Direction Générale" date="Synthèse stratégique · Q2 2026"
      summary="SGCI consolide sa position de leader rentabilité et compresse son coefficient d'exploitation à 47,9 %. Deux écarts à surveiller — wallet trésorerie corporate et programme femmes entrepreneures."
      metric={[
        { label: "Position", value: "#1", unit: "ROE", delta: "▲ Leader" },
        { label: "Risque", value: "Faible", delta: "▲ NPL -0,4 pt" },
        { label: "Gap produit", value: "2", delta: "▼ ECOBANK, NSIA" },
        { label: "Décision", value: "T3", delta: "● 3 arbitrages" },
      ]}/>

    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
      <Card eyebrow="Forces" title="Avantages stratégiques"
            action={<CircleIcon icon="shield" tone="green" size={32}/>}>
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            "ROE en tête de panel · +3,2 pts vs peer",
            "Coefficient d'exploitation < 50 %",
            "Catalogue produit complet entreprises",
            "Croissance PNB +8,1 % AN2 → AN3",
          ].map(t => (
            <li key={t} style={{ display: "flex", gap: 10, font: "500 13px/1.5 var(--font-sans)", color: "var(--fg-2)" }}>
              <Icon name="check" size={15} style={{ color: "#34D399", flexShrink: 0, marginTop: 2 }}/>{t}
            </li>
          ))}
        </ul>
      </Card>
      <Card eyebrow="Vigilance" title="Points de surveillance"
            action={<CircleIcon icon="alert" tone="gold" size={32}/>}>
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            "Coût mensuel particuliers > BACI / NSIA",
            "Pas de wallet trésorerie corporate",
            "Carte classique au-dessus du peer avg",
            "Sensibilité au coût du risque AN3",
          ].map(t => (
            <li key={t} style={{ display: "flex", gap: 10, font: "500 13px/1.5 var(--font-sans)", color: "var(--fg-2)" }}>
              <Icon name="dot" size={10} style={{ color: "#FBBF24", flexShrink: 0, marginTop: 5 }}/>{t}
            </li>
          ))}
        </ul>
      </Card>
      <Card eyebrow="Actions DG" title="À arbitrer · T3 2026"
            action={<CircleIcon icon="target" tone="red" size={32}/>}>
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 14 }}>
          {[
            { t: "Lancer wallet trésorerie corporate", h: "Capex 1,2 Mds · 18 mois", pill: "À décider" },
            { t: "Réduire frais tenue de -8 %", h: "Impact PNB -2,1 Mds · ROE -0,4 pt", pill: "Modélisé" },
            { t: "Pilote femmes entrepreneures", h: "Capex 0,4 Mds · partenariat ICCO", pill: "Pré-cadrage" },
          ].map(a => (
            <li key={a.t} style={{ font: "500 12.5px/1.4 var(--font-sans)", color: "var(--fg-2)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <Icon name="arrow-right" size={14} style={{ color: "var(--sg-red-500)", flexShrink: 0, marginTop: 3 }}/>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
                    <span>{a.t}</span>
                    <StatusPill kind="pressure">{a.pill}</StatusPill>
                  </div>
                  <div style={{ font: "500 11px var(--font-mono)", color: "var(--fg-4)", marginTop: 3 }}>{a.h}</div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  </div>
);

/* =========================================================================
   ASSISTANT IA
   ========================================================================= */
const AssistantScreen = () => {
  const [messages, setMessages] = useS([
    { role: "assistant", content: "Bonjour, je suis l'assistant SGCI. J'interroge en temps réel les 248 documents indexés — conditions, états financiers, rapports d'activité, réglementaire. Posez votre question." },
  ]);
  const [input, setInput] = useS("");
  const [loading, setLoading] = useS(false);
  const scrollRef = useR(null);

  useE(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [messages, loading]);

  const replyFor = (q) => {
    const lq = q.toLowerCase();
    if (lq.includes("rentable") || lq.includes("roe"))
      return {
        text: "**Analyse de rentabilité (ROE · AN3)**\n\nSGCI est en tête avec **21,4 %**, devançant BICICI (18,9 %) et ECOBANK (17,3 %).",
        rank: [
          { bank: "SGCI", v: "21,4 %", focus: true },
          { bank: "BICICI", v: "18,9 %" },
          { bank: "ECOBANK", v: "17,3 %" },
          { bank: "NSIA", v: "15,1 %" },
          { bank: "SIB", v: "14,7 %" },
        ],
        cites: ["Rapport activité SGCI 2025 · p. 14", "États financiers BICICI · AN3", "Bench peer panel"],
      };
    if (lq.includes("ecobank") || lq.includes("cher"))
      return {
        text: "**Pourquoi ECOBANK est plus chère ?**\n\n1. Positionnement pan-africain → coûts réseau plus élevés\n2. Catalogue le plus complet du panel\n3. Investissement digital soutenu sur 3 exercices\n\nLe sur-prix se justifie sur le segment entreprises ; il reste marginal sur particuliers.",
        cites: ["Rapport ECOBANK AN3 · stratégie", "Matrice produits Strategic Intel"],
      };
    return {
      text: "Je traite votre question contre le corpus. Précisez le segment (particuliers / entreprises) et la dimension (tarifs, performance, services).",
      cites: [],
    };
  };

  const send = (q) => {
    const text = (q || input).trim();
    if (!text) return;
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setTimeout(() => {
      setMessages(prev => [...prev, { role: "assistant", ...replyFor(text) }]);
      setLoading(false);
    }, 700);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16, height: "calc(100vh - 200px)" }}>
      <Card padded={false}>
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-1)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 38, height: 38, borderRadius: 10, background: "linear-gradient(135deg, var(--sg-red-500), var(--sg-red-700))", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", boxShadow: "0 8px 20px -6px rgba(228,0,43,0.5)" }}><Icon name="sparkles" size={18}/></div>
              <div>
                <div style={{ font: "700 14px var(--font-display)", color: "var(--fg-1)" }}>Assistant SGCI · RAG</div>
                <div style={{ font: "500 11px var(--font-sans)", color: "var(--fg-3)" }}>Corpus · 248 documents · 7 banques</div>
              </div>
            </div>
            <Chip tone="live" dot pulse>En ligne</Chip>
          </div>
          <div ref={scrollRef} style={{ flex: 1, padding: 20, overflow: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
            {messages.map((m, i) => {
              const isUser = m.role === "user";
              return (
                <div key={i} style={{ display: "flex", gap: 12, flexDirection: isUser ? "row-reverse" : "row" }}>
                  <div style={{
                    width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                    background: isUser ? "linear-gradient(135deg, var(--sg-red-500), var(--sg-red-700))" : "linear-gradient(135deg, #182438, #0B1220)",
                    border: isUser ? 0 : "1px solid var(--border-2)",
                    display: "flex", alignItems: "center", justifyContent: "center", color: "#fff",
                  }}><Icon name={isUser ? "user" : "bot"} size={16}/></div>
                  <div style={{
                    maxWidth: "78%",
                    background: isUser ? "linear-gradient(135deg, var(--sg-red-500), var(--sg-red-700))" : "var(--bg-2)",
                    border: isUser ? 0 : "1px solid var(--border-1)",
                    color: isUser ? "#fff" : "var(--fg-2)",
                    padding: "12px 14px", borderRadius: 12,
                    boxShadow: isUser ? "0 8px 20px -8px rgba(228,0,43,0.45)" : "0 1px 2px rgba(0,0,0,0.4)",
                  }}>
                    <div style={{ font: "500 13px/1.55 var(--font-sans)", whiteSpace: "pre-wrap" }}
                      dangerouslySetInnerHTML={{ __html: m.content.replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fff;">$1</strong>') }}/>
                    {m.rank && (
                      <div style={{ marginTop: 10, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 8, overflow: "hidden" }}>
                        {m.rank.map((r, ri) => {
                          const pct = 30 + ri * 12;
                          return (
                            <div key={r.bank} style={{ padding: "10px 12px", borderTop: ri === 0 ? 0 : "1px solid var(--divider)" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", font: "500 12px var(--font-mono)", color: r.focus ? "var(--sg-red-400)" : "var(--fg-2)", fontWeight: r.focus ? 700 : 500, marginBottom: 5 }}>
                                <span><span style={{ color: "var(--fg-4)", marginRight: 8 }}>#{ri + 1}</span>{r.bank}</span>
                                <span>{r.v}</span>
                              </div>
                              <div style={{ height: 4, background: "var(--bg-3)", borderRadius: 999 }}>
                                <div style={{ height: "100%", width: (100 - pct) + "%", borderRadius: 999, background: r.focus ? "var(--grad-progress-red)" : "var(--grad-progress-slate)" }}/>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {m.cites && m.cites.length > 0 && (
                      <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {m.cites.map(c => (
                          <span key={c} style={{
                            display: "inline-flex", alignItems: "center", gap: 4,
                            font: "500 10.5px var(--font-mono)",
                            background: "var(--bg-inset)", border: "1px solid var(--border-1)",
                            padding: "3px 7px", borderRadius: 4, color: "var(--fg-3)",
                          }}><Icon name="file-text" size={10}/>{c}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(135deg, #182438, #0B1220)", border: "1px solid var(--border-2)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}><Icon name="bot" size={16}/></div>
                <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", padding: "12px 14px", borderRadius: 12, display: "inline-flex", gap: 8, alignItems: "center", color: "var(--fg-3)", font: "500 12px var(--font-sans)" }}>
                  <span className="typing-dot"/><span className="typing-dot" style={{ animationDelay: ".15s" }}/><span className="typing-dot" style={{ animationDelay: ".30s" }}/>
                  Analyse du corpus…
                </div>
              </div>
            )}
          </div>
          <div style={{ padding: "12px 20px 6px", borderTop: "1px solid var(--border-1)", display: "flex", gap: 6, flexWrap: "wrap" }}>
            {D.suggested.slice(0, 3).map(q => (
              <button key={q} onClick={() => send(q)} style={{
                font: "600 11.5px var(--font-sans)", color: "var(--fg-3)",
                background: "var(--bg-3)", border: "1px solid var(--border-1)",
                borderRadius: 999, padding: "5px 11px", cursor: "pointer",
              }}>{q}</button>
            ))}
          </div>
          <div style={{ padding: "10px 20px 18px", display: "flex", gap: 8 }}>
            <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, background: "var(--bg-inset)", border: "1px solid var(--border-2)", borderRadius: 10, padding: "10px 14px" }}>
              <Icon name="sparkles" size={14} style={{ color: "var(--sg-red-500)" }}/>
              <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
                placeholder="Posez votre question… ex. « Pourquoi ECOBANK est plus chère ? »"
                style={{ flex: 1, background: "transparent", border: 0, outline: 0, color: "var(--fg-1)", font: "500 13px var(--font-sans)" }}/>
              <span style={{ font: "700 10px var(--font-mono)", background: "var(--bg-3)", padding: "3px 6px", borderRadius: 5, color: "var(--fg-3)" }}>↵</span>
            </div>
            <Button kind="primary" icon="send" onClick={() => send()}/>
          </div>
        </div>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
        <Card eyebrow="Simulateur" title="Impact tarifaire"
              action={<CircleIcon icon="calculator" tone="red" size={32}/>}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div className="kit-eyebrow" style={{ marginBottom: 6 }}>Banque</div>
              <select style={{ width: "100%", background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 8, padding: "10px 12px", font: "500 13px var(--font-sans)", color: "var(--fg-1)" }}>
                {D.banks.map(b => <option key={b.id}>{b.short}</option>)}
              </select>
            </div>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="kit-eyebrow">Baisse des frais</span>
                <span className="t-num" style={{ font: "700 12px var(--font-mono)", color: "var(--sg-red-400)" }}>-8 %</span>
              </div>
              <input type="range" min="0" max="20" defaultValue="8" style={{ width: "100%", accentColor: "var(--sg-red-500)" }}/>
            </div>
            <div style={{ background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: 14 }}>
              <div className="kit-eyebrow" style={{ marginBottom: 5 }}>Impact estimé</div>
              <div className="t-num" style={{ font: "700 26px var(--font-display)", color: "#FCA5A5", letterSpacing: "-0.02em" }}>-2,4<span style={{ fontSize: 12, color: "var(--fg-3)", marginLeft: 4 }}>Mds FCFA</span></div>
              <div style={{ font: "500 11.5px var(--font-sans)", color: "var(--fg-3)", marginTop: 4 }}>Résultat net AN3 SGCI · ROE -0,4 pt</div>
            </div>
          </div>
        </Card>
        <Card eyebrow="Suggestions" title="Questions populaires"
              action={<CircleIcon icon="sparkles" tone="gold" size={32}/>}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {D.suggested.map(q => (
              <button key={q} onClick={() => send(q)} style={{
                textAlign: "left", font: "500 12.5px/1.4 var(--font-sans)", color: "var(--fg-2)",
                background: "var(--bg-inset)", border: "1px solid var(--border-1)",
                borderRadius: 8, padding: "10px 12px", cursor: "pointer",
              }}>{q}</button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
};

/* =========================================================================
   Documents
   ========================================================================= */
const DocumentsScreen = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
      <KpiCard label="Conditions bancaires" value="87" unit="docs"   sub="Tarifs · UEMOA"          icon="wallet"      tone="red"/>
      <KpiCard label="États financiers"     value="63" unit="docs"   sub="3 exercices · 7 banques" icon="trending-up" tone="green"/>
      <KpiCard label="Rapports d'activité"  value="54" unit="docs"   sub="2023 → 2025"             icon="file-text"   tone="gold"/>
      <KpiCard label="Réglementaire"        value="44" unit="docs"   sub="BCEAO · prudentiel"      icon="shield"      tone="sky"/>
    </div>
    <Card eyebrow="Corpus" title="Recherche vectorielle"
          subtitle="Stub — intégrer le moteur RAG + visualiseur PDF + citations cliquables">
      <div style={{ padding: 14, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, font: "500 12.5px/1.55 var(--font-sans)", color: "var(--fg-3)" }}>
        Cette vue intégrera la recherche par embedding sur le corpus, le filtre par banque/exercice/type, et l'agent de consolidation. Voir <span className="t-code">README.md</span> pour le contrat d'API.
      </div>
    </Card>
  </div>
);

Object.assign(window, { DashboardScreen, PositionnementScreen, PerformanceScreen, SyntheseScreen, AssistantScreen, DocumentsScreen });
