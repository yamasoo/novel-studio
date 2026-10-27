# New-book interview

Goal: get the information needed to build the project with as few questions as possible. The author may say "skip", "you decide" or "just give me a few" at any time; then offer 2-3 options for them to choose from, or adopt the most reasonable default and mark it as a default.

Ask one round at a time, at most 4 questions per round. If there is a question tool (a multiple-choice interface), use it and mark the recommended option.

## Round 1: what is the story (required)

1. **Genre and one-line idea**: what do you want to write? (a sentence, a blurb or a few keywords are all fine)
2. **Target readers and platform**: who is it for, and where will it be published? (e.g. a web-serial site, Kindle serial, a Substack or personal blog, just for yourself)
3. **Length**: how long do you expect it to be? (short story under 10k words / novella 30k-80k / novel 80k-120k / long series 200k+ / not sure)
4. **Title**: is there a working title? (if not, use a keyword from the idea as the folder name)

Round 1 is enough to judge genre and scale. If the idea is too vague to squeeze out "who is the lead, what do they want, what blocks them", ask in round 2; do not fill it into a full setting on your own.

## Round 2: how to write it (required)

1. **Point of view**: first person, third person following the lead, or multiple viewpoints / omniscient? Past or present tense?
2. **Chapter length**: (web serials often run 1,500-3,000 words; if unsure, use 2,000-3,000)
3. **Style direction**: what feel do you like? You can name works or authors, or describe it (e.g. light and wry, hard-boiled and spare, fine-grained and lyrical, ornate and period).
4. **Writing sample**: is there a passage you wrote, or text you especially like, that you can paste? (the most useful input; fine if not)

## Round 3: rules and taboos (optional)

Ask only if the author is interested, or if it comes up naturally from rounds 1-2:

1. **Must have**: e.g. a romance line, a type of payoff, a certain ending.
2. **Must not have**: e.g. torturing the lead, a harem, a type of plot, certain words.
3. **Reader contract**: what do you want to promise readers? (e.g. a lead who is not a doormat, one-to-one romance, no abandoned ending)
4. **Working habits**: e.g. show you each chapter before moving on, whether to run consistency checks automatically, how detailed the reports should be.

## Handling a writing sample

When the author pastes a sample, handle it as novel-style's "B. Analyse a sample" does (run `scripts/style_metrics.py` for statistics first, then distil rules and pick example passages).

When the author has no sample and only describes a direction, follow novel-style's "A. Design from a description": write a first draft of the style, then attach a 120-200 word trial passage and ask them to judge "is this the feel?". If the author says it is not, ask what is off and revise.

Handle it yourself only when novel-style cannot be found: make the rules concrete enough to follow ("many short sentences" is not enough; write "in tense scenes use mostly sentences under 8 words, otherwise alternate lengths"), and put the sample in "example passages" with one line on what works.

## After the interview

Organise the results into first drafts of three files:
- `CLAUDE.md`: per references/claude-md-template.md
- `設定/故事核心.md`: fill in what is known, keep the template comments for what is not
- `設定/文風.md`: from the sample handling above

Then tell the author in plain words where the project was built, what has been filled in, what is still empty, and the suggested next step (usually finishing the story core with novel-outline, or building the lead's profile with novel-bible).
