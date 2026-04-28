from io import BytesIO

from werkzeug.datastructures import FileStorage

from repair_workbench.scanner import scan_dataset


def make_label_file(name: str, content: str):
    return FileStorage(stream=BytesIO(content.encode("utf-8")), filename=name, name="labels")


def make_image_file(name: str):
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00"
        b"\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return FileStorage(stream=BytesIO(png_bytes), filename=name, name="images")


def test_scan_detect_flags_missing_pairs():
    result = scan_dataset(
        task_type="detect",
        image_files=[make_image_file("a.jpg")],
        label_files=[],
        classes_text="cat\ndog",
    )

    assert result["summary"]["issue_count"] == 1
    assert result["issues"][0]["code"] == "missing_label"


def test_scan_detect_flags_out_of_range_class():
    result = scan_dataset(
        task_type="detect",
        image_files=[make_image_file("a.jpg")],
        label_files=[make_label_file("a.txt", "3 0.5 0.5 0.2 0.2")],
        classes_text="cat\ndog",
    )

    assert any(issue["code"] == "class_range" for issue in result["issues"])


def test_scan_segment_flags_invalid_polygon():
    result = scan_dataset(
        task_type="segment",
        image_files=[make_image_file("a.jpg")],
        label_files=[make_label_file("a.txt", "0 0.1 0.1 0.2 0.2")],
        classes_text="cat",
    )

    assert any(issue["code"] == "segment_format" for issue in result["issues"])
