/**
 * PB Health Employee Awareness Survey: final edits to the live Google Form.
 *
 * What it changes:
 * 1. Replaces the "Floor" text box with two dropdowns: Office building and Floor.
 * 2. Keeps every question on one page. "How did you hear about PB Health Hospital?"
 *    moves to a short last page that opens only when someone answers Yes to
 *    "Do you know PB Health has its own hospital in Gurugram?". No submits from page 1.
 * 3. Moves the "Your PB Health benefits" page text into the thank-you message,
 *    so it shows after submit instead of as an extra page.
 *
 * How to use:
 * 1. Open https://script.google.com and click "New project".
 * 2. Delete the sample code, paste this whole file, and click Save.
 * 3. Pick "finaliseSurvey" in the function list at the top and click Run.
 *    Allow access when Google asks. Then check the Execution log.
 * Safe to run again: it skips anything already done.
 */

const FORM_ID = '1CB2OuwhG0H6_uJat89Q4UAdp8MP1ROXz2g3TC_57cXA';

const BUILDINGS = [
  'Gurgaon P - 28 - East Tower', 'Gurgaon P - 28 - West Tower', 'Gurgaon P - 47', 'Gurgaon P - 49',
  'Gurgaon P - 57', 'Gurgaon P - 84', 'Gurgaon P - 95', 'Gurgaon P - 105', 'Gurgaon P - 107',
  'Gurgaon P - 109', 'Gurgaon P - 110', 'Gurgaon P - 112', 'Gurgaon P - 113', 'Gurgaon P - 116',
  'Gurgaon P - 117', 'Gurgaon P - 119', 'Gurgaon P - 120', 'Gurgaon P - 129', 'Gurgaon P - 130',
  'Gurgaon P - 131', 'Gurgaon P - 135',
];
const FLOORS = ['B1', 'GF', '1st', '2nd', '3rd', '4th', '5th', '6th'];

const DEFAULT_BENEFITS = [
  'For you, spouse, kids, parents and in-laws',
  '',
  '75% off doctor consultation',
  '30% off X-ray, CT, MRI',
  'Free registration',
  'Free follow-up within 10 days',
  'Free ambulance within 10 km',
  '',
  'PB Health Hospital, IFFCO Chowk, Gurugram',
  'Helpline 1800 1201  |  Ambulance 1800 1203',
].join('\n');

function finaliseSurvey() {
  const form = FormApp.openById(FORM_ID);
  const T = FormApp.ItemType;

  // 1. Office building + Floor dropdowns, right after Department
  if (!findItem(form, T.LIST, 'Office building')) {
    const dept = findItem(form, T.TEXT, 'Department');
    const building = form.addListItem().setTitle('Office building').setChoiceValues(BUILDINGS).setRequired(true);
    const floor = form.addListItem().setTitle('Floor').setChoiceValues(FLOORS).setRequired(true);
    const at = dept ? dept.getIndex() + 1 : 3;
    form.moveItem(building.getIndex(), at);
    form.moveItem(floor.getIndex(), at + 1);
    Logger.log('Added Office building and Floor dropdowns');
  }
  const floorText = findItem(form, T.TEXT, 'Floor');
  if (floorText) {
    form.deleteItem(floorText);
    Logger.log('Removed the old Floor text box');
  }

  // 2. "Will you visit" becomes a plain question (its jumps pointed at the benefits page)
  const visit = findItem(form, T.MULTIPLE_CHOICE, 'Will you visit PB Health next time you need a doctor?');
  if (visit) {
    const mc = visit.asMultipleChoiceItem();
    mc.setChoiceValues(mc.getChoices().map(c => c.getValue()));
  } else {
    Logger.log('WARNING: "Will you visit" question not found');
  }

  // 3. Benefits page text goes to the thank-you message, page removed
  const benefits = findItem(form, T.PAGE_BREAK, 'Your PB Health benefits');
  if (benefits) {
    const text = benefits.asPageBreakItem().getHelpText() || DEFAULT_BENEFITS;
    form.setConfirmationMessage('Thank you! Your PB Health benefits:\n\n' + text);
    form.deleteItem(benefits);
    Logger.log('Moved the benefits page into the thank-you message');
  }

  // 4. "How did you hear" on a short last page
  const heardItem = findItem(form, T.MULTIPLE_CHOICE, 'How did you hear', true);
  if (!heardItem) throw new Error('"How did you hear about it?" question not found');
  const found = findItem(form, T.PAGE_BREAK, 'One last question');
  const page = found ? found.asPageBreakItem() : form.addPageBreakItem().setTitle('One last question');
  page.setGoToPage(FormApp.PageNavigationType.SUBMIT);
  const heard = heardItem.asMultipleChoiceItem();
  const hasOther = heard.hasOtherOption();
  heard
    .setTitle('How did you hear about PB Health Hospital?')
    .setChoiceValues(heard.getChoices().map(c => c.getValue()))
    .showOtherOption(hasOther);
  form.moveItem(heard.getIndex(), form.getItems().length - 1);

  // 5. Yes opens that page, No submits from page 1
  const knowsItem = findItem(form, T.MULTIPLE_CHOICE, 'Do you know PB Health has its own hospital in Gurugram?');
  if (!knowsItem) throw new Error('"Do you know PB Health has its own hospital" question not found');
  const knows = knowsItem.asMultipleChoiceItem();
  knows.setChoices([
    knows.createChoice('Yes', page),
    knows.createChoice('No', FormApp.PageNavigationType.SUBMIT),
  ]);
  Logger.log('Q1 now opens "How did you hear" only for Yes');

  Logger.log('Done. Form: ' + form.getPublishedUrl());
}

function findItem(form, type, title, startsWith) {
  const want = title.trim().toLowerCase();
  return form.getItems(type).find(i => {
    const t = (i.getTitle() || '').trim().toLowerCase();
    return startsWith ? t.startsWith(want) : t === want;
  }) || null;
}
