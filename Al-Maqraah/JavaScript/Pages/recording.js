const ASSIGNMENT_KEY = "maqraahAssignment";
const RESULT_KEY = "maqraahLastResult";

const assignedAyahText = document.getElementById("assignedAyahText");
const assignedAyahRef = document.getElementById("assignedAyahRef");
const assignedSurah = document.getElementById("assignedSurah");
const assignedRange = document.getElementById("assignedRange");
const recordBtn = document.getElementById("recordBtn");
const audioPreview = document.getElementById("audioPreview");
const audioPlayer = document.getElementById("audioPlayer");
const timer = document.getElementById("recordTimer");
const submitRecording = document.getElementById("submitRecording");
const hint = document.querySelector(".record-hint");
const heardTextPanel = document.getElementById("heardTextPanel");
const heardTextValue = document.getElementById("heardTextValue");

let currentTask = null;
let hasOpenAssignment = false;
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let recordingCompleted = false;
let submissionStarted = false;
let seconds = 0;
let timerInterval;
let recordedWavBlob = null;
let activeStream = null;

function formatAssignment(task) {
  return {
    id: task.id || null,
    mode: "assignment",
    surah: task.surah_number || task.surah || 67,
    surahName: task.surah_name || task.surahName || "السورة المحددة",
    fromAyah: task.ayah_from || task.fromAyah || 1,
    toAyah: task.ayah_to || task.toAyah || 1,
    ayahText: task.ayah_text || task.ayahText || "",
    verses: Array.isArray(task.verses) ? task.verses : [],
    submitted: Boolean(task.submitted),
    submittedRecitationId: task.submitted_recitation_id || task.submittedRecitationId || null,
    submittedAt: task.submitted_at || task.submittedAt || null
  };
}

function resetRecordingDraft() {
  recordedWavBlob = null;
  recordingCompleted = false;
  submissionStarted = false;
  audioPlayer.src = "";
  audioPreview.style.display = "none";
  submitRecording.disabled = true;
  clearHeardText();
  timer.textContent = "00:00";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatVerseNumber(value) {
  return new Intl.NumberFormat("ar-EG", { useGrouping: false }).format(Number(value) || 0);
}

function setStatus(message) {
  hint.textContent = message;
}

function clearHeardText() {
  if (!heardTextPanel || !heardTextValue) {
    return;
  }
  heardTextPanel.hidden = true;
  heardTextValue.textContent = "";
}

function showHeardText(data) {
  if (!heardTextPanel || !heardTextValue) {
    return;
  }

  const verification = data.recitation_verification || {};
  const heardText = data.heard_text || verification.transcript || verification.normalized_transcript || "";
  heardTextValue.textContent = heardText.trim() || "لم يتمكن النظام من استخراج نص واضح من التسجيل.";
  heardTextPanel.hidden = false;
}

function setRecordingEnabled(enabled) {
  hasOpenAssignment = enabled;
  recordBtn.disabled = !enabled || submissionStarted;
  submitRecording.disabled = !enabled || !recordedWavBlob;
  recordBtn.classList.toggle("is-disabled", recordBtn.disabled);
}

function renderTask(task) {
  if (Array.isArray(task.verses) && task.verses.length) {
    assignedAyahText.innerHTML = task.verses.map(verse => {
      const text = verse.uthmani || verse.imlaey || verse.text || "";
      return `
        <span class="ayah-verse">
          <span class="ayah-verse__text">${escapeHtml(text)}</span>
          <span class="ayah-number">﴿${formatVerseNumber(verse.ayah)}﴾</span>
        </span>
      `;
    }).join("");
  } else {
    assignedAyahText.textContent = task.ayahText || "لم يتم تحميل نص الآيات بعد.";
  }

  assignedAyahRef.textContent = `تكليف المعلم: ${task.surahName} - الآيات ${task.fromAyah} إلى ${task.toAyah}`;
  assignedSurah.textContent = task.surahName;
  assignedRange.textContent = `من الآية ${task.fromAyah} إلى الآية ${task.toAyah}`;
}

function renderNoAssignment(message = "لا يوجد تكليف تسميع متاح الآن. عند نشر المعلم لتكليف جديد سيظهر هنا.") {
  currentTask = null;
  localStorage.removeItem(ASSIGNMENT_KEY);
  resetRecordingDraft();
  assignedAyahText.textContent = message;
  assignedAyahRef.textContent = "لا يوجد تكليف متاح";
  assignedSurah.textContent = "-";
  assignedRange.textContent = "-";
  setRecordingEnabled(false);
  setStatus(message);
}

function renderSubmittedAssignment(task) {
  assignedAyahText.textContent = "لا يوجد تكليف جديد";
  assignedAyahRef.textContent = `تكليف المعلم: ${task.surahName} - الآيات ${task.fromAyah} إلى ${task.toAyah}`;
  assignedSurah.textContent = task.surahName;
  assignedRange.textContent = `من الآية ${task.fromAyah} إلى الآية ${task.toAyah}`;
}

async function attachAssignmentVerses(task) {
  if (task.submitted) {
    return { ...task, ayahText: "", verses: [] };
  }

  try {
    const response = await fetch(`/api/verses?surah=${task.surah}&from=${task.fromAyah}&to=${task.toAyah}`);
    const data = await response.json();
    if (!response.ok) {
      return task;
    }
    return {
      ...task,
      surahName: data.surah?.name || task.surahName,
      ayahText: data.verses?.map(verse => verse.uthmani || verse.imlaey || verse.text || "").join(" ") || task.ayahText,
      verses: Array.isArray(data.verses) ? data.verses : task.verses
    };
  } catch (error) {
    console.error(error);
    return task;
  }
}

async function loadCurrentAssignment() {
  setRecordingEnabled(false);
  resetRecordingDraft();
  setStatus("جاري تحميل التكليف الذي حدده المعلم...");

  try {
    const response = await fetch("/api/assignments/current");
    const data = await response.json();

    if (!response.ok) {
      renderNoAssignment(data.error || "تعذر تحميل التكليف الحالي.");
      return;
    }

    if (!data.assignment) {
      renderNoAssignment("لا يوجد تكليف جديد متاح، أو أنك سلّمت التكليف الحالي مسبقًا.");
      return;
    }

    const formattedAssignment = formatAssignment({
      ...data.assignment,
      submitted: data.assignment.submitted || data.submitted
    });

    if (formattedAssignment.submitted) {
      currentTask = { ...formattedAssignment, ayahText: "", verses: [] };
      localStorage.setItem(ASSIGNMENT_KEY, JSON.stringify(currentTask));
      renderSubmittedAssignment(currentTask);
      setRecordingEnabled(false);
      setStatus("تم تسليم هذا التكليف مسبقًا. يمكنك مراجعة نتيجتك، ولا يمكن إرسال تسجيل جديد.");
      return;
    }

    renderTask(formattedAssignment);
    currentTask = await attachAssignmentVerses(formattedAssignment);
    localStorage.setItem(ASSIGNMENT_KEY, JSON.stringify(currentTask));
    renderTask(currentTask);

    if (currentTask.submitted) {
      setRecordingEnabled(false);
      setStatus("تم تسليم هذا التكليف مسبقًا. يمكنك مراجعة نتيجتك، ولا يمكن إرسال تسجيل جديد.");
      return;
    }

    setRecordingEnabled(true);

    setStatus("اقرأ التعليمات ثم اضغط على زر المايكروفون عند الجاهزية. يمكنك إعادة التسجيل قبل الإرسال، وبعد الإرسال لا يمكن تسليم تسجيل آخر لنفس التكليف.");
  } catch (error) {
    console.error(error);
    renderNoAssignment("تعذر الاتصال بالخادم لتحميل تكليف المعلم.");
  }
}

function startTimer() {
  seconds = 0;
  timer.textContent = "00:00";

  timerInterval = setInterval(() => {
    seconds++;
    const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
    const secs = String(seconds % 60).padStart(2, "0");
    timer.textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
}

function stopActiveStream() {
  if (activeStream) {
    activeStream.getTracks().forEach(track => track.stop());
    activeStream = null;
  }
}

function audioBufferToWav(audioBuffer) {
  const numberOfChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const length = audioBuffer.length * numberOfChannels * 2;
  const buffer = new ArrayBuffer(44 + length);
  const view = new DataView(buffer);
  const channels = [];
  let offset = 0;

  function writeString(value) {
    for (let i = 0; i < value.length; i++) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
    offset += value.length;
  }

  writeString("RIFF");
  view.setUint32(offset, 36 + length, true);
  offset += 4;
  writeString("WAVE");
  writeString("fmt ");
  view.setUint32(offset, 16, true);
  offset += 4;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint16(offset, numberOfChannels, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, sampleRate * numberOfChannels * 2, true);
  offset += 4;
  view.setUint16(offset, numberOfChannels * 2, true);
  offset += 2;
  view.setUint16(offset, 16, true);
  offset += 2;
  writeString("data");
  view.setUint32(offset, length, true);
  offset += 4;

  for (let channel = 0; channel < numberOfChannels; channel++) {
    channels.push(audioBuffer.getChannelData(channel));
  }

  for (let i = 0; i < audioBuffer.length; i++) {
    for (let channel = 0; channel < numberOfChannels; channel++) {
      const sample = Math.max(-1, Math.min(1, channels[channel][i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
  }

  return new Blob([buffer], { type: "audio/wav" });
}

async function convertToWav(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const audioContext = new AudioContextClass();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  const wavBlob = audioBufferToWav(audioBuffer);
  await audioContext.close();
  return wavBlob;
}

recordBtn.addEventListener("click", async () => {
  if (!hasOpenAssignment || !currentTask?.id) {
    setStatus("لا يوجد تكليف متاح للتسجيل. انتظر حتى يحدد المعلم السورة والآيات.");
    return;
  }

  if (submissionStarted) {
    setStatus("تم إرسال التسجيل للتحليل، ولا يمكن تسجيل محاولة جديدة لهذا التكليف.");
    return;
  }

  try {
    if (!isRecording) {
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "";

      activeStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(activeStream, mimeType ? { mimeType } : undefined);
      audioChunks = [];
      recordedWavBlob = null;
      clearHeardText();
      audioPreview.style.display = "none";
      submitRecording.disabled = true;

      mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const recordedBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        audioPlayer.src = URL.createObjectURL(recordedBlob);
        audioPreview.style.display = "block";
        recordingCompleted = true;
        recordBtn.disabled = false;
        recordBtn.classList.remove("is-disabled");
        setStatus("تم حفظ التسجيل. يمكنك إعادة التسجيل قبل الإرسال أو إرسال هذا التسجيل للتحليل.");

        try {
          recordedWavBlob = await convertToWav(recordedBlob);
          submitRecording.disabled = false;
        } catch (error) {
          submitRecording.disabled = true;
          setStatus("تعذر تجهيز التسجيل للإرسال من المتصفح. يمكنك إعادة التسجيل قبل الإرسال ثم المحاولة مرة أخرى.");
          console.error(error);
        }
      };

      mediaRecorder.start();
      isRecording = true;
      recordBtn.classList.add("recording");
      setStatus("جاري التسجيل...");
      startTimer();
    } else {
      mediaRecorder.stop();
      stopActiveStream();
      isRecording = false;
      recordingCompleted = true;
      recordBtn.disabled = false;
      recordBtn.classList.remove("is-disabled");
      recordBtn.classList.remove("recording");
      stopTimer();
    }
  } catch (error) {
    setStatus("لم نتمكن من تشغيل المايكروفون. تأكد من السماح للمتصفح باستخدامه.");
    stopActiveStream();
    isRecording = false;
    recordBtn.classList.remove("recording");
    console.error(error);
  }
});

submitRecording.addEventListener("click", async () => {
  if (!hasOpenAssignment || !currentTask?.id) {
    setStatus("لا يوجد تكليف من المعلم لإرسال التسجيل.");
    return;
  }

  if (!recordedWavBlob) {
    setStatus("سجّل التلاوة أولًا قبل إرسالها للتحليل.");
    return;
  }

  const formData = new FormData();
  formData.append("audio", recordedWavBlob, "recitation.wav");
  formData.append("assignment_id", currentTask.id);

  submissionStarted = true;
  recordBtn.disabled = true;
  recordBtn.classList.add("is-disabled");
  recordBtn.classList.remove("recording");
  submitRecording.disabled = true;
  setStatus("جاري إرسال التسجيل وتحليله...");

  try {
    const response = await fetch("/api/analyze-audio", {
      method: "POST",
      body: formData
    });
    const data = await response.json();

    if (!response.ok) {
      setStatus(data.error || "تعذر تحليل التسجيل.");
      if (data.recitation_verification || data.heard_text) {
        showHeardText(data);
      }
      if (response.status === 409) {
        setRecordingEnabled(false);
        return;
      }
      submissionStarted = false;
      if (hasOpenAssignment) {
        recordBtn.disabled = false;
        recordBtn.classList.remove("is-disabled");
      }
      submitRecording.disabled = !recordedWavBlob;
      return;
    }

    localStorage.setItem(RESULT_KEY, JSON.stringify(data));
    localStorage.removeItem(ASSIGNMENT_KEY);
    window.location.href = data.recitation_id
      ? `student-result-details.html?recitation_id=${encodeURIComponent(data.recitation_id)}`
      : "result.html";
  } catch (error) {
    setStatus("تعذر الاتصال بالخادم أثناء التحليل.");
    submissionStarted = false;
    if (hasOpenAssignment) {
      recordBtn.disabled = false;
      recordBtn.classList.remove("is-disabled");
    }
    submitRecording.disabled = !recordedWavBlob;
    console.error(error);
  }
});

async function initRecordingPage() {
  renderNoAssignment("جاري البحث عن تكليف المعلم...");
  await loadCurrentAssignment();
}

initRecordingPage();
