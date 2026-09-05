# Klon-Befund workflowhooker — 2026-08-30

Ticket T-20260830-500233160. Read-only Messung zuerst, danach begrenzte Aktionen (siehe unten).
Alle Angaben nachgemessen, nicht vom Vorlauf-Worker-Bericht übernommen.

## 1. Remotes (gemessen)

```
origin      https://github.com/ellmos-ai/workflowhooker.git
provenance  https://github.com/ellmos-ai/workflowhooker-provenance.git
```

## 2. Branches vor Eingriff (git branch -vv, nach git fetch --all --prune)

| Branch | Tracking | Stand |
|---|---|---|
| `legacy/master-vorstufe-2026-08-01` | (kein Tracking) | `8864c39`, kein Ancestor von `provenance-master` |
| `main` | `origin/main` | in sync, `6d2b190` |
| `master` | `origin/master` | ahead 1 / behind 18 |
| `* provenance-master` | `provenance/master` | ahead 3 |
| `+ ticket/T-20260731-05-session-hygiene` | eigener Worktree `…/worktrees/workflowhooker-t20260731-05` | ahead 4 / behind 5 (rel. `provenance/master`) |

## 3. Die 3 unpushed Commits auf `provenance-master` (vor Push)

Alle drei von **Lukas Geiger** (`lukas@um-bruch.org`), keine Fremdcommits, keine Testcommits:

- `14dd84d` (2026-08-28) `feat: add durable lifecycle job receipts` — 14 Dateien, +2498/-163
- `78f85ae` (2026-08-29) `feat: add evidence-bound extractor consumer` — 12 Dateien, +1908/-34
- `3896720` (2026-08-30) `feat: add repo_aliases for workflowhooker-provenance` — 1 Datei (`ellmos-module.v2.json`), +4/-1

Diff gegen `provenance/master` per `grep -iE "api[_-]?key|token|secret|password|BEGIN (RSA|OPENSSH|PRIVATE)|ssh-rsa|AKIA"` geprüft:
**keine echten Zugangsdaten** — alle Treffer sind Doku/Code über die eingebaute Secret-Redaction-Funktion des Tools selbst, keine Werte.
`pytest -q` auf `provenance-master`: **240 passed** (44 s).

**Befund zum "harmlosen Testcommit eines früheren Workers":** in dieser Messung **nicht bestätigt**. Die 3 unpushed Commits sind ausschließlich reguläre Feature-Commits mit Tests, keiner trägt einen erkennbaren Test-/Probe-Charakter. `git reflog` und `git log --all` um die Spitze zeigen keinen isolierten Fremd-/Testcommit. Entweder war der Vorbericht ungenau, oder der Commit wurde zwischen dem Vorlauf und diesem Lauf bereits entfernt/ersetzt (auf `provenance-master` liegen inzwischen neuere Commits vom 2026-08-30, nach dem vermuteten Berichtszeitpunkt).

## 4. Fremde TODO.md-Änderung (vor Eingriff)

```diff
+- [ ] Diagnose the live Codex `hook-run Stop` output contract: on ASUS-GEI the
+  command exited 0 but emitted no `hookSpecificOutput` on 2026-08-29 and again
+  on 2026-08-30. Treat this as unproven runtime effect until a deterministic
+  provider/event fixture yields non-empty closing evidence.
```

Ein einzelner neuer TODO-Punkt im bestehenden Format (Checkbox-Stil), dokumentiert einen beobachteten Befund, keine Geheimnisse, keine Kollision mit eigener Arbeit. **Sinnvoll** nach Hausregel → zertifiziert und in eigenem Commit `bd093f8` (`chore: certify foreign TODO.md addition …`) übernommen.

## 5. Einordnung: welches Remote ist kanonisch?

**Kanonisch für Weiterentwicklung: `provenance` = `ellmos-ai/workflowhooker-provenance`.** Belegt aus zwei Quellen:

1. **`CONTRIBUTING.md` im Repo selbst** (Commit `6d2b190`, Autor Lukas Geiger, 2026-08-01, "docs: document the public/provenance split"):
   > „`ellmos-ai/workflowhooker-provenance` — private twin — full development history … Development and the complete history live in the private twin. What reaches `main` here [= origin/workflowhooker] are curated, tested changes, brought over by squash or cherry-pick. … A local clone that tracks a `master` branch belongs to the private twin, not to this repository."
   Das erklärt zugleich, warum der lokale `master` (Tracking `origin/master`) hier ein Fremdkörper ist: laut eigener Doku des Repos gehört ein `master`-Tracking-Branch zum privaten Zwilling (`provenance`), nicht zu `origin`. `origin` arbeitet mit `main`, nicht `master`.
2. **OneDrive-Modul-Pointer** `.AI/.MODULES/.CONTROL/flowhooker/PLAN_D_POINTER.md`: nennt `origin/master` als „aktiven Branch" — das ist **veraltet** (Stand 2026-07-23/27, vor dem Public/Provenance-Split vom 2026-08-01) und widerspricht der neueren, im Repo selbst dokumentierten Konvention. Die aktuellere Quelle (`CONTRIBUTING.md`, jünger, vom Repo-Owner selbst geschrieben) hat Vorrang.

`ellmos-module.v2.json` (OneDrive **und** Repo-Kopie) trägt `source_of_truth.repository = https://github.com/ellmos-ai/workflowhooker` mit `repo_aliases: ["ellmos-ai/workflowhooker-provenance"]`. Das widerspricht Punkt 1 NICHT: „source of truth" meint hier die öffentliche Distributionsadresse (der kuratierte Lesestand), nicht den Ort, an dem entwickelt/gepusht wird. Beide Aussagen sind konsistent, wenn man sie als getrennte Rollen liest (Entwicklung vs. öffentliche Referenz).

## 6. Durchgeführte Aktionen (nur belegte, sichere Schritte)

1. `git fetch --all --prune` (read-only).
2. Fremde `TODO.md`-Änderung geprüft, sinnvoll befunden, **eigener Commit** `bd093f8`.
3. Die 3 unpushed Commits **gepusht**: `git push provenance provenance-master:master` → `62e74fc..bd093f8 provenance-master -> master` (normaler, nicht-forcierter Push, Fast-Forward auf dem Remote). Voraussetzungen erfüllt: kanonisches Ziel belegt (Abschnitt 5), Inhalt sinnvoll + testgrün (240 passed), keine Credentials.
4. `master` (18 hinter `origin/master`) NUR mit `git merge --ff-only origin/master` versucht → **schlägt fehl** ("Diverging branches", 1 vs. 18 unterschiedliche Commits). Nach Vorgabe **nicht gemergt**, keine weitere Aktion — liegt unverändert (`master` @ `17acec3`, `origin/master` @ neuerem Stand mit 18 Commits Unterschied in beide Richtungen).

## 7. Bewusst NICHT angefasst

- **Testcommit-Frage:** siehe Abschnitt 3 — es gibt aktuell keinen zu entfernenden/revertierenden Commit dieser Art auf `provenance-master`. Kein Revert nötig.
- **`master`-Divergenz zu `origin/master`** (1 vs. 18): kein Fast-Forward möglich, kein Merge/Rebase versucht (Historie-Umschreiben war ausdrücklich untersagt). Liegt offen.
- **`legacy/master-vorstufe-2026-08-01`**: unverändert gelassen (kein Ancestor von `provenance-master`, alter Wip-Stand vor der Klon-Sanierung 2026-08-01 — reine Historie, keine Aktion angefordert).
- **`ticket/T-20260731-05-session-hygiene`** (eigener Worktree, ahead 4 von `provenance-master`, 4 weitere `feat:`-Commits): außerhalb des Auftragsumfangs, nicht angerührt.
- **Kein Force-Push, kein Rebase, kein Branch gelöscht, keine Sichtbarkeit geändert.**

## 8. Zusatzbefund aus dem Ticket: Sichtbarkeits-Widerspruch (nur Analyse, keine Aktion)

Frage: Katalog führt `WORKFLOWHOOKER` als `visibility: private`, das Modul ist Mitglied eines freigegebenen Bundle-Rezepts, sein „einziges Repo" heißt `workflowhooker-provenance` — welche Angabe stimmt?

**Befund:** Die Prämisse „einziges Repo = `workflowhooker-provenance`" ist **unvollständig**. Es gibt zwei Repos (Abschnitt 1/5): `ellmos-ai/workflowhooker` (kuratiert, laut `CONTRIBUTING.md` die **öffentliche** Distributionsseite) und `ellmos-ai/workflowhooker-provenance` (privater Entwicklungszwilling, volle Historie). Der Katalog kennt/registriert offenbar nur den privaten Zwilling und schließt daraus pauschal `visibility: private` für das ganze Modul — das übersieht die öffentliche Gegenseite.

**Empfehlung (keine Ausführung, Nutzerentscheid):** `visibility` im Katalog nicht als einzelnes Feld, sondern gesplittet abbilden — z. B. `public` für `ellmos-ai/workflowhooker` (passt zur Bundle-Freigabe) und `private` weiterhin für `ellmos-ai/workflowhooker-provenance` (passt zu „privater Zwilling, volle Historie" aus `CONTRIBUTING.md`). Ein pauschales `private` für das Gesamtmodul widerspricht der dokumentierten Konstruktion und der Bundle-Freigabe. Zusätzlich: `PLAN_D_POINTER.md` im OneDrive-Modulordner ist mit „aktiver Branch: master / Repo: workflowhooker" veraltet (vor dem 2026-08-01-Split) und sollte bei Gelegenheit auf den Public/Provenance-Split + `main`-statt-`master`-Konvention aktualisiert werden — nicht in diesem Lauf ausgeführt (außerhalb des read-only/sicheren Scopes dieses Auftrags).

## 9. Endzustand (nachgemessen)

```
* provenance-master (HEAD)  bd093f8  up to date with 'provenance/master'
  master                    17acec3  diverged from origin/master (1 vs 18)
  main                       6d2b190  in sync mit origin/main
  legacy/master-vorstufe…    8864c39  unverändert
  ticket/T-20260731-05…      aab6b2f  unverändert (eigener Worktree)
```
`git status --short` auf `provenance-master`: nur `LOCK.wfh-konsolidierung.txt` (wird nach diesem Lauf entfernt).
