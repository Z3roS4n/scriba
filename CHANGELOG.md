# Changelog

Everything that changed in Scriba, newest first.
In italiano: [CHANGELOG.it.md](CHANGELOG.it.md).

Each entry is split into three sections, and the highest one present decides
the version bump: **Breaking changes** (major), **New features** (minor),
**Fixes** (patch). A section with nothing in it is left out.

## 0.6.3 — 9 August 2026

### Fixes

- **Scriba can finally carry a font of its own.** Three things prevented it,
  and none of them failed loudly: the pages' CSP disallowed fonts even local
  ones, the build copied six files by name and so would never have brought a
  folder along, and the files were not there. The result would have been an
  app starting in the fallback typeface and looking fine. Montserrat now
  travels inside the installer with its SIL OFL licence, and the build **stops**
  if a font or image declared in a stylesheet does not make it into the
  package. Nothing looks different yet: the typeface comes into use with the
  new design. ([#81](https://github.com/Z3roS4n/scriba/issues/81))

## 0.6.2 — 9 August 2026

### Fixes

- **The working note is visible during the call.** It was only mounted in
  branches of the panel that a recording never reaches: the feature existed,
  kept itself up to date, and could not be looked at exactly when it is meant
  to be used. It even carried a waiting message written for that moment — "The
  first one arrives after the first ten minutes of the call" — that nobody
  could ever have read. ([#70](https://github.com/Z3roS4n/scriba/issues/70))
- **Task priority no longer disappears.** You typed it by hand, and anything
  other than `bassa`, `media`, `alta` or `critica` — a capital letter was
  enough — made the write fail: the field went back to what it was, saying
  nothing. Now the four values are chosen, the core rejects anything else and
  explains what is allowed, and a save that fails says so where you pressed,
  keeping what you typed. This applies to all four fields, not just priority.
  ([#71](https://github.com/Z3roS4n/scriba/issues/71))
- **The analysis cost is written in dollars, because dollars is what it is.**
  The panel appended a `€` without converting anything: a number wrong by a
  little and always in the same direction, which is the kind you never catch
  by re-reading. ([#72](https://github.com/Z3roS4n/scriba/issues/72))
- **If the microphone you picked is gone, Scriba says so.** When the device
  chosen in settings has been unplugged, recording falls back to the default
  one: the core had always reported this and the interface was not listening.
  A notice now names the device actually recording.
  ([#73](https://github.com/Z3roS4n/scriba/issues/73))
- **With the archive or the review open the window can still be controlled.**
  Minimise, maximise and close disappeared: in a frameless window that bar is
  the frame, and only Alt+F4 was left. Notices went with them — and those do
  not talk about the call you are looking at but about the core failing to
  start or the model failing to load, so one arriving while a plane was open
  was seen by nobody. ([#74](https://github.com/Z3roS4n/scriba/issues/74))

## 0.6.1 — 8 August 2026

### Fixes

- **The overlay no longer shows up in screen sharing.** Sharing your screen
  during a call put the strip — with the live transcript of what was being
  said — in front of everyone in the meeting. A comment in the code promised
  the opposite, but the call that would have made it true had never been
  written. The strip is now excluded from capture, including Scriba's own
  screenshots, where you want the slide underneath and not your transcript on
  top. ([#69](https://github.com/Z3roS4n/scriba/issues/69))

## 0.6.0 — 7 August 2026

### New features

- **The analysis comes out in the language of the call.** Summary, key points,
  tasks and the working note follow the language chosen under Settings →
  Transcription: an English meeting produces an English summary, with English
  section headings. It used to always come out in Italian, and the model was
  told the transcript was Italian even when it was not — a false statement
  about what it had in front of it.
  ([#61](https://github.com/Z3roS4n/scriba/issues/61))

### Fixes

- **The language you pick in settings now actually applies.** Only "Redo the
  transcription" read it: recording always started in Italian, so every call
  showed as Italian in the archive and in exports even when it was not. Calls
  recorded before this stay marked "it", because that is how they were
  recorded. ([#61](https://github.com/Z3roS4n/scriba/issues/61))

## 0.5.1 — 7 August 2026

### Fixes

- **Sentences your microphone picked up from the speaker no longer end up in
  the summary as yours.** Your microphone always catches some of what comes out
  of your headphones, even at low volume, and those sentences were attributed
  to you: the summary then had the wrong person saying things. Measured on six
  recorded calls, **one microphone line in three** was a repeat of the other
  side — 352 lines in all. They are now recognised and left out of the summary,
  the working notes and every export.

  The setting under Settings → Transcription was never the problem: the rule is
  accurate — on the same recordings it flags 34.5% of lines against what the
  speaker had just said and 0.2% against what it said ten minutes earlier,
  where no echo can exist. What failed was the timing. A sentence from the
  other side only entered the filter once it had finished, and the echo on the
  microphone finishes well before that, so the filter was comparing against
  something not yet said. It now takes the running hypothesis too, and
  re-checks everything once the call ends.

  Those lines are **not deleted**: the transcript shows a "N lines picked up
  from the speaker" control at the top, and opening it shows them faded and
  labelled as picked up rather than as your own words. One line in three is too
  much to throw away without leaving anything to check.

  This applies to calls recorded from now on. Existing calls are untouched: the
  echo lines in them are real, and nothing goes back to reconsider them.
  ([#59](https://github.com/Z3roS4n/scriba/issues/59))

The installer is still unsigned: Windows shows a SmartScreen warning, and with
Smart App Control on it is refused outright.

## 0.5.0 — 7 August 2026

First published release. The project had been going for a while: this entry
covers what changed recently, not its whole history.

Scriba records work calls, transcribes them as you speak, and turns them into
a summary, key points and tasks. Transcription always runs locally; analysis
does too if you choose it.

### New features

- **Proper nouns can be corrected.** A name the model does not know is guessed
  again for every sentence, and differently each time: in one call "Clotilde"
  came out as *Tilde*, *Cotilde* and *Protile*. Settings → Transcription →
  Proper nouns takes the names that matter, one per line; clients from the
  address book are included on their own. The original text is kept, so every
  correction can be checked. ([#42](https://github.com/Z3roS4n/scriba/issues/42))
- **"Redo the transcription", with the language pinned.** Live transcription
  uses the faster model, which is also the only one whose language **cannot**
  be set: it infers it from the audio and occasionally gets it wrong — those
  are the sentences that appear in Spanish inside an Italian call. Once the
  call is over the pass runs again with Canary, which does accept the language
  (5.3% WER against 6.8% on Italian FLEURS, measured on the same machine).
  Needs a ~1 GB model from Settings → Local models.
  ([#41](https://github.com/Z3roS4n/scriba/issues/41))
- **The work note written during a call is visible.** It was being generated
  and stored, and nothing showed it — from the outside that is
  indistinguishable from a feature that does nothing. It now sits beside the
  transcript and updates while the meeting runs. The interval is selectable
  (5 / 10 / 15 minutes): it was fixed at ten and stated nowhere, so a shorter
  call produced none at all. ([#47](https://github.com/Z3roS4n/scriba/issues/47))
- **You can see which build you are running.** Settings → Data and privacy,
  with the commit beside it: between two builds of the same version that is the
  only thing telling them apart.
  ([#48](https://github.com/Z3roS4n/scriba/issues/48))

### Fixes

- **Whole sentences are no longer lost.** When a sentence failed to close, the
  next one took its place: the first disappeared and the second inherited its
  timestamp. It was not the model mishearing — it was text transcribed
  correctly and lost afterwards.
  ([#40](https://github.com/Z3roS4n/scriba/issues/40))
- **The other side's audio follows the call clock.** The system delivers
  nothing while no application is playing audio, and those silences were
  missing from the saved file: on one measured call twenty-four minutes were
  gone, and every minute of the transcript pointed somewhere else inside the
  file. The silence is now written. **It costs space**: an hour where the
  others speak for twenty minutes goes from ~37 MB to ~115 MB on that track.
  ([#45](https://github.com/Z3roS4n/scriba/issues/45))
- The packaged build did not report the commit it came from.
  ([#52](https://github.com/Z3roS4n/scriba/pull/52))

### Worth knowing before you install

- **The installer is not signed.** Windows will show the SmartScreen warning
  the first time you open it.
- **Calls recorded before this version cannot have the other side's track
  redone.** That file does not contain what would be needed to realign it, and
  no calculation invents it: the pass notices and gives up on that track,
  saying so, rather than rewriting every line with another line's text. Your
  own voice is redone normally.
- **Windows only.** No macOS or Linux support.
- **The Notion export and the remote PostgreSQL database have never been tried
  against a real service.** The logic is covered by tests with simulated
  calls; until those run against a real server, treat both integrations as
  unverified.
