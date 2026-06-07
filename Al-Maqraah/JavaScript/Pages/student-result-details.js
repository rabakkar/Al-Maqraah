let studentResult = null;

const wordIssueLabels = {
  missing: "كلمة ناقصة",
  extra: "كلمة زائدة",
  different: "كلمة مختلفة",
  unmatched_word: "كلمة غير مطابقة"
};

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = value;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderEmpty(message = "لم يتم العثور على النتيجة المطلوبة.") {
  setText("studentScoreValue", "--");
  byId("studentScoreRing").style.setProperty("--score", "0deg");
  setText("studentResultSummary", message);
  setText("studentLevelBadge", "نتيجة الطالب");
  setText("studentLevelValue", "--");
  setText("studentSurahValue", "--");
  setText("studentRangeValue", "--");
  byId("pronunciationErrors").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  byId("studentRuleList").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function statusForCount(count) {
  return Number(count || 0) > 0 ? "mid" : "good";
}

function renderPronunciation(pronunciation) {
  const items = [
    { label: "كلمات ناقصة", value: pronunciation?.missing_words ?? 0 },
    { label: "كلمات زائدة", value: pronunciation?.extra_words ?? 0 },
    { label: "كلمات مختلفة", value: pronunciation?.different_words ?? 0 },
    { label: "كلمات غير مطابقة", value: pronunciation?.unmatched_words ?? 0 },
    { label: "درجة النطق", value: `${pronunciation?.score ?? "--"}%`, score: true }
  ];


  byId("pronunciationErrors").innerHTML = `
    ${items.map(item => `
      <article class="student-error-card ${item.score ? "score" : statusForCount(item.value)}">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </article>
    `).join("")}
  `;
}

function renderWordIssues(issues) {
  const visibleIssues = Array.isArray(issues) ? issues.filter(item => item.status !== "matched") : [];

  if (!visibleIssues.length) {
    return `<div class="student-issue-list empty-state">لا توجد كلمات تحتاج مراجعة في هذه التلاوة.</div>`;
  }

  return `
    <div class="student-issue-list">
      <h3>الكلمات التي تحتاج مراجعة</h3>
      ${visibleIssues.map(item => {
        const label = wordIssueLabels[item.status] || "ملاحظة";
        const text = item.status === "extra"
          ? (item.actual || "--")
          : (item.expected || "--");
        const note = item.status === "different" && item.actual
          ? `قُرئت: ${item.actual}`
          : label;

        return `
          <article class="student-word-issue ${escapeHtml(item.status || "")}">
            <span>${escapeHtml(label)}</span>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderRules(rules) {
  const visibleRules = (Array.isArray(rules) ? rules : [])
    .filter(rule => Number(rule.total || 0) > 0);

  if (!visibleRules.length) {
    byId("studentRuleList").innerHTML = `<div class="empty-state">لم تظهر أحكام مدرجة داخل نطاق هذه التلاوة.</div>`;
    return;
  }

  const appliedRules = visibleRules.filter(rule => Number(rule.passed || 0) > 0);
  const reviewRules = visibleRules.filter(rule => Number(rule.issues_count || 0) > 0);

  byId("studentRuleList").innerHTML = `
    ${renderRuleGroup("الأحكام التي طبقها الطالب", appliedRules, "good", "مطبق")}
    ${renderRuleGroup("الأحكام التي لم يطبقها الطالب", reviewRules, "mid", "يحتاج مراجعة")}
  `;
}

function renderRuleGroup(title, rules, statusClass, statusLabel) {
  if (!rules.length) {
    const message = statusClass === "good"
      ? "لا توجد أحكام مطبقة في هذه التلاوة."
      : "لا توجد أحكام تحتاج مراجعة في هذه التلاوة.";
    return `
      <section class="student-rule-group">
        <h3>${escapeHtml(title)}</h3>
        <div class="empty-state">${escapeHtml(message)}</div>
      </section>
    `;
  }

  return `
    <section class="student-rule-group">
      <h3>${escapeHtml(title)}</h3>
      ${rules.map(rule => {
        const passed = Number(rule.passed || 0);
        const issues = Number(rule.issues_count || 0);
        const value = statusClass === "good" ? passed : issues;
        const detail = statusClass === "good"
          ? `${value} موضع مطبق`
          : `${value} موضع يحتاج مراجعة`;

        return `
          <article class="student-rule-row student-rule-row--compact student-rule-row--${escapeHtml(statusClass)}">
            <div>
              <strong>${escapeHtml(rule.label)}</strong>
              <span>${escapeHtml(detail)}</span>
            </div>
            <span class="status ${escapeHtml(statusClass)}">${escapeHtml(statusLabel)}</span>
          </article>
        `;
      }).join("")}
    </section>
  `;
}

function renderStudentResult() {
  if (!studentResult) {
    renderEmpty();
    return;
  }

  const view = studentResult.student_view || {};
  const selection = studentResult.selection || {};
  const level = view.level || {};
  const score = Number(studentResult.score || 0);
  const levelLabel = level.label || level.level_label || "--";

  setText("studentScoreValue", `${score}%`);
  byId("studentScoreRing").style.setProperty("--score", `${score * 3.6}deg`);
  setText("studentLevelBadge", levelLabel !== "--" ? `المستوى: ${levelLabel}` : "نتيجة الطالب");
  setText("studentLevelValue", levelLabel);
  setText("studentSurahValue", selection.surah?.name || "--");
  setText("studentRangeValue", `${selection.ayah_from || "--"} إلى ${selection.ayah_to || "--"}`);
  setText(
    "studentResultSummary",
    levelLabel !== "--"
      ? `تم تصنيفك في مستوى ${levelLabel}. يمكنك الاطلاع على تفاصيل تقييم تلاوتك أدناه.`
      : "تم تحليل نتيجتك بنجاح."
  );

  renderPronunciation(view.pronunciation || {});
  renderRules(view.rules || []);
}

async function loadStudentResult() {
  const params = new URLSearchParams(window.location.search);
  const recitationId = params.get("recitation_id");

  if (!recitationId) {
    renderEmpty("اختر نتيجة من قائمة النتائج لعرضها.");
    return;
  }

  try {
    const meResponse = await fetch("/api/auth/me");
    const meData = await meResponse.json();
    if (meData.user?.role === "teacher") {
      window.location.replace(`result_details.html?recitation_id=${encodeURIComponent(recitationId)}`);
      return;
    }

    const response = await fetch(`/api/recitations/${encodeURIComponent(recitationId)}`);
    const data = await response.json();

    if (!response.ok || !data.result) {
      renderEmpty(data.error || "لم يتم العثور على النتيجة المطلوبة.");
      return;
    }

    studentResult = data.result;
    renderStudentResult();
  } catch (error) {
    renderEmpty("تعذر تحميل النتيجة من قاعدة البيانات.");
  }
}

loadStudentResult();
