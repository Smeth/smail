# Smail — analyse et propositions d’interface

## Périmètre

Étapes 0 et 1 uniquement. L’analyse ci-dessous repose sur la lecture des fichiers d’interface existants, sans lancer le vrai client ni ouvrir ses comptes. Tous les fichiers produits sont dans `mockups/`. Les services IMAP/SMTP, le stockage, les secrets, les politiques TLS et OAuth2 ne sont ni importés, ni modifiés, ni remplacés. Les maquettes n’implémentent aucune de ces opérations réelles.

## Étape 0 — structure existante

| Source actuelle | Écran et responsabilités d’interface |
| --- | --- |
| `mailclient/ui/main_window.py` | Fenêtre à trois panneaux ; comptes, dossiers, liste, recherche, actions, préférences, zone de notification, coordination des retours de tâches |
| `mailclient/ui/mail_view.py` | Lecture texte/HTML, images bloquées, pièces jointes, avertissement avant enregistrement d’un exécutable |
| `mailclient/ui/compose_window.py` | Rédaction, réponses/transfert, Cc/Cci, signature, fichiers joints, brouillons et retours d’envoi |
| `mailclient/ui/account_dialog.py` | Ajout et modification d’un compte ; authentification, serveurs, test et signature |
| `mailclient/ui/cert_dialog.py` | Certificat invalide ; détails, annulation, exception temporaire ou mémorisée |
| `mailclient/ui/settings_dialog.py` | Thème, synchronisation, cache, chiffrement, IDLE, notifications et réduction en zone de notification |

Le dossier contient aussi un `__init__.py` sans écran. Les composants sont majoritairement assemblés directement dans ces six fichiers ; il n’existe pas encore de bibliothèque de composants visuels ou de QSS global partagé. Les thèmes actuels combinent palette Qt, couleurs locales et styles du lecteur HTML.

### Inventaire exhaustif des fonctions et points d’entrée à conserver

Cet inventaire recense les commandes, champs, états et garanties présentés par l’interface actuelle. Les garanties métier citées restent des contraintes de migration, pas une logique à reproduire dans les maquettes.

| Domaine | Fonctions à conserver |
| --- | --- |
| Comptes | Ajouter et modifier plusieurs comptes ; nom, adresse, sélection du compte actif ; réception unifiée avec compte d’origine identifiable ; choix d’un compte depuis les préférences lorsqu’une vue unifiée est active |
| Configuration | Paramètres distincts IMAP/SMTP : serveur, port, SSL/TLS, STARTTLS ou Aucun ; ports automatiques et modifiables ; préréglages Gmail/Outlook/Hotmail/Yahoo ; adresse utilisée comme identifiant de connexion |
| Identifiants | Mot de passe masqué ; stockage uniquement via le coffre Windows ; conservation possible du mot de passe lors de la modification d’un compte ; indication des erreurs de coffre |
| OAuth2 | Sélection Google/Microsoft ; identifiant client, secret client Google si requis, tenant Microsoft ; autorisation dans le navigateur ; état d’attente, annulation et retour de réussite/échec ; obligation de connexion chiffrée |
| Test | Test IMAP **et** SMTP avant enregistrement, sans envoyer de message ; progression, résultat et erreurs en français ; test facultatif avant sauvegarde |
| Connexion en clair | Avertissement rouge explicite ; confirmation obligatoire ; rappel permanent près du compte et indication en réception unifiée |
| Certificat | Serveur/port, émetteur, validité, raison et empreinte SHA-256 sélectionnable ; Annuler par défaut ; Continuer quand même ; confiance persistante facultative pour ce compte ; nouvelle alerte si l’empreinte change |
| Transport | Vérification des certificats par défaut ; absence de repli STARTTLS vers le clair ; authentification après contrôle ; prise de décision explicite requise lors d’une erreur rencontrée en arrière-plan |
| Navigation | Dossiers de réception, envoyés, brouillons, corbeille, indésirables, archives et autres dossiers du serveur ; actualisation ; réception unifiée ; attribution correcte du compte lors d’une réponse/action |
| Liste | Expéditeur, objet, date, non lu, étoile, pièce jointe ; ordre récent ; sélection unique ; pagination de 50, page précédente/suivante et total ; état d’une page indisponible hors ligne |
| Recherche | Recherche dans expéditeur, objet et contenu via le serveur ; saisie UTF-8 ; résultats paginés ; recherche dans les contenus déjà en cache hors ligne et en réception unifiée ; indication de la portée réelle |
| Lecture | Trois panneaux ; texte brut et HTML sécurisé ; décodage des en-têtes/MIME ; expéditeur, destinataires, Cc, objet et date ; lecture sans changement implicite du drapeau lu |
| Protection de lecture | HTML assaini, JavaScript désactivé ; navigation/liens et téléchargements WebEngine bloqués ; profil privé ; ressources locales interdites ; aucun contenu de message dans les journaux |
| Images | Images distantes bloquées par défaut ; bouton d’autorisation pour le message courant ; réinitialisation au message suivant ; images intégrées Content-ID consultables sans réseau |
| Pièces jointes | Liste, nom et taille ; sélection ; enregistrement explicite ; noms assainis ; avertissement supplémentaire pour exécutable/script/contenu actif avec Annuler par défaut ; aucune ouverture automatique |
| Actions | Marquer lu/non lu ; étoiler/retirer l’étoile ; déplacer ; archiver ; supprimer vers la corbeille après confirmation ; choisir une destination existante si dossier spécial inconnu ; pas de suppression définitive globale |
| Intégrité des actions | Compte, dossier, UID et UIDVALIDITY conservés ; refus d’une action après changement d’identité du dossier/serveur ; message d’erreur invitant à actualiser après une coupure ; pas de purge globale des messages d’autres sessions |
| Rédaction | Nouveau message, réponse, réponse à tous, transfert ; choix du compte expéditeur ; À/Cc/Cci, objet et texte ; ajout/retrait des pièces jointes ; transfert avec fichiers joints |
| Réponses | Respect de Reply-To ; destinataires de réponse à tous sans doublons et sans soi-même ; conservation du fil de discussion ; texte cité ; signature du compte ; avertissement après changement de compte dans une rédaction |
| Envoi | Validation des en-têtes et adresses ; confirmation d’un objet vide ; Cci uniquement dans l’enveloppe ; état d’envoi en cours ; erreurs et livraison incertaine explicites ; aucun renvoi SMTP automatique ; seuls les destinataires refusés restent après un envoi partiel |
| Brouillons | Sauvegarde locale automatique après modification et périodique ; attente de sauvegarde à la fermeture/Échap ; reprise via liste des brouillons ; suppression avec confirmation ; copie explicite aux brouillons serveur, même sans destinataire |
| Envoyés | Copie locale après acceptation SMTP ; copie serveur séparée avec traitement Gmail ; erreur de copie distincte d’une erreur d’envoi ; liste des envoyés locaux ; lecture et export `.eml` sans renvoi |
| Hors ligne | Consultation des dossiers/listes/messages/attachments téléchargés ; case Hors ligne ; messages explicites pour contenus ou pages non téléchargés ; envois et modifications réseau interdits dans ce mode ; tâches déjà engagées pouvant finir |
| Synchronisation | Déclenchement manuel ; intervalle réglable 1–120 min ; limite automatique 50–5000 messages par dossier ; arrière-plan ; réutilisation des contenus ; IMAP IDLE optionnel et reconnexion progressive ; retour d’erreur sans gel volontaire de l’interface |
| Cache | Option de chiffrement authentifié des **contenus** ; clé dans le coffre Windows ; ne pas présenter cela comme du SQLCipher intégral ; paramètres publics lisibles ; exports/fichiers enregistrés hors de cette protection |
| Confort | Thèmes clair et sombre, y compris lecture ; notifications de nouveaux mails sans faux signalement initial ; signature personnalisée par compte |
| Zone de notification | Icône, double-clic pour rouvrir, menu Ouvrir/Synchroniser/Quitter ; réduction à la fermeture facultative ; attente des tâches et sauvegardes à la sortie |
| Raccourcis existants | Ctrl+N rédiger ; Ctrl+R répondre ; Ctrl+Maj+R répondre à tous ; Ctrl+L transférer ; Suppr corbeille ; F5 synchroniser. Les nouveaux raccourcis de maquette sont explicités séparément |
| États et retours | Attente de connexion/lecture/sauvegarde, erreur d’authentification, serveur inaccessible, délai dépassé, certificat invalide, absence de dossier, boîte vide, page non mise en cache, succès et envoi partiel ; textes en français et sans secrets |

### Défauts observés dans le code de l’interface actuelle

| Constat | Effet sur l’usage | Réponse proposée |
| --- | --- | --- |
| Une même barre porte rédaction, lecture, actions, brouillons, envoyés, export, compte et préférences | Toutes les commandes semblent également prioritaires ; débordement probable en petite largeur | Une action principale « Nouveau message », des actions contextuelles près du lecteur, des paramètres hors du flux courrier |
| Liste en table, sans aperçu, avec la ligne entière mise en gras | Difficile de balayer expéditeur/objet et d’estimer le contenu | Trois niveaux explicites : expéditeur, objet, aperçu ; date discrète ; non lu par point et poids de l’objet |
| Largeurs de colonnes partiellement fixes et noms de comptes ajoutés dans la cellule expéditeur | Contenu tronqué et variations de hauteur sans hiérarchie | Delegate de liste adapté à la densité ; initiales/attribution de compte distincte ; panneaux redimensionnables |
| Pas de système typographique, d’espacement ou d’icônes partagé | Hétérogénéité entre les fenêtres et maintenance dispersée | Tokens, Segoe UI, composants communs et SVG Lucide locaux |
| Paramètres présentés dans une seule liste ; compte très long et peu segmenté | Coût de recherche élevé, champs OAuth visibles même lorsqu’ils sont inutiles | Quatre catégories de préférences ; authentification progressive ; serveurs côte à côte ; options avancées repliables |
| Erreurs et progression principalement en barre d’état | Informations importantes faciles à manquer | Bannières sémantiques au lieu concerné, état de liste, indication permanente de connexion |
| Pas de squelette ni de vue dédiée pour une boîte vide ou la déconnexion | Une zone vide peut sembler être un défaut de l’application | États illustrés avec explication et action de retour/reprise |
| Thème réparti entre QPalette, styles locaux et HTML | Risque de contrastes ou de fonds incohérents entre composants | QSS unique et tokens utilisés aussi par le lecteur riche et les delegates peints |
| Raccourcis et capacité de navigation peu découvrables | Les utilisateurs rapides doivent mémoriser sans aide | Palette Ctrl+K, indices contextuels, onglet Raccourcis et J/K limités au focus de liste |
| Bouton de poursuite du certificat visuellement comparable aux autres actions | Le défaut clavier sûr peut manquer de priorité visuelle | Annuler est aussi l’action visuellement principale ; poursuivre est secondaire et explicitement risqué |

Il s’agit d’une analyse du code et des points d’entrée, pas d’un audit de production avec lecteur d’écran ni d’un test utilisateur de l’application existante.

## Étape 1 — trois variantes

Les sources d’inspiration sont des **principes** (densité, calme, vitesse), sans logos, textes, dessins d’icônes propriétaires ni reproduction d’identité visuelle. Les trois variantes partagent le même jeu de données, les mêmes actions et le même système de couleurs.

| Critère | 01 · Classique productif | 02 · Épurée | 03 · Rapide au clavier |
| --- | --- | --- | --- |
| Organisation | Dossiers, liste dense, lecture ; compte dans un sélecteur | Comptes exposés, avatars, liste plus espacée, lecture avec marges accrues | Rail de comptes par initiales, navigation compacte, liste courte, accès Commandes mis en avant |
| Ligne normale | 76 px | 102 px | 66 px |
| Points forts | Repères immédiats, scan de nombreux mails, transition familière | Hiérarchie apaisée, meilleure séparation, identification visuelle des échanges | Davantage de messages visibles, gestes réduits, palette filtrable et raccourcis contextuels |
| Points faibles | Plus d’information simultanée ; lisibilité à surveiller sur très petit écran | Moins de messages à l’écran ; la navigation des dossiers peut défiler | Demande un apprentissage ; initiales moins explicites ; éviter de masquer les actions souris |
| Public | Travail quotidien, volume moyen/élevé, utilisateurs attachés aux dossiers | Lecture longue, usage personnel, volume modéré | Utilisateurs réguliers, tri rapide et clavier |
| Navigation | Souris et raccourcis standards | Souris, Tab et recherche | Même accès souris, plus J/K/E/S quand la liste a le focus |
| Compromis | Équilibre information/rapidité | Équilibre calme/espace occupé | Équilibre vitesse/découvrabilité |

Aucune variante n’est intégrée ni déclarée retenue. La densité peut changer indépendamment de la variante : le choix doit porter sur l’organisation et le rythme, pas seulement la quantité d’espace.

## Couleurs et contrastes

Une seule couleur d’accent contrôle sélection, action principale, focus et liens de maquette. Les comptes sont distingués par nom et initiales, pas par trois nouvelles couleurs. Rouge et ambre sont réservés à la sémantique de risque, pas à la décoration.

| Token | Clair | Sombre |
| --- | --- | --- |
| Fond général | `#F3F5F8` | `#12161E` |
| Surface | `#FFFFFF` | `#1B212D` |
| Panneau secondaire | `#F8FAFC` | `#171D27` |
| Texte principal | `#172238` | `#EFF3FA` |
| Texte secondaire | `#56657A` | `#B0BDD0` |
| Bordure | `#D7DEE8` | `#3B475B` |
| Accent bleu initial | `#275BCC` | `#9EB8FF` |
| Accent prune alternatif | `#7545B0` | `#C8ADFA` |
| Accent sarcelle alternatif | `#007568` | `#81D9CB` |
| Avertissement : fond / texte | `#FFF5DF` / `#805100` | `#382C15` / `#FFD88F` |
| Danger : fond / texte | `#FFF0F0` / `#AE252F` | `#3D222C` / `#FFB0B8` |

La surface de sélection est un mélange de l’accent et de la surface (9 % en clair, 15 % en sombre). La couleur personnalisée est ajustée pour obtenir au moins 4,5:1 face à la surface. Le texte sur bouton principal est choisi entre sombre et blanc pour préserver ce seuil. Les tests couvrent les accents prédéfinis et des cas extrêmes personnalisés, sans prétendre certifier à eux seuls toute la conformité WCAG.

## Typographie, composants et espacement

- **Segoe UI** installée dans Windows. Aucun fichier de police Microsoft copié dans le livrable. Le mode capture charge la police depuis `Windows/Fonts` pour éviter une substitution en mode Qt offscreen.
- Base 13 px ; aperçu/secondaire environ 12 px ; métadonnées 11 px ; titres de section 24/26/21 px selon la variante ; dialogues 25 px ; objet du lecteur 23/25/22 px. Le delegate utilise des tailles en points équivalentes à l’échelle Qt Windows. Expéditeur toujours demi-gras ; objet non lu demi-gras ; aperçu et date secondaires. Les sujets longs sont élidés dans la liste et visibles entièrement dans le lecteur/infobulle.
- Grille d’espacement : **4, 8, 12, 16, 24, 32 px**. Champs/actions généralement 36–42 px ; comptes à deux lignes au moins 54 px. Marges du lecteur : 22 / 34 / 26 px selon la variante.
- Densité : Compacte retire 12 px à une ligne de liste ; Aérée ajoute 16 px. Soit 64/76/92 px pour V1, 90/102/118 px pour V2, 54/66/82 px pour V3. En compact V3, l’aperçu peut être omis de la ligne, mais reste disponible par infobulle et lecture.
- Coins : 10 px pour cartes/panneaux V1/V2, 6 px pour V3 ; contrôles 7 px ; badges 4–5 px. Pas d’effet de verre simulant une vraie API Mica : la maquette emploie des surfaces sobres et des bordures Fluent adaptées à Qt Widgets.
- Composants : Button/primary/secondary/nav, Card, Banner Info/Warning/Danger, avatars, badges, delegate Mail, lecteur sans ressources externes, cartes de fichiers, Skeleton, états vides, palette de commandes et dialogues communs.
- Icônes Lucide 18–20 px, trait cohérent. Source et licences dans `assets/SOURCE.txt` et `assets/LICENSE-LUCIDE.txt`. Quatre flèches QSS sont des variantes recolorées/retournées du SVG Lucide livré. Licence [Lucide](https://lucide.dev/license), conservant également les mentions Feather du dépôt.

Tout le QSS est dans `styles/theme.qss`, alimenté par `theme.py`. Les composants peints et le contenu riche emploient les mêmes tokens : il n’y a pas de deuxième palette indépendante dans une fenêtre.

## Interactions et accessibilité

Les contrôles Qt restent natifs pour leur rôle et leur focus. Les boutons à icône ont nom accessible et infobulle ; les champs ont des labels/identifiants accessibles ; l’élément de liste contient aussi un texte complet pour l’accessibilité, au-delà du dessin du delegate. Les indications de sécurité associent icône **et texte**, sans dépendre uniquement de la couleur. Les empreintes restent sélectionnables au clavier.

Tab et Maj+Tab parcourent les contrôles, y compris en sortie du corps de rédaction. Les flèches parcourent les mails et commandes ; Entrée cible la lecture ou exécute la commande ; Échap ferme un dialogue. Suppr est limité au focus de liste afin de ne pas archiver/supprimer un mail pendant une saisie. J/K/E/S sont activés seulement en variante 3 et dans la liste. Annuler est l’action par défaut des deux alertes et visuellement prioritaire.

Le changement de message utilise un fondu discret de **170 ms**. Il disparaît avec « Réduire les animations ». Les squelettes restent sobres et fixes ; le passage à un état de résultat est simulé par un timer local. Les captures figent les animations et réinitialisent les données à chaque scène, pour une comparaison fidèle.

Les contrastes et parcours clavier sont vérifiés automatiquement ; une validation manuelle avec NVDA et au zoom/DPI 125–200 % fera partie de la migration après choix. La maquette n’est pas annoncée comme un audit d’accessibilité certifié.

## Couverture des captures

Chaque variante comprend les mêmes 19 scènes en clair et sombre : principale ; unifiée ; rédaction ; ajout de compte chiffré ; compte en clair ; certificat ; apparence ; comptes ; sécurité ; raccourcis ; recherche et filtres ; boîte vide ; absence de connexion ; chargement ; palette ; images bloquées ; HTML ; fichier suspect ; confirmation du fichier suspect.

Les **114 PNG** sont de vrais rendus Qt, classés sous `screenshots/variante-N/clair|sombre/`. La galerie locale et `COMPARAISON.png` servent de point d’entrée. Les fenêtres principales sont exportées à 1440×940 pixels logiques à l’échelle de capture ; les dialogues gardent leurs dimensions propres et défilent si nécessaire. La zone cliente seule est capturée afin de ne pas mélanger style de maquette et décoration Windows réelle.

## Limites intentionnelles

Envoi, fichiers joints, synchronisation, confiance, identifiants et réglages de sécurité sont simulés. Pas de vrai sélecteur de fichiers, de navigateur OAuth, de notifications système ou de connexion. Les états ne persistent pas entre lancements. Le lecteur riche est un QTextBrowser sans ressources externes, **pas** une proposition de remplacement de la sécurité WebEngine existante. Le rendu Mica/WinUI natif, les tests NVDA et la migration vers le vrai modèle restent des étapes futures, conditionnées au choix de variante.
