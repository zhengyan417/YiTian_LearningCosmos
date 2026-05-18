Evaluate the citation coverage of the generation on a continuous scale from 0 to 1.

## Scoring Criteria
A generation has good citation coverage (Score: 1) if it:
- Attributes specific factual claims to identifiable sources (URLs, paper titles, organization names, publication dates)
- Provides enough source information that a reader could independently verify each non-trivial claim
- Does not present unverifiable claims as established facts
- Distinguishes between sourced facts and the writer's own synthesis or opinion

A generation has poor citation coverage (Score: 0) if it:
- Makes factual claims with no sources whatsoever
- Cites only vague authority ("studies show", "experts say") without naming a specific source
- Mixes cited and uncited claims with no signal which is which

Only apply this metric to outputs that purport to relay factual information drawn from external sources. Pure language transformations, creative writing, or code answers should receive a neutral score around 0.5 — they do not need citations to be valid.

## Example

### Input
What is the current state of EU AI Act enforcement?

### Output
The EU AI Act entered into force on 1 August 2024 and is being phased in over several years. According to the European Commission's official AI Act timeline (https://digital-strategy.ec.europa.eu/...), prohibitions on certain AI practices apply from 2 February 2025, while requirements for general-purpose AI models apply from 2 August 2025. Member states are also designating national competent authorities, as documented in the AI Office's progress report from March 2025.

### Evaluation
**Score**: 0.9

**Reasoning**: Each factual claim about phase-in dates and member-state authorities is attached to an identifiable source (the European Commission timeline, the AI Office progress report), letting a reader verify independently. Minor weakness: one URL is truncated rather than complete, slightly degrading verifiability.

## Instructions
Think step by step.
