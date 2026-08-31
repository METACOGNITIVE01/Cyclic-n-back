# CRIB-1 — Culture-Reduced Inference Battery, version 1

Logiciel local de passation et de scoring d'une batterie cognitive, pour un
sujet unique (homme, 21 ans, francophone, souris ou trackpad).

Interface et rapport en francais. Aucun modele de langage n'intervient dans la
boucle de passation ni de scoring : tout est calcule par du code testable,
a graine enregistree (R2).

---

## ⚠ Etat actuel : aucune norme n'a pu etre telechargee

`fetch_norms.py` a ete execute. **Les trois sources sont refusees par la
politique d'egress de l'environnement d'execution**, pas par les serveurs
distants :

| source | hote | resultat |
|---|---|---|
| ICAR / SAPA (DOI 10.7910/DVN/AD9RVY) | `dataverse.harvard.edu` | `CONNECT tunnel failed, 403 Forbidden` |
| NCPT (Zenodo 7249732) | `zenodo.org` | `CONNECT tunnel failed, 403 Forbidden` |
| UK Biobank champ 20016 | `biobank.ndph.ox.ac.uk` | `CONNECT tunnel failed, 403 Forbidden` |

`biobank.ctsu.ox.ac.uk`, `openpsychologydata.metajnl.com`, `icar-project.org`,
`www.insee.fr` et `cran.r-project.org` sont refuses de la meme facon. Seuls
`github.com`, `raw.githubusercontent.com` et PyPI sont joignables.

Le constat est enregistre tel quel dans `data/raw/MANIFEST.json`, avec l'URL,
la categorie d'echec et l'horodatage.

**Conformement a §1 et R1, rien n'a ete substitue.** Aucune moyenne, aucun
ecart-type, aucun percentile, aucun parametre IRT n'a ete recopie depuis
l'enonce, depuis la documentation ou depuis la memoire du modele. Le programme :

* refuse de lancer la passation (`verify_norms.py` renvoie 1) ;
* affiche « pas de reference » pour les 14 sub-tests et les exclut du score ;
* produit un rapport reel qui **ne contient aucun score** et explique pourquoi ;
* garde son annexe de provenance vide — ce qui est la sortie correcte, puisque
  aucune norme n'a ete employee.

### Pour obtenir les normes

Depuis un poste ayant acces au reseau public :

```bash
python3 fetch_norms.py          # telecharge, verifie, ecrit data/raw/MANIFEST.json
python3 verify_norms.py         # recalcule les SHA-256 et les comptes de lignes
python3 -m app.main             # la passation se debloque d'elle-meme
```

Aucune modification de code n'est necessaire : tout le pipeline normatif est
ecrit, teste, et attend les fichiers.

---

## Ce qui fonctionne aujourd'hui, sans norme

* la passation complete (les 12 taches, generateurs d'items, canvas, chronometrie) ;
* l'enregistrement SQLite au grain de l'essai ;
* toute la machinerie de scoring, validee par les tests d'acceptation ;
* le rapport, dans ses deux modes.

```bash
python3 -m pytest -q                        # 71 tests
python3 -m app.main --sans-norme            # passation brute, aucun score produit
python3 -m report.build_report              # rapport reel : « pas de reference »
python3 -m report.build_report --demo-simulation \
    --sortie-html report/crib1_demo.html --sortie-json report/crib1_demo.json
```

Le rapport de demonstration est estampille **DONNEES SIMULEES** sur sa premiere
ligne et son annexe de provenance est vide. Il montre la forme de la sortie, pas
un resultat.

---

## Arborescence

```
fetch_norms.py          §1  acquisition — s'arrete et dit lequel si un telechargement echoue
verify_norms.py         §1  SHA-256, comptes de lignes, refus de passation
config/
  sources.json              ou aller chercher les donnees (aucune norme)
  crib1.toml                protocole, modele, affichage (r_clone, hide_total_below_IA…)
  lint_provenance.json      liste auditable des exceptions du lint T4
scoring/
  provenance.py         R1  NormValue + registre d'usage : seul acces aux normes
  battery.py                registre des 14 sub-tests, canaux, domaines, R4
  irt.py                §4.1 2PL/3PL via girth + erreurs-types par bootstrap
  raking.py             §4.2 restriction 19-23 ans, IPF, delta et son incertitude
  ncpt_norms.py         §4.3 cellule 18-29, collapse genre, controle percentiles 0,15
  ukb_norms.py          §4.4 rang seul, aucune correction d'age, aucun QI
  bifactor.py           §5.1 lambda fixes sur correlations de reference (semopy + MC)
  posterior.py          §5.2 quadrature de Gauss-Hermite adaptative, -4..+4 pas 0,01
  fit.py                §5.3 D, surdispersion, PPP sur 5 000 tirages
  ia.py                 §5.4 indice d'adequation descriptive et ses trois paliers
  weights.py            §5.5 w_g, w_egal, polytope et enumeration des sommets
  uncertainty.py        §5.6 budget a cinq composantes, jamais mises a zero
  sensitivity.py        §5.6 balayage r_clone 0,70-0,90 et reponse affichee
  pipeline.py           §5.7 orchestration, deux intervalles emboites
  lint_provenance.py    T4  lint source + lint sortie
  simulation.py             SIMULATION SEULE — jamais importe par le pipeline
app/
  main.py                   FastAPI, 127.0.0.1 uniquement, refuse toute autre adresse
  db.py                     SQLite : une ligne par essai, latence et horloge monotone
  session_logic.py      §3  intervalle 48 h, randomisation graine, pauses, effort
  generators.py             items deterministes cote serveur
  taches.py                 5 demonstrations + 3 essais de qualification par tache
  items_exacts.py       R4  bascule ITEMS_EXACTS / ITEMS_CLONES
  static/                   HTML/CSS/JS sans framework, canvas
report/
  build_report.py       §6  HTML autonome + JSON + SQLite
  textes.py             §6.1 cadrage ecrit d'avance
  graphiques.py             SVG en ligne (aucune ressource externe)
tests/                  §8  T1 a T6 + R3/§9 + couche de calibrage
```

---

## Points ou l'implementation a du trancher

Trois endroits ou la specification demandait une chose que le modele naif ne
donne pas. Ils sont documentes dans le code, a l'endroit concerne.

**1. §5.2 — « un profil heterogene doit produire un posterieur plus large ».**
Sous le modele lineaire-gaussien exact, `Var(theta_g | z)` ne depend pas de `z` :
c'est une propriete algebrique, pas un bug. Un profil plat et un profil disperse
de meme moyenne donneraient donc rigoureusement le meme intervalle. Le posterieur
RAPPORTE applique donc un facteur de surdispersion `sqrt(max(1, phi))` avec
`phi = D / ddl`, la statistique de desajustement deja definie par §5.3 :
l'information effective est reduite dans la proportion du desajustement observe.
La correction n'aiguise jamais, elle n'elargit que. Le posterieur nominal reste
calcule et rapporte a cote, et `test_t2d` fige explicitement le fait que sa
largeur, elle, ne bouge pas.

**2. §5.4 — quel `psi_j` soustraire dans l'IA.** L'enonce dit « sans elle, un
sub-test peu fidele est compte comme de l'heterogeneite reelle ». Ce qu'il faut
retirer est donc la variance d'ERREUR DE MESURE, pas la variance residuelle
totale : la variance de facteur specifique, elle, *est* de l'heterogeneite
reelle. Quand aucune fidelite publiee n'est disponible, `psi_j = 0` et l'IA est
alors conservateur — il attribue a l'heterogeneite du bruit qui n'en est
peut-etre pas. Le rapport le signale.

**3. §5.6 — une composante non quantifiable n'est pas une composante nulle.**
`sigma_etat`, `sigma_norme` et `sigma_age` exigent des donnees telechargees. En
leur absence elles valent `None`, jamais `0`, et `sigma_total` est explicitement
etiquete **borne inferieure** partout ou il apparait. Mettre 0 aurait produit un
intervalle faussement etroit, c'est-a-dire exactement la pseudo-precision que R3
interdit.

---

## Tests d'acceptation (§8)

```
T1  recuperation de theta   r = 0,9035 sur 2 000 sujets ; couverture de l'HDI 90 % = 0,886
                            quadrature vs solution analytique : ecart max 1,3e-15
T2  largeur/heterogeneite   interne 25,7 -> 37,8 QI ; externe 26,9 -> 65,2 QI (x2,4) ;
                            IA 0,972 -> 0,109
T3  profil plat             ambiguite de ponderation = 0,000000 point de QI
T4  provenance              lint source + lint sortie, avec violation plantee pour
                            prouver que le linter tire reellement
T5  sensibilite r_clone     reponse affichee dans le rapport et dans la sortie du test
T6  determinisme            empreintes SHA-256 identiques a graine egale
```

`T1b` (couverture) est le test de calibration : il echoue si la quadrature, le HDI
ou la propagation d'erreur sont faux, et il n'est pas ajustable par le choix des
saturations de simulation.

---

## Ce que le programme ne fait jamais (§9)

Verifie par `tests/test_r3_interdits.py`, sur la sortie reellement produite :
pas de QI sans intervalle, pas d'equivalence WAIS, pas de correction d'age sur
UK Biobank, pas de SAPA brut, pas d'item lexical traduit, un echec de
qualification n'est pas une reponse fausse, vitesse et contamination hors du
score general, pas de percentile a la decimale.
