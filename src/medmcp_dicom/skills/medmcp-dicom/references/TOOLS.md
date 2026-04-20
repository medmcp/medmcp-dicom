# Tool reference

Load this file when you need parameter details for a specific tool.
The MCP server exposes these tools; their names and schemas are also
discoverable at runtime via the MCP `tools/list` call.

---

## explore_data

Scan a directory tree and return a structured inventory of DICOM data.
Reads only DICOM headers (no pixel data) for speed. Non-DICOM and unreadable
files are counted in `summary.skipped_files` but not reported individually.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `root_dir` | `Path` | — | Root directory to scan recursively |
| `include_phi` | `bool` | `False` | Include `PatientName` and real `PatientID` in output. Only set to `True` when the user explicitly requests it. |
| `summary_only` | `bool` | `True` | Return only the `summary` block; `patients` will be an empty list. Use for large datasets to keep the response size manageable. |

**Returns**

```json
{
  "summary": {
    "patients": 3,
    "studies": 5,
    "series": 22,
    "instances": 4108,
    "skipped_files": 12,
    "study_date_range": {"min": "2022-01-03", "max": "2024-12-18"},
    "modalities": {"CT": 12, "MR": 8, "PT": 2},
    "body_parts": {"CHEST": 10, "ABDOMEN": 8, "": 4}
  },
  "patients": [
    {
      "patient_id": "PATIENT_001",
      "studies": [
        {
          "study_uid": "1.2.840...",
          "study_date": "2024-01-15",
          "study_description": "Abdomen CT",
          "series": [
            {
              "series_uid": "1.2.840...",
              "modality": "CT",
              "body_part": "ABDOMEN",
              "series_number": "3",
              "series_description": "Portal venous phase",
              "instances": 312,
              "shape": [512, 512],
              "pixel_spacing_mm": [0.6, 0.6],
              "slice_thickness_mm": 1.0
            }
          ]
        }
      ]
    }
  ]
}
```

With `include_phi=True`, each patient entry also contains `"patient_name": "John Doe"` (formatted as "Given Family") and `patient_id` is the real DICOM `PatientID` tag value.

`study_date` is returned in **YYYY-MM-DD** format (e.g. `"2024-01-15"`), or an
empty string if the tag was absent.

`body_part`, `shape`, `pixel_spacing_mm`, and `slice_thickness_mm` may be
`null` if the corresponding DICOM tags are absent. `body_part` reflects the
`BodyPartExamined` DICOM tag (e.g. `"BRAIN"`, `"CHEST"`, `"ABDOMEN"`) and is
often `null` in real-world PACS exports.

In series entries, absent `body_part` is `null`. In `summary.body_parts`, the
same case is represented by the `""` key — JSON object keys cannot be `null`.

When `summary_only=True`, `include_phi` has no effect — no patient entries are
returned regardless.

Series within each study are ordered by `SeriesNumber` (ascending, numeric).
`series_uid` is always present and can be used to target a specific series in
downstream processing tools.
