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

sync SuggestConfidentAnswer
  when   Decider.decide(...) -> answers                   for each (field, value, confidence)
  where  Call.version(call) = v                           (no newer speech since — drop stale answers)
         and confidence >= settings.threshold(field)
  then   Draft.suggest(call, field, value, confidence, source = decider name)

sync RetractUnsureAnswer
  when   Decider.decide(...) -> answers                   for each field below its threshold
  where  Call.version(call) = v
  then   Draft.retract(call, field)

sync HumanEdits
  when   Request.setField(call, field, value)   then  Draft.set(call, field, value)
  when   Request.releaseField(call, field)      then  Draft.release(call, field)

sync ConfirmCreatesQuote
  when   Request.confirm(call)
  then   Draft.confirm(call, settings.REQUIRED) -> fields
         Quote.create(call, fields, Catalog.lines(fields.car, fields.zone, fields.side, fields.severity))
         Call.end(call)
```

A question the decider gets: `{key, prompt, options: [{value, hint}]}`; it answers each key with one option value and a confidence in [0, 1], or not at all.
