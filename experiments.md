# Experiments log

All tests on the 30 labelled events in `events/`, compared with `manual_labels.csv`
(21 of 30 are Financials, so always answering Financials would score 70%).

## Week 5 (November 2026)

### Speed: models in parallel
| Setup | Time |
|---|---|
| Before: models one after another | about 10 s per event |
| Models in parallel, 4 events at a time | 30 events in 111 s (about 3.7 s per event) |
| One event on the webpage (via MCP) | about 10 s |

### Accuracy per model
| Model | Correct |
|---|---|
| claude | 90% |
| qwen | 87% |
| laya | 53% |
| laya_choice | 13% |
| vote (claude + qwen + laya) | 90% |

### laya_choice: can rewording fix it?
laya_choice answers Information Technology for almost every event.

| Version of the question | Correct | Most common answer |
|---|---|---|
| Current | 4/30 | Information Technology x26 |
| Reworded: ask about the victims, ignore the malware/tools | 3/30 | Information Technology x27 |
| Reworded, Information Technology removed as an option | 14/30 | Communication Services x12 |

Conclusion: rewording does not help; with IT removed it just picks the next tech-sounding sector.
(Week 3: dividing by laya's average answer distribution only reached 27%.) laya's choice mode cannot do this task.

### Agreement flag ("check by hand" when no model has more than half the votes)
| Models | Vote correct | Flagged | Mistakes not flagged |
|---|---|---|---|
| claude + qwen + laya + laya_choice | 27/30 | 13 | 0 |
| claude + qwen + laya (new default) | 27/30 | 1 | 2 |
| claude + qwen | 27/30 | 2 | 2 |
| qwen + laya (free setup) | 26/30 | 16 | 0 |
| qwen alone | 26/30 | 0 | 4 |

- laya_choice does not change the vote's accuracy; it only causes flags because it disagrees with nearly everything.
  Removed from the default models (still in the code).
- laya can only change the vote when Claude and Qwen disagree (2 of 30 events). It is kept: it never makes the vote worse,
  and in the free setup it flags every one of Qwen's mistakes.
- The 2 mistakes that are not flagged (Carbanak, Zeus Panda) are events where Claude and Qwen both answered
  Consumer Discretionary and the manual label is Financials: debatable (banking malware, but the victims are shoppers/bank customers).

### laya threshold
| Threshold | laya correct | laya "Not sector-specific" | Vote (claude + qwen + laya) | Free vote (qwen + laya) |
|---|---|---|---|---|
| 0.8 (kept) | 16/30 | 2 | 27/30, 1 flagged | 26/30, 16 flagged |
| 0.9 | 15/30 | 3 | 27/30, 1 flagged | 26/30, 17 flagged |
| 0.95 | 15/30 | 3 | 27/30, 1 flagged | 26/30, 17 flagged |
| 0.99 | 12/30 | 7 | 27/30, 1 flagged | 26/30, 20 flagged |

Conclusion: laya is overconfident (top score 0.96 or higher on 27 of 30 events, right or wrong), so a threshold
cannot separate good from bad answers. Higher thresholds only turn answers into "Not sector-specific".
