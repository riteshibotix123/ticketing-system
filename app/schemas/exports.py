from enum import StrEnum


class ExportType(StrEnum):
    TICKETS = "tickets"
    KPIS = "kpis"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"
