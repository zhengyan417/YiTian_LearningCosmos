Evaluate the quality of code in the generation on a continuous scale from 0 to 1.

## Scoring Criteria
A generation has high code quality (Score: 1) if it:
- Produces code that correctly addresses the requested task
- Uses idiomatic constructs for the chosen language
- Handles obvious edge cases (empty inputs, type mismatches, boundary values) where the task implies them
- Names identifiers clearly and structures the code readably
- Avoids gratuitous complexity, dead branches, or unused imports

A generation has low code quality (Score: 0) if it:
- Returns code that does not run, or fails on the stated task
- Uses non-idiomatic patterns inappropriate for the language
- Misses obvious edge cases the task clearly implies
- Has unclear names, copy-paste duplication, or unmotivated dead code

When the task is to *explain* code rather than write it, evaluate the snippets embedded in the explanation against the same criteria. Sparse-but-correct illustrative examples are acceptable.

## Example

### Input
Write a Python function that flattens a nested list of arbitrary depth.

### Output
def flatten(items):
    out = []
    for it in items:
        if isinstance(it, list):
            out.extend(flatten(it))
        else:
            out.append(it)
    return out

### Evaluation
**Score**: 0.9

**Reasoning**: The function correctly handles arbitrary nesting via recursion, uses clear identifier names, and `extend` avoids per-element appending in the recursive case. Minor gap: it only handles `list` — a more thorough implementation might also support tuples or general iterables — but for the stated task this is acceptable.

## Instructions
Think step by step.
