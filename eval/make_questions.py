# Builds eval/questions.csv from the list below, filling gold chunk ids/labels
# from the chunk file. Re-run after editing the list.
# verified / verifier / correction columns are filled in by hand.
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = "2026-sporting-"; T = "2026-technical-"; G = "2026-general-"
S25 = "2025-sporting-"; T25 = "2025-technical-"

Q = [
# ---------------- 2026 Sporting: direct lookups ----------------
("sporting_2026", "What is the pit lane speed limit during a 2026 Formula 1 competition?",
 "80 km/h for the whole Competition, although the Race Director may amend it for safety.", [S+"B1.6.3"]),
("sporting_2026", "What is the fine if a driver exceeds the pit lane speed limit during a free practice session?",
 "The Competitor is fined €100 for each km/h above the limit, up to a maximum of €1000 (applies to free practice, qualifying and sprint qualifying).", [S+"B1.6.3"]),
("sporting_2026", "When does a Competition officially begin under the 2026 Sporting Regulations?",
 "Four hours before FP1 is scheduled to start.", [S+"B1.1.1"]),
("sporting_2026", "How many team members per Competitor are allowed in the signalling area during sessions?",
 "Twelve (12).", [S+"B1.5.8"]),
("sporting_2026", "What penalty does a driver get for entering the pit lane during the race while it is closed, without needing essential repairs?",
 "A Stop-and-Go Penalty (during a TTCS, i.e. Sprint or Race).", [S+"B1.6.4"]),
("sporting_2026", "How is a 5-second time penalty served during a race?",
 "The driver must enter the pit lane, stop in their designated pit stop position for at least five seconds, and then rejoin.", [S+"B1.9.5"]),
("sporting_2026", "What happens if a drive-through penalty is imposed during the last three laps of a race?",
 "20 seconds are added to the driver's elapsed time (30 seconds for a Stop-and-Go Penalty).", [S+"B1.9.6", S+"B1.9.6-p2"],
 "yes", "The answer is in the second part of the clause (chunk B1.9.6-p2)."),
("sporting_2026", "What penalties can the stewards give for an incident during qualifying?",
 "They may delete the driver's lap time(s) or drop the driver a number of grid positions; grid penalties are served in the Race (or the Sprint if the infringement was in Sprint Qualifying).", [S+"B1.9.4"]),
("sporting_2026", "How long is SQ1 in Sprint Qualifying and how many cars are eliminated at the end of it?",
 "12 minutes; the slowest six cars are eliminated.", [S+"B2.2.2"]),
("sporting_2026", "How long are Q1, Q2 and Q3 in 2026 qualifying?",
 "Q1 18 minutes, Q2 15 minutes, Q3 13 minutes, with seven-minute breaks between them.", [S+"B2.4.2"]),
("sporting_2026", "What is the distance of a sprint?",
 "The least number of complete laps that exceed 100 km.", [S+"B2.3.2"]),
("sporting_2026", "What is the maximum time a sprint can run, including if it is suspended?",
 "One hour from the start signal; if suspended, the suspension time is added up to a maximum total of 1.5 hours.", [S+"B2.3.3"]),
("sporting_2026", "What is the scheduled race distance in 2026, and is Monaco different?",
 "The least number of complete laps exceeding 305 km; in Monaco it is the least number exceeding 260 km.", [S+"B2.5.2"]),
("sporting_2026", "From how long before FP1 are screens or covers that hide the cars banned?",
 "From 29 hours before the scheduled start of FP1 (unless needed solely for mechanical reasons, e.g. fire protection).", [S+"B3.3.1"]),
("sporting_2026", "How many times per championship can a team request to replace front wing, rear wing, rear bodywork or floor bodywork with parts of a different design under parc fermé?",
 "Six (6) times, provided the replacement is a specification previously used in pre-season testing, a qualifying session or a race/sprint.", [S+"B3.5.5"]),
("sporting_2026", "By how much is a race shortened after an aborted start procedure?",
 "By one lap for each Aborted Start procedure.", [S+"B5.8.3"]),
("sporting_2026", "What happens if the Safety Car is still deployed at the start of the last lap?",
 "It enters the pit lane at the end of the lap (unless the Race Director decides otherwise) and cars take the chequered flag without overtaking; the Safety Car's orange lights are switched off as the signal.", [S+"B5.13.8"]),
("sporting_2026", "How many sets of dry, intermediate and wet tyres may each driver use at a standard format competition without ICTT?",
 "13 dry-weather sets, 5 intermediate sets and 2 wet-weather sets (12 dry sets at sprint or ICTT weekends).", [S+"B6.3.4"]),
("sporting_2026", "How many engines (ICE), turbochargers and exhaust sets can each driver use in the 2026 championship?",
 "3 ICE, 3 turbochargers and 3 exhaust sets (with an additional unit allowed under B8.2.3 conditions).", [S+"B8.2.2"]),
("sporting_2026", "What grid penalty applies when a driver uses more power unit elements than allowed?",
 "10 grid places the first time an additional element of each type is used, then 5 grid places each subsequent time; penalties are cumulative.", [S+"B8.2.8"]),
("sporting_2026", "What happens when a race is suspended with a red flag?",
 "Overtaking is forbidden, the pit lane exit is closed and all cars must proceed slowly into the pit lane, lining up in the fast lane behind the first car.", [S+"B5.14.2"]),

# ---------------- 2026 Technical ----------------
("technical_2026", "What is the minimum mass of a 2026 Formula 1 car?",
 "724 kg plus the Nominal Tyre Mass; 726 kg plus Nominal Tyre Mass during Sprint Qualifying and Qualifying (increased further under a Heat Hazard).", [T+"C4.1"]),
("technical_2026", "What is the maximum electrical power of the ERS-K in 2026?",
 "350 kW (absolute DC power).", [T+"C5.2.7"]),
("technical_2026", "What is the fuel energy flow limit for the 2026 power unit?",
 "3000 MJ/h, with no cylinder exceeding 550 MJ/h under normal operating conditions.", [T+"C5.2.3"]),
("technical_2026", "What engine capacity is required in 2026?",
 "1600cc (+0/−10cc).", [T+"C5.1.2"]),
("technical_2026", "How many forward gears must a 2026 car have?",
 "Eight forward gear ratios; continuously variable transmissions are not permitted.", [T+"C9.6.1"]),
("technical_2026", "What is the maximum wheelbase of a 2026 car?",
 "3400 mm (at Legality Setup).", [T+"C2.3.3"]),
("technical_2026", "What kind of fuel must be used under the 2026 technical regulations?",
 "Advanced Sustainable (AS) fuels made solely of AS components; co-processing is not permitted.", [T+"C16.1.2"]),
("technical_2026", "How far may the front wing flaps move when the front wing adjuster is used?",
 "Maximum deviation of 30 mm for the FW Primary Flap and 60 mm for the FW Secondary Flap.", [T+"C3.10.10-p2"]),

# ---------------- 2026 General Provisions ----------------
("general_2026", "What is the maximum and minimum number of competitions in the championship?",
 "Maximum 24, minimum 8.", [G+"A2.1.2"]),
("general_2026", "How many cars can take part in the championship?",
 "No more than 24 cars, with two cars entered by each team.", [G+"A2.1.3"]),
("general_2026", "Which competition numbers can drivers use?",
 "1 to 99 inclusive, except 17.", [G+"A2.4.5"]),
("general_2026", "Who may use car number 1?",
 "The reigning World Champion Driver; their previous number is reserved for them if they lose the title.", [G+"A2.4.2"]),
("general_2026", "How many points does the winner get if the leader completed at least two laps but less than 25% of the race distance?",
 "6 points (column 1 scale: 6, 4, 3, 2, 1 for the top five).", [G+"A2.2.1"]),
("general_2026", "What is the fine if the top three drivers don't attend the FIA Prize Giving Ceremony?",
 "Up to €250,000 for each failure to comply (except in case of Force Majeure), payable by the team.", [G+"A2.6.1"]),

# ---------------- Fan language (2026) ----------------
("fan_language", "Can teams change their car setup after qualifying?",
 "No. Cars are in parc fermé; only the permitted work is allowed. Breaching parc fermé means starting from the pit lane.", [S+"B3.5.3"]),
("fan_language", "If it's pouring rain at the start, what happens?",
 "The formation lap(s) may be started behind the Safety Car (signalled at the 10-minute signal), and wet-weather tyres become compulsory.", [S+"B5.5.2"]),
("fan_language", "Do laps behind the safety car count toward the race distance?",
 "Yes, each lap completed behind the Safety Car counts as a race lap (VSC laps also count).", [S+"B5.13.7", S+"B5.12.5"]),
("fan_language", "What's the longest a Grand Prix can go on for?",
 "Two hours from the start signal; with a red-flag suspension the total can reach a maximum of three hours.", [S+"B2.5.3"]),
("fan_language", "What happens if a driver lines up badly in their grid box at the start?",
 "Cars must be stationary and positioned so no part of the front tyre contact patch is outside the box lines; the stewards can give a 5-second, 10-second or drive-through penalty.", [S+"B5.11.1"]),
("fan_language", "If someone stalls on the formation lap, can the cars behind overtake them?",
 "Only to avoid unduly delaying the field and only to re-establish the original order; a delayed driver who can't regain position before the first safety car line must start from the pit lane, or get a Stop-and-Go Penalty.", [S+"B5.6.4"]),
("fan_language", "Can a car reverse in the pit lane?",
 "No, at no time may a car be reversed in the pit lane under its own power.", [S+"B1.6.3"]),
("fan_language", "How does the moving wing system work in 2026?",
 "Driver Adjustable Bodywork adjusts both the front wing profiles and rear wing flap via the FIA Standard ECU; Corner Mode = deactivated; the driver may only activate it when notified that it is enabled (partial activation only in low-grip conditions).", [S+"B7.1.1", S+"B7.1.2"]),
("fan_language", "How heavy does the car need to be?",
 "At least 724 kg plus the Nominal Tyre Mass (726 kg plus tyres in qualifying).", [T+"C4.1"]),
("fan_language", "Can a driver drive super slowly to mess with others?",
 "No; a car may never be driven unnecessarily slowly, erratically or in a potentially dangerous manner.", [S+"B1.8.5"]),
("fan_language", "What penalties can a driver get for crashing into someone in the race?",
 "During a race (TTCS) the stewards can give a 5-second, 10-second, drive-through or 10-second stop-and-go penalty, among others.", [S+"B1.9.5"]),

# ---------------- 2025 only ----------------
("season_2025", "What was the pit lane speed limit and practice speeding fine in 2025?",
 "80 km/h; fine of €100 per km/h over the limit, up to €1000, in practice and qualifying sessions.", [S25+"34.7"]),
("season_2025", "How many MGU-H units could a driver use in the 2025 season?",
 "Four (4).", [S25+"28.2"]),
("season_2025", "How many energy stores and control electronics could each driver use in 2025?",
 "Two energy stores and two control electronics.", [S25+"28.2"]),
("season_2025", "How many points did the winner of a sprint receive in 2025, and down to which position were sprint points awarded?",
 "8 points for the winner; points down to 8th place (8-7-6-5-4-3-2-1).", [S25+"6.4"]),
("season_2025", "What was the minimum mass of the car in 2025?",
 "800 kg without fuel, plus the Heat Hazard Mass Increase.", [T25+"4.1"]),
("season_2025", "What was the maximum fuel mass flow in 2025?",
 "100 kg/h.", [T25+"5.2.3"]),
("season_2025", "How many tyre sets did each driver get at a 2025 sprint weekend?",
 "12 dry-weather, 5 intermediate and 2 wet-weather sets (Monaco: 3 wet sets).", [S25+"30.2"]),
("season_2025", "How many cars were eliminated in Q1 in 2025 and how long was Q1?",
 "Q1 lasted 18 minutes and the slowest five cars were eliminated.", [S25+"39.2"]),
("season_2025", "In 2025, did drivers have to use two different dry tyre compounds in a race?",
 "Yes, unless they used intermediate/wet tyres, each driver had to use at least two different dry-weather specifications, one being a mandatory race specification. In Monaco, at least three sets of any specification.", [S25+"30.5-p4"]),
("season_2025", "What was the maximum rotational speed of the MGU-K in 2025?",
 "50,000 rpm.", [T25+"5.3.3"]),
("season_2025", "When could the driver adjustable bodywork (DRS) be used in 2025?",
 "Only in pre-determined activation zones; the Race Director may disable it at his discretion, and if disabled during a qualifying period it stays disabled for that period.", [S25+"22.1"]),
("season_2025", "What was the race distance in 2025?",
 "The least number of complete laps exceeding 305 km (Monaco: 260 km).", [S25+"5.4"]),

# ---------------- 2025 vs 2026 changes ----------------
("compare", "How did the minimum car mass change from 2025 to 2026?",
 "2025: 800 kg without fuel. 2026: 724 kg plus Nominal Tyre Mass (726 kg plus tyres in qualifying), so the cars are much lighter.", [T25+"4.1", T+"C4.1"]),
("compare", "How did the number of cars eliminated in Q1 change between 2025 and 2026?",
 "2025: slowest 5 eliminated in Q1 and Q2. 2026: slowest 6 eliminated, reflecting the larger grid. Q1 is 18 minutes in both.", [S25+"39.2", S+"B2.4.2"]),
("compare", "Did the number of engines a driver can use change from 2025 to 2026?",
 "Yes: 4 ICE in 2025, 3 ICE in 2026 (also turbochargers 4 → 3).", [S25+"28.2", S+"B8.2.2"]),
("compare", "How is fuel flow limited in 2026 compared to 2025?",
 "2025 limited fuel MASS flow to 100 kg/h; 2026 limits fuel ENERGY flow to 3000 MJ/h (550 MJ/h per cylinder).", [T25+"5.2.3", T+"C5.2.3"]),
("compare", "Did the race distance rules change in 2026?",
 "No. Both seasons use the least number of laps exceeding 305 km, and 260 km for Monaco.", [S25+"5.4", S+"B2.5.2"]),
("compare", "Did the pit lane speeding fine in practice change from 2025 to 2026?",
 "No. Both: €100 per km/h above the limit, up to €1000.", [S25+"34.7", S+"B1.6.3"]),
("compare", "Are points for a full-distance race different in 2026 compared to 2025?",
 "No. 25, 18, 15, 12, 10, 8, 6, 4, 2, 1 in both seasons.", [S25+"6.4", G+"A2.2.1"]),
("compare", "Did the number of dry tyre sets at a normal (non-sprint) weekend change in 2026?",
 "No, 13 dry-weather sets in both seasons (when no additional tyres are provided).", [S25+"30.2", S+"B6.3.4"]),
("compare", "How did the adjustable wing system change from 2025 to 2026?",
 "2025: driver adjustable bodywork (DRS, rear wing) only in activation zones. 2026: both front wing profiles and rear wing flap adjust between Corner Mode and an activated mode, enabled via the FIA ECU.", [S25+"22.1", S+"B7.1.1"]),
("compare", "How did Sprint Qualifying SQ1 change from 2025 to 2026?",
 "Both 12 minutes; 2025 eliminated the slowest 5 cars, 2026 eliminates the slowest 6.", [S25+"39.3", S+"B2.2.2"]),

# ---------------- 2026 stewards' decisions ----------------
("stewards", "Why was Sergio Perez penalised at the 2026 Chinese Grand Prix?",
 "5-second time penalty in the Sprint for failing to stay above the ECU minimum time behind the Safety Car (breach of B5.13.2b).", ["stewards-r02-doc49"]),
("stewards", "What penalty did Kimi Antonelli get in the 2026 Chinese Grand Prix sprint?",
 "10-second time penalty for causing a collision with Car 6 (Hadjar) at Turn 6 on Lap 1.", ["stewards-r02-doc48"]),
("stewards", "Why did Alexander Albon start the 2026 Chinese Grand Prix race from the pit lane?",
 "Changes were made to his car during parc fermé after Qualifying, so he was required to start from the pit lane.", ["stewards-r02-doc68"]),
("stewards", "What penalty did Charles Leclerc receive in the 2026 Miami Grand Prix race and why?",
 "A drive-through penalty imposed after the race (20 seconds added) for leaving the track several times without justifiable reason (cutting chicanes after damaging the car on the last lap).", ["stewards-r04-doc97"]),
("stewards", "Why was Gabriel Bortoleto disqualified at the 2026 Miami Grand Prix?",
 "Car 5 was disqualified from the Sprint classification for a technical non-conformity related to engine intake air pressure.", ["stewards-r04-doc54"]),
("stewards", "Why was Isack Hadjar disqualified from qualifying in Miami 2026?",
 "Technical non-conformity of the floor board; Car 6 was disqualified from the Qualifying classification.", ["stewards-r04-doc70"]),
("stewards", "Why was McLaren fined at the 2026 Monaco Grand Prix for Lando Norris's car?",
 "The CDS did not function when the car stopped; the team had taped over the CDS activation button for aerodynamic reasons. Fined €30,000, €10,000 suspended for 12 months (breach of C9.3).", ["stewards-r06-doc42"]),
("stewards", "What happened with George Russell's head restraint at the 2026 Canadian Grand Prix?",
 "He threw it onto the track after his car stopped; fined €5,000, suspended for 12 months, after he apologised.", ["stewards-r05-doc104"]),
("stewards", "What penalty did Isack Hadjar get for failing to slow for yellow flags in Canada 2026?",
 "A 10-second stop-and-go penalty.", ["stewards-r05-doc106"]),
("stewards", "Why did Sergio Perez get a penalty after the 2026 Monaco Grand Prix restart?",
 "He was out of position at the restart after the red flag (front-right wheel outside the box), a breach of B5.11; 10-second penalty imposed after the race.", ["stewards-r06-doc82"]),
("stewards", "What penalty did Pierre Gasly get for impeding Lance Stroll in qualifying at the 2026 British Grand Prix?",
 "A three-place grid drop for the next race in which he participates (breach of B4.1.1).", ["stewards-r09-doc60"]),
("stewards", "Why did Lance Stroll get a 10-place grid drop at the 2026 British Grand Prix?",
 "He used a 5th Energy Store and a 5th Control Electronics unit; each additional element carried 5 places, totalling 10.", ["stewards-r09-doc68"]),
("stewards", "Why was Carlos Sainz given a penalty lap at Silverstone in 2026?",
 "He overtook the Safety Car after 'lapped cars may now overtake' although he was not a lapped car at that moment (breach of B5.13.4c); 1 penalty lap.", ["stewards-r09-doc83"]),
("stewards", "What penalty did Lewis Hamilton get at the start of the 2026 British Grand Prix?",
 "A 5-second time penalty for a false start (moving before the start signal).", ["stewards-r09-doc72"]),
("stewards", "What penalty did Franco Colapinto get for yellow flags at the 2026 Barcelona-Catalunya race?",
 "A 10-second time penalty imposed after the race and 1 penalty point (2 in total for the 12-month period).", ["stewards-r07-doc62"]),
("stewards", "Why was Racing Bulls fined after Liam Lawson's car stopped in practice at the 2026 Canadian Grand Prix?",
 "The CDS did not function when the car stopped (breach of C9.3); fined €30,000, €20,000 of which suspended for 12 months.", ["stewards-r05-doc26"]),
("stewards", "Which drivers were penalised for pit lane speeding during the 2026 Monaco Grand Prix race?",
 "Pierre Gasly (two 5-second penalties), Franco Colapinto, Lewis Hamilton, George Russell and Oscar Piastri (5-second penalty each).",
 ["stewards-r06-doc73", "stewards-r06-doc75", "stewards-r06-doc72", "stewards-r06-doc70", "stewards-r06-doc71", "stewards-r06-doc74"],
 "yes", "Aggregation across 6 documents: expected to be hard with k=5. Gasly's penalties were later rescinded by the stewards (Doc 99) and then reinstated by the International Court of Appeal, which is not in the corpus."),

# ---------------- Unanswerable (bot should refuse) ----------------
("unanswerable", "What is the 2026 cost cap for Formula 1 teams?",
 "Not in the corpus (Section D Financial Regulations was not included). The bot should say it can't find it.", [], "no",
 "Tests refusal: the LLM likely 'knows' a figure from training and may hallucinate it. Note: the 2025 Sporting Appendix 4 lists ENTRY FEES in US$, which are not the cost cap."),
("unanswerable", "Who won the 2026 Monaco Grand Prix?",
 "Not in the corpus (no race results). The bot should say it can't find it.", [], "no", ""),
("unanswerable", "How much does Lewis Hamilton earn per year?",
 "Not in the corpus. The bot should say it can't find it.", [], "no", ""),
("unanswerable", "Which tyre compounds did Pirelli bring to the 2026 British Grand Prix?",
 "Not in the corpus. The bot should say it can't find it.", [], "no", "One British GP stewards' document mentions a driver on 'new soft tyres', but not which compounds were nominated, so the question is unanswerable."),
("unanswerable", "What will the power unit rules be in 2027?",
 "Not in the corpus (future-season appendix was deliberately excluded). The bot should say it can't find it.", [], "no", ""),
("unanswerable", "How many world championships has Max Verstappen won?",
 "Not in the corpus. The bot should say it can't find it.", [], "no", ""),
("unanswerable", "What penalty did Max Verstappen receive at the 2026 Japanese Grand Prix?",
 "False premise: the documents contain no penalty for Verstappen in Japan (only a 'no further action' incident between Hamilton and Car 3). The bot should say it can't find such a penalty.", [], "no",
 "Tests false-premise handling."),
("unanswerable", "What is the minimum age to get an FIA Super Licence?",
 "Not in the corpus (Super Licence rules are in the ISC Appendix L). The bot should say it can't find it.", [], "no", "Checked: no Super Licence age appears in the corpus (only a 2025 rule that under-16s may not be in the pit lane at certain times)."),
]


def main():
    chunks = {}
    with open(ROOT / "data" / "processed" / "chunks_article.jsonl", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            chunks[c["id"]] = c
    rows, missing = [], []
    for i, item in enumerate(Q, start=1):
        cat, q, ans, gold = item[:4]
        answerable = item[4] if len(item) > 4 else "yes"
        notes = item[5] if len(item) > 5 else ""
        labels = []
        for g in gold:
            if g not in chunks:
                missing.append((i, g)); continue
            md = chunks[g]["metadata"]
            if md["source_type"] == "stewards":
                labels.append(f"{md['race']} Doc {md['document_no']}")
            else:
                labels.append(f"{md['season']} {md['clause']} (p{md['page']})")
        rows.append({"id": f"Q{i:03d}", "category": cat, "question": q, "expected_answer": ans,
                     "gold_chunk_ids": ";".join(gold), "gold_labels": "; ".join(labels),
                     "answerable": answerable, "notes": notes,
                     "verified": "", "verifier": "", "correction": ""})
    out = ROOT / "eval" / "questions.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig so Excel shows € correctly
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"Wrote {len(rows)} questions to {out}")
    print("By category:", dict(Counter(r["category"] for r in rows)))
    print("Missing gold chunk ids:", missing or "none")


if __name__ == "__main__":
    main()
