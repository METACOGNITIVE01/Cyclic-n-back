# icar_items/ — chemin ITEMS_EXACTS (vide par defaut)

Les stimuli ICAR sont sous **acces restreint** (icar-project.org). Ils ne sont
pas redistribuables et ne sont donc pas fournis ici.

Si vous obtenez les items aupres du projet ICAR, deposez-les ici sous la forme :

    icar_items/matrix_reasoning.json              (11 items -> C1)
    icar_items/three_dimensional_rotation.json    (24 items -> C2)
    icar_items/letter_number_series.json          ( 9 items -> K1)

Chaque fichier est une liste JSON d'items. Le sub-test correspondant bascule
alors automatiquement de `ITEMS_CLONES` a `ITEMS_EXACTS` (R4), et la composante
`sigma_clone` du budget d'incertitude tombe a zero pour ce sub-test.

Un fichier au compte d'items incorrect est **refuse** plutot que complete par des
clones : melanger items exacts et clones dans un meme sub-test invaliderait
l'etiquette.
