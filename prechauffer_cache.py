"""Précalcule TOUTES les combinaisons de filtres et les dépose dans le cache de la base.

LE PROBLÈME QU'IL RÉSOUT
    L'instance hébergée dispose d'un dixième de processeur. Le préchauffage au démarrage a dû
    être réduit à la période courante, faute de quoi il monopolisait ce dixième pendant des
    minutes et bloquait les requêtes des utilisateurs — la sonde de santé de l'hébergeur
    expirait même, et le service était déclaré indisponible.

    Résultat : « Particuliers 2026 S1 » répondait en une seconde, et toutes les autres
    combinaisons — Entreprises, 2025, 2024, S2 — étaient recalculées intégralement à chaque
    consultation. Des minutes d'attente pour le premier qui ouvrait un filtre.

L'IDÉE
    Ces résultats sont ENTIÈREMENT déterministes : à données inchangées, deux exécutions
    rendent exactement la même chose — vérifié en dupliquant la base. Rien n'oblige donc à les
    calculer sur la machine la plus faible du dispositif. On les calcule ICI, sur un poste qui
    a un vrai processeur, et on les dépose dans la table `cache_app` de la base hébergée.
    L'application déployée n'a plus qu'à les lire.

    On passe par l'APPLICATION ELLE-MÊME (son client de test), et non par une reproduction des
    calculs : les clés de cache et les formats restent ainsi ceux de la production, sans
    risque de divergence. Une reproduction finit toujours par diverger, et l'on ne s'en aperçoit
    qu'en voyant l'écran se remplir de travers.

USAGE
    python prechauffer_cache.py                 toutes les combinaisons présentes en base
    python prechauffer_cache.py --annees 2026   une année seulement
    python prechauffer_cache.py --forcer        recalcule même ce qui est déjà en cache
    python prechauffer_cache.py --lister        montre l'état du cache, n'écrit rien

À RELANCER APRÈS CHAQUE INGESTION DE DONNÉES : le cache est vidé à ce moment-là, et sans ce
passage le premier visiteur de chaque filtre repaierait le calcul.
"""
import argparse
import os
import sys
import time

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)


def charger_application(url_base):
    """Importe l'application Flask, pointée sur la base voulue."""
    if url_base:
        os.environ["DATABASE_URL"] = url_base
    import wsgi                                    # résout le chemin et importe server
    return wsgi.app


def combinaisons(app):
    """Périodes et segments RÉELLEMENT présents en base, plutôt qu'une liste écrite en dur.

    Une liste figée devient fausse à la première ingestion : on chaufferait des périodes
    disparues en oubliant celles qui viennent d'arriver.
    """
    import db
    periodes = {}
    try:
        for r in db.query("SELECT DISTINCT annee, semestre FROM cb_tarifs "
                          "WHERE annee IS NOT NULL AND semestre IS NOT NULL "
                          "ORDER BY annee DESC, semestre"):
            periodes.setdefault(int(r["annee"]), set()).add(r["semestre"])
    except Exception as e:
        print(f"  lecture des périodes impossible ({str(e)[:70]}) — repli sur 2026 S1")
        periodes = {2026: {"S1"}}
    try:
        segments = [r["segment"] for r in db.query(
            "SELECT DISTINCT segment FROM cb_tarifs WHERE segment IS NOT NULL ORDER BY segment")]
    except Exception:
        segments = ["Particuliers", "Entreprises"]
    return periodes, segments or ["Particuliers"]


def appels(periodes, segments, banques):
    """Toutes les requêtes portant des DONNÉES, la plus consultée d'abord.

    EXHAUSTIVITÉ VOULUE (2026-08-11). Une première version ne couvrait que sept endpoints sur
    la quinzaine qui portent des données : les autres restaient calculés à la demande, et
    c'est toujours celui qu'on a oublié que l'utilisateur ouvre en premier. La liste est
    désormais alignée sur ce que le navigateur appelle réellement.

    Ne sont PAS chauffés ici :
      — les rédactions du modèle de langage (elles ont leur propre cache, et dépendent d'un
        quota journalier : les forcer ici le viderait sans rien garantir) ;
      — les appels sans état (login, moi, features, banques) qui répondent en millisecondes.

    L'ordre compte : si le processus est interrompu, mieux vaut avoir chauffé ce que les gens
    ouvrent en premier — l'année la plus récente, puis les précédentes.
    """
    plan = []
    for annee in sorted(periodes, reverse=True):
        for sem in sorted(periodes[annee]):
            for seg in segments:
                p = f"annee={annee}&semestre={sem}&segment={seg}"
                court = f"{annee} {sem} {seg[:4]}"
                plan.append((f"CB {court}", f"/api/cb?{p}"))
                plan.append((f"  détail prix {court}", f"/api/cb_prix_par_libelle?{p}"))
                plan.append((f"  bandeau {court}", f"/api/cb_bd?{p}"))
                for q in (1, 2, 3, 5, 6):
                    plan.append((f"  q{q} {court}", f"/api/cb_strat_data?q={q}&{p}"))
                # q1 dépend AUSSI de la banque comparée : le panneau « Nouveaux services
                # concurrents » en change à chaque clic sur un onglet de banque.
                for b in banques:
                    plan.append((f"  q1·{b[:6]} {court}",
                                 f"/api/cb_strat_data?q=1&{p}&banque={b}"))
                plan.append((f"  compétitivité {court}", f"/api/cb_prix_competitivite?{p}"))
                plan.append((f"  repricing {court}", f"/api/cb_repricing?{p}"))
                plan.append((f"  strat-op {court}", f"/api/strategie_operationnelle?{p}"))

    for seg in segments:
        s = seg[:4]
        plan.append((f"évolutions {s}", f"/api/cb_evolutions_all?segment={seg}"))
        plan.append((f"série temporelle {s}", f"/api/cb_serie_temporelle?segment={seg}"))
        plan.append((f"rattrapage {s}", f"/api/cb_rattrapage_depassement?segment={seg}"))
        plan.append((f"innovation/finance {s}", f"/api/cb_innovation_vs_finance?segment={seg}"))
        plan.append((f"STRATÉGIE {s}", f"/api/strategie?segment={seg}"))

    # Santé financière : rapide aujourd'hui, mais elle dépend de l'exercice choisi (AN1/2/3)
    # et le préchauffage ne coûte presque rien. Autant qu'aucun écran ne fasse exception.
    for anx in (1, 2, 3):
        plan.append((f"KPI AN{anx}", f"/api/kpis?rn_anx={anx}"))
        plan.append((f"résilience AN{anx}", f"/api/resilience?anx={anx}"))
    for chemin, libelle in (("/api/ef_series", "séries financières"),
                            ("/api/rn", "résultat net"),
                            ("/api/rn_series", "série résultat net"),
                            ("/api/frais", "frais"),
                            ("/api/radar_agent", "radar"),
                            ("/api/dashboard_resume", "résumé tableau de bord")):
        plan.append((libelle, chemin))
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cible", default=os.getenv("DATABASE_URL_CIBLE"),
                    help="base à chauffer (défaut : celle du .env)")
    ap.add_argument("--annees", type=int, nargs="*", help="limiter à ces années")
    ap.add_argument("--forcer", action="store_true", help="recalculer même si déjà en cache")
    ap.add_argument("--lister", action="store_true", help="montrer l'état du cache, sans écrire")
    a = ap.parse_args()

    app = charger_application(a.cible)
    import db
    print(f"\nBase : {db.DB.get('dbname')}@{db.DB.get('host')}")

    if a.lister:
        try:
            lignes = db.query("SELECT split_part(cle, ':', 1) AS famille, COUNT(*) AS n, "
                              "MAX(maj) AS dernier FROM cache_app GROUP BY 1 ORDER BY 1")
            print(f"\n  {'famille':26} {'entrées':>8}   dernière mise à jour")
            for r in lignes:
                print(f"  {r['famille']:26} {r['n']:>8}   {r['dernier']:%Y-%m-%d %H:%M}")
            if not lignes:
                print("  (cache vide)")
        except Exception as e:
            print("  lecture impossible :", str(e)[:90])
        return 0

    periodes, segments = combinaisons(app)
    if a.annees:
        periodes = {k: v for k, v in periodes.items() if k in a.annees}
    print(f"Périodes : {', '.join(f'{k} ({chr(47).join(sorted(v))})' for k, v in sorted(periodes.items()))}")
    print(f"Segments : {', '.join(segments)}")

    if a.forcer:
        try:
            n = db.execute("DELETE FROM cache_app WHERE cle LIKE 'cb%%' OR cle LIKE 'stratop%%'")
            print(f"Cache vidé : {n} entrée(s)")
        except Exception as e:
            print("Vidage impossible :", str(e)[:80])

    banques = list(getattr(db, "BANKS", []) or ["SGCI"])
    plan = appels(periodes, segments, banques)
    print(f"Banques  : {', '.join(banques)}")
    print(f"\n{len(plan)} appels à jouer.\n")

    client = app.test_client()
    # L'authentification est exigée par la porte unique ; on ouvre une session d'administration.
    mdp = os.getenv("APP_ADMIN_PASSWORD") or "@Dmin124"
    r = client.post("/api/login", json={"identifiant": os.getenv("APP_ADMIN_USER", "admin"),
                                        "mot_de_passe": mdp})
    if r.status_code != 200:
        print(f"Connexion refusée ({r.status_code}) — vérifiez APP_ADMIN_PASSWORD.")
        return 2

    t0, faits, echecs = time.time(), 0, 0
    for i, (libelle, chemin) in enumerate(plan, 1):
        d = time.time()
        try:
            rep = client.get(chemin)
            taille = len(rep.data)
            if rep.status_code != 200 or taille < 20:
                echecs += 1
                etat = f"ÉCHEC {rep.status_code}"
            else:
                faits += 1
                # Afficher en octets sous le kilo-octet : « 0 ko » pour une réponse de
                # 532 octets se lit comme un échec, et j'ai perdu du temps à chercher une
                # panne qui n'existait pas. Une unité mal choisie fabrique de faux bugs.
                etat = f"{taille} o" if taille < 1024 else f"{taille // 1024} ko"
        except Exception as e:
            echecs += 1
            etat = f"ÉCHEC {type(e).__name__}"
        ecoule = time.time() - t0
        reste = (ecoule / i) * (len(plan) - i)
        print(f"  [{i:3}/{len(plan)}] {libelle:26} {time.time()-d:6.1f}s  {etat:12}"
              f"  reste ~{reste/60:.0f} min")

    print(f"\n{faits} réussis, {echecs} échec(s), en {(time.time()-t0)/60:.1f} min.")
    try:
        n = db.query("SELECT COUNT(*) AS n FROM cache_app")[0]["n"]
        print(f"Le cache contient {n} entrée(s).")
    except Exception:
        pass
    # CODE DE SORTIE : on ne considère comme un échec du SCRIPT que l'impossibilité de
    # travailler. Une poignée de réponses vides n'en est pas un — « les services apparus en
    # 2024 » est légitimement vide, 2024 étant la première année de la base : il n'y a rien
    # avant à comparer. Rendre 1 dans ce cas m'a fait annoncer au directeur que le
    # préchauffage s'était « arrêté en erreur » alors qu'il avait tourné jusqu'au bout.
    if echecs:
        print("Les réponses vides sont normales quand la période n'a pas d'antérieur "
              "(ex. « nouveaux services » sur la première année chargée).")
    return 0 if faits else 1


if __name__ == "__main__":
    sys.exit(main())
