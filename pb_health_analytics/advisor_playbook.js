/*
 * PB Health Hospital - Advisor Playbook (.docx)
 *
 *   npm install docx@9      (once, anywhere on NODE_PATH)
 *   node advisor_playbook.js  ->  output/sales_kit/PB_Health_Advisor_Playbook.docx
 *
 * Rewrite of the sales team's "PB Health Pitch Analysis & Advisor Benchmark Guide".
 * Facts are the team's approved claims (Oct 2026); numbers come from
 * output/sales_kit/stats.json (real-call analysis) and keyword_rules.py.
 * Quotes are verbatim excerpts from real calls (speech-to-text, lightly trimmed).
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, Header, Footer,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType, PageNumber, TabStopType,
} = require("docx");

const ROOT = __dirname;
const S = JSON.parse(fs.readFileSync(path.join(ROOT, "output/sales_kit/stats.json"), "utf8"));
const OUT = path.join(ROOT, "output/sales_kit/PB_Health_Advisor_Playbook.docx");
const LOGO = fs.readFileSync(path.join(ROOT, "assets/pbh-logo.png"));

const ORANGE = "EA4722", BLUE = "01589F", INK = "000000", GREY = "5F5E5A", LINE = "D9D9D9", TINT = "F3F3F3", TINT_B = "E6F1FB";
const FONT = "Arial";
const W = 9906; // A4 width 11906 - 2 x 1000 margins
const pct = (v) => `${Math.round(v)}%`;
const doubtCalls = Math.round((S.any_doubt / 100) * S.pitched);

// ---------- helpers ----------
const run = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 21, bold: o.bold, italics: o.italics, color: o.color || INK });
const p = (children, o = {}) => new Paragraph({
  children: Array.isArray(children) ? children : [run(children, o)],
  spacing: { after: o.after ?? 120, before: o.before ?? 0, line: o.line ?? 288 },
  alignment: o.align, keepNext: o.keepNext,
});
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(text, { size: 30, bold: true, color: BLUE })],
  spacing: { before: 280, after: 120 }, keepNext: true });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [run(text, { size: 24, bold: true, color: ORANGE })],
  spacing: { before: 220, after: 80 }, keepNext: true });
const bullet = (children, o = {}) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  children: Array.isArray(children) ? children : [run(children, o)],
  spacing: { after: 60, line: 276 },
});
const labelled = (label, text, color = BLUE) => new Paragraph({
  children: [run(label + "  ", { bold: true, color }), ...(Array.isArray(text) ? text : [run(text)])],
  spacing: { after: 70, line: 276 }, indent: { left: 0 },
});
const quote = (text, id) => new Paragraph({
  children: [run(`“${text}”`, { italics: true, color: GREY }), run(`   call ${id}`, { size: 17, color: GREY })],
  spacing: { after: 90, line: 276 }, indent: { left: 360 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: ORANGE, space: 8 } },
});
const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border };
function cell(content, width, o = {}) {
  const paras = (Array.isArray(content) ? content : [content]).map((c) =>
    typeof c === "string" ? p([run(c, { bold: o.bold, color: o.color, size: o.size })], { after: 40, line: 264 }) : c);
  return new TableCell({
    children: paras, width: { size: width, type: WidthType.DXA }, borders,
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
  });
}
function table(widths, rows, headerFill = BLUE) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => cell(c, widths[j], i === 0 ? { bold: true, color: "FFFFFF", fill: headerFill } : {})),
    })),
  });
}
function callout(children, fill = TINT_B) {
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    rows: [new TableRow({ children: [new TableCell({
      children, width: { size: W, type: WidthType.DXA }, shading: { fill, type: ShadingType.CLEAR, color: "auto" },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
                 left: { style: BorderStyle.SINGLE, size: 18, color: BLUE }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } },
      margins: { top: 120, bottom: 120, left: 200, right: 200 },
    })] })],
  });
}
const gap = (after = 120) => new Paragraph({ children: [], spacing: { after } });

// ---------- content ----------
const SCRIPT_HI = "Sir, ek important baat: Policybazaar ka khud ka hospital khul gaya hai, PB Health Hospital, MG Road, Gurugram. " +
  "India mein yeh akeli insurance company hai jiska apna hospital hai. 100-bed multispeciality hospital hai: modular OT, critical care, " +
  "MRI, CT, Cath Lab. Doctors salaried hain, commission nahi, toh sirf zaroori treatment. PB customer ko day one se consultation pe " +
  "50% off aur tests pe 20% off. Aur claim ki tension nahi: policy PB se, claim advisor PB ka, hospital PB ka. 100% claim guarantee.";
const SCRIPT_EN = "Policybazaar has opened its own hospital, PB Health Hospital, on MG Road, Gurugram - India's only insurance company with its " +
  "own hospital. It is a 100-bed multispeciality hospital with modular OT, critical care, MRI, CT and a Cath Lab. Doctors are salaried, " +
  "not on commission, so you get only the treatment you need. As a PB customer you get 50% off consultations and 20% off tests from " +
  "day one. And no claim worries: policy, claim advisor and hospital are all PB - a 100% claim guarantee.";

const PILLARS = [
  { name: "Policybazaar's own hospital",
    say: "\"India mein akeli insurance company hai jiska apna hospital hai: Policybazaar ka khud ka hospital, PB Health Hospital, MG Road, Gurugram.\"",
    why: "Customers trust a company that puts its own name on a hospital. It turns PB from 'a website' into a healthcare provider.",
    facts: "India's only insurance company with its own hospital. First flagship hospital: MG Road, Gurugram.",
    quote: ["policy bazaar ne apna khud ka hospital khol diya hai sir aur batao sau beds available hai wahan par", "3956183861"],
    avoid: `Saying only "apna hospital" (customers hear "choose your own hospital") or only "PB Health" (customers think of the app). ${S.pbh_only.toLocaleString("en-IN")} calls said "PB Health" without ever mentioning the hospital.` },
  { name: "A real multispeciality hospital",
    say: "\"100-bed multispeciality hospital hai: modular OT, critical care, MRI, CT scan, Cath Lab, digital X-ray, in-house lab. Consultation se surgery aur admission tak.\"",
    why: "The second most common question is \"hospital hai ya clinic?\". Customers need to hear it can admit and operate.",
    facts: "100 beds. Modular OT, MRI, CT scan, Cath Lab, digital X-ray, critical care, in-house lab.",
    quote: ["jo facilities apollo max wagairah milta hai multi speciality hospital mein wo saare facilities humare hospital mein bhi available hai", "3955656657"],
    avoid: `Describing it only through OPD / consultation discounts: ${pct(S.opd_only)} of pitches do this, and ${pct(S.scope_missing)} say nothing about what it treats.` },
  { name: "Honest, senior doctors",
    say: "\"Doctors salaried hain, commission nahi, toh sirf zaroori test aur treatment. Specialists Apollo, Max, Narayana, Manipal aur Armed Forces se hain.\"",
    why: "Fear of overbilling and unnecessary tests is real. Salaried doctors answer it directly.",
    facts: "Doctors are salaried (non-commission). Specialists from Apollo, Max, Narayana and Manipal, and Armed Forces / military doctors.",
    quote: ["unka koi commission base kaam nahi hota, wo salaried doctors hote hai, toh fayda yeh rehta hai ki koi treatment high … nahi kar dete", "3954582239"],
    avoid: `Saying only "top doctors" with no reason. Today only ${pct(S.ethical)} of pitches mention salaried doctors.` },
  { name: "Day-1 savings",
    say: "\"PB customer ko day one se consultation pe 50% off aur tests aur scans pe 20% off.\"",
    why: "It is value the customer gets without being hospitalised - something to use this month, not 'some day'.",
    facts: "50% off specialist consultations. 20% off tests and scans. From day one.",
    quote: ["consultation lene ke liye to usko fifty percent ka discount mil jata hai, maan lijiye uska consultation fees hai two thousand rupees … one thousand", "3961809744"],
    avoid: "Other numbers or 'free' - on calls we heard 25%, 30% and 75% off, and 'free consultation' or 'free revisit'. Use only 50% and 20%." },
  { name: "The claim promise",
    say: "\"Policy PB se, claim advisor PB ka, hospital PB ka: 100% claim guarantee. Claim ke time PB ka RM 30 minute mein hospital pahunchta hai.\"",
    why: "The biggest fear about health insurance is the claim being rejected or delayed. This closes the loop.",
    facts: "100% claim guarantee. A PB advisor / RM reaches the hospital within 30 minutes to manage paperwork.",
    quote: ["apne sirf relationship manager ko call karna hai … aadhe ghante ke andar andar humara ek advisor aapke hospital mein hoga", "3960944863"],
    avoid: "Confirming cashless for a specific insurer or hospital without checking - take the policy name and confirm." },
];

const ASKS = [
  ["“kahan pe hai yeh hospital” (call 3928334064)", String(S.doubts["Location friction"]),
   "MG Road, Gurugram. Abhi pehla hospital yahi hai; Noida aur Delhi next. Claim ke time PB ka RM 30 minute mein hospital pahunchta hai."],
  ["“that's a hospital also ya phir koi walk in facility” (call 3961693224)", String(S.doubts["Scope doubt"]),
   "100-bed multispeciality hospital: modular OT, critical care, MRI, CT, Cath Lab. Consultation se surgery aur admission tak."],
  ["“matlab discount kitna mil jayega” (call 3932040651)", String(S.doubts["Discount confusion"]),
   "PB customer ko day one se: consultation pe 50% off, tests aur scans pe 20% off."],
  ["“yahan ke m d kaun hai” (call 3961763292)", String(S.doubts["Doctor/Trust doubt"]),
   "Apollo, Max, Narayana, Manipal aur Armed Forces ke senior doctors. Salaried hain, commission nahi. Specific doctor ka naam chahiye toh main details WhatsApp kar deta hoon."],
  ["“mujhe nahi chahiye … hospital mein mere ko nahi jaana hai” (call 3975641784)", String(S.doubts["Skepticism/Rushing past"]),
   "Bilkul sir. Bas yaad rakhiye: hospital, doctor aur claim advisor, teeno PB ke. Location WhatsApp kar deta hoon. Then move on - don't repeat the pitch."],
  ["“meri policy wahan cashless chalegi?” (not heard yet - be ready)", "0",
   "Apni policy ka naam bataiye, main abhi check karke batata hoon ki wahan cashless milega ya nahi."],
];

const DO = [
  "Say all three every time: \"Policybazaar ka khud ka hospital\", \"PB Health Hospital\", \"MG Road, Gurugram\".",
  "Say what it treats: \"100-bed multispeciality\".",
  "Give the reason to trust: salaried doctors, no commission.",
  "Pitch on every health call - inside or outside NCR. Don't wait to be asked: 96% of customers never ask.",
  "Send the location on WhatsApp before ending the call.",
];
const DONT = [
  `Say Noida, Delhi, Rohini or Faridabad is open - only MG Road is. ${pct(S.noida)} of pitches mention Noida today.`,
  "Give opening dates for new hospitals.",
  "Call it a clinic, an \"OPD card\" or a wellness benefit.",
  "Quote any discount other than 50% (consultations) and 20% (tests and scans), or say anything is free.",
  "Promise cashless for a specific insurer without checking.",
];

const CHECKS = [
  ["Named it as Policybazaar's own hospital", "\"Policybazaar ka khud ka hospital\" / \"PB Health Hospital\""],
  ["Said where it is", "\"MG Road, Gurugram\" - and nothing about other cities being open"],
  ["Said what it treats", "\"100-bed multispeciality\", OT / critical care / MRI / CT"],
  ["Gave the reason to trust", "Salaried doctors, no commission"],
  ["Gave the day-1 value", "50% off consultations, 20% off tests and scans"],
  ["Closed with the claim promise", "100% claim guarantee, RM at the hospital in 30 minutes"],
  ["Pitched at the right moment", "After the premium, on a claim worry, for parents / chronic conditions"],
  ["Answered the customer's question", "With the approved line, then moved on"],
];

const FACTS = [
  ["Location", "MG Road, Gurugram. The only PB Health hospital open today."],
  ["Size and type", "100-bed multispeciality flagship hospital."],
  ["Facilities", "Modular OT, MRI, CT scan, Cath Lab, digital X-ray, critical care, in-house lab."],
  ["Doctors", "Salaried (non-commission). Specialists from Apollo, Max, Narayana, Manipal; Armed Forces / military doctors."],
  ["Savings", "50% off specialist consultations, 20% off tests and scans, from day one."],
  ["Claims", "100% claim guarantee. A PB advisor / RM reaches the hospital within 30 minutes for paperwork."],
  ["Positioning", "India's only insurance company with its own hospital."],
  ["Expansion", "Starting in Gurugram; expanding to Delhi NCR (Noida, Delhi), Mumbai, Bengaluru. No dates."],
];
const NOT_APPROVED = [
  "Opening dates for any new hospital, or that any hospital other than MG Road is open.",
  "Discounts other than 50% / 20% (we heard 25%, 30%, 75%), \"free\" consultations or revisits.",
  "\"First priority admission\" for PB customers, specific doctor names, bed availability.",
];

// ---------- document ----------
const children = [];
children.push(new Paragraph({ children: [new ImageRun({ type: "png", data: LOGO, transformation: { width: 150, height: 59 } })], spacing: { after: 160 } }));
children.push(p([run("PB Health Hospital", { size: 44, bold: true }), run("  Advisor Playbook", { size: 44, bold: true, color: ORANGE })], { after: 80 }));
children.push(p("How to pitch Policybazaar's own hospital on every health call. Built from 15,000+ real calls, Sep - Oct 2026.", { size: 24, color: GREY, after: 60 }));
children.push(p("Version 2  ·  21 Oct 2026  ·  For Health Sales advisors, TLs and AMs", { size: 18, color: GREY, after: 240 }));

children.push(h1("1. What the calls tell us"));
children.push(p(`We read ${S.team_calls.toLocaleString("en-IN")} Gurgaon FF calls (8 Sep - 20 Oct) and ${S.analysed.toLocaleString("en-IN")} health sales calls from across India (${S.period}). This is what advisors actually say about the hospital today.`));
children.push(table([1700, W - 1700], [
  ["Number", "What it means"],
  [`4 in 10`, `Gurgaon calls that actually mention the hospital (${S.team_actual.toFixed(1)}%). The current tracker reports ${S.team_tracker.toFixed(0)}% because it counts words like "discount" and "claims" that come up on almost every insurance call.`],
  [pct(S.scope_missing), `of pitches never say what the hospital treats. Another ${pct(S.opd_only)} describe it only as OPD or consultation discounts.`],
  [pct(S.ethical), `of pitches mention salaried doctors. ${pct(S.zero_wait)} mention no waiting / online booking, ${pct(S.family_discount)} the family discount.`],
  [pct(S.mg_road), `of pitches name MG Road. ${pct(S.gurgaon_generic)} just say "Gurgaon", ${pct(S.no_location)} name no place at all, and ${pct(S.noida)} mention Noida, which is not open yet.`],
  [pct(S.outside_ncr), "of pitches go to customers outside Delhi NCR, who cannot easily visit."],
  [pct(S.any_doubt), `of pitches get any question back. In ${S.doubts["Location friction"]} of the ${doubtCalls} calls with a question, it was "Kahan hai?".`],
  [pct(S.claims["Quotes a % discount (e.g. '50% off consultation')"]), `of pitches quote a discount, but the numbers vary (25%, 30%, 50%, 75%, "free"). ${pct(S.claims["Says other cities/hubs are 'coming soon'"])} talk about hospitals "coming soon".`],
]));
children.push(gap(80));
children.push(callout([p([run("The fix: ", { bold: true, color: BLUE }), run("say the full pitch, the same way, on every call. The script and the five points below are built from what the best advisors already say.")], { after: 0 })]));

children.push(h1("2. The 30-second pitch"));
children.push(p([run("Say it word for word. ", { bold: true }), run("It covers all five points and the three phrases the call tracker listens for.")]));
children.push(callout([
  p([run(SCRIPT_HI, { size: 23 })], { after: 100, line: 300 }),
  p([run(SCRIPT_EN, { italics: true, color: GREY, size: 19 })], { after: 0 }),
], TINT));
children.push(gap(100));
children.push(p([run("Always say these three phrases: ", { bold: true, color: ORANGE }),
  run("\"Policybazaar ka khud ka hospital\"  ·  \"PB Health Hospital\"  ·  \"MG Road, Gurugram\". They tell the customer exactly what and where, and they are what the call tracker counts as a pitch.")]));

children.push(h1("3. The 5 points, in this order"));
PILLARS.forEach((x, i) => {
  children.push(h2(`${i + 1}. ${x.name}`));
  children.push(labelled("Say", [run(x.say, { bold: true })]));
  children.push(labelled("Why it lands", x.why));
  children.push(labelled("Facts you can use", x.facts));
  children.push(labelled("Heard on a real call", ""));
  children.push(quote(x.quote[0], x.quote[1]));
  children.push(labelled("Avoid", x.avoid, ORANGE));
});

children.push(h1("4. Where it is, and what is next"));
children.push(bullet([run("Only MG Road, Gurugram is open. ", { bold: true }), run("Say \"abhi pehla hospital MG Road, Gurugram mein hai; Noida aur Delhi next, phir Mumbai aur Bengaluru\". Never give dates.")]));
children.push(bullet([run("Customer in Delhi NCR: ", { bold: true }), run("open with the location: \"PB Health Hospital, MG Road, Gurugram\".")]));
children.push(bullet([run("Customer outside NCR: ", { bold: true }), run(`lead with the claim promise. The hospital is proof that PB stands behind claims; don't ask them to travel. A third of pitches today go to customers outside NCR.`)]));

children.push(h1("5. When to pitch"));
[
  "Right after you share the premium: \"ek aur benefit jo sirf PB pe milta hai\".",
  "When the customer worries about claim rejection or paperwork.",
  "Parents, senior citizens, or BP / sugar / heart conditions in the family.",
  "Customer lives in Delhi NCR: open with the location.",
  "On every other health call too - 96% of customers never ask about the hospital, so if you don't bring it up, it never comes up.",
].forEach((t) => children.push(bullet(t)));

children.push(h1("6. When the customer asks"));
children.push(p(`Real questions from ${S.analysed.toLocaleString("en-IN")} calls, most asked first. Answer in one line, then carry on with the call.`));
children.push(table([3300, 900, W - 4200], [["Customer says (real example)", "Calls", "Say this"], ...ASKS]));

children.push(h1("7. Do and don't"));
children.push(table([W / 2, W / 2], [["Do", "Don't"], ...Array.from({ length: Math.max(DO.length, DONT.length) }, (_, i) => [DO[i] || "", DONT[i] || ""])]));

children.push(h1("8. How your pitch is tracked"));
children.push(p("Until now a call was marked \"Pitched\" if words like \"discount\", \"claims\", \"facility\" or \"top doctors\" came up. Those words are on almost every insurance call, so the tracker reported 65% when about 42% of calls actually mentioned the hospital - and some real pitches were missed."));
children.push(p("The new tracker listens for the hospital itself. If you say the three phrases, your pitch is counted:"));
[
  "\"khud ka hospital\", \"khud ke hospital\", \"khud ka bhi hospital\"",
  "\"PB Health Hospital\", \"PB Hospital\", \"PB Health Care\"",
  "\"MG Road\", \"IFFCO Chowk\" + \"open\"",
  "\"hospital bhi open\", \"hospital open ho gaya\", \"apna hospital open kiya\"",
].forEach((t) => children.push(bullet(t)));
children.push(p([run("Accuracy: ", { bold: true }), run("on 6,378 Gurgaon calls the new list was right 93% of the time when it said \"Pitched\" and caught 96% of real pitches (the old list: 58% and 90%). Full list and test results: PB_Health_Pitch_Keywords.xlsx.")]));

children.push(h1("9. For TLs: the call check"));
children.push(p("Use this when you listen to a call. Each line is a yes or no - coach the first \"no\"."));
children.push(table([3900, W - 3900], [["Did the advisor…", "What good sounds like"], ...CHECKS]));

children.push(h1("Appendix: approved facts"));
children.push(p("The only facts to use on calls. Source: PB Health sales team advisor guide, Oct 2026; confirmed by PB Health strategy, 21 Oct 2026. Check with PB Health ops before adding anything new."));
children.push(table([2200, W - 2200], [["Topic", "Approved wording"], ...FACTS]));
children.push(gap(80));
children.push(p([run("Not approved - don't say:", { bold: true, color: ORANGE })], { after: 60 }));
NOT_APPROVED.forEach((t) => children.push(bullet(t)));

const doc = new Document({
  creator: "PB Health Strategy", title: "PB Health Hospital - Advisor Playbook",
  styles: { default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, font: FONT, color: BLUE }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 24, bold: true, font: FONT, color: ORANGE }, paragraph: { spacing: { before: 220, after: 80 }, outlineLevel: 1 } },
    ] },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      tabStops: [{ type: TabStopType.RIGHT, position: W }],
      children: [run("PB Health Hospital  ·  Advisor Playbook  ·  v2, Oct 2026", { size: 16, color: GREY }),
                 new TextRun({ children: ["\tPage ", PageNumber.CURRENT], font: FONT, size: 16, color: GREY })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("written", OUT); });
