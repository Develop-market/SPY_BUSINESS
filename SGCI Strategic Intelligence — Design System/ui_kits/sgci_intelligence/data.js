// Demo dataset for the SGCI Strategic Intelligence UI kit.
// Numbers are representative, not real — they exist to drive the visual fidelity.

window.SGCI_DATA = {
  banks: [
    { id: "sgci",    name: "Société Générale CI", short: "SGCI",    logo: "../../assets/logos/SGCI.png",    focus: true },
    { id: "bicici",  name: "BICICI (BNP Paribas)", short: "BICICI",  logo: "../../assets/logos/BICICI.png" },
    { id: "ecobank", name: "Ecobank Côte d'Ivoire", short: "ECOBANK", logo: "../../assets/logos/ECOBANK.png" },
    { id: "nsia",    name: "NSIA Banque",          short: "NSIA",    logo: "../../assets/logos/NSIA.png" },
    { id: "sib",     name: "SIB (Attijariwafa)",   short: "SIB",     logo: "../../assets/logos/SIB.png" },
    { id: "baci",    name: "BACI",                 short: "BACI",    logo: "../../assets/logos/BACI.png" },
    { id: "bni",     name: "BNI",                  short: "BNI",     logo: "../../assets/logos/BNI.jpg" },
  ],

  kpis: {
    positionnement: [
      { id: "cheapest", label: "Banque la moins chère", value: "BACI", sub: "10 100 FCFA/mois · particuliers", delta: { tone: "info", text: "● Panier modèle" }, ic: "wallet" },
      { id: "cards", label: "Meilleures cartes", value: "BICICI", sub: "À partir de 18 000 FCFA/an", delta: { tone: "gain", text: "▲ -8% vs peer avg" }, ic: "card" },
      { id: "incidents", label: "Incidents les – chers", value: "NSIA", sub: "Chèque impayé : 12 200 FCFA", delta: { tone: "warn", text: "● 4 banques au-dessus" }, ic: "alert" },
      { id: "credit", label: "Meilleur découvert", value: "SGCI", sub: "Taux découvert : 9,8 %", delta: { tone: "gain", text: "▲ -1,4 pts vs avg" }, ic: "percent" },
      { id: "savings", label: "Meilleure épargne", value: "ECOBANK", sub: "Taux épargne : 4,9 %", delta: { tone: "gain", text: "▲ +0,6 pts" }, ic: "pig" },
    ],
    performance: [
      { id: "pnb",     label: "PNB · AN3",         value: "182,4", unit: "Mds FCFA", delta: { tone: "gain", text: "▲ +8,1 %" }, sub: "vs AN2" },
      { id: "rn",      label: "Résultat Net · AN3", value: "47,1",  unit: "Mds FCFA", delta: { tone: "gain", text: "▲ +12,4 %" }, sub: "vs AN2" },
      { id: "roe",     label: "ROE",                value: "21,4",  unit: "%",        delta: { tone: "warn", text: "● Peer avg 18,2 %" }, sub: "AN3" },
      { id: "coeff",   label: "Coef. Exploitation", value: "47,9",  unit: "%",        delta: { tone: "gain", text: "▼ -2,1 pts" }, sub: "objectif < 55%" },
      { id: "npl",     label: "NPL",                value: "3,8",   unit: "%",        delta: { tone: "warn", text: "● Vigilance" }, sub: "vs avg 4,2 %" },
    ],
  },

  // Tariff comparison
  pricing: [
    { bank: "SGCI",    monthlyCost: 12450, cardClassic: 22000, savingsRate: 3.5, overdraftRate: 9.8,  uemoaTransfer: 4500 },
    { bank: "BICICI",  monthlyCost: 11200, cardClassic: 18000, savingsRate: 3.2, overdraftRate: 11.2, uemoaTransfer: 4200 },
    { bank: "ECOBANK", monthlyCost: 13900, cardClassic: 24000, savingsRate: 4.9, overdraftRate: 12.4, uemoaTransfer: 5000 },
    { bank: "NSIA",    monthlyCost: 10800, cardClassic: 19500, savingsRate: 3.9, overdraftRate: 10.6, uemoaTransfer: 4100 },
    { bank: "SIB",     monthlyCost: 12100, cardClassic: 21000, savingsRate: 3.6, overdraftRate: 11.5, uemoaTransfer: 4400 },
    { bank: "BACI",    monthlyCost: 10100, cardClassic: 17500, savingsRate: 3.3, overdraftRate: 11.9, uemoaTransfer: 4000 },
    { bank: "BNI",     monthlyCost: 11800, cardClassic: 20000, savingsRate: 3.4, overdraftRate: 11.7, uemoaTransfer: 4300 },
  ],

  // Financial series — AN1..AN3 PNB in Mds FCFA, hand-tuned to look plausible.
  pnbSeries: {
    sgci:    [149, 168, 182],
    bicici:  [88,  91,  94],
    ecobank: [121, 132, 142],
    nsia:    [60,  66,  73],
    sib:     [78,  83,  87],
    baci:    [42,  46,  49],
    bni:     [55,  58,  62],
  },

  // Bank x Product presence matrix (subset)
  productMatrix: {
    products: [
      "Compte à vue", "DAT", "Cartes International", "Banque mobile",
      "MYBUSINESS / cash mgmt", "TPE / e-commerce", "Crédit immo",
      "Crédit doc / garanties", "Programme femmes entrepreneures",
    ],
    presence: {
      sgci:    [1,1,1,1,1,1,1,1,0],
      bicici:  [1,1,1,1,1,1,1,1,0],
      ecobank: [1,1,1,1,1,1,1,1,1],
      nsia:    [1,1,1,1,0,1,1,0,1],
      sib:     [1,1,1,1,1,1,1,1,0],
      baci:    [1,1,0,1,0,0,1,0,0],
      bni:     [1,1,1,1,0,0,1,0,0],
    },
  },

  // Assistant suggested questions
  suggested: [
    "Quelle banque est la plus rentable ?",
    "Comparer SGCI et BICICI",
    "Quel est le meilleur taux épargne ?",
    "Pourquoi ECOBANK est plus chère ?",
    "Analyser la performance de NSIA",
  ],
};
