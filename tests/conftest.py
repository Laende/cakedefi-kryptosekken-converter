from pathlib import Path
import sys

import pytest


# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_cake_csv_row():
    """Sample CakeDeFi CSV row data for testing"""
    return {
        "Date": "2022-02-02T19:36:32+01:00",
        "Operation": "Staking reward",
        "Amount": "0.5197701",
        "Coin/Asset": "ETH",
        "FIAT value": "1396.0833343587865",
        "FIAT currency": "USD",
        "Transaction ID": "0x123abc",
        "Withdrawal address": "",
        "Reference": "ref123",
        "Related reference ID": "",
    }


@pytest.fixture
def sample_swap_csv_rows():
    """Sample swap transaction group from CakeDeFi"""
    return [
        {
            "Date": "2022-02-02T20:12:09+01:00",
            "Operation": "Deposit",
            "Amount": "124.82730894",
            "Coin/Asset": "DFI",
            "FIAT value": "314.1166718520186",
            "FIAT currency": "USD",
            "Transaction ID": "d7d4d980aef15621f7bfa0eae2c9d977a02ac943b25bd113e66ee0ca7082e858",
            "Withdrawal address": "",
            "Reference": "a2d8d873-27bc-4917-816a-96155d2872a9",
            "Related reference ID": "dd3b52bc-7eeb-42ef-a194-fad96f751ecd",
        },
        {
            "Date": "2022-02-02T20:12:09+01:00",
            "Operation": "Paid swap fee",
            "Amount": "-0.00059123685",
            "Coin/Asset": "ETH",
            "FIAT value": "-1.5908828103729529",
            "FIAT currency": "USD",
            "Transaction ID": "",
            "Withdrawal address": "",
            "Reference": "1763bb37-697b-4a80-b291-33d681f9654f",
            "Related reference ID": "dd3b52bc-7eeb-42ef-a194-fad96f751ecd",
        },
        {
            "Date": "2022-02-02T20:12:09+01:00",
            "Operation": "Withdrew for swap",
            "Amount": "-0.11765613315",
            "Coin/Asset": "ETH",
            "FIAT value": "-316.5856792642176",
            "FIAT currency": "USD",
            "Transaction ID": "d7d4d980aef15621f7bfa0eae2c9d977a02ac943b25bd113e66ee0ca7082e858",
            "Withdrawal address": "",
            "Reference": "ae29ccc9-2e0f-4c43-9780-9a838d5adf3a",
            "Related reference ID": "dd3b52bc-7eeb-42ef-a194-fad96f751ecd",
        },
    ]
