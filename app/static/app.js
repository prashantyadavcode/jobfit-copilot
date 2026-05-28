const analyzeBtn = document.getElementById('analyzeBtn');
const resumeFile = document.getElementById('resumeFile');
const jdText = document.getElementById('jdText');
const statusEl = document.getElementById('status');
const scoreEl = document.getElementById('score');
const summaryEl = document.getElementById('summary');
const matchedEl = document.getElementById('matched');
const missingEl = document.getElementById('missing');
const suggestionsEl = document.getElementById('suggestions');
const latexPanel = document.getElementById('latexPanel');
const latexCodeEl = document.getElementById('latexCode');
const rewriteBtn = document.getElementById('rewriteBtn');
const latexStatusEl = document.getElementById('latexStatus');
const sectionContainer = document.getElementById('sectionContainer');
const rewriteOutputEl = document.getElementById('rewriteOutput');

let latestAnalysis = null;
let extractedSections = [];
let extractTimer = null;

function renderList(el, items) {
  el.innerHTML = '';
  (items || []).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    el.appendChild(li);
  });
}

analyzeBtn.addEventListener('click', async () => {
  if (!resumeFile.files.length || !jdText.value.trim()) {
    statusEl.textContent = 'Please upload resume and paste job description.';
    return;
  }

  statusEl.textContent = 'Analyzing...';
  const formData = new FormData();
  formData.append('resume_file', resumeFile.files[0]);
  formData.append('jd_text', jdText.value);

  try {
    const res = await fetch('/analyze/mixed', { method: 'POST', body: formData });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    latestAnalysis = data;

    scoreEl.textContent = `Score: ${data.score}%`;
    summaryEl.textContent = `${data.matched_skills.length} matched skills · ${data.missing_skills.length} missing skills`;
    renderList(matchedEl, data.matched_skills);
    renderList(missingEl, data.missing_skills);
    renderList(suggestionsEl, data.suggestions);
    statusEl.textContent = 'Done.';
    latexPanel.classList.remove('hidden');
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  }
});

function renderSectionChecklist() {
  sectionContainer.innerHTML = '';
  extractedSections.forEach((section) => {
    const wrapper = document.createElement('label');
    wrapper.className = 'section-item';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = section.id;
    checkbox.checked = false;
    checkbox.addEventListener('change', updateRewriteButtonState);

    const text = document.createElement('span');
    text.textContent = section.title;

    wrapper.appendChild(checkbox);
    wrapper.appendChild(text);
    sectionContainer.appendChild(wrapper);
  });
  updateRewriteButtonState();
}

function getSelectedSectionIds() {
  return Array.from(
    sectionContainer.querySelectorAll('input[type="checkbox"]:checked')
  ).map((el) => el.value);
}

function updateRewriteButtonState() {
  const hasSelectedSections = getSelectedSectionIds().length > 0;
  rewriteBtn.disabled = !hasSelectedSections;
}

async function extractSectionsFromLatex() {
  const latexCode = latexCodeEl.value.trim();
  if (!latexCode) {
    extractedSections = [];
    sectionContainer.innerHTML = '';
    rewriteBtn.disabled = true;
    latexStatusEl.textContent = 'Paste LaTeX code to auto-extract sections.';
    return;
  }

  latexStatusEl.textContent = 'Extracting sections...';
  try {
    const res = await fetch('/latex/sections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latex_code: latexCode }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    extractedSections = data.sections || [];
    renderSectionChecklist();
    latexStatusEl.textContent = extractedSections.length
      ? `Found ${extractedSections.length} sections. Select at least one section to enable rewrite.`
      : 'No sections found. Ensure your LaTeX uses \\section{...}.';
  } catch (e) {
    rewriteBtn.disabled = true;
    latexStatusEl.textContent = `Error: ${e.message}`;
  }
}

latexCodeEl.addEventListener('input', () => {
  if (extractTimer) {
    clearTimeout(extractTimer);
  }
  extractTimer = setTimeout(() => {
    extractSectionsFromLatex();
  }, 400);
});

rewriteBtn.addEventListener('click', async () => {
  if (!latestAnalysis) {
    latexStatusEl.textContent = 'Run Step 1 analysis first.';
    return;
  }

  const latexCode = latexCodeEl.value.trim();
  if (!latexCode) {
    latexStatusEl.textContent = 'Paste LaTeX code first.';
    return;
  }

  const selectedSectionIds = getSelectedSectionIds();

  if (!selectedSectionIds.length) {
    latexStatusEl.textContent = 'Select at least one section.';
    return;
  }

  latexStatusEl.textContent = 'Rewriting selected sections...';
  try {
    const res = await fetch('/latex/rewrite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latex_code: latexCode,
        selected_section_ids: selectedSectionIds,
        jd_text: jdText.value,
        missing_skills: latestAnalysis.missing_skills || [],
        suggestions: latestAnalysis.suggestions || [],
      }),
    });
    if (!res.ok) {
      const message = await res.text();
      throw new Error(message);
    }
    const data = await res.json();
    rewriteOutputEl.value = data.merged_latex || 'No merged LaTeX returned.';
    latexStatusEl.textContent = data.message || 'Rewrite complete.';
  } catch (e) {
    latexStatusEl.textContent = `Error: ${e.message}`;
  }
});
