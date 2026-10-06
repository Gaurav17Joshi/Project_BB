# Local (qwen3.5:9b) vs closed (gpt-6-luna) abstraction

**Encounter contacts with the same outcome as the closed model: 20/20** (service type, counted or not, minutes of counted contacts).

| Date | Encounter | Closed | Local | Same |
|---|---|---|---|---|
| 2026-01-05 | HG-E101 | individual_psy attended included 50-50 | individual_psy attended included 50-50 | ✓ |
| 2026-01-06 | HG-E102 | group_psychoth attended included 45-45 | group_psychoth attended included 45-45 | ✓ |
| 2026-01-08 | HG-E103 | individual_psy no_show excluded None-None | individual_psy no_show excluded None-None | ✓ |
| 2026-01-09 | HG-E104 | family_psychot attended included 45-45 | family_psychot attended included 45-45 | ✓ |
| 2026-01-12 | HG-E105 | group_psychoth attended included 75-75 | group_psychoth attended included 75-75 | ✓ |
| 2026-01-13 | HG-E106 | medication_man attended excluded 25-25 | medication_man attended excluded 25-25 | ✓ |
| 2026-01-14 | HG-E107 | individual_psy attended included 45-45 | individual_psy attended included 45-45 | ✓ |
| 2026-01-15 | HG-E108 | group_psychoth clinic_cancelled excluded None-None | group_psychoth clinic_cancelled excluded None-None | ✓ |
| 2026-01-16 | HG-E109 | collateral_con attended excluded None-None | collateral_con disputed excluded None-None | ✓ (status label differs) |
| 2026-01-19 | HG-E110 | group_psychoth attended included 60-60 | group_psychoth attended included 60-60 | ✓ |
| 2026-01-19 | HG-E111 | individual_psy attended included 30-30 | individual_psy attended included 30-30 | ✓ |
| 2026-01-21 | HG-E112 | individual_psy attended included 45-45 | individual_psy attended included 45-45 | ✓ |
| 2026-01-22 | HG-E113 | group_psychoth attended included 45-45 | group_psychoth attended included 45-45 | ✓ |
| 2026-01-23 | HG-E114 | care_coordinat attended excluded None-None | care_coordinat no_show excluded 0-0 | ✓ (status label differs) |
| 2026-01-26 | HG-E115 | individual_psy attended included 40-50 | individual_psy attended included 40-50 | ✓ |
| 2026-01-27 | HG-E116 | group_psychoth no_show excluded None-None | group_psychoth no_show excluded None-None | ✓ |
| 2026-01-28 | HG-E117 | individual_psy patient_cancelled excluded None-None | individual_psy patient_cancelled excluded None-None | ✓ |
| 2026-01-29 | HG-E118 | group_psychoth attended included 75-75 | group_psychoth attended included 75-75 | ✓ |
| 2026-01-30 | HG-E119 | family_psychot attended included 30-30 | family_psychot attended included 30-30 | ✓ |
| 2026-01-30 | HG-E120 | medication_man attended excluded 20-20 | medication_man attended excluded 20-20 | ✓ |

## Headline results

| | Closed | Local | Same |
|---|---|---|---|
| Session counts | ({'individual_psychotherapy': {'established': 5, 'possible_additional': 0}, 'group_psychotherapy': {'established': 5, 'possible_additional': 0}, 'family_psychotherapy': {'established': 2, 'possible_additional': 0}}, 12, 11) | ({'individual_psychotherapy': {'established': 5, 'possible_additional': 0}, 'group_psychotherapy': {'established': 5, 'possible_additional': 0}, 'family_psychotherapy': {'established': 2, 'possible_additional': 0}}, 12, 11) | ✓ |
| Weekly goal | [('2026-01-05 to 2026-01-11', 3, 140, 'not_met'), ('2026-01-12 to 2026-01-18', 2, 120, 'not_met'), ('2026-01-19 to 2026-01-25', 3, 180, 'met'), ('2026-01-26 to 2026-02-01', 3, '145-155', 'indeterminate')] | [('2026-01-05 to 2026-01-11', 3, 140, 'not_met'), ('2026-01-12 to 2026-01-18', 2, 120, 'not_met'), ('2026-01-19 to 2026-01-25', 3, 180, 'met'), ('2026-01-26 to 2026-02-01', 3, '145-155', 'indeterminate')] | ✓ |
| PHQ-9 administrations | [('2026-01-05', 18.0), ('2026-01-16', 14.0), ('2026-01-30', 10.0)] | [('2026-01-05', 18.0), ('2026-01-16', 14.0), ('2026-01-30', 10.0)] | ✓ |
| Total minutes | 585-595 | 585-595 | ✓ |

## Issues raised

| Closed | Local |
|---|---|
| draft_or_billing_without_service: HG-E116 on 2026-01-27: draft/template or billing record exists, but signed records show 'n | attendance_conflict: HG-E109 on 2026-01-16: tier-A sources disagree: attended per ['BH-D006'], not per ['BH-D01 |
| duplicate_copy: HG-E110 on 2026-01-19: BH-D104 is a resent/imported copy of an existing record; merged int | duplicate_copy: HG-E110 on 2026-01-19: BH-D103, BH-D104 is a resent/imported copy of an existing record; m |
| duplicate_measure: PHQ-9 completed 2026-01-16: 2 records of one administration (BH-D014 [copy/import], BH-D01 | duplicate_copy: HG-E116 on 2026-01-27: BH-D112 is a resent/imported copy of an existing record; merged int |
| duration_conflict: HG-E115 on 2026-01-26: final records disagree on patient-present time (40-50 min). No corr | duplicate_copy: measure_or_questionnaire_review#BH-D014:S0 on 2026-01-16: BH-D014 is a resent/imported cop |
| multiple_notes_one_encounter: HG-E104 on 2026-01-09: 2 clinical notes (BH-D007, BH-D008) describe the same encounter; co | duplicate_measure: PHQ-9 completed 2026-01-16: 2 records of one administration (BH-D014 [copy/import], BH-D01 |
| multiple_notes_one_encounter: HG-E115 on 2026-01-26: 2 clinical notes (BH-D111, BH-D110) describe the same encounter; co | duration_conflict: HG-E115 on 2026-01-26: final records disagree on patient-present time (40-50 min). No corr |
|  | invalid_date: Record BH-D001:S0 has service date '2026-01-05 to 2026-01-30', not a single calendar date; |
|  | schedule_echo_discarded: HG-E102 on 2026-01-06: BH-D004 gives exactly the scheduled slot as patient time while BH-D |
|  | schedule_echo_discarded: HG-E113 on 2026-01-22: BH-D107 gives exactly the scheduled slot as patient time while BH-D |
|  | unverified_evidence: Record BH-D005:S1 evidence quote not found in source text. |
|  | unverified_evidence: Record BH-D109:S0 evidence quote not found in source text. |
|  | unverified_evidence: Record BH-D112:S0 evidence quote not found in source text. |
|  | unverified_evidence: Record BH-D115:S0 evidence quote not found in source text. |

Local extraction quote verification: [{'ev_match': 'approx', 'n': 4}, {'ev_match': 'exact', 'n': 136}, {'ev_match': 'missing', 'n': 8}, {'ev_match': 'normalised', 'n': 11}]
