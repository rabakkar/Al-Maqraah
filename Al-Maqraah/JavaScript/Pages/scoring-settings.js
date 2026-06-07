const levelSettingsForm = document.getElementById("levelSettingsForm");
const levelSettingsGrid = document.getElementById("levelSettingsGrid");
const levelSettingsStatus = document.getElementById("levelSettingsStatus");
const teacherAdminNav = document.getElementById("teacherAdminNav");

const LEVELS = [
  { key: "beginner", label: "مبتدئ", countId: "beginnerRuleCount" },
  { key: "intermediate", label: "متوسط", countId: "intermediateRuleCount" },
  { key: "advanced", label: "متقدم", countId: "advancedRuleCount" }
];

const RULES = [
  { key: "izhar", label: "الإظهار" },
  { key: "idgham", label: "الإدغام" },
  { key: "iqlab", label: "الإقلاب" },
  { key: "ikhfa", label: "الإخفاء" }
];

const DEFAULT_LEVELS = {
  beginner: {
    izhar_enabled: 1,
    idgham_enabled: 0,
    iqlab_enabled: 0,
    ikhfa_enabled: 0
  },
  intermediate: {
    izhar_enabled: 1,
    idgham_enabled: 1,
    iqlab_enabled: 1,
    ikhfa_enabled: 0
  },
  advanced: {
    izhar_enabled: 1,
    idgham_enabled: 1,
    iqlab_enabled: 1,
    ikhfa_enabled: 1
  }
};

const DEFAULT_THRESHOLDS = {
  beginner: 0,
  intermediate: 70,
  advanced: 85
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function defaultSettings(level) {
  return {
    level,
    ...DEFAULT_LEVELS[level],
    izhar_weight: 1,
    idgham_weight: 1,
    iqlab_weight: 1,
    ikhfa_weight: 1,
    placement_threshold: DEFAULT_THRESHOLDS[level] ?? 0,
    missing_word_penalty: 0.10,
    extra_word_penalty: 0.05,
    different_word_penalty: 0.08
  };
}

function inputName(level, key) {
  return `${level}_${key}`;
}

function renderRuleRow(level, settings, rule) {
  const enabledKey = `${rule.key}_enabled`;
  const weightKey = `${rule.key}_weight`;
  const checked = Number(settings[enabledKey] ?? 0) === 1;

  return `
    <div class="rule-weight-row">
      <label class="rule-check">
        <input
          type="checkbox"
          data-level="${level}"
          data-rule="${rule.key}"
          data-field="enabled"
          ${checked ? "checked" : ""}
        >
        <span>${escapeHtml(rule.label)}</span>
      </label>
      <input
        id="${inputName(level, weightKey)}"
        type="number"
        min="0"
        max="1"
        step="0.05"
        value="${escapeHtml(settings[weightKey] ?? 1)}"
        data-level="${level}"
        data-rule="${rule.key}"
        data-field="weight"
        ${checked ? "" : "disabled"}
      >
    </div>
  `;
}

function renderLevelCard(levelMeta, settings) {
  const level = levelMeta.key;
  return `
    <article class="level-settings-card" data-level-card="${level}">
      <div class="level-settings-card__head">
        <div>
          <span class="panel-label">${escapeHtml(levelMeta.label)}</span>
          <h3>${escapeHtml(levelMeta.label)}</h3>
        </div>
        <span class="status good" data-rule-count="${level}">0 حكم</span>
      </div>

      <div class="level-threshold-setting">
        <label>
          درجة اجتياز المستوى
          <input data-level="${level}" data-field="placement_threshold" type="number" min="0" max="100" step="1" value="${escapeHtml(settings.placement_threshold ?? DEFAULT_THRESHOLDS[level] ?? 0)}">
        </label>
      </div>

      <div class="rule-weight-table">
        <div class="rule-weight-row rule-weight-row--head">
          <strong>الحكم</strong>
          <span>الوزن</span>
        </div>
        ${RULES.map(rule => renderRuleRow(level, settings, rule)).join("")}
      </div>

      <div class="pronunciation-settings">
        <h4>خصم الكلمات</h4>
        <label>
          خصم الكلمة الناقصة
          <input data-level="${level}" data-field="missing_word_penalty" type="number" min="0" max="1" step="0.01" value="${escapeHtml(settings.missing_word_penalty ?? 0.10)}">
        </label>
        <label>
          خصم الكلمة الزائدة
          <input data-level="${level}" data-field="extra_word_penalty" type="number" min="0" max="1" step="0.01" value="${escapeHtml(settings.extra_word_penalty ?? 0.05)}">
        </label>
        <label>
          خصم الكلمة المختلفة
          <input data-level="${level}" data-field="different_word_penalty" type="number" min="0" max="1" step="0.01" value="${escapeHtml(settings.different_word_penalty ?? 0.08)}">
        </label>
      </div>
    </article>
  `;
}

function countEnabledRules(level) {
  return RULES.filter(rule => {
    const checkbox = levelSettingsGrid.querySelector(`[data-level="${level}"][data-rule="${rule.key}"][data-field="enabled"]`);
    return checkbox?.checked;
  }).length;
}

function updateRuleCounts() {
  LEVELS.forEach(level => {
    const count = countEnabledRules(level.key);
    const summary = document.getElementById(level.countId);
    const badge = levelSettingsGrid.querySelector(`[data-rule-count="${level.key}"]`);
    if (summary) {
      summary.textContent = count;
    }
    if (badge) {
      badge.textContent = `${count} حكم`;
      badge.className = `status ${count > 0 ? "good" : "mid"}`;
    }
  });
}

function syncWeightAvailability() {
  RULES.forEach(rule => {
    LEVELS.forEach(level => {
      const checkbox = levelSettingsGrid.querySelector(`[data-level="${level.key}"][data-rule="${rule.key}"][data-field="enabled"]`);
      const weight = levelSettingsGrid.querySelector(`[data-level="${level.key}"][data-rule="${rule.key}"][data-field="weight"]`);
      if (weight) {
        weight.disabled = !checkbox?.checked;
      }
    });
  });
  updateRuleCounts();
}

function renderLevels(levels) {
  levelSettingsGrid.innerHTML = LEVELS.map(level => {
    const settings = {
      ...defaultSettings(level.key),
      ...(levels?.[level.key] || {})
    };
    return renderLevelCard(level, settings);
  }).join("");

  syncWeightAvailability();
}

function readLevelSettings(level) {
  const settings = { level };
  RULES.forEach(rule => {
    const checkbox = levelSettingsGrid.querySelector(`[data-level="${level}"][data-rule="${rule.key}"][data-field="enabled"]`);
    const weight = levelSettingsGrid.querySelector(`[data-level="${level}"][data-rule="${rule.key}"][data-field="weight"]`);
    settings[`${rule.key}_enabled`] = checkbox?.checked ? 1 : 0;
    settings[`${rule.key}_weight`] = Number(weight?.value || 0);
  });

  ["placement_threshold", "missing_word_penalty", "extra_word_penalty", "different_word_penalty"].forEach(field => {
    const input = levelSettingsGrid.querySelector(`[data-level="${level}"][data-field="${field}"]`);
    settings[field] = Number(input?.value || 0);
  });

  return settings;
}

function collectPayload() {
  const levels = {};
  LEVELS.forEach(level => {
    const settings = readLevelSettings(level.key);
    const hasRule = RULES.some(rule => Number(settings[`${rule.key}_enabled`]) === 1);
    if (!hasRule) {
      throw new Error(`اختر حكمًا واحدًا على الأقل في مستوى ${level.label}.`);
    }
    levels[level.key] = settings;
  });
  return { levels };
}

async function loadLevelSettings() {
  try {
    const response = await fetch("/api/scoring-settings");
    const data = await response.json();

    if (!response.ok) {
      levelSettingsGrid.innerHTML = `<div class="empty-state">${escapeHtml(data.error || "تعذر تحميل إعدادات الأوزان.")}</div>`;
      return;
    }

    renderLevels(data.levels || {});
  } catch (error) {
    levelSettingsGrid.innerHTML = `<div class="empty-state">تعذر الاتصال بالخادم لتحميل إعدادات الأوزان.</div>`;
  }
}

async function syncTeacherNavigation() {
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    const isAdmin = data.user?.role === "teacher" && data.user?.is_admin;

    if (teacherAdminNav) {
      teacherAdminNav.style.display = isAdmin ? "" : "none";
    }
  } catch (error) {
    if (teacherAdminNav) {
      teacherAdminNav.style.display = "none";
    }
  }
}

levelSettingsGrid.addEventListener("change", event => {
  if (event.target.matches('[data-field="enabled"]')) {
    syncWeightAvailability();
  }
});

levelSettingsForm.addEventListener("submit", async event => {
  event.preventDefault();
  levelSettingsStatus.textContent = "جاري حفظ أوزان المستويات...";

  let payload;
  try {
    payload = collectPayload();
  } catch (error) {
    levelSettingsStatus.textContent = error.message;
    return;
  }

  try {
    const response = await fetch("/api/scoring-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json();

    if (!response.ok) {
      levelSettingsStatus.textContent = data.error || "تعذر حفظ إعدادات الأوزان.";
      return;
    }

    renderLevels(data.levels || payload.levels);
    levelSettingsStatus.textContent = "تم حفظ أوزان المستويات بنجاح.";
  } catch (error) {
    levelSettingsStatus.textContent = "تعذر الاتصال بالخادم.";
  }
});

async function initScoringSettings() {
  await syncTeacherNavigation();
  loadLevelSettings();
}

initScoringSettings();
