# Cardmarket avec AutoScrape

Le lanceur exécute le moteur Playwright et le plugin Cardmarket de
[DrankRock/AutoScrape](https://github.com/DrankRock/AutoScrape), copiés sous licence
MIT et adaptés dans `autoscrape_vendor`. Il fonctionne indépendamment du service
Docker et du navigateur local déjà utilisés par TCG Radar.

Depuis la racine du projet :

```powershell
python -m pip install -r tools/autoscrape-requirements.txt
python -m playwright install chromium
python tools/autoscrape_cardmarket.py "https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu"
```

Au maximum dix fiches explicites, avec trois secondes entre les lectures.
`--engine playwright-stealth` sélectionne la variante du dépôt amont.
`--output chemin` choisit le dossier de sortie (défaut `.autoscrape`, ignoré par Git).
Un fichier `user-agents.txt` dans ce dossier est facultatif ; sans fichier,
le navigateur conserve son user-agent natif.

Sorties :

- `report.json` : URL, date de tentative, révision amont, statut, statistiques et offres.
- `offers.csv` : offres de vendeurs Pokémon Singles, importables dans Bonnes affaires.
- Un fichier HTML par URL lorsque la navigation aboutit.

Les statistiques ne deviennent jamais des annonces fictives. Un prix moyen ne
prouve ni la langue ni l'état d'une offre. Un port absent reste inconnu.
Le code de sortie vaut 2 si une page échoue ou ne contient aucune donnée reconnue.
Le rapport et le CSV sont remplacés à chaque exécution ; les captures HTML anciennes
peuvent subsister, seuls les fichiers référencés dans le rapport courant font foi.

Pour analyser une capture HTML existante :

```powershell
python tools/autoscrape_cardmarket.py "https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu" --html capture.html
```

Dans ce mode, la date de modification du fichier sert de date d'observation des
offres ; utiliser une capture dont cette date correspond à la collecte réelle.
L'import CSV n'est pas automatique : utiliser l'import de la page Bonnes affaires.

Validation locale du 20 septembre 2026 : 39 tests réussis (adaptateur et module
deals). Les tests réels Playwright standard et stealth reçoivent HTTP 403 sur la fiche Pikachu.
La collecte live n'est donc pas validée et aucune offre réelle n'a été extraite
par ces tests. Rapports : `.validation/autoscrape-live/report.json` et
`.validation/autoscrape-stealth/report.json`.
