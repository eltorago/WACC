"""Keep exported text literal when a CSV is opened in a spreadsheet."""


def safe_cell(value):
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def write_row(writer, values):
    return writer.writerow([safe_cell(value) for value in values])
