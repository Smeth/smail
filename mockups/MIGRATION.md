# Plan de migration — à appliquer après choix d’une variante

**Ce document est un plan, pas une intégration. Aucun fichier du vrai client n’a été modifié.** Attendre le choix explicite d’une des trois variantes avant toute modification hors `mockups/`.

## 1. Décision et contrat visuel

Valider la variante, la densité initiale, l’accent et les deux thèmes à partir de la galerie. Revoir au moins les écrans principale, rédaction, ajout d’un compte en clair, certificat et pièce exécutable. Conserver les autres variantes comme références de comparaison ; ne pas incorporer trois interfaces concurrentes dans le client sans nouvelle demande.

Décider ensuite des adaptations à 1280×800, au redimensionnement et aux DPI Windows 100/125/150/200 %. Les panneaux doivent conserver des minima utiles et la navigation latérale doit défiler avant que ses labels ne soient comprimés.

## 2. Extraction des composants de présentation

| Source de maquette | Destination future proposée | Travail après validation |
| --- | --- | --- |
| `theme.py`, `styles/theme.qss` | `mailclient/ui/theme.py`, `ui/styles/theme.qss` | Conserver les tokens et contrastes ; brancher les préférences existantes sans modifier le chiffrement/cache |
| `components.py` | `mailclient/ui/widgets/` | Extraire Button, Card, Banner, badges, états et delegate en fichiers dédiés ; remplacer leurs callbacks de démonstration par des signaux Qt |
| `icons.py`, `assets/` | `mailclient/ui/icons.py`, `ui/assets/` | Embarquer les SVG et mentions de licence ; inclure les assets dans le build |
| `fonts.py` | Initialisation de présentation | Segoe UI système ; éviter toute redistribution de police Microsoft et conserver le comportement DPI de Qt |
| `window.py` | `mailclient/ui/main_window.py` | Refaire l’assemblage visuel ; conserver les handlers existants comme premiers points de branchement |
| `dialogs.py` | Les cinq fichiers de dialogue/lecture existants selon responsabilité | Appliquer l’apparence choisie progressivement, sans remplacer les fonctions métier par les simulations |

Le QSS et les petits composants sont réutilisables directement. Le delegate de la maquette attend un objet fictif `Mail` : introduire un adaptateur de présentation vers les lignes réelles plutôt que modifier le format des données du service. Les simulations, `data.py`, la capture et les garde-fous de test **ne doivent pas entrer dans le client réel**.

## 3. Points de branchement et fichiers d’interface

| Fichier futur à modifier | Contrats à préserver |
| --- | --- |
| `ui/main_window.py` | `reload_accounts`, `load_folders`, `load_messages`, `read_selected`, `mutate`, `move`, `compose`, `open_draft`, `open_sent_copy`, `export_sent_copy`, `sync_now`, `preferences`, fermeture et zone de notification |
| `ui/mail_view.py` | `display`, `clear`, `show_images`, `save_attachment`, `set_dark`, `shutdown` ; conserver le profil WebEngine, le schéma interne, l’intercepteur, la CSP et la destruction page-avant-profil |
| `ui/compose_window.py` | Compte actif, state du brouillon, pièces jointes binaires, en-têtes de réponse, autosave, envoi partiel, copie locale/serveur, fermeture différée ; ne jamais fusionner envoi SMTP et copie IMAP dans une tâche rejouable |
| `ui/account_dialog.py` | Champs existants, ports manuels, choix des deux transports, confirmation obligatoire, mot de passe conservé si inchangé, OAuth2 et test asynchrone ; garder les actions Annuler pendant l’attente |
| `ui/cert_dialog.py` | L’objet d’alerte réel et tous ses détails ; Annuler par défaut ; case de confiance non cochée ; restituer seulement décision/option au contrôleur TLS existant |
| `ui/settings_dialog.py` | Valeurs et plages existantes de synchronisation/cache ; chiffrement des contenus décrit exactement ; sauvegarde des préférences par le chemin actuel ; nouveaux champs visuels seulement après décision sur leur persistance |
| `main.py` | Initialiser le thème de présentation et les ressources ; garder le diagnostic sans chargement des comptes ; ne pas déplacer les appels réseau dans le fil graphique |
| `Smail.spec` | Ajouter les QSS/SVG/licences comme données ; maintenir keyring Windows et les dépendances WebEngine ; reconstruire sous Windows |

**À laisser inchangés dans cette migration visuelle** : `core/imap_client.py`, `smtp_client.py`, `oauth.py`, `tls_policy.py`, `service.py`, `sync.py`, `parser.py`, `html_security.py`, `storage/database.py` et `storage/secrets.py`. Si un manque de contrat est découvert, le traiter dans une proposition distincte et justifiée, plutôt que le masquer dans le changement de style.

## 4. Signaux et modèle de présentation

Créer un petit modèle de présentation des lignes : identifiant de compte, dossier, UID, UIDVALIDITY, expéditeur, objet, aperçu disponible, date, non lu, étoile et pièce jointe. Le delegate ne déclenche aucun réseau et ne décide d’aucune confiance. L’aperçu doit rester facultatif tant que le cache/service ne le fournit pas : ne pas télécharger un corps depuis `paint()` ou depuis un getter du modèle.

Les composants émettent des intentions (`replyRequested`, `moveRequested`, `imagesRequested`, `saveAttachmentRequested`, `certificateDecision`, etc.). La fenêtre les relie aux chemins existants. Les identifiants de compte/dossier/UID ne doivent jamais être déduits du numéro de ligne après filtrage, tri ou passage en réception unifiée. Les retours asynchrones ne doivent pas afficher un message devenu obsolète à la suite d’une nouvelle sélection.

La palette appelle les mêmes commandes que les boutons, avec les mêmes états activés/désactivés. Aucun chemin clavier ne contourne une confirmation, un refus de connexion ou l’interdiction hors ligne. Les raccourcis à une lettre sont limités au focus de la liste ; Suppr ne s’applique pas aux champs de saisie.

## 5. Ordre d’intégration proposé

1. Intégrer tokens, QSS, icônes et boutons derrière l’interface existante. Contrôler les deux thèmes avant de changer les layouts.
2. Refaire le lecteur et les alertes, en conservant strictement le moteur WebEngine et les décisions de sécurité actuels.
3. Refaire la navigation et le modèle de liste ; vérifier comptes/dossiers, recherche, pagination et attribution des actions en vue unifiée.
4. Habiller la rédaction et les comptes. Conserver les champs, validations, signaux et protections d’envoi ; ajouter seulement la hiérarchie et le repli des options.
5. Catégoriser les préférences ; ajouter la palette comme autre point d’entrée des mêmes commandes. Décider alors du stockage des préférences visuelles nouvelles (densité/accent) sans toucher aux secrets.
6. Vérifier tray/notifications, fermeture, DPI et accessibilité ; reconstruire le paquet et réaliser un test utilisateur avec un compte de test.

Chaque étape doit laisser le client exécutable, avec un retour arrière simple sur les seuls changements d’interface.

## 6. Risques de régression et vérifications

| Risque | Vérification à prévoir après intégration |
| --- | --- |
| Mauvais compte/UID après tri, filtre ou unification | Jeu multi-comptes avec mêmes UID ; vérifier compte, dossier et UIDVALIDITY reçus par les actions |
| Rendu du delegate inaccessible | Texte accessible complet, rôle/sélection annoncés par NVDA, flèches et recherche native ; test à fort zoom |
| Aperçu provoquant des téléchargements cachés | Aucun appel réseau depuis delegate, modèle ou animation ; aperçu uniquement issu d’une donnée déjà disponible |
| Images/librairie de lecture moins protégées | Tests WebEngine réels : images bloquées avant clic, reset au message suivant, scripts/liens/fichiers refusés, profil et CSP conservés |
| Annulation/certificat moins sûr après relookage | Annuler reste défaut clavier et priorité visuelle ; case persistante décochée ; détails complets et texte sélectionnable |
| Ports écrasés ou confirmation contournée | SSL/TLS, STARTTLS, Aucun sur chaque serveur ; port personnalisé ; confirmation réinitialisée après changement ; OAuth2 jamais en clair |
| Double envoi après erreur de copie | Tests existants de refus partiel et certificat sur APPEND ; SMTP appelé une fois ; états distincts envoi/copie/cache |
| Brouillon perdu à Échap/fermeture | Modification pendant sauvegarde, fermeture différée, reprise après redémarrage, suppression confirmée, erreur de coffre |
| Mode hors ligne ignoré par une nouvelle commande | Palette, raccourcis et boutons respectent les mêmes interdictions et messages |
| Timers/signaux sur widgets détruits | Timers parentés ; connexions à récepteurs vivants ; fermeture de dialogue pendant animation/test ; destruction WebEngine ordonnée |
| Styles coupant des labels ou masquant le focus | Vérification 1280×800, fenêtres redimensionnées, textes longs, DPI 100–200 %, Tab/Maj+Tab et contrastes |
| Cache présenté comme totalement chiffré | Libellé exact « contenus du cache » ; paramètres publics et exports explicitement exclus ; aucune valeur réelle écrasée par un défaut de maquette |
| Sortie involontaire ou impossible avec tray | Fermer/rouvrir, fermer une rédaction avec fenêtre masquée, Quitter pendant sync et sauvegarde, attente des tâches |
| Ressources absentes de l’exécutable | Lancement du dossier distribué sur un poste de test sans Python ; vérification des SVG, QSS, licences, keyring et WebEngine |

Conserver les tests métier actuels comme garde-fous, puis ajouter les tests de présentation adaptés. Les captures de maquette ne remplacent pas des tests d’envoi et de sécurité réels. Aucun de ces changements ou tests sur le vrai client n’a été appliqué pendant la présente étape.

## Critère de fin de la prochaine étape

Une seule variante choisie, inventaire fonctionnel intégralement préservé, aucun changement de protocole/stockage/sécurité dissimulé dans l’interface, tests pertinents réussis, contrôle visuel clair/sombre et accessibilité clavier/NVDA, build Windows vérifié. **Attendre votre choix avant de commencer.**
