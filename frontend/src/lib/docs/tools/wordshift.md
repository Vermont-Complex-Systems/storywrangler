# Wordshift

Wordshift decomposes the difference in average word score (sentiment, frequency, or any per-word signal) between two text collections into word-level contributions — which words drove the change, through increased or decreased usage, and whether they pulled the score up or down.

The reference implementation is the [wordshift](https://pypi.org/project/wordshift/) Python package, usable directly in scripts and notebooks. Install it:

```bash
pip install wordshift
```

Give it two `{word: frequency}` maps and a bundled labMT lexicon; it returns each word's signed contribution to the change in average sentiment, plus the component sums a shift graph needs:

```python
import wordshift

# type2freq_1, type2freq_2: {word: frequency} maps, e.g. two days of ranked
# n-grams from GET /storywrangler/top-ngrams
result = wordshift.weighted_avg_shift(
    type2freq_1, type2freq_2,
    lexicon="labMT_English",   # bundled labMT happiness lexicon
    top_n=50,                  # cap the returned per-word entries
)

result["entries"][:5]          # the words that drove the sentiment change
```

On the platform you do not have to fetch and feed the two systems yourself. `GET /storywrangler/wordshift` (or `wiki.wordshift(...)` in the SDK) resolves the dataset, loads both date-or-entity systems, and runs the shift server-side, the same way `/rtd` does for divergence.

The core math lives in [wordshift-core](https://github.com/Vermont-Complex-Systems/wordshift-core), a Rust crate, mirroring the [allotaxonometer](/tools/allotaxonometer)'s `allotaxonometer-core`.
