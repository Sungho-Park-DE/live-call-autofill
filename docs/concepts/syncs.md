# Syncs

Implemented in `app/syncs/flow.py`, one method per sync. `Decider` and `SpeechToText` are adapters (see `volatile.md`), not concepts.

```text
sync OpenDraftOnCallStart
  when   Request.startCall(caller)
  then   Call.start(caller) -> call
         Draft.open(call)

sync SpeechIntoCall
  when   SpeechToText.segment(call, text, final)        (live audio)
      or Request.say(call, text, final)                   (typed line or replayed demo call)
  then   Call.hear(call, text, final)

sync DecideOnFinalSegment
  when   Call.hear(call, text, final=true) -> version v
  then   Decider.decide(Call.transcript(call), questions(settings.FIELDS, Catalog.options())) -> answers

sync DecideOnPartialSegment
  when   Call.hear(call, text, final=false)
  where  settings.PARTIAL_DECIDE_SECS > 0
         and the last Decider request for this call started at least that long ago
  then   Decider.decide(Call.transcript(call), questions(...))        (same as DecideOnFinalSegment)
  else   one later decision is scheduled for when the interval has passed, so the newest partial is
         decided even if the caller stops talking; a final decides at once

         A decision is skipped when the transcript has the same words as the last answer that was used.

sync SuggestConfidentAnswer
  when   Decider.decide(...) -> answers                   for each (field, value, confidence)
  where  Call.version(call) = v                           (a newer final arrived — drop stale answers)
         and no newer answer was already used             (partial and final decisions can overlap)
         and confidence >= settings.threshold(field)
  then   Draft.suggest(call, field, value, confidence, source = decider name)

sync RetractUnsureAnswer
  when   Decider.decide(...) -> answers                   for each field below its threshold
  where  Call.version(call) = v
  then   Draft.retract(call, field)

sync ReportAdapterProblem
  when   Decider.decide(...) fails (DeciderError)
      or SpeechToText.stream(...) fails (SpeechError)
  then   the call and the draft stay as they are; the problem is shown to the person until the next
         successful decision (decider) or until the microphone is started again (speech)

sync WarmDeciderOnCallStart
  when   Request.startCall(caller)
  then   Decider.warm()                                   (optional; failures are ignored)

sync ListOpenQuestions                                   (computed on every view, nothing stored)
  when   Draft.view(call) has fields without a value      and the draft is not confirmed
  where  the intent is not settings.NO_QUOTE_INTENT
  then   for each such field: its settings question, and the value the decider heard below the threshold, if any;
         required fields first

sync HumanEdits
  when   Request.setField(call, field, value)   then  Draft.set(call, field, value)
  when   Request.releaseField(call, field)      then  Draft.release(call, field)

sync SuggestCompanions                                   (computed on every view, nothing stored)
  when   Draft.view(call) has zone and severity           and settings.COMPANIONS
  then   Accident.companions(call, car or "*", Catalog.zones()[zone].position, side, severity, exclude = {zone})
         each with lines = Catalog.lines(car, companion zone, side, severity)

sync HumanTogglesCompanion
  when   Request.toggleCompanion(call, zone, included)
  where  Draft not confirmed
  then   Accident.accept(call, zone) if included else Accident.decline(call, zone)

sync ConfirmCreatesQuote
  when   Request.confirm(call)
  then   Draft.confirm(call, settings.REQUIRED) -> fields
         Quote.create(call, fields, Catalog.lines(fields.car, fields.zone, fields.side, fields.severity)
                                    + lines of every included companion (SuggestCompanions), each part number once)
         Call.end(call)
```

The Accident table is built offline (`python -m datagen && python -m analysis` → `app/data/zones.json`); the app only reads it.

A question the decider gets: `{key, prompt, options: [{value, hint}]}`; it answers each key with one option value and a confidence in [0, 1], or not at all.
