# Maquettes Smail — étape 1 uniquement

Application **PySide6 indépendante** : aucune dépendance au package `mailclient`, aucun accès aux comptes, au coffre Windows ou à SQLite, aucun appel réseau. Les 30 messages et les 3 comptes sont fictifs. Les interactions modifient seulement la mémoire de la maquette ; envoyer, enregistrer une pièce jointe, se connecter ou faire confiance à un certificat n’a aucun effet réel.

## Lancer

Depuis la racine du projet, avec le Python déjà équipé de PySide6 :

```powershell
python mockups/run_mockup.py
python mockups/run_mockup.py --variante 2
python mockups/run_mockup.py --variante 3 --theme sombre
```

Avec l’environnement virtuel existant :

```powershell
.\.venv\Scripts\python.exe mockups/run_mockup.py --variante 1
```

Si PySide6 manque : `python -m pip install -r mockups/requirements.txt`. Les maquettes ne nécessitent ni Bleach, ni keyring, ni WebEngine.

## Comparer

- Le bandeau supérieur change en direct **variante**, **thème**, **densité**, **accent** et **écran**. Les raccourcis Alt+1, Alt+2 et Alt+3 changent de variante.
- Le menu **Parcourir les écrans…** donne accès aux 19 scènes : principale, unifiée, rédaction, ajout de compte, compte non chiffré, certificat, quatre onglets de paramètres, recherche, boîte vide, absence de connexion, chargement, palette, images bloquées, HTML, pièce suspecte et avertissement de pièce jointe.
- Ctrl+K ouvre la palette ; Ctrl+N rédige ; Ctrl+F cible la recherche ; Ctrl+Maj+L change le thème ; Ctrl+Maj+D change la densité. Dans la liste de la variante 3, J/K parcourent, E archive et S étoile. Suppr agit uniquement quand la liste a le focus, pas pendant la saisie d’une recherche.
- Les listes et filtres fonctionnent sur les faux messages. Les comptes et dossiers se sélectionnent. Les actions lu/non lu, favoris, archive et corbeille agissent en mémoire. Les changements disparaissent au redémarrage.
- **Afficher** les images produit une illustration dessinée localement ; rien n’est téléchargé. **Joindre** ajoute un faux fichier sans lire votre disque. **Envoyer** affiche un résultat simulé. Les champs Cc/Cci, la signature et les types de chiffrement sont interactifs. La confirmation du risque est nécessaire pour activer l’ajout d’un compte en clair.
- Les paramètres appliquent l’apparence en direct. Les autres cases sont des représentations interactives, sans modification des réglages réels.

## Captures déjà fournies

Ouvrez [la galerie locale](screenshots/index.html) ou [la planche comparative](screenshots/COMPARAISON.png). Les PNG sont classés par variante, puis `clair/` et `sombre/`. Chaque thème contient les 19 écrans, soit **114 captures**, plus la planche comparative.

```powershell
python -B mockups/run_mockup.py --captures
```

Cette commande régénère seulement les fichiers de `mockups/screenshots/`. Elle capture les vrais widgets Qt, avec animations figées, sur un même jeu de données réinitialisé à chaque scène. `manifest.json` contient les dimensions et empreintes des PNG. La capture porte sur la zone cliente Qt, sans bordure ni barre de titre du système Windows. Les polices Segoe UI sont chargées depuis l’installation Windows ; aucun fichier de police Microsoft n’est redistribué.

## Vérifier

```powershell
python -B mockups/verify.py
python -B mockups/run_mockup.py --smoke-test
python -B mockups/audit.py
```

Le contrôle des maquettes parcourt les 114 combinaisons, les filtres, les raccourcis, les contrastes, la confirmation du mode en clair et l’annulation par défaut du certificat. L’audit compare les empreintes des fichiers du projet situés hors `mockups/` à l’état enregistré avant le travail. Il ne réinitialise ni ne réécrit aucun fichier du projet existant.

## Organisation

| Fichier | Rôle |
| --- | --- |
| `run_mockup.py` | Entrée autonome et arguments |
| `data.py` | Comptes, messages et pièces jointes fictifs |
| `theme.py`, `styles/theme.qss` | Tokens, palette, contraste et QSS centralisé |
| `icons.py`, `fonts.py` | Rendu SVG local et Segoe UI Windows |
| `components.py` | Boutons, bannières, cartes, liste, squelettes, lecteur sans ressources |
| `window.py` | Trois compositions et navigation entre scènes |
| `dialogs.py` | Rédaction, compte, certificat, préférences, palette |
| `capture.py` | Export PNG, galerie et planche comparative |
| `verify.py`, `audit.py` | Contrôles limités aux maquettes et audit d’intégrité |
| `DESIGN.md` | Analyse de l’existant et système de design |
| `MIGRATION.md` | Plan futur ; aucune intégration appliquée |

Les icônes [Lucide](https://lucide.dev/license) sont livrées localement avec leur licence et leur révision source dans `assets/`. Aucun téléchargement ni outil réseau n’est requis ou livré. `prepare_assets.py` fabrique hors réseau les quatre flèches QSS à partir d’un SVG déjà livré.

Le choix d’une variante et l’intégration dans le vrai client restent à faire après votre validation.
