from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from repair_workbench.qa_engine import (
    compute_iou,
    is_anomalous_box,
    parse_ground_truth_labels,
    compare_labels,
)


def make_image_file(name: str):
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00"
        b"\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return FileStorage(stream=BytesIO(png_bytes), filename=name, name="images")


def make_label_file(name: str, content: str):
    return FileStorage(stream=BytesIO(content.encode("utf-8")), filename=name, name="labels")


class TestComputeIoU:
    def test_perfect_overlap(self):
        box1 = [0, 0, 100, 100]
        box2 = [0, 0, 100, 100]
        assert compute_iou(box1, box2) == pytest.approx(1.0)

    def test_no_overlap(self):
        box1 = [0, 0, 50, 50]
        box2 = [60, 60, 100, 100]
        assert compute_iou(box1, box2) == 0.0

    def test_partial_overlap(self):
        box1 = [0, 0, 100, 100]
        box2 = [50, 50, 150, 150]
        expected = 2500 / 17500
        assert compute_iou(box1, box2) == pytest.approx(expected)


class TestIsAnomalousBox:
    def test_normal_box(self):
        box = [0.5, 0.5, 0.2, 0.2]
        assert not is_anomalous_box(box, 640, 480)

    def test_too_small_box(self):
        box = [0.5, 0.5, 0.00005, 0.00005]
        assert is_anomalous_box(box, 640, 480)

    def test_too_large_box(self):
        box = [0.5, 0.5, 0.95, 0.95]
        assert is_anomalous_box(box, 640, 480)

    def test_extreme_aspect_ratio(self):
        box = [0.5, 0.5, 0.5, 0.02]
        assert is_anomalous_box(box, 640, 480)


class TestParseGroundTruthLabels:
    def test_valid_labels(self):
        content = "0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1"
        labels = parse_ground_truth_labels(content, class_count=3)
        assert len(labels) == 2
        assert labels[0]["class_id"] == 0
        assert labels[1]["class_id"] == 1

    def test_invalid_format(self):
        content = "0 0.5 0.5 0.2\n1 0.3 0.3 0.1 0.1 0.5"
        labels = parse_ground_truth_labels(content, class_count=3)
        assert len(labels) == 0

    def test_out_of_range_class(self):
        content = "0 0.5 0.5 0.2 0.2\n5 0.3 0.3 0.1 0.1"
        labels = parse_ground_truth_labels(content, class_count=3)
        assert len(labels) == 1

    def test_negative_values(self):
        content = "0 -0.1 0.5 0.2 0.2\n0 1.5 0.3 0.1 0.1"
        labels = parse_ground_truth_labels(content, class_count=3)
        assert len(labels) == 0


class TestCompareLabels:
    def test_no_ground_truth_no_detections(self):
        result = compare_labels(
            ground_truth=[],
            detections=[],
            img_width=640,
            img_height=480,
            class_names=["person", "car"],
        )
        assert result["ground_truth_count"] == 0
        assert result["detection_count"] == 0
        assert result["matched_count"] == 0
        assert len(result["issues"]) == 0

    def test_missing_label(self):
        ground_truth = []
        detections = [
            {
                "class_id": 0,
                "x_center": 0.5,
                "y_center": 0.5,
                "width": 0.2,
                "height": 0.2,
                "confidence": 0.8,
            }
        ]
        result = compare_labels(
            ground_truth=ground_truth,
            detections=detections,
            img_width=640,
            img_height=480,
            class_names=["person", "car"],
        )
        missing_issues = [i for i in result["issues"] if i["type"] == "missing_label"]
        assert len(missing_issues) == 1

    def test_class_conflict(self):
        ground_truth = [
            {
                "class_id": 0,
                "x_center": 0.5,
                "y_center": 0.5,
                "width": 0.2,
                "height": 0.2,
                "raw": "0 0.5 0.5 0.2 0.2",
            }
        ]
        detections = [
            {
                "class_id": 1,
                "x_center": 0.5,
                "y_center": 0.5,
                "width": 0.2,
                "height": 0.2,
                "confidence": 0.8,
            }
        ]
        result = compare_labels(
            ground_truth=ground_truth,
            detections=detections,
            img_width=640,
            img_height=480,
            class_names=["person", "car"],
        )
        conflict_issues = [i for i in result["issues"] if i["type"] == "class_conflict"]
        assert len(conflict_issues) == 1
        assert result["matched_count"] == 1


class TestDecisionUpdate:
    def test_decision_should_update_not_append(self):
        decisions = [
            {"issue_index": 0, "decision": "accept", "issue": {}},
            {"issue_index": 1, "decision": "reject", "issue": {}},
        ]

        issue_index = 0
        new_decision = "keep"

        existing_idx = None
        for i, d in enumerate(decisions):
            if d["issue_index"] == issue_index:
                existing_idx = i
                break

        new_decision_obj = {
            "issue_index": issue_index,
            "decision": new_decision,
            "issue": {},
        }

        if existing_idx is not None:
            decisions[existing_idx] = new_decision_obj
        else:
            decisions.append(new_decision_obj)

        assert len(decisions) == 2
        assert decisions[0]["decision"] == "keep"
        assert decisions[1]["decision"] == "reject"

    def test_decision_should_append_if_new(self):
        decisions = [
            {"issue_index": 0, "decision": "accept", "issue": {}},
        ]

        issue_index = 1
        new_decision = "reject"

        existing_idx = None
        for i, d in enumerate(decisions):
            if d["issue_index"] == issue_index:
                existing_idx = i
                break

        new_decision_obj = {
            "issue_index": issue_index,
            "decision": new_decision,
            "issue": {},
        }

        if existing_idx is not None:
            decisions[existing_idx] = new_decision_obj
        else:
            decisions.append(new_decision_obj)

        assert len(decisions) == 2
        assert decisions[0]["decision"] == "accept"
        assert decisions[1]["decision"] == "reject"


class TestBuildFinalLabelsLogic:
    def test_class_conflict_accept_should_use_detection(self):
        session_data = {
            "results": [
                {
                    "image_key": "test",
                    "ground_truth": [
                        {
                            "class_id": 0,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                        }
                    ],
                    "detections": [
                        {
                            "class_id": 1,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                            "confidence": 0.8,
                        }
                    ],
                    "comparison": {
                        "issues": [
                            {
                                "type": "class_conflict",
                                "ground_truth": {
                                    "box_index": 0,
                                    "class_id": 0,
                                    "class_name": "person",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                                "detection": {
                                    "class_id": 1,
                                    "class_name": "car",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                            }
                        ]
                    },
                    "decisions": [
                        {
                            "issue_index": 0,
                            "decision": "accept",
                            "issue": {
                                "type": "class_conflict",
                                "ground_truth": {"box_index": 0},
                            },
                        }
                    ],
                }
            ]
        }

        result = session_data["results"][0]
        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        final_boxes = []

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                continue

            if gt_idx in gt_box_issue_map:
                issue_idx = gt_box_issue_map[gt_idx]
                if issue_idx in decisions and decisions[issue_idx] == "reject":
                    continue

            final_boxes.append({
                "class_id": gt_box["class_id"],
                "x_center": gt_box["x_center"],
                "y_center": gt_box["y_center"],
                "width": gt_box["width"],
                "height": gt_box["height"],
            })

        for gt_idx in class_conflict_map:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            conflict_info = class_conflict_map[gt_idx]
            issue_idx = conflict_info["issue_idx"]
            issue = conflict_info["issue"]

            if issue_idx in decisions:
                decision = decisions[issue_idx]
                if decision == "accept":
                    det_info = issue.get("detection", {})
                    box_info = det_info.get("box", {})
                    final_boxes.append({
                        "class_id": det_info.get("class_id", 0),
                        "x_center": box_info.get("x_center", 0),
                        "y_center": box_info.get("y_center", 0),
                        "width": box_info.get("width", 0),
                        "height": box_info.get("height", 0),
                    })
                elif decision == "reject":
                    pass
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        assert len(final_boxes) == 1
        assert final_boxes[0]["class_id"] == 1

    def test_class_conflict_keep_should_use_ground_truth(self):
        session_data = {
            "results": [
                {
                    "image_key": "test",
                    "ground_truth": [
                        {
                            "class_id": 0,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                        }
                    ],
                    "detections": [
                        {
                            "class_id": 1,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                            "confidence": 0.8,
                        }
                    ],
                    "comparison": {
                        "issues": [
                            {
                                "type": "class_conflict",
                                "ground_truth": {
                                    "box_index": 0,
                                    "class_id": 0,
                                    "class_name": "person",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                                "detection": {
                                    "class_id": 1,
                                    "class_name": "car",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                            }
                        ]
                    },
                    "decisions": [
                        {
                            "issue_index": 0,
                            "decision": "keep",
                            "issue": {
                                "type": "class_conflict",
                                "ground_truth": {"box_index": 0},
                            },
                        }
                    ],
                }
            ]
        }

        result = session_data["results"][0]
        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        final_boxes = []

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                continue

            if gt_idx in gt_box_issue_map:
                issue_idx = gt_box_issue_map[gt_idx]
                if issue_idx in decisions and decisions[issue_idx] == "reject":
                    continue

            final_boxes.append({
                "class_id": gt_box["class_id"],
                "x_center": gt_box["x_center"],
                "y_center": gt_box["y_center"],
                "width": gt_box["width"],
                "height": gt_box["height"],
            })

        for gt_idx in class_conflict_map:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            conflict_info = class_conflict_map[gt_idx]
            issue_idx = conflict_info["issue_idx"]
            issue = conflict_info["issue"]

            if issue_idx in decisions:
                decision = decisions[issue_idx]
                if decision == "accept":
                    det_info = issue.get("detection", {})
                    box_info = det_info.get("box", {})
                    final_boxes.append({
                        "class_id": det_info.get("class_id", 0),
                        "x_center": box_info.get("x_center", 0),
                        "y_center": box_info.get("y_center", 0),
                        "width": box_info.get("width", 0),
                        "height": box_info.get("height", 0),
                    })
                elif decision == "reject":
                    pass
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        assert len(final_boxes) == 1
        assert final_boxes[0]["class_id"] == 0

    def test_class_conflict_reject_should_remove_both(self):
        session_data = {
            "results": [
                {
                    "image_key": "test",
                    "ground_truth": [
                        {
                            "class_id": 0,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                        }
                    ],
                    "detections": [
                        {
                            "class_id": 1,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                            "confidence": 0.8,
                        }
                    ],
                    "comparison": {
                        "issues": [
                            {
                                "type": "class_conflict",
                                "ground_truth": {
                                    "box_index": 0,
                                    "class_id": 0,
                                    "class_name": "person",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                                "detection": {
                                    "class_id": 1,
                                    "class_name": "car",
                                    "box": {
                                        "x_center": 0.5,
                                        "y_center": 0.5,
                                        "width": 0.2,
                                        "height": 0.2,
                                    },
                                },
                            }
                        ]
                    },
                    "decisions": [
                        {
                            "issue_index": 0,
                            "decision": "reject",
                            "issue": {
                                "type": "class_conflict",
                                "ground_truth": {"box_index": 0},
                            },
                        }
                    ],
                }
            ]
        }

        result = session_data["results"][0]
        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        final_boxes = []

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                continue

            if gt_idx in gt_box_issue_map:
                issue_idx = gt_box_issue_map[gt_idx]
                if issue_idx in decisions and decisions[issue_idx] == "reject":
                    continue

            final_boxes.append({
                "class_id": gt_box["class_id"],
                "x_center": gt_box["x_center"],
                "y_center": gt_box["y_center"],
                "width": gt_box["width"],
                "height": gt_box["height"],
            })

        for gt_idx in class_conflict_map:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            conflict_info = class_conflict_map[gt_idx]
            issue_idx = conflict_info["issue_idx"]
            issue = conflict_info["issue"]

            if issue_idx in decisions:
                decision = decisions[issue_idx]
                if decision == "accept":
                    det_info = issue.get("detection", {})
                    box_info = det_info.get("box", {})
                    final_boxes.append({
                        "class_id": det_info.get("class_id", 0),
                        "x_center": box_info.get("x_center", 0),
                        "y_center": box_info.get("y_center", 0),
                        "width": box_info.get("width", 0),
                        "height": box_info.get("height", 0),
                    })
                elif decision == "reject":
                    pass
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        assert len(final_boxes) == 0

    def test_missing_label_accept_should_add(self):
        session_data = {
            "results": [
                {
                    "image_key": "test",
                    "ground_truth": [],
                    "detections": [
                        {
                            "class_id": 0,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                            "confidence": 0.8,
                        }
                    ],
                    "comparison": {
                        "issues": [
                            {
                                "type": "missing_label",
                                "source": "detection",
                                "box_index": 0,
                                "class_id": 0,
                                "class_name": "person",
                                "box": {
                                    "x_center": 0.5,
                                    "y_center": 0.5,
                                    "width": 0.2,
                                    "height": 0.2,
                                },
                            }
                        ]
                    },
                    "decisions": [
                        {
                            "issue_index": 0,
                            "decision": "accept",
                            "issue": {
                                "type": "missing_label",
                                "source": "detection",
                                "box_index": 0,
                            },
                        }
                    ],
                }
            ]
        }

        result = session_data["results"][0]
        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        final_boxes = []

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                continue

            if gt_idx in gt_box_issue_map:
                issue_idx = gt_box_issue_map[gt_idx]
                if issue_idx in decisions and decisions[issue_idx] == "reject":
                    continue

            final_boxes.append({
                "class_id": gt_box["class_id"],
                "x_center": gt_box["x_center"],
                "y_center": gt_box["y_center"],
                "width": gt_box["width"],
                "height": gt_box["height"],
            })

        for gt_idx in class_conflict_map:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            conflict_info = class_conflict_map[gt_idx]
            issue_idx = conflict_info["issue_idx"]
            issue = conflict_info["issue"]

            if issue_idx in decisions:
                decision = decisions[issue_idx]
                if decision == "accept":
                    det_info = issue.get("detection", {})
                    box_info = det_info.get("box", {})
                    final_boxes.append({
                        "class_id": det_info.get("class_id", 0),
                        "x_center": box_info.get("x_center", 0),
                        "y_center": box_info.get("y_center", 0),
                        "width": box_info.get("width", 0),
                        "height": box_info.get("height", 0),
                    })
                elif decision == "reject":
                    pass
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        assert len(final_boxes) == 1
        assert final_boxes[0]["class_id"] == 0

    def test_missing_label_reject_should_not_add(self):
        session_data = {
            "results": [
                {
                    "image_key": "test",
                    "ground_truth": [],
                    "detections": [
                        {
                            "class_id": 0,
                            "x_center": 0.5,
                            "y_center": 0.5,
                            "width": 0.2,
                            "height": 0.2,
                            "confidence": 0.8,
                        }
                    ],
                    "comparison": {
                        "issues": [
                            {
                                "type": "missing_label",
                                "source": "detection",
                                "box_index": 0,
                                "class_id": 0,
                                "class_name": "person",
                                "box": {
                                    "x_center": 0.5,
                                    "y_center": 0.5,
                                    "width": 0.2,
                                    "height": 0.2,
                                },
                            }
                        ]
                    },
                    "decisions": [
                        {
                            "issue_index": 0,
                            "decision": "reject",
                            "issue": {
                                "type": "missing_label",
                                "source": "detection",
                                "box_index": 0,
                            },
                        }
                    ],
                }
            ]
        }

        result = session_data["results"][0]
        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        final_boxes = []

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                continue

            if gt_idx in gt_box_issue_map:
                issue_idx = gt_box_issue_map[gt_idx]
                if issue_idx in decisions and decisions[issue_idx] == "reject":
                    continue

            final_boxes.append({
                "class_id": gt_box["class_id"],
                "x_center": gt_box["x_center"],
                "y_center": gt_box["y_center"],
                "width": gt_box["width"],
                "height": gt_box["height"],
            })

        for gt_idx in class_conflict_map:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            conflict_info = class_conflict_map[gt_idx]
            issue_idx = conflict_info["issue_idx"]
            issue = conflict_info["issue"]

            if issue_idx in decisions:
                decision = decisions[issue_idx]
                if decision == "accept":
                    det_info = issue.get("detection", {})
                    box_info = det_info.get("box", {})
                    final_boxes.append({
                        "class_id": det_info.get("class_id", 0),
                        "x_center": box_info.get("x_center", 0),
                        "y_center": box_info.get("y_center", 0),
                        "width": box_info.get("width", 0),
                        "height": box_info.get("height", 0),
                    })
                elif decision == "reject":
                    pass
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        assert len(final_boxes) == 0
