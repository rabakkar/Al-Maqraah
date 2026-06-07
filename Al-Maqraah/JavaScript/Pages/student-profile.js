const recitationList = document.querySelector(".recitation-list");
const studentNameTitle = document.querySelector(".student-hero__text h1");
const studentLevelBadge = document.querySelector(".student-hero__text .dashboard-badge");
const todayTask = document.querySelector(".today-task-mini span");

async function loadProfile() {
  try {
    const meResponse = await fetch("/api/auth/me");
    const meData = await meResponse.json();

    if (meData.user && studentNameTitle) {
      studentNameTitle.textContent = `السلام عليكم، ${meData.user.full_name}`;
    }
    if (meData.user && studentLevelBadge) {
      studentLevelBadge.textContent = `مستواك: ${meData.user.student_level_label || "غير مصنف"}`;
    }
  } catch (error) {
    console.warn("Could not load current user.", error);
  }

  if (todayTask) {
    todayTask.textContent = "يحدد من قبل المعلم ";
  }

  try {
    const response = await fetch("/api/recitations");
    const data = await response.json();
    const recitations = data.recitations || [];

    if (!recitations.length) {
      recitationList.innerHTML = `<div class="empty-state">لا توجد تسميعات محفوظة بعد.</div>`;
      return;
    }

    recitationList.innerHTML = recitations.slice(0, 2).map(item => {
      const reviewCount = item.summary?.needs_review || 0;
      const statusClass = reviewCount > 0 ? "mid" : "good";
      const statusText = reviewCount > 0 ? `${reviewCount} ملاحظة` : "مكتملة";

      return `
        <div class="recitation-row">
          <div>
            <strong>${item.surah_name}</strong>
            <span>الآيات ${item.ayah_from} إلى ${item.ayah_to} - ${item.created_at}</span>
          </div>
          <p>${item.score}%</p>
          <span class="status ${statusClass}">${statusText}</span>
        </div>
      `;
    }).join("");
  } catch (error) {
    recitationList.innerHTML = `<div class="empty-state">تعذر تحميل التسميعات من قاعدة البيانات.</div>`;
  }
}

loadProfile();
