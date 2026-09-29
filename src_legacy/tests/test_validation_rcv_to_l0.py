from unittest.mock import Mock, patch

import pytest

from scripts.commons.validations import (
    ValidationError,
    validate_file,
    validate_schema,
    validate_rcv_to_l0,
)

VALIDATION_MODULE = "scripts.commons.validations"

# validate_file


def test_validate_file_not_found():
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "config": {"l0_format": "csv"},
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:
        mock_s3.check_file_exists.return_value = False

        with pytest.raises(ValidationError, match="File not found"):
            validate_file(context)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [b""],
        [b"   "],
        [b"\n"],
    ],
)
def test_validate_file_empty(lines):
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "config": {"l0_format": "csv"},
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:
        mock_s3.check_file_exists.return_value = True
        mock_s3.get_object.return_value = {"Body": Mock(iter_lines=lambda: iter(lines))}

        with pytest.raises(ValidationError, match="File empty"):
            validate_file(context)

        mock_s3.copy_file.assert_called_once()


def test_validate_file_header_only():
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "config": {"l0_format": "csv"},
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:
        mock_s3.check_file_exists.return_value = True
        mock_s3.get_object.return_value = {
            "Body": Mock(
                iter_lines=lambda: iter(
                    [
                        b"id,name",
                    ]
                )
            )
        }

        with pytest.raises(
            ValidationError,
            match="File contains only header without data",
        ):
            validate_file(context)

        mock_s3.copy_file.assert_called_once()


def test_validate_file_not_readable():
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "config": {"l0_format": "csv"},
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:
        mock_s3.check_file_exists.return_value = True
        mock_s3.get_object.side_effect = Exception("read error")

        with pytest.raises(
            ValidationError,
            match="File is not readable",
        ):
            validate_file(context)

        mock_s3.copy_file.assert_called_once()


def test_validate_file_success():
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "config": {"l0_format": "csv"},
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:

        mock_s3.check_file_exists.return_value = True

        mock_s3.get_object.return_value = {
            "Body": Mock(
                iter_lines=lambda: iter(
                    [
                        b"id,name",
                        b"1,John",
                    ]
                )
            )
        }

        validate_file(context)

        assert context["header_line"] == "id,name"

        mock_s3.check_file_exists.assert_called_once_with(
            "test-bucket",
            "input/file.csv",
        )

        mock_s3.get_object.assert_called_once_with(
            "test-bucket",
            "input/file.csv",
        )

        mock_s3.copy_file.assert_not_called()


def test_validate_schema_success():
    context = {
        "header_line": "id,name",
        "config": {
            "columns": [
                {"name": "id"},
                {"name": "name"},
            ]
        },
    }

    # không raise exception
    validate_schema(context)


@pytest.mark.parametrize(
    "header_line",
    [
        "id,name,age",  # new column
        "id",  # missing column
        "name,id",  # wrong order
    ],
)
def test_validate_schema_mismatch(header_line):
    context = {
        "bucket": "test-bucket",
        "key_source": "input/file.csv",
        "key_quarantine": "quarantine/file.csv",
        "header_line": header_line,
        "config": {
            "columns": [
                {"name": "id"},
                {"name": "name"},
            ]
        },
    }

    with patch(f"{VALIDATION_MODULE}.s3_helper") as mock_s3:
        with pytest.raises(
            ValidationError,
            match="Schema mismatch",
        ):
            validate_schema(context)

        mock_s3.copy_file.assert_called_once_with(
            "test-bucket",
            "input/file.csv",
            "test-bucket",
            "quarantine/file.csv",
        )


def test_validate_rcv_to_l0_calls_enabled_validations():

    context = {
        "config": {"validation": {"validate_file": True, "validate_schema": True}}
    }

    with patch(
        f"{VALIDATION_MODULE}.VALIDATE_FUNCTIONS",
        {"validate_file": Mock(), "validate_schema": Mock()},
    ) as functions:

        validate_rcv_to_l0(context)

        functions["validate_file"].assert_called_once_with(context)
        functions["validate_schema"].assert_called_once_with(context)
