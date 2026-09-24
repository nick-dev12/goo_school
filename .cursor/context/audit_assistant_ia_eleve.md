# Audit + feuille de route — Assistant IA Élève (compte élève seul)

**Date** : 2026-09-24  
**Statut** : **Elv0–Elv8 livrées** (2026-09-24).  
**Branche** : `cursor/assistant-eleve-elv8-a40c`  
**Workspace** : `C:\wamp64\www\goo_school`

---

## 1. Verdict en une phrase

Parcours **élève seul** complet : UI 14 écrans, WS persona `eleve`, **14 tools lecture** (navigation + scolaire + notif/historique), Wolof v1, cache **`aria-eleve-tools-v1`**, pas d’écriture vocale (Elv7). Mode parent sur espace enfant : **persona parent** inchangé.

---

## 13. Compteurs (post Elv8)

| Élément | Nombre |
|---------|--------|
| Widget Aria élève seul | **14** écrans |
| Tools exposés (`persona=eleve`) | **14** lecture |
| Tools écriture | **0** (Elv7 arbitrage) |
| Tests assistant élève | **~50** (scope, WS, UI, Elv2–8, recette) |
| Branches vagues | `cursor/assistant-eleve-elv0-a40c` … `elv8-a40c` |

---

## 14–22. Livraisons par vague

| Vague | Branche | Contenu clé | Tests |
|-------|---------|-------------|-------|
| Elv0 | `elv0-a40c` | WS `Eleve`, scope self-only, prompt | scope, WS |
| Elv1 | `elv1-a40c` | `assistant_vocal_eleve.html`, welcome bilingue | UI, WS |
| Elv2 | `elv2-a40c` | `assistant_pages_eleve`, nav tools | `test_assistant_eleve_tools_elv2` |
| Elv3 | `elv3-a40c` | Wolof STT/TTS/chips élève, session `aria_eleve_lang` | `test_assistant_eleve_language` |
| Elv4 | `elv4-a40c` | Wrappers scolaire parent (notes, bulletin, …) | `test_assistant_eleve_tools_elv4` |
| Elv5 | `elv5-a40c` | `get_notifications` (+ id), `get_mon_historique` | `test_assistant_eleve_tools_elv5` |
| Elv6 | `elv6-a40c` | Cache `aria-eleve-tools-v1`, G7 live tools | `test_assistant_eleve_g7` |
| Elv7 | `elv7-a40c` | **Skip** `marquer_notification_lue` (documenté) | `test_assistant_eleve_elv7` |
| Elv8 | `elv8-a40c` | Recette primaire/collège/supérieur + checklist §10 | `test_assistant_eleve_recette_elv8` |

---

## Checklist §10 (Elv8)

| # | Critère | Auto | Manuel |
|---|---------|------|--------|
| 1 | Bulle sur 14 pages | `test_assistant_eleve_recette_elv8` (UI) | Parcours navigateur |
| 2 | Notes/devoirs via tools | tools Elv4+ | Dialogue Gemini |
| 3 | Pas d’autre `eleve_id` | scope + recette | — |
| 4 | Wolof | `wolof_marker_score`, language tests | TTS/STT réel |
| 5 | Ouvrir devoirs | `ouvrir_page` recette | UI navigate |
| 6 | Pas tools directeur/CG | scan schema recette | — |
| 7 | Écriture confirmée | Elv7 : aucune | Carte N/A |

---

*Feuille de route Elv0–Elv8 complète — hors scope : paiement, scolarité parent, CG, shell.*
