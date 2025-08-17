from decimal import Decimal
import json

import pytest

from src.balance_tracker import BalanceTracker


@pytest.fixture
def transactions_2022() -> list[dict]:
    """Sample transactions for the year 2022."""
    return [
        {
            "row": 2,
            "type": "Deposit",
            "inn": Decimal("2.5"),
            "inn_valuta": "BTC",
            "ut": None,
            "ut_valuta": None,
            "gebyr": None,
            "gebyr_valuta": None,
        },
        {
            "row": 3,
            "type": "Staking",
            "inn": Decimal("100.0"),
            "inn_valuta": "ETH",
            "ut": None,
            "ut_valuta": None,
            "gebyr": None,
            "gebyr_valuta": None,
        },
        {
            "row": 4,
            "type": "Trade",
            "inn": Decimal("5.0"),
            "inn_valuta": "LTC",
            "ut": Decimal("0.5"),
            "ut_valuta": "BTC",
            "gebyr": Decimal("1.0"),
            "gebyr_valuta": "ETH",
        },
    ]


@pytest.fixture
def transactions_2023(transactions_2022) -> list[dict]:
    """Sample transactions for 2023 that depend on 2022's balances."""
    # After 2022, balances are: BTC=2.0, ETH=99.0, LTC=5.0
    return [
        # This trade is valid because we have 2.0 BTC from the previous year
        {
            "row": 5,
            "type": "Trade",
            "inn": Decimal("15000.0"),
            "inn_valuta": "USDC",
            "ut": Decimal("1.5"),
            "ut_valuta": "BTC",
            "gebyr": None,
            "gebyr_valuta": None,
        },
        # This spend is valid because we have 99.0 ETH
        {
            "row": 6,
            "type": "Withdrawal",
            "inn": None,
            "inn_valuta": None,
            "ut": Decimal("50.0"),
            "ut_valuta": "ETH",
            "gebyr": Decimal("0.1"),
            "gebyr_valuta": "ETH",
        },
    ]


@pytest.fixture
def invalid_transactions() -> list[dict]:
    """Sample transactions where an outflow exceeds the available balance."""
    return [
        {
            "row": 2,
            "type": "Deposit",
            "inn": Decimal("1.0"),
            "inn_valuta": "BTC",
            "ut": None,
            "ut_valuta": None,
            "gebyr": None,
            "gebyr_valuta": None,
        },
        # This transaction is invalid because we only have 1.0 BTC
        {
            "row": 3,
            "type": "Withdrawal",
            "inn": None,
            "inn_valuta": None,
            "ut": Decimal("1.5"),
            "ut_valuta": "BTC",
            "gebyr": None,
            "gebyr_valuta": None,
        },
    ]


@pytest.fixture
def isolated_tracker(tmp_path) -> BalanceTracker:
    """
    Provides a BalanceTracker instance that uses a unique, temporary file
    for its state, ensuring complete isolation between tests.
    """
    balance_file = tmp_path / "state.json"
    return BalanceTracker(balance_file)


class TestBalanceTracker:
    """Groups tests for the BalanceTracker class."""

    def test_initialization_no_file(self, isolated_tracker):
        """Test that the tracker initializes with an empty history when no file exists."""
        assert not isolated_tracker.balance_history
        assert isolated_tracker.balance_file.exists() is False

    def test_load_valid_existing_state(self, tmp_path):
        """Test that the tracker correctly loads data from a valid JSON file."""
        balance_file = tmp_path / "state.json"
        initial_data = {"2022": {"BTC": "2.0", "ETH": "99.0"}}
        with open(balance_file, "w") as f:
            json.dump(initial_data, f)

        tracker = BalanceTracker(balance_file)
        assert 2022 in tracker.balance_history
        assert tracker.balance_history[2022]["BTC"] == Decimal("2.0")
        assert tracker.balance_history[2022]["ETH"] == Decimal("99.0")

    def test_load_corrupted_state(self, tmp_path, caplog):
        """Test that the tracker handles a corrupted JSON file gracefully."""
        balance_file = tmp_path / "state.json"
        balance_file.write_text("this is not json")

        tracker = BalanceTracker(balance_file)
        assert not tracker.balance_history
        assert "Could not load balance state" in caplog.text

    def test_save_and_reload_state(
        self, isolated_tracker: BalanceTracker, transactions_2022
    ):
        """Test that saving the state creates a correct file that can be reloaded."""
        # The isolated_tracker fixture provides tracker1
        tracker1 = isolated_tracker
        tracker1.process_and_validate_year(2022, transactions_2022)
        tracker1.save_balance_state()

        assert tracker1.balance_file.exists()

        # Second instance: load the saved state from the same isolated file
        tracker2 = BalanceTracker(tracker1.balance_file)
        assert 2022 in tracker2.balance_history
        assert tracker2.balance_history[2022]["BTC"] == Decimal("2.0")

    def test_process_single_year_balances(
        self, isolated_tracker: BalanceTracker, transactions_2022
    ):
        """Verify correct end-of-year balances for a single year."""
        result = isolated_tracker.process_and_validate_year(2022, transactions_2022)

        expected_balances = {
            "BTC": Decimal("2.0"),  # 2.5 in, 0.5 out
            "ETH": Decimal("99.0"),  # 100 in, 1.0 fee out
            "LTC": Decimal("5.0"),  # 5.0 in
        }
        assert result["valid"] is True
        assert result["ending_balances"] == expected_balances
        assert isolated_tracker.balance_history[2022] == expected_balances

    def test_multi_year_balance_carryover(
        self, isolated_tracker: BalanceTracker, transactions_2022, transactions_2023
    ):
        """Verify that balances are correctly carried over to the next year."""
        # Process first year
        isolated_tracker.process_and_validate_year(2022, transactions_2022)

        # Process second year
        result_2023 = isolated_tracker.process_and_validate_year(
            2023, transactions_2023
        )

        # Check that starting balances for 2023 match ending for 2022
        expected_starting_2023 = {
            "BTC": Decimal("2.0"),
            "ETH": Decimal("99.0"),
            "LTC": Decimal("5.0"),
        }
        assert result_2023["starting_balances"] == expected_starting_2023

        # Check final balances for 2023
        expected_ending_2023 = {
            "BTC": Decimal("0.5"),  # 2.0 start, 1.5 out
            "ETH": Decimal("48.9"),  # 99.0 start, 50.0 out, 0.1 fee out
            "LTC": Decimal("5.0"),
            "USDC": Decimal("15000.0"),
        }
        assert result_2023["valid"] is True
        assert result_2023["ending_balances"] == expected_ending_2023

    def test_validation_insufficient_funds(
        self, isolated_tracker: BalanceTracker, invalid_transactions
    ):
        """Test that validation fails when trying to spend more than available."""
        result = isolated_tracker.process_and_validate_year(2022, invalid_transactions)

        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "insufficient funds" in result["errors"][0]

        problem = result["problematic_transactions"][0]
        assert problem["currency"] == "BTC"
        assert problem["attempted"] == Decimal("1.5")
        assert problem["available"] == Decimal("1.0")
        assert problem["deficit"] == Decimal("0.5")

    def test_generate_report_no_data(self, isolated_tracker: BalanceTracker):
        """Test report generation when no history exists."""
        report = isolated_tracker.generate_balance_report()
        assert report == "No balance history available."
