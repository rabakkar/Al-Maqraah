const teacherStudentResultsTitle = document.getElementById("teacherStudentResultsTitle");
const teacherStudentResultsSummary = document.getElementById("teacherStudentResultsSummary");
const teacherStudentResultsList = document.getElementById("teacherStudentResultsList");

let currentTeacherStudent = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function summarizeIssues(summary) {
  const ruleIssues = (summary?.needs_review || 0) + (summary?.unmatched || 0);
  const verification = summary?.recitation_verification || {};
  return ruleIssues
    + Number(verification.missing_words || 0)
    + Number(verification.extra_words || 0)
    + Number(verification.different_words || 0)
    + Number(verification.unmatched_words || 0);
}

function levelLabelFromResult(item) {
  const level = item.summary?.scoring_level || item.summary?.placement?.selected || {};
  return level.label || level.level_label || "--";
}

function renderResults(recitations) {
  const studentName = currentTeacherStudent?.full_name || recitations[0]?.student_name || "الطالب";
  teacherStudentResultsTitle.textContent = `نتائج ${studentName}`;
  teacherStudentResultsSummary.textContent = recitations.length
    ? `يعرض هذا السجل النتائج المحفوظة لهذا الطالب.`
    : "لا توجد نتائج محفوظة لهذا الطالب حتى الآن.";

  if (!recitations.length) {
    teacherStudentResultsList.innerHTML = `<div class="empty-state">لا توجد نتائج محفوظة لهذا الطالب حتى الآن.</div>`;
    return;
  }

  teacherStudentResultsList.innerHTML = recitations.map(item => {
    const issuesCount = summarizeIssues(item.summary);
    const statusClass = issuesCount > 0 ? "mid" : "good";
    const statusText = issuesCount > 0 ? `${issuesCount} ملاحظة` : "مكتملة";

    return `
      <button class="result-list-row" type="button" data-recitation-id="${escapeHtml(item.id)}">
        <div>
          <strong>${escapeHtml(item.surah_name)}</strong>
          <span>الآيات ${escapeHtml(item.ayah_from)} إلى ${escapeHtml(item.ayah_to)} - المستوى: ${escapeHtml(levelLabelFromResult(item))} - ${escapeHtml(item.created_at)}</span>
        </div>
        <p>${escapeHtml(item.score || 0)}%</p>
        <span class="status ${statusClass}">${escapeHtml(statusText)}</span>
      </button>
    `;
  }).join("");

  teacherStudentResultsList.querySelectorAll("[data-recitation-id]").forEach(button => {
    button.addEventListener("click", () => {
      window.location.href = `result_details.html?recitation_id=${encodeURIComponent(button.dataset.recitationId)}`;
    });
  });
}

async function loadStudentName(studentId) {
  try {
    const response = await fetch("/api/students");
    const data = await response.json();
    currentTeacherStudent = (data.students || []).find(student => String(student.id) === String(studentId)) || null;
  } catch (error) {
    currentTeacherStudent = null;
  }
}

async function loadTeacherStudentResults() {
  const params = new URLSearchParams(window.location.search);
  const studentId = params.get("student_id");

  if (!studentId) {
    teacherStudentResultsTitle.textContent = "نتائج الطالب";
    teacherStudentResultsSummary.textContent = "اختر طالبا من صفحة الطلاب لعرض نتائجه.";
    teacherStudentResultsList.innerHTML = `<div class="empty-state">لم يتم تحديد الطالب المطلوب.</div>`;
    return;
  }

  try {
    const meResponse = await fetch("/api/auth/me");
    const meData = await meResponse.json();
    const teacherAdminNav = document.getElementById("teacherAdminNav");
    if (teacherAdminNav) {
      const isAdmin = meData.user?.role === "teacher" && meData.user?.is_admin;
      teacherAdminNav.style.display = isAdmin ? "" : "none";
    }

    if (meData.user?.role !== "teacher") {
      window.location.replace("result.html");
      return;
    }

    await loadStudentName(studentId);

    const response = await fetch(`/api/recitations?student_id=${encodeURIComponent(studentId)}`);
    const data = await response.json();

    if (!response.ok) {
      teacherStudentResultsList.innerHTML = `<div class="empty-state">${escapeHtml(data.error || "تعذر تحميل نتائج الطالب.")}</div>`;
      return;
    }

    renderResults(data.recitations || []);
  } catch (error) {
    teacherStudentResultsList.innerHTML = `<div class="empty-state">تعذر تحميل نتائج الطالب من قاعدة البيانات.</div>`;
  }
}

loadTeacherStudentResults();
