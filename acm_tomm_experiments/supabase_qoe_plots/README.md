# Subjective QoE experiment — figures for the ACM TOMM revision

These figures answer the reviewer request to run a **subjective experiment** and
map it onto the paper's **objective QoE model** (Q_video, Q_Int, QoE ∈ [0,1];
`paper/5-experiments_results.tex`). Section 5 currently notes that
*"MOS-calibrated weights are left for future work"* — this study supplies the
missing human-perception validation.

## The experiment
Source: `../supabase_responses_acm_tomm_subjective_qoe_rows.csv`

- **20 participants**, **295 trials** (~19–20 per game × bandwidth cell — full grid).
- **3 games** (Fortnite, Forza, Kombat) × **5 bandwidths** (2/4/6/8/10 Mbit/s).
- Each trial shows a **real** (original encode) and a **synth** (RIFE
  frame-interpolated) clip of the same condition, in randomized A/B order.
- Participants give a **1–5 MOS** to each clip and answer **"which is real?"**
  (Video A / Video B / Both / None) → discrimination / Turing-style test.

Regenerate:
- Subjective-only figures: `python3 generate_qoe_subjective_plots.py`
- Objective+subjective overlays: `python3 generate_objective_subjective_overlay.py`

Both output `.pdf` (for the paper) and `.png` (preview), 300 dpi.

## Headline numbers (cite in the rebuttal)
- Mean MOS **real = 3.43**, **synth = 3.27**, gap **−0.16** on the 1–5 scale
  (**≈ 4 %** of the scale range). Statistically significant (paired *t* = −4.26,
  *p* < 0.001) but **small in magnitude — consistent with the objective model's
  "bounded within 5–10 %" real-vs-synth deviation.**
- Real/synth **discrimination accuracy = 37.6 %** (111/295), significantly
  **below the 50 % chance line** (binomial *p* < 0.001): participants **cannot
  reliably tell the synthetic clip from the real one**, and in fact often pick the
  interpolated clip as "real."
- Objective↔subjective correlation: **LPIPS r = −0.82** (best), **SSIM r = 0.77**,
  **VMAF r = 0.76**, **PSNR r = 0.02** (none). The perceptual metrics that drive
  the QoE model track human opinion; PSNR does not — justifying the model's
  metric choices.

## Figures
| File | Shows | Reviewer takeaway |
|------|-------|-------------------|
| `fig1_mos_vs_bandwidth_overall` | MOS (rescaled to model's [0,1]) vs bandwidth, real vs synth, with fitted logarithmic QoE law | Subjective QoE follows the same monotonic log-shaped bandwidth curve as the objective model (fit R² ≈ 1.0); real–synth gap stays small and bounded |
| `fig1_mos_vs_bandwidth_per_game` | Same, 3-panel split by game | The trend and bounded gap hold per game |
| `fig1_mos_vs_bandwidth_{fortnite,forza,kombat}` | Same, one standalone figure per game | Drop-in per-game subplots for the paper |
| `fig2_objective_vs_subjective` | AvgVMAF vs MOS scatter + regression | Objective model output correlates with human perception (r = 0.76) |
| `fig2_objective_vs_subjective_all_metrics` | VMAF / PSNR / SSIM / LPIPS vs MOS | LPIPS & SSIM correlate strongly, PSNR not at all — validates the model's perceptual basis |
| `fig3_discrimination_accuracy` | % correct real/synth ID vs bandwidth, chance line + Wilson CI | At/below chance ⇒ synthetic is perceptually indistinguishable, so the small objective gap is imperceptible |
| `fig7_distinguishability` | **How often users correctly distinguished real from synth** — outcome breakdown (correct / fooled / couldn't tell) + per-participant accuracy vs chance (2-panel) | Only **37.6 %** of trials correctly identified the real clip; 13.9 % were fooled (chose the synthetic), 48.5 % couldn't tell; only **6/20** participants beat chance |
| `fig7a_outcome_breakdown` | Standalone left panel of fig7 (correct / fooled / couldn't tell) | Drop-in single-panel version |
| `fig7b_participant_accuracy` | Standalone right panel of fig7 (per-participant accuracy vs chance) | Drop-in single-panel version |
| `fig4_real_synth_mos_gap` | Mean (synth − real) MOS per condition | Deviation is small at every game × bandwidth point |
| `fig5_rating_distribution` | Diverging 1–5 rating distribution, real vs synth | Rating distributions overlap heavily |
| `fig6_which_real_composition` | A/B/Both/None answer mix per bandwidth | Large "Both"/"None" share ⇒ participants frequently can't tell them apart |
| `qoe_overlay_objective_subjective_{fortnite,forza,kombat}` | **Objective QoE model (bars) + subjective MOS (points), shared [0,1] axis** | The model's [0,1] output and human MOS rise together and stay close — the direct objective↔subjective mapping the reviewers asked for (**preferred for the paper**) |
| `qoe_overlay_objective_subjective_non_scaled_{fortnite,forza,kombat}` | Same, but subjective MOS on a native **1–5** right axis (true dual-axis) | Alternative for readers who prefer raw MOS; trend agreement is identical, but point↔bar vertical alignment is axis-dependent, so don't argue exact-value matching from it |

### On the objective+subjective overlay (the "right y-axis" request)
Both series are on **one shared [0,1] scale**: the objective QoE model already
outputs [0,1], and subjective MOS is rescaled to [0,1]. The figure shows the
objective QoE as grouped bars (colors/hatches matching the existing
`new_graphs/qoe_bandwidth_summary_*` figures) with the subjective MOS overlaid as
lines+markers (±95% CI). The right-hand axis **mirrors the same 0–1 scale** so the
subjective series can be read off the right — it is deliberately *not* a second,
different scale (a true dual-axis chart with two scales is misleading and easy to
manipulate; here both axes are identical by construction).

Objective QoE is recomputed exactly as `tools/generate_graphs.py`:
`QoE = 0.5·(AvgVMAF/100) + 0.5·Q_sync`, `Q_sync = 0.5·(Q_Vsmooth + Q_Csmooth)`,
reading `Q_Vsmooth`/`Q_Csmooth` from each condition's `srv_QoEMetrics.csv` under
`reference_vs_{real,synth}/`. (The overlay script re-implements the two smoothness
helpers locally to avoid `vmaf_scatter.py`'s `cv2` import.)

## Visual style (matches the paper figures)
Bars and lines use the same texture/line vocabulary as
`new_graphs/psnr_summary_*` (bars) and `new_graphs/delay_rt_bandwidth_summary_*`
(lines), so these figures sit next to the existing ones without a style clash:
- **Bar fills** — black edges + hatch textures (`""` / `//` / `xx` / `..`).
  Per-game bars reuse the paper's map (Fortnite none, Forza `//`, Kombat `xx`);
  categorical bars (fig6, fig7) get one distinct hatch per category. Hatching
  keeps the bars distinguishable in grayscale / CVD / print.
- **Lines** — series separated by marker **and** linestyle: **real = solid +
  circle**, **synth = dashed + square**; fitted log-law curves are **dotted**.
- (fig5's 1–5 rating stack keeps its sequential blue ramp — hatching 5 ordinal
  levels would fight the color encoding, so it is intentionally left un-hatched.)

## Notes / caveats
- The real–synth MOS gap is **statistically significant but small**; frame it as
  *bounded/imperceptible*, not *zero*. This matches the objective model's story.
- Discrimination being **below** chance is honest evidence of indistinguishability
  (not cherry-picked); report it as "≤ chance," not "participants prefer synth."
- Colors: real/synth use the CVD-safe Okabe-Ito blue/vermillion (validated); game
  colors match the existing paper figures and are always paired with a distinct
  marker/position for colorblind safety.
- The objective x-axis in fig2 uses per-condition `AvgVMAF/PSNR/SSIM/LPIPS` from
  `../processed_data/vmaf_metrics_{real,synth}.csv`. If you compute the final
  fused QoE ∈ [0,1] per condition, swap it in as the x-axis for the most direct
  "objective-QoE-vs-MOS" plot.
