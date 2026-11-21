"""Build a spreadsheet-safe CSV for a patient's consultations."""
import csv
import io


def spreadsheet_cell(value):
    """Treat formula-like text as text in common spreadsheet applications."""
    if value is None:
        return ''
    value = str(value)
    if value and (value[0] in '\t\r\n' or value.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def consultation_csv(items):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['id', 'symptoms', 'status', 'priority', 'clinician_notes', 'prescription', 'created_at', 'updated_at'])
    for item in items:
        writer.writerow([spreadsheet_cell(value) for value in (
            item.id, item.symptoms, item.status, item.priority, item.doctor_notes,
            item.prescription, item.created_at.isoformat(), item.updated_at.isoformat()
        )])
    return stream.getvalue().encode('utf-8-sig')
