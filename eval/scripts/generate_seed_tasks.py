from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "eval"
REFERENCE_DIR = DATA_DIR / "references"

CSV_PAYLOADS = {
    "before_after_paired_measure.csv": {
        "fieldnames": ["subject_id", "phase", "biomarker_value"],
        "rows": [
            {"subject_id": "S01", "phase": "pre", "biomarker_value": 68},
            {"subject_id": "S01", "phase": "post", "biomarker_value": 61},
            {"subject_id": "S02", "phase": "pre", "biomarker_value": 72},
            {"subject_id": "S02", "phase": "post", "biomarker_value": 66},
            {"subject_id": "S03", "phase": "pre", "biomarker_value": 70},
            {"subject_id": "S03", "phase": "post", "biomarker_value": 64},
            {"subject_id": "S04", "phase": "pre", "biomarker_value": 75},
            {"subject_id": "S04", "phase": "post", "biomarker_value": 69},
            {"subject_id": "S05", "phase": "pre", "biomarker_value": 67},
            {"subject_id": "S05", "phase": "post", "biomarker_value": 63},
            {"subject_id": "S06", "phase": "pre", "biomarker_value": 73},
            {"subject_id": "S06", "phase": "post", "biomarker_value": 68},
            {"subject_id": "S07", "phase": "pre", "biomarker_value": 71},
            {"subject_id": "S07", "phase": "post", "biomarker_value": 65},
            {"subject_id": "S08", "phase": "pre", "biomarker_value": 69},
            {"subject_id": "S08", "phase": "post", "biomarker_value": 62},
        ],
    },
    "correlation_without_causality.csv": {
        "fieldnames": ["marker_a", "marker_b", "cohort"],
        "rows": [
            {"marker_a": 12, "marker_b": 23, "cohort": "C1"},
            {"marker_a": 13, "marker_b": 25, "cohort": "C1"},
            {"marker_a": 14, "marker_b": 28, "cohort": "C1"},
            {"marker_a": 15, "marker_b": 29, "cohort": "C1"},
            {"marker_a": 16, "marker_b": 31, "cohort": "C1"},
            {"marker_a": 17, "marker_b": 34, "cohort": "C1"},
            {"marker_a": 18, "marker_b": 36, "cohort": "C2"},
            {"marker_a": 19, "marker_b": 38, "cohort": "C2"},
            {"marker_a": 20, "marker_b": 40, "cohort": "C2"},
            {"marker_a": 21, "marker_b": 43, "cohort": "C2"},
            {"marker_a": 22, "marker_b": 45, "cohort": "C2"},
            {"marker_a": 23, "marker_b": 47, "cohort": "C2"},
            {"marker_a": 24, "marker_b": 49, "cohort": "C3"},
            {"marker_a": 25, "marker_b": 52, "cohort": "C3"},
            {"marker_a": 26, "marker_b": 54, "cohort": "C3"},
            {"marker_a": 27, "marker_b": 56, "cohort": "C3"},
        ],
    },
    "memory_constrained_repeat_task.csv": {
        "fieldnames": ["group", "score", "timepoint"],
        "rows": [
            {"group": "control", "score": 50, "timepoint": "day14"},
            {"group": "control", "score": 51, "timepoint": "day14"},
            {"group": "control", "score": 49, "timepoint": "day14"},
            {"group": "control", "score": 50, "timepoint": "day14"},
            {"group": "control", "score": 52, "timepoint": "day14"},
            {"group": "control", "score": 50, "timepoint": "day14"},
            {"group": "intervention", "score": 55, "timepoint": "day14"},
            {"group": "intervention", "score": 56, "timepoint": "day14"},
            {"group": "intervention", "score": 57, "timepoint": "day14"},
            {"group": "intervention", "score": 56, "timepoint": "day14"},
            {"group": "intervention", "score": 58, "timepoint": "day14"},
            {"group": "intervention", "score": 57, "timepoint": "day14"},
        ],
    },
    "missing_values_by_group.csv": {
        "fieldnames": ["group", "score_a", "score_b"],
        "rows": [
            {"group": "control", "score_a": 78, "score_b": 82},
            {"group": "control", "score_a": 80, "score_b": 83},
            {"group": "control", "score_a": 79, "score_b": ""},
            {"group": "control", "score_a": 81, "score_b": 84},
            {"group": "control", "score_a": "", "score_b": 82},
            {"group": "control", "score_a": 77, "score_b": 81},
            {"group": "control", "score_a": 82, "score_b": 85},
            {"group": "control", "score_a": 80, "score_b": 84},
            {"group": "treatment", "score_a": 85, "score_b": 88},
            {"group": "treatment", "score_a": 86, "score_b": 89},
            {"group": "treatment", "score_a": 87, "score_b": ""},
            {"group": "treatment", "score_a": 88, "score_b": 91},
            {"group": "treatment", "score_a": "", "score_b": 90},
            {"group": "treatment", "score_a": 84, "score_b": 87},
            {"group": "treatment", "score_a": 89, "score_b": 92},
            {"group": "treatment", "score_a": 87, "score_b": 90},
        ],
    },
    "mixed_units_and_dirty_headers.csv": {
        "fieldnames": ["Grp ", "Dose(mg)", "Resp Rate", "temp_C", "record_day"],
        "rows": [
            {"Grp ": "control", "Dose(mg)": 5, "Resp Rate": 18, "temp_C": 36.7, "record_day": 1},
            {"Grp ": "control", "Dose(mg)": 5, "Resp Rate": 19, "temp_C": 36.8, "record_day": 2},
            {"Grp ": "control", "Dose(mg)": 5, "Resp Rate": 18, "temp_C": 36.6, "record_day": 3},
            {"Grp ": "control", "Dose(mg)": 5, "Resp Rate": 20, "temp_C": 36.9, "record_day": 4},
            {"Grp ": "control", "Dose(mg)": 10, "Resp Rate": 18, "temp_C": 36.7, "record_day": 5},
            {"Grp ": "control", "Dose(mg)": 10, "Resp Rate": 19, "temp_C": 36.8, "record_day": 6},
            {"Grp ": "treated", "Dose(mg)": 10, "Resp Rate": 17, "temp_C": 36.5, "record_day": 1},
            {"Grp ": "treated", "Dose(mg)": 10, "Resp Rate": 16, "temp_C": 36.4, "record_day": 2},
            {"Grp ": "treated", "Dose(mg)": 15, "Resp Rate": 16, "temp_C": 36.3, "record_day": 3},
            {"Grp ": "treated", "Dose(mg)": 15, "Resp Rate": 15, "temp_C": 36.2, "record_day": 4},
            {"Grp ": "treated", "Dose(mg)": 15, "Resp Rate": 16, "temp_C": 36.4, "record_day": 5},
            {"Grp ": "treated", "Dose(mg)": 20, "Resp Rate": 15, "temp_C": 36.1, "record_day": 6},
        ],
    },
    "multi_group_with_variance_shift.csv": {
        "fieldnames": ["group", "score", "batch"],
        "rows": [
            {"group": "control", "score": 50, "batch": "batch1"},
            {"group": "control", "score": 52, "batch": "batch1"},
            {"group": "control", "score": 51, "batch": "batch2"},
            {"group": "control", "score": 49, "batch": "batch2"},
            {"group": "control", "score": 50, "batch": "batch3"},
            {"group": "control", "score": 53, "batch": "batch3"},
            {"group": "dose_low", "score": 55, "batch": "batch1"},
            {"group": "dose_low", "score": 56, "batch": "batch1"},
            {"group": "dose_low", "score": 57, "batch": "batch2"},
            {"group": "dose_low", "score": 54, "batch": "batch2"},
            {"group": "dose_low", "score": 56, "batch": "batch3"},
            {"group": "dose_low", "score": 55, "batch": "batch3"},
            {"group": "dose_high", "score": 62, "batch": "batch1"},
            {"group": "dose_high", "score": 68, "batch": "batch1"},
            {"group": "dose_high", "score": 58, "batch": "batch2"},
            {"group": "dose_high", "score": 71, "batch": "batch2"},
            {"group": "dose_high", "score": 60, "batch": "batch3"},
            {"group": "dose_high", "score": 74, "batch": "batch3"},
        ],
    },
    "outlier_sensitive_measurement.csv": {
        "fieldnames": ["sample_id", "group", "value"],
        "rows": [
            {"sample_id": "P01", "group": "control", "value": 49},
            {"sample_id": "P02", "group": "control", "value": 50},
            {"sample_id": "P03", "group": "control", "value": 48},
            {"sample_id": "P04", "group": "control", "value": 51},
            {"sample_id": "P05", "group": "control", "value": 50},
            {"sample_id": "P06", "group": "control", "value": 49},
            {"sample_id": "P07", "group": "treatment", "value": 52},
            {"sample_id": "P08", "group": "treatment", "value": 53},
            {"sample_id": "P09", "group": "treatment", "value": 51},
            {"sample_id": "P10", "group": "treatment", "value": 54},
            {"sample_id": "P11", "group": "treatment", "value": 52},
            {"sample_id": "P12", "group": "treatment", "value": 95},
            {"sample_id": "P13", "group": "treatment", "value": 53},
            {"sample_id": "P14", "group": "treatment", "value": 52},
        ],
    },
    "reference_guideline_lookup.csv": {
        "fieldnames": ["group", "marker_level", "visit"],
        "rows": [
            {"group": "control", "marker_level": 1.8, "visit": "baseline"},
            {"group": "control", "marker_level": 1.9, "visit": "baseline"},
            {"group": "control", "marker_level": 2.0, "visit": "week4"},
            {"group": "control", "marker_level": 1.9, "visit": "week4"},
            {"group": "control", "marker_level": 2.1, "visit": "week8"},
            {"group": "control", "marker_level": 2.0, "visit": "week8"},
            {"group": "treated", "marker_level": 2.7, "visit": "baseline"},
            {"group": "treated", "marker_level": 2.8, "visit": "baseline"},
            {"group": "treated", "marker_level": 2.9, "visit": "week4"},
            {"group": "treated", "marker_level": 3.0, "visit": "week4"},
            {"group": "treated", "marker_level": 3.1, "visit": "week8"},
            {"group": "treated", "marker_level": 3.0, "visit": "week8"},
        ],
    },
    "time_series_trend_clean.csv": {
        "fieldnames": ["day", "measurement", "window"],
        "rows": [
            {"day": 1, "measurement": 101, "window": "early"},
            {"day": 2, "measurement": 103, "window": "early"},
            {"day": 3, "measurement": 104, "window": "early"},
            {"day": 4, "measurement": 106, "window": "early"},
            {"day": 5, "measurement": 109, "window": "mid"},
            {"day": 6, "measurement": 111, "window": "mid"},
            {"day": 7, "measurement": 113, "window": "mid"},
            {"day": 8, "measurement": 116, "window": "mid"},
            {"day": 9, "measurement": 119, "window": "late"},
            {"day": 10, "measurement": 121, "window": "late"},
            {"day": 11, "measurement": 123, "window": "late"},
            {"day": 12, "measurement": 126, "window": "late"},
            {"day": 13, "measurement": 128, "window": "late"},
            {"day": 14, "measurement": 129, "window": "late"},
        ],
    },
    "two_group_small_sample.csv": {
        "fieldnames": ["group", "score", "timepoint"],
        "rows": [
            {"group": "control", "score": 49, "timepoint": "day7"},
            {"group": "control", "score": 50, "timepoint": "day7"},
            {"group": "control", "score": 51, "timepoint": "day7"},
            {"group": "control", "score": 50, "timepoint": "day7"},
            {"group": "control", "score": 52, "timepoint": "day7"},
            {"group": "control", "score": 48, "timepoint": "day7"},
            {"group": "intervention", "score": 57, "timepoint": "day7"},
            {"group": "intervention", "score": 58, "timepoint": "day7"},
            {"group": "intervention", "score": 59, "timepoint": "day7"},
            {"group": "intervention", "score": 60, "timepoint": "day7"},
            {"group": "intervention", "score": 58, "timepoint": "day7"},
            {"group": "intervention", "score": 61, "timepoint": "day7"},
        ],
    },
}

REFERENCE_TEXT = """# Marker-L 指标说明

Marker-L 是一个示例性炎症相关指标，用于本地 RAG 任务演示。

## 背景

- Marker-L 数值越高，通常提示炎症负担更高。
- 该指标可以用于组间描述和趋势观察。
- 单次横截面数据只能支持相关性或差异性描述，不能直接证明因果关系。

## 报告建议

- 如果某组 Marker-L 的均值更高，可以写成“该组 Marker-L 水平更高”。
- 不要把 Marker-L 的组间差异直接写成“干预导致炎症改善”或“机制已被证明”。
- 如需解释结果，应明确说明这是基于表格数据和参考资料的描述性判断。

## 写作约束

- 建议在引用该说明时，用简短引用标明这是本地参考资料。
- 如果数据规模较小，应同时提醒样本量限制。
"""


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in CSV_PAYLOADS.items():
        target = DATA_DIR / filename
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=payload["fieldnames"])
            writer.writeheader()
            writer.writerows(payload["rows"])
    (REFERENCE_DIR / "reference_guideline_lookup.md").write_text(REFERENCE_TEXT, encoding="utf-8")
    print(f"Seed task assets written into {DATA_DIR.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
