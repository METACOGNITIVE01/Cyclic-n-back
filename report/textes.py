"""Textes fixes du rapport, ecrits d'avance (§6.1).

Ils ne dependent d'aucun resultat : ils enoncent ce que ce dispositif peut et ne
peut pas dire, quelle que soit la valeur obtenue.
"""

CE_QUE_LE_TEST_PEUT_DIRE = [
    ("Contenu reduit n'est pas absence de biais.",
     "Retirer le vocabulaire, les references culturelles explicites et une partie "
     "de l'arithmetique reduit certaines sources de variance etrangeres au "
     "raisonnement. Cela n'en fait pas une mesure neutre. La familiarite avec les "
     "surfaces graphiques, la souris, les jeux de reglage visuel, l'habitude des "
     "epreuves a choix multiple restent des competences acquises, inegalement "
     "distribuees, et elles sont mesurees ici en meme temps que le raisonnement."),

    ("Les echantillons de reference ne sont pas representatifs.",
     "SAPA est un echantillon de volontaires en ligne, majoritairement etudiants : "
     "il n'est jamais utilise brut ici, mais le redressement corrige des marges, "
     "pas la selection sur des variables non observees. NCPT est une population "
     "d'utilisateurs d'un logiciel d'entrainement cognitif, donc auto-selectionnee "
     "elle aussi. UK Biobank a 40-69 ans, c'est-a-dire pas l'age du sujet."),

    ("Une partie des sub-tests est clonee, pas identique.",
     "Les items etiquetes ITEMS_CLONES sont regeneres d'apres la description "
     "publiee de la tache. Ils mesurent probablement quelque chose de tres proche, "
     "mais la norme a ete etablie sur les items d'origine, pas sur ceux-ci. "
     "L'ecart est traite comme une incertitude explicite (composante sigma_clone), "
     "pas comme une quantite negligeable."),

    ("Le facteur general obtenu ici est un g a contenu reduit.",
     "Ce n'est pas le g d'une batterie large. Il est estime sur sept sub-tests qui "
     "sur-representent l'induction figurale et la visualisation spatiale et qui "
     "excluent entierement le contenu verbal. Un facteur general extrait d'un "
     "domaine etroit est plus etroit que le facteur qu'on extrait d'un domaine "
     "large, meme quand les deux se correlent fortement."),

    ("Aucune equivalence avec une batterie clinique n'est annoncee.",
     "Les points d'echelle sont exprimes sur une metrique de moyenne 100 et "
     "d'ecart-type 15 parce que c'est une convention de lecture repandue. Ce n'est "
     "pas une equivalence WAIS, et ce rapport n'en propose aucune."),

    ("Un score unique n'est jamais donne sans intervalle.",
     "Tous les chiffres de ce rapport sont accompagnes d'un intervalle. Quand une "
     "composante d'incertitude n'a pas pu etre quantifiee faute de source, "
     "l'intervalle affiche est une BORNE INFERIEURE de l'incertitude reelle, et "
     "c'est signale a l'endroit ou il apparait."),
]

INTERDITS = [
    "produire un « QI » unique sans intervalle",
    "annoncer une equivalence WAIS",
    "corriger le score UK Biobank pour l'age",
    "utiliser l'echantillon SAPA brut comme reference de population",
    "traduire un item lexical et conserver sa norme",
    "compter un echec de qualification comme une reponse fausse",
    "fusionner le canal vitesse ou le canal contamination dans le score general",
    "afficher un percentile a la decimale pres",
]

NOTE_RESIDUS = (
    "Cette section est la partie informative du profil. Le residu d'un sub-test est "
    "l'ecart entre ce que le sujet y a fait et ce que son propre niveau general "
    "laissait attendre — pas l'ecart a la moyenne de la population. Un residu proche "
    "de zero signifie « conforme a lui-meme », pas « moyen »."
)

NOTE_CANAUX = (
    "Le canal vitesse et le canal contamination sont rapportes a part et n'entrent "
    "dans aucun score general. Le canal contamination existe precisement pour "
    "mesurer l'ecart entre une performance qui depend de conventions notationnelles "
    "apprises (ordre alphabetique, chiffres arabes, arithmetique, anglais) et une "
    "performance qui en depend moins."
)

NOTE_PREDICTIONS_ABSENTES = (
    "Aucun coefficient de validite publie n'a pu etre telecharge et cite dans cette "
    "execution. Cette section reste donc vide : le rapport ne propose aucune "
    "prediction de reussite scolaire, professionnelle, de revenu ou de sante. "
    "Enoncer une prediction sans son coefficient source et sans son intervalle "
    "residuel serait exactement ce que ce dispositif est cense empecher."
)

NOTE_ECART_TYPE_RESIDUEL = (
    "Rappel de lecture pour toute prediction : avec une correlation r = 0,50 entre "
    "le score et un critere, connaitre le score laisse encore un ecart-type residuel "
    "de sqrt(1 - 0,50^2) = 0,87 ecart-type sur ce critere. La variance expliquee est "
    "de 25 %, ce qui veut dire que 75 % de la variation du critere reste ailleurs."
)
