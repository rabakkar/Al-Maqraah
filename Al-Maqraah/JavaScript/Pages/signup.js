const cards = document.querySelectorAll(".account-card");
const signupForm = document.querySelector(".login-form");
const signupButton = signupForm.querySelector('button[type="submit"]');

const selectedRole = "student";

cards.forEach(card => {
  card.addEventListener("click", () => {
    cards.forEach(item => item.classList.remove("active"));
    card.classList.add("active");
  });
});

signupForm.addEventListener("submit", async event => {
  event.preventDefault();

  const inputs = signupForm.querySelectorAll("input");
  const fullName = inputs[0].value.trim();
  const email = inputs[1].value.trim();
  const password = inputs[2].value;
  const confirmPassword = inputs[3].value;

  if (!fullName || !email || !password || !confirmPassword) {
    alert("الرجاء تعبئة جميع الحقول.");
    return;
  }

  if (password !== confirmPassword) {
    alert("كلمتا المرور غير متطابقتين.");
    return;
  }

  signupButton.disabled = true;
  signupButton.textContent = "جاري إنشاء الحساب...";

  try {
    const response = await fetch("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        email,
        password,
        role: selectedRole
      })
    });
    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "تعذر إنشاء الحساب.");
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
    signupButton.disabled = false;
    signupButton.textContent = "إنشاء الحساب";
  }
});
