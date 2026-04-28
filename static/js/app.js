const elements = {
  classNames: document.querySelector("#class-names"),
  confThreshold: document.querySelector("#conf-threshold"),
  iouThreshold: document.querySelector("#iou-threshold"),
  decisionHint: document.querySelector("#decision-hint"),
  decisionPanel: document.querySelector("#decision-panel"),
  exportAuditButton: document.querySelector("#export-audit-button"),
  exportLabelsButton: document.querySelector("#export-labels-button"),
  heroHealth: document.querySelector("#hero-health"),
  imageHint: document.querySelector("#image-hint"),
  imageInput: document.querySelector("#image-input"),
  imageList: document.querySelector("#image-list"),
  issueDetailHint: document.querySelector("#issue-detail-hint"),
  issueDetailPanel: document.querySelector("#issue-detail-panel"),
  labelInput: document.querySelector("#label-input"),
  metricDet: document.querySelector("#metric-det"),
  metricGt: document.querySelector("#metric-gt"),
  metricImages: document.querySelector("#metric-images"),
  metricIssues: document.querySelector("#metric-issues"),
  runQaButton: document.querySelector("#run-qa-button"),
  sessionId: document.querySelector("#session-id"),
  statusLine: document.querySelector("#status-line"),
};

const state = {
  imageFiles: [],
  labelFiles: [],
  sessionId: null,
  results: [],
  selectedImageKey: null,
  selectedResult: null,
};

function setStatus(message, type = "info") {
  elements.statusLine.textContent = message;
  elements.heroHealth.textContent =
    type === "error" ? "Blocked" : type === "warn" ? "Needs review" : "Ready";
}

function updateMetrics() {
  if (!state.results.length) {
    elements.metricImages.textContent = "0";
    elements.metricGt.textContent = "0";
    elements.metricDet.textContent = "0";
    elements.metricIssues.textContent = "0";
    return;
  }

  const totalGt = state.results.reduce((sum, r) => sum + r.comparison.ground_truth_count, 0);
  const totalDet = state.results.reduce((sum, r) => sum + r.comparison.detection_count, 0);
  const totalIssues = state.results.reduce((sum, r) => sum + r.comparison.issues.length, 0);

  elements.metricImages.textContent = String(state.results.length);
  elements.metricGt.textContent = String(totalGt);
  elements.metricDet.textContent = String(totalDet);
  elements.metricIssues.textContent = String(totalIssues);
}

function getIssueTypeLabel(type) {
  const labels = {
    missing_label: "漏标",
    class_conflict: "类别冲突",
    anomalous_box: "异常框",
    possibly_wrong_label: "可能错标",
    unmatched_ground_truth: "未匹配原标签",
  };
  return labels[type] || type;
}

function getIssueTypeClass(type) {
  const classes = {
    missing_label: "issue-missing",
    class_conflict: "issue-conflict",
    anomalous_box: "issue-anomalous",
    possibly_wrong_label: "issue-warning",
    unmatched_ground_truth: "issue-warning",
  };
  return classes[type] || "issue-default";
}

function formatBox(box) {
  if (!box) return "N/A";
  return `x: ${box.x_center?.toFixed(4) || "?"}, y: ${box.y_center?.toFixed(4) || "?"}, w: ${box.width?.toFixed(4) || "?"}, h: ${box.height?.toFixed(4) || "?"}`;
}

function renderImageList() {
  if (!state.results.length) {
    elements.imageList.innerHTML = '<li class="empty-state">Processed images will appear here. Click to view details.</li>';
    elements.imageHint.textContent = "No images processed yet.";
    return;
  }

  elements.imageHint.textContent = `${state.results.length} images processed.`;

  elements.imageList.innerHTML = state.results
    .map((result) => {
      const isSelected = result.image_key === state.selectedImageKey;
      const issueCount = result.comparison.issues.length;
      const decisionCount = result.decisions?.length || 0;
      const hasIssues = issueCount > 0;

      return `
        <li class="stack-item ${isSelected ? "selected" : ""} ${hasIssues ? "has-issues" : ""}" data-key="${result.image_key}">
          <p class="item-title">${result.image_info.filename}</p>
          <p class="item-meta">${result.image_info.width} × ${result.image_info.height}</p>
          <p class="item-meta">
            ${result.comparison.ground_truth_count} GT | ${result.comparison.detection_count} Det | 
            <span class="${issueCount > 0 ? "text-danger" : ""}">${issueCount} issues</span>
            ${decisionCount > 0 ? ` | <span class="text-success">${decisionCount} decisions</span>` : ""}
          </p>
        </li>
      `;
    })
    .join("");

  document.querySelectorAll("#image-list .stack-item").forEach((item) => {
    item.addEventListener("click", () => {
      const key = item.dataset.key;
      selectImage(key);
    });
  });
}

function selectImage(imageKey) {
  state.selectedImageKey = imageKey;
  state.selectedResult = state.results.find((r) => r.image_key === imageKey);

  renderImageList();
  renderIssueDetails();
}

function renderIssueDetails() {
  if (!state.selectedResult) {
    elements.issueDetailPanel.innerHTML = '<div class="empty-state">Select an image from the left to view detailed issues and make decisions.</div>';
    elements.issueDetailHint.textContent = "Select an image to view issues.";
    return;
  }

  const result = state.selectedResult;
  const issues = result.comparison.issues;
  const decisions = result.decisions || [];
  const decidedIndices = new Set(decisions.map((d) => d.issue_index));

  elements.issueDetailHint.textContent = `${issues.length} issues found. ${decisions.length} decisions made.`;

  if (!issues.length) {
    elements.issueDetailPanel.innerHTML = '<div class="empty-state">No issues found for this image.</div>';
    return;
  }

  elements.issueDetailPanel.innerHTML = issues
    .map((issue, index) => {
      const isDecided = decidedIndices.has(index);
      const decision = decisions.find((d) => d.issue_index === index);

      let issueContent = "";

      if (issue.type === "missing_label") {
        issueContent = `
          <div class="issue-section">
            <p class="issue-section-title">Model Suggestion:</p>
            <p class="issue-box-info">Class: <strong>${issue.class_name}</strong> (ID: ${issue.class_id})</p>
            <p class="issue-box-info">Box: ${formatBox(issue.box)}</p>
            <p class="issue-box-info">Confidence: <strong>${(issue.confidence * 100).toFixed(1)}%</strong></p>
          </div>
        `;
      } else if (issue.type === "class_conflict") {
        issueContent = `
          <div class="issue-section">
            <p class="issue-section-title">Ground Truth:</p>
            <p class="issue-box-info">Class: <strong>${issue.ground_truth.class_name}</strong> (ID: ${issue.ground_truth.class_id})</p>
            <p class="issue-box-info">Box: ${formatBox(issue.ground_truth.box)}</p>
          </div>
          <div class="issue-section">
            <p class="issue-section-title">Model Suggestion:</p>
            <p class="issue-box-info">Class: <strong>${issue.detection.class_name}</strong> (ID: ${issue.detection.class_id})</p>
            <p class="issue-box-info">Box: ${formatBox(issue.detection.box)}</p>
            <p class="issue-box-info">Confidence: <strong>${(issue.detection.confidence * 100).toFixed(1)}%</strong></p>
          </div>
          <p class="issue-iou">IoU: ${(issue.iou * 100).toFixed(1)}%</p>
        `;
      } else {
        issueContent = `
          <div class="issue-section">
            <p class="issue-section-title">Box:</p>
            <p class="issue-box-info">Class: <strong>${issue.class_name}</strong> (ID: ${issue.class_id})</p>
            <p class="issue-box-info">Box: ${formatBox(issue.box)}</p>
            ${issue.best_iou !== undefined ? `<p class="issue-box-info">Best IoU: ${(issue.best_iou * 100).toFixed(1)}%</p>` : ""}
          </div>
        `;
      }

      let actionsHtml = "";
      if (!isDecided) {
        if (issue.type === "missing_label") {
          actionsHtml = `
            <div class="issue-actions">
              <button class="btn-accept" data-index="${index}" data-decision="accept">Accept (Add Label)</button>
              <button class="btn-reject" data-index="${index}" data-decision="reject">Reject</button>
            </div>
          `;
        } else if (issue.type === "class_conflict") {
          actionsHtml = `
            <div class="issue-actions">
              <button class="btn-accept" data-index="${index}" data-decision="accept">Use Model</button>
              <button class="btn-keep" data-index="${index}" data-decision="keep">Keep Original</button>
            </div>
          `;
        } else {
          actionsHtml = `
            <div class="issue-actions">
              <button class="btn-reject" data-index="${index}" data-decision="reject">Remove Label</button>
              <button class="btn-keep" data-index="${index}" data-decision="keep">Keep Label</button>
            </div>
          `;
        }
      } else {
        const decisionLabel = {
          accept: "Accepted",
          reject: "Rejected",
          keep: "Kept",
        }[decision.decision] || decision.decision;
        const decisionClass = {
          accept: "decision-accepted",
          reject: "decision-rejected",
          keep: "decision-kept",
        }[decision.decision] || "";

        actionsHtml = `
          <div class="decision-badge ${decisionClass}">
            ${decisionLabel}
          </div>
        `;
      }

      return `
        <div class="issue-card ${getIssueTypeClass(issue.type)} ${isDecided ? "decided" : ""}">
          <div class="issue-header">
            <span class="issue-type-badge">${getIssueTypeLabel(issue.type)}</span>
            <span class="issue-index">#${index + 1}</span>
          </div>
          <p class="issue-reason">${issue.reason}</p>
          ${issueContent}
          ${actionsHtml}
        </div>
      `;
    })
    .join("");

  document.querySelectorAll("#issue-detail-panel button[data-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      const index = parseInt(button.dataset.index, 10);
      const decision = button.dataset.decision;
      await submitDecision(index, decision);
    });
  });
}

async function submitDecision(issueIndex, decision) {
  if (!state.sessionId || !state.selectedImageKey) {
    setStatus("No active session.", "error");
    return;
  }

  try {
    setStatus("Submitting decision...");

    const response = await fetch("/api/qa/decision", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: state.sessionId,
        image_key: state.selectedImageKey,
        issue_index: issueIndex,
        decision: decision,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Decision submission failed");
    }

    const result = state.selectedResult;
    if (result) {
      if (!result.decisions) {
        result.decisions = [];
      }
      result.decisions.push({
        issue_index: issueIndex,
        decision: decision,
        issue: result.comparison.issues[issueIndex],
      });
    }

    setStatus(`Decision "${decision}" recorded.`);
    renderIssueDetails();
    renderImageList();
    renderDecisionSummary();
  } catch (error) {
    setStatus(error.message || "Failed to submit decision.", "error");
  }
}

function renderDecisionSummary() {
  const allDecisions = [];
  state.results.forEach((result) => {
    (result.decisions || []).forEach((decision) => {
      allDecisions.push({
        image_key: result.image_key,
        filename: result.image_info.filename,
        ...decision,
      });
    });
  });

  if (!allDecisions.length) {
    elements.decisionPanel.innerHTML = '<div class="empty-state">Accept or reject suggestions to populate this panel.</div>';
    elements.decisionHint.textContent = "No decisions made yet.";
    return;
  }

  elements.decisionHint.textContent = `${allDecisions.length} decisions made.`;

  const grouped = {
    accept: allDecisions.filter((d) => d.decision === "accept"),
    reject: allDecisions.filter((d) => d.decision === "reject"),
    keep: allDecisions.filter((d) => d.decision === "keep"),
  };

  elements.decisionPanel.innerHTML = `
    <div class="decision-stats">
      <div class="stat-item stat-accept">
        <span class="stat-label">Accepted</span>
        <span class="stat-value">${grouped.accept.length}</span>
      </div>
      <div class="stat-item stat-reject">
        <span class="stat-label">Rejected</span>
        <span class="stat-value">${grouped.reject.length}</span>
      </div>
      <div class="stat-item stat-keep">
        <span class="stat-label">Kept</span>
        <span class="stat-value">${grouped.keep.length}</span>
      </div>
    </div>
    <div class="decision-list">
      ${allDecisions
        .map((d) => {
          const decisionClass = {
            accept: "decision-accepted",
            reject: "decision-rejected",
            keep: "decision-kept",
          }[d.decision] || "";
          const decisionLabel = {
            accept: "Accepted",
            reject: "Rejected",
            keep: "Kept",
          }[d.decision] || d.decision;

          return `
            <div class="decision-item ${decisionClass}">
              <p class="decision-filename">${d.filename}</p>
              <p class="decision-type">${getIssueTypeLabel(d.issue.type)}</p>
              <p class="decision-label">${decisionLabel}</p>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

async function runQA() {
  if (!state.imageFiles.length) {
    setStatus("Select at least one image file first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("classes_text", elements.classNames.value);
  formData.append("conf_threshold", elements.confThreshold.value);
  formData.append("iou_threshold", elements.iouThreshold.value);

  state.imageFiles.forEach((file) => formData.append("images", file));
  state.labelFiles.forEach((file) => formData.append("labels", file));

  setStatus("Running QA detection... This may take a moment.");
  elements.runQaButton.disabled = true;

  try {
    const response = await fetch("/api/qa/process", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "QA processing failed");
    }

    state.sessionId = payload.session_id;
    state.results = payload.results;
    state.selectedImageKey = null;
    state.selectedResult = null;

    elements.sessionId.textContent = state.sessionId;
    elements.exportLabelsButton.disabled = false;
    elements.exportAuditButton.disabled = false;

    updateMetrics();
    renderImageList();
    renderIssueDetails();
    renderDecisionSummary();

    const summary = payload.summary;
    if (summary.total_issues > 0) {
      setStatus(`QA complete. ${summary.total_issues} issues found across ${summary.total_images} images.`, "warn");
    } else {
      setStatus(`QA complete. No issues found across ${summary.total_images} images.`);
    }
  } catch (error) {
    setStatus(error.message || "QA processing failed.", "error");
  } finally {
    elements.runQaButton.disabled = false;
  }
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
  setStatus(`${state.imageFiles.length} image files selected.`);
});

elements.labelInput.addEventListener("change", (event) => {
  state.labelFiles = [...(event.target.files || [])];
  setStatus(`${state.labelFiles.length} label files selected.`);
});

elements.runQaButton.addEventListener("click", async () => {
  try {
    await runQA();
  } catch (error) {
    setStatus(error.message || "QA failed.", "error");
  }
});

elements.exportLabelsButton.addEventListener("click", () => {
  if (!state.sessionId) {
    return;
  }
  window.open(`/api/qa/export/labels/${state.sessionId}`, "_blank");
  setStatus("Exporting labels...");
});

elements.exportAuditButton.addEventListener("click", () => {
  if (!state.sessionId) {
    return;
  }
  window.open(`/api/qa/export/audit/${state.sessionId}`, "_blank");
  setStatus("Exporting audit report...");
});

updateMetrics();
