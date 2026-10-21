// Question crops: a crop the pipeline turned into text (bank.texts, pipeline/qtext.py) is shown as that text,
// every other crop as its PNG. Callers keep using the crop path as the question's identity either way.
const texts = new Map();

/** Remember bank.texts of a loaded exam (api.loadExam calls this). */
export function registerTexts(bank) {
  for (const [path, html] of Object.entries(bank?.texts || {})) texts.set(path, html);
}

export const hasText = (path) => texts.has(path);

/** Markup for one crop. `cls` = classes of the <img> ("qimg", "qimg stem", "thumb"); the text block keeps them too. */
export function qimg(path, cls = 'qimg') {
  if (!path) return '';
  // bank html is built by the pipeline from the PDF text layer (escaped there), not user input
  if (texts.has(path)) return `<div class="${cls} qtext">${texts.get(path)}</div>`;
  return `<img class="${cls}" src="/${path}" loading="lazy">`;
}
