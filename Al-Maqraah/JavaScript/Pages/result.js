const resultsList = document.getElementById("resultsList");
let currentUser = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function summarizeIssues(summary) {
  return (summary?.needs_review || 0) + (summary?.unmatched || 0);
}

function renderResultsList(recitations) {
  if (!recitations.length) {
    resultsList.innerHTML = `<div class="empty-state">لا توجد نتائج محفوظة لهذا الطالب حتى الآن.</div>`;
    return;
  }

  resultsList.innerHTML = recitations.map(item => {
    const issuesCount = summarizeIssues(item.summary);
    const statusClass = issuesCount > 0 ? "mid" : "good";
    const statusText = issuesCount > 0 ? `${issuesCount} ملاحظة` : "مكتملة";
    const level = item.summary?.scoring_level || item.summary?.placement?.selected || {};
    const levelLabel = level.label || level.level_label || "--";

    return `
      <button class="result-list-row" type="button" data-recitation-id="${item.id}">
        <div>
          <strong>${escapeHtml(item.surah_name)}</strong>
          <span>الآيات ${escapeHtml(item.ayah_from)} إلى ${escapeHtml(item.ayah_to)} - المستوى: ${escapeHtml(levelLabel)} - ${escapeHtml(item.created_at)}</span>
        </div>
        <p>${item.score || 0}%</p>
        <span class="status ${statusClass}">${statusText}</span>
      </button>
    `;
  }).join("");

  resultsList.querySelectorAll("[data-recitation-id]").forEach(button => {
    button.addEventListener("click", () => {
      const targetPage = currentUser?.role === "student"
        ? "student-result-details.html"
        : "result_details.html";
      window.location.href = `${targetPage}?recitation_id=${encodeURIComponent(button.dataset.recitationId)}`;
    });
  });
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    currentUser = data.user || null;
  } catch (error) {
    currentUser = null;
  }
}

async function loadResultsList() {
  const params = new URLSearchParams(window.location.search);
  const studentId = params.get("student_id");
  const listUrl = studentId
    ? `/api/recitations?student_id=${encodeURIComponent(studentId)}`
    : "/api/recitations";

  try {
    const response = await fetch(listUrl);
    const data = await response.json();
    renderResultsList(data.recitations || []);
  } catch (error) {
    resultsList.innerHTML = `<div class="empty-state">تعذر تحميل قائمة النتائج من قاعدة البيانات.</div>`;
  }
}

async function initResultsPage() {
  await loadCurrentUser();
  await loadResultsList();
}

initResultsPage();
