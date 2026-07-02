const state = {
  activePanel: "resume",
  lastOutput: "",
  profilePhoto: "",
};

const titles = {
  resume: "ATS Resume Builder",
  portfolio: "Portfolio Content Studio",
  score: "Hiring Probability Score",
  interview: "Interview Simulation",
  chat: "Career Copilot Chat",
};

const resumeThemes = new Set([
  "modern",
  "classic",
  "executive",
  "creative",
  "minimal",
  "sidebar",
]);

const cityOptions = {
  "Tamil Nadu": [
    "Coimbatore",
    "Chennai",
    "Madurai",
    "Tiruchirappalli",
    "Salem",
    "Erode",
    "Tiruppur",
    "Thanjavur",
    "Thiruvarur",
  ],
  Kerala: ["Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur"],
  Karnataka: ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi"],
  "Andhra Pradesh": ["Vijayawada", "Visakhapatnam", "Guntur", "Tirupati"],
  Telangana: ["Hyderabad", "Warangal", "Karimnagar", "Nizamabad"],
  Maharashtra: ["Mumbai", "Pune", "Nagpur", "Nashik"],
  Delhi: ["New Delhi", "Delhi"],
};

const outputText = document.querySelector("#outputText");
const outputStatus = document.querySelector("#outputStatus");
const toast = document.querySelector("#toast");

function showToast(message, type = "") {
  toast.textContent = message;
  toast.className = `toast show ${type}`.trim();
  window.setTimeout(() => {
    toast.className = "toast";
  }, 3600);
}

function setLoading(isLoading, label = "Working...") {
  document.body.classList.toggle("loading", isLoading);
  if (isLoading) {
    outputStatus.textContent = label;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const data = await readResponse(response);
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

async function readResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (contentType.includes("application/json")) {
    try {
      return JSON.parse(text || "{}");
    } catch {
      return { error: "The server returned invalid JSON." };
    }
  }

  if (!response.ok) {
    return {
      error: `Server returned ${response.status}. Restart the app and refresh the page.`,
    };
  }

  return { text };
}

function filenameSafe(value) {
  return (value || "hiresense-output")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "hiresense-output";
}

function profilePayload() {
  const city = document.querySelector("#city").value;
  const selectedState = document.querySelector("#state").value;

  return {
    name: document.querySelector("#name").value,
    target_role: document.querySelector("#targetRole").value,
    city,
    state: selectedState,
    location: [city, selectedState].filter(Boolean).join(", "),
    phone_country_code: document.querySelector("#phoneCountryCode").value,
    phone: document.querySelector("#phone").value,
    email: document.querySelector("#email").value,
    linkedin: document.querySelector("#linkedin").value,
    profile_photo: state.profilePhoto,
    resume_theme: document.querySelector("#resumeTheme").value,
    degree_name: document.querySelector("#degreeName").value,
    college_name: document.querySelector("#collegeName").value,
    university_name: document.querySelector("#universityName").value,
    degree_year: document.querySelector("#degreeYear").value,
    degree_score: document.querySelector("#degreeScore").value,
    hsc_school: document.querySelector("#hscSchool").value,
    hsc_year: document.querySelector("#hscYear").value,
    hsc_score: document.querySelector("#hscScore").value,
    sslc_school: document.querySelector("#sslcSchool").value,
    sslc_year: document.querySelector("#sslcYear").value,
    sslc_score: document.querySelector("#sslcScore").value,
    skills: document.querySelector("#skills").value,
    candidate_notes: document.querySelector("#candidateNotes").value,
    job_description: document.querySelector("#jobDescription").value,
  };
}

async function saveProfile(showSaved = true) {
  const data = await api("/api/profile", {
    method: "POST",
    body: JSON.stringify(profilePayload()),
  });
  if (showSaved) {
    showToast("Profile saved.");
  }
  return data.profile;
}

function setSelectValue(select, value, fallback = "") {
  const hasValue = Array.from(select.options).some((option) => option.value === value);
  select.value = hasValue ? value : fallback;
}

function updateCityOptions(selectedCity = "") {
  const state = document.querySelector("#state").value;
  const citySelect = document.querySelector("#city");
  const cities = cityOptions[state] || [];

  citySelect.innerHTML = '<option value="">Select city</option>';
  cities.forEach((city) => {
    const option = document.createElement("option");
    option.value = city;
    option.textContent = city;
    citySelect.appendChild(option);
  });

  const fallbackCity = cities.includes("Coimbatore") ? "Coimbatore" : "";
  setSelectValue(citySelect, selectedCity, fallbackCity);
}

function updatePhotoPreview() {
  const preview = document.querySelector("#photoPreview");
  if (!preview) {
    return;
  }

  if (state.profilePhoto) {
    preview.innerHTML = `<img src="${state.profilePhoto}" alt="">`;
    preview.classList.add("has-photo");
    return;
  }

  preview.innerHTML = "<span>Photo</span>";
  preview.classList.remove("has-photo");
}

function handlePhotoUpload(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }

  if (!file.type.startsWith("image/")) {
    showToast("Choose an image file for the profile picture.", "warning");
    return;
  }

  if (file.size > 2 * 1024 * 1024) {
    showToast("Use an image under 2 MB.", "warning");
    event.target.value = "";
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    state.profilePhoto = String(reader.result || "");
    updatePhotoPreview();
    showToast("Profile photo added.");
  };
  reader.readAsDataURL(file);
}

function setOutput(content, status = "Ready") {
  state.lastOutput = content || "";
  outputText.innerHTML = renderOutput(state.lastOutput || "No output yet.", status);
  outputStatus.textContent = status;
}

function setErrorOutput(message) {
  state.lastOutput = "";
  outputText.innerHTML = `
    <div class="error-panel">
      <strong>Could not complete this request</strong>
      <p>${escapeHtml(message)}</p>
      <p>Try again after a short wait. Temporary model-demand errors usually clear by themselves.</p>
    </div>
  `;
  outputStatus.textContent = "Error";
}

function fullPhoneNumber(profile) {
  const phone = (profile.phone || "").trim();
  if (!phone) {
    return "";
  }

  if (phone.startsWith("+")) {
    return phone;
  }

  return `${profile.phone_country_code || ""} ${phone}`.trim();
}

function profileInitials(name) {
  const parts = (name || "HS").trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0] || "").join("").toUpperCase() || "HS";
}

function normalizedResumeTheme(value) {
  return resumeThemes.has(value) ? value : "modern";
}

function resumeViewModel(content) {
  const profile = profilePayload();
  const theme = normalizedResumeTheme(profile.resume_theme);
  const contactItems = [
    [profile.city, profile.state].filter(Boolean).join(", "),
    fullPhoneNumber(profile),
    profile.email,
    profile.linkedin,
  ].filter(Boolean);
  const skills = profile.skills || "";
  const skillHint = skills.split(/\r?\n|,/).find((line) => line.trim()) || profile.target_role;
  const photo = state.profilePhoto
    ? `<img src="${state.profilePhoto}" alt="Candidate profile photo">`
    : `<span>${profileInitials(profile.name)}</span>`;
  const name = escapeHtml(profile.name || "Candidate Name");
  const role = escapeHtml(profile.target_role || "Target Role");
  const body = renderOutputBody(cleanResumeBody(content, profile));
  const contactHtml = contactItems.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  const highlightsHtml = [
    "ATS-ready",
    "Project-focused",
    skillHint,
  ]
    .filter(Boolean)
    .map((item) => `<span>${escapeHtml(item)}</span>`)
    .join("");

  return {
    theme,
    photo,
    name,
    role,
    body,
    contactHtml,
    highlightsHtml,
  };
}

function renderResumeIdentity(view) {
  return `
    <div class="resume-identity">
      <div class="resume-photo">${view.photo}</div>
      <div>
        <h1>${view.name}</h1>
        <p class="resume-role">${view.role}</p>
      </div>
    </div>
  `;
}

function renderResumeShell(content) {
  const view = resumeViewModel(content);

  if (view.theme === "sidebar") {
    return `
      <section class="resume-template resume-theme-${view.theme} resume-layout-sidebar">
        <aside class="resume-sidebar">
          <div class="resume-photo">${view.photo}</div>
          <h1>${view.name}</h1>
          <p class="resume-role">${view.role}</p>
          <div class="resume-contact">${view.contactHtml}</div>
          <div class="resume-highlight">${view.highlightsHtml}</div>
        </aside>
        <main class="resume-main">
          <div class="resume-body">${view.body}</div>
        </main>
      </section>
    `;
  }

  if (view.theme === "minimal") {
    return `
      <section class="resume-template resume-theme-${view.theme} resume-layout-minimal">
        <header class="resume-minimal-header">
          <div>
            <h1>${view.name}</h1>
            <p class="resume-role">${view.role}</p>
          </div>
          <div class="resume-contact">${view.contactHtml}</div>
        </header>
        <div class="resume-highlight">${view.highlightsHtml}</div>
        <div class="resume-body">${view.body}</div>
      </section>
    `;
  }

  return `
    <section class="resume-template resume-theme-${view.theme}">
      <header class="resume-hero">
        ${renderResumeIdentity(view)}
        <div class="resume-contact">
          ${view.contactHtml}
        </div>
      </header>
      <div class="resume-highlight">
        ${view.highlightsHtml}
      </div>
      <div class="resume-body">
        ${view.body}
      </div>
    </section>
  `;
}

function cleanResumeBody(content, profile) {
  const profileValues = [
    profile.name,
    profile.target_role,
    [profile.city, profile.state].filter(Boolean).join(", "),
    fullPhoneNumber(profile),
    profile.email,
    profile.linkedin,
  ]
    .filter(Boolean)
    .map((value) => value.toLowerCase());

  const lines = content.split(/\r?\n/);
  let startIndex = 0;

  while (startIndex < Math.min(lines.length, 5)) {
    const normalizedLine = lines[startIndex].trim().toLowerCase();
    if (!normalizedLine) {
      startIndex += 1;
      continue;
    }

    const matchedProfileValue = profileValues.some(
      (value) => normalizedLine === value || normalizedLine.includes(value),
    );
    const isPlaceholderContact = /\[linkedin profile url\]|\[profile link\]/i.test(lines[startIndex]);

    if (!matchedProfileValue && !isPlaceholderContact) {
      break;
    }

    startIndex += 1;
  }

  return lines.slice(startIndex).join("\n").trim() || content;
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function inlineMarkdown(value) {
  return escapeHtml(value).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

function renderOutput(content, status = "") {
  if (state.activePanel === "resume" || status.toLowerCase().includes("resume")) {
    return renderResumeShell(content);
  }

  return renderOutputBody(content);
}

function renderOutputBody(content) {
  const lines = content.split(/\r?\n/);
  const html = [];
  let listType = "";

  function closeList() {
    if (listType) {
      html.push(`</${listType}>`);
      listType = "";
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (!line) {
      closeList();
      html.push("<p></p>");
      return;
    }

    if (/^-{3,}$/.test(line)) {
      closeList();
      html.push('<hr class="rule">');
      return;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    const numbered = line.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${inlineMarkdown(numbered[2])}</li>`);
      return;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${inlineMarkdown(bullet[1])}</li>`);
      return;
    }

    closeList();
    html.push(`<p class="plain-line">${inlineMarkdown(line)}</p>`);
  });

  closeList();
  return html.join("");
}

function appendChat(role, content) {
  const log = document.querySelector("#chatLog");
  const message = document.createElement("div");
  message.className = `chat-message ${role}`;
  message.textContent = content;
  log.appendChild(message);
  log.scrollTop = log.scrollHeight;
}

function renderChat(history) {
  const log = document.querySelector("#chatLog");
  log.innerHTML = "";
  history.forEach((item) => {
    const content = item.content.split("\n\nCurrent candidate context:")[0];
    appendChat(item.role === "user" ? "user" : "assistant", content);
  });
}

async function loadState() {
  const data = await api("/api/state");
  const profile = data.profile;
  document.querySelector("#name").value = profile.name || "";
  setSelectValue(document.querySelector("#targetRole"), profile.target_role || "", "AI Developer");
  setSelectValue(document.querySelector("#state"), profile.state || "", "Tamil Nadu");
  updateCityOptions(profile.city || "");
  setSelectValue(document.querySelector("#phoneCountryCode"), profile.phone_country_code || "", "+91");
  document.querySelector("#phone").value = profile.phone || "";
  document.querySelector("#email").value = profile.email || "";
  document.querySelector("#linkedin").value = profile.linkedin || "";
  state.profilePhoto = profile.profile_photo || "";
  updatePhotoPreview();
  setSelectValue(document.querySelector("#resumeTheme"), profile.resume_theme || "", "modern");
  document.querySelector("#degreeName").value = profile.degree_name || "";
  document.querySelector("#collegeName").value = profile.college_name || "";
  document.querySelector("#universityName").value = profile.university_name || "";
  document.querySelector("#degreeYear").value = profile.degree_year || "";
  document.querySelector("#degreeScore").value = profile.degree_score || "";
  document.querySelector("#hscSchool").value = profile.hsc_school || "";
  document.querySelector("#hscYear").value = profile.hsc_year || "";
  document.querySelector("#hscScore").value = profile.hsc_score || "";
  document.querySelector("#sslcSchool").value = profile.sslc_school || "";
  document.querySelector("#sslcYear").value = profile.sslc_year || "";
  document.querySelector("#sslcScore").value = profile.sslc_score || "";
  document.querySelector("#skills").value = profile.skills || "";
  document.querySelector("#candidateNotes").value = profile.candidate_notes || "";
  document.querySelector("#jobDescription").value = profile.job_description || "";
  renderChat(data.chat_history || []);

  const apiStatus = document.querySelector("#apiStatus span");
  apiStatus.textContent = data.api_configured
    ? data.model
    : "API key needed";
  if (!data.api_configured) {
    showToast("Add a valid API key in .env, then restart the app.", "warning");
  }
}

function activatePanel(panel) {
  state.activePanel = panel;
  document.querySelector("#activeTitle").textContent = titles[panel];
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.panel === panel);
  });
  document.querySelectorAll(".control-surface").forEach((surface) => {
    surface.classList.toggle("hidden", surface.id !== `panel-${panel}`);
  });
}

async function generate(type) {
  try {
    await saveProfile(false);
    setLoading(true, `Generating ${type}...`);
    const data = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ type }),
    });
    setOutput(data.content, data.title);
    if (data.fallback) {
      showToast("AI model is busy, so an offline score estimate was generated.", "warning");
    }
  } catch (error) {
    setErrorOutput(error.message);
    showToast(error.message, "error");
  } finally {
    setLoading(false, outputStatus.textContent);
  }
}

async function startInterview() {
  try {
    await saveProfile(false);
    setLoading(true, "Starting interview...");
    const data = await api("/api/interview/start", {
      method: "POST",
      body: JSON.stringify({
        type: document.querySelector("#interviewType").value,
        rounds: document.querySelector("#interviewRounds").value,
      }),
    });
    document.querySelector("#questionMeta").textContent =
      `Question ${data.question_number} of ${data.rounds}`;
    document.querySelector("#questionText").textContent = data.question;
    document.querySelector("#interviewAnswer").value = "";
    setOutput(data.question, "Interview running");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false, outputStatus.textContent);
  }
}

async function submitInterviewAnswer() {
  const answerInput = document.querySelector("#interviewAnswer");
  try {
    setLoading(true, "Reviewing answer...");
    const data = await api("/api/interview/answer", {
      method: "POST",
      body: JSON.stringify({ answer: answerInput.value }),
    });
    answerInput.value = "";
    if (data.finished) {
      document.querySelector("#questionMeta").textContent = "Interview complete";
      document.querySelector("#questionText").textContent =
        "Review the final report in the output panel.";
      setOutput(data.report, "Final interview report");
      return;
    }
    document.querySelector("#questionMeta").textContent =
      `Question ${data.question_number} of ${data.rounds}`;
    document.querySelector("#questionText").textContent = data.question;
    setOutput(data.question, "Next interview prompt");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false, outputStatus.textContent);
  }
}

async function endInterview() {
  try {
    setLoading(true, "Ending interview...");
    const data = await api("/api/interview/end", { method: "POST" });
    document.querySelector("#questionMeta").textContent = "Interview complete";
    document.querySelector("#questionText").textContent =
      "Review the final report in the output panel.";
    setOutput(data.report, "Final interview report");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false, outputStatus.textContent);
  }
}

async function sendChat() {
  const input = document.querySelector("#chatMessage");
  const message = input.value.trim();
  if (!message) {
    showToast("Enter a message first.", "warning");
    return;
  }

  try {
    await saveProfile(false);
    appendChat("user", message);
    input.value = "";
    setLoading(true, "Thinking...");
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    appendChat("assistant", data.reply);
    setOutput(data.reply, "Career copilot reply");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false, outputStatus.textContent);
  }
}

async function downloadOutput() {
  const content = state.lastOutput || outputText.textContent;
  try {
    const response = await fetch("/api/export/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: outputStatus.textContent || titles[state.activePanel],
        content,
        profile: profilePayload(),
      }),
    });

    if (!response.ok) {
      const data = await readResponse(response);
      throw new Error(data.error || "PDF download failed.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filenameSafe(outputStatus.textContent || state.activePanel)}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
    showToast("PDF downloaded.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function downloadTextOutput() {
  const content = state.lastOutput || outputText.textContent;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `hiresense-${state.activePanel}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  document.querySelector("#state").addEventListener("change", () => updateCityOptions());
  document.querySelector("#profilePhoto").addEventListener("change", handlePhotoUpload);
  document.querySelector("#resumeTheme").addEventListener("change", () => {
    if (state.lastOutput && state.activePanel === "resume") {
      setOutput(state.lastOutput, outputStatus.textContent);
    }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => activatePanel(tab.dataset.panel));
  });

  document.querySelector("#profileForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveProfile(true);
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.querySelector("#saveProfileTop").addEventListener("click", async () => {
    try {
      await saveProfile(true);
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.querySelectorAll(".generate-button").forEach((button) => {
    button.addEventListener("click", () => generate(button.dataset.type));
  });

  document.querySelector("#startInterview").addEventListener("click", startInterview);
  document.querySelector("#submitAnswer").addEventListener("click", submitInterviewAnswer);
  document.querySelector("#endInterview").addEventListener("click", endInterview);
  document.querySelector("#sendChat").addEventListener("click", sendChat);

  document.querySelector("#chatMessage").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      sendChat();
    }
  });

  document.querySelector("#clearChat").addEventListener("click", async () => {
    try {
      await api("/api/chat/clear", { method: "POST" });
      renderChat([]);
      showToast("Chat cleared.");
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  document.querySelector("#copyOutput").addEventListener("click", async () => {
    await navigator.clipboard.writeText(state.lastOutput || outputText.textContent);
    showToast("Output copied.");
  });

  document.querySelector("#downloadOutput").addEventListener("click", downloadOutput);
}

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  activatePanel("resume");
  await loadState();
  if (window.lucide) {
    window.lucide.createIcons();
  }
});
