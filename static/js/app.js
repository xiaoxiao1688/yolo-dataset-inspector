const elements = {
  classNames: document.querySelector("#class-names"),
  entryList: document.querySelector("#entry-list"),
  exportReportButton: document.querySelector("#export-report-button"),
  heroHealth: document.querySelector("#hero-health"),
  imageInput: document.querySelector("#image-input"),
  inventoryHint: document.querySelector("#inventory-hint"),
  issueHint: document.querySelector("#issue-hint"),
  issueList: document.querySelector("#issue-list"),
  labelInput: document.querySelector("#label-input"),
  metricEntries: document.querySelector("#metric-entries"),
  metricImages: document.querySelector("#metric-images"),
  metricIssues: document.querySelector("#metric-issues"),
  metricLabels: document.querySelector("#metric-labels"),
  repairPlan: document.querySelector("#repair-plan"),
  scanButton: document.querySelector("#scan-button"),
  statusLine: document.querySelector("#status-line"),
  taskType: document.querySelector("#task-type"),
};

const state = {
  imageFiles: [],
  labelFiles: [],
  lastResult: null,
};

function setStatus(message, type = "info") {
  elements.statusLine.textContent = message;
  elements.heroHealth.textContent = type === "error" ? "Blocked" : type === "warn" ? "Needs review" : "Ready";
}

function updateSelectedCounts() {
  elements.metricImages.textContent = String(state.imageFiles.length);
  elements.metricLabels.textContent = String(state.labelFiles.length);
}

function renderEntries(entries) {
  if (!entries.length) {
    elements.entryList.innerHTML = '<li class="empty-state">Scan results will appear here.</li>';
    return;
  }

  elements.entryList.innerHTML = entries
    .map(
      (entry) => `
        <li class="stack-item">
          <p class="item-title">${entry.key}</p>
          <p class="item-meta">${entry.image_name || "missing image"} | ${entry.label_name || "missing label"}</p>
          <p class="item-meta">${entry.record_count} parsed records | ${entry.issue_count} issues</p>
        </li>
      `
    )
    .join("");
}

function renderIssues(issues) {
  if (!issues.length) {
    elements.issueList.innerHTML = '<li class="empty-state">No issues found in the current scan.</li>';
    return;
  }

  const sortedIssues = [...issues].sort((a, b) => {
    const left = a.level === "error" ? 2 : 1;
    const right = b.level === "error" ? 2 : 1;
    return right - left;
  });

  elements.issueList.innerHTML = sortedIssues
    .map(
      (issue) => `
        <li class="stack-item ${issue.level === "error" ? "issue-error" : "issue-warning"}">
          <p class="issue-title">${issue.code}</p>
          <p class="issue-meta">${issue.message}</p>
          <p class="issue-meta">${issue.entry_key || "-"}${issue.line ? ` | line ${issue.line}` : ""}</p>
        </li>
      `
    )
    .join("");
}

function renderRepairPlan(plan) {
  if (!plan.length) {
    elements.repairPlan.innerHTML = '<div class="empty-state">No repair suggestions for the current scan.</div>';
    return;
  }

  elements.repairPlan.innerHTML = plan
    .map(
      (item) => `
        <div class="plan-card">
          <p class="plan-title">${item.code}</p>
          <p class="plan-meta">${item.strategy}</p>
        </div>
      `
    )
    .join("");
}

function renderScanResult(result) {
  state.lastResult = result;
  elements.metricEntries.textContent = String(result.summary.entry_count);
  elements.metricIssues.textContent = String(result.summary.issue_count);
  elements.inventoryHint.textContent = `${result.summary.entry_count} entries scanned.`;
  elements.issueHint.textContent = `${result.summary.error_count} errors, ${result.summary.warning_count} warnings.`;
  elements.exportReportButton.disabled = false;

  renderEntries(result.entries);
  renderIssues(result.issues);
  renderRepairPlan(result.repair_plan);

  if (result.summary.issue_count > 0) {
    setStatus(`Scan complete. ${result.summary.issue_count} issues found.`, "warn");
  } else {
    setStatus("Scan complete. No issues found.");
  }
}

async function runScan() {
  if (!state.imageFiles.length && !state.labelFiles.length) {
    setStatus("Select at least one image or label file first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("task_type", elements.taskType.value);
  formData.append("classes_text", elements.classNames.value);

  state.imageFiles.forEach((file) => formData.append("images", file));
  state.labelFiles.forEach((file) => formData.append("labels", file));

  setStatus("Uploading files and scanning dataset...");

  const response = await fetch("/api/scan", {
    method: "POST",
    body: formData,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Scan failed");
  }

  renderScanResult(payload);
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

elements.imageInput.addEventListener("change", (event) => {
  state.imageFiles = [...(event.target.files || [])];
  updateSelectedCounts();
  setStatus(`${state.imageFiles.length} image files selected.`);
});

elements.labelInput.addEventListener("change", (event) => {
  state.labelFiles = [...(event.target.files || [])];
  updateSelectedCounts();
  setStatus(`${state.labelFiles.length} label files selected.`);
});

elements.scanButton.addEventListener("click", async () => {
  try {
    await runScan();
  } catch (error) {
    setStatus(error.message || "Scan failed.", "error");
  }
});

elements.exportReportButton.addEventListener("click", () => {
  if (!state.lastResult) {
    return;
  }
  downloadJson("scan-report.json", state.lastResult);
  setStatus("Exported scan report.");
});

updateSelectedCounts();
