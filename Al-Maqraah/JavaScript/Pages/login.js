const cards = document.querySelectorAll(".account-card");
const loginBtn = document.getElementById("loginBtn");
const loginForm = document.querySelector(".login-form");

let selectedRole = "student";

cards.forEach(card => {
  card.addEventListener("click", () => {
    cards.forEach(item => item.classList.remove("active"));
    card.classList.add("active");
    selectedRole = card.dataset.role || "student";
  });
});

loginForm.addEventListener("submit", async event => {
  event.preventDefault();

  const email = loginForm.querySelector('input[type="email"]').value.trim();
  const password = loginForm.querySelector('input[type="password"]').value;

  if (!email || !password) {
    alert("الرجاء إدخال البريد الإلكتروني وكلمة المرور.");
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = "جاري الدخول...";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        role: selectedRole
      })
    });
    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "تعذر تسجيل الدخول.");
      return;
    }

    localStorage.setItem("maqraahUser", JSON.stringify(data.user));
    window.location.href = selectedRole === "student"
      ? "student-profile.html"
      : "teacher-dashboard.html";
  } catch (error) {
    alert("تعذر الاتصال بالخادم.");
    console.error(error);
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "دخول";
  }
});
