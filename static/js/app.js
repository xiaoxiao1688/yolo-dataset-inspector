const elements = {
  analyzeButton: document.querySelector("#analyze-button"),
  classNames: document.querySelector("#class-names"),
  exportReportButton: document.querySelector("#export-report-button"),
  fileList: document.querySelector("#file-list"),
  heroHealth: document.querySelector("#hero-health"),
  heroTaskType: document.querySelector("#hero-task-type"),
  imageInput: document.querySelector("#image-input"),
  inventoryHint: document.querySelector("#inventory-hint"),
  issueHint: document.querySelector("#issue-hint"),
  issueList: document.querySelector("#issue-list"),
  labelInput: document.querySelector("#label-input"),
  labelTextList: document.querySelector("#label-text-list"),
  metricImages: document.querySelector("#metric-images"),
  metricIssues: document.querySelector("#metric-issues"),
  metricLabels: document.querySelector("#metric-labels"),
  metricPairs: document.querySelector("#metric-pairs"),
  previewCanvas: document.querySelector("#preview-canvas"),
  previewCanvasTab: document.querySelector("#preview-canvas-tab"),
  previewImageMeta: document.querySelector("#preview-image-meta"),
  previewLabelMeta: document.querySelector("#preview-label-meta"),
  previewLabelsTab: document.querySelector("#preview-labels-tab"),
  previewName: document.querySelector("#preview-name"),
  previewTabs: document.querySelectorAll(".preview-tab"),
  previewContents: document.querySelectorAll(".preview-content"),
  statusLine: document.querySelector("#status-line"),
  taskType: document.querySelector("#task-type"),
  // Filter elements
  severityFilter: document.querySelector("#severity-filter"),
  codeFilter: document.querySelector("#code-filter"),
  selectedFileOnly: document.querySelector("#selected-file-only"),
};

const state = {
  datasetEntries: [],
  imageFiles: [],
  issues: [],
  labelFiles: [],
  previewImage: null,
  selectedEntryKey: null,
  selectedIssue: null,
  highlightedRecordIndex: null,
  highlightedLineNumber: null,
  taskType: "detect",
};

function getIssueFilterState() {
  return {
    severity: elements.severityFilter ? elements.severityFilter.value : "all",
    codeFilter: elements.codeFilter ? elements.codeFilter.value.trim().toLowerCase() : "",
    selectedFileOnly: elements.selectedFileOnly ? elements.selectedFileOnly.checked : false,
  };
}

function setStatus(message, type = "info") {
  elements.statusLine.textContent = message;
  elements.heroHealth.textContent = type === "error" ? "Blocked" : type === "warn" ? "Needs review" : "Ready";
}

function normalizeBaseName(filename) {
  return String(filename || "").replace(/\.[^.]+$/, "").trim().toLowerCase();
}

function parseClassNames() {
  return elements.classNames.value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function createIssue(level, code, message, entryKey = null, line = null) {
  return { level, code, message, entryKey, line };
}

function getIssueWeight(level) {
  return level === "error" ? 2 : 1;
}

function getFilteredIssues() {
  const { severity, codeFilter, selectedFileOnly } = getIssueFilterState();

  return state.issues
    .map((issue, originalIndex) => ({ issue, originalIndex }))
    .filter(({ issue }) => {
      if (severity !== "all" && issue.level !== severity) {
        return false;
      }

      if (codeFilter && !issue.code.toLowerCase().includes(codeFilter)) {
        return false;
      }

      if (selectedFileOnly && issue.entryKey !== state.selectedEntryKey) {
        return false;
      }

      return true;
    })
    .sort((a, b) => getIssueWeight(b.issue.level) - getIssueWeight(a.issue.level));
}

function describeIssueFilterSummary() {
  const { severity, codeFilter, selectedFileOnly } = getIssueFilterState();
  const parts = [];

  if (severity !== "all") {
    parts.push(severity);
  }

  if (codeFilter) {
    parts.push(`code:${codeFilter}`);
  }

  if (selectedFileOnly) {
    parts.push(state.selectedEntryKey ? `file:${state.selectedEntryKey}` : "selected file");
  }

  return parts.length ? parts.join(" | ") : "all issues";
}

function refreshIssueFeedFeedback() {
  const filteredIssues = getFilteredIssues();
  const totalIssues = state.issues.length;
  const filterSummary = describeIssueFilterSummary();

  if (totalIssues === 0) {
    elements.issueHint.textContent = "No issues reported yet.";
    return;
  }

  if (filteredIssues.length === totalIssues && filterSummary === "all issues") {
    elements.issueHint.textContent = `${totalIssues} issues found. Highest severity first.`;
    return;
  }

  elements.issueHint.textContent = `Showing ${filteredIssues.length} of ${totalIssues} issues for ${filterSummary}.`;
}

function updateFilterStatus() {
  if (!state.datasetEntries.length) {
    return;
  }

  const filteredCount = getFilteredIssues().length;
  const filterSummary = describeIssueFilterSummary();
  const message = filteredCount
    ? `Issue filter active: ${filterSummary}. ${filteredCount} issues shown.`
    : `Issue filter active: ${filterSummary}. No matching issues.`;

  setStatus(message, filteredCount === 0 && state.issues.length > 0 ? "warn" : "info");
}

async function loadImageInfo(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      resolve({ url, width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Failed to load image: ${file.name}`));
    };
    image.src = url;
  });
}

function parseDetectLine(parts, classNamesLength, lineNumber) {
  if (parts.length !== 5) {
    return {
      issue: createIssue("error", "detect_format", "Detect label must contain 5 values.", null, lineNumber),
    };
  }

  const classId = Number(parts[0]);
  const xCenter = Number(parts[1]);
  const yCenter = Number(parts[2]);
  const width = Number(parts[3]);
  const height = Number(parts[4]);
  const numericValues = [classId, xCenter, yCenter, width, height];

  if (numericValues.some((value) => !Number.isFinite(value))) {
    return {
      issue: createIssue("error", "detect_nan", "Detect label contains non-numeric values.", null, lineNumber),
    };
  }

  if (!Number.isInteger(classId) || classId < 0) {
    return {
      issue: createIssue("error", "class_id", "Class id must be a non-negative integer.", null, lineNumber),
    };
  }

  if (classNamesLength > 0 && classId >= classNamesLength) {
    return {
      issue: createIssue("error", "class_range", "Class id is outside the configured class list.", null, lineNumber),
    };
  }

  const normalizedValues = [xCenter, yCenter, width, height];
  if (normalizedValues.some((value) => value < 0 || value > 1)) {
    return {
      issue: createIssue("error", "normalized_range", "Detect coordinates must stay within 0..1.", null, lineNumber),
    };
  }

  return {
    record: { type: "detect", classId, xCenter, yCenter, width, height },
  };
}

function parseSegmentLine(parts, classNamesLength, lineNumber) {
  if (parts.length < 7 || parts.length % 2 === 0) {
    return {
      issue: createIssue("error", "segment_format", "Segment label needs class id plus point pairs.", null, lineNumber),
    };
  }

  const classId = Number(parts[0]);
  if (!Number.isInteger(classId) || classId < 0) {
    return {
      issue: createIssue("error", "class_id", "Class id must be a non-negative integer.", null, lineNumber),
    };
  }

  if (classNamesLength > 0 && classId >= classNamesLength) {
    return {
      issue: createIssue("error", "class_range", "Class id is outside the configured class list.", null, lineNumber),
    };
  }

  const values = parts.slice(1).map(Number);
  if (values.some((value) => !Number.isFinite(value))) {
    return {
      issue: createIssue("error", "segment_nan", "Segment label contains non-numeric values.", null, lineNumber),
    };
  }

  const points = [];
  for (let index = 0; index < values.length; index += 2) {
    const x = values[index];
    const y = values[index + 1];
    if (x < 0 || x > 1 || y < 0 || y > 1) {
      return {
        issue: createIssue("error", "normalized_range", "Segment coordinates must stay within 0..1.", null, lineNumber),
      };
    }
    points.push({ x, y });
  }

  if (points.length < 3) {
    return {
      issue: createIssue("error", "segment_points", "Segment polygon needs at least 3 points.", null, lineNumber),
    };
  }

  return {
    record: { type: "segment", classId, points },
  };
}

function parseLabelText(text, taskType, classNamesLength, entryKey) {
  const records = [];
  const issues = [];
  const rawLines = String(text || "").split(/\r?\n/);
  const lineToRecordMap = new Map();
  const lineToIssueMap = new Map();
  let recordIndex = 0;

  if (!rawLines.some((line) => line.trim())) {
    issues.push(createIssue("warning", "empty_label", "Label file is empty.", entryKey));
    return {
      records,
      issues,
      rawText: text,
      rawLines,
      lineToRecordMap,
      lineToIssueMap,
    };
  }

  for (let rawLineIndex = 0; rawLineIndex < rawLines.length; rawLineIndex++) {
    const rawLine = rawLines[rawLineIndex];
    const trimmedLine = rawLine.trim();
    const lineNumber = rawLineIndex + 1;

    if (!trimmedLine) {
      continue;
    }

    const parts = trimmedLine.split(/\s+/);
    const result =
      taskType === "segment"
        ? parseSegmentLine(parts, classNamesLength, lineNumber)
        : parseDetectLine(parts, classNamesLength, lineNumber);

    if (result.issue) {
      result.issue.entryKey = entryKey;
      result.issue.rawLineText = rawLine;
      issues.push(result.issue);

      const existingIssues = lineToIssueMap.get(lineNumber) || [];
      existingIssues.push(result.issue);
      lineToIssueMap.set(lineNumber, existingIssues);
    } else if (result.record) {
      result.record.rawLineNumber = lineNumber;
      result.record.rawLineText = rawLine;
      records.push(result.record);
      lineToRecordMap.set(lineNumber, recordIndex);
      recordIndex++;
    }
  }

  return {
    records,
    issues,
    rawText: text,
    rawLines,
    lineToRecordMap,
    lineToIssueMap,
  };
}

function collectDuplicateIssues(files, kind) {
  const seen = new Map();
  const issues = [];

  files.forEach((file) => {
    const key = normalizeBaseName(file.name);
    if (!key) {
      return;
    }
    const count = seen.get(key) || 0;
    seen.set(key, count + 1);
  });

  for (const [key, count] of seen.entries()) {
    if (count > 1) {
      issues.push(createIssue("warning", "duplicate_basename", `${kind} basename "${key}" appears ${count} times.`, key));
    }
  }

  return issues;
}

async function buildDatasetEntries() {
  const classNames = parseClassNames();
  const imageMap = new Map();
  const labelMap = new Map();

  state.imageFiles.forEach((file) => {
    const key = normalizeBaseName(file.name);
    if (key && !imageMap.has(key)) {
      imageMap.set(key, file);
    }
  });

  state.labelFiles.forEach((file) => {
    const key = normalizeBaseName(file.name);
    if (key && !labelMap.has(key)) {
      labelMap.set(key, file);
    }
  });

  const allKeys = [...new Set([...imageMap.keys(), ...labelMap.keys()])].sort();
  const entries = [];
  const issues = [
    ...collectDuplicateIssues(state.imageFiles, "Image"),
    ...collectDuplicateIssues(state.labelFiles, "Label"),
  ];

  for (const key of allKeys) {
    const imageFile = imageMap.get(key) || null;
    const labelFile = labelMap.get(key) || null;
    const entry = {
      key,
      imageFile,
      labelFile,
      imageInfo: null,
      records: [],
      issues: [],
      labelRawText: null,
      labelRawLines: [],
      lineToRecordMap: new Map(),
      lineToIssueMap: new Map(),
    };

    if (!imageFile) {
      entry.issues.push(createIssue("warning", "missing_image", "No image matches this label file.", key));
    }

    if (!labelFile) {
      entry.issues.push(createIssue("warning", "missing_label", "No label matches this image file.", key));
    }

    if (imageFile) {
      try {
        entry.imageInfo = await loadImageInfo(imageFile);
      } catch (error) {
        entry.issues.push(createIssue("error", "image_load", error.message, key));
      }
    }

    if (labelFile) {
      const labelText = await labelFile.text();
      const parsed = parseLabelText(labelText, state.taskType, classNames.length, key);
      entry.records = parsed.records;
      entry.issues.push(...parsed.issues);
      entry.labelRawText = parsed.rawText;
      entry.labelRawLines = parsed.rawLines;
      entry.lineToRecordMap = parsed.lineToRecordMap;
      entry.lineToIssueMap = parsed.lineToIssueMap;
    }

    issues.push(...entry.issues);
    entries.push(entry);
  }

  return { entries, issues };
}

function renderDatasetList() {
  if (!state.datasetEntries.length) {
    elements.fileList.innerHTML = '<li class="empty-state">Run analysis to build the dataset list.</li>';
    return;
  }

  const sortedEntries = [...state.datasetEntries].sort((left, right) => {
    const leftWeight = left.issues.reduce((sum, issue) => sum + getIssueWeight(issue.level), 0);
    const rightWeight = right.issues.reduce((sum, issue) => sum + getIssueWeight(issue.level), 0);
    return rightWeight - leftWeight || left.key.localeCompare(right.key);
  });

  elements.fileList.innerHTML = sortedEntries
    .map((entry) => {
      const issueCount = entry.issues.length;
      const imageLabel = entry.imageFile ? entry.imageFile.name : "missing image";
      const labelLabel = entry.labelFile ? entry.labelFile.name : "missing label";
      const activeClass = entry.key === state.selectedEntryKey ? "stack-item active" : "stack-item";

      return `
        <li class="${activeClass}">
          <button type="button" data-entry-key="${entry.key}">
            <p class="item-title">${entry.key}</p>
            <p class="item-meta">${imageLabel} | ${labelLabel}</p>
            <p class="item-meta">${entry.records.length} parsed records | ${issueCount} issues</p>
          </button>
        </li>
      `;
    })
    .join("");
}

function updateMetrics() {
  const matchedPairs = state.datasetEntries.filter((entry) => entry.imageFile && entry.labelFile).length;
  elements.metricImages.textContent = String(state.imageFiles.length);
  elements.metricLabels.textContent = String(state.labelFiles.length);
  elements.metricPairs.textContent = String(matchedPairs);
  elements.metricIssues.textContent = String(state.issues.length);
  elements.inventoryHint.textContent = state.datasetEntries.length
    ? `${state.datasetEntries.length} files tracked in the current dataset view.`
    : "No analysis yet.";
  refreshIssueFeedFeedback();
}

function renderIssueList() {
  const filteredIssues = getFilteredIssues();

  if (!filteredIssues.length) {
    if (state.issues.length === 0) {
      elements.issueList.innerHTML = '<li class="empty-state">Dataset issues will appear here.</li>';
    } else if (elements.selectedFileOnly && elements.selectedFileOnly.checked && !state.selectedEntryKey) {
      elements.issueList.innerHTML = '<li class="empty-state">Select a dataset item to filter issues by file.</li>';
    } else {
      elements.issueList.innerHTML = '<li class="empty-state">No issues match the current filter.</li>';
    }
    return;
  }

  elements.issueList.innerHTML = filteredIssues
    .map(({ issue, originalIndex }) => {
      const baseClass = issue.level === "error" ? "issue-error" : "issue-warning";
      const selectedClass = state.selectedIssue === originalIndex ? " selected" : "";
      const itemClass = `stack-item ${baseClass} issue-item-clickable${selectedClass}`;

      const lineMeta = issue.line ? ` | line ${issue.line}` : "";
      const keyMeta = issue.entryKey ? ` | ${issue.entryKey}` : "";

      const dataAttrs = [];
      if (issue.entryKey) dataAttrs.push(`data-entry-key="${issue.entryKey}"`);
      if (issue.line) dataAttrs.push(`data-line="${issue.line}"`);
      dataAttrs.push(`data-issue-index="${originalIndex}"`);

      return `
        <li class="${itemClass}" ${dataAttrs.join(" ")}>
          <p class="issue-title">${issue.code}</p>
          <p class="issue-meta">${issue.message}${keyMeta}${lineMeta}</p>
        </li>
      `;
    })
    .join("");
}

function getSelectedEntry() {
  if (!state.selectedEntryKey) {
    return null;
  }
  return state.datasetEntries.find((entry) => entry.key === state.selectedEntryKey) || null;
}

function getRecordIndexFromLineNumber(entry, lineNumber) {
  if (!entry || !entry.lineToRecordMap) {
    return null;
  }
  const recordIndex = entry.lineToRecordMap.get(lineNumber);
  return recordIndex !== undefined ? recordIndex : null;
}

function getIssuesFromLineNumber(entry, lineNumber) {
  if (!entry || !entry.lineToIssueMap) {
    return [];
  }
  return entry.lineToIssueMap.get(lineNumber) || [];
}

function selectIssue(issueIndex) {
  if (issueIndex === null || issueIndex === undefined || issueIndex < 0 || issueIndex >= state.issues.length) {
    state.selectedIssue = null;
    state.highlightedRecordIndex = null;
    state.highlightedLineNumber = null;
    renderIssueList();
    renderPreview();
    renderLabelTextList();
    return;
  }

  const issue = state.issues[issueIndex];
  state.selectedIssue = issueIndex;

  if (issue.entryKey) {
    if (state.selectedEntryKey !== issue.entryKey) {
      state.selectedEntryKey = issue.entryKey;
      state.previewImage = null;
      renderDatasetList();
    }

    if (issue.line !== undefined && issue.line !== null) {
      state.highlightedLineNumber = issue.line;

      const entry = getSelectedEntry();
      if (entry) {
        const recordIndex = getRecordIndexFromLineNumber(entry, issue.line);
        state.highlightedRecordIndex = recordIndex;

        switchPreviewTab("labels");
      }
    } else {
      state.highlightedLineNumber = null;
      state.highlightedRecordIndex = null;
    }
  } else {
    state.highlightedLineNumber = null;
    state.highlightedRecordIndex = null;
  }

  setStatus(`Selected issue: ${issue.code}${issue.line ? ` at line ${issue.line}` : ""}`);
  renderIssueList();
  renderPreview();
  renderLabelTextList();
}

function selectLabelLine(lineNumber) {
  const entry = getSelectedEntry();
  if (!entry) {
    return;
  }

  state.highlightedLineNumber = lineNumber;

  const recordIndex = getRecordIndexFromLineNumber(entry, lineNumber);
  state.highlightedRecordIndex = recordIndex;

  const issues = getIssuesFromLineNumber(entry, lineNumber);
  if (issues.length > 0) {
    for (let i = 0; i < state.issues.length; i++) {
      if (state.issues[i] === issues[0]) {
        state.selectedIssue = i;
        break;
      }
    }
  } else {
    state.selectedIssue = null;
  }

  if (recordIndex !== null) {
    switchPreviewTab("canvas");
  }

  renderIssueList();
  renderPreview();
  renderLabelTextList();
}

function switchPreviewTab(tabId) {
  if (!elements.previewTabs || !elements.previewContents) {
    return;
  }

  elements.previewTabs.forEach((tab) => {
    if (tab.dataset.tab === tabId) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });

  elements.previewContents.forEach((content) => {
    if (tabId === "canvas" && content.id === "preview-canvas-tab") {
      content.classList.add("active");
    } else if (tabId === "labels" && content.id === "preview-labels-tab") {
      content.classList.add("active");
    } else {
      content.classList.remove("active");
    }
  });
}

function renderLabelTextList() {
  if (!elements.labelTextList) {
    return;
  }

  const entry = getSelectedEntry();
  if (!entry || !entry.labelRawLines || entry.labelRawLines.length === 0) {
    elements.labelTextList.innerHTML = '<div class="empty-state">Select a dataset item with labels to view.</div>';
    return;
  }

  const html = entry.labelRawLines
    .map((line, index) => {
      const lineNumber = index + 1;
      const isHighlighted = state.highlightedLineNumber === lineNumber;
      const issues = getIssuesFromLineNumber(entry, lineNumber);
      const hasIssue = issues.length > 0;
      const hasError = issues.some((i) => i.level === "error");
      const recordIndex = getRecordIndexFromLineNumber(entry, lineNumber);
      const isParsedRecord = recordIndex !== null;

      let lineClasses = "label-line";
      if (isHighlighted) lineClasses += " selected";
      if (hasError) lineClasses += " has-error";
      else if (hasIssue) lineClasses += " has-warning";

      let statusHtml = "";
      if (hasIssue) {
        const issueType = hasError ? "error" : "warning";
        const issueCodes = issues.map((i) => i.code).join(", ");
        statusHtml = `<span class="label-line-status ${issueType}">${issueCodes}</span>`;
      } else if (isParsedRecord) {
        statusHtml = `<span class="label-line-status" style="color: #86efac;">record #${recordIndex}</span>`;
      }

      const displayLine = line || " ";

      return `
        <div class="${lineClasses}" data-line-number="${lineNumber}">
          <span class="label-line-number">${lineNumber}</span>
          <span class="label-line-content">${escapeHtml(displayLine)}${statusHtml}</span>
        </div>
      `;
    })
    .join("");

  elements.labelTextList.innerHTML = html;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function fitImageToCanvas(imageWidth, imageHeight, canvasWidth, canvasHeight) {
  const scale = Math.min(canvasWidth / imageWidth, canvasHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return {
    scale,
    width,
    height,
    x: (canvasWidth - width) / 2,
    y: (canvasHeight - height) / 2,
  };
}

function drawDetectRecord(context, record, frame, isHighlighted = false) {
  const boxWidth = record.width * frame.width;
  const boxHeight = record.height * frame.height;
  const x = frame.x + (record.xCenter * frame.width - boxWidth / 2);
  const y = frame.y + (record.yCenter * frame.height - boxHeight / 2);

  if (isHighlighted) {
    context.setLineDash([6, 4]);
    context.lineWidth = 4;
    context.strokeRect(x, y, boxWidth, boxHeight);
    context.setLineDash([]);
    context.lineWidth = 2;
  } else {
    context.strokeRect(x, y, boxWidth, boxHeight);
  }
}

function drawSegmentRecord(context, record, frame, isHighlighted = false) {
  if (!record.points.length) {
    return;
  }

  context.beginPath();
  record.points.forEach((point, index) => {
    const x = frame.x + point.x * frame.width;
    const y = frame.y + point.y * frame.height;
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  context.closePath();

  if (isHighlighted) {
    context.setLineDash([6, 4]);
    context.lineWidth = 4;
    context.stroke();
    context.setLineDash([]);
    context.lineWidth = 2;
  } else {
    context.stroke();
  }
}

function renderPreview() {
  const canvas = elements.previewCanvas;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "rgba(148, 163, 184, 0.12)";
  context.fillRect(0, 0, canvas.width, canvas.height);

  const entry = getSelectedEntry();
  if (!entry) {
    elements.previewName.textContent = "Nothing selected.";
    elements.previewImageMeta.textContent = "-";
    elements.previewLabelMeta.textContent = "-";
    context.fillStyle = "rgba(255,255,255,0.72)";
    context.font = "20px Segoe UI";
    context.fillText("Select a dataset item to preview.", 32, 48);
    return;
  }

  elements.previewName.textContent = entry.key;
  elements.previewLabelMeta.textContent = `${entry.records.length} records | ${entry.issues.length} issues`;

  if (!entry.imageInfo) {
    elements.previewImageMeta.textContent = "No image available";
    context.fillStyle = "rgba(255,255,255,0.72)";
    context.font = "20px Segoe UI";
    context.fillText("No image found for this entry.", 32, 48);
    return;
  }

  const image = state.previewImage;
  if (!image || image.dataset.entryKey !== entry.key) {
    const previewImage = new Image();
    previewImage.onload = () => {
      state.previewImage = previewImage;
      renderPreview();
    };
    previewImage.dataset.entryKey = entry.key;
    previewImage.src = entry.imageInfo.url;
    return;
  }

  const frame = fitImageToCanvas(image.naturalWidth, image.naturalHeight, canvas.width, canvas.height);
  context.drawImage(image, frame.x, frame.y, frame.width, frame.height);

  const normalStyle = {
    lineWidth: 2,
    strokeStyle: "#22d3ee",
    fillStyle: "#22d3ee",
  };

  const highlightStyle = {
    lineWidth: 4,
    strokeStyle: "#fbbf24",
    fillStyle: "#fbbf24",
  };

  context.font = "14px Segoe UI";

  entry.records.forEach((record, index) => {
    const isHighlighted = index === state.highlightedRecordIndex;

    if (isHighlighted) {
      context.lineWidth = highlightStyle.lineWidth;
      context.strokeStyle = highlightStyle.strokeStyle;
      context.fillStyle = highlightStyle.fillStyle;
    } else {
      context.lineWidth = normalStyle.lineWidth;
      context.strokeStyle = normalStyle.strokeStyle;
      context.fillStyle = normalStyle.fillStyle;
    }

    if (record.type === "segment") {
      drawSegmentRecord(context, record, frame, isHighlighted);
    } else {
      drawDetectRecord(context, record, frame, isHighlighted);
    }

    if (isHighlighted) {
      context.fillStyle = highlightStyle.fillStyle;
      context.font = "bold 16px Segoe UI";
      context.fillText(`[HIGHLIGHTED] #${index} c${record.classId}`, frame.x + 10, frame.y + 30);
      context.font = "14px Segoe UI";
    } else {
      context.fillText(`#${index} c${record.classId}`, frame.x + 10, frame.y + 22 + index * 18);
    }
  });

  if (state.highlightedLineNumber !== null && state.highlightedRecordIndex === null) {
    const issues = getIssuesFromLineNumber(entry, state.highlightedLineNumber);
    if (issues.length > 0) {
      context.fillStyle = "#fca5a5";
      context.font = "bold 14px Segoe UI";
      const issueText = `Line ${state.highlightedLineNumber}: ${issues.map((i) => i.code).join(", ")}`;
      context.fillText(issueText, frame.x + 10, frame.y + frame.height - 20);
    }
  }

  elements.previewImageMeta.textContent = `${entry.imageInfo.width} x ${entry.imageInfo.height}`;
}

function selectEntry(entryKey) {
  state.selectedEntryKey = entryKey;
  state.previewImage = null;
  state.selectedIssue = null;
  state.highlightedRecordIndex = null;
  state.highlightedLineNumber = null;
  updateMetrics();
  renderDatasetList();
  renderIssueList();
  renderPreview();
  renderLabelTextList();
  if (elements.selectedFileOnly && elements.selectedFileOnly.checked) {
    updateFilterStatus();
  }
}

function buildReportPayload() {
  return {
    generatedAt: new Date().toISOString(),
    taskType: state.taskType,
    classNames: parseClassNames(),
    summary: {
      imageCount: state.imageFiles.length,
      labelCount: state.labelFiles.length,
      entryCount: state.datasetEntries.length,
      issueCount: state.issues.length,
    },
    entries: state.datasetEntries.map((entry) => ({
      key: entry.key,
      imageName: entry.imageFile?.name || null,
      labelName: entry.labelFile?.name || null,
      parsedRecordCount: entry.records.length,
      issues: entry.issues,
    })),
    issues: state.issues,
  };
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

async function analyzeDataset() {
  if (!state.imageFiles.length && !state.labelFiles.length) {
    setStatus("Select at least one image or label file before analysis.", "error");
    return;
  }

  setStatus("Running YOLO dataset analysis...");
  const result = await buildDatasetEntries();
  state.datasetEntries = result.entries;
  state.issues = result.issues;

  if (!state.selectedEntryKey && state.datasetEntries.length) {
    state.selectedEntryKey = state.datasetEntries[0].key;
  }

  updateMetrics();
  renderDatasetList();
  renderIssueList();
  renderPreview();
  renderLabelTextList();

  if (state.issues.length) {
    setStatus(`Analysis complete. ${state.issues.length} issues found.`, "warn");
  } else {
    setStatus(`Analysis complete. ${state.datasetEntries.length} dataset entries look clean.`);
  }
}

function syncTaskTypeUI() {
  state.taskType = elements.taskType.value || "detect";
  elements.heroTaskType.textContent = state.taskType === "segment" ? "Segment" : "Detect";
}

elements.imageInput.addEventListener("change", (event) => {
  state.imageFiles = [...(event.target.files || [])];
  updateMetrics();
  setStatus(`${state.imageFiles.length} image files selected.`);
});

elements.labelInput.addEventListener("change", (event) => {
  state.labelFiles = [...(event.target.files || [])];
  updateMetrics();
  setStatus(`${state.labelFiles.length} label files selected.`);
});

elements.taskType.addEventListener("change", () => {
  syncTaskTypeUI();
  setStatus(`Switched parser mode to ${state.taskType}.`);
});

elements.analyzeButton.addEventListener("click", () => {
  analyzeDataset();
});

elements.exportReportButton.addEventListener("click", () => {
  const payload = buildReportPayload();
  downloadJson(`yolo-qa-report-${state.taskType}.json`, payload);
  setStatus("Exported the current QA report.");
});

elements.fileList.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-entry-key]");
  if (!trigger) {
    return;
  }
  selectEntry(trigger.dataset.entryKey);
});

elements.issueList.addEventListener("click", (event) => {
  const issueItem = event.target.closest("[data-issue-index]");
  if (!issueItem) {
    return;
  }

  const issueIndex = parseInt(issueItem.dataset.issueIndex, 10);
  if (!isNaN(issueIndex)) {
    selectIssue(issueIndex);
  }
});

document.addEventListener("click", (event) => {
  const labelLine = event.target.closest(".label-line[data-line-number]");
  if (!labelLine) {
    return;
  }

  const lineNumber = parseInt(labelLine.dataset.lineNumber, 10);
  if (!isNaN(lineNumber)) {
    selectLabelLine(lineNumber);
  }
});

if (elements.previewTabs) {
  elements.previewTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const tabId = tab.dataset.tab;
      if (tabId) {
        switchPreviewTab(tabId);
      }
    });
  });
}

// Filter event listeners
if (elements.severityFilter) {
  elements.severityFilter.addEventListener("change", () => {
    updateMetrics();
    renderIssueList();
    updateFilterStatus();
  });
}

if (elements.codeFilter) {
  elements.codeFilter.addEventListener("input", () => {
    updateMetrics();
    renderIssueList();
    updateFilterStatus();
  });
}

if (elements.selectedFileOnly) {
  elements.selectedFileOnly.addEventListener("change", () => {
    updateMetrics();
    renderIssueList();
    updateFilterStatus();
  });
}

syncTaskTypeUI();
updateMetrics();
renderDatasetList();
renderIssueList();
renderPreview();
renderLabelTextList();
