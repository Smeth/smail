"""Trente messages fictifs. Aucun accès au carnet, au disque ou au réseau."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Account:
    name: str
    address: str
    initials: str
    secure: bool = True

ACCOUNTS = [Account('Atelier', 'camille@atelier.example', 'AT'),
            Account('Personnel', 'camille.martin@example.net', 'CM'),
            Account('Association', 'contact@association.example', 'AS', False)]
FOLDERS = [('inbox', 'Réception'), ('star', 'Favoris'), ('send', 'Envoyés'),
           ('file-pen-line', 'Brouillons'), ('archive', 'Archives'), ('shield-alert', 'Indésirables'),
           ('trash-2', 'Corbeille')]

@dataclass
class Attachment:
    name: str
    size: str
    suspect: bool = False

@dataclass
class Mail:
    id: int
    sender: str
    address: str
    subject: str
    preview: str
    time: str
    account: int
    unread: bool = False
    starred: bool = False
    folder: str = 'Réception'
    body: str = ''
    html: bool = False
    remote_images: bool = False
    attachments: list[Attachment] = field(default_factory=list)

def messages() -> list[Mail]:
    entries = [
        ('Élodie Bernard', 'Planche d’inspiration — la nouvelle collection', 'Les matières et les premières pistes pour notre rendez-vous de jeudi.', '10:42', 0),
        ('Maison Nacre', 'Votre sélection du mois de novembre', 'Trois idées pour un atelier plus doux et plus durable.', '10:18', 0),
        ('Service facturation', 'Facture en attente : vérification requise', 'Veuillez consulter le document joint pour régulariser votre dossier.', '09:56', 0),
        ('Thomas Leroy', 'Re: Validation du devis — espace accueil', 'C’est parfait pour nous. On peut confirmer la version B.', '09:35', 0),
        ('Amélie Roche', 'Les photos de notre repérage', 'J’ai regroupé les vues et les cotes. La lumière est superbe côté cour.', '09:12', 1),
        ('Studio Rivage', 'Point projet : lancement le 18 novembre', 'Un petit récapitulatif des prochaines étapes et des livrables attendus.', '08:48', 0),
        ('Nadia Kouamé', 'Réunion bénévoles — jeudi à 18 h', 'Nous avons une nouvelle salle pour accueillir les inscriptions.', '08:30', 2),
        ('Julien Mercier', 'Retour sur les propositions de signalétique', 'Merci pour les pistes. Quelques remarques sur les contrastes.', 'Hier', 0),
        ('Sophie Martin', 'Déjeuner dimanche ?', 'On se retrouve chez nous vers midi ? Je prépare quelque chose.', 'Hier', 1),
        ('Claire Dubois', 'Bon à tirer — dossier Horizon', 'Voici la dernière version, avec les corrections de ce matin.', 'Hier', 0),
        ('Hugo Petit', 'Votre commande de fournitures est prête', 'Le retrait est possible dès demain, entre 9 h et 18 h.', 'Hier', 0),
        ('Équipe du jardin', 'Atelier compost : les inscriptions sont ouvertes', 'Un rendez-vous pratique au jardin partagé samedi matin.', 'Hier', 2),
        ('Léa Moreau', 'Merci pour cette belle présentation', 'Le comité a beaucoup apprécié votre approche et les exemples.', 'Sam.', 0),
        ('Bibliothèque du quartier', 'Votre réservation est disponible', 'Le livre que vous attendiez est arrivé à l’accueil.', 'Sam.', 1),
        ('Paul Garnier', 'Budget prévisionnel — mise à jour', 'Le tableau intègre les derniers devis des prestataires.', 'Ven.', 0),
        ('Sarah Diallo', 'Une idée pour notre prochaine escapade', 'J’ai trouvé une petite maison près de la côte pour décembre.', 'Ven.', 1),
        ('Mathieu Colin', 'Planning des livraisons de la semaine', 'Le transporteur nous confirme une livraison mercredi matin.', 'Ven.', 0),
        ('Emma Laurent', 'Les retours de l’équipe sur la maquette', 'Une synthèse des commentaires, classés par écran.', 'Jeu.', 0),
        ('Cinéma Le Passage', 'Votre séance : mardi 10 novembre', 'Retrouvez votre réservation et les informations pratiques.', 'Jeu.', 1),
        ('Lucie Fontaine', 'Assemblée générale — ordre du jour', 'Merci de nous transmettre vos questions avant lundi.', 'Mer.', 2),
        ('Vincent Rousseau', 'Proposition de partenariat local', 'Nous aimerions vous présenter notre nouvelle initiative.', 'Mer.', 0),
        ('Anaïs Leclerc', 'Re: Les invitations pour vendredi', 'Je viens de les envoyer. Il reste deux confirmations à recevoir.', 'Mar.', 1),
        ('Atelier du papier', 'Échantillons reçus — merci !', 'Nous allons pouvoir finaliser les choix de grammage.', 'Mar.', 0),
        ('Gabriel Faure', 'Le compte rendu de notre atelier', 'Voici les décisions prises et les actions pour la semaine.', 'Lun.', 0),
        ('Camille Martin', 'Re: Validation du devis — espace accueil', 'Bonjour Thomas, voici la version corrigée du devis.', 'Lun.', 0),
        ('Camille Martin', 'Quelques idées pour le week-end', 'Je te joins les adresses dont nous avons parlé.', 'Lun.', 1),
        ('Camille Martin', 'Proposition de rendez-vous', 'Bonjour Élodie, seriez-vous disponible jeudi après-midi ?', 'Lun.', 0),
        ('Alice Perrin', 'Projet d’été — documents de clôture', 'Le dossier final et les éléments de restitution.', '28 oct.', 0),
        ('Offre exceptionnelle', 'Un cadeau vous attend aujourd’hui', 'Confirmez vos informations pour recevoir votre avantage.', '27 oct.', 1),
        ('Mairie — vie associative', 'Confirmation de réservation de la salle', 'La salle est réservée pour votre réunion du 19 novembre.', '26 oct.', 2),
    ]
    result = []
    for i, (sender, subject, preview, time, account) in enumerate(entries):
        folder = 'Envoyés' if i in (24, 25) else 'Brouillons' if i == 26 else 'Archives' if i == 27 else 'Indésirables' if i == 28 else 'Réception'
        result.append(Mail(i, sender, f'expediteur{i+1}@courrier.example', subject, preview, time, account,
                           unread=i in (0,1,2,4,5,6,9,12,19), starred=i in (0,3,9,14), folder=folder,
                           body=f'Bonjour Camille,\n\n{preview}\n\nNous avons pris le temps de réunir les éléments utiles pour avancer sereinement. N’hésitez pas à me faire part de vos remarques : nous pourrons les reprendre ensemble lors de notre prochain échange.\n\nMerci et très belle journée,\n{sender}'))
    result[0].remote_images = True
    result[0].body = 'Bonjour Camille,\n\nVoici les premières pistes pour la collection. J’ai privilégié les matières naturelles, les lignes simples et une palette lumineuse.\n\nTrois directions se dessinent :\n• une entrée chaleureuse, avec du chêne clair ;\n• des textiles durables, faciles à entretenir ;\n• une signalétique discrète et lisible.\n\nEst-ce que jeudi à 14 h vous conviendrait pour en discuter ?\n\nÀ très vite,\nÉlodie\nDirectrice de création · Atelier du Nord'
    result[0].attachments = [Attachment('Planche-inspiration.pdf', '2,4 Mo'), Attachment('Palette-matieres.png', '840 Ko')]
    result[1].html = True
    result[2].attachments = [Attachment('Facture_novembre.pdf.exe', '186 Ko', True)]
    for index, name, size in [(4,'Reperage-cour.zip','12,8 Mo'), (9,'Horizon-BAT.pdf','3,1 Mo'), (14,'Budget-2026.xlsx','248 Ko'), (17,'Retours-maquette.pdf','1,2 Mo'), (19,'Ordre-du-jour.pdf','124 Ko')]:
        result[index].attachments = [Attachment(name, size)]
    return result
