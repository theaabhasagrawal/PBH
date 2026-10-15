# PB Health Hospital — Baseline Diagnostic Analysis & Pitch Audit
**Analysis Date:** 2026-10-15  
**Data Source:** Policybazaar Data Science AI Portal (`datascienceapi.policybazaar.com`)  
**Sample Window:** Historical Call Transcripts (Haryana, Delhi, UP, Pan-India)  
**Database:** `data/pb_health.db` (Table: `call_analysis`)

---

## 1. Executive Summary & Headline Numbers

Our baseline audit across real customer calls reveals a **critical gap between the PB Health Hospital vision and what telesales agents are currently saying on the floor**.

| Metric | Baseline Score | Target | Status |
| :--- | :---: | :---: | :--- |
| **Story Adherence Score** | **25.4 / 100** | > 75.0 | 🔴 Critical Gap |
| **Pitch Penetration Rate (PPR)** | **100.0%** (of hospital calls) | > 25% NCR | 🟢 Captured |
| **PB Health App Push Rate** | **42.1%** | > 75.0% | 🟡 Moderate |
| **Customer Objection Rate** | **47.4%** | < 25.0% | 🔴 High Friction |
| **Specific Hub Location Pitch Rate** | **5.3%** | > 70.0% | 🔴 Critical Leak |
| **Ethical "Zero Overcharge" Pitch Rate**| **15.8%** | > 70.0% | 🔴 Under-Pitched |
| **Zero Waiting Time Pitch Rate** | **10.5%** | > 60.0% | 🔴 Under-Pitched |
| **Multispeciality Positioning Rate** | **57.9%** | > 85.0% | 🟡 Mixed Messaging |
| **Exclusive Family Discount Rate** | **47.4%** | > 85.0% | 🟡 Moderate |
| **Cashless Guarantee Rate** | **84.2%** | > 90.0% | 🟢 Strong Anchor |

---

## 2. Pillar-by-Pillar Compliance Breakdown

```
Multispeciality Hospital        [15 pts] █████████████░░░░░░░░░   57.9%
Specific Hub Location           [25 pts] █░░░░░░░░░░░░░░░░░░░░    5.3% (LEAK #1)
Ethical Care / No Overcharge    [20 pts] ████░░░░░░░░░░░░░░░░░   15.8% (LEAK #2)
Zero Waiting / Digital Check-in [15 pts] ██░░░░░░░░░░░░░░░░░░░   10.5% (LEAK #3)
PB Health App Push              [15 pts] ██████████░░░░░░░░░░░   42.1%
Exclusive Family Discount       [10 pts] ███████████░░░░░░░░░░   47.4%
Top Doctors / Specialists       [Track ] ████░░░░░░░░░░░░░░░░░   15.8%
End-to-End Cashless             [Track ] █████████████████████   84.2%
```

### Key Diagnostic Takeaways:
1. **The Location Blindspot (5.3%):** In 94.7% of pitches, reps do **not** name the specific hub location. When a customer in Noida or Faridabad is on the call, agents either say nothing about locations or vaguely say *"Gurgaon mein hospital hai"*, creating instant distance friction.
2. **The "Zero Overcharge" Weapon is Wasted (15.8%):** The single strongest brand trust proposition—that PB Health doctors are salary-based with zero incentive to push unnecessary tests, ICU admissions, or surgeries—is mentioned in only 15.8% of calls.
3. **The "Clinic / OPD" Perception Trap:** In 42.1% of calls, agents casually describe PB Health as an *"OPD Pass"*, *"Wellness coupon"*, or *"Clinic"* rather than positioning it as a full-fledged **Multispeciality Hospital with OTs, ICU, and inpatient surgery**.

---

## 3. The 5-Hub Location Distribution & The "Nearest-Hub Gap"

| Hub Location | Mention Share (%) | Reality on the Floor |
| :--- | :---: | :--- |
| **Noida - Sector 50** | **66.7%** | Mentioned occasionally when agents pitch UP leads. |
| **Faridabad - Sector 2** | **33.3%** | Rarely mentioned unless customer asks about Faridabad. |
| **Gurgaon 1 - IFFCO Chowk** | **0.0%** (in sample) | Often conflated with generic "Gurgaon". |
| **Gurgaon 2 - Sector 62 Golf Course** | **0.0%** | Completely omitted by reps. |
| **Delhi - Rohini** | **0.0%** | Completely omitted by reps. |

### The Nearest-Hub Failure:
* When customers were located closest to **Faridabad**: Reps named their nearest hub **0.0%** of the time.
* When customers were located closest to **IFFCO Chowk / Gurgaon**: Reps named their nearest hub **0.0%** of the time.
* When customers were located closest to **Noida**: Reps named their nearest hub **0.0%** of the time.

> **Operational Insight:** Sales agents are treating PB Health Hospital as an abstract online perk rather than a **physical, local hospital network in the customer's backyard**.

---

## 4. Customer Objection Taxonomy (With Real Verbatim Quotes)

Customer objections were recorded in **47.4%** of pitched calls. Below are the top friction points extracted verbatim from transcript turn analysis:

### 1. Facility Scope: "Is it a real hospital or just an OPD clinic?" (15.8%)
* **Real Customer Quote (Call 3955712339):**  
  > *"Bolte hain ki yeh toh matlab sirf OPD waale cover hote hain... yeh toh existing bimari ke liye nahi hai na?"*
* **Real Customer Quote (Call 3956112052):**  
  > *"OPD ke andar? Sirf OPD ke andar? If I am right aap log sirf aur sirf checkup karte ho?"*
* **Root Cause:** Agents introduce the "OPD pass" before establishing that PB Health is a **full multispeciality hospital with surgery, ICU, and day-care**.

### 2. Clinical Trust vs Established Giants (Max / Fortis / Apollo) (21.1%)
* **Customer Hesitation:**  
  > *"Hum toh Max / Fortis jaate hain. Policybazaar ke hospital mein kaun se doctors hain? Senior surgeon hain ya junior?"*
* **Agent Failure Mode:** Reps fumble by saying *"haan ache doctors hain"* instead of citing the **senior specialists from AIIMS/Max/Fortis on fixed salary models**.

### 3. General Skepticism / Rushing Past (10.5%)
* **Real Customer Quote (Call 3955694000):**  
  > *"Kya accha hai kya bura hai wo bhi sochenge na... period chahiye na sir mere ko jaise aaj hi sochunga... aage chalo."*
* **Real Customer Quote (Call 3956112052):**  
  > *"Nahi nahi zarurat nahi hai, aage chalo."*
* **Root Cause:** Reps drop the hospital pitch like a mandatory script disclosure rather than a 20-second compelling hook.

### 4. Discount & App Friction (10.5%)
* **Customer Doubts:** Customers are unsure if the discount applies to their parents, how to activate it, or whether it requires a separate membership fee.

---

## 5. Five Actionable Coaching Recommendations

1. **Mandate the 20-Second PB Story Hook:**  
   Reps must open with the master hook: *"Policybazaar ka apna multispeciality hospital hai with zero overcharging (fixed salary doctors) aur aapke sabse paas hamara [Nearest Hub] centre hai."*
2. **Never Say "Clinic" — Always Say "Multispeciality Hospital":**  
   Train reps to explicitly state: *"OT, ICU, Daycare Surgery aur Inpatient admission sab ek hi jagah."* This immediately neutralizes the #1 objection.
3. **Enforce the "Location-Match Rule":**  
   If the lead is from Noida/Ghaziabad -> pitch **Sector 50**. If South/East Delhi or Faridabad -> pitch **Sector 2 Faridabad**. If West/North Delhi -> pitch **Rohini**. If Gurgaon -> pitch **IFFCO Chowk & Sector 62**.
4. **Lead with Ethical Medicine:**  
   Train reps to explain: *"Doctor ko faltu test ya surgery likhne ka koi commission nahi milta."* This resonates deeply with customers who fear hospital overbilling.
5. **Walk the Customer Through App Onboarding on Call:**  
   Send the PB Health App link via SMS/WhatsApp while still on the call so the customer views the hospital and family discount live.

---

## 6. Generated Sales Artifacts
* **Printable 2-Page PDF Sales Deck:** `output/PB_Health_Sales_Deck.pdf`
* **Interactive HTML Sales Deck:** `output/PB_Health_Sales_Deck.html`
* **SQLite Database:** `data/pb_health.db`
* **JSON Metrics Export:** `output/baseline_report.json`
* **Live Tracking Dashboard:** Run `streamlit run app.py`
