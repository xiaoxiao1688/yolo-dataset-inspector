const elements = {
  classNames: document.querySelector("#class-names"),
  confThreshold: document.querySelector("#conf-threshold"),
  iouThreshold: document.querySelector("#iou-threshold"),
  decisionHint: document.querySelector("#decision-hint"),
  decisionPanel: document.querySelector("#decision-panel"),
  exportAuditButton: document.querySelector("#export-audit-button"),
  exportLabelsButton: document.querySelector("#export-labels-button"),
  strictExportCheckbox: document.querySelector("#strict-export-checkbox"),
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
  previewCanvas: document.querySelector("#preview-canvas"),
  previewEmpty: document.querySelector("#preview-empty"),
  previewHint: document.querySelector("#preview-hint"),
};

const state = {
  imageFiles: [],
  labelFiles: [],
  sessionId: null,
  results: [],
  selectedImageKey: null,
  selectedResult: null,
  selectedIssueIndex: null,
  canvasImage: null,
  canvasScale: 1,
  strictExport: false,
};

const BOX_COLORS = {
  gt: { stroke: "#0088cc", fill: "rgba(0, 136, 204, 0.1)" },
  detection: { stroke: "#22c55e", fill: "rgba(34, 197, 94, 0.1)" },
  highlight: { stroke: "#f97316", fill: "rgba(249, 115, 22, 0.2)" },
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
    missing_label: "Missing Label",
    class_conflict: "Class Conflict",
    anomalous_box: "Anomalous Box",
    unmatched_ground_truth: "Unmatched GT",
  };
  return labels[type] || type;
}

function getIssueTypeClass(type) {
  const classes = {
    missing_label: "issue-missing",
    class_conflict: "issue-conflict",
    anomalous_box: "issue-anomalous",
    unmatched_ground_truth: "issue-warning",
  };
  return classes[type] || "issue-default";
}

function getDecisionForIssueType(issueType, action) {
  if (issueType === "missing_label") {
    return action === "accept" ? "accept" : "reject";
  } else if (issueType === "class_conflict") {
    return action === "accept" ? "accept" : "keep";
  } else {
    return action === "accept" ? "keep" : "reject";
  }
}

function getReviewProgress() {
  const progress = {
    total: 0,
    decided: 0,
    undecided: 0,
    byType: {},
    byImage: {},
  };

  state.results.forEach((result) => {
    const issues = result.comparison.issues || [];
    const decisions = result.decisions || [];
    const decidedIndices = new Set(decisions.map((d) => d.issue_index));

    progress.byImage[result.image_key] = {
      total: issues.length,
      decided: 0,
      undecided: 0,
    };

    issues.forEach((issue, idx) => {
      progress.total++;
      const issueType = issue.type;

      if (!progress.byType[issueType]) {
        progress.byType[issueType] = { total: 0, decided: 0, undecided: 0 };
      }
      progress.byType[issueType].total++;

      if (decidedIndices.has(idx)) {
        progress.decided++;
        progress.byType[issueType].decided++;
        progress.byImage[result.image_key].decided++;
      } else {
        progress.undecided++;
        progress.byType[issueType].undecided++;
        progress.byImage[result.image_key].undecided++;
      }
    });
  });

  progress.percentage = progress.total > 0 ? Math.round((progress.decided / progress.total) * 100) : 100;
  return progress;
}

const STORAGE_KEY = "geodraft_qa_session";

function saveSessionToStorage() {
  if (state.sessionId) {
    localStorage.setItem(STORAGE_KEY, state.sessionId);
  }
}

function clearSessionFromStorage() {
  localStorage.removeItem(STORAGE_KEY);
}

async function restoreSessionFromStorage() {
  const savedSessionId = localStorage.getItem(STORAGE_KEY);
  if (!savedSessionId) {
    return false;
  }

  try {
    setStatus("Restoring session...");
    const response = await fetch(`/api/qa/session/${savedSessionId}`);
    if (!response.ok) {
      clearSessionFromStorage();
      setStatus("Session expired. Please upload files again.");
      return false;
    }

    const sessionData = await response.json();
    state.sessionId = sessionData.session_id;
    state.results = sessionData.results || [];
    state.selectedImageKey = null;
    state.selectedResult = null;
    state.selectedIssueIndex = null;

    const config = sessionData.config || {};
    state.strictExport = config.strict_export || false;

    elements.sessionId.textContent = state.sessionId;
    elements.exportLabelsButton.disabled = false;
    elements.exportAuditButton.disabled = false;
    elements.strictExportCheckbox.disabled = false;
    elements.strictExportCheckbox.checked = state.strictExport;

    updateMetrics();
    renderImageList();
    renderIssueDetails();
    renderDecisionSummary();
    clearCanvas();

    setStatus(`Session restored: ${state.results.length} images loaded.`);
    return true;
  } catch (error) {
    console.error("Failed to restore session:", error);
    clearSessionFromStorage();
    setStatus("Failed to restore session. Please upload files again.");
    return false;
  }
}

function formatBox(box) {
  if (!box) return "N/A";
  return `x: ${box.x_center?.toFixed(4) || "?"}, y: ${box.y_center?.toFixed(4) || "?"}, w: ${box.width?.toFixed(4) || "?"}, h: ${box.height?.toFixed(4) || "?"}`;
}

function yoloToPixels(box, imgWidth, imgHeight, canvasWidth, canvasHeight) {
  const scaleX = canvasWidth / imgWidth;
  const scaleY = canvasHeight / imgHeight;

  const x_center = box.x_center * imgWidth * scaleX;
  const y_center = box.y_center * imgHeight * scaleY;
  const width = box.width * imgWidth * scaleX;
  const height = box.height * imgHeight * scaleY;

  return {
    x: x_center - width / 2,
    y: y_center - height / 2,
    width: width,
    height: height,
  };
}

function drawBox(ctx, rect, colors, label = "", lineWidth = 2) {
  ctx.strokeStyle = colors.stroke;
  ctx.fillStyle = colors.fill;
  ctx.lineWidth = lineWidth;

  ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
  ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);

  if (label) {
    ctx.font = "bold 12px sans-serif";
    const textMetrics = ctx.measureText(label);
    const textWidth = textMetrics.width + 8;
    const textHeight = 18;

    ctx.fillStyle = colors.stroke;
    ctx.fillRect(rect.x, rect.y - textHeight, textWidth, textHeight);

    ctx.fillStyle = "white";
    ctx.fillText(label, rect.x + 4, rect.y - 5);
  }
}

function clearCanvas() {
  const canvas = elements.previewCanvas;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

async function renderPreview() {
  if (!state.selectedResult) {
    elements.previewCanvas.style.display = "none";
    elements.previewEmpty.style.display = "flex";
    elements.previewHint.textContent = "Select an image to preview with boxes.";
    return;
  }

  const result = state.selectedResult;
  const imageFilename = result.image_filename;
  const imgWidth = result.image_info.width;
  const imgHeight = result.image_info.height;

  elements.previewHint.textContent = `${result.image_info.filename} (${imgWidth} × ${imgHeight})`;

  try {
    const imageUrl = `/api/qa/image/${state.sessionId}/${imageFilename}`;
    const img = new Image();
    img.crossOrigin = "anonymous";

    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = imageUrl;
    });

    const canvas = elements.previewCanvas;
    const container = canvas.parentElement;

    const maxWidth = container.clientWidth - 32;
    const maxHeight = Math.min(500, window.innerHeight * 0.4);

    let scale = 1;
    if (imgWidth > maxWidth) {
      scale = maxWidth / imgWidth;
    }
    const scaledHeight = imgHeight * scale;
    if (scaledHeight > maxHeight) {
      scale = maxHeight / imgHeight;
    }

    const canvasWidth = Math.max(1, Math.floor(imgWidth * scale));
    const canvasHeight = Math.max(1, Math.floor(imgHeight * scale));

    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    state.canvasScale = scale;
    state.canvasImage = img;

    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    ctx.drawImage(img, 0, 0, canvasWidth, canvasHeight);

    const groundTruth = result.ground_truth || [];
    const detections = result.detections || [];

    groundTruth.forEach((box, index) => {
      const rect = yoloToPixels(box, imgWidth, imgHeight, canvasWidth, canvasHeight);
      const label = `GT #${index + 1}`;
      drawBox(ctx, rect, BOX_COLORS.gt, label);
    });

    detections.forEach((box, index) => {
      const rect = yoloToPixels(box, imgWidth, imgHeight, canvasWidth, canvasHeight);
      const label = `Det #${index + 1} (${(box.confidence * 100).toFixed(0)}%)`;
      drawBox(ctx, rect, BOX_COLORS.detection, label);
    });

    if (state.selectedIssueIndex !== null) {
      highlightIssueBox(state.selectedIssueIndex);
    }

    elements.previewCanvas.style.display = "block";
    elements.previewEmpty.style.display = "none";
  } catch (error) {
    console.error("Failed to render preview:", error);
    elements.previewHint.textContent = "Failed to load image: " + error.message;
  }
}

function highlightIssueBox(issueIndex) {
  if (!state.selectedResult || !state.canvasImage) {
    return;
  }

  const result = state.selectedResult;
  const issues = result.comparison.issues;
  if (issueIndex < 0 || issueIndex >= issues.length) {
    return;
  }

  const issue = issues[issueIndex];
  const imgWidth = result.image_info.width;
  const imgHeight = result.image_info.height;
  const canvas = elements.previewCanvas;
  const ctx = canvas.getContext("2d");

  if (issue.type === "missing_label") {
    const rect = yoloToPixels(issue.box, imgWidth, imgHeight, canvas.width, canvas.height);
    drawBox(ctx, rect, BOX_COLORS.highlight, "Selected (Det)", 3);
  } else if (issue.type === "class_conflict") {
    if (issue.ground_truth && issue.ground_truth.box) {
      const rect = yoloToPixels(issue.ground_truth.box, imgWidth, imgHeight, canvas.width, canvas.height);
      drawBox(ctx, rect, BOX_COLORS.highlight, "Selected (GT)", 3);
    }
    if (issue.detection && issue.detection.box) {
      const rect = yoloToPixels(issue.detection.box, imgWidth, imgHeight, canvas.width, canvas.height);
      drawBox(ctx, rect, BOX_COLORS.highlight, "Selected (Det)", 3);
    }
  } else if (issue.source === "ground_truth" && issue.box) {
    const rect = yoloToPixels(issue.box, imgWidth, imgHeight, canvas.width, canvas.height);
    drawBox(ctx, rect, BOX_COLORS.highlight, "Selected (GT)", 3);
  }
}

function selectIssue(issueIndex) {
  state.selectedIssueIndex = issueIndex;

  document.querySelectorAll("#issue-detail-panel .issue-card").forEach((card, index) => {
    if (index === issueIndex) {
      card.classList.add("highlighted");
    } else {
      card.classList.remove("highlighted");
    }
  });

  if (state.canvasImage) {
    renderPreview();
  }
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
  state.selectedIssueIndex = null;

  renderImageList();
  renderIssueDetails();
  renderPreview();
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

  const undecidedCount = issues.length - decisions.length;
  elements.issueDetailHint.textContent = `${issues.length} issues found. ${decisions.length} decided, ${undecidedCount} pending.`;

  if (!issues.length) {
    elements.issueDetailPanel.innerHTML = '<div class="empty-state">No issues found for this image.</div>';
    return;
  }

  const issueTypeStats = {};
  issues.forEach((issue, idx) => {
    const type = issue.type;
    if (!issueTypeStats[type]) {
      issueTypeStats[type] = { total: 0, undecided: 0 };
    }
    issueTypeStats[type].total++;
    if (!decidedIndices.has(idx)) {
      issueTypeStats[type].undecided++;
    }
  });

  let batchActionsHtml = "";
  if (undecidedCount > 0) {
    const typeButtons = Object.entries(issueTypeStats)
      .filter(([_, stats]) => stats.undecided > 0)
      .map(([type, stats]) => {
        const typeLabel = getIssueTypeLabel(type);
        const acceptDecision = getDecisionForIssueType(type, "accept");
        const rejectDecision = getDecisionForIssueType(type, "reject");

        let acceptLabel = "Accept";
        let rejectLabel = "Reject";
        if (type === "missing_label") {
          acceptLabel = "Accept All";
          rejectLabel = "Reject All";
        } else if (type === "class_conflict") {
          acceptLabel = "Use Model";
          rejectLabel = "Keep Original";
        } else {
          acceptLabel = "Keep All";
          rejectLabel = "Remove All";
        }

        return `
          <div class="batch-type-group" data-type="${type}">
            <span class="batch-type-label">${typeLabel} (${stats.undecided}/${stats.total})</span>
            <div class="batch-type-buttons">
              <button class="batch-accept" data-type="${type}" data-decision="${acceptDecision}">${acceptLabel}</button>
              <button class="batch-reject" data-type="${type}" data-decision="${rejectDecision}">${rejectLabel}</button>
            </div>
          </div>
        `;
      })
      .join("");

    if (typeButtons) {
      batchActionsHtml = `
        <div class="batch-actions-panel">
          <p class="batch-actions-title">Batch Actions (Undecided: ${undecidedCount})</p>
          <div class="batch-actions-content">
            ${typeButtons}
          </div>
        </div>
      `;
    }
  }

  const issuesHtml = issues
    .map((issue, index) => {
      const isDecided = decidedIndices.has(index);
      const isHighlighted = state.selectedIssueIndex === index;
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
        <div class="issue-card ${getIssueTypeClass(issue.type)} ${isDecided ? "decided" : ""} ${isHighlighted ? "highlighted" : ""}" data-issue-index="${index}" data-issue-type="${issue.type}">
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

  elements.issueDetailPanel.innerHTML = batchActionsHtml + '<div class="issues-list-container">' + issuesHtml + "</div>";

  document.querySelectorAll("#issue-detail-panel .issue-card").forEach((card) => {
    card.addEventListener("click", (event) => {
      if (event.target.tagName === "BUTTON") {
        return;
      }
      const index = parseInt(card.dataset.issueIndex, 10);
      selectIssue(index);
    });
  });

  document.querySelectorAll("#issue-detail-panel button[data-index]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const index = parseInt(button.dataset.index, 10);
      const decision = button.dataset.decision;
      await submitDecision(index, decision);
    });
  });

  document.querySelectorAll("#issue-detail-panel .batch-accept, #issue-detail-panel .batch-reject").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const issueType = button.dataset.type;
      const decision = button.dataset.decision;
      await submitBatchDecision(issueType, decision);
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

      let existingIndex = -1;
      for (let i = 0; i < result.decisions.length; i++) {
        if (result.decisions[i].issue_index === issueIndex) {
          existingIndex = i;
          break;
        }
      }

      const newDecision = {
        issue_index: issueIndex,
        decision: decision,
        issue: result.comparison.issues[issueIndex],
      };

      if (existingIndex >= 0) {
        result.decisions[existingIndex] = newDecision;
      } else {
        result.decisions.push(newDecision);
      }
    }

    setStatus(`Decision "${decision}" recorded.`);
    renderIssueDetails();
    renderImageList();
    renderDecisionSummary();
  } catch (error) {
    setStatus(error.message || "Failed to submit decision.", "error");
  }
}

async function submitBatchDecision(issueType, decision) {
  if (!state.sessionId || !state.selectedImageKey) {
    setStatus("No active session.", "error");
    return;
  }

  const result = state.selectedResult;
  if (!result) {
    return;
  }

  const issues = result.comparison.issues;
  const decisions = result.decisions || [];
  const decidedIndices = new Set(decisions.map((d) => d.issue_index));

  const targetIndices = issues
    .map((issue, idx) => ({ issue, idx }))
    .filter(({ issue, idx }) => issue.type === issueType && !decidedIndices.has(idx))
    .map(({ idx }) => idx);

  if (targetIndices.length === 0) {
    setStatus("No undecided issues of this type.", "warn");
    return;
  }

  try {
    setStatus(`Processing ${targetIndices.length} decisions...`);

    const response = await fetch("/api/qa/decision/batch", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: state.sessionId,
        image_key: state.selectedImageKey,
        issue_type: issueType,
        decision: decision,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to submit batch decisions");
    }

    if (result.decisions) {
      result.decisions = [];
    }

    const freshResponse = await fetch(`/api/qa/session/${state.sessionId}`);
    if (freshResponse.ok) {
      const freshData = await freshResponse.json();
      state.results = freshData.results || [];
      const updatedResult = state.results.find((r) => r.image_key === state.selectedImageKey);
      if (updatedResult) {
        state.selectedResult = updatedResult;
      }
    }

    const processedCount = payload.processed_count || 0;
    const totalCount = payload.total_count || targetIndices.length;

    if (processedCount === totalCount) {
      setStatus(`Successfully processed ${processedCount} decisions.`);
    } else {
      setStatus(`Processed ${processedCount}/${totalCount} decisions.`, "warn");
    }

    renderIssueDetails();
    renderImageList();
    renderDecisionSummary();
  } catch (error) {
    setStatus(error.message || "Failed to submit batch decisions.", "error");
  }
}

async function setStrictExport(enabled) {
  if (!state.sessionId) {
    setStatus("No active session.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/qa/config/${state.sessionId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        strict_export: enabled,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to set strict export mode");
    }

    if (state.sessionId) {
      const progressResponse = await fetch(`/api/qa/progress/${state.sessionId}`);
      if (progressResponse.ok) {
        const progressData = await progressResponse.json();
        state.strictExport = progressData.strict_export || false;
      }
    }

    const modeText = enabled ? "enabled" : "disabled";
    setStatus(`Strict export mode ${modeText}.`);
  } catch (error) {
    setStatus(error.message || "Failed to set strict export mode.", "error");
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

  const progress = getReviewProgress();

  if (progress.total === 0) {
    elements.decisionPanel.innerHTML = '<div class="empty-state">No issues to review. All labels look good!</div>';
    elements.decisionHint.textContent = "No issues found.";
    return;
  }

  const progressPercent = progress.percentage;
  const isComplete = progressPercent === 100;

  elements.decisionHint.textContent = `Review Progress: ${progressPercent}% (${progress.decided}/${progress.total} decided, ${progress.undecided} pending)`;

  const grouped = {
    accept: allDecisions.filter((d) => d.decision === "accept"),
    reject: allDecisions.filter((d) => d.decision === "reject"),
    keep: allDecisions.filter((d) => d.decision === "keep"),
  };

  let byTypeStatsHtml = "";
  if (Object.keys(progress.byType).length > 0) {
    byTypeStatsHtml = Object.entries(progress.byType)
      .map(([type, stats]) => {
        const typeLabel = getIssueTypeLabel(type);
        const typePercent = stats.total > 0 ? Math.round((stats.decided / stats.total) * 100) : 100;
        return `
          <div class="type-progress-item">
            <span class="type-progress-label">${typeLabel}: ${stats.decided}/${stats.total}</span>
            <div class="type-progress-bar">
              <div class="type-progress-fill" style="width: ${typePercent}%"></div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  let completenessHtml = "";
  if (!isComplete) {
    completenessHtml = `
      <div class="incomplete-warning">
        <strong>⚠️ ${progress.undecided} issues pending decision.</strong>
        <p>Exported labels will use original/unchanged values for undecided issues.</p>
      </div>
    `;
  } else {
    completenessHtml = `
      <div class="complete-badge">
        <strong>✓ All issues reviewed!</strong>
        <p>Ready to export.</p>
      </div>
    `;
  }

  let decisionsListHtml = "";
  if (allDecisions.length > 0) {
    decisionsListHtml = `
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

  elements.decisionPanel.innerHTML = `
    <div class="progress-overview">
      <div class="progress-bar-container">
        <div class="progress-bar">
          <div class="progress-fill ${isComplete ? "complete" : ""}" style="width: ${progressPercent}%"></div>
        </div>
        <span class="progress-text">${progressPercent}%</span>
      </div>
      ${byTypeStatsHtml}
    </div>
    ${completenessHtml}
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
    ${decisionsListHtml}
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
    state.selectedIssueIndex = null;
    state.strictExport = false;

    elements.sessionId.textContent = state.sessionId;
    elements.exportLabelsButton.disabled = false;
    elements.exportAuditButton.disabled = false;
    elements.strictExportCheckbox.disabled = false;
    elements.strictExportCheckbox.checked = false;

    saveSessionToStorage();

    updateMetrics();
    renderImageList();
    renderIssueDetails();
    renderDecisionSummary();
    clearCanvas();
    elements.previewCanvas.style.display = "none";
    elements.previewEmpty.style.display = "flex";

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

elements.strictExportCheckbox.addEventListener("change", async () => {
  const enabled = elements.strictExportCheckbox.checked;
  await setStrictExport(enabled);
});

elements.exportLabelsButton.addEventListener("click", async () => {
  if (!state.sessionId) {
    return;
  }

  try {
    const response = await fetch(`/api/qa/export/labels/${state.sessionId}`);

    if (!response.ok) {
      const payload = await response.json();
      if (response.status === 400 && payload.error === "Export blocked: pending decisions exist") {
        const progress = payload.progress || {};
        setStatus(
          `Export blocked: ${progress.undecided || "unknown"} issues pending. Complete all reviews or disable Strict Export.`,
          "error"
        );
        return;
      }
      throw new Error(payload.error || "Export failed");
    }

    window.open(`/api/qa/export/labels/${state.sessionId}`, "_blank");
    setStatus("Exporting labels...");
  } catch (error) {
    setStatus(error.message || "Export failed.", "error");
  }
});

elements.exportAuditButton.addEventListener("click", () => {
  if (!state.sessionId) {
    return;
  }

  const progress = getReviewProgress();
  if (progress.undecided > 0) {
    setStatus(`Audit export: ${progress.undecided} issues pending decision.`, "warn");
  }

  window.open(`/api/qa/export/audit/${state.sessionId}`, "_blank");
  setStatus("Exporting audit report...");
});

window.addEventListener("resize", () => {
  if (state.selectedResult && state.canvasImage) {
    renderPreview();
  }
});

updateMetrics();

(async () => {
  const restored = await restoreSessionFromStorage();
  if (!restored) {
    setStatus("Ready. Upload images and labels to begin QA.");
  }
})();
