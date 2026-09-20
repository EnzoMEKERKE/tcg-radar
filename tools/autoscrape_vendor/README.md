# AutoScrape — copie minimale

Source : https://github.com/DrankRock/AutoScrape

Révision : `d5e8afd3f03907ad693451651ab1659fdcb889fb` (licence MIT dans LICENSE).
Fichiers repris : `Backend/playwrightPy.py`, `Backend/Plugins/cardmarket_parser.py`
et `Backend/Plugins/templated_plugin.py`.

Adaptations locales : import relatif du plugin ; ajout du champ `accumulate`
manquant dans la dataclass amont ; propagation des erreurs de navigation/HTTP ;
user-agent natif sans fichier de configuration ; attente du DOM et des sélecteurs
Cardmarket à la place de `networkidle` (les connexions persistantes peuvent
empêcher cette dernière attente de terminer).

Le parseur amont extrait des statistiques produit, pas des offres individuelles.
Le lanceur utilise séparément le parseur TCG Radar pour les offres Pokémon.
L'interface Qt et les autres moteurs ne sont pas nécessaires au lanceur.
