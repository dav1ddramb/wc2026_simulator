# FIFA World Cup 2026 Simulator

Before the World Cup 2026 started, I really wanted to get my own **estimates of the win probabilities** based on the **overall team strength** and the **schedule**. This is a Monte Carlo simulator I wrote for it. Runs thousands of tournament simulations to estimate each team's probability of reaching the quarterfinals, semifinals, and winning the whole thing.

## How it works

`world_cup_sim.py` simulates the full tournament -- group stage, best third-place qualification, and knockout rounds (R32 through the Final) -- using a Poisson goal model. Each simulation produces a complete bracket and the results are saved as individual CSVs under `simulation_results/`.

`analyze_simulations.ipynb` aggregates the simulation outputs into win/SF/QF probabilities per team, for both methods, and compares them.

### Simulation methods

Two modes are supported (configurable via the `mode` parameter):

- **ELO-based** (`mode="elo"`): Uses FIFA ELO ratings to derive win probabilities via the standard formula `P(A) = 1 / (1 + 10^((ELO_B - ELO_A) / 400))`, then converts to expected goals with a Poisson distribution.
- **Odds-based** (`mode="odds"`): Derives team strength from bookmaker tournament winner odds. Since the probability of winning a multi-round tournament is not linear in match strength, a square-root transform is applied as a proxy: `strength = (1/odds)^0.5`. This avoids overstating the gap between favorites and underdogs, e.g.: Spain's odds (5.5) are ~half the Argentina's ones (10), that does not mean that in a head-to-head they're twice as likely to go through. The true gap is smaller, but gets amplified when it comes to tournament winning odds, due to a cumulative effect.

Both methods sample match scores from `Poisson(lambda)` where `lambda` is proportional to the team's relative strength, centered around a base of 1.25 expected goals per team.

### Using real results

The simulator supports **incremental simulation**: if a match in `schedule.csv` has a score filled in (e.g. `3-1`), that result is used as-is instead of being simulated. This lets you re-run the simulations after a stage is complete -- for example, locking in all group stage results and only simulating the playoffs.

## Data

- `teams.csv` -- 48 qualified teams with their group, ELO rating, and bookmaker odds to win the tournament.
- `schedule.csv` -- Full match schedule (104 matches). The `score` column can be filled in progressively as the tournament unfolds.

## Running

```bash
pip install pandas numpy
python world_cup_sim.py
```

By default this runs 10,000 simulations for each mode (`elo` and `odds`). Results are saved to `simulation_results/{mode}/`. Then open `analyze_simulations.ipynb` to aggregate and compare.

## Predictions overview

Based on 10,000 simulations per method (pre-tournament, no real results locked in):

| Team | Win % (ELO) | Win % (Odds) | SF % (avg) | Win % (avg) | Win % (SF/4) |
|------|-------------|--------------|------------|-------------|--------------|
| Spain | 41.6% | 22.6% | 63.2% | 32.1% | **15.8%** |
| France | 13.1% | 20.6% | 52.2% | 16.8% | **13.0%** |
| Argentina | 24.4% | 9.3% | 48.0% | 16.8% | **12.0%** |
| England | 6.1% | 14.5% | 40.9% | 10.3% | **10.2%** |
| Portugal | 2.9% | 12.6% | 31.3% | 7.7% | **7.8%** |
| Brazil | 2.7% | 8.1% | 27.6% | 5.4% | **6.9%** |
| Germany | 0.9% | 4.4% | 18.4% | 2.6% | **4.6%** |
| Netherlands | 1.5% | 2.7% | 18.2% | 2.1% | **4.5%** |

- **SF % (avg)** and **Win % (avg)**: averages of the ELO and odds models.
- **Win % (SF/4)**: `sf_prob_avg / 4` -- an alternative win probability estimate that takes the average probability of reaching the semifinals and divides by 4, assuming that once a team reaches the SF it's roughly a toss-up from there. This smooths out noise in the direct win simulations and produces results remarkably close to [Opta's supercomputer predictions](https://theanalyst.com/articles/who-will-win-2026-fifa-world-cup-predictions-opta-supercomputer).

The ELO model heavily favors Spain (due to their dominant rating of 2157, far above the field, and easy group/draw) while the odds model distributes probability more evenly among the top 6.

Some other insights:
- Spain	(72%), France (68%), Argentina (66%), England (63%) and Portugal (56%) all have a >50% chance to reach the QFs
- When rounded to whole %, only 11 teams have at least 1% chance of winning the cup: the TOP-8 above + Colombia	(1.45%), Norway	(0.89%) and Belgium (0.7%)
- Some conventional dark-horses are not so likely to win: Turkey (0.3%), Croatia (0.3%), Morocco (0.1%), Senegal (0.07%)
- Belgium is good up until a certain point: 40% chance to get to the QFs but only 10% to the SFs
