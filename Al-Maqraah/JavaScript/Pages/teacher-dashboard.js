const surahSelect = document.getElementById("surahSelect");
const assignmentForm = document.getElementById("assignmentForm");
const assignmentStatus = document.getElementById("assignmentStatus");
const studentsCount = document.getElementById("studentsCount");
const recitationsCount = document.getElementById("recitationsCount");
const averageScore = document.getElementById("averageScore");
const pendingAssignmentsCount = document.getElementById("pendingAssignmentsCount");
const studentProgressRows = document.getElementById("studentProgressRows");
const teacherAdminPanel = document.getElementById("teacherAdminPanel");
const teacherAdminNav = document.getElementById("teacherAdminNav");
const teacherCreateForm = document.getElementById("teacherCreateForm");
const teacherCreateStatus = document.getElementById("teacherCreateStatus");
const teacherRows = document.getElementById("teacherRows");
const dashboardHero = document.querySelector("[data-dashboard-hero]");
const dashboardViews = document.querySelectorAll("[data-dashboard-view]");
const dashboardTabTriggers = document.querySelectorAll("[data-dashboard-tab]");

const ASSIGNMENT_KEY = "maqraahAssignment";
let currentUser = null;
let activeStudentsLevel = "beginner";

function isAdminUser() {
  return currentUser?.role === "teacher" && currentUser?.is_admin;
}

function normalizeDashboardTab(tab) {
  const value = String(tab || "overview").replace("#", "");
  return ["overview", "assignments", "students", "teachers"].includes(value)
    ? value
    : "overview";
}

function setDashboardTab(tab, updateHash = true) {
  let activeTab = normalizeDashboardTab(tab);
  if (activeTab === "teachers" && !isAdminUser()) {
    activeTab = "overview";
  }

  dashboardViews.forEach(view => {
    const isActive = view.dataset.dashboardView === activeTab;
    view.hidden = !isActive;
    view.classList.toggle("is-active", isActive);
  });

  if (dashboardHero) {
    dashboardHero.hidden = activeTab !== "overview";
  }

  dashboardTabTriggers.forEach(trigger => {
    const isActive = trigger.dataset.dashboardTab === activeTab;
    trigger.classList.toggle("is-active", isActive);

    if (trigger.tagName === "A") {
      trigger.classList.toggle("active", isActive);
      trigger.setAttribute("aria-current", isActive ? "page" : "false");
    }
  });

  if (updateHash) {
    const nextPath = activeTab === "overview"
      ? window.location.pathname
      : `${window.location.pathname}#${activeTab}`;
    window.history.replaceState(null, "", nextPath);
  }
}

function initDashboardTabs() {
  dashboardTabTriggers.forEach(trigger => {
    trigger.addEventListener("click", event => {
      event.preventDefault();
      setDashboardTab(trigger.dataset.dashboardTab);
    });
  });

  setDashboardTab(window.location.hash || "overview", false);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatAssignment(task) {
  return {
    id: task.id,
    studentName: task.student_name,
    studentId: task.student_id,
    surah: task.surah_number,
    surahName: task.surah_name,
    fromAyah: task.ayah_from,
    toAyah: task.ayah_to,
    ayahText: task.ayah_text,
    stats: task.stats,
    createdAt: task.created_at
  };
}

function renderDashboardStats(stats) {
  studentsCount.textContent = stats.students_count || 0;
  recitationsCount.textContent = stats.recitations_count || 0;
  averageScore.textContent = `${stats.average_score || 0}%`;
  pendingAssignmentsCount.textContent = stats.pending_assignments_count || 0;
}

function renderStudentProgress(students) {
  if (!students.length) {
    studentProgressRows.innerHTML = `<div class="empty-state">لا يوجد طلاب مسجلون حتى الآن.</div>`;
    return;
  }

  const levels = [
    { key: "beginner", label: "مبتدئ" },
    { key: "intermediate", label: "متوسط" },
    { key: "advanced", label: "متقدم" }
  ];
  const grouped = {
    beginner: [],
    intermediate: [],
    advanced: []
  };
  const unclassified = [];

  students.forEach(student => {
    if (grouped[student.student_level]) {
      grouped[student.student_level].push(student);
    } else {
      unclassified.push(student);
    }
  });

  function renderStudentRow(student) {
    const hasRecitation = Boolean(student.recitation_id);
    const issuesCount = student.issues_count || 0;
    const score = hasRecitation ? `${student.score || 0}%` : "--";
    const statusClass = !hasRecitation ? "mid" : issuesCount > 0 ? "mid" : "good";
    const statusText = !hasRecitation
      ? "لم يسمع بعد"
      : issuesCount > 0
        ? `${issuesCount} ملاحظة`
        : "مكتمل";
    const lastRecitation = hasRecitation
      ? `آخر تلاوة: ${student.surah_name} - الآيات ${student.ayah_from} إلى ${student.ayah_to}`
      : student.pending_assignments_count > 0
        ? `لديه ${student.pending_assignments_count} تكليف معلق`
        : "لا توجد قراءات أو تكليفات بعد";
    const levelLabel = student.student_level_label || "مبتدئ";
    const resultLink = hasRecitation
      ? `<a href="teacher-student-results.html?student_id=${student.id}" class="status ${statusClass}">نتائج الطالب</a>`
      : `<span class="status ${statusClass}">${statusText}</span>`;

    return `
      <div class="student-row">
        <div>
          <strong>${escapeHtml(student.full_name)}</strong>
          <span>${escapeHtml(levelLabel)} - ${escapeHtml(lastRecitation)}</span>
        </div>
        <div class="student-row__footer">
          <p>${score}</p>
          ${resultLink}
        </div>
      </div>
    `;
  }

  if (activeStudentsLevel === "unclassified" && !unclassified.length) {
    activeStudentsLevel = "beginner";
  }
  if (activeStudentsLevel !== "unclassified" && !levels.some(level => level.key === activeStudentsLevel)) {
    activeStudentsLevel = "beginner";
  }

  const activeLevel = levels.find(level => level.key === activeStudentsLevel) || levels[0];
  const activeLevelStudents = grouped[activeLevel.key] || [];

  const levelCards = levels.map(level => {
    const levelStudents = grouped[level.key] || [];
    const isActive = level.key === activeLevel.key;

    return `
      <button class="student-level-card student-level-toggle-card ${level.key} ${isActive ? "is-active" : ""}" type="button" data-student-level="${level.key}">
        <div class="student-level-card__head">
          <strong>${escapeHtml(level.label)}</strong>
          <span>${escapeHtml(levelStudents.length)} طالب</span>
        </div>
      </button>
    `;
  }).join("");

  const pendingCard = unclassified.length
    ? `
      <button class="student-level-card student-level-toggle-card student-level-card--pending ${activeStudentsLevel === "unclassified" ? "is-active" : ""}" type="button" data-student-level="unclassified">
        <div class="student-level-card__head">
          <strong>بانتظار تحديد المستوى</strong>
          <span>${escapeHtml(unclassified.length)} طالب</span>
        </div>
      </button>
    `
    : "";

  const selectedStudents = activeStudentsLevel === "unclassified"
    ? unclassified
    : activeLevelStudents;
  const selectedLabel = activeStudentsLevel === "unclassified"
    ? "بانتظار تحديد المستوى"
    : activeLevel.label;
  const selectedRows = selectedStudents.length
    ? selectedStudents.map(renderStudentRow).join("")
    : `<div class="empty-state">لا يوجد طلاب في هذا المستوى.</div>`;

  studentProgressRows.innerHTML = `
    <div class="student-level-grid">
      ${levelCards}
      ${pendingCard}
    </div>
    <section class="student-level-detail">
      <div class="student-level-detail__head">
        <strong>${escapeHtml(selectedLabel)}</strong>
        <span>${escapeHtml(selectedStudents.length)} طالب</span>
      </div>
      <div class="student-level-list">${selectedRows}</div>
    </section>
  `;

  studentProgressRows.querySelectorAll("[data-student-level]").forEach(button => {
    button.addEventListener("click", () => {
      activeStudentsLevel = button.dataset.studentLevel || "beginner";
      renderStudentProgress(students);
    });
  });
}

async function loadDashboardData() {
  try {
    const response = await fetch("/api/teacher/dashboard");
    const data = await response.json();

    if (!response.ok) {
      studentProgressRows.innerHTML = `<div class="empty-state">${escapeHtml(data.error || "تعذر تحميل لوحة المعلم.")}</div>`;
      return;
    }

    renderDashboardStats(data.stats || {});
    renderStudentProgress(data.students || []);
  } catch (error) {
    studentProgressRows.innerHTML = `<div class="empty-state">تعذر تحميل بيانات لوحة المعلم من قاعدة البيانات.</div>`;
  }
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    currentUser = data.user;

    const isAdmin = isAdminUser();
    teacherAdminPanel.hidden = !isAdmin;
    if (teacherAdminNav) {
      teacherAdminNav.style.display = isAdmin ? "" : "none";
    }

    if (isAdmin) {
      loadTeachers();
    }
    return currentUser;
  } catch (error) {
    teacherAdminPanel.hidden = true;
    if (teacherAdminNav) {
      teacherAdminNav.style.display = "none";
    }
    return null;
  }
}

async function loadTeachers() {
  try {
    const response = await fetch("/api/teachers");
    const data = await response.json();
    const teachers = data.teachers || [];

    if (!teachers.length) {
      teacherRows.innerHTML = `<div class="empty-state">لا يوجد معلمون مضافون بعد.</div>`;
      return;
    }

    teacherRows.innerHTML = teachers.map(teacher => `
      <div class="teacher-row">
        <div>
          <strong>${escapeHtml(teacher.full_name)}</strong>
          <span>${escapeHtml(teacher.email)}</span>
        </div>
        <span class="status ${teacher.is_admin ? "good" : "mid"}">
          ${teacher.is_admin ? "أدمن" : "معلم"}
        </span>
      </div>
    `).join("");
  } catch (error) {
    teacherRows.innerHTML = `<div class="empty-state">تعذر تحميل قائمة المعلمين.</div>`;
  }
}

async function loadSurahs() {
  try {
    const response = await fetch("/api/surahs");
    const data = await response.json();

    surahSelect.innerHTML = data.surahs.map(surah => `
      <option value="${surah.index}" data-name="${surah.name}">${surah.index}. ${surah.name}</option>
    `).join("");

    surahSelect.value = "67";
  } catch (error) {
    surahSelect.innerHTML = `<option value="67" data-name="الملك">67. الملك</option>`;
    assignmentStatus.textContent = "تعذر تحميل السور من الخادم.";
  }
}

assignmentForm.addEventListener("submit", async event => {
  event.preventDefault();

  const selectedSurah = surahSelect.selectedOptions[0];
  const ayahFrom = Number(document.getElementById("ayahFrom").value);
  const ayahTo = Number(document.getElementById("ayahTo").value);

  if (ayahFrom > ayahTo) {
    assignmentStatus.textContent = "تأكد أن بداية نطاق الآيات لا تتجاوز نهايته.";
    return;
  }

  assignmentStatus.textContent = "جاري حفظ التكليف...";

  try {
    const response = await fetch("/api/assignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        surah: Number(surahSelect.value),
        surah_name: selectedSurah?.dataset.name || selectedSurah?.textContent || "الملك",
        from: ayahFrom,
        to: ayahTo
      })
    });
    const data = await response.json();

    if (!response.ok) {
      assignmentStatus.textContent = data.error || "تعذر حفظ التكليف.";
      return;
    }

    localStorage.setItem(ASSIGNMENT_KEY, JSON.stringify(formatAssignment(data.assignment)));
    assignmentStatus.textContent = "تم حفظ التكليف في قاعدة البيانات وسيظهر للطالب.";
    loadDashboardData();
  } catch (error) {
    assignmentStatus.textContent = "تعذر الاتصال بالخادم.";
    console.error(error);
  }
});

teacherCreateForm.addEventListener("submit", async event => {
  event.preventDefault();

  const fullName = document.getElementById("teacherFullName").value.trim();
  const email = document.getElementById("teacherEmail").value.trim();
  const password = document.getElementById("teacherPassword").value;
  const isAdmin = document.getElementById("teacherIsAdmin").checked;

  if (!fullName || !email || !password) {
    teacherCreateStatus.textContent = "الرجاء تعبئة بيانات المعلم.";
    return;
  }

  teacherCreateStatus.textContent = "جاري إضافة المعلم...";

  try {
    const response = await fetch("/api/teachers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        email,
        password,
        is_admin: isAdmin
      })
    });
    const data = await response.json();

    if (!response.ok) {
      teacherCreateStatus.textContent = data.error || "تعذر إضافة المعلم.";
      return;
    }

    teacherCreateForm.reset();
    teacherCreateStatus.textContent = "تمت إضافة المعلم بنجاح.";
    loadTeachers();
  } catch (error) {
    teacherCreateStatus.textContent = "تعذر الاتصال بالخادم.";
    console.error(error);
  }
});

async function initTeacherDashboard() {
  await loadCurrentUser();
  initDashboardTabs();
  loadDashboardData();
  loadSurahs();
}

initTeacherDashboard();
