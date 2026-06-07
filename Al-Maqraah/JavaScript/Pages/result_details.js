let result = null;
let currentUser = null;

const ruleLabels = {
  izhar: "إظهار",
  idgham: "إدغام",
  iqlab: "إقلاب",
  ikhfa: "إخفاء",
  pronunciation: "النطق",
  missing_words: "خصم الكلمات الناقصة",
  extra_words: "خصم الكلمات الزائدة",
  different_words: "خصم الكلمات المختلفة",
  unmatched_words: "خصم الكلمات غير المطابقة"
};

const statusClasses = {
  passed: "passed",
  needs_review: "review",
  unmatched: "unmatched"
};

const statusLabels = {
  passed: "مطابق",
  needs_review: "يحتاج مراجعة",
  unmatched: "غير محدد"
};

const wordStatusLabels = {
  matched: "مطابقة",
  missing: "ناقصة",
  extra: "زائدة",
  different: "مختلفة",
  unmatched_word: "غير مطابقة",
  ignored_rule_word: "مستثناة بسبب الحكم"
};

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getAnalysis() {
  return result?.rule_analysis || {};
}

function getSummary() {
  return getAnalysis().summary || {
    total: 0,
    passed: 0,
    needs_review: 0,
    unmatched: 0,
    by_rule: {}
  };
}

function getEvaluations() {
  return Array.isArray(getAnalysis().evaluations) ? getAnalysis().evaluations : [];
}

function getPhoneticText() {
  const script = result?.phonetic_script;

  if (!script) return "--";
  if (typeof script === "string") return script;
  if (script.text) return script.text;
  if (Array.isArray(script.tokens)) return script.tokens.map(item => item.token || "").join("");
  return JSON.stringify(script, null, 2);
}

function isStudentViewer() {
  return currentUser?.role === "student";
}

function percentage(part, total) {
  return total ? Math.round((part / total) * 100) : 0;
}

function renderEmptyDetails(message = "لم يتم العثور على النتيجة المطلوبة.") {
  byId("scoreValue").textContent = "--";
  byId("scoreRing").style.setProperty("--score", "0deg");
  byId("resultSummary").textContent = message;
  byId("resultLevel").textContent = "--";
  byId("resultSurah").textContent = "--";
  byId("resultRange").textContent = "--";
  const audioFileName = byId("audioFileName");
  if (audioFileName) {
    audioFileName.textContent = "--";
  }
  byId("summaryTotal").textContent = "0";
  byId("summaryPassed").textContent = "0";
  byId("summaryReview").textContent = "0";
  byId("summaryUnmatched").textContent = "0";
  byId("referenceLetters").textContent = "--";
  byId("predictedLetters").textContent = "--";
  byId("mappedLetters").textContent = "--";
  byId("phoneticOutput").textContent = "--";
  byId("scoreComponents").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  byId("heardTranscript").textContent = "--";
  byId("normalizedTranscript").textContent = "--";
  byId("wordEvaluationList").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  byId("ruleTable").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  byId("evaluationsList").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderScoreComponents(summary) {
  const weighted = summary.weighted_score || {};
  const components = Array.isArray(weighted.components) ? weighted.components : [];
  const verification = summary.recitation_verification || result?.recitation_verification || {};

  if (!components.length) {
    byId("scoreComponents").innerHTML = `<div class="empty-state">لا توجد تفاصيل أوزان محفوظة لهذه النتيجة.</div>`;
    return;
  }

  const rows = components.map(item => {
    const isPenalty = item.type === "penalty";
    const detail = isPenalty
      ? `${item.count || 0} × ${item.weight ?? 0}`
      : (item.total ? `${item.passed || 0} / ${item.total}` : "--");
    const score = isPenalty ? `${item.score ?? 0}` : `${item.score ?? 0}%`;

    return `
      <div class="score-component-row">
        <strong>${escapeHtml(ruleLabels[item.key] || item.key)}</strong>
        <span>${escapeHtml(score)}</span>
        <span>${escapeHtml(item.weight ?? 0)}</span>
        <span>${escapeHtml(detail)}</span>
      </div>
    `;
  }).join("");

  byId("scoreComponents").innerHTML = `
    <div class="score-component-row score-component-row--head">
      <strong>العنصر</strong>
      <span>درجة النظام</span>
      <span>الوزن</span>
      <span>التفاصيل</span>
    </div>
    ${rows}
    <div class="pronunciation-metrics">
      <span>كلمات ناقصة: <strong>${escapeHtml(verification.missing_words ?? 0)}</strong></span>
      <span>كلمات زائدة: <strong>${escapeHtml(verification.extra_words ?? 0)}</strong></span>
      <span>كلمات مختلفة: <strong>${escapeHtml(verification.different_words ?? 0)}</strong></span>
      <span>كلمات غير مطابقة: <strong>${escapeHtml(verification.unmatched_words ?? 0)}</strong></span>
      <span>درجة النطق: <strong>${escapeHtml(verification.pronunciation_score ?? "--")}%</strong></span>
    </div>
  `;
}

function renderPronunciationDetails(summary) {
  const verification = summary.recitation_verification || result?.recitation_verification || {};
  const words = Array.isArray(verification.word_evaluations) ? verification.word_evaluations : [];
  const pronunciationMatch = byId("pronunciationMatch");

  if (pronunciationMatch) {
    pronunciationMatch.hidden = isStudentViewer();
  }

  if (isStudentViewer()) {
    const missingWords = words.filter(item => item.status === "missing");

    if (!missingWords.length) {
      byId("wordEvaluationList").innerHTML = `<div class="empty-state">لا توجد كلمات ناقصة في هذه القراءة.</div>`;
      return;
    }

    byId("wordEvaluationList").innerHTML = `
      <div class="word-evaluation-row word-evaluation-row--head word-evaluation-row--missing-only">
        <span>الحالة</span>
        <strong>الكلمة الناقصة</strong>
      </div>
      ${missingWords.map(item => `
        <div class="word-evaluation-row missing word-evaluation-row--missing-only">
          <span>${escapeHtml(wordStatusLabels.missing)}</span>
          <strong>${escapeHtml(item.expected || "--")}</strong>
        </div>
      `).join("")}
    `;
    return;
  }

  byId("heardTranscript").textContent = verification.transcript || "لم يسجل النظام نصًا مسموعًا واضحًا.";
  byId("normalizedTranscript").textContent = verification.normalized_transcript || "--";

  if (!words.length) {
    byId("wordEvaluationList").innerHTML = `<div class="empty-state">لا توجد تفاصيل كلمات محفوظة لهذه النتيجة.</div>`;
    return;
  }

  byId("wordEvaluationList").innerHTML = `
    <div class="word-evaluation-row word-evaluation-row--head">
      <span>الحالة</span>
      <strong>الكلمة المطلوبة</strong>
      <strong>الكلمة المسموعة</strong>
    </div>
    ${words.map(item => {
      const status = item.status || "different";
      return `
        <div class="word-evaluation-row ${escapeHtml(status)}">
          <span>${escapeHtml(wordStatusLabels[status] || status)}</span>
          <strong>${escapeHtml(item.expected || "--")}</strong>
          <strong>${escapeHtml(item.actual || "--")}</strong>
        </div>
      `;
    }).join("")}
  `;
}

function renderRuleTable(summary) {
  const rows = ["izhar", "idgham", "iqlab", "ikhfa"].map(rule => {
    const item = summary.by_rule?.[rule] || {};

    return `
      <div class="rule-row">
        <strong>${ruleLabels[rule]}</strong>
        <span>${item.total || 0}</span>
        <span class="passed-text">${item.passed || 0}</span>
        <span class="review-text">${item.needs_review || 0}</span>
        <span>${item.unmatched || 0}</span>
      </div>
    `;
  }).join("");

  byId("ruleTable").innerHTML = `
    <div class="rule-row rule-row--head">
      <strong>الحكم</strong>
      <span>الإجمالي</span>
      <span>مطابق</span>
      <span>مراجعة</span>
      <span>غير محدد</span>
    </div>
    ${rows}
  `;
}

function renderEvaluations(evaluations) {
  if (evaluations.length === 0) {
    byId("evaluationsList").innerHTML = `<div class="empty-state">لم يجد النظام مواضع تفصيلية في نطاق الآيات المحدد.</div>`;
    return;
  }

  byId("evaluationsList").innerHTML = evaluations.map(item => {
    const status = item.status || "unmatched";
    const statusClass = statusClasses[status] || "unmatched";
    const label = item.status_label || statusLabels[status] || status;
    const rule = item.rule_label || ruleLabels[item.rule] || item.rule || "حكم غير محدد";
    const sourceLabel = item.source_label || (item.source_type === "tanween" ? "تنوين" : "نون ساكنة");
    const detail = item.rule_detail ? `<span>${escapeHtml(item.rule_detail)}</span>` : "";
    const phoneticWindow = item.phonetic_window || item.phonetic_window_letters || "--";

    return `
      <article class="evaluation-card ${statusClass}">
        <div class="evaluation-card__head">
          <div>
            <strong>${escapeHtml(rule)}</strong>
            <p>${escapeHtml(sourceLabel)} ${detail}</p>
          </div>
          <span class="analysis-status ${statusClass}">${escapeHtml(label)}</span>
        </div>

        <div class="evaluation-snippet">${escapeHtml(item.snippet || item.source_text || "--")}</div>

        <div class="evaluation-meta">
          <span>الآية: <strong>${escapeHtml(item.ayah || "--")}</strong></span>
          <span>الحرف التالي: <strong>${escapeHtml(item.next_letter || "--")}</strong></span>
          <span>ظهور النون: <strong>${item.noon_visible === null || item.noon_visible === undefined ? "--" : item.noon_visible ? "نعم" : "لا"}</strong></span>
          <span>ظهور الميم: <strong>${item.meem_visible === null || item.meem_visible === undefined ? "--" : item.meem_visible ? "نعم" : "لا"}</strong></span>
        </div>

        <p class="evaluation-reason">${escapeHtml(item.reason || "لا توجد ملاحظة تفصيلية لهذا الموضع.")}</p>

        <div class="phonetic-window">
          <span>النافذة الصوتية</span>
          <code>${escapeHtml(phoneticWindow)}</code>
        </div>
      </article>
    `;
  }).join("");
}

function renderResultDetails() {
  if (!result) {
    renderEmptyDetails();
    return;
  }

  const summary = getSummary();
  const evaluations = getEvaluations();
  const selection = result.selection || {};
  const score = result.score ?? percentage(summary.passed || 0, summary.total || 0);
  const alignment = getAnalysis().alignment || {};
  const level = summary.scoring_level || summary.placement?.selected || result?.student_view?.level || {};

  byId("scoreValue").textContent = `${score}%`;
  byId("scoreRing").style.setProperty("--score", `${score * 3.6}deg`);
  const placement = summary.placement?.selected;
  byId("resultSummary").textContent = placement
    ? `تم تحليل التلاوة وتصنيف الطالب في مستوى ${placement.level_label}.`
    : "تم تحليل أحكام النون الساكنة والتنوين بنجاح.";
  byId("resultLevel").textContent = level.label || level.level_label || "--";
  byId("resultSurah").textContent = selection.surah?.name || selection.surah || "--";
  byId("resultRange").textContent = `${selection.ayah_from || "--"} إلى ${selection.ayah_to || "--"}`;
  const audioFileName = byId("audioFileName");
  if (audioFileName) {
    audioFileName.textContent = "";
  }
  byId("summaryTotal").textContent = summary.total || 0;
  byId("summaryPassed").textContent = summary.passed || 0;
  byId("summaryReview").textContent = summary.needs_review || 0;
  byId("summaryUnmatched").textContent = summary.unmatched || 0;
  byId("referenceLetters").textContent = alignment.reference_letters ?? "--";
  byId("predictedLetters").textContent = alignment.predicted_letters ?? "--";
  byId("mappedLetters").textContent = alignment.mapped_letters ?? "--";
  byId("phoneticOutput").textContent = getPhoneticText();

  const backLink = byId("resultBackLink");
  if (backLink) {
    backLink.href = result.student_id
      ? `teacher-student-results.html?student_id=${encodeURIComponent(result.student_id)}`
      : "teacher-dashboard.html#students";
  }

  const audioPlayer = byId("audioPlayer");
  if (audioPlayer && result.audio_file) {
    audioPlayer.src = `/uploads/${result.audio_file}`;
  } else if (audioPlayer) {
    audioPlayer.style.display = "none";
  }

  renderRuleTable(summary);
  renderScoreComponents(summary);
  renderPronunciationDetails(summary);
  renderEvaluations(evaluations);
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    currentUser = data.user || null;
  } catch (error) {
    currentUser = null;
  }

  const teacherAdminNav = document.getElementById("teacherAdminNav");
  if (teacherAdminNav) {
    const isAdmin = currentUser?.role === "teacher" && currentUser?.is_admin;
    teacherAdminNav.style.display = isAdmin ? "" : "none";
  }
}

async function loadResultDetails() {
  const params = new URLSearchParams(window.location.search);
  const recitationId = params.get("recitation_id");

  if (!recitationId) {
    renderEmptyDetails("اختر نتيجة من قائمة النتائج لعرض تفاصيلها.");
    return;
  }

  try {
    await loadCurrentUser();
    if (isStudentViewer()) {
      window.location.replace(`student-result-details.html?recitation_id=${encodeURIComponent(recitationId)}`);
      return;
    }

    const response = await fetch(`/api/recitations/${encodeURIComponent(recitationId)}`);
    const data = await response.json();

    if (!response.ok || !data.result) {
      renderEmptyDetails(data.error || "لم يتم العثور على النتيجة المطلوبة.");
      return;
    }

    result = data.result;
    localStorage.setItem("maqraahLastResult", JSON.stringify(result));
    renderResultDetails();
  } catch (error) {
    renderEmptyDetails("تعذر تحميل تفاصيل النتيجة من قاعدة البيانات.");
  }
}

loadResultDetails();
