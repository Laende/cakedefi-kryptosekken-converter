# CakeDeFi to Kryptosekken Tax Converter

🍰 ➡️ 🏛️ Convert Bake.io (previously known as Cake DeFi) transaction data to Norwegian tax-compliant format for Kryptosekken

## Overview

This tool converts CakeDeFi transaction exports to the format required by [Kryptosekken](https://kryptosekken.no/) (Norwegian cryptocurrency tax software). It provides:

- ✅ **Official Norges Bank USD/NOK exchange rates** 
- ✅ **Transaction grouping** to minimize Kryptosekken processing costs (94.7% reduction in my use case*)
- ✅ **validation** with detailed income analysis
- ✅ **FIFO cost basis calculations**

## ⚠️ Important Disclaimer

**This tool is provided as-is and may not be 100% accurate.** 

While it has been extensively tested and follows Norwegian tax regulations, cryptocurrency tax rules are complex and subject to interpretation. 

**You are responsible for:**
- Verifying all transaction categorizations are correct for your situation
- Reviewing all output files before submitting to tax authorities
- Ensuring compliance with current Norwegian tax laws

**Always review the generated files carefully before using them for tax reporting.**

## Features

### 🏦 Norwegian Tax Compliance
- Uses official Norges Bank exchange rates for USD to NOK conversion
- Implements FIFO (First In, First Out) method for cost basis
- Categorizes transactions according to Norwegian tax law

### 📊 Transaction Processing
- Groups related transactions (swaps, daily rewards) to reduce costs
- Handles various CakeDeFi operation types
- Validates output data for accuracy

### 💰 Your Earnings Summary
The tool provides a comprehensive analysis of your DeFi earnings:
- Total cryptocurrency earned by asset
- USD and NOK valuations using historical rates
- Tax liability calculations
- Breakdown by income source (staking, liquidity mining, etc.)

## Quick Start

### Prerequisites

- Python 3.8+
- CakeDeFi transaction export CSV file
- Internet connection (for exchange rates)

### Installation

```bash
git clone https://github.com/Laende/cakedefi-kryptosekken-converter.git
cd cakedefi-kryptosekken-converter
uv sync  # Install dependencies
```

### Basic Usage

1. **Export your CakeDeFi transactions**:
   - Log into Bake.io (formerly CakeDeFi) → Account → Transaction History
   - Export to CSV format
   - Save in the `input/` folder (any filename works, e.g., `my_transactions.csv`)

2. **Run the processor**:
   ```bash
   python process_transactions.py --input input/my_transactions.csv --output-dir output/
   ```

3. **Review the output**:
   - `output/cake_transactions_final_kryptosekken_import.csv` ← Import this to Kryptosekken
   - `output/cake_transactions_summary.txt` ← Your income summary and tax info

## Output Files

| File | Purpose |
|------|---------|
| `*_01_original.json` | Original CakeDeFi data (for debugging) |
| `*_02_groups.json` | Grouped transactions (for review) |
| `*_03_kryptosekken.json` | Final format (for review) |
| `*_final_kryptosekken_import.csv` | **Ready for Kryptosekken import** |
| `*_kryptosekken_YYYY.csv` | **Year-specific files for tax reporting** |
| `*_summary.txt` | **Your income and tax summary** |
| `*_balance_report.txt` | Balance validation and currency tracking |
| `balance_state.json` | Balance state for multi-year processing |

## Transaction Types Handled

### Income Operations (Subject to Tax)
- Staking rewards
- Liquidity mining rewards (ETH-DFI, BTC-DFI, DUSD-DFI, dToken pairs)
- Freezer staking and liquidity mining bonuses
- 5-year freezer rewards
- Earn/YieldVault rewards
- Referral and promotion bonuses
- Lending rewards
- DeFiChain voting rewards

### Trade Operations
- DeFi swaps and liquidity operations
- Token conversions
- Entry/exit staking (when withdrawing for trades)

### Transfers
- Deposits and withdrawals
- Staking/unstaking operations
- Platform transfers

### Fees
- Withdrawal fees
- Address creation fees

## Configuration

### Command Line Options

```bash
python process_transactions.py --help
```

| Option | Description | Default |
|--------|-------------|---------|
| `--input` | Input CSV file | `input/cake_transactions.csv` |
| `--output-dir` | Output directory | `output/` |
| `--prefix` | Output file prefix | `cake_transactions` |

### Exchange Rate Data

**Required**: The tool requires USD/NOK exchange rate data from Norges Bank to function correctly.

1. **Download historical exchange rates from Norges Bank**:
   - Visit: https://app.norges-bank.no/query/index.html#/no/currency
   - Select Currency: `USD`
   - Select Frequency: `Business days (B)` 
   - Set date range covering your transaction period
   - Download the CSV file (typically named `EXR.csv`)
   - Place it in the `data/` folder

2. **Example URL for 2024-2025 data**:
   ```
   https://app.norges-bank.no/query/index.html#/no/currency?currency=USD&frequency=B&startdate=2024-08-17&stopdate=2025-08-17
   ```

**Note**: The tool does not automatically fetch exchange rates online. You must download the `EXR.csv` file manually and place it in the `data/` folder before processing transactions.

### Advanced Configuration

For advanced use cases, you can modify:
- `src/operation_mapper.py` - Transaction type mappings
- `src/currency_converter.py` - Exchange rate handling
- `src/transaction_grouper.py` - Grouping logic

## Data Privacy & Security

- **No data leaves your computer** - All processing is done locally
- Exchange rates are fetched from Norges Bank's public API
- No personal information is transmitted
- All intermediate files are saved locally for your review

## Norwegian Tax Information

### Tax Rates
- **Capital gains on cryptocurrency**: 22%
- **Income from staking/mining**: Subject to income tax (22% + potential additional taxes)

### Important Notes
- This tool categorizes staking rewards as capital gains (22% tax)
- You should verify the categorization matches your tax situation
- Consider consulting a Norwegian tax advisor for complex scenarios
- The tool uses FIFO method as commonly accepted in Norway

### Getting Help

1. Check the `*_summary.txt` file for processing statistics
2. Review intermediate JSON files for data accuracy
3. Run validation scripts in `scripts/` folder
4. Open a GitHub issue with your error details

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `python -m pytest`
5. Submit a pull request

### Development Setup

```bash
# Clone and setup
git clone https://github.com/Laende/cakedefi-kryptosekken-converter.git
cd cakedefi-kryptosekken-converter
uv sync --dev  # Install dependencies including dev tools

# Code quality checks
ruff check .        # Lint code
ruff format        # Format code
ruff check . --fix # Auto-fix issues

# Run tests
python -m pytest

# Run with your data
python process_transactions.py --input your_data.csv
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Acknowledgments

- [Norges Bank](https://www.norges-bank.no/) for providing official USD/NOK exchange rates
- [Kryptosekken](https://kryptosekken.no/) for Norwegian cryptocurrency tax software

*Transaction grouping reduction percentage (94.7%) based on my use case: 37,612 original transactions reduced to 1,995 grouped transactions. Results may vary depending on transaction patterns and types.

---