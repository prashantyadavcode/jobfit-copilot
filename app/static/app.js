const analyzeBtn = document.getElementById('analyzeBtn');
const resumeFile = document.getElementById('resumeFile');
const resumeDropZone = document.getElementById('resumeDropZone');
const resumeFileName = document.getElementById('resumeFileName');
const jdText = document.getElementById('jdText');
const statusEl = document.getElementById('status');

const ACCEPTED_RESUME_EXTENSIONS = ['.pdf', '.docx', '.txt'];

function isAcceptedResumeFile(file) {
  const name = (file?.name || '').toLowerCase();
  return ACCEPTED_RESUME_EXTENSIONS.some((ext) => name.endsWith(ext));
}

function setResumeFile(file) {
  if (!file || !isAcceptedResumeFile(file)) {
    statusEl.textContent = 'Only PDF, DOCX, and TXT files are accepted.';
    return;
  }
  const dt = new DataTransfer();
  dt.items.add(file);
  resumeFile.files = dt.files;
  resumeDropZone.classList.add('has-file');
  resumeFileName.textContent = file.name;
  resumeFileName.classList.remove('hidden');
  statusEl.textContent = '';
  updateAnalyzeFormState();
}

resumeDropZone.addEventListener('click', () => resumeFile.click());

resumeDropZone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    resumeFile.click();
  }
});

resumeFile.addEventListener('change', () => {
  const file = resumeFile.files[0];
  if (file) setResumeFile(file);
});

['dragenter', 'dragover'].forEach((eventName) => {
  resumeDropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    resumeDropZone.classList.add('is-dragover');
  });
});

resumeDropZone.addEventListener('dragleave', (e) => {
  e.preventDefault();
  if (!resumeDropZone.contains(e.relatedTarget)) {
    resumeDropZone.classList.remove('is-dragover');
  }
});

resumeDropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  resumeDropZone.classList.remove('is-dragover');
  const file = e.dataTransfer?.files?.[0];
  if (file) setResumeFile(file);
});

const matchResultPanel = document.getElementById('matchResultPanel');

function isAnalyzeFormReady() {
  return resumeFile.files.length > 0 && jdText.value.trim().length > 0;
}

function updateAnalyzeFormState() {
  const ready = isAnalyzeFormReady();
  analyzeBtn.disabled = !ready;
  analyzeBtn.classList.toggle('btn-ocean', ready);
}

jdText.addEventListener('input', updateAnalyzeFormState);

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
const downloadLatexBtn = document.getElementById('downloadLatexBtn');
const downloadRewriteBtn = document.getElementById('downloadRewriteBtn');

function downloadTextFile(content, filename) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function updateDownloadButtons() {
  if (downloadLatexBtn) {
    downloadLatexBtn.disabled = !latexCodeEl.value.trim();
  }
  if (downloadRewriteBtn) {
    downloadRewriteBtn.disabled = !rewriteOutputEl.value.trim();
  }
}

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

    scoreEl.textContent = `${data.score}%`;
    summaryEl.textContent = `${data.matched_skills.length} matched skills · ${data.missing_skills.length} missing skills`;
    renderList(matchedEl, data.matched_skills);
    renderList(missingEl, data.missing_skills);
    renderList(suggestionsEl, data.suggestions);
    statusEl.textContent = 'Done.';
    matchResultPanel.classList.remove('hidden');
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
  rewriteBtn.classList.toggle('btn-ocean', hasSelectedSections);
}

async function extractSectionsFromLatex() {
  const latexCode = latexCodeEl.value.trim();
  if (!latexCode) {
    extractedSections = [];
    sectionContainer.innerHTML = '';
    rewriteBtn.disabled = true;
    rewriteBtn.classList.remove('btn-ocean');
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
    rewriteBtn.classList.remove('btn-ocean');
    latexStatusEl.textContent = `Error: ${e.message}`;
  }
}

latexCodeEl.addEventListener('input', () => {
  updateDownloadButtons();
  if (extractTimer) {
    clearTimeout(extractTimer);
  }
  extractTimer = setTimeout(() => {
    extractSectionsFromLatex();
  }, 400);
});

downloadLatexBtn.addEventListener('click', () => {
  const content = latexCodeEl.value.trim();
  if (!content) return;
  downloadTextFile(content, 'resume.tex');
});

downloadRewriteBtn.addEventListener('click', () => {
  const content = rewriteOutputEl.value.trim();
  if (!content) return;
  downloadTextFile(content, 'resume_rewritten.tex');
});

rewriteBtn.addEventListener('click', async () => {
  if (!latestAnalysis) {
    latexStatusEl.textContent = 'Run Analyze Match first.';
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
        matched_skills: latestAnalysis.matched_skills || [],
        suggestions: latestAnalysis.suggestions || [],
      }),
    });
    if (!res.ok) {
      const raw = await res.text();
      let message = raw;
      try {
        const err = JSON.parse(raw);
        message = typeof err.detail === 'string' ? err.detail : raw;
      } catch {
        // keep raw body
      }
      throw new Error(message);
    }
    const data = await res.json();
    rewriteOutputEl.value = data.merged_latex || 'No merged LaTeX returned.';
    updateDownloadButtons();
    latexStatusEl.textContent = data.message || 'Rewrite complete.';
  } catch (e) {
    latexStatusEl.textContent = `Error: ${e.message}`;
  }
});
