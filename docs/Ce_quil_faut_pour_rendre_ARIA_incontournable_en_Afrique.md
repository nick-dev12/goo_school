# Ce qu’il faut pour rendre ARIA incontournable en Afrique

Document de travail (14 septembre 2026).  
Audit marché d’origine, **corrigé pour rester complet sans noyer les utilisateurs**.

---

## Boussole produit

ARIA gère déjà le cœur pédagogique d’un établissement francophone (élèves, profs, EDT, notes, bulletins, présences, scolarité). Le marché africain se gagne sur le **moteur économique** : qui a payé, qui doit, combien on verse aux vacataires.

Le triangle concurrent (Novacole, PERIS, Logesco, KiboERP) est **heures → paie → recouvrement**. Pronote / Skolengo / Eduka restent pensés France : pas de Mobile Money, pas d’OHADA, pas de CEPE/BEPC.

**Correction de cap.** Complet pour l’école ≠ toutes les options à l’écran. Un ERP SYSCOHADA / HSA-HSE / 17 barèmes CNSS copie Logesco : puissant, illisible, abandonné. L’avantage ARIA, c’est Pronote-simple + cash africain.

### Trois questions, trois écrans

1. Qui me doit de l’argent ? → **Impayés**
2. Combien je paie ce mois ? → **Volume horaire / paie**
3. Combien il reste en caisse ? → **Caisse**

Tout le reste est automatique, replié, ou plus tard.

### Six règles d’ergonomie (non négociables)

1. **Un métier = un mot.** « À recouvrer », jamais « À jour » et « reste dû 197 000 » en même temps.
2. **Défauts intelligents.** Pays, devise, calendrier sept–juin, 9 mois, tolérance 15 jours : une fois à la création de l’école, plus jamais redemandés.
3. **L’écran vide explique la suite.** Volume horaire à 0 → « Publiez l’emploi du temps ». Classe sans barème → « Fixez les frais ».
4. **Progressive disclosure.** Moratoire, charges sociales, options de relance : visibles seulement quand on en a besoin.
5. **Parent : un montant, une date, un reçu.** Pas de tableau de comptable.
6. **Vocabulaire d’école.** Heures, caisse, impayés. Jamais HSA/HSE, compte 422, SYSCOHADA à l’écran directeur.

### Contraintes Afrique — nativement, pas en option visible

À traiter dans le moteur, **pas comme une page de 40 cases** :

- **Devises** : XOF (UEMOA), XAF (CEMAC), CDF (RDC). Un champ `devise_monnaie` existe : **une seule devise partout**, plus de mélange « FCFA » / XOF.
- **Calendrier** : septembre–juin, 9 mensualités, trimestres **ou** 6 séquences (Cameroun) = un type de période, pas un nouveau produit.
- **Privé vs public** : déjà distingué. Le public a cotisations / stats / bourses — plus tard, en une remise sur la fiche, pas un moteur.
- **OHADA** : réel pour l’expert-comptable. Pour le directeur : caisse. Export CSV plus tard, jamais un plan de comptes à l’écran.
- **Canal n°1** : SMS / WhatsApp / Wave–Orange Money–MTN, pas l’e-mail.

---

## État réel (après Vague 1 dans `main`)

Livré dans `main` (commit `8b7a5c54`) — l’audit d’origine les mettait encore en « manque » :

| Sujet | Audit d’origine | Réalité |
|---|---|---|
| Frais annexes | PR / pas dans main | Livré (migration 0219) |
| Impayés + relance 1 clic | Manque | Livré (0220) |
| Moratoire / fratrie calculée / reçu de paiement | Manque | Livré |
| Parent scolarité | Manque | Écran livré, **session à fiabiliser** |
| Volume horaire × tarif | Tarif jamais multiplié | Livré ; **0 si EDT non publié** |
| Statut « À jour » | Non vu | **Bug** : À jour alors que reste dû > 0 |

**On ne démarre pas Vague 2 tant que Vague 1 n’est pas claire.** Un directeur qui voit « À jour » avec 197 000 à payer n’installera jamais la caisse.

---

## 1. Professeurs & volume horaire

**Déjà dans ARIA**  
Fiches profs (`prix_volume_horaire`), affectations collège/lycée et primaire, EDT publié, dossier légal, heures semaine côté enseignant. **Vague 1** : EDT × semaines − absences × tarif → montant à payer.

**À garder, version simple**
- Planifié / absent / **à payer**. Un bouton « Payé ».
- Remplacement : sur une absence, « qui a fait le cours » — recalcule les heures.

**À ne pas construire tel quel**
- Service dû 18 h / 22 h paramétrable par pays.
- Ventilation HSA / HSE / heures poste (jargon Éducation nationale FR).
- Ratio élèves/prof, masse salariale prévisionnelle complexe → un chiffre sur le dashboard, pas un module.

**Pourquoi c’est décisif**  
Les privés paient souvent **à l’heure**. Sans ce montant, pas de budget, pas de paie, pas de contrôle.

---

## 2. Paie enseignants & personnel

**Déjà dans ARIA**  
Salaire de base, RIB, CNSS employé, tarif horaire. `Depense` côté plateforme ARIA ≠ compta de l’école.

**À garder, version simple**  
Liste du mois (reprise du volume horaire) + PDF + « Marquer payé ». Une retenue **%** optionnelle (charges), pas 17 législations.

**À ne pas construire tel quel**
- Bulletins conformes décret par décret (Sénégal 973, CNPS CI, IPRES…).
- Écritures 661 / 664 / 421 / 431 / 447.
- Acomptes compte SYSCOHADA 422, livre de paie, échéancier déclaratif 15 du mois.

**Pourquoi c’est décisif**  
Les profs partent si on paie « au feeling ». Un PDF lisible suffit pour commencer ; l’expert-comptable vient après.

---

## 3. Personnel administratif

**Déjà dans ARIA**  
Fonctions africaines (censeur, SG, intendant…), permissions, CRUD, espace personnel limité.

**À garder, version simple**
- Libellés métiers manquants si besoin (économe, chauffeur, gardien) = une valeur de plus, pas un module.
- Congés : demander / valider. Une liste.

**À couper**  
Organigramme, workflow avenants/rupture, postes budgétaires « 1 SG pour X élèves », pointage entrée/sortie (sauf demande client).

---

## 4. Comptabilité établissement = caisse, pas un cabinet OHADA

**Déjà dans ARIA**  
Scolarité élèves (inscription, mensualités, annexes, bilan). Type public/privé, devise. Pas de trésorerie école. `Depense` / `Budget` = facturation **ARIA → école**.

**À garder, version simple (Vague 2)**  
Un écran **Caisse du mois** :
- Entrées = paiements élèves (automatique)
- Sorties = date, motif, montant (salaire, loyer, électricité…)
- Solde

**À reporter / ne pas montrer au directeur**  
Plan de comptes SYSCOHADA, journal, grand-livre, plusieurs caisses (scolarité/cantine/internat), rapprochement Wave, clôture d’exercice. Export CSV expert-comptable = Vague 3+, fichier, pas écran.

---

## 5. Scolarité & recouvrement

**Déjà dans ARIA (Vague 1)**  
Inscription / mensualités, paiements partiels, barèmes par groupe, Mobile Money saisi à la main, annexes, impayés, relance, reçu, fratrie **calculée**, moratoire, écran parent.

**Clarté à corriger (Vague 1.5)**
- Statut unique : **À recouvrer / En retard / Soldé**.
- Paramètres : 4 champs visibles (classes, inscription, mensualité, annexes). Règles (tolérance, max partiels, jour de versement, avance…) **repliées** avec défauts.
- Classe sans barème → bandeau « Fixez les frais », pas des zéros silencieux.
- Relancer : dire si WhatsApp n’est pas configuré, plutôt que d’échouer dans le vide.

**À garder plus tard, un geste chacun**
- Référence Wave / Orange / MTN **à la saisie** (pas d’API au début).
- Bourse = une remise sur la fiche élève, pas un moteur.
- Blocage bulletin si impayé = **un interrupteur**, off par défaut.

**À ne pas empiler**  
Échéanciers 40/30/30 **en plus** des 9 mensualités **en plus** du moratoire **en plus** des bourses = 4 façons de se tromper. On garde : barème + annexes + **une** exception (moratoire).

---

## 6. Élèves

**Déjà dans ARIA**  
Dossier riche, checklist documents, inscriptions, certificats, sanctions, historique.

**À garder plus tard**  
Pièces scannées (le oui/non ne stocke pas le fichier). Matricule ministériel. Flag vulnérable pour stats inspection.

**Pas un produit séparé**  
Infirmerie, orientation, conseil de discipline consolidé : flags vides aujourd’hui. **Ne plus afficher un module tant qu’il n’a pas d’écran.**

---

## 7. Pédagogie

**Déjà dans ARIA**  
Notes, coefficients, rang, bulletins, examens internes, trimestres / semestres / LMD, devoirs.

**À garder, version simple**
- **6 séquences Cameroun** = un type de période, **mêmes** notes et bulletins.
- CEPE / BEPC / BAC = session d’examen existante + frais d’examen en annexe. Pas un sous-système.

**Plus tard / coupe**  
Canevas bulletin par pays (quand un pays l’exige). Conseil de classe, livret APC, cahier de textes quotidien — pas avant que cash + paie soient naturels.

---

## 8. Parents & communication

**Déjà dans ARIA**  
Compte parent, notes, bulletin, absences, FCM, annonces, PWA / app. WhatsApp câblé (OTP). Vague 1 : « vous devez X, échéance Y ».

**À fiabiliser tout de suite**  
Session sur `/parent/scolarite/`. Vue fratrie = le même écran, totaux des enfants.

**À ne pas recréer**  
Messagerie parent ↔ prof. WhatsApp **est** le chat. Digest SMS oui ; chat in-app non.

---

## 9. Vie scolaire

**Déjà dans ARIA**  
Présences, sanctions, convocations. Flags `module_cantine`, `module_transport`, `module_sante`, etc. **sans écran**.

**Correction**  
Cantine + transport **encaissent déjà** via les frais annexes. C’est suffisant pour le cash. Menus, circuits, pointage montée/descente = plus tard, seulement si un client le demande.

Absence enseignant + remplacement : un champ sur l’absence (Vague 2), pas un module vie scolaire.

Internat, CDI, infirmerie : Vague 3+, sauf demande client.

---

## 10. Administration direction

**Déjà dans ARIA**  
Années, classes, salles, rôles africains, assistant vocal, établissement mixte (primaire+collège+lycée).

**À garder plus tard**  
Jours fériés pays (calendrier, pas un module). Import Excel élèves/notes (un bouton). Paramètre pays = devise + type de période, pas 40 champs.

**Reporter**  
Multi-établissements / console groupe (ticket cher, mais après que **un** site soit naturel). Hors-ligne au-delà de la PWA : pas Vague 2.

---

## 11. Conformité Afrique

**À garder, un bloc profil**  
NINEA / RCCM / agrément : **une fois** sur la fiche établissement → imprimés sur les reçus. Export Excel effectifs + impayés pour l’inspection.

**Pas un module conformité**  
Conservation 10 ans, RGPD CEMAC, archivage annuel : règles techniques, pas des écrans.

---

## Priorités corrigées

Impact : **privé africain d’abord** (cash + paie), clarté avant nouveauté.

### Vague 1 — Cash & profs — LIVRÉE dans `main`

1. Volume horaire réel × tarif → montant à payer
2. Relances SMS / WhatsApp
3. Frais annexes collés au recouvrement
4. Reçu de chaque paiement
5. Réduction fratrie appliquée
6. Tableau impayés + relance 1 clic
7. Moratoire simple
8. Espace parent « vous devez X »

### Vague 1.5 — Clarté (avant toute nouveauté)

1. Statut unique : À recouvrer / En retard / Soldé
2. Session parent `/parent/scolarite/`
3. États vides utiles (EDT, barème, WhatsApp)
4. Paramètres scolarité : 4 champs visibles, le reste replié
5. Une seule devise partout (plus de FCFA / XOF mélangés)

### Vague 2 — L’école tient toute seule (4 écrans, pas 8 modules)

1. **Caisse du mois** : recettes auto / dépenses (date, motif, montant) / solde
2. **Paie du mois** : volume horaire → Marquer payé → PDF ; retenue % optionnelle
3. **Remplacement** : qui a fait le cours d’un prof absent
4. **Réf. Mobile Money** à la saisie (N° Wave / Orange / MTN) — pas d’API

Hors Vague 2 : SYSCOHADA, 17 barèmes CNSS, module cantine/bus, séquences Cameroun (sauf si ça tient en un type de période sans nouveau menu).

### Vague 3 — Seulement si Vague 2 est naturelle

Oui, plus tard :
- Type de période « séquence »
- Export Excel effectifs / impayés
- NINEA / RCCM sur le profil → reçus
- Congés personnel (demander / valider)
- Remise bourse sur la fiche élève

Non, sauf demande client :
- Plan de comptes SYSCOHADA à l’écran
- Multi-sites, internat, CDI, infirmerie
- Chat in-app parent–prof
- Moteur cantine / bus (menus, circuits)
- 17 législations sociales hardcodées

---

## Ce qu’ARIA a déjà de solide (ne pas re-spécifier)

- Boucle pédagogique : inscription → classe → EDT → appel → notes → rang → bulletin → parent notifié
- Profs spécialisés **et** polyvalents primaire
- Scolarité privé/public, barèmes, partiels, Vague 1 recouvrement
- Dossiers employés (contrat, CNSS, RIB) prêts à nourrir une paie simple
- Documents élèves, rôles africains, année sept–juin
- PWA + app Flutter + assistant vocal — avance que Logesco/Pronote n’ont pas
- WhatsApp déjà câblé (OTP) : même tuyau pour les relances

---

*Audit d’origine : code `school_admin/` + veille Novacole, PERIS, Logesco, KiboERP, Turboschool, Pronote, Skolengo, Eduka, SYSCOHADA / CNSS-IPRES-CNPS.  
Correctifs produit (ergonomie, Vague 1.5, caisse simple) intégrés le 14/09/2026 après revue de Vague 1 dans `main`.*
