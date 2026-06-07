const forgotForm = document.getElementById("forgotForm");

forgotForm.addEventListener("submit", function(e){

  e.preventDefault();

  const email = document.getElementById("recoveryEmail").value;

  if(email === ""){
    alert("الرجاء إدخال البريد الإلكتروني");
    return;
  }

  alert("تم إرسال رابط استعادة كلمة المرور");

});