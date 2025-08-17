# Input Files

Place your CakeDeFi transaction export files in this directory.

## How to Get Your CakeDeFi Data

1. **Log into CakeDeFi/Bake.io**:
   - Visit [Bake.io](https://app.bake.io) (formerly CakeDeFi)
   - Sign in to your account

2. **Navigate to Transaction History**:
   - Go to Account → Transaction History
   - Or look for "Transactions" or "History" in your dashboard

3. **Export Your Data**:
   - Look for an "Export" or "Download" button
   - Choose CSV format
   - Select the full date range of your activity
   - Download the file

4. **Place the File Here**:
   - Save the downloaded CSV file in this `input/` folder
   - You can name it anything (e.g., `my_cake_transactions.csv`)
   - The processor will automatically sort the transactions by date

## File Format

The tool expects a CSV file with these columns:
- Date
- Operation
- Amount
- Coin/Asset
- FIAT value
- Reference (optional)
- Related reference ID (optional)

**Note**: Your transaction data contains personal financial information. This folder is excluded from git to protect your privacy.

## Example Usage

Once you have your CSV file in this folder:

```bash
# If your file is named differently, specify it:
python process_transactions.py --input input/my_transactions.csv

# Or use the default name:
python process_transactions.py
```

The tool will automatically:
- ✅ Sort transactions chronologically (handles unsorted exports)
- ✅ Process all supported CakeDeFi operations
- ✅ Generate tax-compliant output for Kryptosekken