"""Tests for export-pdf.py — PDF export via LibreOffice."""

import os
import shutil

import pytest

from conftest import make_deck


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice not installed")
def test_libreoffice_export(export_pdf, tmp_path):
    """LibreOffice converts a PPTX to PDF successfully."""
    prs = make_deck(3)
    pptx_path = str(tmp_path / "deck.pptx")
    prs.save(pptx_path)

    pdf_path = str(tmp_path / "deck.pdf")
    result = export_pdf.try_libreoffice(pptx_path, pdf_path)
    assert result is True
    assert os.path.isfile(pdf_path)
    assert os.path.getsize(pdf_path) > 100


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice not installed")
def test_libreoffice_custom_output_path(export_pdf, tmp_path):
    """PDF output goes to the specified path, not alongside the PPTX."""
    prs = make_deck(2)
    pptx_path = str(tmp_path / "source" / "deck.pptx")
    os.makedirs(os.path.dirname(pptx_path), exist_ok=True)
    prs.save(pptx_path)

    pdf_path = str(tmp_path / "dest" / "output.pdf")
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    result = export_pdf.try_libreoffice(pptx_path, pdf_path)
    assert result is True
    assert os.path.isfile(pdf_path)


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice not installed")
def test_libreoffice_missing_file(export_pdf, tmp_path):
    """Non-existent PPTX produces no PDF output."""
    pdf_path = str(tmp_path / "out.pdf")
    export_pdf.try_libreoffice(
        str(tmp_path / "missing.pptx"),
        pdf_path,
    )
    # Whether it returns True or False depends on LibreOffice version,
    # but a missing input should never produce a valid PDF
    assert not os.path.isfile(pdf_path)
