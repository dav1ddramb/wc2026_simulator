import pandas as pd
import numpy as np
import random
from datetime import datetime
import os

BASE_GOALS = 1.25


def load_data():
    teams_df = pd.read_csv("teams.csv")
    schedule_df = pd.read_csv("schedule.csv")

    teams = {}
    for _, row in teams_df.iterrows():
        teams[row["country"]] = {
            "group": row["group"],
            "elo": row["elo"],
            "win_odds": row["win_odds"],
        }

    group_matches = schedule_df[schedule_df["stage"] == "Group"].to_dict("records")
    knockout_template = schedule_df[schedule_df["stage"] != "Group"].to_dict("records")

    return teams, group_matches, knockout_template


def parse_score(score):
    if pd.isna(score) or str(score).strip() == "":
        return None
    parts = str(score).strip().split("-")
    return int(parts[0]), int(parts[1])


def simulate_match_score(team_a, team_b, teams, mode):
    if mode == "random":
        lambda_a = np.random.uniform(0, 2 * BASE_GOALS)
        lambda_b = np.random.uniform(0, 2 * BASE_GOALS)
        return int(np.random.poisson(lambda_a)), int(np.random.poisson(lambda_b))

    if mode == "odds":
        odds_a = teams[team_a]["win_odds"]
        odds_b = teams[team_b]["win_odds"]
        odds_based_prob_a = 1 / odds_a
        odds_based_prob_b = 1 / odds_b

        # Infer team strength from odds
        # logic: the probability of winning the whole tournament is not proportional to the team strength
        # since it ignores the multiplicative nature of the tournament and random factors, so use sqrt as proxy for non-linearity
        # e.g.: England (0.13) is twice as likely to win WC2026 as Germany (0.065), while the sqrt-s are 0.36 and 0.25 respectively,
        # which imply that England is ~44% stronger than Germany (0.36 / 0.25 = 1.44), or in other words
        # that'd have the edge in  0.36 / (0.36 + 0.25) = 0.6 percent (60%) of the matches
        inf_strength_a = odds_based_prob_a**0.5
        inf_strength_b = odds_based_prob_b**0.5
        lambda_a = BASE_GOALS * 2 * (inf_strength_a / (inf_strength_a + inf_strength_b))
        lambda_b = BASE_GOALS * 2 * (inf_strength_b / (inf_strength_a + inf_strength_b))
        return int(np.random.poisson(lambda_a)), int(np.random.poisson(lambda_b))

    # ELO-based Poisson Simulation
    if mode == "elo":
        elo_a = teams[team_a]["elo"]
        elo_b = teams[team_b]["elo"]
        win_prob_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
        win_prob_b = 1 / (1 + 10 ** ((elo_a - elo_b) / 400))
        lambda_a = BASE_GOALS * 2 * win_prob_a
        lambda_b = BASE_GOALS * 2 * win_prob_b
        return int(np.random.poisson(lambda_a)), int(np.random.poisson(lambda_b))

    raise ValueError(f"Invalid mode: {mode}")


def simulate_knockout_match(team_a, team_b, teams, mode):
    goals_a, goals_b = simulate_match_score(team_a, team_b, teams, mode)
    if goals_a != goals_b:
        winner = team_a if goals_a > goals_b else team_b
        return goals_a, goals_b, winner, ""

    regulation_a, regulation_b = goals_a, goals_b
    while True:
        et_a, et_b = simulate_match_score(team_a, team_b, teams, mode)
        if et_a != et_b:
            winner = team_a if et_a > et_b else team_b
            notes = f"Draw ({regulation_a}-{regulation_b}); winner decided in ET/Pen: {winner}"
            return regulation_a, regulation_b, winner, notes


def compute_group_standings(group_matches_results, teams):
    groups = {}
    for team_name, info in teams.items():
        g = info["group"]
        if g not in groups:
            groups[g] = {}
        groups[g][team_name] = {"pts": 0, "gf": 0, "ga": 0, "gd": 0, "elo": info["elo"]}

    for m in group_matches_results:
        home, away = m["home"], m["away"]
        hg, ag = m["home_goals"], m["away_goals"]
        g = teams[home]["group"]

        groups[g][home]["gf"] += hg
        groups[g][home]["ga"] += ag
        groups[g][away]["gf"] += ag
        groups[g][away]["ga"] += hg

        if hg > ag:
            groups[g][home]["pts"] += 3
        elif hg < ag:
            groups[g][away]["pts"] += 3
        else:
            groups[g][home]["pts"] += 1
            groups[g][away]["pts"] += 1

    for g in groups:
        for team_name in groups[g]:
            groups[g][team_name]["gd"] = (
                groups[g][team_name]["gf"] - groups[g][team_name]["ga"]
            )

    standings = {}
    for g, team_stats in groups.items():
        ranked = sorted(
            team_stats.items(),
            key=lambda x: (x[1]["pts"], x[1]["gd"], x[1]["gf"], x[1]["elo"]),
            reverse=True,
        )
        standings[g] = [(name, stats) for name, stats in ranked]

    return standings


def select_best_third_places(standings):
    thirds = []
    for g, ranked in standings.items():
        team_name, stats = ranked[2]
        thirds.append({"team": team_name, "group": g, **stats})

    thirds.sort(key=lambda x: (x["pts"], x["gd"], x["gf"], x["elo"]), reverse=True)
    return thirds[:8]


def assign_third_places_to_slots(qualified_thirds, knockout_template):
    slots = []
    for m in knockout_template:
        if m["stage"] == "R32" and str(m["away"]).startswith("THIRD_"):
            allowed_groups = list(m["away"].replace("THIRD_", ""))
            slots.append({"match_no": m["match_no"], "allowed": allowed_groups})

    qualified_groups = [t["group"] for t in qualified_thirds]
    team_by_group = {t["group"]: t["team"] for t in qualified_thirds}

    valid_assignments = []
    _find_assignments(slots, qualified_groups, team_by_group, 0, {}, valid_assignments)

    if not valid_assignments:
        raise ValueError("No valid third-place assignment found")

    chosen = random.choice(valid_assignments)
    return chosen


def _find_assignments(
    slots, available_groups, team_by_group, idx, current, results, max_results=100
):
    if idx == len(slots):
        results.append(dict(current))
        return
    if len(results) >= max_results:
        return

    slot = slots[idx]
    for g in slot["allowed"]:
        if g in available_groups:
            remaining = [x for x in available_groups if x != g]
            current[slot["match_no"]] = team_by_group[g]
            _find_assignments(
                slots, remaining, team_by_group, idx + 1, current, results, max_results
            )
            del current[slot["match_no"]]


def resolve_team_ref(ref, standings, third_place_assignment, bracket):
    ref = str(ref)

    # Group position reference: single letter + single digit (e.g., A1, L2)
    if len(ref) == 2 and ref[0].isalpha() and ref[1].isdigit():
        group_letter = ref[0]
        position = int(ref[1]) - 1
        return standings[group_letter][position][0]

    # Winner/loser bracket reference (e.g., W74, L101)
    if ref[0] in ("W", "L") and ref[1:].isdigit():
        match_no = int(ref[1:])
        if ref[0] == "W":
            return bracket[match_no]["winner"]
        else:
            return bracket[match_no]["loser"]

    return ref


def run_simulation(mode="elo"):
    teams, group_matches, knockout_template = load_data()
    all_results = []

    # --- Group stage ---
    group_results = []
    for m in group_matches:
        home, away = m["home"], m["away"]
        actual = parse_score(m.get("score"))
        if actual:
            hg, ag = actual
        else:
            hg, ag = simulate_match_score(home, away, teams, mode)
        winner = home if hg > ag else (away if ag > hg else "Draw")
        result = {
            "match_no": m["match_no"],
            "stage": "Group",
            "home": home,
            "away": away,
            "home_goals": hg,
            "away_goals": ag,
            "winner": winner,
            "notes": "",
        }
        group_results.append(result)
        all_results.append(result)

    standings = compute_group_standings(group_results, teams)

    # --- Third-place qualification ---
    qualified_thirds = select_best_third_places(standings)
    third_place_assignment = assign_third_places_to_slots(
        qualified_thirds, knockout_template
    )

    # --- Knockout stage ---
    bracket = {}

    for m in knockout_template:
        match_no = m["match_no"]
        stage = m["stage"]
        home_ref = str(m["home"])
        away_ref = str(m["away"])

        if away_ref.startswith("THIRD_"):
            away_team = third_place_assignment[match_no]
        else:
            away_team = resolve_team_ref(
                away_ref, standings, third_place_assignment, bracket
            )

        home_team = resolve_team_ref(
            home_ref, standings, third_place_assignment, bracket
        )

        actual = parse_score(m.get("score"))
        if actual:
            goals_h, goals_a = actual
            winner = home_team if goals_h > goals_a else away_team
            notes = ""
        else:
            goals_h, goals_a, winner, notes = simulate_knockout_match(
                home_team, away_team, teams, mode
            )
        loser = away_team if winner == home_team else home_team

        bracket[match_no] = {"winner": winner, "loser": loser}

        result = {
            "match_no": match_no,
            "stage": stage,
            "home": home_team,
            "away": away_team,
            "home_goals": goals_h,
            "away_goals": goals_a,
            "winner": winner,
            "notes": notes,
        }
        all_results.append(result)

    # --- Save results ---
    results_df = pd.DataFrame(all_results)
    results_df = results_df[
        [
            "match_no",
            "stage",
            "home",
            "away",
            "home_goals",
            "away_goals",
            "winner",
            "notes",
        ]
    ]

    # Save
    save_dir = f"simulation_results/{mode}"
    file_name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')}.csv"
    os.makedirs(save_dir, exist_ok=True)
    results_df.to_csv(f"{save_dir}/{file_name}", index=False)

    # # Print output
    # print("=== World Cup 2026 Simulation Complete ===\n")
    # print("--- Group Standings ---")
    # for g in sorted(standings.keys()):
    #     print(f"\nGroup {g}:")
    #     for i, (team_name, stats) in enumerate(standings[g], 1):
    #         print(
    #             f"  {i}. {team_name:25s} Pts:{stats['pts']}  GD:{stats['gd']:+d}  GF:{stats['gf']}"
    #         )

    # print("\n--- Qualified Third Places ---")
    # for t in qualified_thirds:
    #     print(
    #         f"  {t['team']:25s} (Group {t['group']}) Pts:{t['pts']}  GD:{t['gd']:+d}  GF:{t['gf']}"
    #     )

    # print("\n--- Knockout Results ---")
    # for r in all_results:
    #     if r["stage"] != "Group":
    #         score = f"{r['home_goals']}-{r['away_goals']}"
    #         extra = f"  [{r['notes']}]" if r["notes"] else ""
    #         print(
    #             f"  Match {r['match_no']:3d} ({r['stage']:5s}): {r['home']:25s} {score} {r['away']:25s} -> {r['winner']}{extra}"
    #         )

    # final = all_results[-1]
    # print(f"\n*** CHAMPION: {final['winner']} ***")
    # print("\nResults saved to simulation_results.csv")


if __name__ == "__main__":
    # run_simulation(mode="elo")

    N_SIMULATIONS = 10000
    for mode in ["elo", "odds"]:  # , "random"]:
        for _ in range(N_SIMULATIONS):
            run_simulation(mode=mode)
