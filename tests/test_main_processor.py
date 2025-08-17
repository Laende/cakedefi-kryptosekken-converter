import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.main_processor import CakeTransactionProcessor


class TestCakeTransactionProcessor:
    @pytest.fixture
    def sample_csv_content(self):
        """Sample CakeDeFi CSV content for testing"""
        return """Date,Operation,Amount,Coin/Asset,FIAT value,FIAT currency,Transaction ID,Withdrawal address,Reference,Related reference ID
2022-02-02T19:36:32+01:00,Staking reward,0.5197701,ETH,1396.0833343587865,USD,,,ref123,
2022-02-03T02:34:42+01:00,Staking reward,0.00917367,DFI,0.0230499643513991,USD,,,ref456,
2022-02-03T14:35:24+01:00,Staking reward,0.0091062,DFI,0.0225381978273431,USD,,,ref789,"""

    @pytest.fixture
    def processor(self):
        """Create processor with test EXR file"""
        exr_file = Path(__file__).parent.parent / "src" / "data" / "EXR.csv"
        return CakeTransactionProcessor(exr_file=exr_file)

    def test_processor_initialization(self, processor):
        """Test that processor initializes correctly"""
        assert processor.currency_converter is not None
        assert processor.grouper is not None
        assert processor.stats["input_transactions"] == 0

    def test_process_small_file(self, processor, sample_csv_content):
        """Test processing a small CSV file"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "test_input.csv"
            input_file.write_text(sample_csv_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(input_file=input_file, output_prefix="test")

            # Check result structure
            assert "success" in result
            assert "statistics" in result
            assert "files" in result
            assert "validation_result" in result

            # Check statistics
            stats = result["statistics"]
            assert stats["input_transactions"] == 3  # 3 transactions in sample
            assert stats["grouped_transactions"] >= 1  # Should create at least 1 group
            assert (
                stats["output_transactions"] >= 1
            )  # Should output at least 1 transaction

            # Check files were created
            files = result["files"]
            for file_type, file_path in files.items():
                if file_type == "yearly_csv_files":
                    # This is a dictionary of year -> file path
                    assert isinstance(file_path, dict), (
                        f"yearly_csv_files should be a dict, got {type(file_path)}"
                    )
                    for year, yearly_file_path in file_path.items():
                        assert yearly_file_path.exists(), (
                            f"Yearly file for {year} not created: {yearly_file_path}"
                        )
                else:
                    # Regular file path
                    assert file_path.exists(), (
                        f"{file_type} file not created: {file_path}"
                    )

            # Verify final CSV has correct headers
            final_csv = files["final_csv"]
            csv_content = final_csv.read_text()
            assert (
                "Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat"
                in csv_content
            )

    def test_process_file_creates_intermediate_outputs(
        self, processor, sample_csv_content
    ):
        """Test that intermediate JSON files are created with correct content"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "test_input.csv"
            input_file.write_text(sample_csv_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(input_file=input_file, output_prefix="test")

            files = result["files"]

            # Check original transactions JSON
            original_json = files["original_json"]
            with open(original_json) as f:
                original_data = json.load(f)

            assert len(original_data) == 3
            assert all("date" in tx for tx in original_data)
            assert all("operation" in tx for tx in original_data)
            assert all("mapped_type" in tx for tx in original_data)

            # Check groups JSON
            groups_json = files["groups_json"]
            with open(groups_json) as f:
                groups_data = json.load(f)

            assert isinstance(groups_data, list)
            assert len(groups_data) >= 1
            for group in groups_data:
                assert "group_type" in group
                assert "transactions" in group
                assert "transaction_count" in group

            # Check kryptosekken JSON
            kryptosekken_json = files["kryptosekken_json"]
            with open(kryptosekken_json) as f:
                kryptosekken_data = json.load(f)

            assert isinstance(kryptosekken_data, list)
            assert len(kryptosekken_data) >= 1
            for tx in kryptosekken_data:
                assert "tidspunkt" in tx
                assert "type" in tx

    def test_process_file_handles_empty_file(self, processor):
        """Test processing an empty CSV file"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create empty CSV file (only header)
            input_file = tmp_path / "empty.csv"
            input_file.write_text(
                "Date,Operation,Amount,Coin/Asset,FIAT value,FIAT currency,Transaction ID,Withdrawal address,Reference,Related reference ID\n"
            )

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(
                input_file=input_file, output_prefix="empty"
            )

            # Should handle empty file gracefully
            assert result["statistics"]["input_transactions"] == 0
            assert result["statistics"]["output_transactions"] == 0

            # Files should still be created
            files = result["files"]
            for file_type, file_path in files.items():
                if file_type == "yearly_csv_files":
                    # Should be empty dict for no transactions
                    assert isinstance(file_path, dict), (
                        f"yearly_csv_files should be a dict, got {type(file_path)}"
                    )
                    # No yearly files should be created for empty data
                    assert len(file_path) == 0, (
                        f"Expected no yearly files for empty data, got {len(file_path)}"
                    )
                else:
                    # Regular file path - should still be created even for empty data
                    assert file_path.exists(), (
                        f"{file_type} file not created: {file_path}"
                    )

    def test_summary_report_generated(self, processor, sample_csv_content):
        """Test that summary report is generated with correct content"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "test_input.csv"
            input_file.write_text(sample_csv_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(input_file=input_file, output_prefix="test")

            # Check summary report
            summary_file = result["files"]["summary_report"]
            summary_content = summary_file.read_text(encoding="utf-8")

            assert "CAKEDEFI TO KRYPTOSEKKEN PROCESSING REPORT" in summary_content
            assert "PROCESSING STATISTICS:" in summary_content
            assert "Input transactions" in summary_content
            assert "Output transactions" in summary_content
            assert "KRYPTOSEKKEN TRANSACTION SUMMARY" in summary_content
            assert "EXCHANGE RATE DATA" in summary_content
            assert "FILES GENERATED" in summary_content

    def test_csv_validation_integration(self, processor, sample_csv_content):
        """Test that CSV validation is integrated and works correctly"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "test_input.csv"
            input_file.write_text(sample_csv_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(input_file=input_file, output_prefix="test")

            # Check that CSV validation results are included
            assert "csv_validation_results" in result
            validation_results = result["csv_validation_results"]

            # Should have validation results for generated yearly files
            assert isinstance(validation_results, dict)

            # Each year should have validation result structure
            for year, validation_result in validation_results.items():
                assert isinstance(year, int)  # Year should be integer
                assert isinstance(validation_result, dict)
                assert "valid" in validation_result
                assert "transaction_count" in validation_result
                assert "errors" in validation_result
                assert "warnings" in validation_result

    def test_income_transactions_no_negative_balance(self, processor):
        """Test that income transactions don't create negative currency balances"""
        # Create CSV content with only income transactions (simplified test)
        income_only_content = """Date,Operation,Amount,Coin/Asset,FIAT value,FIAT currency,Transaction ID,Withdrawal address,Reference,Related reference ID
2022-02-02T19:36:32+01:00,Staking reward,0.5197701,ETH,1396.0833343587865,USD,,,ref123,
2022-02-03T02:34:42+01:00,Staking reward,0.00917367,DFI,0.0230499643513991,USD,,,ref456,"""

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "income_test.csv"
            input_file.write_text(income_only_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(
                input_file=input_file, output_prefix="income_test"
            )

            # Check that processing succeeded
            assert result["success"] is True

            # Check validation results - should have no negative balance errors
            validation_results = result["csv_validation_results"]

            for _year, validation_result in validation_results.items():
                errors = validation_result["errors"]
                error_text = " ".join(errors)

                # Should not have negative currency balance errors
                assert "Negative currency balances" not in error_text
                assert "impossible" not in error_text

                # Income transactions should be valid
                if validation_result["transaction_count"] > 0:
                    # May have warnings about NOK in notes, but should be valid
                    assert (
                        validation_result["valid"] is True
                        or len([e for e in errors if "Negative" in e]) == 0
                    )

    def test_sorting_already_sorted(self, processor):
        """Test that sorter recognizes already sorted transactions"""
        from datetime import datetime
        from decimal import Decimal

        from src.models import CakeTransaction

        # Create sorted transactions (oldest to newest)
        sorted_transactions = [
            CakeTransaction(
                date=datetime(2022, 1, 1, 10, 0, 0),
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx1",
                related_reference_id=None,
            ),
            CakeTransaction(
                date=datetime(2022, 1, 2, 10, 0, 0),
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx2",
                related_reference_id=None,
            ),
            CakeTransaction(
                date=datetime(2022, 1, 3, 10, 0, 0),
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx3",
                related_reference_id=None,
            ),
        ]

        # Should return False (no sorting needed)
        needs_sorting = processor._check_if_sorting_needed(sorted_transactions)
        assert needs_sorting is False

    def test_sorting_detects_unsorted(self, processor):
        """Test that sorter detects unsorted transactions"""
        from datetime import datetime
        from decimal import Decimal

        from src.models import CakeTransaction

        # Create unsorted transactions (newest first)
        unsorted_transactions = [
            CakeTransaction(
                date=datetime(2022, 1, 3, 10, 0, 0),  # Newest first
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx3",
                related_reference_id=None,
            ),
            CakeTransaction(
                date=datetime(2022, 1, 1, 10, 0, 0),  # Oldest last
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx1",
                related_reference_id=None,
            ),
        ]

        # Should return True (sorting needed)
        needs_sorting = processor._check_if_sorting_needed(unsorted_transactions)
        assert needs_sorting is True

    def test_sorting_single_transaction(self, processor):
        """Test sorting with single transaction"""
        from datetime import datetime
        from decimal import Decimal

        from src.models import CakeTransaction

        single_transaction = [
            CakeTransaction(
                date=datetime(2022, 1, 1, 10, 0, 0),
                operation="Staking reward",
                amount=Decimal("1.0"),
                coin_asset="DFI",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="tx1",
                related_reference_id=None,
            )
        ]

        # Single transaction never needs sorting
        needs_sorting = processor._check_if_sorting_needed(single_transaction)
        assert needs_sorting is False

    def test_sorting_empty_list(self, processor):
        """Test sorting with empty transaction list"""
        needs_sorting = processor._check_if_sorting_needed([])
        assert needs_sorting is False

    def test_enhanced_income_summary_in_report(self, processor, sample_csv_content):
        """Test that enhanced income summary appears in the report"""
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test CSV file
            input_file = tmp_path / "test_input.csv"
            input_file.write_text(sample_csv_content)

            # Set output directory
            processor.output_dir = tmp_path / "output"

            # Process file
            result = processor.process_file(input_file=input_file, output_prefix="test")

            # Check summary report contains enhanced income information
            summary_file = result["files"]["summary_report"]
            summary_content = summary_file.read_text(encoding="utf-8")

            assert "💰 YOUR CAKEDEFI INCOME SUMMARY" in summary_content
            assert "Total cryptocurrency earned" in summary_content
            assert "💵 Estimated Total Value:" in summary_content
            assert "📊 Income Sources" in summary_content
            assert "🏛️ Norwegian Tax Information:" in summary_content
            assert "Tax Liability:" in summary_content
