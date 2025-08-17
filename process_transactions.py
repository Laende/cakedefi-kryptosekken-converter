"""
CakeDeFi to Kryptosekken Transaction Processor

This script processes CakeDeFi transaction exports and converts them
to kryptosekken-compatible format for Norwegian tax reporting.

Usage:
    python process_transactions.py [--input INPUT_FILE] [--output-dir OUTPUT_DIR]

Example:
    python process_transactions.py --input tx_sorted.csv --output-dir output/
"""

import argparse
from pathlib import Path
import sys

from src.main_processor import CakeTransactionProcessor


def main():
    parser = argparse.ArgumentParser(
        description="Convert CakeDeFi transactions to kryptosekken format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_transactions.py
  python process_transactions.py --input my_transactions.csv
  python process_transactions.py --input tx_sorted.csv --output-dir results/
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("input/cake_transactions.csv"),
        help="Input CakeDeFi CSV file (default: input/cake_transactions.csv)",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("output"),
        help="Output directory for processed files (default: output/)",
    )

    parser.add_argument(
        "--exr-file",
        type=Path,
        default=Path("src/data/EXR.csv"),
        help="Exchange rates file (default: src/data/EXR.csv)",
    )

    parser.add_argument(
        "--prefix",
        type=str,
        default="cake_transactions",
        help="Prefix for output files (default: cake_transactions)",
    )

    args = parser.parse_args()

    # Validate input file exists
    if not args.input.exists():
        print(f"❌ Error: Input file not found: {args.input}")
        print("   Please ensure the CakeDeFi CSV file exists.")
        return 1

    # Validate EXR file exists
    if not args.exr_file.exists():
        print(f"❌ Error: Exchange rates file not found: {args.exr_file}")
        print("   Please ensure the EXR.csv file exists.")
        return 1

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Initialize processor
        processor = CakeTransactionProcessor(
            exr_file=args.exr_file, output_dir=args.output_dir
        )

        # Process the file
        result = processor.process_file(
            input_file=args.input, output_prefix=args.prefix
        )

        # Print results
        print("\n" + "=" * 50)
        if result["success"]:
            print("🎉 PROCESSING COMPLETED SUCCESSFULLY!")
        else:
            print("⚠️  PROCESSING COMPLETED WITH ERRORS")

        print("📊 Statistics:")
        stats = result["statistics"]
        print(f"   Input transactions:  {stats['input_transactions']:,}")
        print(f"   Groups created:      {stats['grouped_transactions']:,}")
        print(f"   Output transactions: {stats['output_transactions']:,}")

        if stats["processing_errors"]:
            print(f"   Processing errors:   {len(stats['processing_errors'])}")

        if stats["validation_errors"]:
            print(f"   Validation errors:   {len(stats['validation_errors'])}")

        print(f"\n📁 Files generated in: {args.output_dir}")
        for file_type, file_path in result["files"].items():
            if file_type == "yearly_csv_files":
                print("   yearly CSV files:")
                for year, yearly_file_path in sorted(file_path.items()):
                    print(f"     {year}: {yearly_file_path.name}")
            else:
                print(f"   {file_type}: {file_path.name}")

        print("\n🚨 IMPORTANT:")
        print("   1. Review the JSON files before using the final CSV")
        print("   2. Check the summary report for any issues")
        print("   3. The final CSV is ready for kryptosekken import")
        print("   4. Ensure all transactions are correct for tax purposes")

        return 0 if result["success"] else 1

    except Exception as e:
        print(f"❌ Fatal error during processing: {str(e)}")
        import traceback

        print(f"   Traceback: {traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
